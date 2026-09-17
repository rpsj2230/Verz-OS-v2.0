"""The corpus writer and the embedding worker, end to end against a stand-in session and service.

**No database, and what that leaves unproved is said rather than implied.** The stand-in session
answers the resolver, the department registry and a window read, and records every statement it
is handed, so what is asserted here is the order of work, the refusals, and that every chunk
statement carries the owner's reach. Whether PostgreSQL's policy admits those statements, and
whether the vector column takes the literal, is `tests/unit/test_embedding_path_db.py`, which
needs a server and, for the vector half, pgvector.

**The service is a stand-in and it counts being asked.** A run that refused and a run that sent
a batch and threw the answer away write the same nothing, and only the count separates them.

Task ids: none
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import TextClause, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import Insert, Select, Update

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.entitlement_store import RESOLVE
from brain.knowledge.chunk_store import (
    A_DOCUMENT_ITS_OWNER_CANNOT_REACH_IS_NOT_INDEXED_ON_THEIR_BEHALF,
    ChunkStoreError,
    chunk_row,
    embedding_update,
    ingest_document,
    retire_tail_statement,
    run_embed_job,
    text_blocks,
    upsert_statement,
    window_statement,
    write_document,
)
from brain.knowledge.chunking import BlockKind, ChunkBounds, chunk_document
from brain.knowledge.embed_policy import (
    COLUMN_DIMENSIONS,
    REVISION_SETTING,
    EmbeddingUnavailable,
    served_embedding_model,
)
from brain.knowledge.embed_queue import (
    EMBED_TASK,
    WRITTEN_COLUMNS,
    Embedded,
    EmbeddingBatch,
    EmbeddingWrite,
)
from brain.knowledge.embedding import EmbeddedVector, EmbeddingError, MixedEmbeddingError
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.search import KNOWLEDGE_READ, Reach, reach_predicate, session_settings
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.queue import Job

POSTGRES = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Far from any wall clock, because nothing here is about the present.
NOW = datetime(2019, 1, 1, 9, 0, tzinfo=UTC)
READ_AT = datetime(2019, 1, 1, 8, 0, tzinfo=UTC)

A_REVISION = "v1.0.0"
MODEL = served_embedding_model(revision=A_REVISION)
OWNER = "p_owner"
REGISTRY = ("finance", "web")


def compiled(statement: Any) -> str:
    return str(statement.compile(dialect=POSTGRES))


def rendered(statements: Sequence[Any]) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for one in statements:
        done = one.compile(dialect=POSTGRES)
        out.append((str(done), dict(done.params)))
    return out


def an_item(
    content: str = "Deployments go out on a Tuesday.\n\nRollbacks need two approvers.",
    *,
    department: str = "web",
    item_id: str = "k_sop",
) -> KnowledgeItem:
    return KnowledgeItem(
        item_id=item_id,
        content=content,
        title="Release procedure",
        visibility=KnowledgeVisibility.of_department(department, owner_id=OWNER),
        owner_id=OWNER,
        state=KnowledgeState.PUBLISHED,
    )


def grants(*departments: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id=OWNER,
        grants=tuple(
            Grant(capability=Capability(value=KNOWLEDGE_READ.value), scope=Scope.department(one))
            for one in departments
        ),
    )


# ------------------------------------------------------------------ the stand-ins
@dataclass
class Result:
    scalar: object = None
    scalars_: Sequence[object] = ()
    rows: Sequence[object] = ()
    rowcount: int = 1

    def scalar_one(self) -> object:
        return self.scalar

    def scalars(self) -> Result:
        return self

    def all(self) -> list[object]:
        return list(self.scalars_)

    def __iter__(self) -> Any:
        return iter(self.rows)


@dataclass
class Database:
    """What the stand-in session answers from, and everything it was asked, in order."""

    entitlement: EntitlementSet = field(default_factory=lambda: grants("web"))
    window: Sequence[tuple[str, str]] = (("k_sop.0000", "Deployments go out on a Tuesday."),)
    updated: int = 1
    asked: list[Any] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

    def answer(self, statement: Any) -> Result:
        self.asked.append(statement)
        if statement is RESOLVE:
            return Result(scalar=self.entitlement.model_dump(mode="json"))
        if isinstance(statement, TextClause):
            return Result()
        if isinstance(statement, Select) and "gate.department" in compiled(statement):
            return Result(scalars_=REGISTRY)
        if isinstance(statement, Select):
            return Result(
                rows=tuple(
                    SimpleNamespace(chunk_id=ref, body=text, updated_at=READ_AT)
                    for ref, text in self.window
                )
            )
        if isinstance(statement, Update) and "embedding_literal" in compiled(statement):
            return Result(rowcount=self.updated)
        return Result()

    def updates(self) -> list[Update]:
        return [
            one
            for one in self.asked
            if isinstance(one, Update) and "embedding_literal" in compiled(one)
        ]


class Session:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Result:
        return self.database.answer(statement)

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        self.database.events.append("begin")
        try:
            yield
        except BaseException:
            self.database.events.append("rollback")
            raise
        self.database.events.append("commit")


def sessions_over(database: Database) -> async_sessionmaker[AsyncSession]:
    """A session factory over the stand-in. Cast at the seam: the store asks a session for
    `execute` and `begin` and nothing else, and proving the stand-in structurally equal to
    SQLAlchemy's classes buys nothing the tests below do not already exercise."""

    @asynccontextmanager
    async def open_session() -> AsyncIterator[Session]:
        yield Session(database)

    return cast("async_sessionmaker[AsyncSession]", open_session)


