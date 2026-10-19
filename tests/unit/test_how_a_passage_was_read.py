"""How each passage of a document was read, page by page, and what a scan that was not clear says.

The owner's requirement is that a citation can say how the passage it cites was read, **per page
when one document was read more than one way**. This file holds the half that is stored: the route
stamps every block with the path and engine that read it and never the reader's answer, a
photographed page in a PDF whose other pages have text is read by the scanned-page reader and says
so, the passages cut from blocks carry what their block carried, and the pages that were not clear
enough are named to the uploader. The citation that shows it is not here.

Task ids: M7.7.9, M7.7.10
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from brain.connectors.throttle import CallOutcome
from brain.knowledge.chunk_store import chunk_row
from brain.knowledge.chunking import Block, BlockKind, ChunkBounds, chunk_document
from brain.knowledge.ingest import (
    AdmittedUpload,
    MediaType,
    ParseCause,
    ParseFailure,
    ScanVerdict,
    admit_upload,
)
from brain.knowledge.item import MAX_PARSE_NOTICE_CHARS, KnowledgeItem, KnowledgeState
from brain.knowledge.item_store import row_values
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.model_server_parsers import (
    DocumentServices,
    FilledIn,
    fill_in_scanned_pages,
    services_for,
    stamped,
)
from brain.knowledge.parse_ocr import NOTICE_CHARS, ocr_provenance
from brain.knowledge.parse_paths import ParsePath, ParseProvenance
from brain.knowledge.scanning import ScannedContent, ScanReport, scan_for_parsing
from brain.knowledge.text_path import joined, pages_without_text
from brain.knowledge.uploads import ReadUpload, ReceivedUpload, read_for_text_path
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.model_server import Part
from brain.ops.model_server_client import Reply
from brain.tables.knowledge import PARSE_NOTICE_CHARS
from tests.fixtures.documents import a_locked_pdf, a_pdf

OWNER = "u_uploader"
BOUNDS = ChunkBounds(size=120, overlap=20, minimum=40, lookback=40)


class _Clean:
    def scan(self, content: bytes) -> ScanReport:
        return ScanReport(verdict=ScanVerdict.CLEAN, scanner="fake-av")


def _upload(body: bytes) -> AdmittedUpload:
    return admit_upload(filename="mixed.pdf", declared_type=MediaType.PDF.value, content=body)


def _cleared(body: bytes) -> ScannedContent:
    return scan_for_parsing(_upload(body), body, scanner=_Clean())


#: A PDF whose first page has text and whose second has none, as a photographed page has none.
MIXED = a_pdf("Quarterly report", "")


class _Server:
    def __init__(self, **replies: Reply) -> None:
        self.replies = {Part(name): reply for name, reply in replies.items()}
        self.asked: list[tuple[Part, Mapping[str, Any]]] = []

    def ask(self, part: Part, request: object) -> Reply:
        self.asked.append((part, request))  # type: ignore[arg-type]
        return self.replies.get(part, Reply(CallOutcome.UNAVAILABLE))


def _entry(text: str, page: int, start: int = 0) -> dict[str, object]:
    return {"kind": "prose", "text": text, "start": start, "page": page, "section": ""}


def _scan_answer(text: str, page: int, confidence: float) -> Reply:
    body = {"blocks": [_entry(text, page)], "pages": [{"page": page, "confidence": confidence}]}
    return Reply(CallOutcome.OK, body)


def _layout_block(text: str = "Quarterly report", page: int = 1) -> Block:
    return Block(
        kind=BlockKind.PROSE, text=text, start=0, page=page, path="layout", engine="docling"
    )


# ------------------------------------------------------------------ which pages have no text
def test_the_pages_with_no_text_layer_are_found_from_the_text_layer_alone() -> None:
    """A page whose extracted text is empty is blank for this purpose, from 1; a document with text
    on every page has none; a file that cannot be opened says nothing rather than every page.

    Delete this and either a photographed page is never found, or a locked file is read as one
    whose every page needs recognising."""
    assert pages_without_text(a_pdf("one", "", "three", "")) == (2, 4)
    assert pages_without_text(a_pdf("one", "two")) == ()
    assert pages_without_text(b"%PDF-1.4 not really") == ()
    assert pages_without_text(a_locked_pdf("secret")) == ()


# ------------------------------------------------------------------ stamping what the route says
def test_a_block_takes_the_path_the_route_declared_and_one_that_already_says_keeps_it() -> None:
    """Blocks that say nothing take the route's provenance; one that says how it was read is not
    overwritten, which is how a filled-in page stays an OCR page inside a layout read.

    Delete this and a scanned page in a layout-read document is recorded as a layout reading,
    which is a guess filed as a reading."""
    layout = ParseProvenance(path=ParsePath.LAYOUT, engine="docling")
    plain = Block(kind=BlockKind.PROSE, text="a", start=0, page=1)
    already = Block(
        kind=BlockKind.PROSE, text="b", start=3, page=2, path="ocr", engine="docling-ocr"
    )

    first, second = stamped([plain, already], layout)

    assert (first.path, first.engine) == ("layout", "docling")
    assert (second.path, second.engine) == ("ocr", "docling-ocr")


# ------------------------------------------------------------------ the blank pages are filled in
def test_a_photographed_page_in_a_layout_read_pdf_is_read_by_ocr_and_says_so() -> None:
    """Page 1 was read by layout; page 2 has no text, so the scanned-page reader is asked for page
    2 alone, its block is laid in after the layout's with offsets that are true, and each block says
    how it was read.

    Delete this and a PDF with a photographed page is indexed without it while reading as whole."""
    server = _Server(ocr=_scan_answer("Invoice 1042", 2, 0.95))
    services = services_for((Part.LAYOUT, Part.OCR), server)

    filled = fill_in_scanned_pages(_cleared(MIXED), [_layout_block()], services)

    assert isinstance(filled, FilledIn)
    assert [(b.page, b.text, b.path, b.engine) for b in filled.blocks] == [
        (1, "Quarterly report", "layout", "docling"),
        (2, "Invoice 1042", "ocr", ocr_provenance().engine),
    ]
    assert joined(filled.blocks) == "Quarterly report\n\nInvoice 1042"
    assert filled.left_out_pages == ()
    [(part, request)] = server.asked
    assert part is Part.OCR and request["pages"] == (2,)


def test_a_filled_in_page_is_laid_in_among_the_layout_pages_by_its_page_number() -> None:
    """Pages 1 and 3 were read by layout and page 2, which had no text, by the scanned-page
    reader: the blocks come back in page order with offsets that are true of that order.

    Delete this and the filled-in page is put after the pages that were read, so a citation to
    page 2 resolves against the wrong words and the document reads out of order."""
    body = a_pdf("Quarterly report", "", "Approved by finance")
    first = Block(
        kind=BlockKind.PROSE,
        text="Quarterly report",
        start=0,
        page=1,
        path="layout",
        engine="docling",
    )
    third = Block(
        kind=BlockKind.PROSE,
        text="Approved by finance",
        start=len("Quarterly report") + 2,
        page=3,
        path="layout",
        engine="docling",
    )
    services = services_for(
        (Part.LAYOUT, Part.OCR), _Server(ocr=_scan_answer("Invoice 1042", 2, 0.95))
    )

    filled = fill_in_scanned_pages(_cleared(body), [first, third], services)

    assert isinstance(filled, FilledIn)
    assert [(b.page, b.text) for b in filled.blocks] == [
        (1, "Quarterly report"),
        (2, "Invoice 1042"),
        (3, "Approved by finance"),
    ]
    assert joined(filled.blocks) == "Quarterly report\n\nInvoice 1042\n\nApproved by finance"


def test_a_page_the_recogniser_was_not_sure_of_is_left_out_and_named() -> None:
    """The blank page is recognised badly: it is not added, and it is returned so the uploader is
    told which.

    Delete this and a garbled page is indexed beside the pages that were read."""
    services = services_for((Part.LAYOUT, Part.OCR), _Server(ocr=_scan_answer("noise", 2, 0.2)))

    filled = fill_in_scanned_pages(_cleared(MIXED), [_layout_block()], services)

    assert isinstance(filled, FilledIn)
    assert [b.page for b in filled.blocks] == [1] and filled.left_out_pages == (2,)


def test_a_reader_that_does_not_answer_fails_the_whole_read_so_it_is_tried_again() -> None:
    """An outage is a retryable failure of the document and not a page quietly left out.

    Delete this and a part that was loading costs a document its photographed pages for good."""
    services = services_for((Part.LAYOUT, Part.OCR), _Server())

    filled = fill_in_scanned_pages(_cleared(MIXED), [_layout_block()], services)

    assert isinstance(filled, ParseFailure) and filled.is_retryable
    assert filled.cause is ParseCause.PARSER_UNAVAILABLE


def test_a_refusal_that_is_not_an_outage_leaves_the_blank_pages_out_and_names_them() -> None:
    """The reader declining the file (a request over its limit, say) leaves the pages it was asked
    for out and named, because the rest was read.

    Delete this and one page that could not be filled in costs the whole document."""
    refusal = Reply(CallOutcome.OK, {"refusal": {"cause": "unsupported", "stage": "ocr"}})
    services = services_for((Part.LAYOUT, Part.OCR), _Server(ocr=refusal))

    filled = fill_in_scanned_pages(_cleared(MIXED), [_layout_block()], services)

    assert isinstance(filled, FilledIn)
    assert [b.page for b in filled.blocks] == [1] and filled.left_out_pages == (2,)


@pytest.mark.parametrize(
    "case",
    ["no-scanned-page-reader", "every-page-has-text", "not-a-pdf", "the-layout-read-the-page"],
)
def test_nothing_is_asked_of_the_scanned_page_reader_when_there_is_nothing_to_fill_in(
    case: str,
) -> None:
    """With no scanned-page reader chosen, text on every page, a file that is not a PDF, or a block
    already on the blank page, the blocks come back as they were and the server is not asked.

    Delete this and every PDF is recognised again after it was read."""
    server = _Server(ocr=_scan_answer("x", 2, 0.95))
    services: DocumentServices = services_for((Part.LAYOUT, Part.OCR), server)
    blocks = [_layout_block()]
    body = MIXED
    if case == "no-scanned-page-reader":
        services = services_for((Part.LAYOUT,), server)
    elif case == "every-page-has-text":
        body = a_pdf("one", "two")
    elif case == "not-a-pdf":
        # The blank page is there to be filled in, so only the type keeps it from being asked.
        content = _cleared(MIXED)
        object.__setattr__(content.upload, "media_type", MediaType.DOCX)
    elif case == "the-layout-read-the-page":
        blocks.append(_layout_block("a table image caption", page=2))
    content = _cleared(body) if case != "not-a-pdf" else content

    filled = fill_in_scanned_pages(content, blocks, services)

    assert isinstance(filled, FilledIn) and filled.blocks == tuple(blocks)
    assert filled.left_out_pages == () and server.asked == []


# ------------------------------------------------------------------ the whole read
def test_a_mixed_pdf_becomes_an_item_with_its_passages_read_two_ways_and_a_notice() -> None:
    """Through `read_for_text_path`: the layout block is stamped layout, the filled-in page is
    OCR, a page too unclear is named in the item's notice, and the item's content is the blocks
    laid out as the citation resolves against.

    Delete this and the pieces are tested and never joined, so the notice or the stamp is lost
    between the reader and the row."""
    layout = Reply(CallOutcome.OK, {"blocks": [_entry("Quarterly report", 1)]})
    server = _Server(layout=layout, ocr=_scan_answer("noise", 2, 0.2))
    services = services_for((Part.LAYOUT, Part.OCR), server)

    read = read_for_text_path(
        ReceivedUpload(upload=_upload(MIXED), body=MIXED),
        kind=KnowledgeKind.SOP,
        placement=KnowledgeVisibility.personal(OWNER),
        owner_id=OWNER,
        scanner=_Clean(),
        services=services,
    )

    assert isinstance(read, ReadUpload)
    assert [(b.page, b.path) for b in read.blocks] == [(1, "layout")]
    assert read.left_out_pages == (2,)
    assert read.item.parse_notice.startswith("Page 2 was not clear enough")
    assert read.item.content == "Quarterly report"


def test_a_whole_read_has_no_notice() -> None:
    """A document every page of which was read has an empty notice, which is stored as nothing.

    Delete this and every item carries a sentence about pages it did not lose."""
    layout = Reply(CallOutcome.OK, {"blocks": [_entry("one", 1), _entry("two", 2, start=5)]})
    services = services_for((Part.LAYOUT, Part.OCR), _Server(layout=layout))
    body = a_pdf("one", "two")

    read = read_for_text_path(
        ReceivedUpload(upload=_upload(body), body=body),
        kind=KnowledgeKind.SOP,
        placement=KnowledgeVisibility.personal(OWNER),
        owner_id=OWNER,
        scanner=_Clean(),
        services=services,
    )

    assert isinstance(read, ReadUpload) and read.item.parse_notice == ""
    assert "parse_notice" in row_values(read.item) and row_values(read.item)["parse_notice"] is None


# ------------------------------------------------------------------ what is stored
def _item(content: str, notice: str = "") -> KnowledgeItem:
    return KnowledgeItem(
        item_id="k_mixed",
        content=content,
        title="Mixed",
        visibility=KnowledgeVisibility.personal(OWNER),
        owner_id=OWNER,
        state=KnowledgeState.PUBLISHED,
        parse_notice=notice,
    )


def test_a_passage_is_cut_from_one_block_and_carries_how_that_block_was_read() -> None:
    """A document read two ways has passages of each, and a passage never spans a layout block and
    an OCR block, so each says one thing.

    Delete this and the path of a passage is the document's, which is the lie the requirement says
    one document read two ways must not tell."""
    first = "Quarterly figures were agreed by the finance team on the second of the month."
    second = "Invoice 1042 is payable within thirty days of the date printed at the top."
    content = f"{first}\n\n{second}"
    blocks = [
        Block(kind=BlockKind.PROSE, text=first, start=0, page=1, path="layout", engine="docling"),
        Block(
            kind=BlockKind.PROSE,
            text=second,
            start=len(first) + 2,
            page=2,
            path="ocr",
            engine="docling-ocr",
        ),
    ]
    item = _item(content)

    chunks = chunk_document(item, blocks, bounds=BOUNDS)

    assert {(c.page, c.path, c.engine) for c in chunks} == {
        (1, "layout", "docling"),
        (2, "ocr", "docling-ocr"),
    }
    rows = {row["page"]: row for row in (chunk_row(c, item=item) for c in chunks)}
    assert (rows[1]["parse_path"], rows[1]["parse_engine"]) == ("layout", "docling")
    assert (rows[2]["parse_path"], rows[2]["parse_engine"]) == ("ocr", "docling-ocr")


def test_a_passage_whose_reading_was_not_recorded_is_stored_as_nothing() -> None:
    """Both columns are NULL together for a passage read before reading was recorded or by a path
    that records none, which the table's own constraint requires.

    Delete this and an empty string is written where NULL is required, and every such write is
    refused."""
    block = Block(kind=BlockKind.PROSE, text="a plain paragraph " * 5, start=0)
    item = _item(block.text)

    [chunk, *_] = chunk_document(item, [block], bounds=BOUNDS)
    row = chunk_row(chunk, item=item)

    assert row["parse_path"] is None and row["parse_engine"] is None


def test_the_notice_the_wording_keeps_inside_is_the_width_the_column_has() -> None:
    """The wording's bound, the item's bound and the column's are one figure, read from three
    places.

    Delete this and the wording is allowed past what the column holds, and the database cuts a
    notice in the middle of a page number."""
    assert NOTICE_CHARS == MAX_PARSE_NOTICE_CHARS == PARSE_NOTICE_CHARS == 400
