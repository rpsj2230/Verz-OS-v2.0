"""Console reads through `ConsoleReads`: which session answers, how the reading is cached, and
what a failing replica does to a page.

Two halves. Without a server: sessions are stubs that record which database they stand for and
what they were asked, and the measurement is a function the test hands in, so every band of
the policy can be driven through the store. With one: `measure_lag` is run against a real
PostgreSQL, which is a primary, so what is proven there is that the query parses and executes
and that a primary reads as not in recovery. No test here has seen a real standby; see the
store's docstring.

Task ids: M36.1.2.2, M36.1.2.3
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from brain.console.read_replica import (
    BANNER_AFTER,
    FALL_BACK_AFTER,
    MEASURE_EVERY,
    LagReading,
    Purpose,
    Unreachable,
)
from brain.ops.replica_store import ConsoleReads, console_reads_for, measure_lag
from tests.fixtures.scratch_postgres import database_url, engine, run

NOW = datetime(2999, 1, 1, 12, tzinfo=UTC)
SECOND = timedelta(seconds=1)


class Recorder:
    """Which database each statement went to, in order."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, str]] = []
        self.fail_reads_on: set[str] = set()


RECORDER = Recorder()


class _Stub(AsyncSession):
    NAME = ""

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        RECORDER.statements.append((self.NAME, str(statement)))
        return None

    async def close(self) -> None:
        return None


class PrimarySession(_Stub):
    NAME = "primary"


class ReplicaSession(_Stub):
    NAME = "replica"


@pytest.fixture(autouse=True)
def recorder() -> Iterator[Recorder]:
    global RECORDER
    RECORDER = Recorder()
    yield RECORDER


def primary() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(class_=PrimarySession)


def replica() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(class_=ReplicaSession)


class Lag:
    """A measurement function answering a chosen reading, counting how often it was asked."""

    def __init__(self, reading: LagReading | Exception) -> None:
        self.reading = reading
        self.asked = 0

    async def __call__(self, session: AsyncSession) -> LagReading:
        self.asked += 1
        if isinstance(self.reading, Exception):
            raise self.reading
        return self.reading


def lagging(seconds: float) -> Lag:
    return Lag(LagReading(in_recovery=True, replay_age=timedelta(seconds=seconds), caught_up=False))


async def which(session: AsyncSession) -> str:
    """The work: say which database answered it."""
    name = type(session).NAME  # type: ignore[attr-defined]
    if name in RECORDER.fail_reads_on:
        raise OperationalError("SELECT 1", {}, Exception("conflict with recovery"))
    return str(name)


# ------------------------------------------------------------------ which answers
def test_a_display_read_on_a_current_replica_is_answered_by_the_replica() -> None:
    """The positive case: the store runs the work where the policy sent it.

    Delete this and `read` can always use the primary, and M36.1.2.2 is a policy nobody calls."""
    reads = ConsoleReads(primary(), replica(), measure=lagging(1))

    served = run(lambda: reads.read(which, now=NOW))

    assert (served.value, served.banner) == ("replica", None)


def test_a_page_from_a_lagging_replica_carries_the_banner_the_policy_made() -> None:
    """The banner reaches the caller, from the replica's own read.

    Delete this and `Served` can be built with `banner=None` on every replica read, which is the
    stale page served silently."""
    reads = ConsoleReads(primary(), replica(), measure=lagging(60))

    served = run(lambda: reads.read(which, now=NOW))

    assert served.value == "replica"
    assert served.banner is not None
    assert served.banner.behind_seconds == 60


def test_with_no_replica_every_read_is_the_primary_and_nothing_is_measured() -> None:
    """Unchanged behaviour when the setting is empty.

    Delete this and an install with no replica can be asked for a measurement on every read."""
    lag = lagging(0)
    reads = ConsoleReads(primary(), None, measure=lag)

    served = run(lambda: reads.read(which, now=NOW))

    assert (served.value, served.banner, lag.asked) == ("primary", None, 0)


