"""A document added from the console, against a real PostgreSQL, as the role the policy binds.

`tests/unit/test_knowledge_routes.py` drives the route with the store replaced. This drives the
store: a file read by the text path is written by `ingest_document` for an administrator who holds
`admin:knowledge` and reads no knowledge, on an install declaring no embedding revision, and then
searched by text as a reader in the department it was placed in and as a reader in another. The
first is handed the passage, carrying the department, visibility and owner it was stored with, and
reads it through the passage policy under department-scoped field grants; the second is handed
exactly what a question about nothing is handed.

It runs on `tests.unit.test_embedding_path_db`'s database: every migration to head where the
server has pgvector, which is CI, and otherwise the chain that builds the resolver, the registry,
`know.item` with its kind and `know.chunk` less its vector column. The two checks that need
`0115` itself, the shape of `know.item` and the library read, skip without pgvector.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is.

Task ids: M7.6.3, M7.7.1, M7.6.1
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.view import AuditFilter, AuditView
from brain.audit_routes import StoredLedger, entry_from
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import TypedResult
from brain.core.redaction import redact
from brain.core.scope import Scope
from brain.gate.model_lane import PASSAGE_POLICY
from brain.knowledge.chunk_store import ingest_document
from brain.knowledge.document_tools import DocumentSearch, KnowledgePassage, searcher
from brain.knowledge.embed_policy import REVISION_SETTING, REVISION_UNSET
from brain.knowledge.ingest import MediaType, admit_upload
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.row_store import SessionRowSource
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD
from brain.knowledge.uploads import ReadUpload, ReceivedUpload, read_for_text_path
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.queue import Job
from brain.tables.audit import AuditEntryRow, attributed_to
from tests.fixtures.documents import LINE
from tests.fixtures.knowledge_items import a_person
from tests.fixtures.retirable import has_pgvector
from tests.fixtures.scratch_postgres import admin_url, modelled, shape, sql
from tests.unit.test_embedding_path_db import (
    FINANCE_OWNER,
    WEB_OWNER,
    _database,
    people,
    through,
)

pytestmark = pytest.mark.needs_db

ADMINISTRATOR = "u_knowledge_administrator"
MARKDOWN = LINE.join(["# Site handover", "", "Sign the TEALCHECK list before leaving."]).encode()


def as_application(url: str, statement: str) -> list[tuple[object, ...]]:
    """One statement as `brain_app`, in a transaction rolled back afterwards."""
    with psycopg.connect(url) as conn:
        conn.execute("SET ROLE brain_app")
        try:
            return conn.execute(statement).fetchall()
        finally:
            conn.rollback()


def an_administrator(url: str) -> None:
    """A person holding `admin:knowledge` over everything and no read of the knowledge layer."""
    a_person(url, ADMINISTRATOR)
    sql(
        url,
        "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by, reason) "
        "VALUES (%s, %s, %s, %s, %s)",
        ADMINISTRATOR,
        KNOWLEDGE_UPLOAD.value,
        json.dumps(Scope.unrestricted().model_dump(mode="json")),
        "u_seed",
        "loaded by the test fixture",
    )


def uploaded(kind: KnowledgeKind = KnowledgeKind.SOP) -> ReadUpload:
    """The markdown file, read by the text path and placed in web for the administrator."""
    upload = admit_upload(
        filename="Site handover.md", declared_type=MediaType.MARKDOWN.value, content=MARKDOWN
    )
    read = read_for_text_path(
        ReceivedUpload(upload=upload, body=MARKDOWN),
        kind=kind,
        placement=KnowledgeVisibility.of_department("web", owner_id=ADMINISTRATOR),
        owner_id=ADMINISTRATOR,
    )
    assert isinstance(read, ReadUpload)
    return read


#: The reach digest and trace the upload below is attributed with, as the route's request would.
UPLOAD_REACH = "b" * 32
UPLOAD_TRACE = "t-knowledge-upload"


def stored(url: str, read: ReadUpload) -> Job | None:
    """`ingest_document` as the route's store calls it, attributed, with no vector leg."""

    async def enqueue(job: Job) -> None:
        raise AssertionError("an install declaring no embedding revision queued a job")

    return through(
        url,
        lambda sessions: ingest_document(
            sessions,
            read.item,
            enqueue=enqueue,
            now=datetime.now(tz=UTC),
            env={REVISION_SETTING: REVISION_UNSET},
            blocks=read.blocks,
            attributed=attributed_to(
                actor_id=ADMINISTRATOR, ent_hash=UPLOAD_REACH, trace_id=UPLOAD_TRACE
            ),
        ),
    )


def departmental(principal_id: str, department: str) -> EntitlementSet:
    """The plane and the passage fields over one department, as a pack assignment grants them."""
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.department(department))
            for one in (
                KNOWLEDGE_READ.value,
                "read:knowledge.document",
                "read:knowledge.title",
                "read:knowledge.updated_at",
            )
        ),
    )


def searched(
    url: str, who: EntitlementSet, *, kinds: tuple[KnowledgeKind, ...] = ()
) -> TypedResult[KnowledgePassage]:
    async def work(sessions: async_sessionmaker[AsyncSession]) -> TypedResult[KnowledgePassage]:
        handler = searcher(SessionRowSource(sessions))
        return await handler(DocumentSearch(question="TEALCHECK", kinds=kinds), entitlement=who)

    return through(url, work)


