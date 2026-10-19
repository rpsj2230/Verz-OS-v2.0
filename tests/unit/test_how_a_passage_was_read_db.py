"""How a passage was read, and what a scan left out, against a real PostgreSQL.

`test_how_a_passage_was_read.py` shows the blocks, the passages and the rows; this writes them
through `ingest_document` as the administrator who uploaded them and reads the columns back as the
superuser, then asks the table to refuse a path that is not a path and an engine without one. It
runs on the database `test_embedding_path_db` builds, where `0250` is part of the chain.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is.

Task ids: M7.7.9, M7.7.10
"""

from __future__ import annotations

import psycopg
import pytest

from brain.connectors.throttle import CallOutcome
from brain.knowledge.ingest import MediaType, admit_upload
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.model_server_parsers import services_for
from brain.knowledge.uploads import ReadUpload, ReceivedUpload, read_for_text_path
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.model_server import Part
from brain.ops.model_server_client import Reply
from tests.fixtures.documents import a_pdf
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_embedding_path_db import _database, people
from tests.unit.test_knowledge_upload_db import ADMINISTRATOR, an_administrator, stored

pytestmark = pytest.mark.needs_db

#: A first page with text and a second with none, as a photographed page has none.
MIXED = a_pdf("Quarterly report", "")


class _Server:
    def __init__(self, ocr: Reply) -> None:
        self.ocr = ocr

    def ask(self, part: Part, request: object) -> Reply:
        if part is Part.LAYOUT:
            block = {
                "kind": "prose",
                "text": "Quarterly report",
                "start": 0,
                "page": 1,
                "section": "",
            }
            return Reply(CallOutcome.OK, {"blocks": [block]})
        return self.ocr


def _read(ocr: Reply) -> ReadUpload:
    upload = admit_upload(filename="mixed.pdf", declared_type=MediaType.PDF.value, content=MIXED)
    read = read_for_text_path(
        ReceivedUpload(upload=upload, body=MIXED),
        kind=KnowledgeKind.SOP,
        placement=KnowledgeVisibility.of_department("web", owner_id=ADMINISTRATOR),
        owner_id=ADMINISTRATOR,
        services=services_for((Part.LAYOUT, Part.OCR), _Server(ocr)),
    )
    assert isinstance(read, ReadUpload)
    return read


def _scan(text: str, confidence: float) -> Reply:
    block = {"kind": "prose", "text": text, "start": 0, "page": 2, "section": ""}
    pages = [{"page": 2, "confidence": confidence}]
    return Reply(CallOutcome.OK, {"blocks": [block], "pages": pages})


def test_each_passage_is_stored_with_the_path_and_engine_of_the_block_it_was_cut_from() -> None:
    """A document read two ways is written with a row of each: the layout page as `layout`, the
    filled-in page as `ocr`, each with its engine, and an item with no notice.

    Delete this and the columns `0250` added are never written, so nothing can say how any passage
    of any document was read."""
    with _database("brain_how_read_stored") as url:
        people(url)
        an_administrator(url)
        read = _read(_scan("Invoice 1042", 0.95))
        stored(url, read)
        rows = sql(
            url,
            "SELECT page, parse_path, parse_engine FROM know.chunk "
            "WHERE document_id = %s ORDER BY ordinal",
            read.item.item_id,
        )
        notice = sql(
            url, "SELECT parse_notice FROM know.item WHERE item_id = %s", read.item.item_id
        )

    assert rows == [
        (1, "layout", "docling-layout-and-tableformer"),
        (2, "ocr", "docling-ocr"),
    ]
    assert notice == [(None,)]


def test_a_page_that_was_not_clear_is_named_in_the_item_and_has_no_passage() -> None:
    """The unclear page has no row, and the item says which page in the words the uploader was
    told.

    Delete this and the notice is built and never kept, so the next person to open the document
    cannot learn why a page of it cannot be found."""
    with _database("brain_how_read_notice") as url:
        people(url)
        an_administrator(url)
        read = _read(_scan("noise", 0.2))
        stored(url, read)
        pages = sql(url, "SELECT page FROM know.chunk WHERE document_id = %s", read.item.item_id)
        notice = sql(
            url, "SELECT parse_notice FROM know.item WHERE item_id = %s", read.item.item_id
        )

    assert pages == [(1,)]
    assert notice[0][0].startswith("Page 2 was not clear enough")


@pytest.mark.parametrize(
    ("path", "engine"),
    [("guess", "docling"), ("ocr", None), (None, "docling")],
    ids=["not-a-path", "a-path-without-an-engine", "an-engine-without-a-path"],
)
def test_the_table_refuses_a_path_that_is_not_one_and_an_engine_without_its_path(
    path: str | None, engine: str | None
) -> None:
    """The two constraints `0250` wrote: the path is one of three words, and the path and the
    engine are both there or both absent.

    Delete this and a chunk can be written saying it was read by a method nobody has."""
    with _database("brain_how_read_checks") as url:
        people(url)
        an_administrator(url)
        read = _read(_scan("Invoice 1042", 0.95))
        stored(url, read)
        with pytest.raises(psycopg.errors.CheckViolation):
            sql(
                url,
                "UPDATE know.chunk SET parse_path = %s, parse_engine = %s "
                "WHERE document_id = %s AND ordinal = 0",
                path,
                engine,
                read.item.item_id,
            )


# ------------------------------------------------------------------ the install's own checks
MODULE = "brain.ops.acceptance_checks_modelserver"
STORED = "a_document_read_two_ways_is_stored_passage_by_passage"
PHOTOGRAPHS = "a_photograph_is_judged_by_what_its_header_claims"


def test_on_a_real_database_the_modules_checks_pass_or_are_not_run_and_leave_nothing() -> None:
    """**The module as the worker runs it, against PostgreSQL at head.** The two checks that need
    no server pass (a photograph's header is judged, and a document read two ways is stored passage
    by passage with its unclear page named), the six that ask the server are not run for a reason
    in words, none fails, and every table a check writes holds afterwards what it held before.

    Delete this and the checks pass over a stub harness and fail on the install they are for."""
    from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
    from tests.unit.test_acceptance import at_head, counts
    from tests.unit.test_acceptance_hubspot import run_checks

    with at_head("brain_acceptance_model_server") as url:
        before = counts(url)
        outcome = run_checks(url, registered((MODULE,)))
        after = counts(url)

    states = {name: state for name, (state, _) in outcome.items()}
    assert states.pop(STORED) == PASSED and states.pop(PHOTOGRAPHS) == PASSED
    assert set(states.values()) == {NOT_RUN}
    assert FAILED not in {state for state, _ in outcome.values()}
    assert after == before
