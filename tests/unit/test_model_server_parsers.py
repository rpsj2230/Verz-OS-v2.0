"""The model server's document parts as parsers: what a file is sent, what is read back, and which
reader a document goes to.

The server itself is a stand-in here (a caller that answers what the test scripted), because the
cases that matter are a part that is loading, one that answers with something nobody expected, a
scan whose pages are sure and unsure by turns, and a route in an order that would produce a worse
corpus without raising. What is held against real code is everything on this side of the wire: the
decoders, the floor, the route, the door and the job's refusal to end a document over an outage.

Task ids: M7.2.1, M7.2.3, M7.2.4, M7.7.10
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from typing import Any

import pytest

from brain.connectors.throttle import CallOutcome
from brain.knowledge.chunking import Block, BlockKind
from brain.knowledge.ingest import (
    AdmittedUpload,
    IngestRefused,
    MediaType,
    ParseCause,
    ParseFailure,
    ScanCause,
    ScanVerdict,
    admit_upload,
)
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.model_server_parsers import (
    EXTRACT_ENGINE,
    EXTRACT_MODEL,
    OCR_MODEL,
    TEXT_PATH_ENGINE,
    DocumentServices,
    ServerExtract,
    ServerLayout,
    ServerOcr,
    readable_types,
    route_for,
    services_for,
)
from brain.knowledge.parse_layout import LAYOUT_ENGINE, LayoutParser
from brain.knowledge.parse_ocr import (
    NOTICE_CHARS,
    OCR_FLOOR_CONFIDENCE,
    OcrPage,
    OcrParser,
    OcrReading,
    decode_pages,
    left_out_notice,
    page_ranges,
    read_by_page,
)
from brain.knowledge.parse_paths import ParsePath, route_refusals
from brain.knowledge.scanning import (
    ParsedDocument,
    ParseRefusal,
    ParseStage,
    ReadWithGaps,
    ScannedContent,
    ScanReport,
    parse_scanned,
    scan_for_parsing,
)
from brain.knowledge.text_path import MAX_IMAGE_PIXELS, StructuralCheck, joined
from brain.knowledge.uploads import ReadUpload, ReceivedUpload, read_for_text_path, text_path_type
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.model_server import Part
from brain.ops.model_server_client import Reply
from inference_server.parts import layout as layout_server
from inference_server.parts import ocr as server_ocr
from inference_server.parts import tika as server_tika
from tests.fixtures.documents import a_pdf

OWNER = "u_uploader"
FLOOR = OCR_FLOOR_CONFIDENCE


class _Clean:
    def scan(self, content: bytes) -> ScanReport:
        return ScanReport(verdict=ScanVerdict.CLEAN, scanner="fake-av")


def _upload(content: bytes, media_type: MediaType, filename: str = "scan.pdf") -> AdmittedUpload:
    return admit_upload(filename=filename, declared_type=media_type.value, content=content)


def _cleared(content: bytes | None = None, media_type: MediaType = MediaType.PDF) -> ScannedContent:
    body = content if content is not None else a_pdf("Quarterly report")
    return scan_for_parsing(_upload(body, media_type), body, scanner=_Clean())


class _Server:
    """Answers each part with what the test scripted, and keeps what it was asked."""

    def __init__(self, **replies: Reply) -> None:
        self.replies = {Part(name): reply for name, reply in replies.items()}
        self.asked: list[tuple[Part, Any]] = []

    def ask(self, part: Part, request: object) -> Reply:
        self.asked.append((part, request))
        return self.replies.get(part, Reply(CallOutcome.UNAVAILABLE))


def _ok(payload: Mapping[str, object]) -> Reply:
    return Reply(CallOutcome.OK, payload)


def _entry(text: str, start: int, page: int | None, kind: str = "prose") -> dict[str, object]:
    return {"kind": kind, "text": text, "start": start, "page": page, "section": ""}


def _block(text: str, start: int, page: int, kind: BlockKind = BlockKind.PROSE) -> Block:
    return Block(kind=kind, text=text, start=start, page=page)


# ------------------------------------------------------------------ the floor, page by page
def test_a_page_under_the_floor_is_left_out_and_every_offset_after_it_is_true_of_what_is_kept() -> (
    None
):
    """Blocks of pages 1, 2 and 3, the middle one unsure: the kept blocks are laid out again so
    each `start` is where its text sits in the kept content, and page 2 is named as left out.

    Delete this and the second block keeps the offset it had with the middle page in front of it,
    so a citation to it resolves against the wrong words (the application's own `joined` refuses
    exactly that)."""
    blocks = (
        _block("first page", 0, 1),
        _block("garbled middle", len("first page") + 2, 2),
        _block("third page", len("first page") + 2 + len("garbled middle") + 2, 3),
    )
    pages = (OcrPage(1, 0.9), OcrPage(2, FLOOR / 2), OcrPage(3, 0.8))

    reading = read_by_page(blocks, pages)

    assert [(block.text, block.page) for block in reading.blocks] == [
        ("first page", 1),
        ("third page", 3),
    ]
    assert joined(reading.blocks) == "first page\n\nthird page"
    assert reading.left_out_pages == (2,)
    assert reading.confidence == pytest.approx(0.85)


def test_a_page_exactly_at_the_floor_is_kept_and_one_under_it_is_not() -> None:
    """The floor is inclusive, as `OcrReading.is_legible` is.

    Delete this and a page the engine was exactly as sure of as the floor is dropped by one
    path and kept by the other."""
    kept = read_by_page((_block("at", 0, 1),), (OcrPage(1, FLOOR),))
    dropped = read_by_page((_block("under", 0, 1),), (OcrPage(1, FLOOR - 0.01),))

    assert kept.blocks and not kept.left_out_pages
    assert not dropped.blocks and dropped.left_out_pages == (1,)


def test_a_page_with_no_recognised_word_is_not_named_as_left_out() -> None:
    """A blank back side reports 0 and has no blocks: nothing was read from it, so nothing was
    left out and the uploader is not told about it.

    Delete this and every scan with a blank page tells its uploader a page was unclear."""
    reading = read_by_page((_block("front", 0, 1),), (OcrPage(1, 0.9), OcrPage(2, 0.0)))

    assert reading.left_out_pages == ()


def test_a_block_on_a_page_nobody_scored_is_left_out() -> None:
    """A block whose page has no figure is a block nobody vouches for.

    Delete this and text with no confidence is indexed beside text that has one."""
    reading = read_by_page((_block("unscored", 0, 4),), (OcrPage(1, 0.9),))

    assert reading.blocks == ()
    assert reading.left_out_pages == (4,)


def test_a_scan_whose_every_page_is_unsure_is_illegible_and_not_an_empty_document() -> None:
    """With nothing kept the reading has no blocks, and the parser says `ILLEGIBLE`, the cause
    whose remedy is a clearer scan, and never `NO_TEXT_LAYER`.

    Delete this and a scan of noise tells its uploader to run it through the scanned-page reader
    that has just refused it."""
    reading = read_by_page((_block("noise", 0, 1),), (OcrPage(1, 0.1),))

    outcome = OcrParser(engine=_FixedEngine(reading)).parse(_cleared())

    assert outcome == ParseRefusal(cause=ParseCause.ILLEGIBLE, stage=ParseStage.OCR)


class _FixedEngine:
    def __init__(self, reading: OcrReading | ParseRefusal) -> None:
        self.reading = reading

    def read(self, content: ScannedContent) -> OcrReading | ParseRefusal:
        return self.reading


def test_a_scan_read_in_part_carries_the_pages_it_left_out_to_the_parsed_document() -> None:
    """The pages travel from the engine through the parser and the gate to the document the
    knowledge layer receives, as numbers.

    Delete this and the uploader is never told which pages of their scan were not added."""
    reading = read_by_page(
        (_block("clear", 0, 1), _block("smudged", 7, 2)), (OcrPage(1, 0.9), OcrPage(2, 0.2))
    )

    document = parse_scanned(_cleared(), parser=OcrParser(engine=_FixedEngine(reading)))

    assert isinstance(document, ParsedDocument)
    assert [block.text for block in document.blocks] == ["clear"]
    assert document.left_out_pages == (2,)


def test_a_scan_read_whole_leaves_no_page_out() -> None:
    """The positive sibling: every page sure, none named, and the blocks are returned as they
    are rather than wrapped. Delete this and the gap wrapper is applied to every scan."""
    reading = read_by_page((_block("clear", 0, 1),), (OcrPage(1, 0.9),))

    outcome = OcrParser(engine=_FixedEngine(reading)).parse(_cleared())

    assert not isinstance(outcome, (ParseRefusal, ReadWithGaps))
    assert tuple(outcome) == reading.blocks


# ------------------------------------------------------------------ what the uploader is told
def test_the_notice_names_the_pages_in_the_uploaders_own_numbers_and_nothing_the_file_says() -> (
    None
):
    """Pages are written as runs (`3, 7 to 9, 12`), one page is singular and several plural, and
    nothing but numbers and fixed words appears.

    Delete this and the notice is a sentence nobody wrote down, free to grow a snippet of the
    page it describes."""
    assert page_ranges([12, 3, 7, 8, 9, 3]) == "3, 7 to 9, 12"
    assert left_out_notice([4]).startswith("Page 4 was not clear enough")
    assert left_out_notice([4, 6]).startswith("Pages 4, 6 were not clear enough")
    assert left_out_notice([]) == ""
    assert left_out_notice([2, 5, 6]).startswith("Pages 2, 5 to 6 were not clear enough")


def test_a_notice_that_would_not_fit_its_column_says_how_many_pages_instead() -> None:
    """Two hundred scattered pages cannot be listed in the 400 characters the column has, so the
    count is said, which is still true and still sends the uploader to the scan.

    Delete this and a long list is cut by the database mid-number or refuses the whole item."""
    scattered = list(range(1, 400, 2))

    notice = left_out_notice(scattered)

    assert len(notice) <= NOTICE_CHARS
    assert notice.startswith(f"{len(scattered)} pages of this scan")


# ------------------------------------------------------------------ the scanned-page reader
def _ocr_answer(*entries: dict[str, object], pages: object = None) -> Reply:
    return _ok({"blocks": list(entries), "pages": pages if pages is not None else []})


def test_the_scanned_page_reader_applies_the_floor_to_the_pages_the_server_reports() -> None:
    """End to end through the adapter and the parser over a scripted answer: page 1 sure, page 2
    unsure, page 3 blank. One block is kept, the middle page is named, the blank is not.

    Delete this and the adapter can ignore `pages` and index every block the server sent."""
    server = _Server(
        ocr=_ocr_answer(
            _entry("clear page", 0, 1),
            _entry("smudge", 12, 2),
            pages=[
                {"page": 1, "confidence": 0.93},
                {"page": 2, "confidence": 0.31},
                {"page": 3, "confidence": 0.0},
            ],
        )
    )

    outcome = OcrParser(engine=ServerOcr(server)).parse(_cleared())

    assert isinstance(outcome, ReadWithGaps)
    assert [block.text for block in outcome.blocks] == ["clear page"]
    assert outcome.left_out_pages == (2,)
    [(part, request)] = server.asked
    assert part is Part.OCR
    assert request["model"] == OCR_MODEL


@pytest.mark.parametrize(
    "reply",
    [
        _ok({"blocks": [_entry("x", 0, 1)]}),
        _ocr_answer(_entry("x", 0, 1), pages=[{"page": 2, "confidence": 0.9}]),
        _ocr_answer(_entry("x", 0, 1), pages=[{"page": 1, "confidence": 1.5}]),
        _ocr_answer(_entry("x", 0, 1), pages=[{"page": True, "confidence": 0.9}]),
        _ocr_answer(_entry("x", 0, 1), pages=[{"page": 1, "confidence": True}]),
        _ocr_answer(
            _entry("x", 0, 1),
            pages=[{"page": 1, "confidence": 0.9}, {"page": 1, "confidence": 0.9}],
        ),
        _ocr_answer(_entry("x", 0, 1), pages="all of them"),
    ],
)
def test_an_answer_that_contradicts_itself_about_its_pages_is_unreadable_and_not_sure(
    reply: Reply,
) -> None:
    """No `pages`, a block on a page nobody scored, a figure over 1, a boolean page number, a page
    named twice and a `pages` that is not a list: each is the server's answer being unreadable, an
    outage the queue retries, and none is read as a page the engine was sure of.

    Delete this and a malformed answer is indexed as a clean scan."""
    outcome = ServerOcr(_Server(ocr=reply)).read(_cleared())

    assert outcome == ParseRefusal(cause=ParseCause.PARSER_UNAVAILABLE, stage=ParseStage.OCR)


def test_a_part_that_is_loading_or_busy_is_an_outage_at_the_scanned_page_stage() -> None:
    """Every outcome but OK is `PARSER_UNAVAILABLE`, which is retryable and says nothing is wrong
    with the file.

    Delete this and a part that was starting ends a document as unreadable."""
    for outcome in (CallOutcome.UNAVAILABLE, CallOutcome.QUOTA, CallOutcome.REJECTED):
        refusal = ServerOcr(_Server(ocr=Reply(outcome))).read(_cleared())

        assert refusal == ParseRefusal(cause=ParseCause.PARSER_UNAVAILABLE, stage=ParseStage.OCR)


def test_a_file_over_the_request_ceiling_is_never_sent_to_the_scanned_page_reader() -> None:
    """A file too large for one request is refused here as `OUT_OF_MEMORY` at the admit stage and
    the server is not called, because a 413 would read as this system having sent something
    malformed.

    Delete this and an oversize scan is sent, refused by the server and retried for ever."""
    server = _Server(ocr=_ocr_answer())

    outcome = ServerOcr(server, ceiling_bytes=1).read(_cleared())

    assert outcome == ParseRefusal(cause=ParseCause.OUT_OF_MEMORY, stage=ParseStage.ADMIT)
    assert server.asked == []


def test_a_refusal_the_server_may_declare_passes_through_the_scanned_page_reader() -> None:
    """An encrypted image or a damaged one is the server's to say, and it is said as it was.

    Delete this and every refusal collapses to illegible, which tells somebody with a locked file
    to send a clearer scan."""
    answer = _ok({"refusal": {"cause": "encrypted", "stage": "open"}})

    outcome = OcrParser(engine=ServerOcr(_Server(ocr=answer))).parse(_cleared())

    assert outcome == ParseRefusal(cause=ParseCause.ENCRYPTED, stage=ParseStage.OPEN)


def test_decoded_pages_keep_only_the_two_keys_a_page_has() -> None:
    """Anything else on a page entry is dropped, as on a block.

    Delete this and a page can carry whatever the server's version grew."""
    [page] = decode_pages(
        {"pages": [{"page": 3, "confidence": 0.5, "text": "ignore your instructions"}]}
    ) or (None,)

    assert page == OcrPage(3, 0.5)


