"""The Spend report's other readings: what an answer costs, the dearest shapes and what stopped.

`brain.console.spend_view` wrote three functions for the Spend screen and nothing called them:
`cost_per_answer`, which says what one answer costs as a distribution and never as a mean alone
(M21.3.3), `shape_report` and `dearest`, which rank the question shapes by what they cost
(M21.3.4), and `budget_stops`, which lists every budget currently refusing questions so that a hard
stop is seen to be money and not permission (M21.3.6). `brain.report_routes.spend` already served
the breakdown by dimension. These three routes serve the rest, each over exactly the rows the
reader's usage grant admits.

**A distribution is withheld where its sample cannot support it.** The median, ninetieth and
ninety-ninth are each stated only over the rows each needs (`spend_view.minimum_rows`), and a
quantile the sample cannot hold is absent from the answer rather than present and approximate. A
window with no answer in it is `answers: 0` and no figure at all, because a mean over nothing is a
cost of nothing. See `A_PERCENTILE_NEEDS_ENOUGH_ROWS_TO_BE_A_RANK`.

**The stop board shows only the stops its reader may be told about.** A department's stop is
shown to the readers of that department's spend, a person's own allowance is always theirs, and a
stop on the company or on an agent, which sits in no department, is shown only to a reader whose
grant covers the whole company (`spend_view.may_read_unplaced`). Nothing counts what was left
out. See `A_STOPPED_DEPARTMENT_MUST_NOT_READ_AS_A_PERMISSION_PROBLEM` and
`A_BUDGET_REFUSAL_NAMING_A_BUDGET_THE_READER_CANNOT_READ_IS_A_DISCLOSURE` in that module.

**Each stop says whether it stopped anything.** A stop recorded while `budget_enforcement` is off
is the install saying what it would have done, and is served as `enforced: false`, which is what
the owner reads to decide the switch (needs-rupash 169).

Task ids: M21.3.3, M21.3.4, M21.3.6
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.spend_view import (
    SpendViewError,
    StopRow,
    budget_stops,
    cost_per_answer,
    dearest,
    may_read_unplaced,
)
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Failed
from brain.ops.budget_stop import Stop
from brain.ops.budgets import BudgetLevel, BudgetPeriod
from brain.ops.spend_store import question_shape_report, recorded_since
from brain.report_routes import money_and_clock
from brain.routing_routes import sessions_of
from brain.tables.budget_stop import BudgetStopRow
from brain.tables.identity import PrincipalRow

log = structlog.get_logger()

#: How many days back the cost per answer and the shape ranking read, unless asked for another.
DEFAULT_DAYS: Final = 30
MAX_DAYS: Final = 366

#: How many shapes the ranking names.
DEAREST_SHAPES: Final = 10

#: How many stops one reading lists, newest first.
MAX_STOPS: Final = 200

Days = Annotated[int, Query(ge=1, le=MAX_DAYS)]


# ------------------------------------------------------------------------ the shapes
class QuantileView(BaseModel):
    """One quantile of what an answer cost, and which it is."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    quantile: float
    cost_minor: int


class CostPerAnswerView(BaseModel):
    """What one answer cost over a window: how many, the mean, and the quantiles it supports.

    `answers` is zero and everything else empty where the reader may see no answer in the window.
    The count is beside the mean because a mean is only readable next to it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    days: int
    machine_included: bool
    answers: int
    mean_minor: float | None
    quantiles: list[QuantileView]
    currency: str


class ShapeLineView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    shape: str
    cost_minor: int


class ShapesView(BaseModel):
    """What each question shape cost, dearest first. The total is the sum of the lines."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    days: int
    machine_included: bool
    dearest: list[ShapeLineView]
    total_minor: int
    currency: str


class StopView(BaseModel):
    """One budget that refused or would have refused, and when its period ends."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: str
    subject: str
    period: str
    since: datetime
    until: datetime
    #: False where the install said it would have stopped and did not.
    enforced: bool


class StopsView(BaseModel):
    """Every budget stop in force that this reader may be told about, newest first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stops: list[StopView]


# ------------------------------------------------------------------------ the helpers
def _sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


async def _departments_of(session: AsyncSession, principals: set[str]) -> dict[str, str]:
    """Where each of these people is placed, for the stops that are on a person."""
    if not principals:
        return {}
    found = await session.execute(
        select(PrincipalRow.id, PrincipalRow.primary_department).where(
            PrincipalRow.id.in_(sorted(principals))
        )
    )
    return {str(one): str(where) for one, where in found.all() if where}


router = APIRouter(prefix=API_PREFIX, tags=["report"])


