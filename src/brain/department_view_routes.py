"""A department head's budget against pace and their department's knowledge coverage, over HTTP.

`brain.console.scoped_authority.department_pace` and `department_coverage` were written, argued
and tested, and nothing reached either: no route called them and no page drew them. This module
is the read they sit behind, and it decides one thing of its own, which is who is a head.

**A head is a live row in `gate.department_lead`, read through `brain.ops.head_audit_store.leads`,
which is the same answer M1.8.3 gives.** That function is what decides whose audit reach the staff
sync rewrites, so a person who reads their department's activity on the Activity screen is the
person who is offered its budget and its coverage here, and a lead stood down, a department
retired or a head the roster marks as having left is no head on either screen at once. Rejected:
the departments named on the reader's grants (`brain.console.department_console.departments_held`).
That is where somebody administers, and `scoped_authority.HEADING_A_DEPARTMENT_IS_NOT_THE_SAME_AS_
READING_IT` is the argument against reading a department page off reach: a company-wide grant
names no department and a generous one names several. See
`A_HEAD_IS_WHOEVER_LEADS_IT_AND_EVERYBODY_ELSE_IS_ONE_ANSWER`.

**Everybody who is not a head of the department named gets the console's one 404**, in one
sentence that names the screen and never the department, so a department that does not exist,
one somebody else leads and one this reader used to lead are one answer. The department is a
query parameter rather than a path segment, held to the slug grammar, so a malformed one is the
422 every malformed parameter is and depends on nothing stored.

**The pace is `department_pace`'s and the route withholds it exactly where that function does.**
Each ceiling in force at the department level, daily and monthly, is paired with what the
department has spent since its period began and handed to the function, and a `None` from it is
the 404. With no ceiling in force there is nothing to hand it, so the same question it asks,
`scoped_authority.within_reach` over the budget screen's capability in the department, is asked
directly: a head who may not read the budget is not told that their department has none. **Only
the two fractions and the period are sent**, because that is what the function returns; the
ceiling and the sum stay on the Budget screen, which is read behind its own grant. Spend is every
cost row charged to the department, machine traffic included, because a budget is money and a
nightly job spends it as surely as a person does.

**A pace over spend nothing could have recorded is not a pace.** On an install where no model has
a price in its own currency the recorder writes no cost, so every department would read as having
spent nothing. `brain.console_overview_figures_routes.cost_recorded_in` decides that for the
landing screen and is called here, and the answer is the sentence instead of the fractions, after
the reach has been decided so the sentence is never a head's way past it.

**Coverage reads `know.item` at the reader's own reach, told to the database first.** The items
are read with `app.principal_id` and `app.departments` set from the reader's knowledge reach over
the department, so `know.item`'s policy narrows on the same person `operate.coverage` then judges,
and the statement asks for the department's own items only. A `StoredItem` is what comes back,
which carries no text, and `operate.Covered` is why that is enough. **The areas of a department
are the department**: `operate.coverage` groups an item under the department its visibility names
and nothing finer exists, since a team carries no documents. So a head's report is one row, its
items and its freshness bands, with no total, share or percentage anywhere.

**A coverage load that comes back full is withheld rather than shown short**, with a sentence,
which is `brain.mine_routes`' rule about a budget over a truncated spend load: a figure that is
quietly a floor is read as the figure. The load is narrowed to the reader's reach and to a
department they lead, so whether it came back full is a fact about what they may see.

Task ids: M33.2.1.3, M33.2.1.4
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, TextClause, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.operate import COVERAGE_BANDS
from brain.console.scoped_authority import (
    BUDGET_AUTHORITY,
    department_coverage,
    department_pace,
    within_reach,
)
from brain.console_overview_figures_routes import FigureNotRecordedView, cost_recorded_in
from brain.core.department import SLUG_PATTERN
from brain.core.errors import Absent, Failed
from brain.core.scope import Scope
from brain.knowledge.item_store import reach_from
from brain.knowledge.lifecycle import StoredItem
from brain.knowledge.lifecycle_store import stored_item
from brain.knowledge.search import session_settings
from brain.mine_routes import day_start, month_start
from brain.ops.budget_store import in_force
from brain.ops.budgets import Allowance, BudgetLevel, BudgetPeriod, BudgetRow
from brain.ops.head_audit_store import heads_from, leads
from brain.routing_routes import sessions_of
from brain.tables.organisation import DepartmentLeadRow
from brain.tables.spend import SpendActualRow

log = structlog.get_logger()

PACE_PATH: Final = "/console/department/pace"
COVERAGE_PATH: Final = "/console/department/coverage"

#: The page these answer. Named in the one refusal, which names nothing else.
DEPARTMENT_SCREEN: Final = "department"

# ------------------------------------------------------------------ written-down reasons
#: Why the lead table decides who is answered, and why everybody else is answered alike.
A_HEAD_IS_WHOEVER_LEADS_IT_AND_EVERYBODY_ELSE_IS_ONE_ANSWER: Final = (
    "A department's budget and its coverage are shown to the person who leads it, which is a live "
    "row in gate.department_lead, read by the same statement that decides whose audit reach the "
    "staff sync rewrites. A department nobody here leads, one that does not exist and one this "
    "reader once led are answered with one 404 naming the page and not the department, so typing "
    "names into the address learns nothing about which departments exist or who leads them."
)

#: Why a full coverage load is withheld rather than drawn as the figure.
A_COVERAGE_LOAD_THAT_CAME_BACK_FULL_IS_WITHHELD: Final = (
    "The department's documents are read up to a bound. A load that reached it has left some "
    "out, and a count drawn from it is a floor that reads as the figure, so the rows are not "
    "drawn and the page says why. The load is already narrowed to what this reader may see in a "
    "department they lead, so the sentence says nothing about anything withheld from them."
)

#: What the coverage card says when its load came back full.
COVERAGE_LOAD_WAS_FULL: Final = (
    "This department holds more documents you may read than this page counts, so its coverage "
    "is not drawn here rather than drawn short. The Knowledge screen lists every one."
)

#: The periods a department's pace is read over, in the order a head reads them. A per-run
#: ceiling has no period to be part-way through, which `spend_view.pace` refuses in its words.
PACED_PERIODS: Final[tuple[BudgetPeriod, ...]] = (BudgetPeriod.DAY, BudgetPeriod.MONTH)

#: The most documents one coverage answer is counted from. A resource bound, not a permission.
MAX_ITEMS_COUNTED: Final = 5000

#: One department's stewardship rows at the reach this transaction was told, oldest id first.
#: The columns are `lifecycle_store`'s, so `stored_item` reads them, and the text is not among
#: them because `know.item` holds none.
DEPARTMENT_ITEMS: Final = (
    "SELECT item_id, title, owner_id, visibility, department, state, kind, verified_by, "
    "verified_at, review_by, supersedes, created_at FROM know.item "
    "WHERE department = :department ORDER BY item_id LIMIT :limit"
)


# ------------------------------------------------------------------------- the shapes
class PaceView(BaseModel):
    """How much of one ceiling has gone against how much of its period has. Two fractions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    period: str
    started_at: datetime
    ends_at: datetime
    spent_fraction: float
    elapsed_fraction: float
    #: Spend is running strictly faster than time. `spend_view.Pace.ahead`.
    ahead: bool


