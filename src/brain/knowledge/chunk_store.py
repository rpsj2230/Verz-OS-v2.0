"""Where a document's chunks are written, read back for embedding, and given their vectors.

`brain.knowledge.search` declares `know.chunk` and every query over it, `chunking` makes the only
value a chunk can be, and `embed_queue` makes the only update an embedding can be. Until this
module the table had no writer, so every one of those was a statement about rows nobody put
there. This is the store half of that split, in the shape `item_store` and `row_store` take: it
holds a session and decides as little as it can.

**Every statement here runs under a person's reach, and it is the owner's, resolved when the
statement runs.** `search` says it in its own docstring: "A worker re-chunking a document runs as
that document's owner and sets the same settings a request does, through the same function."
So the writer and the worker both resolve the owner's grants through
`gate.entitlements_with_lapse`, reduce them with `reach_for` against the live department
registry, set `session_settings` for that `Reach`, and put `reach_predicate` inside every
statement that reads or updates a chunk. There is no principal here with more reach than a
caller, and there is no second answer to what a chunk's owner may reach. See
`THE_STORE_RUNS_AS_THE_OWNER_AND_NEVER_AS_ITSELF`.

**A document is written only if its owner can reach it, and that is checked before a row is
written rather than discovered by a job.** `know.chunk`'s insert policy is `WITH CHECK (true)`, so
the database would take the rows. What it would not do is let anybody embed them: the worker
reads the window back under the owner's reach, finds nothing, and fails the job every time it
is redriven, while the passages sit in the corpus found by text search and by no vector. So
`Reach.admits`, the Python half of the policy, is asked about the rows first. See
`A_DOCUMENT_ITS_OWNER_CANNOT_REACH_IS_NOT_INDEXED_ON_THEIR_BEHALF`.

**The text is the item's, and it is cut into blocks without a layout model.** `KnowledgeItem`
holds text because "everything in the knowledge layer is text by the time it is stored", so what
arrives here has already been parsed by whatever produced it, and asking the layout parser to
parse it again would put the inference server between a person and text search. `text_blocks`
cuts on blank lines and keeps a run of lines that all begin with a pipe as one table, which is
the one layout fact plain text carries and the one `chunk_blocks` refuses to split. Rejected:
treating the whole item as one prose block, which would cut tables across chunks.

**An embedding job is enqueued after the commit, never inside the transaction.** A job enqueued
before the rows are committed can be fetched before they are visible, and the worker would find
nothing in its window and fail. The price is stated: a process that dies between the commit and
the enqueue leaves a document written and unembedded, found by text search and not by vector,
and nothing records it. That is the ingest leg's outage response in
`embed_policy.OUTAGE_POLICY` arriving by another route, and the repair is a rebuild, which is
`brain.knowledge.embedding`'s command and has no caller either.

**The worker holds no transaction while the server is thinking.** The window is read in one
transaction, the batches are sent with none open, and the writes are applied in a second
transaction that asks for each row as it was read: the chunk id, the `updated_at` the read saw,
and the reach. A document re-ingested in between has a new `updated_at`, the update finds no
row, and the whole window is refused rather than a vector for the old text being written onto
the new. See `A_VECTOR_IS_WRITTEN_ONLY_ONTO_THE_TEXT_IT_WAS_MADE_FROM`.

**What this does not do, stated.** A document that shrank and later grew again collides with its
own retired rows: chunk ids are the item id and an ordinal, the retired row still holds the id,
and the upsert is refused by the update policy because a retired row is out of every reach. It
fails loudly and writes nothing; clearing retired rows is a delete nobody holds a grant for. And
nothing supersedes a document's chunks, because 0046 records that no statement can move a live
chunk to `superseded` under the current policy.

No leaf is claimed below, for the reason `brain.knowledge.embed` gives about the one this serves.

Task ids: none
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import Update

from brain.gate.entitlement_store import RESOLVE, entitlements_from
from brain.knowledge.chunking import Block, BlockKind, Chunk, ChunkBounds, chunk_document
from brain.knowledge.document_tools import departments_query
from brain.knowledge.embed import embed_units
from brain.knowledge.embed_policy import (
    EmbeddingUnavailable,
    EmbedRun,
    embedding_revision,
    served_embedding_model,
)
from brain.knowledge.embed_queue import (
    WRITTEN_COLUMNS,
    EmbeddingService,
    EmbeddingUnit,
    EmbeddingWrite,
    embed_job,
    plan_batches,
    units_for,
)
from brain.knowledge.embedding import EMBEDDING_FIELD, EmbeddingError, MixedEmbeddingError
from brain.knowledge.item import KnowledgeItem
from brain.knowledge.item_store import put_item, reach_from
from brain.knowledge.search import (
    CHUNK,
    EMBEDDING_DIMENSIONS,
    Reach,
    Vector,
    chunk_text_fields,
    reach_predicate,
    session_settings,
    to_vector_literal,
)
from brain.ops.queue import Job

# ------------------------------------------------------------------ written-down reasons

#: Why nothing here has a reach of its own.
THE_STORE_RUNS_AS_THE_OWNER_AND_NEVER_AS_ITSELF: Final = (
    "The writer and the embedding worker have nobody present, and the tempting shape is a role "
    "that sees past know.chunk's policy because it is only indexing. That role would be a "
    "principal with more reach than any caller, which E_run(caller, agent) = E(caller) ∩ "
    "ceiling says does not exist, and a maintenance query written through it is exactly what "
    "the policy is the second wall against. So both run as the document's owner, with the "
    "owner's grants resolved at the moment the statement runs, and a grant revoked since the "
    "document was queued is revoked for the job too."
)

#: Why the owner's reach is checked before anything is written.
A_DOCUMENT_ITS_OWNER_CANNOT_REACH_IS_NOT_INDEXED_ON_THEIR_BEHALF: Final = (
    "The insert policy on know.chunk admits any row, and the read and update policies admit only "
    "rows within a reach. A document written for an owner who cannot reach it is therefore a set "
    "of rows no embedding job can read back: every job fails, every redrive fails, and the "
    "passages are found by text search and by no vector with nothing reporting why. So the rows "
    "are put to Reach.admits before they are written, and a document its owner cannot reach is "
    "refused at the door, where the person handing it over can be told."
)

#: Why the write asks for the row as it was read.
A_VECTOR_IS_WRITTEN_ONLY_ONTO_THE_TEXT_IT_WAS_MADE_FROM: Final = (
    "The window is read, the batches go to the server with no transaction open, and the writes "
    "come back seconds later. A document re-ingested in that gap has new text under the same "
    "chunk ids, and an update keyed by id alone would store the old text's vector against the "
    "new text under an identity that says it is right. So each update also asks for the "
    "updated_at the read saw, an update that finds no row refuses the whole window, and the job "
    "the re-ingest enqueued embeds the new text."
)

#: Why a row an update could not find stops every write in the window.
A_WINDOW_IS_WRITTEN_WHOLE_OR_NOT_AT_ALL: Final = (
    "embed_policy.OUTAGE_POLICY says the ingest leg writes nothing when it fails, and "
    "A_RUN_THAT_STOPPED_IS_NOT_A_RUN_THAT_FINISHED says a partial run is not a finished one. An "
    "update that finds no row is the same event from the database's side: the row changed, left "
    "the owner's reach, or was retired. Writing the rest would report a window embedded that is "
    "not, so the transaction is rolled back and the job fails for the queue to see."
)

# ------------------------------------------------------------------ the text, as blocks

#: A blank line, which is where one block ends and the next begins.
_BLANK_LINE: Final = re.compile(r"\n[ \t]*\n")

#: What begins every line of a table in the only table syntax plain text has.
TABLE_ROW_MARK: Final = "|"


class ChunkStoreError(Exception):
    """A document that cannot be written to the corpus, or a window that cannot be embedded.

    Outside the `brain.core.errors` taxonomy like every refusal in this package: those outcomes
    describe an answer to a person, and this describes a refusal to write a row.
    """


def text_blocks(content: str) -> tuple[Block, ...]:
    """An item's text as the blocks `chunk_document` cuts, in document order, offsets exact.

    A block is a run of text between blank lines, with the whitespace at either end left out so
    that a citation span never begins on a space. A block whose every line begins with a pipe is
    a table and is kept whole; see the module docstring for why that is the only layout this
    reads. Offsets are into `content` itself, which is what a citation resolves against.
    """
    blocks: list[Block] = []
    start = 0
    for boundary in (*_BLANK_LINE.finditer(content), None):
        end = len(content) if boundary is None else boundary.start()
        segment = content[start:end]
        stripped = segment.strip()
        if stripped:
            offset = start + segment.index(stripped)
            lines = [line.strip() for line in stripped.splitlines() if line.strip()]
            is_table = all(line.startswith(TABLE_ROW_MARK) for line in lines)
            blocks.append(
                Block(
                    kind=BlockKind.TABLE if is_table else BlockKind.PROSE,
                    text=stripped,
                    start=offset,
                )
            )
        if boundary is not None:
            start = boundary.end()
    return tuple(blocks)


# ------------------------------------------------------------------ the rows


def chunk_row(chunk: Chunk, *, item: KnowledgeItem) -> dict[str, object]:
    """One chunk as the columns of `know.chunk`, permissions from the chunk and nowhere else.

    The owner and the visibility are read off `chunk.permissions`, which `chunk_document` copied
    from the item and compared before returning. The department is the item's, because the scope
    on the permissions is a predicate and the column is the name it tests, and it is stored the
    way `item_store.row_values` stores it so the item and its chunks name one place. The text
    columns the database cannot compute come from `chunk_text_fields`, the one function that
    produces them.
    """
    if chunk.document_id != item.item_id:
        msg = (
            f"chunk {chunk.chunk_id!r} belongs to {chunk.document_id!r} and was offered as a row "
            f"of {item.item_id!r}; a row carries the permissions of the item it is written with"
        )
        raise ChunkStoreError(msg)
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "ordinal": chunk.ordinal,
        "kind": chunk.kind.value,
        "title": item.title,
        "section": chunk.section,
        "page": chunk.page,
        "span_start": chunk.start,
        "span_end": chunk.end,
        "body": chunk.text,
        **chunk_text_fields(chunk.text),
        "owner_id": chunk.owner_id,
        "department": item.visibility.department or None,
        "visibility": chunk.visibility.value,
        "state": item.state.value,
    }


def upsert_statement(rows: Sequence[Mapping[str, object]]) -> Any:
    """Write these chunks, replacing live rows with the same ids, and clear their vectors.

    The vector and its model are cleared on every rewrite, because a vector belongs to the text
    it was made from and the text may just have changed; the job enqueued with this write puts
    them back. `updated_at` moves, which is what `A_VECTOR_IS_WRITTEN_ONLY_ONTO_THE_TEXT_IT_WAS_
    MADE_FROM` reads.
    """
    statement = insert(CHUNK).values([dict(row) for row in rows])
    refreshed = {name: statement.excluded[name] for name in rows[0] if name != "chunk_id"}
    return statement.on_conflict_do_update(
        index_elements=[CHUNK.c.chunk_id],
        set_={
            **refreshed,
            EMBEDDING_FIELD: None,
            "embedding_model": None,
            "updated_at": sa.func.now(),
        },
    )


def retire_tail_statement(document_id: str, *, keep: int, reach: Reach) -> Update:
    """Retire this document's live chunks from ordinal `keep` on, within the reach.

    `statement_timestamp()` and nothing else, because that is the one stamp 0046's update policy
    accepts on the new row, and a retired row stays out of every reach after it.
    """
    return (
        sa.update(CHUNK)
        .where(
            sa.and_(
                CHUNK.c.document_id == document_id,
                CHUNK.c.ordinal >= keep,
                reach_predicate(reach),
            )
        )
        .values(deleted_at=func.statement_timestamp())
    )


def window_statement(document_id: str, *, first: int, last: int, reach: Reach) -> sa.Select[Any]:
    """The live chunks of one ordinal window, within the reach, in reading order."""
    return (
        sa.select(CHUNK.c.chunk_id, CHUNK.c.body, CHUNK.c.updated_at)
        .where(
            sa.and_(
                reach_predicate(reach),
                CHUNK.c.document_id == document_id,
                CHUNK.c.ordinal.between(first, last),
            )
        )
        .order_by(CHUNK.c.ordinal)
    )


def embedding_update(write: EmbeddingWrite, *, reach: Reach, read_at: datetime) -> Update:
    """One embedding, as an update of the two columns `EmbeddingWrite.columns` names.

    The columns are taken from the write rather than listed here, and a name outside
    `WRITTEN_COLUMNS` is refused, so this cannot become the place a third column is added. The
    vector is bound as text and cast, for the reason `search.to_vector_literal` gives.
    """
    columns = write.columns
    unexpected = sorted(set(columns) - set(WRITTEN_COLUMNS))
    if unexpected:
        msg = (
            f"an embedding for {write.chunk_id!r} would write {unexpected}; an embedding "
            f"writes {list(WRITTEN_COLUMNS)} and nothing else"
        )
        raise ChunkStoreError(msg)
    values: dict[str, object] = {}
    for name, value in columns.items():
        if name == EMBEDDING_FIELD:
            literal = to_vector_literal(cast("Sequence[float]", value))
            values[name] = sa.cast(
                sa.bindparam("embedding_literal", literal, type_=sa.Text),
                Vector(EMBEDDING_DIMENSIONS),
            )
        else:
            values[name] = value
    return (
        sa.update(CHUNK)
        .where(
            sa.and_(
                CHUNK.c.chunk_id == write.chunk_id,
                CHUNK.c.updated_at == read_at,
                reach_predicate(reach),
            )
        )
        .values(**values)
    )


# ------------------------------------------------------------------ the reach


async def reach_of(session: AsyncSession, principal_id: str, *, now: datetime) -> Reach | None:
    """What this person reaches of the document plane now, in this transaction, or None.

    The resolver is told whose grants it reads before it reads them, which is
    `entitlement_store.THE_DATABASE_IS_TOLD_WHOSE_GRANTS_ARE_READ`, and `session_settings` for a
    reach of no departments is exactly that statement. The registry is every live department,
    as `document_tools` reads it, because a grant with no department clause reaches all of them
    and the second wall takes names rather than a wildcard. A grant `reach_for` refuses is read
    as no reach, through `item_store.reach_from`, for the reason that module gives.
    """
    for setting in session_settings(Reach(principal_id=principal_id)):
        await session.execute(setting)
    payload = (
        await session.execute(RESOLVE, {"principal_id": principal_id, "at": now})
    ).scalar_one()
    entitlement = entitlements_from(payload)
    registry = (await session.execute(departments_query().statement)).scalars().all()
    return reach_from(entitlement, departments=[str(slug) for slug in registry], now=now)


async def _within(session: AsyncSession, reach: Reach) -> None:
    for setting in session_settings(reach):
        await session.execute(setting)


# ------------------------------------------------------------------ the writer


async def write_document(
    session: AsyncSession,
    item: KnowledgeItem,
    *,
    reach: Reach,
    revision: str | None,
    bounds: ChunkBounds | None = None,
) -> Job | None:
    """Write an item and its chunks in this transaction, and return the job that embeds them.

    None when this install has declared no embedding revision, which is an install with no
    vector leg; see `embed_policy.AN_UNDECLARED_REVISION_IS_AN_INSTALL_WITH_NO_VECTOR_LEG`. Does
    not commit and does not enqueue: `ingest_document` does both, in that order.

    Four refusals before a row is written. A reach that is not the owner's is somebody else's
    reach judging this document. A document with no text has no passage and a window over it
    names nothing. A document its owner cannot reach is
    `A_DOCUMENT_ITS_OWNER_CANNOT_REACH_IS_NOT_INDEXED_ON_THEIR_BEHALF`. And a chunk no batch
    could carry is refused here, through `plan_batches`, rather than by every job after it.
    """
    if reach.principal_id != item.owner_id:
        msg = (
            f"a reach for {reach.principal_id!r} was offered to write {item.item_id!r}, which "
            f"{item.owner_id!r} stewards; the store runs as the owner and nobody else"
        )
        raise ChunkStoreError(msg)
    chunks = chunk_document(item, text_blocks(item.content), bounds=bounds or ChunkBounds())
    if not chunks:
        msg = f"{item.item_id!r} holds no text between its blank lines, so it has no passage"
        raise ChunkStoreError(msg)
    model = None if revision is None else served_embedding_model(revision=revision)
    if model is not None:
        plan_batches(units_for(chunks), model=model)
    rows = [chunk_row(chunk, item=item) for chunk in chunks]
    if not all(reach.admits(row) for row in rows):
        msg = (
            f"{item.owner_id!r} cannot reach {item.item_id!r} as it would be written. "
            f"{A_DOCUMENT_ITS_OWNER_CANNOT_REACH_IS_NOT_INDEXED_ON_THEIR_BEHALF}"
        )
        raise ChunkStoreError(msg)

    await _within(session, reach)
    await put_item(session, item)
    await session.execute(upsert_statement(rows))
    await session.execute(retire_tail_statement(item.item_id, keep=len(rows), reach=reach))
    if model is None:
        return None
    return embed_job(
        document_id=item.item_id,
        first_ordinal=0,
        last_ordinal=len(rows) - 1,
        model=model,
        owner_id=item.owner_id,
    )


async def ingest_document(
    sessions: async_sessionmaker[AsyncSession],
    item: KnowledgeItem,
    *,
    enqueue: Callable[[Job], Awaitable[object]],
    now: datetime,
    env: Mapping[str, str] | None = None,
    bounds: ChunkBounds | None = None,
) -> Job | None:
    """Write an admitted item to the corpus, commit, then hand its embedding job to the queue.

    `enqueue` is whatever carries a `Job` onto the queue, which is `brain.ops.queue.enqueue_job`
    bound to an app with the task registered. A parameter rather than an app, so the door that
    calls this decides which process holds the queue and this module names no driver.

    The owner's reach is resolved in the same transaction the rows are written in, so the reach
    that admitted the document is the one the policy sees. See the module docstring for why the
    enqueue follows the commit.
    """
    revision = embedding_revision(env)
    async with sessions() as session, session.begin():
        reach = await reach_of(session, item.owner_id, now=now)
        if reach is None:
            msg = (
                f"{item.owner_id!r} reaches no part of the document plane. "
                f"{A_DOCUMENT_ITS_OWNER_CANNOT_REACH_IS_NOT_INDEXED_ON_THEIR_BEHALF}"
            )
            raise ChunkStoreError(msg)
        job = await write_document(session, item, reach=reach, revision=revision, bounds=bounds)
    if job is not None:
        await enqueue(job)
    return job


# ------------------------------------------------------------------ the worker


@dataclass(frozen=True)
class StoredChunk:
    """One chunk as the worker read it: what to send, and the moment it was read at."""

    chunk_id: str
    text: str
    updated_at: datetime


async def run_embed_job(
    *,
    document_id: str,
    first_ordinal: int,
    last_ordinal: int,
    model: str,
    owner_id: str,
    sessions: async_sessionmaker[AsyncSession],
    service: EmbeddingService,
    revision: str | None,
    now: datetime,
) -> str:
    """What the `knowledge.embed` task does: read, embed, write, or raise and write nothing.

    Refuses a job queued for a model this worker does not serve before anything is read: the
    vectors would be recorded under an identity the corpus was not asked for. An install with no
    declared revision refuses every job with the sentence saying so, rather than guessing one.

    The window is read in one transaction and written in another, with the server asked in
    between and no transaction open. See `A_VECTOR_IS_WRITTEN_ONLY_ONTO_THE_TEXT_IT_WAS_MADE_FROM`
    and `A_WINDOW_IS_WRITTEN_WHOLE_OR_NOT_AT_ALL`. The answer names the document and how much of
    it was written, which is an operator's line about work this job did and not a count of
    anything hidden from anybody.
    """
    if revision is None:
        msg = (
            "this worker was handed an embedding job and its install has declared no revision. "
            "Nothing was read or sent"
        )
        raise EmbeddingUnavailable(msg)
    served = served_embedding_model(revision=revision)
    if served.identity != model:
        msg = (
            f"the job was queued for {model} and this worker serves {served.identity}; storing "
            "its vectors would record a model the corpus was not asked for"
        )
        raise MixedEmbeddingError(msg)

    async with sessions() as session, session.begin():
        reach = await reach_of(session, owner_id, now=now)
        if reach is None:
            msg = (
                f"{owner_id!r} reaches no part of the document plane now, so the window of "
                f"{document_id!r} cannot be read on their behalf and nothing was sent"
            )
            raise ChunkStoreError(msg)
        await _within(session, reach)
        result = await session.execute(
            window_statement(document_id, first=first_ordinal, last=last_ordinal, reach=reach)
        )
        stored = tuple(
            StoredChunk(chunk_id=str(row.chunk_id), text=str(row.body), updated_at=row.updated_at)
            for row in result
        )

    units = tuple(EmbeddingUnit(chunk_id=one.chunk_id, text=one.text) for one in stored)

    # A named call inside a function handed to the thread, rather than the function handed
    # over bare: `brain.ops.controls.call_sites` reads calls, and a callable passed as an
    # argument is one it cannot see, which would list this step as reached by nothing.
    def embed() -> EmbedRun:
        return embed_units(units, service=service, revision=revision)

    run = await asyncio.to_thread(embed)
    if not run.is_complete:
        msg = (
            f"{run.completed} of {run.planned} batch(es) of {document_id!r} came back and "
            f"nothing was written: {run.failure}"
        )
        raise EmbeddingError(msg)

    read_at = {one.chunk_id: one.updated_at for one in stored}
    async with sessions() as session, session.begin():
        await _within(session, reach)
        for write in run.writes:
            update = embedding_update(write, reach=reach, read_at=read_at[write.chunk_id])
            written = cast("CursorResult[Any]", await session.execute(update))
            if written.rowcount != 1:
                msg = (
                    f"chunk {write.chunk_id!r} was not as it was read, so no vector of "
                    f"{document_id!r} was written. {A_WINDOW_IS_WRITTEN_WHOLE_OR_NOT_AT_ALL}"
                )
                raise ChunkStoreError(msg)
    return f"embedded {len(run.writes)} chunk(s) of {document_id} as {served.identity}"
