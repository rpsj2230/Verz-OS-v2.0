"""Reading plain text, Markdown, PDF and Word inside the application, with nothing else running.

The layout service (`brain.knowledge.parse_layout`), the OCR path and the parse worker are the
knowledge layer's full reading path, and every one of them is a container an install has to run.
M7.6.3 asks for the other end of that: a document added from the console and answered from on an
install with no worker, no object store and no embedding server. This module is that path's
scanner and parser, and `brain.knowledge.uploads.admit_text_upload` is where they are called.

**It goes through the same gates as the full path, not round them.** The parser is a
`brain.knowledge.scanning.Parser`, so it takes `ScannedContent` and cannot be handed bytes
nobody scanned; it is called by `parse_scanned`, so the memory budget is asked before it runs and
an empty result is the named `NO_TEXT_LAYER` failure rather than an item that answers nothing; and
it reports failure as a `ParseRefusal`, a cause and a stage and no prose. A second, simpler route
for small files was rejected because the simplest route is the one every later change is made to.

**The scanner is a structural check and says so in its name.** See
`A_STRUCTURAL_CHECK_IS_NOT_AN_ANTIVIRUS`. No antivirus runs on an install this path is for, and
unscanned is not clean, so the choice was between refusing every PDF and Word file on such an
install and checking what can be checked in process. What it checks is the class of hostile file
that attacks the parser this path runs: an archive that expands without bound, an encrypted part
that cannot be looked at, a Word document carrying macros or an XML part declaring entities, and
a PDF carrying script or an embedded file. The verdict it records names it, so a later question
about why a file was let through is answered by what looked at it.

**Tables survive as tables.** A table in a Word document becomes a `TABLE` block whose rows are
pipe-separated lines, the one table syntax plain text has, so `brain.knowledge.chunking` keeps it
whole and `brain.knowledge.chunk_store.text_blocks` would read it back the same way. A pipe table
in Markdown or plain text is already one. A PDF's tables are not visible to a text layer, and
`TABLES_ARE_VISIBLE` records that per type rather than pretending otherwise; the pricing-note
rule in `brain.knowledge.kinds` reads it.

**Blocks are laid out once, with the offsets a citation resolves against.** Each block's text is
placed in the item's content separated by one blank line, and its `start` is its offset in that
content, so `content[start:end]` is the block's text exactly and a cited span points at the words
it cites. `joined` rebuilds the content from the blocks and refuses a layout that disagrees.

Nothing here opens a socket or reads a clock. It is CPU work over bytes already in memory, and the
route runs it off the event loop.

Task ids: M7.6.3, M7.2.2, M7.2.5
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

import docx
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PasswordType, PdfReader
from pypdf.errors import PyPdfError

from brain.knowledge.chunking import Block, BlockKind
from brain.knowledge.ingest import (
    SNIFF_BYTES,
    Container,
    IngestRefused,
    MediaType,
    ParseCause,
    ScanCause,
    ScanVerdict,
    sniff,
)
from brain.knowledge.scanning import ParseRefusal, ParseStage, ScannedContent, ScanReport

# ------------------------------------------------------------------ written-down reasons
#: Why the scanner on this path is named for what it is.
A_STRUCTURAL_CHECK_IS_NOT_AN_ANTIVIRUS: Final = (
    "No antivirus runs on an install with no worker, and unscanned is not clean, so the choice "
    "was between refusing every PDF and Word file there and checking in process what can be "
    "checked. This checks the shapes that attack the parser this path runs: an archive that "
    "expands without bound, a part that is encrypted, macros, a declared XML entity, and script "
    "or an embedded file in a PDF. It does not recognise malware, and its name on the scan record "
    "says which of the two looked at a file."
)

#: Why a PDF's tables are recorded as invisible rather than guessed at.
A_TEXT_LAYER_HAS_NO_TABLES: Final = (
    "A PDF's text layer is words in reading order; the cells of a table arrive as lines with the "
    "columns run together, and nothing in them says a table was there. Guessing from spacing "
    "would produce a table the document never had or miss one it did, so this path reads a PDF "
    "as prose and says it cannot see its tables. The layout service is what reads them."
)

# ------------------------------------------------------------------ the figures
#: The types this path reads. Everything else the door admits needs the layout service or OCR.
TEXT_PATH_TYPES: Final[frozenset[MediaType]] = frozenset(
    {MediaType.PLAIN, MediaType.MARKDOWN, MediaType.PDF, MediaType.DOCX}
)

#: Whether this path can see a table in a file of this type. See `A_TEXT_LAYER_HAS_NO_TABLES`.
TABLES_ARE_VISIBLE: Final[dict[MediaType, bool]] = {
    MediaType.PLAIN: True,
    MediaType.MARKDOWN: True,
    MediaType.DOCX: True,
    MediaType.PDF: False,
}

#: What separates two blocks in an item's content: one blank line, which is also where
#: `brain.knowledge.chunk_store.text_blocks` would cut them apart again.
BLOCK_SEPARATOR: Final = chr(10) * 2

#: The scanner's name on every verdict it reaches.
STRUCTURAL_CHECK: Final = "structural check (not an antivirus)"

#: The most entries one archive may hold. A Word document has tens; thousands is a construction.
MAX_ARCHIVE_ENTRIES: Final = 2000

#: The most an archive's entries may add up to once expanded. The parse budget allows a zip eight
#: times its size; this is the absolute bound under that, so a small file claiming an enormous
#: expansion is refused before anything inflates it.
MAX_EXPANDED_BYTES: Final = 256 * 1024 * 1024

#: The most one entry may expand relative to its compressed size. Word's XML deflates at about
#: ten to one and rarely past thirty; a thousand to one is a bomb.
MAX_EXPANSION_RATIO: Final = 200

#: How much of a Word part is read when looking for a declared entity. The declaration comes
#: before the root element, so the head of the part is where it has to be.
XML_HEAD_BYTES: Final = 4096

#: The parts of an Office file that are XML a parser will read: the parts and their relationships.
XML_PARTS: Final[tuple[str, ...]] = (".xml", ".rels")

#: What a Word document carrying macros holds. A `.docx` cannot run them; a file claiming to be
#: one while holding them is dressed as something it is not.
MACRO_PART: Final = "vbaproject.bin"

#: Names in a PDF that mean it carries script, launches something or holds a file. Matched on the
#: raw bytes, which misses one hidden inside a compressed object stream or spelled with a `#`
#: escape; that residue is `A_STRUCTURAL_CHECK_IS_NOT_AN_ANTIVIRUS`'s rather than claimed away.
#: `/JS` is not listed although a script action carries it, because three bytes turn up by chance
#: in the compressed streams of an ordinary large PDF, and every script action also names
#: `/JavaScript` as its type.
PDF_ACTIVE_NAMES: Final[tuple[bytes, ...]] = (
    b"/JavaScript",
    b"/Launch",
    b"/EmbeddedFile",
    b"/RichMedia",
)

#: Paragraph styles that open a section, by the prefix Word gives them in every language pack
#: that keeps the built-in names. A heading's text becomes the section its following blocks cite.
HEADING_STYLES: Final[tuple[str, ...]] = ("Heading", "Title")

#: How long a section name may be, matching `brain.knowledge.search.SECTION_CHARS`.
SECTION_CHARS: Final = 300

#: The character PostgreSQL's text type refuses, removed from anything a parser returns.
_NUL: Final = chr(0)


# ------------------------------------------------------------------ the scanner
#: A verdict and the cause the uploader is told for it; None beside a clean verdict (M7.1.3).
Judged = tuple[ScanVerdict, ScanCause | None]

_CLEAN: Final[Judged] = (ScanVerdict.CLEAN, None)


#: The most pixels one image may have: a photograph of a page is a few million, and the scanned-page
#: reader refuses a page of more than this (`inference_server.parts.ocr.MAX_PAGE_PIXELS`, which a
#: test holds equal). An image whose header claims more is how a small file is built to take a
#: reader's memory, the bomb a zip's expansion ratio is for.
MAX_IMAGE_PIXELS: Final = 100_000_000

#: The start-of-frame markers of a JPEG, which are where its size is written. `0xC4`, `0xC8` and
#: `0xCC` sit among them and are not frames.
_JPEG_FRAMES: Final = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}

#: The markers that stand alone in a JPEG, with no length after them.
_JPEG_STANDALONE: Final = frozenset({0x01, *range(0xD0, 0xDA)})


def _png_size(content: bytes) -> tuple[int, int] | None:
    """The width and height a PNG's first chunk declares, or None if it does not begin as one."""
    if len(content) < 24 or content[12:16] != b"IHDR":
        return None
    return int.from_bytes(content[16:20], "big"), int.from_bytes(content[20:24], "big")