class DepartmentPaceView(BaseModel):
    """A department's ceilings in force, each against its pace, for the person who leads it.

    `paces` is empty when no ceiling is in force, and empty with a sentence in `not_recorded`
    when nothing on this install could have recorded a cost. No amount, and no field that could
    hold one: the ceiling and the sum are the Budget screen's.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    paces: list[PaceView]
    not_recorded: list[FigureNotRecordedView]


class CoverageAreaView(BaseModel):
    """One area's documents this reader may see, and how fresh each is. `operate.CoverageRow`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    area: str
    items: int
    by_freshness: dict[str, int]


class DepartmentCoverageView(BaseModel):
    """What a department knows and where the gaps are, for the person who leads it.

    `areas` names only what the reader's own knowledge reach admits, and is empty when it admits
    none of the department. `unread` is empty, or the sentence saying the rows were withheld
    because the load came back full. No total, share or percentage.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    areas: list[CoverageAreaView]
    unread: str


# ---------------------------------------------------------------------- the statements
def headed_by(principal_id: str) -> Select[Any]:
    """The departments this person leads, as `head_audit_store.leads` decides a lead."""
    statement: Select[Any] = leads()
    return statement.where(DepartmentLeadRow.principal_id == principal_id)


def department_spent(department: str, since: datetime, until: datetime) -> Select[tuple[int]]:
    """What was charged to one department inside `[since, until]`, nought over no rows."""
    return select(
        func.coalesce(func.sum(SpendActualRow.cost_minor), 0).label("department_spent_minor")
    ).where(
        SpendActualRow.department == department,
        SpendActualRow.at >= since,
        SpendActualRow.at <= until,
    )


def department_items(department: str, limit: int) -> TextClause:
    """One department's documents, at the reach the transaction was told. See the module."""
    return text(DEPARTMENT_ITEMS).bindparams(department=department, limit=limit)


def period_bounds(period: BudgetPeriod, now: datetime) -> tuple[datetime, datetime]:
    """The first instant of the period holding `now` and the first instant of the next one."""
    if period is BudgetPeriod.DAY:
        began = day_start(now)
        return began, began + timedelta(days=1)
    began = month_start(now)
    following = (began + timedelta(days=32)).replace(day=1)
    return began, following


# ---------------------------------------------------------------------------- the reads
def _not_answerable() -> Absent:
    """The one refusal. Names the page and never the department, the reader or a capability."""
    return Absent(f"the {DEPARTMENT_SCREEN} page is not answerable for this caller")


