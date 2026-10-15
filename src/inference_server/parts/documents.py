"""What the three document parts have in common: a request, a file for a library, and a refusal.

Layout, scanned pages and the general reader are each sent the same body, one document as base64
inside JSON with its digest and its media type, and each answers with blocks or with a refusal.
The shape is the application's (`brain.knowledge.parse_layout.layout_request` writes it), spelled
here and held equal by `tests/unit/test_inference_server_documents.py`, because the two programs
are built apart.

**A refusal is a closed vocabulary here too.** What a part may say about a document is one of the
four causes `brain.knowledge.parse_layout.CAUSES_A_PARSER_MAY_DECLARE` lets it declare and the
stage it happened at, and nothing else: a sentence a library wrote about a file is a sentence that
quotes the file. The application drops anything outside the list and reads it as an outage, so a
part that added a fifth cause would make every document with it unreadable and retried for ever.

**A library is handed a file and the file is deleted, in this process, before the answer is
sent.** The document is decoded once into a temporary file in a directory this process owns and
removed when the part is done with it, so a part that dies half way does not leave a client's
document in the container's layer for the next one to find. The temporary directory is the
container's own filesystem and never the weights volume, which is mounted read-only.

**Offsets are laid out here, the way the application lays them out.** A block carries `start`, an
offset into the document as parsed, which a citation resolves against. The application's own
text path puts one blank line between blocks (`brain.knowledge.text_path.laid_out`), and a block
the answer carries is checked against that arrangement before it is indexed, so this program lays
its blocks out the same way and a test holds the two arrangements equal.

Task ids: M7.2.1, M7.2.3, M7.2.4
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from inference_server.worker import Answer

#: The keys one request carries and one document carries. Spelled as
#: `brain.knowledge.parse_layout.REQUEST_KEYS` and `DOCUMENT_KEYS`.
REQUEST_KEYS: Final = ("model", "document")
DOCUMENT_KEYS: Final = ("digest", "media_type", "content_base64")
#: The key a request may carry beside those. Spelled as `brain.knowledge.parse_layout.
#: OPTIONAL_REQUEST_KEYS`.
OPTIONAL_REQUEST_KEYS: Final = ("pages",)

#: The most pages a request may name, which is the most pages a part reads in one request.
MOST_PAGES_NAMED: Final = 10_000

#: The causes and the stages a part may declare, spelled as the application's closed lists
#: (`CAUSES_A_PARSER_MAY_DECLARE` and `STAGES_A_PARSER_MAY_DECLARE`).
CAUSES: Final = ("encrypted", "corrupt", "unsupported", "no_text_layer")
STAGES: Final = ("open", "layout", "text", "tables", "ocr")

#: What separates two blocks in the document as parsed, and the longest section name a block
#: carries. Spelled as `brain.knowledge.text_path.BLOCK_SEPARATOR` and
#: `brain.knowledge.search.SECTION_CHARS`.
BLOCK_SEPARATOR: Final = "\n\n"
SECTION_CHARS: Final = 300

#: The suffix a library needs to choose a reader, by the media type the door proved. A type not in
#: this table is not read here, and the answer says so as `unsupported`.
SUFFIX: Final = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}


class BadRequest(Exception):  # noqa: N818 - reads as the status it becomes
    """The body is not a request this server understands, which is the application's mistake."""


class Unreadable(Exception):  # noqa: N818 - reads as the refusal it becomes
    """A library could not read the document, in one of the ways a part may say."""

    def __init__(self, cause: str, stage: str) -> None:
        super().__init__(f"{cause} at {stage}")
        self.cause = cause
        self.stage = stage


#: Exceptions that mean this program is wrong and not that the document is. They propagate, so the
#: worker reports an outage and the application retries, rather than a bug being read as a fact
#: about every document sent while it lasts and the route quietly falling back for all of them.
OUR_OWN_MISTAKES: Final = (
    AttributeError,
    ImportError,
    KeyError,
    NameError,
    NotImplementedError,
    TypeError,
)


def refusal_for(error: Exception, *, stage: str) -> Unreadable:
    """The refusal a library's exception stands for, judged by its type and never its message.

    Encrypted and corrupt only where the type's own name says so, and `unsupported` for everything
    else the library raised about a document: that is the one word that is true whatever went
    wrong inside it (this reader did not handle the file), and it is the one that lets the route
    try the next reader. A wrong `corrupt` would end the document there, and a wrong `encrypted`
    would send somebody to remove a password that is not there.
    """
    name = type(error).__name__.casefold()
    if "password" in name or "encrypt" in name:
        return Unreadable("encrypted", "open")
    if "corrupt" in name:
        return Unreadable("corrupt", "open")
    return Unreadable("unsupported", stage)


