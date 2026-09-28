"""A queued file from its ticket to its outcome, with the database and the queue stood in.

The object store is `tests.fixtures.memory_store.MemoryStore`, so the original and the ticket are
really written and read back; the uploader's grants and the corpus write are stood in, because
what they do against PostgreSQL is `test_knowledge_intake_db.py`'s. Everything between, the
digest check, the placement asked again, the scan, the parse inside a standard slot and the
outcome written onto the ticket, runs for real over files built in memory.

Task ids: M7.1.5, M22.2.4, M7.1.3
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Scope
from brain.knowledge import ingest_queue
from brain.knowledge.ingest import (
    CAUSE_TEXT,
    SCAN_CAUSE_TEXT,
    MediaType,
    ParseCause,
    ScanCause,
    admit_upload,
)
from brain.knowledge.ingest_queue import (
    INGEST_TASK,
    INGEST_TRAFFIC_CLASS,
    NO_LONGER_OFFERED,
    NOT_THE_QUEUED_FILE,
    STANDARD_PARSE_BUDGET,
    IngestJobError,
    IngestRun,
    Ticket,
    TicketState,
    Uploader,
    fits_a_slot,
    get_ticket,
    ingest_job,
    new_ticket,
    put_ticket,
    register_ingest_tasks,
    run_ingest_job,
    ticket_for,
    ticket_key,
)
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.parse_budget import MIB
from brain.knowledge.scanning import scan_for_parsing
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD
from brain.knowledge.text_path import StructuralCheck
from brain.knowledge.uploads import UPLOAD_ID_PREFIX, original_bucket, store_original
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.queue import (
    MAX_ARGUMENT_CHARS,
    MIB_PER_SLOT,
    Job,
    Redrive,
    queue_app,
    queue_name_for,
)
from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from tests.fixtures.console_http import attribution_of
from tests.fixtures.documents import LINE, a_pdf, a_word_document, with_part
from tests.fixtures.memory_store import MemoryStore

UPLOADER = "u_admin"
PREFIX = "brain"
TRACE = "t-queued-upload"
#: A clock far from any wall clock, so no grant here expires on the day the test runs.
NOW = datetime(2999, 1, 1, tzinfo=UTC)
WEB = KnowledgeVisibility.of_department("web", owner_id=UPLOADER)
MARKDOWN = LINE.join(["# Site handover", "", "Sign the TEALQUEUE list before leaving."]).encode()

#: The uploader may add in web and reads nothing, as a first administrator does.
MAY_ADD_IN_WEB = EntitlementSet(
    principal_id=UPLOADER,
    grants=(Grant(capability=KNOWLEDGE_UPLOAD, scope=Scope.department("web")),),
)
#: The same person after their grant to add was revoked: they read web and add nowhere.
READS_ONLY = EntitlementSet(
    principal_id=UPLOADER,
    grants=(Grant(capability=KNOWLEDGE_READ, scope=Scope.department("web")),),
)


class Written:
    """`ingest_document`, keeping the item, the blocks and the attribution it was handed."""

    def __init__(self) -> None:
        self.items: list[Any] = []
        self.attributed: list[tuple[Any, ...]] = []

    async def __call__(
        self,
        sessions: Any,
        item: Any,
        *,
        enqueue: Any,
        now: Any,
        env: Any = None,
        blocks: Any = (),
        attributed: Any = (),
    ) -> Job | None:
        self.items.append((item, tuple(blocks)))
        self.attributed.append(tuple(attributed))
        return None


@pytest.fixture
def written(monkeypatch: pytest.MonkeyPatch) -> Written:
    store = Written()
    monkeypatch.setattr(ingest_queue, "ingest_document", store)
    return store


def grants(monkeypatch: pytest.MonkeyPatch, entitlement: EntitlementSet) -> list[str]:
    """Stand in for the resolver: the uploader holds `entitlement` when the job runs."""
    asked: list[str] = []

    async def uploader_now(sessions: Any, principal_id: str, *, now: datetime) -> Uploader:
        asked.append(principal_id)
        return Uploader(entitlement=entitlement, registry=("finance", "web"))

    monkeypatch.setattr(ingest_queue, "uploader_now", uploader_now)
    return asked


def queued(
    store: MemoryStore,
    body: bytes = MARKDOWN,
    *,
    media_type: MediaType = MediaType.MARKDOWN,
    filename: str = "Site handover.md",
    kind: KnowledgeKind = KnowledgeKind.SOP,
) -> Ticket:
    """What the route does before it enqueues: admit, scan, keep the original, write the ticket."""
    upload = admit_upload(filename=filename, declared_type=media_type.value, content=body)
    store_original(
        scan_for_parsing(upload, body, scanner=StructuralCheck()), backend=store, prefix=PREFIX
    )
    ticket = new_ticket(
        upload, placement=WEB, kind=kind, owner_id=UPLOADER, trace_id=TRACE, now=NOW
    )
    put_ticket(store, ticket, prefix=PREFIX)
    return ticket


def a_run(store: MemoryStore) -> IngestRun:
    async def enqueue(job: Job) -> None:
        raise AssertionError("no embedding job is queued by these tests")

    return IngestRun(backend=store, prefix=PREFIX, sessions=None, enqueue=enqueue, now=NOW)  # type: ignore[arg-type]


def ran(store: MemoryStore, ticket: Ticket) -> Ticket:
    return asyncio.run(run_ingest_job(ticket.ticket, a_run(store)))


# ------------------------------------------------------------------ the job carries a ticket
def test_a_job_carries_its_ticket_and_nothing_about_the_file() -> None:
    """**A queue row has no row-level security.** The job's one argument is a digest, and a
    filename naming a client appears nowhere in it. Delete this and the name, the kind or the
    department can be added to the arguments, where psql and the queue's retention reach them."""
    store = MemoryStore()
    ticket = queued(store, filename="Acme redundancy plan.md")
    job = ingest_job(ticket.ticket)

    assert job.args == {"ticket": ticket.ticket}
    assert len(ticket.ticket) == 40 < MAX_ARGUMENT_CHARS
    assert "Acme" not in repr(job)
    assert (job.task, job.traffic_class, job.redrive) == (
        INGEST_TASK,
        INGEST_TRAFFIC_CLASS,
        Redrive.SAFE,
    )


