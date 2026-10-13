"""Moving the corpus to another embedding model, one page of stale chunks at a time.

`brain.knowledge.embedding` decided everything about a rebuild except doing it: the identity a
vector is recorded under, the cursor that resumes by key, the plan that refuses a rebuild onto the
model the corpus already holds, and `brain.knowledge.embed_queue.rebuild_job`, which names the
task a page of one is carried out by. **Nothing registered that task and nothing enqueued the
first page**, so a model change moved no chunk, which is the gap
`brain.ops.acceptance_checks_knowledge_models` named when it refused to claim M7.3.5. This module
is the page itself.

**A page finds the stale chunks and queues their windows, and embeds nothing.** The embedding of a
window is `brain.knowledge.chunk_store.run_embed_job`, which reads it back under the owner's reach
as it stands, sends it to the inference server, and writes two columns of each row or nothing. A
rebuild that embedded inside its own page would be a second implementation of that, and the second
copy is the one that would drop a permission or write a vector onto text it was not made from.
Queueing `embed_job` reuses every one of its guards, runs on the queue the same slots drain, and
retries one failed window without repeating the rest.

**"Stale" is a fact about the row and not about the rebuild, which is what makes it resume by
itself.** A chunk is stale while its recorded model is not the one this install serves, so a window
that was embedded drops out of the next page's selection without anything remembering that it was,
and a page that died half way costs a re-read of what it already found. The position is the last
chunk id found and the next page reads strictly after it, never an offset, for the reason
`brain.knowledge.embedding.A_REBUILD_RESUMES_BY_KEY_AND_NEVER_BY_OFFSET` gives.

**The page reads across owners, so it runs on the worker's own login and never on the application's
role.** `know.chunk`'s policy admits a reader only through a person's reach, and a rebuild has no
person: under the application role it would find company chunks and nothing else and report a
finished rebuild over a corpus it never saw. The worker connects as the database owner for exactly
this kind of work (`brain.ops.worker.schedule_url`), and what the page selects is ids and ordinals,
never a body. The windows it queues are then embedded as each chunk's owner, under that owner's
reach, which is where the permission is judged: an owner who now reaches nothing has a window that
fails and stays stale, visibly, rather than a document embedded on nobody's behalf.

**Archived and retired chunks are not stale, because nothing retrieves them.** A rebuild that
embedded them would spend the server's time on text no answer can reach and report them as covered.

**What is rejected.** A `know.chunks_to_reembed` function with `SECURITY DEFINER`, as `0040` did for
the review sweep, because the worker already holds the login that reads past the policy and a
function would add a grant to the application role for a read it has no use for. A model change
that rebuilds on its own the moment the setting changes: the identity is the install's declared
revision, a rebuild is hours of the server's time, and it is started by `python -m
brain.ops.worker --reembed` by somebody who has read what it will do.

**While it runs, retrieval is on text search alone.** That is `brain.knowledge.embedding.
A_MIXED_CORPUS_HAS_NO_VECTOR_LEG`, which decided that answers do not keep using the previous
vectors, because a leg that quietly returns half of what it should is worse than one that is
visibly absent. The owner's wording for M7.7.8 says the previous vectors keep serving; that is the
narrowing needs-rupash 186 puts to him.

Scope: the statement, the grouping, and the one function a worker runs. It opens no connection of
its own and holds no queue; the sessions and the enqueue are handed in.

Task ids: M7.3.5, M7.7.8
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.knowledge.embed_policy import EmbeddingUnavailable, served_embedding_model
from brain.knowledge.embed_queue import REEMBED_TASK, embed_job, rebuild_job
from brain.knowledge.embedding import (
    DEFAULT_BATCH_SIZE,
    EmbeddingError,
    EmbeddingModel,
    MixedEmbeddingError,
    RebuildCursor,
    RebuildPlan,
)
from brain.knowledge.search import CHUNK, EMBEDDING_MODEL_FIELD
from brain.knowledge.visibility import OWNER_FIELD
from brain.ops.queue import Job

#: The states whose chunks anything retrieves, and so the only ones worth a vector.
RETRIEVABLE_STATES: Final = ("draft", "published")

#: Why a page reads ids and ordinals and nothing else.
A_REBUILD_PAGE_READS_NO_BODY: Final = (
    "The page reads across every owner on the worker's own login, so what it selects is a chunk's "
    "id, document, owner and ordinal and never its text. The text is read by the window's own job "
    "under the owner's reach, which is where the permission is judged."
)

#: Why a window that cannot run leaves its chunks stale and does not mark them covered.
A_WINDOW_THAT_FAILS_STAYS_STALE: Final = (
    "A chunk is stale for as long as its recorded model is not the one this install serves. A "
    "window whose owner reaches nothing now, or whose server did not answer, writes nothing, so "
    "its chunks are found again by the next page and the count of stale chunks says so."
)


@dataclass(frozen=True)
class Window:
    """One document's stale chunks as an ordinal window and the owner they are embedded for."""

    document_id: str
    owner_id: str
    first_ordinal: int
    last_ordinal: int
    chunks: int