async def _headed(session: AsyncSession, principal_id: str) -> tuple[str, ...]:
    rows = (await session.execute(headed_by(principal_id))).all()
    return heads_from(tuple(row) for row in rows).get(principal_id, ())


def _sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


async def _ceilings(session: AsyncSession, department: str, now: datetime) -> tuple[BudgetRow, ...]:
    found: list[BudgetRow] = []
    for period in PACED_PERIODS:
        row = await in_force(session, (BudgetLevel.DEPARTMENT, department, period), now)
        if row is not None:
            found.append(row)
    return tuple(found)


async def _spent(session: AsyncSession, department: str, since: datetime, until: datetime) -> int:
    ((summed,),) = (await session.execute(department_spent(department, since, until))).all()
    return int(summed)


def _area_view(area: str, items: int, by_freshness: Any) -> CoverageAreaView:
    return CoverageAreaView(
        area=area,
        items=items,
        by_freshness={band.value: int(by_freshness[band]) for band in COVERAGE_BANDS},
    )


Department = Annotated[str, Query(pattern=SLUG_PATTERN, max_length=63)]

router = APIRouter(prefix=API_PREFIX, tags=["console"])


@router.get(PACE_PATH, response_model=DepartmentPaceView, responses=COMMON_RESPONSES)
async def pace_of_department(
    request: Request, asked: Asked, department: Department
) -> DepartmentPaceView:
    """The department's daily and monthly ceilings against the part of each period gone.

    See `A_HEAD_IS_WHOEVER_LEADS_IT_AND_EVERYBODY_ELSE_IS_ONE_ANSWER` for who is answered, and the
    module docstring for why the pace is withheld exactly where `department_pace` withholds it.
    """
    factory = _sessions(request)
    caller_id = asked.caller.principal.id
    async with factory() as session:
        if department not in await _headed(session, caller_id):
            log.info("department pace not answerable", principal=caller_id)
            raise _not_answerable()
        ceilings = await _ceilings(session, department, asked.now)
        if not ceilings:
            if not within_reach(
                asked.reach, BUDGET_AUTHORITY, Scope.department(department), asked.now
            ):
                raise _not_answerable()
            return DepartmentPaceView(department=department, paces=[], not_recorded=[])
        _, unrecorded = await cost_recorded_in(session)
        paces: list[PaceView] = []
        for ceiling in ceilings:
            started_at, ends_at = period_bounds(ceiling.period, asked.now)
            spent = (
                0
                if unrecorded is not None
                else await _spent(session, department, started_at, asked.now)
            )
            made = department_pace(
                department,
                Allowance(row=ceiling, spent_minor=spent),
                asked.reach,
                started_at=started_at,
                ends_at=ends_at,
                now=asked.now,
            )
            if made is None:
                raise _not_answerable()
            paces.append(
                PaceView(
                    period=ceiling.period.value,
                    started_at=started_at,
                    ends_at=ends_at,
                    spent_fraction=made.spent_fraction,
                    elapsed_fraction=made.elapsed_fraction,
                    ahead=made.ahead,
                )
            )
    return DepartmentPaceView(
        department=department,
        paces=paces if unrecorded is None else [],
        not_recorded=[] if unrecorded is None else [unrecorded],
    )


@router.get(COVERAGE_PATH, response_model=DepartmentCoverageView, responses=COMMON_RESPONSES)
async def coverage_of_department(
    request: Request, asked: Asked, department: Department
) -> DepartmentCoverageView:
    """What the department knows and how fresh it is, for the person who leads it.

    `department_coverage` decides it, over the department's documents read at the reader's own
    reach. See the module docstring for the load and for the one area a department has.
    """
    factory = _sessions(request)
    caller_id = asked.caller.principal.id
    async with factory() as session:
        headed = await _headed(session, caller_id)
        if department not in headed:
            log.info("department coverage not answerable", principal=caller_id)
            raise _not_answerable()
        reach = reach_from(asked.reach, departments=(department,), now=asked.now)
        if reach is None:
            # No read of the knowledge plane, or one it cannot reduce to departments, which
            # `operate.coverage` answers with no row and `reach_from` reads as no reach.
            return DepartmentCoverageView(department=department, areas=[], unread="")
        for setting in session_settings(reach):
            await session.execute(setting)
        rows = await session.execute(department_items(department, MAX_ITEMS_COUNTED))
        items: Sequence[StoredItem] = tuple(stored_item(row) for row in rows.mappings())
    if len(items) >= MAX_ITEMS_COUNTED:
        return DepartmentCoverageView(
            department=department, areas=[], unread=COVERAGE_LOAD_WAS_FULL
        )
    rows_found = department_coverage(
        department,
        items,
        asked.reach,
        headed=headed,
        areas_of={department: (department,)},
        now=asked.now,
    )
    return DepartmentCoverageView(
        department=department,
        areas=[_area_view(one.area, one.items, one.by_freshness) for one in rows_found],
        unread="",
    )