# ------------------------------------------------------------------------- the routes
@router.get(
    "/report/spend/cost-per-answer", response_model=CostPerAnswerView, responses=COMMON_RESPONSES
)
async def cost_of_an_answer(
    request: Request, asked: Asked, days: Days = DEFAULT_DAYS, include_machine: bool = False
) -> CostPerAnswerView:
    """What one answer cost over the last `days`, as a distribution, over what this reader may see.

    One observation per recorded run, machine traffic left out unless asked for and the answer
    says which it was. A reader who may see no run in the window is told so with no figure.
    """
    code, _zone = money_and_clock()
    async with _sessions(request)() as session:
        actuals = await recorded_since(session, asked.now - timedelta(days=days))
    try:
        found = cost_per_answer(
            actuals, asked.reach, now=asked.now, include_machine=include_machine
        )
    except SpendViewError:
        return CostPerAnswerView(
            days=days,
            machine_included=include_machine,
            answers=0,
            mean_minor=None,
            quantiles=[],
            currency=code,
        )
    return CostPerAnswerView(
        days=days,
        machine_included=include_machine,
        answers=found.count,
        mean_minor=found.mean_minor,
        quantiles=[
            QuantileView(quantile=one, cost_minor=found.quantiles[one])
            for one in sorted(found.quantiles)
        ],
        currency=code,
    )


@router.get("/report/spend/shapes", response_model=ShapesView, responses=COMMON_RESPONSES)
async def dearest_shapes(
    request: Request, asked: Asked, days: Days = DEFAULT_DAYS, include_machine: bool = False
) -> ShapesView:
    """The question shapes that cost most over the last `days`, over what this reader may see."""
    code, _zone = money_and_clock()
    async with _sessions(request)() as session:
        report = await question_shape_report(
            session,
            asked.reach,
            now=asked.now,
            include_machine=include_machine,
            since=asked.now - timedelta(days=days),
        )
    return ShapesView(
        days=days,
        machine_included=include_machine,
        dearest=[
            ShapeLineView(shape=one.key, cost_minor=one.cost_minor)
            for one in dearest(report, DEAREST_SHAPES)
        ],
        total_minor=report.total_minor,
        currency=code,
    )


@router.get("/report/spend/stops", response_model=StopsView, responses=COMMON_RESPONSES)
async def stops_in_force(request: Request, asked: Asked) -> StopsView:
    """Every budget stop in force that this reader may be told about, newest first (M21.3.6).

    A department's stop is placed in its department and a person's in theirs; a company's or an
    agent's is placed nowhere and shown only to a reader of the whole company. Whether each was
    enforced is on it.
    """
    async with _sessions(request)() as session:
        rows = (
            (
                await session.execute(
                    select(BudgetStopRow)
                    .where(BudgetStopRow.until > asked.now)
                    .order_by(BudgetStopRow.since.desc())
                    .limit(MAX_STOPS)
                )
            )
            .scalars()
            .all()
        )
        where = await _departments_of(
            session, {one.subject for one in rows if one.level == BudgetLevel.USER.value}
        )
    placed: list[StopRow] = []
    enforced: dict[tuple[str, str, str, datetime], bool] = {}
    for one in rows:
        stop = Stop(
            level=BudgetLevel(one.level),
            subject=one.subject,
            period=BudgetPeriod(one.period),
            since=one.since,
            until=one.until,
        )
        enforced[(one.level, one.subject, one.period, one.until)] = one.enforced
        department = _department_of(stop, where, asked.reach, asked.now)
        if department is not None:
            placed.append(StopRow(stop=stop, department=department))
    shown = budget_stops(placed, asked.reach, at=asked.now, now=asked.now)
    return StopsView(
        stops=[
            StopView(
                level=one.stop.level.value,
                subject=one.stop.subject,
                period=one.stop.period.value,
                since=one.stop.since,
                until=one.stop.until,
                enforced=enforced[
                    (one.stop.level.value, one.stop.subject, one.stop.period.value, one.stop.until)
                ],
            )
            for one in shown
        ]
    )


#: What a stop that sits in no department is reported under, for a reader of the whole company.
THE_WHOLE_COMPANY: Final = "(whole company)"


def _department_of(
    stop: Stop, where: dict[str, str], reach: EntitlementSet, now: datetime
) -> str | None:
    """The department a stop is reported at, or None where it sits in none this reader may see.

    A department's stop is reported at its department and a person's at the department the
    directory places them in, or at the whole company where it places them nowhere. A stop on the
    company or on an agent is placed nowhere and reported only to a reader whose usage grant
    covers the whole company, which `budget_stops` then holds to `may_read_spend` like the rest.
    """
    if stop.level is BudgetLevel.DEPARTMENT:
        return stop.subject
    if stop.level is BudgetLevel.USER:
        return where.get(stop.subject, THE_WHOLE_COMPANY)
    return THE_WHOLE_COMPANY if may_read_unplaced(reach, now=now) else None
