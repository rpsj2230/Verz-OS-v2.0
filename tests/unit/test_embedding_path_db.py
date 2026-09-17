"""The embedding path against a real PostgreSQL, as the role the policy binds.

`tests/unit/test_chunk_store.py` holds the path to the statements it builds and the order it
sends them in, against a stand-in session. That cannot say whether `know.chunk`'s policy admits
them, and every failure it would miss is silent: settings that do not reach the policy leave a
department's documents unwritable and unreadable, and nothing raises to say so. So this runs the
writer, the worker and the search tool through `brain.session.make_application_sessions`, which
is what the application and the worker serve through, on a scratch database of its own.

**Two halves, split by pgvector.** Where the server has the extension, which is CI, the database
is every migration to head and the whole path runs: a document is ingested, its job is run by
`run_embed_job` with a stand-in service, the vectors land, and a question with no word in common
with either document finds each asker's own through the vector leg alone, with the reach inside
the query. Where it does not, the resolver, the department registry and `know.item` are built by
their migrations, `know.chunk` is built from `CHUNK` less its vector column with 0009's grants and
0046's policy, and the writer's half is run for real: a document is written under its owner's
reach, rewritten shorter, and refused for an owner who cannot reach it. The vector half says it
was skipped rather than passing.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is.

Task ids: none
"""

from __future__ import annotations

import importlib.util
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from brain.core.entitlement import EntitlementSet
from brain.db import normalise_database_url
from brain.knowledge.chunk_store import ChunkStoreError, ingest_document, run_embed_job
from brain.knowledge.document_tools import DocumentSearch, QuestionEmbedder, searcher
from brain.knowledge.embed_policy import COLUMN_DIMENSIONS, REVISION_SETTING
from brain.knowledge.embed_queue import Embedded, EmbeddingBatch
from brain.knowledge.embedding import EmbeddedVector
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.row_store import SessionRowSource
from brain.knowledge.search import CHUNK
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.queue import Job
from brain.session import make_app_engine, make_application_sessions
from brain.tables.gate import DepartmentRow
from tests.fixtures.knowledge_items import a_person, a_reader
from tests.fixtures.retirable import has_pgvector, predecessor, retirable, revision_of
from tests.fixtures.scratch_postgres import ROOT, drop, fresh, migrate, run, sql

pytestmark = pytest.mark.needs_db

A_REVISION = "v1.0.0"
COMPANY = "c_embedding_path"
WEB_OWNER = "u_web_owner"
FINANCE_OWNER = "u_finance_owner"

ITEM_MIGRATION = ROOT / "migrations" / "versions" / "0040_knowledge_item.py"
LAPSE_MIGRATION = ROOT / "migrations" / "versions" / "0048_grant_lapse.py"
SEARCH_MIGRATION = ROOT / "migrations" / "versions" / "0009_search.py"
RETIRABLE_CHUNKS = ROOT / "migrations" / "versions" / "0046_retirable_chunks.py"

#: Two documents that mean the same thing and share no word with the question below, one per
#: department. The stand-in service embeds every passage and every question onto one axis, so
#: the vector leg ranks both first and only the reach can tell them apart.
WEB_TEXT = "Deployments leave on a Tuesday morning."
FINANCE_TEXT = "Invoices close on the twentieth."
QUESTION = "zyxwv"


def _module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"m_{path.stem}_embedding_path", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def without_pgvector(database: str) -> Iterator[str]:
    """The resolver, the registry, `know.item`, and `know.chunk` less its vector column."""
    scratch = fresh(database)
    try:
        migrate(database, "stamp", "0001")
        migrate(database, "upgrade", "0003")
        migrate(database, "stamp", "0014")
        migrate(database, "upgrade", "0015")
        migrate(database, "stamp", predecessor(ITEM_MIGRATION))
        migrate(database, "upgrade", revision_of(ITEM_MIGRATION))
        migrate(database, "stamp", predecessor(LAPSE_MIGRATION))
        migrate(database, "upgrade", revision_of(LAPSE_MIGRATION))
        metadata = sa.MetaData()
        sa.Table(
            CHUNK.name,
            metadata,
            *(column._copy() for column in CHUNK.columns if column.name != "embedding"),
            schema=CHUNK.schema,
        )
        engine = sa.create_engine(normalise_database_url(_sync(scratch)), poolclass=NullPool)
        try:
            metadata.create_all(engine)
        finally:
            engine.dispose()
        # The writer clears a rewritten chunk's vector, so the column has to exist to be set to
        # NULL. A text column stands in for it: nothing on this chain writes a vector, and the
        # half that does is the test below that skips without pgvector.
        sql(scratch, "ALTER TABLE know.chunk ADD COLUMN embedding text")
        search, retired = _module(SEARCH_MIGRATION), _module(RETIRABLE_CHUNKS)
        for statement in (*search.RLS, *search.GRANTS, *retired.RLS):
            sql(scratch, statement)
        yield scratch
    finally:
        drop(database)


