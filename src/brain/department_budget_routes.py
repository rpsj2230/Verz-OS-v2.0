"""A department's budget, set and moved from the console: its share, its per-run ceiling and the
allowance of everyone in it.

`brain.ops.budgets` built `allocate`, `Transfer`, `apply_transfers` and `user_allowances` and its
own tests held them to their rules, and nothing on an install called one: the only budget rows any
route appended were the company's (`brain.company_routes`) and an agent's
(`brain.agent_workspace_routes`). So no department ever had a budget, no person ever had an
allowance, and the used-up stop (`brain.ops.budget_stop_store`) looked for ceilings no screen
could have written. This module is the four writes that close that, and it adds no rule about
money of its own.

**A share of the company's budget, written as a whole.** `PUT /company/budget/departments` takes the
departments and the fraction of the company's monthly ceiling each is given, hands them to
`allocate`, and appends one row per department as the next version of that department's budget.
`allocate` refuses shares that add up to more than one; this route also refuses an allocation that,
beside the departments it does not name, would add up to more than the company's ceiling, because
a department left out of the request keeps the figure it had and a partial request must not be
the way round the whole. See `A_PARTIAL_ALLOCATION_CANNOT_EXCEED_THE_COMPANYS_CEILING`. Every row
it writes warns at seventy and ninety per cent of its own ceiling (the owner's requirement for the
company, applied to each department), which the rows `allocate` makes carry none of.

**Money moves between departments only by a transfer that names both.** `POST
/company/budget/departments/transfer` is `apply_transfers`: both rows get their next version in one
transaction, the author is the person asking and a reason is required. There is no route that
raises one department's budget without lowering another's or the company's reserve, and the
company's reserve is what a share allocation leaves unspent. See
`NO_IMPLICIT_OVERFLOW_BETWEEN_DEPARTMENTS` in `brain.ops.budgets`.

**Who may write what follows the level.** The allocation and the transfer move the company's money
between departments, so they need `admin:budget` held over everything, as the company's own budget
does. A department's per-run ceiling and its people's allowances are that department's own, so
they need `admin:budget` held over that department, which a department administrator holds. A
caller who holds neither is told which role would let them, and a caller who holds it over another
department is told the same sentence, asked before the department is looked up, so a refusal says
nothing about which departments exist. See `A_REFUSAL_NAMES_THE_ROLE_AND_NEVER_THE_DEPARTMENT`.

**The per-run ceiling is the number the publish gate compares an agent's cost with** (task M20.5.2,
`brain.agent_builder_routes`), read as the department's `RUN` row. It is refused above the
department's monthly budget when one exists, for the reason `budgets.agent_ceilings` refuses a run
above a day: a ceiling that cannot bind is protection nobody has. This is the screen the owner's
question 242 asks about, and it is built here whichever way that is answered: with the publish hold
off, which is how it ships, the ceiling is recorded and compared with nothing.

**An allowance is derived once and then it is a row.** `POST /departments/{d}/budget/allowances`
gives every live member of the department the daily and monthly allowance `user_allowances`
computes from the department's monthly budget and its headcount, capped at a fair share, as the next
version of each. A person whose figure would not change gets no new version, so asking twice writes
nothing the second time. The allowance does not follow the department's budget afterwards, for the
reason `budgets.DepartmentShare` gives about a derived ceiling that moves with no author: asking
again is the recorded act of re-deriving.

**The listing shows a reader the departments they hold the authority over and no others.** A
department head sees their own line; the administrator over everything sees every line and what
the allocation leaves unspent. A reader who holds the authority over nothing is answered with an
empty list, which is also what an install with no department budgets answers, and the list carries
no total that the lines it shows do not add up to.

Task ids: M21.1.2, M21.1.3, M21.1.1
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import trace_of_request
from brain.company_routes import (
    COMPANY_ALERT_FRACTIONS,
    COMPANY_BUDGET_AUTHORITY,
    COMPANY_BUDGET_KEY,
)
from brain.console.scoped_authority import within_reach
from brain.core.department import SLUG_PATTERN
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Failed
from brain.core.scope import Scope
from brain.directory_routes import MAX_DEPARTMENTS, MAX_PEOPLE, live_department_names, live_people
from brain.locale import currency_or_unset
from brain.ops.budget_store import append, in_force, subjects_of
from brain.ops.budgets import (
    BudgetError,
    BudgetLevel,
    BudgetPeriod,
    BudgetRow,
    DepartmentShare,
    Transfer,
    allocate,
    apply_transfers,
    user_allowances,
)
from brain.routing_routes import sessions_of

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why an allocation is judged against the whole of what departments hold and not only its own rows.
A_PARTIAL_ALLOCATION_CANNOT_EXCEED_THE_COMPANYS_CEILING: Final = (
    "A department the request does not name keeps the budget it has. So the shares in a request "
    "are judged together with those figures, and a request that is fine alone but leaves the "
    "departments together holding more than the company's ceiling is refused. Otherwise two "
    "requests of half the departments each would be the implicit overflow `allocate` refuses "
    "in one."
)

#: Why the refusal to a caller without the role is one sentence naming the role.
A_REFUSAL_NAMES_THE_ROLE_AND_NEVER_THE_DEPARTMENT: Final = (
    "The authority is asked before the department is looked up, and the sentence names the role "
    "that would let the caller do it, so the answer for a department that exists and one that does "
    "not is the same words. Typing names into the address learns nothing about which exist."
)

# --------------------------------------------------------------------------- the sentences
#: What a caller without the authority over everything is told for the allocation and a transfer.
MOVING_COMPANY_MONEY_NEEDS_THE_BUDGET_ROLE: Final = (
    "Sharing the company's budget between departments, and moving money from one to another, needs "
    "the budget administrator's role over everything."
)

#: What a caller without the authority over this department is told.
SETTING_A_DEPARTMENT_BUDGET_NEEDS_THE_BUDGET_ROLE: Final = (
    "Setting a department's per-run ceiling and its people's allowances needs the budget "
    "administrator's role over that department."
)

#: What is said when the company has no monthly budget to take a share of.
THE_COMPANY_NEEDS_A_BUDGET_FIRST: Final = (
    "The company has no monthly budget yet, so there is nothing to share. Set it first."
)

#: What is said when a named department is not one this install has.
NOT_A_DEPARTMENT_HERE: Final = "One of the departments named is not a department on this install."

#: What is said when the department has no monthly budget to derive from or compare with.
THE_DEPARTMENT_NEEDS_A_BUDGET_FIRST: Final = (
    "That department has no monthly budget yet. Share the company's budget with it first."
)

#: What is said when a department has nobody in it to give an allowance to.
NOBODY_TO_GIVE_AN_ALLOWANCE_TO: Final = (
    "That department has no live members to give an allowance to."
)

#: What a second write in the same instant is told.
THE_BUDGET_CHANGED_JUST_NOW: Final = "This budget changed a moment ago. Load the page again."

#: What a transfer that would leave the source with nothing is told.
A_TRANSFER_CANNOT_EMPTY_A_DEPARTMENT: Final = (
    "That department cannot give up that much. Moving all of a department's budget suspends it, "
    "which is a different change."
)

#: What a per-run ceiling above the department's month is told.
A_RUN_CEILING_ABOVE_THE_MONTH_CAN_NEVER_BIND: Final = (
    "A run cannot be allowed more than the department may spend in a month, because the month's "
    "budget would stop it first. Lower the figure or raise the department's budget."
)

# ------------------------------------------------------------------------ the figures
#: Where each department's own warning fractions sit: the company's, seventy and ninety per cent
#: (the owner's requirement ARC-B-125), applied to each department it shares the budget with.
DEPARTMENT_ALERT_FRACTIONS: Final[tuple[float, ...]] = COMPANY_ALERT_FRACTIONS

#: The largest figure accepted for one department's per-run ceiling, in minor units.
MAX_RUN_CEILING_MINOR: Final = 1_000_000_000

DEPARTMENT_BUDGETS_PATH: Final = "/company/budget/departments"
TRANSFER_PATH: Final = "/company/budget/departments/transfer"
RUN_CEILING_PATH: Final = "/departments/{department}/budget/run-ceiling"
ALLOWANCES_PATH: Final = "/departments/{department}/budget/allowances"

#: The authority a budget is set with, as the company's and an agent's routes hold it.
BUDGET_AUTHORITY = COMPANY_BUDGET_AUTHORITY


# ------------------------------------------------------------------------- the shapes
class ShareAsked(BaseModel):
    """One department and the fraction of the company's monthly budget it is given."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: Annotated[str, Field(min_length=2, max_length=60, pattern=SLUG_PATTERN)]
    share: Annotated[float, Field(gt=0.0, le=1.0)]