@dataclass(frozen=True)
class Page:
    """What one page found: the windows to queue, how many chunks, and where it stopped."""

    windows: tuple[Window, ...]
    found: int
    last_chunk_id: str
    exhausted: bool


def stale_chunks(model_identity: str, *, after_chunk_id: str, size: int) -> sa.Select[Any]:
    """The next `size` chunks after this id that are retrievable and not on this model.

    `IS DISTINCT FROM`, so a chunk whose model nobody recorded is stale as well as one recorded as
    another: a vector with no identity cannot be compared with anything. Ordered by the key and
    nothing else, which is what lets the position be the last id.
    """
    return (
        sa.select(
            CHUNK.c.chunk_id,
            CHUNK.c.document_id,
            CHUNK.c.ordinal,
            CHUNK.c[OWNER_FIELD].label("owner_id"),
        )
        .where(
            CHUNK.c.deleted_at.is_(None),
            CHUNK.c.state.in_(RETRIEVABLE_STATES),
            CHUNK.c[EMBEDDING_MODEL_FIELD].is_distinct_from(model_identity),
            CHUNK.c.chunk_id > after_chunk_id,
        )
        .order_by(CHUNK.c.chunk_id)
        .limit(size)
    )


def stale_count(model_identity: str) -> sa.Select[Any]:
    """How many chunks are stale on this model, for the claim that a rebuild reached them all."""
    return (
        sa.select(sa.func.count())
        .select_from(CHUNK)
        .where(
            CHUNK.c.deleted_at.is_(None),
            CHUNK.c.state.in_(RETRIEVABLE_STATES),
            CHUNK.c[EMBEDDING_MODEL_FIELD].is_distinct_from(model_identity),
        )
    )


def windows_of(rows: Sequence[Mapping[str, Any]]) -> tuple[Window, ...]:
    """The rows as one window per (document, owner), in the order each was first seen.

    A document's ordinals are not contiguous in key order (`c10` sorts before `c2`), so the window
    is the span from the lowest ordinal found to the highest, which `run_embed_job` reads as a
    range. A span can include a chunk already on the new model; it is embedded again, which is
    harmless because a vector is a deterministic function of the text and the weights.
    """
    spans: dict[tuple[str, str], list[int]] = {}
    for row in rows:
        spans.setdefault((str(row["document_id"]), str(row["owner_id"])), []).append(
            int(row["ordinal"])
        )
    return tuple(
        Window(
            document_id=document,
            owner_id=owner,
            first_ordinal=min(ordinals),
            last_ordinal=max(ordinals),
            chunks=len(ordinals),
        )
        for (document, owner), ordinals in spans.items()
    )


def page_of(rows: Sequence[Mapping[str, Any]], *, size: int) -> Page:
    """One page's result. Exhausted when the selection came back short of the size asked for."""
    if size < 1:
        msg = "a page of no chunks reads nothing and never ends"
        raise EmbeddingError(msg)
    return Page(
        windows=windows_of(rows),
        found=len(rows),
        last_chunk_id=str(rows[-1]["chunk_id"]) if rows else "",
        exhausted=len(rows) < size,
    )


async def read_page(
    sessions: async_sessionmaker[AsyncSession],
    model_identity: str,
    *,
    after_chunk_id: str,
    size: int,
) -> Page:
    """Ask the database for the next page. The sessions are the worker's own login's, never the
    application role's: see `A_REBUILD_PAGE_READS_NO_BODY`."""
    async with sessions() as session, session.begin():
        result = await session.execute(
            stale_chunks(model_identity, after_chunk_id=after_chunk_id, size=size)
        )
        rows = [dict(one) for one in result.mappings().all()]
    return page_of(rows, size=size)