def a_session(database: Database) -> AsyncSession:
    """One stand-in session, cast at the seam for the reason `sessions_over` gives."""
    return cast("AsyncSession", Session(database))


@dataclass
class Service:
    """An `EmbeddingService` answering every chunk with a normalised vector, or failing."""

    down: bool = False
    calls: int = 0

    def embed(self, batch: EmbeddingBatch) -> tuple[Embedded, ...]:
        self.calls += 1
        if self.down:
            msg = "the inference server did not answer"
            raise EmbeddingUnavailable(msg)
        values = [0.0] * COLUMN_DIMENSIONS
        values[0] = 1.0
        vector = EmbeddedVector(model=batch.model, values=tuple(values))
        return tuple(Embedded(chunk_id=unit.chunk_id, vector=vector) for unit in batch.units)


def settle[T](pending: Awaitable[T]) -> T:
    async def wait() -> T:
        return await pending

    return asyncio.run(wait())


def web_reach() -> Reach:
    return Reach(principal_id=OWNER, departments=("web",))


# ------------------------------------------------------------------ the text, as blocks
def test_every_block_is_the_text_at_its_own_offset_and_a_table_is_kept_whole() -> None:
    """**A citation span resolves against the item's text**, so every block's text has to be
    exactly what sits at its offset, with the blank lines between blocks left out and a run of
    pipe lines kept as one table.

    Delete this and an off-by-one in the offsets passes every other test, and every citation
    this corpus issues points a few characters into the wrong passage."""
    content = "  Intro line.\nSecond line.\n\n\n| a | b |\n| 1 | 2 |\n  \n\nTail.  "

    blocks = text_blocks(content)

    assert [block.kind for block in blocks] == [BlockKind.PROSE, BlockKind.TABLE, BlockKind.PROSE]
    assert [block.text for block in blocks] == [
        "Intro line.\nSecond line.",
        "| a | b |\n| 1 | 2 |",
        "Tail.",
    ]
    for block in blocks:
        assert content[block.start : block.end] == block.text


def test_text_with_nothing_between_its_blank_lines_is_no_blocks() -> None:
    """The positive-empty case the writer refuses on. Delete this and whitespace can become a
    block, which `Block` refuses with an error naming nothing the uploader did."""
    assert text_blocks(" \n\n \t\n") == ()


# ------------------------------------------------------------------ the rows
def test_a_row_carries_the_permissions_chunking_copied_and_the_items_place() -> None:
    """**The row is what the policy reads**, so the owner, the visibility, the department and
    the state on it are held to the item they came from, field by field.

    Delete this and a row can be written with a default visibility or no department, which the
    policy reads as company-wide or as nobody's."""
    item = an_item()
    [first, *_] = chunk_document(item, text_blocks(item.content), bounds=ChunkBounds())

    row = chunk_row(first, item=item)

    assert (row["owner_id"], row["visibility"], row["department"], row["state"]) == (
        OWNER,
        "department",
        "web",
        "published",
    )
    assert (row["chunk_id"], row["document_id"], row["body"]) == (
        first.chunk_id,
        item.item_id,
        first.text,
    )