class AllocationAsked(BaseModel):
    """The departments to share the company's monthly budget between, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    shares: Annotated[list[ShareAsked], Field(min_length=1, max_length=MAX_DEPARTMENTS)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]

    @model_validator(mode="after")
    def _each_department_once(self) -> AllocationAsked:
        names = [one.department for one in self.shares]
        if len(set(names)) != len(names):
            msg = "a department appears twice in one allocation"
            raise ValueError(msg)
        return self


class TransferAsked(BaseModel):
    """Money moved from one department's monthly budget to another's, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_department: Annotated[str, Field(min_length=2, max_length=60, pattern=SLUG_PATTERN)]
    to_department: Annotated[str, Field(min_length=2, max_length=60, pattern=SLUG_PATTERN)]
    amount_minor: Annotated[int, Field(ge=1, le=MAX_RUN_CEILING_MINOR * 100)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]

    @model_validator(mode="after")
    def _two_departments(self) -> TransferAsked:
        if self.from_department == self.to_department:
            msg = "a transfer moves money between two departments"
            raise ValueError(msg)
        return self


class RunCeilingAsked(BaseModel):
    """A department's per-run ceiling in the install's minor units, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ceiling_minor: Annotated[int, Field(ge=1, le=MAX_RUN_CEILING_MINOR)]
    reason: Annotated[str, Field(min_length=1, max_length=200)]


class AllowancesAsked(BaseModel):
    """Why a department's people are given allowances again from its budget as it now stands."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: Annotated[str, Field(min_length=1, max_length=200)]