def test_a_decision_read_is_answered_by_the_primary_and_the_replica_is_not_asked() -> None:
    """Not even measured: a decision does not depend on the replica in any way.

    Delete this and a decision read waits on a replica's measurement timeout before reading the
    primary it was always going to read."""
    lag = lagging(0)
    reads = ConsoleReads(primary(), replica(), measure=lag)

    served = run(lambda: reads.read(which, now=NOW, purpose=Purpose.DECISION))

    assert (served.value, lag.asked) == ("primary", 0)


def test_a_replica_too_far_behind_sends_the_page_to_the_primary_with_no_banner() -> None:
    """The fall-back reaches the caller as a primary read with nothing stale on it.

    Delete this and the store can run the work on the replica whatever the route's target said."""
    reads = ConsoleReads(
        primary(), replica(), measure=lagging((FALL_BACK_AFTER + SECOND).total_seconds())
    )

    served = run(lambda: reads.read(which, now=NOW))

    assert (served.value, served.banner) == ("primary", None)


def test_a_replica_that_refuses_the_measurement_is_read_as_unreachable() -> None:
    """A driver error while measuring is a reading, not an exception on the page.

    Delete this and a refused connection to the replica becomes a 500 on every console page."""
    reads = ConsoleReads(primary(), replica(), measure=Lag(OSError("refused")))

    served = run(lambda: reads.read(which, now=NOW))
    measured = run(lambda: reads.measurement(NOW))

    assert served.value == "primary"
    assert measured is not None
    assert isinstance(measured.reading, Unreachable)


def test_a_replica_read_that_fails_is_answered_by_the_primary_and_remembered() -> None:
    """Measured healthy, then refused the query: the page is still answered, current, bannerless.

    And the next read inside the window does not try the replica again. Delete this and a hot
    standby cancelling a statement for a recovery conflict, which is routine, is a 500."""
    RECORDER.fail_reads_on.add("replica")
    lag = lagging(60)
    reads = ConsoleReads(primary(), replica(), measure=lag)

    first = run(lambda: reads.read(which, now=NOW))
    second = run(lambda: reads.read(which, now=NOW + SECOND))

    assert (first.value, first.banner) == ("primary", None)
    assert second.value == "primary"
    assert lag.asked == 1
    # The second read went straight to the primary: the failure was remembered as a reading, so
    # the replica was not tried again inside the window. Counted by statements the replica saw.
    assert [name for name, _ in RECORDER.statements].count("replica") == 1


def test_a_failure_the_primary_shares_reaches_the_caller() -> None:
    """Nothing is swallowed: a read that fails on both is an error.

    Delete this and the fall-back can catch the primary's error too and return nothing."""
    RECORDER.fail_reads_on.update({"replica", "primary"})
    reads = ConsoleReads(primary(), replica(), measure=lagging(1))

    with pytest.raises(OperationalError):
        run(lambda: reads.read(which, now=NOW))


def test_every_read_is_made_read_only_on_whichever_database_answers_it() -> None:
    """`SET TRANSACTION READ ONLY` first, on the replica and on the primary alike.

    Delete this and a display read that writes works on every machine without a replica and
    fails only on the install that added one."""
    run(lambda: ConsoleReads(primary(), replica(), measure=lagging(1)).read(which, now=NOW))
    run(lambda: ConsoleReads(primary()).read(which, now=NOW))

    assert RECORDER.statements == [
        ("replica", "SET TRANSACTION READ ONLY"),
        ("primary", "SET TRANSACTION READ ONLY"),
    ]


# ------------------------------------------------------------------ the cache
def test_a_reading_is_reused_inside_its_window_and_retaken_after_it() -> None:
    """One measurement per `MEASURE_EVERY`, at the boundary on both sides.

    Delete this and the lag query can run on every console request, or never again after the
    first."""
    lag = lagging(1)
    reads = ConsoleReads(primary(), replica(), measure=lag)

    run(lambda: reads.measurement(NOW))
    run(lambda: reads.measurement(NOW + MEASURE_EVERY - SECOND))
    assert lag.asked == 1

    run(lambda: reads.measurement(NOW + MEASURE_EVERY))
    assert lag.asked == 2


