"""Moving the corpus onto another embedding model: the page, the windows it queues, and the whole
path against a real PostgreSQL.

The pure halves need no server: the statement is rendered and read, the windows are grouped from
rows, and a page is run over a stand-in read. The database half is the claim the leaf makes: two
departments' documents are embedded on one model, the install then serves another, and the
rebuild, run the way the worker runs it (the page on the worker's own login, each window on the
application role as its owner), leaves every retrievable chunk on the new model with its owner,
department and visibility exactly as they were.

Task ids: M7.3.5, M7.7.8
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from brain.db import normalise_database_url
from brain.knowledge import reembed
from brain.knowledge.chunk_store import run_embed_job
from brain.knowledge.embed_policy import EmbeddingUnavailable, served_embedding_model
from brain.knowledge.embed_queue import EMBED_TASK, REEMBED_TASK
from brain.knowledge.embedding import EmbeddingError, MixedEmbeddingError
from brain.knowledge.reembed import (
    Page,
    Window,
    jobs_for,
    page_of,
    run_reembed_page,
    served_here,
    stale_chunks,
    start_rebuild,
    windows_of,
)
from brain.ops.queue import Job
from brain.session import make_app_engine, make_session_factory
from tests.fixtures.retirable import has_pgvector
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_embedding_path_db import (
    A_REVISION,
    FINANCE_OWNER,
    FINANCE_TEXT,
    WEB_OWNER,
    WEB_TEXT,
    OneAxis,
    _database,
    an_item,
    ingest,
    live_chunks,
    people,
    through,
    worked,
)

#: A PostgreSQL dialect to render a statement against, taken from an engine because
#: `postgresql.dialect()` is untyped; nothing here connects it.
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

NEW_REVISION = "v2.0.0"
OLD = served_embedding_model(revision=A_REVISION).identity
NEW = served_embedding_model(revision=NEW_REVISION).identity


def rows(*chunks: tuple[str, str, str, int]) -> list[dict[str, Any]]:
    return [
        {"chunk_id": cid, "document_id": doc, "owner_id": owner, "ordinal": n}
        for cid, doc, owner, n in chunks
    ]


# ------------------------------------------------------------------ the statement and the grouping
def test_the_page_selects_retrievable_chunks_not_on_the_model_after_the_key_in_key_order() -> None:
    """The statement as PostgreSQL would be sent it. Delete this and the page can drop the
    distinct-from (a chunk with no recorded model is then never rebuilt), the deleted-at filter
    (retired text is embedded), the state filter (archived text is embedded), the key (the page
    never advances) or the order (the position is not the last id)."""
    text = str(
        stale_chunks(NEW, after_chunk_id="kb.a.0003", size=200).compile(
            dialect=DIALECT, compile_kwargs={"literal_binds": True}
        )
    )
    assert "IS DISTINCT FROM" in text
    assert "deleted_at IS NULL" in text
    assert "state IN ('draft', 'published')" in text
    assert "chunk_id > 'kb.a.0003'" in text
    assert "ORDER BY know.chunk.chunk_id" in text
    assert "LIMIT 200" in text
    assert NEW in text


def test_a_documents_stale_chunks_are_one_window_spanning_their_ordinals() -> None:
    """Three chunks of one document out of key order, and one of another. Delete this and a
    window is one per chunk, which is a queue row per passage, or its span is the first found
    rather than the lowest and highest, which leaves a chunk out of every window."""
    found = rows(
        ("kb.a.0010", "kb.a", "u1", 10),
        ("kb.a.0002", "kb.a", "u1", 2),
        ("kb.b.0000", "kb.b", "u2", 0),
        ("kb.a.0007", "kb.a", "u1", 7),
    )
    assert windows_of(found) == (
        Window("kb.a", "u1", 2, 10, 3),
        Window("kb.b", "u2", 0, 0, 1),
    )


def test_a_page_shorter_than_asked_is_the_last_and_names_the_last_key() -> None:
    """Exhausted exactly when the selection came back short. Delete this and the rebuild either
    stops one page early, leaving the last chunks on the old model, or never stops."""
    full = page_of(rows(("a.0", "a", "u", 0), ("a.1", "a", "u", 1)), size=2)
    short = page_of(rows(("a.0", "a", "u", 0)), size=2)
    empty = page_of([], size=2)
    assert (full.exhausted, full.last_chunk_id, full.found) == (False, "a.1", 2)
    assert (short.exhausted, short.last_chunk_id) == (True, "a.0")
    assert (empty.exhausted, empty.last_chunk_id, empty.windows) == (True, "", ())
    with pytest.raises(EmbeddingError):
        page_of([], size=0)


def test_a_window_is_queued_as_the_ingest_would_have_queued_it() -> None:
    """The job carries the document, the ordinal window, the model and the owner it runs for.
    Delete this and a rebuild queues a different shape from an upload, and the worker's one
    embedding task reads it differently."""
    model = served_embedding_model(revision=NEW_REVISION)
    (job,) = jobs_for(
        Page(windows=(Window("kb.a", "u1", 2, 10, 3),), found=3, last_chunk_id="x", exhausted=True),
        model,
    )
    assert job.task == EMBED_TASK
    assert dict(job.args) == {
        "document_id": "kb.a",
        "first_ordinal": 2,
        "last_ordinal": 10,
        "model": NEW,
        "owner_id": "u1",
    }


def test_a_rebuild_is_refused_for_a_model_this_worker_does_not_serve_or_no_revision() -> None:
    """Both refusals before anything is read. Delete this and a page queued for one model is run
    by a worker serving another, which leaves the corpus holding both, or an install with no
    declared revision is told its rebuild succeeded."""
    assert served_here(NEW_REVISION, NEW).identity == NEW
    with pytest.raises(MixedEmbeddingError):
        served_here(NEW_REVISION, OLD)
    with pytest.raises(EmbeddingUnavailable):
        served_here(None, NEW)


# ------------------------------------------------------------------ a page, over a stand-in read
def test_a_page_queues_its_windows_before_the_next_page_and_the_next_starts_after_the_last_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full page: the window jobs first, then the next page's job, after the last key found.
    Delete this and the next page is queued before the windows (a crash between loses them) or
    starts at the beginning (the rebuild never ends)."""
    page = page_of(rows(("a.0", "a", "u", 0), ("a.1", "a", "u", 1)), size=2)
    queued: list[Job] = []

    async def read(*_: Any, **__: Any) -> Page:
        return page

    async def enqueue(job: Job) -> None:
        queued.append(job)

    monkeypatch.setattr(reembed, "read_page", read)
    said = asyncio.run(
        run_reembed_page(
            sessions(),
            enqueue,
            after_chunk_id="",
            size=2,
            model=NEW,
            revision=NEW_REVISION,
        )
    )
    assert [job.task for job in queued] == [EMBED_TASK, REEMBED_TASK]
    assert dict(queued[1].args) == {"after_chunk_id": "a.1", "size": 2, "model": NEW}
    assert "next page after a.1" in said