def test_the_ticket_is_the_item_id_the_file_will_be_added_as() -> None:
    """Sending the same file to the same place twice is one ticket and one item. Delete this and
    a bulk upload retried after a refusal adds every file that had already been accepted twice."""
    upload = admit_upload(filename="a.md", declared_type=MediaType.MARKDOWN.value, content=MARKDOWN)
    ticket = ticket_for(upload, WEB, UPLOADER)

    assert len(ticket) == 40
    from brain.knowledge.uploads import upload_item_id

    assert upload_item_id(upload, WEB, UPLOADER) == UPLOAD_ID_PREFIX + ticket


def test_a_ticket_is_kept_by_its_digest_beside_the_originals_and_read_back_whole() -> None:
    """The store is the only place the file's name is kept between the request and the worker.
    Delete this and a ticket can be written under the filename, or read back missing a field."""
    store = MemoryStore()
    ticket = queued(store)
    key = ticket_key(ticket.ticket, prefix=PREFIX)

    assert key == f"{PREFIX}/knowledge/queued/{ticket.ticket}.json"
    assert (original_bucket().name, key) in store.objects
    assert get_ticket(store, ticket.ticket, prefix=PREFIX) == ticket


def test_a_ticket_that_is_missing_or_unreadable_fails_the_job_rather_than_guessing() -> None:
    """A job with no ticket has nowhere to say anything. Delete this and it adds nothing and
    reports success, which is the queue saying the file was read when nothing was."""
    store = MemoryStore()
    with pytest.raises(IngestJobError):
        get_ticket(store, "a" * 40, prefix=PREFIX)
    store.put_object(original_bucket().name, ticket_key("b" * 40, prefix=PREFIX), b"{", "x")
    with pytest.raises(IngestJobError, match="could not be read"):
        get_ticket(store, "b" * 40, prefix=PREFIX)