class DepartmentLine(BaseModel):
    """One department's monthly budget and its per-run ceiling as they now stand."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    monthly_minor: int | None
    monthly_version: int | None
    run_ceiling_minor: int | None
    run_version: int | None


class DepartmentBudgetsView(BaseModel):
    """The department budgets this reader holds the authority over.

    `unallocated_minor` is the company's ceiling less every department's, and is sent only to a
    reader who holds the authority over everything, because it is the other half of a subtraction
    the department heads' lines do not let them make.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    currency: str
    lines: list[DepartmentLine]
    may_allocate: bool
    unallocated_minor: int | None = None


class AllocationView(BaseModel):
    """The department budgets an allocation or a transfer left, as they now stand."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    currency: str
    lines: list[DepartmentLine]
    unallocated_minor: int


class RunCeilingView(BaseModel):
    """A department's per-run ceiling as it now stands."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    ceiling_minor: int
    currency: str
    version: int
    effective_from: datetime


class AllowancesView(BaseModel):
    """What each person in a department was given, and how many people it was given to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    people: int
    daily_minor: int
    monthly_minor: int
    currency: str
    effective_from: datetime


# ------------------------------------------------------------------------- the pure half
def plan_allocation(
    company: BudgetRow,
    shares: Sequence[DepartmentShare],
    held: Mapping[str, BudgetRow],
    *,
    author: str,
    reason: str,
    now: datetime,
) -> tuple[BudgetRow, ...]:
    """The rows an allocation appends: version one for a new department, the next for the rest.

    `allocate` makes the figures and refuses shares above one. This adds the department's warning
    fractions, supersedes the row a department already holds (a row at version one would be a
    history that cannot be ordered), and refuses an allocation that, beside the departments it
    does not name, would hold more than the company's ceiling. See
    `A_PARTIAL_ALLOCATION_CANNOT_EXCEED_THE_COMPANYS_CEILING`.
    """
    made = allocate(company, shares, author=author, effective_from=now)
    named = {one.subject for one in made}
    kept = sum(row.ceiling_minor for name, row in held.items() if name not in named)
    if kept + sum(one.ceiling_minor for one in made) > company.ceiling_minor:
        msg = (
            "with the departments this request does not name, the shares would hold more than the "
            "company's budget"
        )
        raise BudgetError(msg)
    rows: list[BudgetRow] = []
    for one in made:
        current = held.get(one.subject)
        if current is None:
            rows.append(
                dataclasses.replace(
                    one,
                    alert_fractions=DEPARTMENT_ALERT_FRACTIONS,
                    reason=f"{reason}: {one.reason}",
                )
            )
        else:
            rows.append(
                current.superseded_by(
                    ceiling_minor=one.ceiling_minor,
                    author=author,
                    effective_from=now,
                    reason=f"{reason}: {one.reason}",
                    alert_fractions=current.alert_fractions or DEPARTMENT_ALERT_FRACTIONS,
                )
            )
    return tuple(rows)


def plan_transfer(
    source: BudgetRow,
    destination: BudgetRow,
    *,
    amount_minor: int,
    author: str,
    reason: str,
    now: datetime,
) -> tuple[BudgetRow, BudgetRow]:
    """The next version of both departments' monthly budgets after one transfer, source first.

    `apply_transfers` returns every row it was handed, in the order handed, so the two rows that
    come back are the two that changed. A source that would be left with nothing is refused by it.
    """
    moved = apply_transfers(
        (source, destination),
        (
            Transfer(
                from_department=source.subject,
                to_department=destination.subject,
                amount_minor=amount_minor,
                author=author,
                at=now,
                reason=reason,
            ),
        ),
    )
    return moved[0], moved[1]


def plan_allowances(
    department: BudgetRow,
    members: Sequence[str],
    held: Mapping[tuple[str, BudgetPeriod], BudgetRow],
    *,
    author: str,
    reason: str,
    now: datetime,
) -> tuple[tuple[BudgetRow, ...], tuple[int, int]]:
    """The allowance rows to append for these people, and the (daily, monthly) figure each gets.

    Everyone in a department is given the same pair: the fair-share cap and the even split do not
    depend on who the person is. A row whose ceiling would not change is not appended, so asking
    again with nothing changed writes nothing.
    """
    ordered = sorted(set(members))
    rows: list[BudgetRow] = []
    figures = (0, 0)
    for person in ordered:
        daily, monthly = user_allowances(
            department,
            principal_id=person,
            headcount=len(ordered),
            author=author,
            effective_from=now,
        )
        figures = (daily.ceiling_minor, monthly.ceiling_minor)
        for made in (daily, monthly):
            current = held.get((person, made.period))
            if current is None:
                rows.append(dataclasses.replace(made, reason=f"{reason}: {made.reason}"))
            elif current.ceiling_minor != made.ceiling_minor:
                rows.append(
                    current.superseded_by(
                        ceiling_minor=made.ceiling_minor,
                        author=author,
                        effective_from=now,
                        reason=f"{reason}: {made.reason}",
                    )
                )
    return tuple(rows), figures


def lines_of(
    monthly: Mapping[str, BudgetRow],
    runs: Mapping[str, BudgetRow],
    reach: EntitlementSet,
    now: datetime,
) -> list[DepartmentLine]:
    """The lines this reach holds the authority over, in department order. No other line exists."""
    names = sorted(set(monthly) | set(runs))
    return [
        DepartmentLine(
            department=name,
            monthly_minor=None if name not in monthly else monthly[name].ceiling_minor,
            monthly_version=None if name not in monthly else monthly[name].version,
            run_ceiling_minor=None if name not in runs else runs[name].ceiling_minor,
            run_version=None if name not in runs else runs[name].version,
        )
        for name in names
        if within_reach(reach, BUDGET_AUTHORITY, Scope.department(name), now)
    ]


# ------------------------------------------------------------------------- the reads
def _refused(message: str, status: int = 403) -> JSONResponse:
    return JSONResponse(status_code=status, content={"message": message})


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


async def department_rows(
    session: AsyncSession, period: BudgetPeriod, now: datetime
) -> dict[str, BudgetRow]:
    """Every department's budget row for this period in force at `now`, by department."""
    found: dict[str, BudgetRow] = {}
    for name in await subjects_of(session, BudgetLevel.DEPARTMENT, limit=MAX_DEPARTMENTS):
        row = await in_force(session, (BudgetLevel.DEPARTMENT, name, period), now)
        if row is not None:
            found[name] = row
    return found


