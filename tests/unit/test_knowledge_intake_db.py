"""A page added by link, and a file read by the queue's worker job, against a real PostgreSQL.

`test_knowledge_intake_routes.py` drives the routes with the store kept rather than written, and
`test_ingest_queue.py` drives the worker job with the resolver and the write stood in. This drives
both halves against the database the policy binds: the page and the queued file are written by
`ingest_document` as an administrator who holds `admin:knowledge` and reads nothing, and are then
searched by text as a reader in the department they were placed in and as a reader in another.
The worker job resolves the administrator's grants through the real resolver, so a revoked grant
is revoked for it, and its write appends the ledger entry `0115`'s trigger records.

It runs on `tests.unit.test_embedding_path_db`'s database, as the upload's database test does.
The two ledger checks need `0115` itself and skip without pgvector, which CI has.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is.

Task ids: M7.1.2, M7.1.5, M22.2.4
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.view import AuditFilter
from brain.audit_routes import StoredLedger, entry_from
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Scope
from brain.knowledge import ingest_queue
from brain.knowledge.chunk_store import ingest_document
from brain.knowledge.embed_policy import REVISION_SETTING, REVISION_UNSET
from brain.knowledge.ingest import MediaType, admit_upload
from brain.knowledge.ingest_queue import (
    IngestRun,
    Ticket,
    TicketState,
    new_ticket,
    put_ticket,
    run_ingest_job,
)
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.scanning import scan_for_parsing
from brain.knowledge.search import KNOWLEDGE_UPLOAD
from brain.knowledge.text_path import StructuralCheck
from brain.knowledge.uploads import ReadUpload, read_for_link, receive_page, store_original
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.queue import Job
from brain.tables.audit import AuditEntryRow, attributed_to
from brain.tools.fetch import FetchedBytes
from tests.fixtures.documents import LINE
from tests.fixtures.memory_store import MemoryStore
from tests.fixtures.retirable import has_pgvector
from tests.fixtures.scratch_postgres import admin_url, sql
from tests.fixtures.web_pages import FURNITURE_WORD, PRICING_PAGE, PRICING_URL, PRICING_WORD
from tests.unit.test_embedding_path_db import FINANCE_OWNER, WEB_OWNER, _database, people, through
from tests.unit.test_knowledge_upload_db import ADMINISTRATOR, an_administrator, departmental

pytestmark = pytest.mark.needs_db

WEB = KnowledgeVisibility.of_department("web", owner_id=ADMINISTRATOR)
NO_VECTORS = {REVISION_SETTING: REVISION_UNSET}
LINK_REACH = "c" * 32
LINK_TRACE = "t-knowledge-link"
QUEUE_TRACE = "t-knowledge-queued"
PREFIX = "brain"
MARKDOWN = LINE.join(["# Site handover", "", "Sign the TEALQUEUE list before leaving."]).encode()


class Site:
    def get_once(self, url: str, *, address: str, max_bytes: int) -> FetchedBytes | str:
        return FetchedBytes(body=PRICING_PAGE, final_url=url)


class Public:
    def resolve(self, host: str) -> Sequence[str]:
        return ["93.184.216.34"]


async def nothing_queued(job: Job) -> None:
    raise AssertionError("an install declaring no embedding revision queued a job")


def linked() -> ReadUpload:
    page = receive_page(PRICING_URL, fetcher=Site(), resolver=Public())
    read = read_for_link(
        page,
        kind=KnowledgeKind.SERVICE_PACKAGE,
        placement=WEB,
        owner_id=ADMINISTRATOR,
        taken_on=date.today(),
    )
    assert isinstance(read, ReadUpload)
    return read


def stored_link(url: str, read: ReadUpload) -> None:
    through(
        url,
        lambda sessions: ingest_document(
            sessions,
            read.item,
            enqueue=nothing_queued,
            now=datetime.now(tz=UTC),
            env=NO_VECTORS,
            blocks=read.blocks,
            attributed=attributed_to(
                actor_id=ADMINISTRATOR, ent_hash=LINK_REACH, trace_id=LINK_TRACE
            ),
        ),
    )


def searched(url: str, who: EntitlementSet, word: str) -> list[str]:
    from brain.knowledge.document_tools import DocumentSearch, searcher
    from brain.knowledge.row_store import SessionRowSource

    async def work(sessions: async_sessionmaker[AsyncSession]) -> list[str]:
        handler = searcher(SessionRowSource(sessions))
        found = await handler(DocumentSearch(question=word), entitlement=who)
        return [one.document for one in found.records]

    return through(url, work)


def queued(store: MemoryStore) -> Ticket:
    """What the queued route does before it enqueues, for a Markdown file placed in web."""
    upload = admit_upload(
        filename="Site handover.md", declared_type=MediaType.MARKDOWN.value, content=MARKDOWN
    )
    store_original(
        scan_for_parsing(upload, MARKDOWN, scanner=StructuralCheck()), backend=store, prefix=PREFIX
    )
    ticket = new_ticket(
        upload,
        placement=WEB,
        kind=KnowledgeKind.SOP,
        owner_id=ADMINISTRATOR,
        trace_id=QUEUE_TRACE,
        now=datetime.now(tz=UTC),
    )
    put_ticket(store, ticket, prefix=PREFIX)
    return ticket


def worked(url: str, store: MemoryStore, ticket: Ticket) -> Ticket:
    """The registered task's body, on application-role sessions over this database."""

    async def work(sessions: async_sessionmaker[AsyncSession]) -> Ticket:
        return await run_ingest_job(
            ticket.ticket,
            IngestRun(
                backend=store,
                prefix=PREFIX,
                sessions=sessions,
                enqueue=nothing_queued,
                now=datetime.now(tz=UTC),
                env=NO_VECTORS,
            ),
        )

    return through(url, work)