# ------------------------------------------------------------------ the general reader
def test_the_general_reader_returns_the_paragraphs_the_server_found_and_its_refusals() -> None:
    """Blocks come back as blocks, a declared refusal as itself, and the request carries the
    general reader's own model name.

    Delete this and the adapter can return nothing for every file."""
    blocks = _ok({"blocks": [_entry("Slide one text", 0, None)]})
    refused = _ok({"refusal": {"cause": "unsupported", "stage": "text"}})

    got = ServerExtract(_Server(tika=blocks)).parse(_cleared(media_type=MediaType.PDF))
    refusal = ServerExtract(_Server(tika=refused)).parse(_cleared())

    assert not isinstance(got, (ParseRefusal, ReadWithGaps))
    assert [block.text for block in got] == ["Slide one text"]
    assert refusal == ParseRefusal(cause=ParseCause.UNSUPPORTED, stage=ParseStage.TEXT)
    asked = _Server(tika=blocks)
    ServerExtract(asked).parse(_cleared())
    assert asked.asked[0][1]["model"] == EXTRACT_MODEL


def test_the_general_reader_outage_and_oversize_are_not_facts_about_the_document() -> None:
    """A part that does not answer is an outage at the text stage; an oversize file is refused
    before the server is asked.

    Delete this and the general reader ends documents because a JVM was starting."""
    down = ServerExtract(_Server()).parse(_cleared())
    server = _Server(tika=_ok({"blocks": []}))
    big = ServerExtract(server, ceiling_bytes=1).parse(_cleared())

    assert down == ParseRefusal(cause=ParseCause.PARSER_UNAVAILABLE, stage=ParseStage.TEXT)
    assert big == ParseRefusal(cause=ParseCause.OUT_OF_MEMORY, stage=ParseStage.ADMIT)
    assert server.asked == []