async def live_departments(session: AsyncSession) -> set[str]:
    """The slug of every live department on this install."""
    rows = (await session.execute(live_department_names(MAX_DEPARTMENTS))).all()
    return {str(one[0]) for one in rows}


def _may_move_company_money(reach: EntitlementSet, now: datetime) -> bool:
    return within_reach(reach, BUDGET_AUTHORITY, Scope.unrestricted(), now)


router = APIRouter(prefix=API_PREFIX, tags=["company"])


@router.get(
    DEPARTMENT_BUDGETS_PATH, response_model=DepartmentBudgetsView, responses=COMMON_RESPONSES
)
async def department_budgets(request: Request, asked: Asked) -> DepartmentBudgetsView:
    """The department budgets this reader holds the authority over. See the module docstring."""
    factory = _require_sessions(request)
    async with factory() as session:
        monthly = await department_rows(session, BudgetPeriod.MONTH, asked.now)
        runs = await department_rows(session, BudgetPeriod.RUN, asked.now)
        company = await in_force(session, COMPANY_BUDGET_KEY, asked.now)
    everything = _may_move_company_money(asked.reach, asked.now)
    unallocated = (
        None
        if not everything or company is None
        else company.ceiling_minor - sum(one.ceiling_minor for one in monthly.values())
    )
    return DepartmentBudgetsView(
        currency=currency_or_unset(),
        lines=lines_of(monthly, runs, asked.reach, asked.now),
        may_allocate=everything,
        unallocated_minor=unallocated,
    )


