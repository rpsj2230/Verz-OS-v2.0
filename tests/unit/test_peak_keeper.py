"""What a worker's clients were told of the server's memory, kept until a job can write it down.

The hand-off is a thread to an event loop, so what is held is shown surviving the thread, bounded,
written one savepoint each and never costing a job its work. The session is a stand-in that keeps
what was written to it, because what the real one does against PostgreSQL is the install check's
and `test_model_server_peaks.py`'s.

Task ids: M7.3.3, M7.7.11
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.knowledge.embed_queue import EMBED_TASK
from brain.ops import model_server_store
from brain.ops.model_server import Part
from brain.ops.model_server_peaks import PeakReport
from brain.ops.model_server_store import PeakKeeper
from brain.tables.model_server import RING_SLOTS

NOW = datetime(2999, 1, 1, tzinfo=UTC)


def report(anon: int, part: Part = Part.LAYOUT) -> PeakReport:
    return PeakReport(
        part=part,
        model="m@r:1",
        items=1,
        request_bytes=10,
        duration_ms=5,
        anon_peak_mib=anon,
        cache_peak_mib=0,
        cgroup_limit_mib=1088,
    )


class _Transaction:
    def __init__(self, log: list[str], label: str) -> None:
        self.log = log
        self.label = label

    async def __aenter__(self) -> _Transaction:
        self.log.append(f"begin {self.label}")
        return self

    async def __aexit__(self, *error: object) -> None:
        self.log.append(f"end {self.label}")


class _Session:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *error: object) -> None:
        return None

    def begin(self) -> _Transaction:
        return _Transaction(self.log, "transaction")

    def begin_nested(self) -> _Transaction:
        return _Transaction(self.log, "savepoint")


class _Sessions:
    def __init__(self) -> None:
        self.log: list[str] = []

    def __call__(self) -> _Session:
        return _Session(self.log)


def recording(monkeypatch: pytest.MonkeyPatch, refuse: set[int] | None = None) -> list[int]:
    written: list[int] = []

    async def record(session: Any, one: PeakReport, *, at: datetime) -> int:
        if refuse and one.anon_peak_mib in refuse:
            msg = "the table refused a row"
            raise RuntimeError(msg)
        written.append(one.anon_peak_mib)
        return 1

    monkeypatch.setattr(model_server_store, "record_peak", record)
    return written


def test_what_a_thread_kept_is_written_by_the_job_in_the_order_it_was_heard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reports kept from other threads are all written once, each in a savepoint of its own, and
    nothing is written twice.

    Delete this and a statistic heard in a thread is lost, or written at the next job as well."""
    written = recording(monkeypatch)
    keeper = PeakKeeper()
    sessions = _Sessions()

    threads = [threading.Thread(target=keeper.keep, args=(report(one),)) for one in (1, 2, 3)]
    for thread in threads:
        thread.start()
        thread.join()
    first = asyncio.run(keeper.flush(sessions, at=NOW))  # type: ignore[arg-type]
    second = asyncio.run(keeper.flush(sessions, at=NOW))  # type: ignore[arg-type]

    assert (first, second) == (3, 0)
    assert written == [1, 2, 3]
    assert sessions.log.count("begin savepoint") == 3


def test_a_row_the_table_refuses_costs_that_row_and_not_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refused report is dropped and the others are written; the job never sees the failure.

    Delete this and a table that would not take a row fails the embedding of fifty passages."""
    written = recording(monkeypatch, refuse={2})
    keeper = PeakKeeper()
    for one in (1, 2, 3):
        keeper.keep(report(one))

    kept = asyncio.run(keeper.flush(_Sessions(), at=NOW))  # type: ignore[arg-type]

    assert kept == 2 and written == [1, 3]


def test_a_keeper_holds_no_more_than_a_ring_for_every_part_and_loses_the_oldest() -> None:
    """Past the bound the oldest are dropped, so a worker whose database is down for an hour does
    not grow without limit.

    Delete this and it does."""
    keeper = PeakKeeper()
    most = PeakKeeper.LARGEST_KEPT
    assert most == RING_SLOTS * len(Part)  # one ring's worth for every part, from the table's own

    for one in range(most + 7):
        keeper.keep(report(one))
    held = keeper.drain()

    assert len(held) == most
    assert [one.anon_peak_mib for one in held][:2] == [7, 8]
    assert held[-1].anon_peak_mib == most + 6
    assert keeper.drain() == ()


def test_the_embedding_task_writes_the_peak_its_client_heard_even_when_the_job_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker hands its clients one keeper and flushes it in a `finally`: a batch the server
    reported on and the job then failed over is still written, and the same keeper is handed to the
    ingest task.

    Delete this and the memory the server measured is lost exactly when a job runs it out of
    memory, which is the figure the limit is tuned from."""
    from brain.ops import worker

    written = recording(monkeypatch)
    registered: dict[str, Any] = {}
    handed: dict[str, Any] = {}
    disposed: list[bool] = []

    def capture(app: Any, name: str, function: Any, *, traffic_class: Any) -> None:
        registered[name] = function

    class Engine:
        async def dispose(self) -> None:
            disposed.append(True)

    def make_client(*, env: Any = None, observer: Any = None, **_rest: Any) -> Any:
        handed["observer"] = observer
        return object()

    async def failing_job(**_kwargs: Any) -> str:
        handed["observer"](report(900))
        msg = "the server was killed"
        raise RuntimeError(msg)

    monkeypatch.setattr(worker, "register_task", capture)
    monkeypatch.setattr(
        worker, "register_ingest_tasks", lambda app, **kwargs: handed.update(kwargs)
    )
    monkeypatch.setattr(worker, "make_client", make_client)
    monkeypatch.setattr(worker, "make_app_engine", lambda url: Engine())
    monkeypatch.setattr(worker, "make_application_sessions", lambda engine: _Sessions())
    monkeypatch.setattr(worker, "run_embed_job", failing_job)
    monkeypatch.setattr(worker, "embedding_revision", lambda env: "abc123def456")

    worker.register_tasks(object(), database_url="postgresql://x/y", env={})
    with pytest.raises(RuntimeError, match="killed"):
        asyncio.run(registered[EMBED_TASK]("d", 1, 2, "m", "u"))

    assert written == [900] and disposed == [True]
    assert isinstance(handed["peaks"], PeakKeeper)
    assert handed["observer"].__self__ is handed["peaks"]