# ------------------------------------------------------------------ the layout reader
def test_the_layout_reader_reads_the_answer_with_the_decoder_that_guards_the_corpus() -> None:
    """The adapter hands the body and the outcome to `LayoutParser`, which is what refuses a
    hostile answer: a block that runs backwards is unreadable, a good one is a block.

    Delete this and the adapter decodes for itself and the one boundary for untrusted answers
    has two copies."""
    good = _Server(layout=_ok({"blocks": [_entry("A heading", 0, 1)]}))
    hostile = _Server(layout=_ok({"blocks": [_entry("a", 5, 1), _entry("b", 0, 1)]}))

    read = LayoutParser(service=ServerLayout(good)).parse(_cleared())
    refused = LayoutParser(service=ServerLayout(hostile)).parse(_cleared())

    assert not isinstance(read, ParseRefusal) and [block.text for block in read] == ["A heading"]
    assert refused == ParseRefusal(cause=ParseCause.PARSER_UNAVAILABLE, stage=ParseStage.TEXT)
    assert good.asked[0][0] is Part.LAYOUT


# ------------------------------------------------------------------ the route
ALL_PARTS = (Part.LAYOUT, Part.OCR, Part.TIKA)


def _services(*parts: Part) -> DocumentServices:
    return services_for(parts, _Server())