def test_a_chunk_offered_as_the_row_of_another_item_is_refused() -> None:
    """Delete this and a row can carry one item's permissions over another item's passage."""
    item = an_item()
    [first, *_] = chunk_document(item, text_blocks(item.content), bounds=ChunkBounds())

    with pytest.raises(ChunkStoreError, match="belongs to"):
        chunk_row(first, item=an_item(item_id="k_other"))


# ------------------------------------------------------------------ the statements
def test_every_statement_that_reads_or_updates_a_chunk_carries_the_owners_reach() -> None:
    """**The reach is inside the statement**: the retirement of a document's tail, the read of a
    window and the write of a vector are each built with `reach_predicate` for the owner's
    reach, compared as the whole compiled predicate.

    Delete this and a maintenance statement can reach past the owner, which the policy then
    has to catch alone, and on a connection that skipped the settings it catches nothing."""
    reach = web_reach()
    predicate = compiled(reach_predicate(reach))
    write = EmbeddingWrite(
        chunk_id="k_sop.0000",
        vector=EmbeddedVector(model=MODEL, values=tuple([1.0] + [0.0] * (COLUMN_DIMENSIONS - 1))),
    )

    for statement in (
        retire_tail_statement("k_sop", keep=2, reach=reach),
        window_statement("k_sop", first=0, last=1, reach=reach),
        embedding_update(write, reach=reach, read_at=READ_AT),
    ):
        assert predicate in compiled(statement), compiled(statement)


def test_a_vector_is_written_only_onto_the_row_as_it_was_read() -> None:
    """The update asks for the chunk id and the moment it was read. Delete this and a document
    re-ingested while the server was thinking gets the old text's vector on its new text."""
    write = EmbeddingWrite(
        chunk_id="k_sop.0000",
        vector=EmbeddedVector(model=MODEL, values=tuple([1.0] + [0.0] * (COLUMN_DIMENSIONS - 1))),
    )

    statement = embedding_update(write, reach=web_reach(), read_at=READ_AT).compile(
        dialect=POSTGRES
    )

    assert "chunk.updated_at = " in str(statement)
    assert READ_AT in statement.params.values()
    assert set(statement.params) >= {"embedding_literal", "embedding_model"}


def test_an_update_naming_a_column_an_embedding_does_not_write_is_refused() -> None:
    """Delete this and the update becomes the place a third column is added, which is how a
    re-embed rewrites who may read a passage."""

    class Wider(EmbeddingWrite):
        @property
        def columns(self) -> Mapping[str, object]:
            return {**super().columns, "visibility": "company"}

    write = Wider(
        chunk_id="k_sop.0000",
        vector=EmbeddedVector(model=MODEL, values=tuple([1.0] + [0.0] * (COLUMN_DIMENSIONS - 1))),
    )

    with pytest.raises(ChunkStoreError, match="visibility"):
        embedding_update(write, reach=web_reach(), read_at=READ_AT)
    assert "visibility" not in WRITTEN_COLUMNS


def test_a_rewritten_chunk_loses_its_vector_and_its_model_until_the_job_puts_them_back() -> None:
    """A vector belongs to the text it was made from. Delete this and a document whose text
    changed keeps answering the vector leg with the meaning of what it used to say."""
    item = an_item()
    chunks = chunk_document(item, text_blocks(item.content), bounds=ChunkBounds())
    rows = [chunk_row(one, item=item) for one in chunks]

    text = str(
        upsert_statement(rows).compile(dialect=POSTGRES, compile_kwargs={"literal_binds": True})
    )
    refreshed = text.split("DO UPDATE SET", 1)[1]

    assert "embedding = NULL" in refreshed
    assert "embedding_model = NULL" in refreshed


# ------------------------------------------------------------------ the writer
def test_a_document_is_written_under_its_owners_reach_and_its_embedding_job_names_every_chunk() -> (
    None
):
    """**The positive case for the writer.** The owner's settings go first, then the item, the
    chunks and the retirement of anything past them, and the job returned names the whole
    window, the served model and the owner it runs for.

    Delete this and every refusal below is satisfied by a writer that refuses everything."""
    database = Database()
    item = an_item()
    reach = web_reach()

    job = settle(write_document(a_session(database), item, reach=reach, revision=A_REVISION))

    assert rendered(database.asked[:2]) == rendered(session_settings(reach))
    kinds = [type(one).__name__ for one in database.asked[2:]]
    assert kinds == ["Insert", "Insert", "Update"]
    assert [one.table.name for one in database.asked[2:4]] == ["item", "chunk"]
    assert job is not None
    assert job.task == EMBED_TASK
    assert dict(job.args) == {
        "document_id": "k_sop",
        "first_ordinal": 0,
        "last_ordinal": 1,
        "model": MODEL.identity,
        "owner_id": OWNER,
    }