def test_a_ticket_is_forty_hex_characters_or_it_is_refused() -> None:
    """The ticket is a key in the store and a path segment in the status route. Delete this and
    a ticket carrying a slash or a dot-dot addresses another object."""
    store = MemoryStore()
    ticket = queued(store)
    with pytest.raises(Exception, match="40 hex"):
        dataclasses.replace(ticket, ticket="../../" + "a" * 34)


# ------------------------------------------------------------------ a standard slot
def test_a_queued_file_is_one_a_standard_slot_can_hold() -> None:
    """**The throttle's memory half.** A file whose declared parse cost is over one slot is not
    queued, because nothing that drains a larger slot runs a task today. Delete this and a large
    PDF is queued for a worker that cannot hold it, or for a container that registers no task."""
    small = admit_upload(filename="a.pdf", declared_type=MediaType.PDF.value, content=a_pdf("x"))
    per_byte = 6  # `parse_budget.PARSE_EXPANSION` for a PDF
    over = STANDARD_PARSE_BUDGET // per_byte + 1

    assert STANDARD_PARSE_BUDGET == MIB_PER_SLOT * MIB
    assert fits_a_slot(small)
    assert not fits_a_slot(dataclasses.replace(small, size_bytes=over))
    assert fits_a_slot(dataclasses.replace(small, size_bytes=over - 1))


# ------------------------------------------------------------------ the run
def test_a_queued_file_is_added_as_its_uploader_with_the_queueing_requests_trace(
    monkeypatch: pytest.MonkeyPatch, written: Written
) -> None:
    """**M7.1.5 end to end over stand-ins.** The worker reads the original, asks the uploader's
    grants now, reads it, writes it as the uploader, at their reach at this moment, carrying the
    trace of the request that queued it, and records the outcome on the ticket. Delete this and a
    queued file can be written as nobody, under the worker's own reach, or never reported."""
    store = MemoryStore()
    ticket = queued(store)
    asked = grants(monkeypatch, MAY_ADD_IN_WEB)

    outcome = ran(store, ticket)

    assert asked == [UPLOADER]
    ((item, blocks),) = written.items
    assert (item.item_id, item.visibility, item.owner_id, item.kind) == (
        UPLOAD_ID_PREFIX + ticket.ticket,
        WEB,
        UPLOADER,
        KnowledgeKind.SOP,
    )
    assert "TEALQUEUE" in item.content
    settings = dict(one for one in map(attribution_of, written.attributed[0]) if one is not None)
    assert settings == {
        ACTOR_SETTING: UPLOADER,
        ENT_HASH_SETTING: MAY_ADD_IN_WEB.ent_hash(),
        TRACE_ID_SETTING: TRACE,
    }
    assert (outcome.state, outcome.item_id, outcome.passages) == (
        TicketState.ADDED,
        item.item_id,
        len(blocks),
    )
    assert get_ticket(store, ticket.ticket, prefix=PREFIX) == outcome


def test_a_file_its_uploader_may_no_longer_add_there_is_not_added(
    monkeypatch: pytest.MonkeyPatch, written: Written
) -> None:
    """**Grants are read when the job runs.** The uploader's right to add in web was revoked
    between the queueing and the reading. Delete this and a revoked administrator's queued files
    are written anyway, under a grant that no longer exists."""
    store = MemoryStore()
    ticket = queued(store)
    grants(monkeypatch, READS_ONLY)

    outcome = ran(store, ticket)

    assert written.items == []
    assert (outcome.state, outcome.reason) == (TicketState.NOT_ADDED, NO_LONGER_OFFERED)