def test_with_no_document_part_the_route_is_empty_for_every_type() -> None:
    """An install that runs no server, or only the embedding part, reads as it always did: no
    route, no provenance.

    Delete this and every install is told its text-path reads are a fallback from a reader it
    never had."""
    for parts in ((), (Part.EMBEDDING,), (Part.ENTITIES,)):
        services = _services(*parts)
        assert not services.any
        assert all(route_for(media, services) == () for media in MediaType)
        assert readable_types(services) == frozenset()


def test_every_route_for_every_choice_of_parts_is_one_the_paths_own_rule_accepts() -> None:
    """For every subset of the three document parts and every type, the route is in the paths'
    order, repeats no path and, where it has readers, is not refused by `route_refusals`.

    Delete this and a part added to a route in the wrong place produces a worse corpus with no
    error, the failure the paths exist to prevent."""
    for size in range(1, 4):
        for chosen in itertools.combinations(ALL_PARTS, size):
            services = _services(*chosen)
            for media in MediaType:
                route = route_for(media, services)
                if route:
                    assert route_refusals(route) == (), (chosen, media)


def test_a_pdf_goes_layout_then_the_reader_in_this_process_then_the_scanned_page_reader() -> None:
    """The order for a PDF with everything chosen, and what each is recorded as.

    Delete this and OCR can precede a reader that would have read the text layer, replacing text
    that was read with glyphs that were guessed."""
    route = route_for(MediaType.PDF, _services(*ALL_PARTS))

    assert [(one.provenance.path, one.provenance.engine) for one in route] == [
        (ParsePath.LAYOUT, "docling-layout-and-tableformer"),
        (ParsePath.FALLBACK, TEXT_PATH_ENGINE),
        (ParsePath.OCR, "docling-ocr"),
    ]