@router.put(DEPARTMENT_BUDGETS_PATH, response_model=AllocationView, responses=COMMON_RESPONSES)
async def allocate_department_budgets(
    request: Request, body: AllocationAsked, asked: Asked
) -> JSONResponse | AllocationView:
    """Share the company's monthly budget between departments. See the module docstring."""
    if not _may_move_company_money(asked.reach, asked.now):
        log.info("department allocation refused", principal=asked.caller.principal.id)
        return _refused(MOVING_COMPANY_MONEY_NEEDS_THE_BUDGET_ROLE)
    factory = _require_sessions(request)
    async with factory() as session:
        company = await in_force(session, COMPANY_BUDGET_KEY, asked.now)
        if company is None:
            return _refused(THE_COMPANY_NEEDS_A_BUDGET_FIRST, 409)
        if not {one.department for one in body.shares} <= await live_departments(session):
            return _refused(NOT_A_DEPARTMENT_HERE, 422)
        held = await department_rows(session, BudgetPeriod.MONTH, asked.now)
        try:
            rows = plan_allocation(
                company,
                [
                    DepartmentShare(department=one.department, share=one.share)
                    for one in body.shares
                ],
                held,
                author=asked.caller.principal.id,
                reason=body.reason,
                now=asked.now,
            )
        except BudgetError as refused:
            await session.rollback()
            log.info("department allocation refused", principal=asked.caller.principal.id)
            # The caller holds the authority over everything, so the budget's own sentence, which
            # names the totals, is theirs to be told.
            return _refused(str(refused), 422)
        for row in rows:
            await append(session, row, ent_hash=asked.reach.ent_hash(), trace_id=trace_of_request())
        await session.commit()
        after = {**held, **{one.subject: one for one in rows}}
    log.info("department budgets allocated", principal=asked.caller.principal.id)
    return AllocationView(
        currency=currency_or_unset(),
        lines=lines_of(after, {}, asked.reach, asked.now),
        unallocated_minor=company.ceiling_minor - sum(one.ceiling_minor for one in after.values()),
    )


@router.post(TRANSFER_PATH, response_model=AllocationView, responses=COMMON_RESPONSES)
async def transfer_between_departments(
    request: Request, body: TransferAsked, asked: Asked
) -> JSONResponse | AllocationView:
    """Move money from one department's monthly budget to another's. See the module docstring."""
    if not _may_move_company_money(asked.reach, asked.now):
        log.info("department transfer refused", principal=asked.caller.principal.id)
        return _refused(MOVING_COMPANY_MONEY_NEEDS_THE_BUDGET_ROLE)
    factory = _require_sessions(request)
    async with factory() as session:
        company = await in_force(session, COMPANY_BUDGET_KEY, asked.now)
        held = await department_rows(session, BudgetPeriod.MONTH, asked.now)
        source, destination = held.get(body.from_department), held.get(body.to_department)
        if company is None or source is None or destination is None:
            return _refused(NOT_A_DEPARTMENT_HERE, 422)
        try:
            moved = plan_transfer(
                source,
                destination,
                amount_minor=body.amount_minor,
                author=asked.caller.principal.id,
                reason=body.reason,
                now=asked.now,
            )
        except BudgetError:
            await session.rollback()
            if body.amount_minor >= source.ceiling_minor:
                return _refused(A_TRANSFER_CANNOT_EMPTY_A_DEPARTMENT, 422)
            return _refused(THE_BUDGET_CHANGED_JUST_NOW, 409)
        for row in moved:
            await append(session, row, ent_hash=asked.reach.ent_hash(), trace_id=trace_of_request())
        await session.commit()
        after = {**held, **{one.subject: one for one in moved}}
    log.info("department money transferred", principal=asked.caller.principal.id)
    return AllocationView(
        currency=currency_or_unset(),
        lines=lines_of(after, {}, asked.reach, asked.now),
        unallocated_minor=company.ceiling_minor - sum(one.ceiling_minor for one in after.values()),
    )