def _sync(url: str) -> str:
    return url if "+psycopg" in url else url.replace("postgresql://", "postgresql+psycopg://", 1)


def people(url: str) -> None:
    """Two owners, each reading one department, and the registry naming both departments."""
    for owner, department in ((WEB_OWNER, "web"), (FINANCE_OWNER, "finance")):
        a_person(url, owner)
        a_reader(url, owner, department)
        sql(
            url,
            "INSERT INTO gate.department (company_id, slug, name, scope_slug) "
            "VALUES (%s, %s, %s, %s)",
            COMPANY,
            department,
            department.title(),
            department,
        )
    assert DepartmentRow.__tablename__ == "department"


def an_item(item_id: str, content: str, *, owner: str, department: str) -> KnowledgeItem:
    return KnowledgeItem(
        item_id=item_id,
        content=content,
        title=item_id,
        visibility=KnowledgeVisibility.of_department(department, owner_id=owner),
        owner_id=owner,
        state=KnowledgeState.PUBLISHED,
    )


def through[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    """Run work on application-role sessions over this database, engine disposed in its loop."""

    async def go() -> T:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await work(make_application_sessions(engine))
        finally:
            await engine.dispose()

    return run(go)


def ingest(url: str, item: KnowledgeItem, queued: list[Job]) -> Job | None:
    async def enqueue(job: Job) -> None:
        queued.append(job)

    return through(
        url,
        lambda sessions: ingest_document(
            sessions,
            item,
            enqueue=enqueue,
            now=datetime.now(tz=UTC),
            env={REVISION_SETTING: A_REVISION},
        ),
    )


def live_chunks(url: str, document_id: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT chunk_id, owner_id, visibility, department, state FROM know.chunk "
        "WHERE document_id = %s AND deleted_at IS NULL ORDER BY ordinal",
        document_id,
    )


# ------------------------------------------------------------------ the writer, on any server
def test_a_document_is_written_under_its_owners_reach_and_rewritten_shorter_by_the_policy() -> None:
    """**The writer's half against the real policy.** A department document is written as the
    application role, under its owner's reach resolved by the real resolver, with every chunk
    carrying the document's visibility and department and a job naming the whole window.
    Rewritten shorter, the chunks past the new end are retired, which 0046's update policy
    admits only with the owner's settings in the transaction and only with the stamp it names.

    Delete this and the writer can pass every stand-in test while the policy refuses the upsert
    or the retirement on a real database, which leaves a document's old tail answering questions
    beside its new text."""
    with _database("brain_embedding_path_writer") as url:
        people(url)
        queued: list[Job] = []
        long_text = "\n\n".join(f"Paragraph {n} about releases." for n in range(3))
        item = an_item("kb.release", long_text, owner=WEB_OWNER, department="web")

        first = ingest(url, item, queued)
        written = live_chunks(url, "kb.release")
        shorter = item.model_copy(update={"content": "Paragraph 0 about releases."})
        second = ingest(url, shorter, queued)
        rewritten = live_chunks(url, "kb.release")
        stored_item = sql(
            url, "SELECT owner_id, visibility FROM know.item WHERE item_id = %s", item.item_id
        )

    assert first is not None and second is not None
    assert queued == [first, second]
    assert written
    assert {row[1:] for row in written} == {(WEB_OWNER, "department", "web", "published")}
    assert dict(first.args)["last_ordinal"] == len(written) - 1
    assert [row[0] for row in rewritten] == ["kb.release.0000"]
    assert stored_item == [(WEB_OWNER, "department")]


def test_a_document_its_owner_cannot_reach_is_refused_and_nothing_is_written() -> None:
    """**The refusal against the real resolver.** An owner reading web hands in a finance
    document: refused, no chunk, no item, nothing queued.

    Delete this and the refusal can be tested only against a stand-in reach, so a resolver or a
    registry that answered differently on a real database would write rows nobody can embed."""
    with _database("brain_embedding_path_refused") as url:
        people(url)
        queued: list[Job] = []
        item = an_item("kb.invoices", FINANCE_TEXT, owner=WEB_OWNER, department="finance")

        with pytest.raises(ChunkStoreError):
            ingest(url, item, queued)
        chunks = live_chunks(url, "kb.invoices")
        items = sql(url, "SELECT item_id FROM know.item")

    assert (queued, chunks, items) == ([], [], [])


# ------------------------------------------------------------------ the whole path, with pgvector
@dataclass
class OneAxis:
    """An `EmbeddingService` that embeds every text onto the same axis, and counts batches."""

    batches: list[EmbeddingBatch] = field(default_factory=list)

    def embed(self, batch: EmbeddingBatch) -> tuple[Embedded, ...]:
        self.batches.append(batch)
        values = [0.0] * COLUMN_DIMENSIONS
        values[0] = 1.0
        vector = EmbeddedVector(model=batch.model, values=tuple(values))
        return tuple(Embedded(chunk_id=unit.chunk_id, vector=vector) for unit in batch.units)


def worked(url: str, job: Job, service: OneAxis) -> str:
    """Run one queued job the way the registered task does, with the stand-in service."""
    args = job.args

    async def work(sessions: async_sessionmaker[AsyncSession]) -> str:
        return await run_embed_job(
            document_id=str(args["document_id"]),
            first_ordinal=int(args["first_ordinal"]),
            last_ordinal=int(args["last_ordinal"]),
            model=str(args["model"]),
            owner_id=str(args["owner_id"]),
            sessions=sessions,
            service=service,
            revision=A_REVISION,
            now=datetime.now(tz=UTC),
        )

    return through(url, work)


def reader_of(owner: str, department: str) -> EntitlementSet:
    from brain.core.entitlement import Capability, Grant
    from brain.core.scope import Scope
    from brain.knowledge.search import KNOWLEDGE_READ

    return EntitlementSet(
        principal_id=owner,
        grants=(
            Grant(
                capability=Capability(value=KNOWLEDGE_READ.value),
                scope=Scope.department(department),
            ),
        ),
    )


def test_an_ingested_document_is_embedded_by_the_worker_and_found_by_its_readers_vector_alone() -> (
    None
):
    """**The path end to end, with a stand-in service.** Two department documents are ingested
    and their jobs run by `run_embed_job`; each chunk then holds a vector and the identity of
    the model that made it. A question sharing no word with either is embedded onto the same
    axis as both, so the nearest-neighbour leg ranks them level, and each asker is handed their
    own department's document and not the other: the reach is inside the vector query, and the
    top-k is drawn from what the asker may already read.

    Delete this and nothing proves that a vector the worker wrote is one the search can find, or
    that the vector leg keeps to the asker's reach on a real index, since every other test of
    either half runs against a stand-in. **Skips without pgvector**, which CI has."""
    with _database("brain_embedding_path_whole") as url:
        if not has_pgvector(url):
            pytest.skip("this server has no pgvector, so the vector column cannot exist")
        people(url)
        queued: list[Job] = []
        ingest(url, an_item("kb.release", WEB_TEXT, owner=WEB_OWNER, department="web"), queued)
        ingest(
            url,
            an_item("kb.invoices", FINANCE_TEXT, owner=FINANCE_OWNER, department="finance"),
            queued,
        )
        service = OneAxis()
        for job in queued:
            worked(url, job, service)
        stored = sql(
            url,
            "SELECT chunk_id, embedding IS NOT NULL, embedding_model FROM know.chunk ORDER BY 1",
        )

        embedder = QuestionEmbedder(service=service, revision=A_REVISION)

        def asked(who: EntitlementSet) -> list[str]:
            async def work(sessions: async_sessionmaker[AsyncSession]) -> list[str]:
                handler = searcher(SessionRowSource(sessions), embedder)
                result = await handler(DocumentSearch(question=QUESTION), entitlement=who)
                return [passage.document_id for passage in result.records]

            return through(url, work)

        web = asked(reader_of(WEB_OWNER, "web"))
        finance = asked(reader_of(FINANCE_OWNER, "finance"))

    identity = service.batches[0].model.identity
    assert [(row[1], row[2]) for row in stored] == [(True, identity), (True, identity)]
    assert web == ["kb.release"]
    assert finance == ["kb.invoices"]


@contextmanager
def _database(name: str) -> Iterator[str]:
    """The full chain where pgvector exists, and the chain without the vector column otherwise."""
    from tests.fixtures.scratch_postgres import admin_url

    if has_pgvector(admin_url()):
        with retirable(name) as url:
            yield url
    else:
        with without_pgvector(name) as url:
            yield url