def test_each_type_is_opened_only_by_the_readers_chosen_for_it() -> None:
    """A presentation needs the layout or the general reader; a photograph needs the scanned-page
    reader; a Word file and a PDF keep the reader in this process whatever is chosen.

    Delete this and a presentation is accepted at a door that nothing behind it can read."""
    assert route_for(MediaType.PPTX, _services(Part.OCR)) == ()
    assert [one.provenance.engine for one in route_for(MediaType.PPTX, _services(Part.TIKA))] == [
        EXTRACT_ENGINE
    ]
    assert route_for(MediaType.PNG, _services(Part.LAYOUT, Part.TIKA)) == ()
    assert [one.provenance.path for one in route_for(MediaType.JPEG, _services(Part.OCR))] == [
        ParsePath.OCR
    ]
    assert [one.provenance.path for one in route_for(MediaType.DOCX, _services(Part.OCR))] == [
        ParsePath.FALLBACK
    ]
    assert readable_types(_services(Part.OCR)) >= {MediaType.PNG, MediaType.JPEG, MediaType.PDF}


def test_the_door_accepts_a_photograph_only_where_a_reader_for_it_is_chosen() -> None:
    """`text_path_type` with no services is the four it always was; with the scanned-page reader
    a photograph is let through, and a presentation still is not.

    Delete this and either every install accepts files nothing can read, or none can add a scan."""
    ocr = _services(Part.OCR)

    assert text_path_type("application/pdf") is MediaType.PDF
    with pytest.raises(IngestRefused):
        text_path_type("image/png")
    assert text_path_type("image/png", ocr) is MediaType.PNG
    with pytest.raises(IngestRefused):
        text_path_type(MediaType.PPTX.value, ocr)