def _jpeg_size(content: bytes) -> tuple[int, int] | None:
    """The width and height a JPEG's frame header declares, or None if none is found."""
    at = 2
    while at + 4 <= len(content):
        if content[at] != 0xFF:
            return None
        marker = content[at + 1]
        if marker == 0xFF:
            at += 1
            continue
        if marker in _JPEG_STANDALONE:
            at += 2
            continue
        if marker in _JPEG_FRAMES:
            if at + 9 > len(content):
                return None
            return (
                int.from_bytes(content[at + 7 : at + 9], "big"),
                int.from_bytes(content[at + 5 : at + 7], "big"),
            )
        at += 2 + int.from_bytes(content[at + 2 : at + 4], "big")
    return None


def _image_verdict(content: bytes, container: Container) -> Judged:
    """A photograph or scan is judged by what its header claims, because that is what a reader pays.

    Nothing here decodes a pixel. A header that cannot be read is an image that is damaged or not
    one, and one that claims more pixels than any page has is built to exhaust whatever decodes it.
    The residue is the same as for a PDF and is `A_STRUCTURAL_CHECK_IS_NOT_AN_ANTIVIRUS`'s.
    """
    size = _png_size(content) if container is Container.PNG else _jpeg_size(content)
    if size is None or size[0] < 1 or size[1] < 1:
        return ScanVerdict.UNSCANNABLE, ScanCause.UNOPENABLE
    if size[0] * size[1] > MAX_IMAGE_PIXELS:
        return ScanVerdict.INFECTED, ScanCause.EXPANDS_WITHOUT_BOUND
    return _CLEAN