def test_the_last_page_queues_its_windows_and_no_next_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A short page ends it. Delete this and a finished rebuild queues a page for ever, each
    finding nothing, which is the rebuild that never ends."""
    page = page_of(rows(("a.0", "a", "u", 0)), size=2)
    queued: list[Job] = []

    async def read(*_: Any, **__: Any) -> Page:
        return page

    async def enqueue(job: Job) -> None:
        queued.append(job)

    monkeypatch.setattr(reembed, "read_page", read)
    asyncio.run(
        run_reembed_page(
            sessions(), enqueue, after_chunk_id="", size=2, model=NEW, revision=NEW_REVISION
        )
    )
    assert [job.task for job in queued] == [EMBED_TASK]


def sessions() -> Any:
    """Never opened: the stand-in read does not use them."""
    return None


# ------------------------------------------------------------------ the whole path, on PostgreSQL
def login[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    """Run work on sessions over this database as its own login, the way the worker's page does."""

    async def go() -> T:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


def stale(url: str, identity: str) -> int:
    row = sql(
        url,
        "SELECT count(*) FROM know.chunk WHERE deleted_at IS NULL "
        "AND embedding_model IS DISTINCT FROM %s",
        identity,
    )
    return int(row[0][0])


def page_run(url: str, job: Job, queued: list[Job]) -> str:
    """One rebuild page, on the worker's own login, queueing what it finds."""
    args = job.args

    async def page(sessions: async_sessionmaker[AsyncSession]) -> str:
        async def enqueue(next_job: Job) -> None:
            queued.append(next_job)

        return await run_reembed_page(
            sessions,
            enqueue,
            after_chunk_id=str(args["after_chunk_id"]),
            size=int(args["size"]),
            model=str(args["model"]),
            revision=NEW_REVISION,
        )

    return login(url, page)