# ------------------------------------------------------------------ the read, end to end
def _read(
    body: bytes,
    media: MediaType,
    services: DocumentServices | None,
    kind: KnowledgeKind = KnowledgeKind.SOP,
) -> ReadUpload | ParseFailure:
    upload = _upload(body, media, filename=f"upload.{'pdf' if media is MediaType.PDF else 'png'}")
    return read_for_text_path(
        ReceivedUpload(upload=upload, body=body),
        kind=kind,
        placement=KnowledgeVisibility.personal(OWNER),
        owner_id=OWNER,
        scanner=_Clean(),
        services=services,
    )


def test_a_document_with_a_text_layer_is_read_by_layout_and_says_so() -> None:
    """The layout part's blocks become the item, and the read names the path and engine.

    Delete this and the route is built and never reached by the read."""
    server = _Server(layout=_ok({"blocks": [_entry("Quarterly report", 0, 1)]}))

    read = _read(a_pdf("Quarterly report"), MediaType.PDF, services_for((Part.LAYOUT,), server))

    assert isinstance(read, ReadUpload)
    assert read.provenance is not None
    assert (read.provenance.path, read.provenance.engine) == (
        ParsePath.LAYOUT,
        "docling-layout-and-tableformer",
    )
    assert read.item.content == "Quarterly report"