def test_a_reading_dated_after_the_instant_asked_about_is_retaken() -> None:
    """A clock that went backwards does not keep a reading alive.

    Delete this and a cached reading from the future answers every read until the clock catches
    up, with its negative age distrusted every time instead of measured again."""
    lag = lagging(1)
    reads = ConsoleReads(primary(), replica(), measure=lag)

    run(lambda: reads.measurement(NOW))
    run(lambda: reads.measurement(NOW - SECOND))

    assert lag.asked == 2


def test_the_cached_readings_age_is_what_raises_the_banner() -> None:
    """The store hands the policy the reading's own instant, not the instant of the read.

    Delete this and a cached reading can be re-stamped with each request's time, and its age is
    never added."""
    reads = ConsoleReads(
        primary(), replica(), measure=lagging((BANNER_AFTER - SECOND).total_seconds())
    )

    run(lambda: reads.measurement(NOW))
    served = run(lambda: reads.read(which, now=NOW + SECOND + SECOND / 2))

    assert served.banner is not None


# ------------------------------------------------------------------ the wiring
def test_a_console_reads_object_is_made_only_when_there_is_a_primary() -> None:
    """No primary, no console reads, whatever the replica setting says.

    Delete this and a process with only a replica configured reads everything from a copy with
    nothing to fall back to."""
    assert console_reads_for(None, "postgresql://replica.invalid/brain") is None


def test_an_empty_replica_setting_makes_a_console_reads_object_with_no_replica() -> None:
    """The positive sibling, and whitespace counts as empty.

    Delete this and an empty string can reach `make_app_engine`, which fails at startup."""
    found = console_reads_for(primary(), "  ")

    assert found is not None
    assert run(lambda: found.measurement(NOW)) is None


def test_a_replica_setting_makes_a_replica_the_store_measures() -> None:
    """A configured replica is measured, and an unreachable one reads as unreachable.

    An address nothing answers on, so what is proven is the wiring, not a replica. Delete this
    and the setting can be read and never turned into a session factory."""
    found = console_reads_for(primary(), "postgresql://nobody@127.0.0.1:1/none")

    assert found is not None
    try:
        measured = run(lambda: found.measurement(NOW))
    finally:
        run(found.close)

    assert measured is not None
    assert isinstance(measured.reading, Unreachable)


class CountedEngine:
    """Stands in for the replica's engine; counts disposals."""

    def __init__(self) -> None:
        self.disposed = 0

    async def dispose(self) -> None:
        self.disposed += 1


def test_closing_disposes_of_the_replica_engine_and_is_harmless_without_one() -> None:
    """Shutdown releases the replica's connections, and a process with no replica closes cleanly.

    Delete this and `close` can skip the engine, leaving the replica's connections open past
    shutdown, or can dispose of an engine that is not there and raise on every clean exit."""
    counted = CountedEngine()
    with_engine = ConsoleReads(primary(), replica(), engine=cast(AsyncEngine, counted))
    without = ConsoleReads(primary())

    run(with_engine.close)
    run(without.close)

    assert counted.disposed == 1


# ------------------------------------------------------------------ with a server
def test_a_primary_measured_as_a_replica_reads_as_not_in_recovery() -> None:
    """The lag query against a real PostgreSQL, which is a primary.

    Proves the statement parses and executes as the application would run it, and that the
    three facts come back in the shapes `LagReading` expects: not in recovery, no replay age,
    not caught up. Delete this and a typo in `LAG_QUERY` ships, and every console read falls
    back to the primary with a log line nobody reads."""
    if database_url() is None:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")
    url = database_url()
    assert url is not None

    async def measured() -> LagReading:
        found = engine(url)
        try:
            async with async_sessionmaker(found)() as session:
                return await measure_lag(session)
        finally:
            await found.dispose()

    reading = run(measured)

    assert reading == LagReading(in_recovery=False, replay_age=None, caught_up=False)