@router.put(RUN_CEILING_PATH, response_model=RunCeilingView, responses=COMMON_RESPONSES)
async def set_department_run_ceiling(
    request: Request, department: str, body: RunCeilingAsked, asked: Asked
) -> JSONResponse | RunCeilingView:
    """Set a department's per-run ceiling. See the module docstring."""
    if not within_reach(asked.reach, BUDGET_AUTHORITY, Scope.department(department), asked.now):
        log.info("department run ceiling refused", principal=asked.caller.principal.id)
        return _refused(SETTING_A_DEPARTMENT_BUDGET_NEEDS_THE_BUDGET_ROLE)
    factory = _require_sessions(request)
    async with factory() as session:
        if department not in await live_departments(session):
            return _refused(NOT_A_DEPARTMENT_HERE, 422)
        month = await in_force(
            session, (BudgetLevel.DEPARTMENT, department, BudgetPeriod.MONTH), asked.now
        )
        if month is not None and body.ceiling_minor > month.ceiling_minor:
            return _refused(A_RUN_CEILING_ABOVE_THE_MONTH_CAN_NEVER_BIND, 422)
        key = (BudgetLevel.DEPARTMENT, department, BudgetPeriod.RUN)
        current = await in_force(session, key, asked.now)
        author = asked.caller.principal.id
        try:
            row = (
                BudgetRow(
                    level=BudgetLevel.DEPARTMENT,
                    subject=department,
                    period=BudgetPeriod.RUN,
                    ceiling_minor=body.ceiling_minor,
                    version=1,
                    author=author,
                    effective_from=asked.now,
                    reason=body.reason,
                )
                if current is None
                else current.superseded_by(
                    ceiling_minor=body.ceiling_minor,
                    author=author,
                    effective_from=asked.now,
                    reason=body.reason,
                )
            )
        except BudgetError:
            await session.rollback()
            return _refused(THE_BUDGET_CHANGED_JUST_NOW, 409)
        await append(session, row, ent_hash=asked.reach.ent_hash(), trace_id=trace_of_request())
        await session.commit()
    log.info("department run ceiling set", principal=author)
    return RunCeilingView(
        department=department,
        ceiling_minor=row.ceiling_minor,
        currency=currency_or_unset(),
        version=row.version,
        effective_from=row.effective_from,
    )


@router.post(ALLOWANCES_PATH, response_model=AllowancesView, responses=COMMON_RESPONSES)
async def give_department_allowances(
    request: Request, department: str, body: AllowancesAsked, asked: Asked
) -> JSONResponse | AllowancesView:
    """Give everyone in a department their daily and monthly allowance. See the module docstring."""
    if not within_reach(asked.reach, BUDGET_AUTHORITY, Scope.department(department), asked.now):
        log.info("department allowances refused", principal=asked.caller.principal.id)
        return _refused(SETTING_A_DEPARTMENT_BUDGET_NEEDS_THE_BUDGET_ROLE)
    factory = _require_sessions(request)
    async with factory() as session:
        if department not in await live_departments(session):
            return _refused(NOT_A_DEPARTMENT_HERE, 422)
        month = await in_force(
            session, (BudgetLevel.DEPARTMENT, department, BudgetPeriod.MONTH), asked.now
        )
        if month is None:
            return _refused(THE_DEPARTMENT_NEEDS_A_BUDGET_FIRST, 409)
        people = (await session.execute(live_people(MAX_PEOPLE))).all()
        members = [str(one[0]) for one in people if one[2] == department and one[4] is None]
        if not members:
            return _refused(NOBODY_TO_GIVE_AN_ALLOWANCE_TO, 409)
        held: dict[tuple[str, BudgetPeriod], BudgetRow] = {}
        for person in members:
            for period in (BudgetPeriod.DAY, BudgetPeriod.MONTH):
                row = await in_force(session, (BudgetLevel.USER, person, period), asked.now)
                if row is not None:
                    held[(person, period)] = row
        try:
            rows, (daily, monthly) = plan_allowances(
                month,
                members,
                held,
                author=asked.caller.principal.id,
                reason=body.reason,
                now=asked.now,
            )
        except BudgetError:
            await session.rollback()
            return _refused(THE_BUDGET_CHANGED_JUST_NOW, 409)
        for row in rows:
            await append(session, row, ent_hash=asked.reach.ent_hash(), trace_id=trace_of_request())
        await session.commit()
    log.info("department allowances given", principal=asked.caller.principal.id)
    return AllowancesView(
        department=department,
        people=len(members),
        daily_minor=daily,
        monthly_minor=monthly,
        currency=currency_or_unset(),
        effective_from=asked.now,
    )