def test_a_scan_the_layout_part_finds_no_text_in_falls_to_the_scanned_page_reader() -> None:
    """Layout returns no blocks (`no_text_layer`), the reader in this process finds none either,
    and the scanned-page reader's blocks become the item, recorded as a guess.

    Delete this and a scanned PDF is refused with the cause that names the path that was never
    asked."""
    server = _Server(
        layout=_ok({"blocks": []}),
        ocr=_ocr_answer(_entry("Invoice 1042", 0, 1), pages=[{"page": 1, "confidence": 0.95}]),
    )

    read = _read(a_pdf(""), MediaType.PDF, services_for((Part.LAYOUT, Part.OCR), server))

    assert isinstance(read, ReadUpload)
    assert read.provenance is not None and read.provenance.path is ParsePath.OCR
    assert read.item.content == "Invoice 1042"
    assert [part for part, _ in server.asked] == [Part.LAYOUT, Part.OCR]


def test_a_layout_part_that_is_down_does_not_send_the_document_to_the_weaker_reader() -> None:
    """An outage is `PARSER_UNAVAILABLE`, which the route returns without trying the next path, so
    the document waits and is not read worse.

    Delete this and an hour of model-server downtime puts every document ingested in it on the
    fallback, recorded and never re-read."""
    server = _Server()  # nothing answers

    read = _read(a_pdf("Quarterly report"), MediaType.PDF, services_for((Part.LAYOUT,), server))

    assert isinstance(read, ParseFailure)
    assert read.cause is ParseCause.PARSER_UNAVAILABLE
    assert read.is_retryable


def test_with_no_services_a_document_is_read_by_the_one_reader_and_carries_no_provenance() -> None:
    """The positive sibling of everything above: no services, the text path, no provenance.

    Delete this and the route is applied to installs that never chose it."""
    read = _read(a_pdf("Quarterly report"), MediaType.PDF, None)

    assert isinstance(read, ReadUpload)
    assert read.provenance is None
    assert "Quarterly report" in read.item.content


def test_the_names_this_side_uses_for_the_server_are_the_names_the_server_declares() -> None:
    """The model names a request carries are the labels the server's parts report loading.

    Delete this and a renamed label leaves requests naming a model nothing has loaded."""
    assert server_ocr.LABEL == OCR_MODEL
    assert server_tika.LABEL == EXTRACT_MODEL
    assert layout_server.LABEL == LAYOUT_ENGINE


# ------------------------------------------------------------------ images at the structural check
def _png(width: int, height: int) -> bytes:
    header = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes((8, 2, 0, 0, 0))
    return b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR" + header + bytes(4)


def _jpeg(width: int, height: int, *, before: bytes = b"") -> bytes:
    app0 = b"\xff\xe0" + (16).to_bytes(2, "big") + b"JFIF\x00" + bytes(9)
    frame = b"\xff\xc0" + (17).to_bytes(2, "big") + b"\x08"
    frame += height.to_bytes(2, "big") + width.to_bytes(2, "big") + bytes(10)
    return b"\xff\xd8" + before + app0 + frame


def _verdict(content: bytes) -> tuple[ScanVerdict, Any]:
    report = StructuralCheck().scan(content)
    return report.verdict, report.cause


def test_a_photograph_is_judged_by_the_size_its_header_claims() -> None:
    """A PNG and a JPEG of an ordinary size are clean; one that claims more pixels than any page
    has is refused as expanding without bound, and one whose header cannot be read is unopenable.

    Delete this and either every photograph is refused (so the scanned-page reader is never
    reached) or a header claiming a gigapixel is handed to a library that decodes it."""
    assert _verdict(_png(2480, 3508)) == (ScanVerdict.CLEAN, None)
    assert _verdict(_jpeg(2480, 3508)) == (ScanVerdict.CLEAN, None)
    assert _verdict(_png(20_000, 20_000)) == (ScanVerdict.INFECTED, ScanCause.EXPANDS_WITHOUT_BOUND)
    assert _verdict(_jpeg(20_000, 20_000)) == (
        ScanVerdict.INFECTED,
        ScanCause.EXPANDS_WITHOUT_BOUND,
    )
    assert _verdict(b"\x89PNG\r\n\x1a\n" + bytes(8)) == (
        ScanVerdict.UNSCANNABLE,
        ScanCause.UNOPENABLE,
    )
    assert _verdict(b"\xff\xd8\xff\xe0\x00\x02") == (ScanVerdict.UNSCANNABLE, ScanCause.UNOPENABLE)


