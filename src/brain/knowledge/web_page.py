"""Reading a web page as knowledge: the words a person reads on it, laid out for citation.

A link an administrator adds is fetched once and kept as the company's own document, which is
M7.1.2's promise and the difference from a connector: nothing here is re-read later, and nothing
about the site is indexed beyond this one page. Most links are web pages, and a web page is not
words. It is markup around words, with a navigation bar, a footer, a cookie banner, scripts and
styles, and the words a person came for somewhere in the middle. This module takes the middle.

**It is a parser, so it takes `ScannedContent` and nothing else.** A page is untrusted input
chosen by whoever runs the site, and `brain.knowledge.scanning` makes reaching a parser without a
scan unspellable. `page_title` takes the same type for the same reason: reading a title is
reading markup.

**The standard library's HTML parser, and no new dependency.** `html.parser` tokenises forgivingly,
resolves character references, and executes nothing, which is the whole of what is needed to take
text out of a page as it arrived. A readability library would guess better at which block is the
article and was rejected for now: it is a dependency through the licence sweep, and the two rules
here get the ordinary page right. Those rules are that the parts no reader reads are skipped
(`SKIPPED`: scripts, styles, navigation, footers, asides, forms), and that a page which marks its
content with `main` or `article` is read from there alone.

**Tables stay tables, headings name sections, and a script-only page is a named failure.** A table
becomes a `TABLE` block of pipe rows, as `brain.knowledge.text_path` makes one from Word, so the
pricing-note rule in `brain.knowledge.kinds` sees it. A heading opens the section its following
blocks cite. And a page with no words until a browser runs its scripts is refused as
`ParseCause.SCRIPTED_PAGE`, whose remedy is to save it from a browser, rather than stored as an
item that answers nothing. See `A_PAGE_OF_SCRIPTS_IS_NOT_AN_EMPTY_DOCUMENT`.

**The page's address is its first line.** `LinkPageParser` puts "Taken from <address> on <date>"
before the page's words, so an answer citing the page carries where and when it came from, which
is the one fact a fetched-once page most needs its reader to know. The address is kept to its
scheme, host and path: a query string is where a share link carries its token, and the item's
text is read by everybody in the department it is placed in.

Task ids: M7.1.2
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from typing import Final
from urllib.parse import urlsplit, urlunsplit

from brain.knowledge.chunking import Block, BlockKind
from brain.knowledge.ingest import MediaType, ParseCause
from brain.knowledge.scanning import ParseRefusal, ParseStage, ScannedContent
from brain.knowledge.search import TITLE_CHARS
from brain.knowledge.text_path import (
    SECTION_CHARS,
    Drafted,
    TextPathParser,
    laid_out,
    pipe_row,
)

# ------------------------------------------------------------------ written-down reasons
#: Why a page with no words is refused with its own cause.
A_PAGE_OF_SCRIPTS_IS_NOT_AN_EMPTY_DOCUMENT: Final = (
    "Many pages arrive as a shell and a script that fetches the words once a browser runs it. "
    "Read as it arrived, such a page holds no words, and stored anyway it is an item that "
    "answers nothing while reading as added. The generic empty-parse cause tells the uploader "
    "the file is a scan needing OCR, which is wrong here, so the page is refused as "
    "SCRIPTED_PAGE, whose remedy is to open it in a browser and save it as a PDF."
)

# ------------------------------------------------------------------ the figures
#: Elements whose content no reader reads as the page's words. Scripts and styles are code; the
#: rest are the furniture every page on a site repeats, which would otherwise be the most common
#: passage in the knowledge layer and cite nothing useful.
SKIPPED: Final[frozenset[str]] = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "math",
        "iframe",
        "object",
        "embed",
        "canvas",
        "head",
        "nav",
        "footer",
        "aside",
        "form",
        "button",
        "select",
        "textarea",
        "dialog",
    }
)

#: Elements a page marks its own content with. When any is present, only what is inside is read.
CONTENT: Final[frozenset[str]] = frozenset({"main", "article"})

#: Elements that end one run of words and start another.
BLOCK_LEVEL: Final[frozenset[str]] = frozenset(
    {
        "address",
        "blockquote",
        "body",
        "caption",
        "dd",
        "details",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "header",
        "hr",
        "html",
        "li",
        "ol",
        "p",
        "pre",
        "section",
        "summary",
        "ul",
        *CONTENT,
    }
)

#: Headings, whose text names the section the blocks after them sit in.
HEADINGS: Final[frozenset[str]] = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

#: Elements with no end tag. Never counted as opened, so a missing close cannot unbalance a skip.
VOID: Final[frozenset[str]] = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

#: How far into a text body the markup test looks. A page's first tag is well inside this.
HTML_HEAD_BYTES: Final = 1024

#: What marks a text body as a page rather than as prose that mentions a tag.
_PAGE_MARKS: Final[tuple[bytes, ...]] = (b"<html", b"<head", b"<body")

#: The byte-order mark a UTF-8 page may begin with.
_BOM: Final = b"\xef\xbb\xbf"

#: The line put first in a page's text. Filled with the address and the date.
TAKEN_FROM: Final = "Taken from {source} on {day}."


def looks_like_html(body: bytes) -> bool:
    """Whether a text body is a web page, from its opening bytes rather than from a header.

    `Content-Type` is a claim the far end makes, and `brain.knowledge.ingest` does not believe
    claims about type. A page opens with a doctype or with one of its three structural tags
    within its first kilobyte; prose that happens to mention `<html>` rarely opens with `<`.
    """
    head = body[:HTML_HEAD_BYTES].removeprefix(_BOM).lstrip().lower()
    if head.startswith((b"<!doctype html", b"<html")):
        return True
    return head.startswith(b"<") and any(mark in head for mark in _PAGE_MARKS)


def source_of(url: str) -> str:
    """The address a page is cited by: scheme, host and path, with no query, fragment or user."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path or "/", "", ""))