def _archive_verdict(content: bytes) -> Judged:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                return ScanVerdict.INFECTED, ScanCause.EXPANDS_WITHOUT_BOUND
            if sum(one.file_size for one in entries) > MAX_EXPANDED_BYTES:
                return ScanVerdict.INFECTED, ScanCause.EXPANDS_WITHOUT_BOUND
            for one in entries:
                if one.flag_bits & 0x1:
                    # An encrypted part is one nothing can look inside, which is unscannable.
                    return ScanVerdict.UNSCANNABLE, ScanCause.ENCRYPTED_PART
                if one.file_size > MAX_EXPANSION_RATIO * max(one.compress_size, 1):
                    return ScanVerdict.INFECTED, ScanCause.EXPANDS_WITHOUT_BOUND
                if one.filename.lower().rsplit("/", 1)[-1] == MACRO_PART:
                    return ScanVerdict.INFECTED, ScanCause.MACROS
            for one in entries:
                if one.filename.lower().endswith(XML_PARTS):
                    with archive.open(one) as part:
                        if b"<!DOCTYPE" in part.read(XML_HEAD_BYTES).upper():
                            return ScanVerdict.INFECTED, ScanCause.XML_ENTITIES
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError, RuntimeError):
        # A zip the standard library cannot open is one this check cannot judge. The parser is
        # never reached, because unscannable is refused at the gate.
        return ScanVerdict.UNSCANNABLE, ScanCause.UNOPENABLE
    return _CLEAN


def _pdf_verdict(content: bytes) -> Judged:
    if any(name in content for name in PDF_ACTIVE_NAMES):
        return ScanVerdict.INFECTED, ScanCause.ACTIVE_CONTENT
    return _CLEAN


def _text_verdict(content: bytes) -> Judged:
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        return ScanVerdict.UNSCANNABLE, ScanCause.NOT_READABLE_TEXT
    if _NUL in decoded:
        return ScanVerdict.UNSCANNABLE, ScanCause.NOT_READABLE_TEXT
    return _CLEAN


@dataclass(frozen=True)
class StructuralCheck:
    """The scanner this path clears a file with. See `A_STRUCTURAL_CHECK_IS_NOT_AN_ANTIVIRUS`.

    It is told nothing but the bytes, as `brain.knowledge.scanning.Scanner` requires, and reads
    the container from them itself. A container it cannot judge is unscannable here, which the
    gate refuses. A photograph or a scan is judged by what its header claims (`_image_verdict`),
    because the scanned-page reader is handed them; before that reader existed an image reaching
    this check was a caller that had skipped the type question, and the answer was no.
    """

    def scan(self, content: bytes) -> ScanReport:
        container = sniff(content[:SNIFF_BYTES])
        match container:
            case Container.ZIP:
                verdict, cause = _archive_verdict(content)
            case Container.PDF:
                verdict, cause = _pdf_verdict(content)
            case Container.TEXT:
                verdict, cause = _text_verdict(content)
            case Container.PNG | Container.JPEG:
                verdict, cause = _image_verdict(content, container)
            case Container.UNKNOWN:
                verdict, cause = ScanVerdict.UNSCANNABLE, ScanCause.NOT_CHECKABLE
        return ScanReport(verdict=verdict, scanner=STRUCTURAL_CHECK, cause=cause)


