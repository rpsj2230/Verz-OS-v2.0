"""Where what runs cost is written, and where the materialised report over it is rebuilt and read.

`brain.ops.spend` decides what an accounting row is and `brain.console.spend_report_view` decides
what a reader may see of the report over them. This is the half that talks to PostgreSQL, and it
decides neither: a row written is an `Actual` somebody else built through its own checks, and a
report read comes back as rows and a timestamp for the console to narrow.

**The refresh timestamp is read before the view, and the order is the point.** Under READ
COMMITTED each statement sees what had committed when it began, so a refresh can land between two
reads. Read the timestamp first and the worst case is figures newer than the instant they are
labelled with, so the report overstates its own age. Read the view first and the worst case is
figures older than their label, which is a report claiming to be fresher than it is. Only the
first error is safe to make.

**A view nobody has refreshed is not selected from.** PostgreSQL refuses to read an unpopulated
materialised view, and the absence of a refresh record is how that state is known without asking
it to fail. `read_spend_daily` returns no rows and no instant, which the console turns into a
report that has not been built rather than one that says nothing was spent.

**The refresh is one function call, and it runs as the view's owner.** `0036` explains why: only
an owner may refresh a materialised view, and the application role must not become one.

**The write is the domain row and nothing more.** No question, no answer, no record id, because
`Actual` has none. See `brain.tables.spend`.

**The question-shape report is two reads and one call, and the call is the console's (M21.3.4).**
`question_shape_report` reads every recorded cost, reads the trace ledger's shapes for their
trace ids through `brain.ops.telemetry_store.shapes_for`, and hands both to
`brain.console.spend_view.shape_report`, which filters by the reader's grant before it groups.
The join is in Python rather than SQL for the reason the unmaterialised report already is: the
filter is `may_read_spend`, which a predicate would be a second implementation of.

What is not here: a caller of `record`. Nothing in this repository completes a run and records
its cost, so it is written and tested against a real server and called by nothing yet, which is
stated rather than left to be discovered from an empty table. The refresh does have one: the
worker's schedule starts `refresh_spend_daily_now` through `brain.ops.schedule_runner`. And the
answer lane, the one path that finishes a request, spends nothing, so no recorded cost has a
trace the ledger holds until a lane that calls a model records one.

Task ids: M36.1.3.1, M36.1.3.2, M21.3.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from brain.console.spend_report_view import SpendDay
from brain.console.spend_view import ShapeReport, shape_report
from brain.core.entitlement import EntitlementSet
from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.gate.context import TrafficClass
from brain.ops.spend import Actual, Dimension
from brain.ops.telemetry_store import shapes_for
from brain.session import make_app_engine, make_session_factory
from brain.tables.spend import ReportRefreshRow, SpendActualRow

#: The view `0035` builds, as `ops.report_refresh` names it.
SPEND_DAILY = "ops.spend_daily"


def actual_from(stored: SpendActualRow) -> Actual:
    """The accounting row a stored cost holds, through `Actual`'s own checks.

    A row with no trace id reaches `Actual` as an empty one and is refused there, loudly, rather
    than read back under a trace nobody recorded. The column is nullable only so the previous
    release's insert survives a deploy (see `0043`), and nothing that writes through `record`
    can produce such a row.
    """
    return Actual(
        principal_id=stored.principal_id,
        principal_kind=PrincipalKind(stored.principal_kind),
        traffic=TrafficClass(stored.traffic),
        department=stored.department,
        agent_id=stored.agent_id,
        model=stored.model,
        lane=Lane(stored.lane),
        cost_minor=stored.cost_minor,
        at=stored.at,
        trace_id=stored.trace_id or "",
    )


async def record(session: AsyncSession, actual: Actual) -> None:
    """Append what one completed run cost. Does not commit; the run's own transaction does."""
    session.add(
        SpendActualRow(
            principal_id=actual.principal_id,
            principal_kind=actual.principal_kind.value,
            traffic=actual.traffic.value,
            department=actual.department,
            agent_id=actual.agent_id,
            model=actual.model,
            lane=actual.lane.value,
            cost_minor=actual.cost_minor,
            at=actual.at,
            trace_id=actual.trace_id,
        )
    )
    await session.flush()