# ------------------------------------------------------------------ the reader
def _words(parts: Sequence[str]) -> str:
    """Runs of text as a reader sees them: whitespace collapsed in each line, blank lines out."""
    lines = "".join(parts).split(chr(10))
    kept = (" ".join(line.split()) for line in lines)
    return chr(10).join(line for line in kept if line)


@dataclass
class _Table:
    """A table being read: its rows, the row being read, and the cell being read."""

    rows: list[list[str]] = field(default_factory=list)
    cell: list[str] | None = None


class _PageReader(HTMLParser):
    """One page's words, as drafts in reading order, each marked inside or outside the content.

    State is a handful of counters rather than a tree. A skipped element is counted by name so
    that its own close ends the skip and a stray close of something else does not; a table
    nested in a table is read as text inside the outer cell.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.drafts: list[tuple[Drafted, bool]] = []
        self.title: list[str] = []
        self._in_title = False
        self._titled = False
        self._skipping: list[str] = []
        self._content_depth = 0
        self._pre_depth = 0
        self._run: list[str] = []
        self._prefix = ""
        self._heading: list[str] | None = None
        self._section = ""
        self._table: _Table | None = None
        self._nested_tables = 0

    # -------------------------------------------------------------- emitting
    def _emit(self, text: str, *, kind: BlockKind = BlockKind.PROSE) -> None:
        if text:
            draft = Drafted(text=text, kind=kind, section=self._section[:SECTION_CHARS])
            self.drafts.append((draft, self._content_depth > 0))

    def _flush(self) -> None:
        text = "".join(self._run).strip(chr(10)) if self._pre_depth else _words(self._run)
        self._run = []
        if text:
            # The list marker waits for the item's first words, which may sit in a paragraph
            # inside the item rather than directly in it.
            text = self._prefix + text
            self._prefix = ""
        self._emit(text)

    # -------------------------------------------------------------- the parser's callbacks
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title" and not self._titled:
            # The first title is the page's; a later one is an SVG's, inside a skipped element.
            self._in_title = True
            return
        if self._skipping:
            if tag in SKIPPED and tag not in VOID:
                self._skipping.append(tag)
            return
        if tag in SKIPPED:
            if tag not in VOID:
                self._skipping.append(tag)
            return
        if tag == "br":
            self._text(chr(10))
            return
        if self._table is not None:
            self._table_start(tag)
            return
        if tag == "table":
            self._flush()
            self._table = _Table()
            return
        if tag in HEADINGS:
            self._flush()
            self._heading = []
            return
        if tag in BLOCK_LEVEL:
            self._flush()
            if tag in CONTENT:
                self._content_depth += 1
            if tag == "pre":
                self._pre_depth += 1
            if tag == "li":
                self._prefix = "- "

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br" and not self._skipping:
            self._text(chr(10))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title = False
            self._titled = True
            return
        if self._skipping:
            if tag == self._skipping[-1]:
                self._skipping.pop()
            return
        if self._table is not None:
            self._table_end(tag)
            return
        if tag in HEADINGS and self._heading is not None:
            text = _words(self._heading)
            self._heading = None
            if text:
                self._section = text
                self._emit(text)
            return
        if tag in BLOCK_LEVEL:
            self._flush()
            if tag in CONTENT and self._content_depth:
                self._content_depth -= 1
            if tag == "pre" and self._pre_depth:
                self._pre_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title.append(data)
            return
        if self._skipping:
            return
        if not self._pre_depth:
            # A line break in the markup is a space on the page; only `br` and `pre` break a line.
            data = data.replace(chr(13), " ").replace(chr(10), " ")
        self._text(data)

    def _text(self, data: str) -> None:
        if self._table is not None:
            if self._table.cell is not None:
                self._table.cell.append(data)
        elif self._heading is not None:
            self._heading.append(data)
        else:
            self._run.append(data)

    # -------------------------------------------------------------- tables
    def _table_start(self, tag: str) -> None:
        table = self._table
        assert table is not None
        if tag == "table":
            self._nested_tables += 1
        elif self._nested_tables:
            return
        elif tag == "tr":
            table.rows.append([])
            table.cell = None
        elif tag in {"td", "th"}:
            if not table.rows:
                table.rows.append([])
            table.cell = []

    def _table_end(self, tag: str) -> None:
        table = self._table
        assert table is not None
        if tag == "table":
            if self._nested_tables:
                self._nested_tables -= 1
                return
            self._close_cell()
            self._table = None
            rows = [row for row in table.rows if any(cell for cell in row)]
            self._emit(chr(10).join(pipe_row(row) for row in rows), kind=BlockKind.TABLE)
        elif not self._nested_tables and tag in {"td", "th"}:
            self._close_cell()

    def _close_cell(self) -> None:
        table = self._table
        if table is not None and table.cell is not None and table.rows:
            table.rows[-1].append(" ".join("".join(table.cell).split()))
            table.cell = None

    def finish(self) -> tuple[Drafted, ...]:
        self.close()
        if self._table is not None:
            self.handle_endtag("table")
        self._flush()
        inside = [draft for draft, within in self.drafts if within]
        return tuple(inside) if inside else tuple(draft for draft, _ in self.drafts)


def _decoded(body: bytes) -> str | None:
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def read_page(body: bytes) -> tuple[Drafted, ...] | ParseRefusal:
    """A page's words as drafts, or the cause it has none.

    Not UTF-8 is `CORRUPT`, although the structural check refuses such a body before this is
    reached; a page with no words is `SCRIPTED_PAGE`, for
    `A_PAGE_OF_SCRIPTS_IS_NOT_AN_EMPTY_DOCUMENT`.
    """
    text = _decoded(body)
    if text is None:
        return ParseRefusal(cause=ParseCause.CORRUPT, stage=ParseStage.OPEN)
    reader = _PageReader()
    try:
        reader.feed(text.replace(chr(0), ""))
        drafts = reader.finish()
    except (AssertionError, ValueError, RecursionError):
        # What the tokeniser raises on markup its authors did not foresee. The page could not be
        # read as markup, which to the person who gave the link is a page that would not open.
        return ParseRefusal(cause=ParseCause.CORRUPT, stage=ParseStage.OPEN)
    if not laid_out(drafts):
        return ParseRefusal(cause=ParseCause.SCRIPTED_PAGE, stage=ParseStage.TEXT)
    return drafts


def page_title(content: ScannedContent) -> str:
    """The page's own title, or empty. Takes scanned content: reading a title is reading markup."""
    if content.upload.media_type is not MediaType.HTML:
        return ""
    text = _decoded(content.body)
    if text is None:
        return ""
    reader = _PageReader()
    try:
        reader.feed(text.replace(chr(0), ""))
        reader.close()
    except (AssertionError, ValueError, RecursionError):
        return ""
    return " ".join("".join(reader.title).split())[:TITLE_CHARS]


# ------------------------------------------------------------------ the parser for a link
@dataclass(frozen=True)
class LinkPageParser:
    """`scanning.Parser` for whatever a link answered with, the address first.

    A web page is read here; anything else a link may answer with, a PDF, a Word document, plain
    text or Markdown, is read by `brain.knowledge.text_path.TextPathParser`, so there is one
    reader per format. Either way the blocks are laid out again with the address line before
    them, and a result with no words of its own stays a failure rather than becoming a document
    of one line.
    """

    source: str
    taken_on: date

    def parse(self, content: ScannedContent) -> Sequence[Block] | ParseRefusal:
        drafted: tuple[Drafted, ...] | ParseRefusal
        if content.upload.media_type is MediaType.HTML:
            drafted = read_page(content.body)
        else:
            blocks = TextPathParser().parse(content)
            if isinstance(blocks, ParseRefusal):
                return blocks
            drafted = tuple(
                Drafted(text=one.text, kind=one.kind, page=one.page, section=one.section)
                for one in blocks
            )
        if isinstance(drafted, ParseRefusal):
            return drafted
        if not laid_out(drafted):
            return ()
        line = TAKEN_FROM.format(source=self.source, day=self.taken_on.isoformat())
        return laid_out((Drafted(text=line), *drafted))