# ------------------------------------------------------------------ laying blocks out
@dataclass(frozen=True)
class Drafted:
    """A block before its offset is known: its words, whether it is a table, and where it sat."""

    text: str
    kind: BlockKind = BlockKind.PROSE
    page: int | None = None
    section: str = ""
    #: How it was read, when the reader that drafted it is not the one that will be recorded for
    #: the rest of the document (a scanned page filled in beside a layout read). Empty otherwise.
    path: str = ""
    engine: str = ""


def _clean(text: str) -> str:
    """Words as a block holds them: no NUL, no trailing space on a line, no blank edges."""
    lines = [line.rstrip() for line in text.replace(_NUL, "").splitlines()]
    return chr(10).join(lines).strip()


def laid_out(drafts: Iterable[Drafted]) -> tuple[Block, ...]:
    """Place drafted blocks one blank line apart and give each the offset it now sits at.

    A draft whose text is empty once cleaned is dropped rather than laid out, because a block of
    nothing would cite a zero-width span. The order is the order given, which is reading order.
    """
    blocks: list[Block] = []
    start = 0
    for draft in drafts:
        text = _clean(draft.text)
        if not text:
            continue
        blocks.append(
            Block(
                kind=draft.kind,
                text=text,
                start=start,
                page=draft.page,
                section=draft.section[:SECTION_CHARS],
                path=draft.path,
                engine=draft.engine,
            )
        )
        start += len(text) + len(BLOCK_SEPARATOR)
    return tuple(blocks)


def joined(blocks: Sequence[Block]) -> str:
    """The content these blocks were laid out from, or a refusal if their offsets disagree.

    The refusal is the check that makes a citation span trustworthy: a block whose `start` is not
    where its text sits in the content would cite words it does not contain.
    """
    content = BLOCK_SEPARATOR.join(block.text for block in blocks)
    for block in blocks:
        if content[block.start : block.end] != block.text:
            msg = (
                f"a block laid out at {block.start} is not where its text sits in the content, "
                "so a citation to it would point at other words"
            )
            raise IngestRefused(msg)
    return content


def pipe_row(cells: Sequence[str]) -> str:
    """One table row as a pipe-separated line. A pipe inside a cell becomes a slash."""
    return "| " + " | ".join(" ".join(cell.replace("|", "/").split()) for cell in cells) + " |"


# ------------------------------------------------------------------ the three readers
def _plain(body: bytes, *, headings: bool) -> tuple[Drafted, ...] | ParseRefusal:
    """Blocks are runs of lines between blank lines, as `chunk_store.text_blocks` cuts them.

    A run whose every line begins with a pipe is a table. With `headings`, a run opening with a
    Markdown heading names the section it and the runs after it sit in.
    """
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ParseRefusal(cause=ParseCause.CORRUPT, stage=ParseStage.OPEN)
    runs: list[list[str]] = [[]]
    for line in text.replace(_NUL, "").splitlines():
        if line.strip():
            runs[-1].append(line)
        elif runs[-1]:
            runs.append([])
    drafts: list[Drafted] = []
    section = ""
    for run in runs:
        if not run:
            continue
        first = run[0].strip()
        if headings and first.startswith("#"):
            section = first.lstrip("#").strip()
        is_table = all(line.strip().startswith("|") for line in run)
        drafts.append(
            Drafted(
                text=chr(10).join(run),
                kind=BlockKind.TABLE if is_table else BlockKind.PROSE,
                section=section,
            )
        )
    return tuple(drafts)


#: What a hostile file can make a parser library raise from inside its own code. Caught only
#: around library calls over the file, where nothing of ours runs, so what arrives is the file's
#: shape reaching a path the library's authors did not guard, and the uploader is told it could
#: not be opened. `brain.knowledge.scanning` rejects reporting such a thing as the parser being
#: unavailable, because that tells the uploader nothing is wrong with the file; corrupt tells
#: them to re-export it, which is the remedy that works.
_LIBRARY_FAULTS: Final = (
    ValueError,
    KeyError,
    IndexError,
    TypeError,
    AttributeError,
    RecursionError,
    SyntaxError,
)


