"""The model server's document parts as parsers, and the route a document takes through them.

`brain.knowledge.parse_layout`, `parse_ocr` and `parse_paths` hold the contracts, the refusals and
the rule for which reader may follow which. What none of them could do was reach a reader: there
was no server. This module is the join, and it is small on purpose: three adapters that send a
document to a part through `brain.ops.model_server_client` and read the answer with the decoders
that already exist, and one function that says, for a type of file and the readers an install has,
which readers are tried in which order.

**With no document part chosen the route is empty and the product reads exactly as it did.** An
install that runs no model server, or runs only the embedding part, has no reader but the one in
this process (`brain.knowledge.text_path`), and that path records no provenance, as every passage
written before the model server existed has none. Recording "fallback" against a reading that had
nothing to fall back from would say a weaker reader was used where no stronger one was ever there.

**The order is the paths' own, and the in-process reader is the fallback.** Layout first, then the
reader in this process, then the scanned-page reader last (`PATH_RANK`). The general reader (the
Tika part) is the fallback only for the types the in-process reader cannot open, a presentation
today: two readers on one path is refused by `route_refusals`, and for a PDF or a Word file the
reader that costs no JVM and no memory is the better second choice. **A reader that is not chosen
is not in the route**, so a type nothing chosen can read has an empty route, and the door refuses
it in the door's words before a byte is read.

**An outage is still not a reason to fall back.** Each adapter returns the refusal the parser
contracts give, and `parse_by_route` already stops on a cause that is about this system. A layout
part that is loading, busy or down returns `PARSER_UNAVAILABLE`, the route returns it, and the
ingest job is re-driven, so a document is never quietly read by the weaker reader because the
stronger one was starting.

**Every adapter checks the request ceiling itself where its contract does not.** `LayoutParser`
checks it before it asks. The scanned-page and general readers are adapters rather than parsers
of that kind, so they refuse a file over the ceiling as `OUT_OF_MEMORY` at the admit stage, the
refusal whose wording tells the uploader to split the file, because a 413 from the server reads
as this system having sent something malformed and would be retried for ever.

Task ids: M7.2.1, M7.2.3, M7.2.4, M7.7.10
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from brain.connectors.throttle import CallOutcome
from brain.knowledge.chunking import Block
from brain.knowledge.ingest import MediaType, ParseCause
from brain.knowledge.parse_layout import (
    LayoutParser,
    LayoutResponse,
    LayoutService,
    decode_layout,
    fits_request_ceiling,
    layout_provenance,
    layout_request,
)
from brain.knowledge.parse_ocr import (
    OcrEngine,
    OcrParser,
    OcrReading,
    decode_pages,
    ocr_provenance,
    read_by_page,
)
from brain.knowledge.parse_paths import ParsePath, ParseProvenance, RoutedParser
from brain.knowledge.scanning import (
    Parser,
    ParseRefusal,
    ParseStage,
    ReadWithGaps,
    ScannedContent,
)
from brain.knowledge.text_path import TextPathParser
from brain.ops.inference import parse_cause_for
from brain.ops.model_server import Part
from brain.ops.model_server_client import Reply

#: The model names a request carries to each part. Spelled as the server's own labels
#: (`inference_server.parts.ocr.LABEL`, `tika.LABEL`), which a test holds equal: the server
#: ignores the name, and a request that names nothing the server has loaded is a request nobody
#: can trace to the reader it was meant for.
OCR_MODEL: Final = "tesseract-eng-fast"
EXTRACT_MODEL: Final = "tika"

#: What the reader in this process and the general reader are recorded as. Bounded lowercase
#: names, as `ParseProvenance` requires.
TEXT_PATH_ENGINE: Final = "text-path"
EXTRACT_ENGINE: Final = "tika"


class Caller(Protocol):
    """What the adapters need of the client: send a body to a part, get an outcome."""

    def ask(self, part: Part, request: object) -> Reply: ...


def text_path_provenance() -> ParseProvenance:
    """What a document read by the reader in this process carries once a route is in use."""
    return ParseProvenance(path=ParsePath.FALLBACK, engine=TEXT_PATH_ENGINE)


def extract_provenance() -> ParseProvenance:
    """What a document read by the general reader carries."""
    return ParseProvenance(path=ParsePath.FALLBACK, engine=EXTRACT_ENGINE)


@dataclass(frozen=True)
class ServerLayout:
    """`LayoutService` over the layout part. The decoding is `LayoutParser`'s, not this class's."""

    server: Caller

    def layout(self, content: ScannedContent) -> LayoutResponse:
        reply = self.server.ask(Part.LAYOUT, layout_request(content))
        return LayoutResponse(outcome=reply.outcome, payload=reply.payload)


def _outage(stage: ParseStage, outcome: CallOutcome) -> ParseRefusal:
    cause = parse_cause_for(outcome) or ParseCause.PARSER_UNAVAILABLE
    return ParseRefusal(cause=cause, stage=stage)


def _unreadable(stage: ParseStage) -> ParseRefusal:
    return ParseRefusal(cause=ParseCause.PARSER_UNAVAILABLE, stage=stage)


def _too_large() -> ParseRefusal:
    return ParseRefusal(cause=ParseCause.OUT_OF_MEMORY, stage=ParseStage.ADMIT)


@dataclass(frozen=True)
class ServerOcr:
    """`OcrEngine` over the scanned-page part, applying the floor to each page it reports."""

    server: Caller
    ceiling_bytes: int | None = None

    def read(self, content: ScannedContent) -> OcrReading | ParseRefusal:
        if not fits_request_ceiling(content, ceiling_bytes=self.ceiling_bytes):
            return _too_large()
        reply = self.server.ask(Part.OCR, layout_request(content, model=OCR_MODEL))
        if reply.outcome is not CallOutcome.OK:
            return _outage(ParseStage.OCR, reply.outcome)
        decoded = decode_layout(reply.payload)
        if isinstance(decoded, ParseRefusal):
            if decoded.cause is ParseCause.PARSER_UNAVAILABLE:
                return _unreadable(ParseStage.OCR)
            return decoded
        pages = decode_pages(reply.payload)
        figured = {one.page for one in pages} if pages is not None else set()
        if pages is None or any(block.page not in figured for block in decoded):
            # A block on a page the answer gave no figure for is a block nobody vouches for, and
            # an answer that contradicts itself is unreadable, never a page that was sure.
            return _unreadable(ParseStage.OCR)
        return read_by_page(decoded, pages)


@dataclass(frozen=True)
class ServerExtract:
    """`Parser` over the general reader: the paragraphs of a file's text, and no metadata."""

    server: Caller
    ceiling_bytes: int | None = None

    def parse(self, content: ScannedContent) -> Sequence[Block] | ParseRefusal | ReadWithGaps:
        if not fits_request_ceiling(content, ceiling_bytes=self.ceiling_bytes):
            return _too_large()
        reply = self.server.ask(Part.TIKA, layout_request(content, model=EXTRACT_MODEL))
        if reply.outcome is not CallOutcome.OK:
            return _outage(ParseStage.TEXT, reply.outcome)
        decoded = decode_layout(reply.payload)
        if isinstance(decoded, ParseRefusal):
            if decoded.cause is ParseCause.PARSER_UNAVAILABLE:
                return _unreadable(ParseStage.TEXT)
            return decoded
        return decoded