@dataclass(frozen=True)
class Document:
    """One document as the request carried it."""

    digest: str
    media_type: str
    content: bytes
    #: The pages to read, from 1, or None for every page. Only the scanned-page part looks at it.
    pages: frozenset[int] | None = None


@dataclass(frozen=True)
class Draft:
    """A block before its offset is known: its words, whether it is a table, and where it sat."""

    text: str
    kind: str = "prose"
    page: int | None = None
    section: str = ""


def read_document(body: bytes) -> Document:
    """The document in a request, or `BadRequest` saying which part of it is wrong."""
    try:
        request = json.loads(body)
    except ValueError as error:
        msg = "the body is not JSON"
        raise BadRequest(msg) from error
    if not isinstance(request, dict) or not isinstance(request.get("document"), dict):
        msg = "the request carries no document"
        raise BadRequest(msg)
    document = request["document"]
    media_type = document.get("media_type")
    encoded = document.get("content_base64")
    digest = document.get("digest")
    if not all(isinstance(one, str) and one for one in (media_type, encoded, digest)):
        msg = "the document names no type, no content or no digest"
        raise BadRequest(msg)
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        msg = "the document's content is not base64"
        raise BadRequest(msg) from error
    return Document(
        digest=digest, media_type=media_type, content=content, pages=_pages_named(request)
    )


def _pages_named(request: dict[str, object]) -> frozenset[int] | None:
    """The pages a request asks for, or None for all of them, or `BadRequest` for nonsense."""
    named = request.get("pages")
    if named is None:
        return None
    if (
        not isinstance(named, list)
        or not 0 < len(named) <= MOST_PAGES_NAMED
        or not all(isinstance(one, int) and not isinstance(one, bool) and one >= 1 for one in named)
    ):
        msg = "the pages named are not a list of page numbers from 1"
        raise BadRequest(msg)
    return frozenset(int(one) for one in named)


def bad_request(error: BadRequest) -> Answer:
    """A request this server cannot read: a 400 the application treats as its own contract."""
    return Answer(400, {"refusal": str(error)})


def refusal(cause: str, stage: str) -> Answer:
    """What a part may say about a document it opened and could not read: a cause and a stage."""
    if cause not in CAUSES or stage not in STAGES:
        msg = f"{cause!r} at {stage!r} is not something a part may declare"
        raise ValueError(msg)
    return Answer(200, {"refusal": {"cause": cause, "stage": stage}}, items=0)


def clean(text: str) -> str:
    """Words as a block holds them: no NUL, no trailing space on a line, no blank edges."""
    lines = [line.rstrip() for line in text.replace("\x00", "").splitlines()]
    return "\n".join(lines).strip()


def laid_out(drafts: Iterable[Draft]) -> list[dict[str, object]]:
    """Place drafted blocks one blank line apart and give each the offset it now sits at.

    A draft that is empty once cleaned is dropped, because a block of nothing cites a zero-width
    span. The order is the order given, which is reading order.
    """
    blocks: list[dict[str, object]] = []
    start = 0
    for draft in drafts:
        text = clean(draft.text)
        if not text:
            continue
        blocks.append(
            {
                "kind": draft.kind,
                "text": text,
                "start": start,
                "page": draft.page,
                "section": draft.section[:SECTION_CHARS],
            }
        )
        start += len(text) + len(BLOCK_SEPARATOR)
    return blocks


def blocks_answer(blocks: list[dict[str, object]], **more: object) -> Answer:
    """An answer carrying blocks, and whatever else the part says beside them."""
    return Answer(200, {"blocks": blocks, **more}, items=len(blocks))


@contextlib.contextmanager
def as_file(document: Document) -> Iterator[Path]:
    """The document as a file a library can open, removed when the caller is done with it."""
    suffix = SUFFIX.get(document.media_type)
    if suffix is None:
        msg = f"{document.media_type} is not a type a part reads"
        raise BadRequest(msg)
    with tempfile.TemporaryDirectory(prefix="document-") as directory:
        path = Path(directory) / f"document{suffix}"
        path.write_bytes(document.content)
        yield path