def ledger_entries(url: str, item_id: str) -> list[tuple[str, str, str]]:
    async def window(sessions: async_sessionmaker[AsyncSession]) -> Sequence[AuditEntryRow]:
        return await StoredLedger(sessions).window(
            AuditFilter(subject_kinds=frozenset({"setting"})),
            position=None,
            newest_first=False,
            limit=50,
        )

    entries = [one for one in (entry_from(row) for row in through(url, window)) if one is not None]
    return [
        (one.actor_id, one.ent_hash, one.trace_id)
        for one in entries
        if one.subject == f"setting:knowledge_item.{item_id}"
    ]


# ------------------------------------------------------------------ a link (M7.1.2)
def test_a_page_added_by_link_is_found_by_its_department_by_text_and_by_nobody_else() -> None:
    """**M7.1.2 on a server: answered from like an uploaded document.** The page, read from its
    recorded markup, is written as the administrator and found by a web reader's text search,
    with its address first and none of its furniture; a finance reader is handed nothing. Delete
    this and a link can be stored where no reader's policy admits it, or found by anybody."""
    with _database("brain_knowledge_link_found") as url:
        people(url)
        an_administrator(url)
        stored_link(url, linked())
        web = searched(url, departmental(WEB_OWNER, "web"), PRICING_WORD)
        finance = searched(url, departmental(FINANCE_OWNER, "finance"), PRICING_WORD)

    assert web
    assert any(PRICING_WORD in one for one in web)
    assert all(FURNITURE_WORD not in one for one in web)
    assert finance == []


def test_a_page_added_by_link_appends_the_ledger_entry_an_upload_does() -> None:
    """**Every addition is audited.** The page's write appends one `setting` entry attributed to
    the administrator at the reach and trace the request set. Delete this and a link can be added
    with nothing on the Audit screen. **Skips without pgvector**: the trigger is `0115`'s."""
    if not has_pgvector(admin_url()):
        pytest.skip("head needs pgvector, which CI has")
    with _database("brain_knowledge_link_audit") as url:
        people(url)
        an_administrator(url)
        read = linked()
        stored_link(url, read)
        entries = ledger_entries(url, read.item.item_id)

    assert entries == [(ADMINISTRATOR, LINK_REACH, LINK_TRACE)]


# ------------------------------------------------------------------ the queue (M7.1.5)
def test_a_queued_file_is_read_by_the_worker_job_and_found_by_its_department() -> None:
    """**M7.1.5 on a server.** The worker job reads the ticket and the original from the store,
    resolves the administrator's grants through the real resolver, and writes the file as them;
    a web reader finds it and a finance reader does not. Delete this and the queue can mark a file
    added that no search finds."""
    store = MemoryStore()
    with _database("brain_knowledge_queued_found") as url:
        people(url)
        an_administrator(url)
        outcome = worked(url, store, queued(store))
        web = searched(url, departmental(WEB_OWNER, "web"), "TEALQUEUE")
        finance = searched(url, departmental(FINANCE_OWNER, "finance"), "TEALQUEUE")
        kind = sql(url, "SELECT kind FROM know.item WHERE item_id = %s", outcome.item_id)

    assert outcome.state is TicketState.ADDED
    assert kind == [("sop",)]
    assert any("TEALQUEUE" in one for one in web)
    assert finance == []


def test_a_queued_files_ledger_entry_names_its_uploader_their_reach_and_its_trace() -> None:
    """**Audited as the person who queued it**, though the worker wrote it: the actor is the
    administrator, the reach digest is the one their grants resolve to when the job ran, and the
    trace is the request that queued the file. Delete this and every bulk upload is recorded as
    the owner, inferred, at no reach. **Skips without pgvector**: the trigger is `0115`'s."""
    if not has_pgvector(admin_url()):
        pytest.skip("head needs pgvector, which CI has")
    store = MemoryStore()
    with _database("brain_knowledge_queued_audit") as url:
        people(url)
        an_administrator(url)
        outcome = worked(url, store, queued(store))

        async def reach(sessions: async_sessionmaker[AsyncSession]) -> str:
            now = datetime.now(tz=UTC)
            found = await ingest_queue.uploader_now(sessions, ADMINISTRATOR, now=now)
            return found.entitlement.ent_hash()

        expected = through(url, reach)
        entries = ledger_entries(url, outcome.item_id)

    assert entries == [(ADMINISTRATOR, expected, QUEUE_TRACE)]
    assert (
        expected
        == EntitlementSet(
            principal_id=ADMINISTRATOR,
            grants=(Grant(capability=KNOWLEDGE_UPLOAD, scope=Scope.unrestricted()),),
        ).ent_hash()
    )


def test_a_queued_file_whose_uploader_lost_the_grant_is_not_added_on_a_server() -> None:
    """**Grants are read when the job runs**, through the real resolver: the administrator's
    `admin:knowledge` is deleted between the queueing and the reading, so nothing is written and
    the ticket says so. Delete this and a revoked grant still adds whatever was queued under it."""
    store = MemoryStore()
    with _database("brain_knowledge_queued_revoked") as url:
        people(url)
        an_administrator(url)
        ticket = queued(store)
        sql(url, "DELETE FROM gate.capability_grant WHERE principal_id = %s", ADMINISTRATOR)
        outcome = worked(url, store, ticket)
        items = sql(url, "SELECT count(*) FROM know.item")

    assert outcome.state is TicketState.NOT_ADDED
    assert outcome.code == "not_offered"
    assert items == [(0,)]