def test_an_administrators_upload_is_found_by_its_department_by_text_and_by_nobody_else() -> None:
    """**M7.6.3 and M7.7.1 on a server.** The administrator reads no knowledge and the document is
    written anyway, under the store reach their `admin:knowledge` gives, with no job queued. A
    web reader's text search finds it, each passage carrying `web`, `department` and the
    administrator; under department-scoped field grants the redactor keeps it. A finance reader
    is handed an empty result that is byte for byte a search nobody's document matches.

    Delete this and the upload can be written where no reader's policy admits it, or found by a
    reader in another department, and every other test of either half runs on a stand-in."""
    with _database("brain_knowledge_upload_found") as url:
        people(url)
        an_administrator(url)
        read = uploaded()
        job = stored(url, read)
        web_reader = departmental(WEB_OWNER, "web")
        web = searched(url, web_reader)
        finance = searched(url, departmental(FINANCE_OWNER, "finance"))
        nothing = searched(url, departmental(FINANCE_OWNER, "nowhere"))
        kind = sql(url, "SELECT kind FROM know.item WHERE item_id = %s", read.item.item_id)

    assert job is None
    assert kind == [("sop",)]
    assert web.records
    assert {(one.department, one.visibility, one.owner_id) for one in web.records} == {
        ("web", "department", ADMINISTRATOR)
    }
    assert any("TEALCHECK" in one.document for one in web.records)
    kept = redact(web, entitlement=web_reader, policy=PASSAGE_POLICY).payload
    assert kept.records and all("TEALCHECK" in str(one.get("document")) for one in kept.records)
    assert finance.records == nothing.records == ()
    assert (finance.truncated, finance.source) == (nothing.truncated, nothing.source)


def test_a_search_narrowed_to_other_kinds_finds_nothing_and_to_its_own_kind_finds_it() -> None:
    """M7.6.1's narrowing on a server: the kind filter reads `know.item` under the reach the
    chunk statement carries. Delete this and a narrowed search can ignore the filter, or filter
    everything out, and the stand-in tests would not notice."""
    with _database("brain_knowledge_upload_kinds") as url:
        people(url)
        an_administrator(url)
        stored(url, uploaded(KnowledgeKind.FAQ))
        reader = departmental(WEB_OWNER, "web")
        other = searched(url, reader, kinds=(KnowledgeKind.POLICY,))
        own = searched(url, reader, kinds=(KnowledgeKind.FAQ, KnowledgeKind.POLICY))

    assert other.records == ()
    assert own.records


def test_the_migrations_build_know_item_with_its_kind_exactly_as_the_model_declares() -> None:
    """`0115` against the model, on a database migrated to head. Delete this and the check the
    migration writes and the one the model declares can differ, which `put_item` finds at the
    first upload naming the kind they disagree about. **Skips without pgvector.**"""
    if not has_pgvector(admin_url()):
        pytest.skip("head needs pgvector, which CI has")
    tables = ("know.item",)
    with (
        _database("brain_knowledge_upload_shape") as url,
        modelled("brain_knowledge_upload_shape_modelled", tables) as from_models,
    ):
        assert shape(url, tables) == shape(from_models, tables)


def test_the_library_read_returns_the_kind_an_item_was_added_as() -> None:
    """`0115`'s library read, executed as the application role. Delete this and the Knowledge
    library can show no kind while the route tests pass over a stub. **Skips without pgvector.**"""
    if not has_pgvector(admin_url()):
        pytest.skip("head needs pgvector, which CI has")
    with _database("brain_knowledge_upload_library") as url:
        people(url)
        an_administrator(url)
        read = uploaded(KnowledgeKind.POLICY)
        stored(url, read)
        rows = as_application(url, "SELECT item_id, kind FROM know.library_items_with_kind(10)")

    assert rows == [(read.item.item_id, "policy")]


def test_an_upload_appends_one_ledger_entry_the_audit_screens_reader_finds() -> None:
    """**Every change is audited, on a server.** `0115`'s trigger appends one `setting` entry for
    the uploaded item, attributed to the administrator at the reach and trace the request set,
    naming the item, its kind, its level and its department; read back through the Audit route's
    own store and `AuditView`, a holder of `read:audit.setting` finds it and it carries no word of
    the title or the text. Sending the same file again appends a second entry saying `replaced`.

    Delete this and the trigger can stop firing, fire with placeholders, or carry the title, with
    every stand-in test green. **Skips without pgvector**, because the trigger is `0115`'s and only
    the full chain runs it."""
    if not has_pgvector(admin_url()):
        pytest.skip("head needs pgvector, which CI has")
    with _database("brain_knowledge_upload_audit") as url:
        people(url)
        an_administrator(url)
        read = uploaded(KnowledgeKind.SOP)
        stored(url, read)
        stored(url, read)

        async def ledger(
            sessions: async_sessionmaker[AsyncSession],
        ) -> Sequence[AuditEntryRow]:
            return await StoredLedger(sessions).window(
                AuditFilter(subject_kinds=frozenset({"setting"})),
                position=None,
                newest_first=False,
                limit=50,
            )

        rows = through(url, ledger)

    entries = [one for one in (entry_from(row) for row in rows) if one is not None]
    mine = [one for one in entries if one.subject == f"setting:knowledge_item.{read.item.item_id}"]
    assert [(one.actor_id, one.ent_hash, one.trace_id) for one in mine] == [
        (ADMINISTRATOR, UPLOAD_REACH, UPLOAD_TRACE)
    ] * 2
    assert [one.details["change"] for one in mine] == ["added", "replaced"]
    assert {key: mine[0].details[key] for key in ("kind", "level", "department")} == {
        "kind": "sop",
        "level": "department",
        "department": "web",
    }
    auditor = EntitlementSet(
        principal_id="u_auditor",
        grants=(Grant(capability=Capability(value="read:audit.setting"), scope=Scope()),),
    )
    page = AuditView(mine, reader=auditor, now=datetime.now(tz=UTC)).page()
    assert len(page.rows) == 2
    shown = repr(page.rows)
    assert "TEALCHECK" not in shown and "Site handover" not in shown