async def recorded(session: AsyncSession) -> tuple[Actual, ...]:
    """Every recorded cost, oldest first. What the unmaterialised report is built from."""
    found = await session.execute(select(SpendActualRow).order_by(SpendActualRow.at))
    return tuple(actual_from(one) for one in found.scalars().all())


async def question_shape_report(
    session: AsyncSession,
    entitlement: EntitlementSet,
    *,
    now: datetime,
    include_machine: bool = False,
) -> ShapeReport:
    """What each question shape cost, at this reader's reach. See the module docstring."""
    actuals = await recorded(session)
    shapes = await shapes_for(session, {one.trace_id for one in actuals})
    return shape_report(actuals, shapes, entitlement, now=now, include_machine=include_machine)


async def refresh_spend_daily(session: AsyncSession) -> datetime:
    """Rebuild the materialised report and record when. Returns the instant it is as of.

    Does not commit. The rebuild and its timestamp land together when the caller commits, and a
    rollback discards both, so the record can never describe a rebuild that did not happen.
    """
    answer = await session.execute(text("SELECT ops.refresh_spend_daily()"))
    as_of: datetime = answer.scalar_one()
    return as_of


def refresh_spend_daily_now(
    database_url: str, *, loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None
) -> datetime:
    """`refresh_spend_daily`, from a thread with no event loop of its own, committed.

    The worker's schedule runs a control off its event loop, because a runner that blocks on
    the loop stops the queue's own workers for as long as it runs, and a runner there is a
    plain function. So this is the one synchronous way into the refresh, and it is a wrapper
    rather than a second refresh: it opens the application's engine, calls the same coroutine
    in one transaction, commits, and disposes of the engine before it returns.

    `brain.session.make_app_engine` because the URL is the application's, behind a transaction
    pooler, and the engine that sets `prepare_threshold=None` for that is the one already
    written. `loop_factory` is the caller's, because which event loop psycopg accepts is a
    property of the platform and `brain.ops.worker` is where that decision already lives.
    """

    async def once() -> datetime:
        engine = make_app_engine(database_url)
        try:
            async with make_session_factory(engine)() as session, session.begin():
                return await refresh_spend_daily(session)
        finally:
            await engine.dispose()

    return asyncio.run(once(), loop_factory=loop_factory)


async def read_spend_daily(session: AsyncSession) -> tuple[datetime | None, tuple[SpendDay, ...]]:
    """When the view was last rebuilt, then every row it holds. See the module docstring."""
    refreshed = await session.execute(
        select(ReportRefreshRow.refreshed_at).where(ReportRefreshRow.view_name == SPEND_DAILY)
    )
    at = refreshed.scalar_one_or_none()
    if at is None:
        return None, ()
    found = await session.execute(
        text(
            "SELECT day, department, principal_kind, traffic, dimension, key, cost_minor "
            "FROM ops.spend_daily"
        )
    )
    return at, tuple(
        SpendDay(
            day=row.day,
            department=row.department,
            principal_kind=PrincipalKind(row.principal_kind),
            traffic=TrafficClass(row.traffic),
            dimension=Dimension(row.dimension),
            key=row.key,
            cost_minor=row.cost_minor,
        )
        for row in found
    )


async def spend_actual_read_policies(session: AsyncSession) -> tuple[str | None, ...]:
    """The expression of every policy letting `brain_app` read `ops.spend_actual`.

    What `brain.console.spend_report_view.view_gaps` checks. Read from `pg_policies` rather than
    from the migration's text, because the property that matters is the one the server enforces.
    """
    found = await session.execute(
        text(
            "SELECT qual FROM pg_catalog.pg_policies "
            "WHERE schemaname = 'ops' AND tablename = 'spend_actual' "
            "AND cmd IN ('SELECT', 'ALL') AND 'brain_app' = ANY(roles) "
            "ORDER BY policyname"
        )
    )
    return tuple(row.qual for row in found)