def test_a_file_the_worker_scan_refuses_is_not_added_and_the_ticket_names_why(
    monkeypatch: pytest.MonkeyPatch, written: Written
) -> None:
    """The worker scans again, because only a scan issues bytes a parser may read. Here the file
    in the store was replaced by one with macros under the same key, so the digest refuses it;
    and a file refused by the scan itself is told its cause. Delete this and the worker parses
    whatever sits under the key."""
    store = MemoryStore()
    word = a_word_document(paragraphs=["Sign the list."])
    ticket = queued(store, word, media_type=MediaType.DOCX, filename="policy.docx")
    grants(monkeypatch, MAY_ADD_IN_WEB)
    macro = with_part(word, "word/vbaProject.bin", b"m")
    (key,) = [key for key in store.names() if "/originals/" in key]
    store.put_object(original_bucket().name, key, macro, MediaType.DOCX.value)

    swapped = ran(store, ticket)
    assert (swapped.state, swapped.reason) == (TicketState.NOT_ADDED, NOT_THE_QUEUED_FILE)

    class Refuses:
        def scan(self, content: bytes) -> Any:
            return StructuralCheck().scan(with_part(word, "word/vbaProject.bin", b"m"))

    fresh = MemoryStore()
    again = queued(fresh, word, media_type=MediaType.DOCX, filename="policy.docx")
    run = dataclasses.replace(a_run(fresh), scanner=Refuses())
    refused = asyncio.run(run_ingest_job(again.ticket, run))

    assert written.items == []
    assert refused.state is TicketState.NOT_ADDED
    assert SCAN_CAUSE_TEXT[ScanCause.MACROS] in refused.reason


def test_a_file_that_will_not_parse_is_not_added_and_the_ticket_names_the_cause(
    monkeypatch: pytest.MonkeyPatch, written: Written
) -> None:
    """**M7.2.5 for a file nobody is waiting on.** A PDF with no text layer is told as that, on
    the ticket the console asks. Delete this and a queued file that would not read vanishes."""
    store = MemoryStore()
    ticket = queued(store, a_pdf(""), media_type=MediaType.PDF, filename="scan.pdf")
    grants(monkeypatch, MAY_ADD_IN_WEB)

    outcome = ran(store, ticket)

    assert written.items == []
    assert (outcome.state, outcome.code) == (TicketState.NOT_ADDED, ParseCause.NO_TEXT_LAYER.value)
    assert CAUSE_TEXT[ParseCause.NO_TEXT_LAYER] in outcome.reason
    assert "scan.pdf" in outcome.reason


def test_the_parse_in_the_worker_is_bounded_by_its_slot(
    monkeypatch: pytest.MonkeyPatch, written: Written
) -> None:
    """The route refuses a file over a slot, and the worker bounds the parse anyway, so a file
    that reached it by another path still cannot spend more than the slot. Delete this and the
    bound is the parse worker's four hundred megabytes inside a forty-eight megabyte slot."""
    store = MemoryStore()
    ticket = queued(store)
    grants(monkeypatch, MAY_ADD_IN_WEB)
    monkeypatch.setattr(ingest_queue, "STANDARD_PARSE_BUDGET", 10)

    outcome = ran(store, ticket)

    assert (outcome.state, outcome.code) == (TicketState.NOT_ADDED, ParseCause.OUT_OF_MEMORY.value)


def test_a_decided_ticket_is_not_read_again_when_its_job_is_redriven(
    monkeypatch: pytest.MonkeyPatch, written: Written
) -> None:
    """`Redrive.SAFE` is only true if a second run writes nothing new. Delete this and a redrive
    after the outcome writes the item a second time and appends a second ledger entry."""
    store = MemoryStore()
    ticket = queued(store)
    grants(monkeypatch, MAY_ADD_IN_WEB)

    first = ran(store, ticket)
    second = ran(store, ticket)

    assert first == second
    assert len(written.items) == 1


def test_the_worker_registers_the_task_on_the_queue_its_class_derives() -> None:
    """The queued file is read by the general worker, which drains `system`. Delete this and the
    task can be registered on a queue nothing drains, or on the parse worker's, which registers
    no task, so every queued file waits for ever."""
    app = queue_app("postgresql://brain@db:5432/brain", pool_max=1)
    register_ingest_tasks(app, database_url="postgresql://brain@db:5432/brain", env={})

    assert app.tasks[INGEST_TASK].queue == queue_name_for(INGEST_TRAFFIC_CLASS) == "system"