def test_a_document_its_owner_cannot_reach_is_refused_before_anything_is_written() -> None:
    """**The permission decision at the door.** A department document whose owner reaches
    another department is refused with nothing sent to the database, because rows no job can
    read back are passages found by text search and by no vector, for ever.

    Delete this and the rows are written, and every embedding job for them fails on redrive
    with nothing telling the person who handed the document over."""
    database = Database()

    with pytest.raises(ChunkStoreError, match="cannot reach"):
        settle(
            write_document(
                a_session(database),
                an_item(department="finance"),
                reach=web_reach(),
                revision=A_REVISION,
            )
        )
    assert database.asked == []
    assert "Reach.admits" in A_DOCUMENT_ITS_OWNER_CANNOT_REACH_IS_NOT_INDEXED_ON_THEIR_BEHALF


def test_a_reach_that_is_not_the_owners_cannot_write_their_document() -> None:
    """Delete this and one person's grants can admit another person's document into the corpus."""
    database = Database()
    somebody = Reach(principal_id="p_somebody", departments=("web",))

    with pytest.raises(ChunkStoreError, match="runs as the owner"):
        settle(write_document(a_session(database), an_item(), reach=somebody, revision=A_REVISION))
    assert database.asked == []


def test_an_install_with_no_declared_weights_writes_the_document_and_queues_nothing() -> None:
    """Text search works without a vector leg. Delete this and an unset revision either stops
    ingestion or queues jobs every worker refuses."""
    database = Database()

    job = settle(write_document(a_session(database), an_item(), reach=web_reach(), revision=None))

    assert job is None
    assert [type(one).__name__ for one in database.asked[2:]] == ["Insert", "Insert", "Update"]


def test_a_chunk_no_batch_could_carry_is_refused_at_the_door() -> None:
    """A table is never split, so a large enough one is a chunk no request can carry. Refused
    here, where somebody can be told, rather than by every job after it.

    Delete this and the document is written and its embedding job fails on every redrive."""
    database = Database()
    table = "\n".join(["| a very wide row of a very wide table |"] * 120_000)

    with pytest.raises(EmbeddingError, match="refused rather than split"):
        settle(
            write_document(
                a_session(database), an_item(table), reach=web_reach(), revision=A_REVISION
            )
        )
    assert database.asked == []


def test_a_document_is_committed_before_its_job_is_handed_to_the_queue() -> None:
    """**The enqueue follows the commit.** A job fetched before its rows are visible reads an
    empty window and fails. Delete this and the enqueue can move inside the transaction."""
    database = Database()
    enqueued: list[Job] = []

    async def enqueue(job: Job) -> None:
        database.events.append("enqueue")
        enqueued.append(job)

    job = settle(
        ingest_document(
            sessions_over(database),
            an_item(),
            enqueue=enqueue,
            now=NOW,
            env={REVISION_SETTING: A_REVISION},
        )
    )

    assert database.events == ["begin", "commit", "enqueue"]
    assert enqueued == [job]
    told = rendered(session_settings(Reach(principal_id=OWNER)))
    assert rendered(database.asked[:2]) == told
    assert database.asked[2] is RESOLVE


def test_an_owner_who_reaches_nothing_now_has_nothing_written_or_queued() -> None:
    """Delete this and a person whose grants were revoked can still have documents indexed in
    their name."""
    database = Database(entitlement=EntitlementSet(principal_id=OWNER, grants=()))
    enqueued: list[Job] = []

    async def enqueue(job: Job) -> None:
        enqueued.append(job)

    with pytest.raises(ChunkStoreError, match="reaches no part"):
        settle(
            ingest_document(
                sessions_over(database),
                an_item(),
                enqueue=enqueue,
                now=NOW,
                env={REVISION_SETTING: A_REVISION},
            )
        )
    assert enqueued == []
    assert not any(isinstance(one, Insert) for one in database.asked)


# ------------------------------------------------------------------ the worker
def embed(database: Database, service: Service, **overrides: Any) -> str:
    arguments: dict[str, Any] = {
        "document_id": "k_sop",
        "first_ordinal": 0,
        "last_ordinal": 1,
        "model": MODEL.identity,
        "owner_id": OWNER,
        "sessions": sessions_over(database),
        "service": service,
        "revision": A_REVISION,
        "now": NOW,
        **overrides,
    }
    return settle(run_embed_job(**arguments))