@dataclass(frozen=True)
class DocumentServices:
    """The readers this install has, each None where its part is not chosen."""

    layout: LayoutService | None = None
    ocr: OcrEngine | None = None
    extract: Parser | None = None

    @property
    def any(self) -> bool:
        """Whether any reader is chosen, which is when a route is used at all."""
        return self.layout is not None or self.ocr is not None or self.extract is not None


def services_for(parts: Collection[Part], server: Caller) -> DocumentServices:
    """The readers for the parts an install chose, all sharing one client of the server."""
    return DocumentServices(
        layout=ServerLayout(server) if Part.LAYOUT in parts else None,
        ocr=ServerOcr(server) if Part.OCR in parts else None,
        extract=ServerExtract(server) if Part.TIKA in parts else None,
    )


def route_for(media_type: MediaType, services: DocumentServices) -> tuple[RoutedParser, ...]:
    """The readers tried for a file of this type, in the order they are tried, or none.

    Empty when no document part is chosen (the product reads as it did), and empty for a type no
    chosen reader opens. The in-process reader is in every route that has any reader, because it
    is the weaker reading a layout part's `unsupported` falls back to and costs nothing to ask.
    """
    if not services.any:
        return ()
    layout = (
        [RoutedParser(layout_provenance(), LayoutParser(service=services.layout))]
        if services.layout is not None
        else []
    )
    text = [RoutedParser(text_path_provenance(), TextPathParser())]
    ocr = (
        [RoutedParser(ocr_provenance(), OcrParser(engine=services.ocr))]
        if services.ocr is not None
        else []
    )
    extract = (
        [RoutedParser(extract_provenance(), services.extract)]
        if services.extract is not None
        else []
    )
    match media_type:
        case MediaType.PLAIN | MediaType.MARKDOWN:
            route = text
        case MediaType.PDF:
            route = [*layout, *text, *ocr]
        case MediaType.DOCX:
            route = [*layout, *text]
        case MediaType.PPTX:
            route = [*layout, *extract]
        case MediaType.PNG | MediaType.JPEG:
            route = ocr
        case _:
            route = []
    return tuple(route)


def readable_types(services: DocumentServices) -> frozenset[MediaType]:
    """The types some chosen reader opens: what a door lets through beyond the text path's four."""
    return frozenset(media for media in MediaType if route_for(media, services))