def test_a_header_claiming_no_pixels_is_unopenable_and_the_bound_is_inclusive() -> None:
    """Zero in either dimension is not an image; exactly the pixel bound is accepted and one more
    row is not.

    Delete this and a zero-width header is cleared, or the bound moves by one without a test
    noticing."""
    assert _verdict(_png(0, 100))[1] is ScanCause.UNOPENABLE
    assert _verdict(_jpeg(100, 0))[1] is ScanCause.UNOPENABLE
    assert _verdict(_png(10_000, 10_000)) == (ScanVerdict.CLEAN, None)
    assert _verdict(_png(10_000, 10_001))[1] is ScanCause.EXPANDS_WITHOUT_BOUND


def test_a_png_whose_first_chunk_is_not_a_header_is_not_read_for_a_size() -> None:
    """Bytes at the place a header's size would be are not a size unless the chunk there is a
    header: an ordinary-looking size in a chunk of another name is unopenable.

    Delete this and any PNG-signed file with plausible numbers in the right place is cleared."""
    not_a_header = bytearray(_png(2480, 3508))
    not_a_header[12:16] = b"tEXt"

    assert _verdict(bytes(not_a_header)) == (ScanVerdict.UNSCANNABLE, ScanCause.UNOPENABLE)


def test_a_jpeg_frame_is_found_after_markers_that_stand_alone_and_segments_of_any_length() -> None:
    """A JPEG with a restart marker and a comment segment in front of its frame still has its size
    read, so a bomb cannot be hidden behind a long segment.

    Delete this and the reader stops at the first segment it does not expect and clears a file it
    did not read."""
    comment = b"\xff\xfe" + (12).to_bytes(2, "big") + bytes(10)
    padded = _jpeg(30_000, 30_000, before=b"\xff\xd0\xff" + comment)

    assert _verdict(padded) == (ScanVerdict.INFECTED, ScanCause.EXPANDS_WITHOUT_BOUND)


def test_the_pixel_bound_is_the_one_the_scanned_page_reader_enforces() -> None:
    """The application's bound and the server's are one figure.

    Delete this and the check clears a page the reader then refuses, which is a retry for ever."""
    assert MAX_IMAGE_PIXELS == server_ocr.MAX_PAGE_PIXELS


# ------------------------------------------------------------------ what a path can see of a table
def test_a_pricing_note_is_judged_by_what_the_reader_that_read_it_could_see() -> None:
    """A pricing note must hold no price table. Read by the layout part a table is seen, so a note
    with none is accepted and one with a table is refused as holding one; read by the reader in
    this process a PDF's tables cannot be seen, so the note is refused as unverifiable.

    Delete this and a layout read is judged as blind as the text layer is (so no PDF pricing note
    is ever accepted), or a text-layer read is judged as sighted (so a price list passes as a
    note)."""
    from brain.knowledge.kinds import KindError

    note = KnowledgeKind.PRICING_NOTE
    prose = _Server(layout=_ok({"blocks": [_entry("Prices are agreed per project.", 0, 1)]}))
    table = _Server(
        layout=_ok({"blocks": [_entry("| item | price |", 0, 1, kind="table")]}),
    )
    plain = a_pdf("Prices are agreed per project.")

    seen = _read(plain, MediaType.PDF, services_for((Part.LAYOUT,), prose), note)
    with pytest.raises(KindError, match="holds a table"):
        _read(plain, MediaType.PDF, services_for((Part.LAYOUT,), table), note)
    with pytest.raises(KindError, match="in this format it cannot"):
        _read(plain, MediaType.PDF, None, note)

    assert isinstance(seen, ReadUpload)
    assert seen.provenance is not None and seen.provenance.path is ParsePath.LAYOUT