def jobs_for(page: Page, model: EmbeddingModel) -> tuple[Job, ...]:
    """The window jobs a page queues, each `embed_job` as an ingest would have built it."""
    return tuple(
        embed_job(
            document_id=one.document_id,
            first_ordinal=one.first_ordinal,
            last_ordinal=one.last_ordinal,
            model=model,
            owner_id=one.owner_id,
        )
        for one in page.windows
    )


def served_here(revision: str | None, model: str) -> EmbeddingModel:
    """The model this install serves, refused when a job was queued for another.

    An install with no declared revision refuses every page, with the sentence saying so, rather
    than guessing one: nothing would be recorded under an identity the corpus was asked for.
    """
    if revision is None:
        msg = (
            "this worker was handed a rebuild and its install has declared no embedding revision. "
            "Nothing was read or queued"
        )
        raise EmbeddingUnavailable(msg)
    served = served_embedding_model(revision=revision)
    if served.identity != model:
        msg = (
            f"the rebuild was queued for {model} and this worker serves {served.identity}; "
            "carrying it on would leave the corpus holding both"
        )
        raise MixedEmbeddingError(msg)
    return served


async def run_reembed_page(
    sessions: async_sessionmaker[AsyncSession],
    enqueue: Callable[[Job], Awaitable[object]],
    *,
    after_chunk_id: str,
    size: int,
    model: str,
    revision: str | None,
) -> str:
    """What the `knowledge.reembed` task does: find a page, queue its windows and the next page.

    Every window is queued before the next page is, so a page that dies between the two leaves
    windows queued and a position that did not move, and the next run finds the same chunks
    again: queueing a window twice is safe because embedding is (`Redrive.SAFE`). The answer names
    the counts of this run's own work and nothing about any document.
    """
    served = served_here(revision, model)
    page = await read_page(sessions, served.identity, after_chunk_id=after_chunk_id, size=size)
    for job in jobs_for(page, served):
        await enqueue(job)
    if page.exhausted:
        return (
            f"re-embedding to {served.identity}: {page.found} stale chunk(s) in the last page, "
            f"{len(page.windows)} window(s) queued, and no more after "
            f"{after_chunk_id or 'the beginning'}"
        )
    plan = RebuildPlan(to_model=served, batch_size=size)
    cursor = RebuildCursor(model=served, after_chunk_id=after_chunk_id).advance(
        last_chunk_id=page.last_chunk_id, written=page.found, exhausted=False
    )
    following = rebuild_job(plan=plan, cursor=cursor)
    if following is None:  # pragma: no cover - a cursor that is not exhausted always has one
        return f"re-embedding to {served.identity}: finished"
    await enqueue(following)
    return (
        f"re-embedding to {served.identity}: {page.found} stale chunk(s), "
        f"{len(page.windows)} window(s) queued, next page after {page.last_chunk_id}"
    )


async def start_rebuild(
    sessions: async_sessionmaker[AsyncSession],
    enqueue: Callable[[Job], Awaitable[object]],
    *,
    revision: str | None,
    size: int = DEFAULT_BATCH_SIZE,
) -> tuple[int, str]:
    """Queue the first page, or say why there is nothing to rebuild.

    Zero when a page was queued or the corpus is already on this model, the exit code `main`
    returns. The count of stale chunks is said, because it is the number a person compares with
    what is left when the last page has run: a rebuild is finished when it is zero, not when the
    jobs are.
    """
    if revision is None:
        return 2, (
            "this install has declared no embedding revision, so there is no model to rebuild "
            "onto; set it in the setup wizard first"
        )
    served = served_embedding_model(revision=revision)
    async with sessions() as session, session.begin():
        stale = int((await session.execute(stale_count(served.identity))).scalar_one())
    if stale == 0:
        return 0, f"nothing to rebuild: every retrievable chunk is on {served.identity}"
    plan = RebuildPlan(to_model=served, batch_size=size)
    first = rebuild_job(plan=plan, cursor=plan.start())
    if first is None:  # pragma: no cover - a cursor at the start is never exhausted
        return 0, "nothing to rebuild"
    await enqueue(first)
    return 0, (
        f"rebuild to {served.identity} queued as task {REEMBED_TASK}: {stale} stale chunk(s) to "
        "find. Retrieval is on text search alone until none is left; count again with the same "
        "command and the rebuild is finished when it says nothing is left to rebuild"
    )
