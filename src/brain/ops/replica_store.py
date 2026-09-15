"""The replica side of console reads: measuring how far behind it is, and reading from it.

`brain.console.read_replica` decides which database answers a console read and what the page
says. This is the half that holds sessions, and it decides neither: it asks the replica one
question, hands the answer to `route_read`, and runs the caller's read wherever it was sent.

**One lag query, three facts, read together.** `pg_is_in_recovery()`, the age of the last
replayed transaction, and whether a WAL receiver is running with nothing left to replay. The
policy module says why each is needed and what a null means; they are one statement so the
three describe the same instant.

**A measurement is reused for `MEASURE_EVERY` and bounded by `MEASURE_TIMEOUT`.** A lag query
per console request doubles the replica's work for no information, and an unreachable replica
must not add a connect timeout to every page. So one reading serves every read inside the
window, an unreachable reading is cached exactly like a good one, and the policy adds the
reading's age to the lag it states, which is what makes caching it safe.

**A replica read that fails is re-run on the primary, and the failure is recorded as a
reading.** A replica can be measured healthy and then refuse the query that follows: it
restarted, or a hot standby cancelled the statement for conflicting with recovery, which is
routine on a busy standby. Answering that with a 500 would make the replica a dependency of
the console, which `PAST_THE_THRESHOLD_THE_PRIMARY_ANSWERS_RATHER_THAN_A_BANNER` refuses. A
failure that is not about the replica fails again on the primary and reaches the caller from
there, so nothing is swallowed.

**Every display read runs `SET TRANSACTION READ ONLY` first, on either database.** A replica
refuses writes and a primary does not, so a display read that happened to write would work on
every development machine, where there is no replica, and fail only on the install that added
one. Making both refuse means the mistake is found where it is written. It is transaction
scoped, which is what a transaction pooler admits.

**No primary means no console reads at all, replica or not.** `console_reads_for` returns
None, and a route reports its process fault exactly as it did before. A replica with nothing to
fall back to would turn every lag into a stale page or an error, which are the two outcomes
the policy exists to prevent.

What is not here: a replica. M36.1.2.1 is the streaming replica's configuration and it is
infrastructure this repository has not built. `measure_lag` is run in tests against a real
PostgreSQL that is a primary, which proves the query parses and that a primary reads as not in
recovery. What a real standby answers is argued from PostgreSQL's documentation and has not
been observed here.

Task ids: M36.1.2.2, M36.1.2.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from brain.console.read_replica import (
    MEASURE_EVERY,
    MEASURE_TIMEOUT,
    LagReading,
    Measurement,
    Purpose,
    StalenessBanner,
    Target,
    Unreachable,
    route_read,
)
from brain.session import make_app_engine, make_application_sessions

log = structlog.get_logger()

#: The three facts `LagReading` holds, in one statement. See `brain.console.read_replica`.
LAG_QUERY = text(
    "SELECT pg_is_in_recovery() AS in_recovery, "
    "now() - pg_last_xact_replay_timestamp() AS replay_age, "
    "coalesce(pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn(), false) "
    "AND EXISTS (SELECT 1 FROM pg_stat_wal_receiver) AS caught_up"
)

#: What a failed replica is recognised by. A driver error, a socket, or a measurement timeout.
REPLICA_FAILURES: tuple[type[BaseException], ...] = (SQLAlchemyError, OSError, TimeoutError)


async def measure_lag(session: AsyncSession) -> LagReading:
    """Ask this server how far behind the primary it is."""
    row = (await session.execute(LAG_QUERY)).one()
    return LagReading(
        in_recovery=bool(row.in_recovery),
        replay_age=row.replay_age,
        caught_up=bool(row.caught_up),
    )


@dataclass(frozen=True)
class Served[T]:
    """What a console read returned, and the banner its page must carry, if any."""

    value: T
    banner: StalenessBanner | None


type Measure = Callable[[AsyncSession], Awaitable[LagReading]]
type Work[T] = Callable[[AsyncSession], Awaitable[T]]


class ConsoleReads:
    """The primary's sessions, a replica's if one is configured, and the last lag reading."""

    def __init__(
        self,
        primary: async_sessionmaker[AsyncSession],
        replica: async_sessionmaker[AsyncSession] | None = None,
        *,
        measure: Measure = measure_lag,
        engine: AsyncEngine | None = None,
    ) -> None:
        self.primary = primary
        self._replica = replica
        self._measure = measure
        self._engine = engine
        self._last: Measurement | None = None

    async def measurement(self, now: datetime) -> Measurement | None:
        """The current reading, re-measured when the last is older than `MEASURE_EVERY`."""
        if self._replica is None:
            return None
        last = self._last
        if last is not None and last.at <= now and now - last.at < MEASURE_EVERY:
            return last
        reading: LagReading | Unreachable
        try:
            async with self._replica() as session:
                reading = await asyncio.wait_for(
                    self._measure(session), MEASURE_TIMEOUT.total_seconds()
                )
        except REPLICA_FAILURES as exc:
            log.warning("replica lag not measured", error=type(exc).__name__)
            reading = Unreachable()
        self._last = Measurement(reading=reading, at=now)
        return self._last

    async def read[T](
        self, work: Work[T], *, now: datetime, purpose: Purpose = Purpose.DISPLAY
    ) -> Served[T]:
        """Run `work` on whichever database `route_read` chooses, read only."""
        measured = None if purpose is Purpose.DECISION else await self.measurement(now)
        route = route_read(purpose, measured, now=now)
        if route.target is Target.REPLICA and self._replica is not None:
            try:
                return Served(value=await _read_only(self._replica, work), banner=route.banner)
            except REPLICA_FAILURES as exc:
                log.warning(
                    "replica read failed, answered by the primary", error=type(exc).__name__
                )
                self._last = Measurement(reading=Unreachable(), at=now)
        else:
            log.debug("console read answered by the primary", why=route.why.value)
        return Served(value=await _read_only(self.primary, work), banner=None)

    async def close(self) -> None:
        """Dispose of the replica's engine, if this object made one."""
        if self._engine is not None:
            await self._engine.dispose()


async def _read_only[T](factory: async_sessionmaker[AsyncSession], work: Work[T]) -> T:
    async with factory() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        return await work(session)


def console_reads_for(
    primary: async_sessionmaker[AsyncSession] | None, replica_url: str
) -> ConsoleReads | None:
    """What `brain.app` attaches for console reads. None when there is no primary."""
    if primary is None:
        return None
    url = replica_url.strip()
    if not url:
        return ConsoleReads(primary)
    engine = make_app_engine(url)
    # As the application role, as the primary's sessions are. A replica that read as the login
    # would show a console page past the policies the same page is held to on the primary. See
    # `brain.session.THE_APPLICATION_ANSWERS_AS_THE_ROLE_ROW_SECURITY_BINDS`.
    return ConsoleReads(primary, make_application_sessions(engine), engine=engine)