def _pdf(body: bytes) -> tuple[Drafted, ...] | ParseRefusal:
    try:
        reader = PdfReader(io.BytesIO(body))
        if reader.is_encrypted and reader.decrypt("") is PasswordType.NOT_DECRYPTED:
            return ParseRefusal(cause=ParseCause.ENCRYPTED, stage=ParseStage.OPEN)
        pages = list(reader.pages)
    except (PyPdfError, *_LIBRARY_FAULTS):
        return ParseRefusal(cause=ParseCause.CORRUPT, stage=ParseStage.OPEN)
    except NotImplementedError:
        # pypdf raises this for an encryption scheme it cannot open, which to the uploader is a
        # password-protected file like any other.
        return ParseRefusal(cause=ParseCause.ENCRYPTED, stage=ParseStage.OPEN)
    drafts: list[Drafted] = []
    for number, page in enumerate(pages, start=1):
        try:
            text = page.extract_text()
        except (PyPdfError, *_LIBRARY_FAULTS):
            return ParseRefusal(cause=ParseCause.CORRUPT, stage=ParseStage.TEXT)
        drafts.append(Drafted(text=text, page=number))
    return tuple(drafts)


def _word(body: bytes) -> tuple[Drafted, ...] | ParseRefusal:
    try:
        document = docx.Document(io.BytesIO(body))
    except (PackageNotFoundError, KeyError):
        # A zip that is not a Word document: the question the door left for the parser.
        return ParseRefusal(cause=ParseCause.UNSUPPORTED, stage=ParseStage.OPEN)
    except (zipfile.BadZipFile, *_LIBRARY_FAULTS):
        return ParseRefusal(cause=ParseCause.CORRUPT, stage=ParseStage.OPEN)
    drafts: list[Drafted] = []
    prose: list[str] = []
    section = ""

    def flush() -> None:
        if prose:
            drafts.append(Drafted(text=chr(10).join(prose), section=section))
            prose.clear()

    for part in document.iter_inner_content():
        if isinstance(part, Paragraph):
            style = part.style.name if part.style is not None else ""
            if style and style.startswith(HEADING_STYLES) and part.text.strip():
                flush()
                section = part.text.strip()
            prose.append(part.text)
        elif isinstance(part, Table):
            flush()
            rows = [pipe_row([cell.text for cell in row.cells]) for row in part.rows]
            drafts.append(Drafted(text=chr(10).join(rows), kind=BlockKind.TABLE, section=section))
    flush()
    return tuple(drafts)


def pages_without_text(body: bytes) -> tuple[int, ...]:
    """The pages of a PDF whose text layer holds nothing, from 1, or none where that cannot be said.

    Asked of the text layer and not of a model, so it is the same statement whichever reader read
    the rest: a page of a photograph has a picture and no text, and a scanned document read by the
    layout part comes back with its text pages and none of these. An unreadable file says nothing
    (an empty tuple), because "I could not open it" is not "every page is blank".
    """
    try:
        reader = PdfReader(io.BytesIO(body))
        if reader.is_encrypted and reader.decrypt("") is PasswordType.NOT_DECRYPTED:
            return ()
        return tuple(
            number
            for number, page in enumerate(reader.pages, start=1)
            if not page.extract_text().strip()
        )
    except (PyPdfError, NotImplementedError, *_LIBRARY_FAULTS):
        return ()


@dataclass(frozen=True)
class TextPathParser:
    """Plain text, Markdown, PDF and Word, as blocks laid out for citation.

    A `brain.knowledge.scanning.Parser`: it takes scanned content and returns blocks or a
    refusal naming a cause and a stage. A type outside `TEXT_PATH_TYPES` is `UNSUPPORTED`, which
    tells the uploader to save it as PDF or Word. Nothing a parser library raises beyond the ones
    named here is caught, for `brain.knowledge.scanning`'s reason: an exception out of a parser is
    out of contract and belongs to the caller as a bug.
    """

    def parse(self, content: ScannedContent) -> Sequence[Block] | ParseRefusal:
        media_type = content.upload.media_type
        drafted: tuple[Drafted, ...] | ParseRefusal
        match media_type:
            case MediaType.PLAIN:
                drafted = _plain(content.body, headings=False)
            case MediaType.MARKDOWN:
                drafted = _plain(content.body, headings=True)
            case MediaType.PDF:
                drafted = _pdf(content.body)
            case MediaType.DOCX:
                drafted = _word(content.body)
            case _:
                return ParseRefusal(cause=ParseCause.UNSUPPORTED, stage=ParseStage.OPEN)
        if isinstance(drafted, ParseRefusal):
            return drafted
        return laid_out(drafted)