def window_run(url: str, job: Job, service: OneAxis) -> str:
    """One window, embedded as its owner on the application role, as the worker's task does."""
    args = job.args

    async def window(sessions: async_sessionmaker[AsyncSession]) -> str:
        return await run_embed_job(
            document_id=str(args["document_id"]),
            first_ordinal=int(args["first_ordinal"]),
            last_ordinal=int(args["last_ordinal"]),
            model=str(args["model"]),
            owner_id=str(args["owner_id"]),
            sessions=sessions,
            service=service,
            revision=NEW_REVISION,
            now=datetime.now(tz=UTC),
        )

    return through(url, window)


def drained(url: str, queued: list[Job], service: OneAxis) -> list[str]:
    """What the worker does with a queue: each page and each window, in the order queued."""
    said: list[str] = []
    while queued:
        job = queued.pop(0)
        said.append(
            page_run(url, job, queued)
            if job.task == REEMBED_TASK
            else window_run(url, job, service)
        )
    return said


@pytest.mark.needs_db
def test_a_model_change_moves_every_chunk_of_every_department_and_changes_no_permission() -> None:
    """**The leaf, end to end.** Two departments' documents are embedded on one model, the install
    then serves another, and the rebuild (the page on the worker's login, a page of one chunk so it
    is several, each window on the application role as its owner) leaves nothing stale and every
    chunk's owner, department, visibility and state as they were. A second run says there is
    nothing to rebuild.

    Delete this and the page, the windows and the worker's embedding task are only ever run in
    pieces against stand-ins, so a rebuild can skip a department's documents (the policy hides
    them from the login the page ran as) or drop a permission while every unit test passes."""
    with _database("brain_reembed_whole") as url:
        if not has_pgvector(url):
            pytest.skip("this server has no pgvector, so the vector column cannot exist")
        people(url)
        first: list[Job] = []
        ingest(url, an_item("kb.release", WEB_TEXT, owner=WEB_OWNER, department="web"), first)
        ingest(
            url,
            an_item("kb.invoices", FINANCE_TEXT, owner=FINANCE_OWNER, department="finance"),
            first,
        )
        service = OneAxis()
        for job in first:
            worked(url, job, service)
        assert stale(url, OLD) == 0
        before = {doc: live_chunks(url, doc) for doc in ("kb.release", "kb.invoices")}
        owners_before = sql(
            url,
            "SELECT chunk_id, owner_id, visibility, department, state FROM know.chunk ORDER BY 1",
        )

        assert stale(url, NEW) == 2
        queued: list[Job] = []

        async def enqueue(job: Job) -> None:
            queued.append(job)

        code, said = login(url, lambda s: start_rebuild(s, enqueue, revision=NEW_REVISION, size=1))
        assert code == 0 and "2 stale chunk(s)" in said
        assert [job.task for job in queued] == [REEMBED_TASK]

        done = drained(url, queued, OneAxis())

        after_stale = stale(url, NEW)
        owners_after = sql(
            url,
            "SELECT chunk_id, owner_id, visibility, department, state FROM know.chunk ORDER BY 1",
        )
        models = {row[0] for row in sql(url, "SELECT DISTINCT embedding_model FROM know.chunk")}
        after = {doc: live_chunks(url, doc) for doc in ("kb.release", "kb.invoices")}
        again = login(url, lambda s: start_rebuild(s, enqueue, revision=NEW_REVISION, size=1))

    assert after_stale == 0
    assert models == {NEW}
    assert owners_after == owners_before
    assert after == before
    assert len(done) >= 4
    assert again[0] == 0 and again[1].startswith("nothing to rebuild")
    assert queued == []