def test_a_window_is_read_under_the_owners_reach_embedded_and_every_row_written() -> None:
    """**The worker end to end, with a stand-in service.** Two transactions, each opened with
    the owner's settings; the read carries the reach; the service is asked once; and one update
    per chunk carries its vector.

    Delete this and every refusal below is satisfied by a worker that never writes."""
    database = Database(window=(("k_sop.0000", "One."), ("k_sop.0001", "Two.")))
    service = Service()

    said = embed(database, service)

    reach = web_reach()
    settings = rendered(session_settings(reach))
    [read] = [one for one in database.asked if isinstance(one, Select) and "chunk" in compiled(one)]
    assert compiled(reach_predicate(reach)) in compiled(read)
    first = database.asked.index(read)
    assert rendered(database.asked[first - 2 : first]) == settings
    assert database.events == ["begin", "commit", "begin", "commit"]
    assert service.calls == 1
    updates = database.updates()
    assert [one.compile(dialect=POSTGRES).params["chunk_id_1"] for one in updates] == [
        "k_sop.0000",
        "k_sop.0001",
    ]
    second = database.asked.index(updates[0])
    assert rendered(database.asked[second - 2 : second]) == settings
    assert "k_sop" in said


def test_a_job_queued_for_another_model_is_refused_before_anything_is_read() -> None:
    """Delete this and vectors from the served model are recorded against a job that asked for
    another, which is a corpus holding two spaces."""
    database = Database()
    service = Service()
    other = served_embedding_model(revision="v2.0.0")

    with pytest.raises(MixedEmbeddingError):
        embed(database, service, model=other.identity)
    assert database.asked == []
    assert service.calls == 0


def test_a_worker_whose_install_declared_no_weights_refuses_every_job_and_sends_nothing() -> None:
    """Delete this and a worker can guess a revision and send a document's text to be refused."""
    database = Database()
    service = Service()

    with pytest.raises(EmbeddingUnavailable):
        embed(database, service, revision=None)
    assert database.asked == []
    assert service.calls == 0


def test_an_owner_who_reaches_nothing_now_has_no_window_read_or_sent() -> None:
    """**The reach is resolved when the job runs, not when it was queued.** Delete this and a
    grant revoked after the enqueue is still honoured by the job, reading and sending text on
    behalf of somebody who may no longer read it."""
    database = Database(entitlement=EntitlementSet(principal_id=OWNER, grants=()))
    service = Service()

    with pytest.raises(ChunkStoreError, match="reaches no part"):
        embed(database, service)
    assert not any(
        isinstance(one, Select) and "know.chunk" in compiled(one) for one in database.asked
    )
    assert service.calls == 0


def test_a_window_the_owner_can_no_longer_see_any_of_is_not_a_success() -> None:
    """An empty read is a scan that found nothing and never a job done. Delete this and a
    window moved out of reach reports itself embedded."""
    database = Database(window=())
    service = Service()

    with pytest.raises(EmbeddingError, match="report"):
        embed(database, service)
    assert service.calls == 0
    assert database.updates() == []


def test_a_run_the_server_did_not_finish_writes_nothing() -> None:
    """The ingest leg's outage writes nothing and fails the job for the queue. Delete this and a
    partial run is written and reported done."""
    database = Database()

    with pytest.raises(EmbeddingError, match="nothing was written"):
        embed(database, Service(down=True))
    assert database.updates() == []
    assert database.events == ["begin", "commit"]


def test_a_row_that_changed_since_it_was_read_refuses_the_whole_window() -> None:
    """**Whole or not at all.** The update that finds no row rolls the transaction back. Delete
    this and the rest of the window is written around a row that holds different text now."""
    database = Database(updated=0)

    with pytest.raises(ChunkStoreError, match="not as it was read"):
        embed(database, Service())
    assert database.events == ["begin", "commit", "begin", "rollback"]


def test_the_write_follows_the_read_by_the_moment_it_was_read_at() -> None:
    """Delete this and the worker can stamp the update with a time of its own, which matches no
    row and refuses every window, or matches rows it never read."""
    database = Database()
    embed(database, Service())

    [update] = database.updates()
    assert READ_AT in update.compile(dialect=POSTGRES).params.values()
