"""Whether a question is stopped by a used-up budget, and the record of every budget that ran out.

`brain.ops.budget_stop` decided on 2026-09-15 what follows a budget being used up: whoever can raise
it is warned, then the questions it covers are refused until its period ends. Nothing called it, so
ceilings were stored, versioned and shown, and never enforced. This is the half that talks to
PostgreSQL, and the request path asks it once per question, after a halt and before anything is
spent. It decides nothing `budget_stop` and `budgets` already decide.

**Behind `budget_enforcement`, which ships off.** While it is off, a budget that runs out is still
found, warned about and recorded, with `enforced` false: the install would have stopped it and did
not. Those rows are what the owner decides the switch on (needs-rupash 169). See
`brain.ops.features.BUDGET_ENFORCEMENT`.

**An outage of the budget store never stops an answer.** If the ceilings, the spend or the stops
cannot be read, or the record cannot be written, the question is answered as it would have been
before any of this existed and the failure is logged. A budget control that refused everybody when
its own table was unreadable would turn a database fault into an outage of the whole product. See
`BUDGET_ENFORCEMENT_FAILS_SAFE_FOR_THE_ASKER`.

**What is recorded is the ceiling's key and ids.** The stop's level, subject and period, when its
period ends, who the warning was addressed to as principal ids, and the principal and trace of the
request that found the budget used up. Never the question, never a figure. See
`A_USED_UP_BUDGET_IS_RECORDED_BY_ITS_KEY_AND_IDS_ONLY`.

**The person refused is told one plain sentence and nothing about the budget.** Not the amount,
not who set it, not which other budgets exist or how close they are. Two refusals carrying a figure
a week apart subtract into what everybody else spent in between, which is `spend`'s
`A_REFUSAL_CARRIES_NO_FIGURE` argued again. See `SPENDING_LIMIT_REACHED`.

**A stop ends where the period does, in the install's own zone.** `budget_stop.next_period_start`
and `period_start`, with `brain.locale.time_zone`, so a monthly budget's spend and its stop cover
the same month a person in the company means. See
`A_STOP_ENDS_AT_THE_PERIOD_BOUNDARY_IN_THE_INSTALLS_ZONE`.

**Who is warned is whoever holds `admin:budget` over the budget's place.** A department's budget
is placed in its department and a person's in their department; the company's and an agent's are
placed in the whole company, because nothing on a question says which department an agent's money
belongs to. `budget_stop.warn` escalates one level wider when nobody holds it there, and records
the warning as unaddressed when nobody holds it either. Delivering the warning is the notice
channel's, and is the next change; this records who it is for.

Rejected: `brain.ops.spend.preflight`, the estimate and the degradation ladder. It judges what a
question will cost before it costs it and offers a cheaper tier first, which changes how a question
is routed. What the owner chose is a stop once a budget is used up, which is judged on what was
actually spent and needs no estimate. The ladder stays for when routing asks for it.

Task ids: M27.12.5, M27.7.15
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.scope import Scope
from brain.ops.budget_stop import (
    BUDGET_AUTHORITY,
    WINDOWS,
    Consequence,
    Stop,
    consequence_of,
    next_period_start,
    period_start,
    stopped,
    wider_than,
)
from brain.ops.budget_store import in_force as ceiling_in_force
from brain.ops.budgets import Allowance, BudgetKey, BudgetLevel, BudgetPeriod, BudgetRow, tightest
from brain.tables.budget import BudgetVersionRow
from brain.tables.budget_stop import BudgetStopRow
from brain.tables.gate import CapabilityGrantRow
from brain.tables.spend import SpendActualRow

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a store that cannot be read answers the question.
BUDGET_ENFORCEMENT_FAILS_SAFE_FOR_THE_ASKER: Final = (
    "If the ceilings, the spend or the stops cannot be read, or a used-up budget cannot be "
    "recorded, the question is answered as it would have been without budgets and the failure is "
    "logged. A budget control that refused everybody when its own table was unreadable would turn "
    "a database fault into an outage of the whole product."
)

#: Why a used-up budget is recorded by its key and ids and nothing else.
A_USED_UP_BUDGET_IS_RECORDED_BY_ITS_KEY_AND_IDS_ONLY: Final = (
    "A budget that ran out is recorded by its level, subject and period, when the period ends, "
    "who was warned as principal ids, and the principal and trace of the request that found it. "
    "Never the question and never a figure: how much was spent is the spend ledger's, behind the "
    "Spend screen's own grant."
)

#: Why the person refused is told one sentence and nothing about the budget.
THE_ASKER_IS_TOLD_A_SPENDING_LIMIT_AND_NOTHING_ABOUT_IT: Final = (
    "A person whose question a budget stops is told that a spending limit covering their questions "
    "was reached, that whoever manages it was told, and that answers resume when its period ends. "
    "Never the amount, who set it, or anything about another budget: two refusals carrying a "
    "figure a week apart subtract into what everybody else spent in between."
)

#: Why the stop ends at the period boundary in the install's own zone.
A_STOP_ENDS_AT_THE_PERIOD_BOUNDARY_IN_THE_INSTALLS_ZONE: Final = (
    "A stop ends when its period does, floored in the time zone the install set, and the spend it "
    "is judged on is summed over the same period. A month summed in UTC and stopped in the "
    "install's zone would count hours the stop never covers."
)

# ------------------------------------------------------------------------ the figures
#: The least a question can cost, which a budget with no headroom left cannot fit.
ONE_MINOR_UNIT: Final = 1

#: What the person whose question was stopped is told. See
#: `THE_ASKER_IS_TOLD_A_SPENDING_LIMIT_AND_NOTHING_ABOUT_IT`.
SPENDING_LIMIT_REACHED: Final = (
    "A spending limit that covers your questions has been reached, so this question was not "
    "answered. Whoever manages that budget has been told, and questions are answered again when "
    "its period ends."
)


@dataclass(frozen=True)
class Asker:
    """Who is asking, as far as a budget is concerned: the person, their department, the agent."""

    principal_id: str
    #: Empty for a person the directory gives no department.
    department: str = ""
    #: The agent picked beside the question, or None for none.
    agent_id: str | None = None


# ------------------------------------------------------------------------ the decisions
def keys_for(asker: Asker, companies: Sequence[str]) -> tuple[BudgetKey, ...]:
    """Every ceiling that could cover this question, in every period that rolls.

    The company's under each subject a company ceiling is written for, the asker's department and
    the asker, and the agent when one was picked. A per-run ceiling is not here: it refuses the
    request that reached it and is never used up (`budget_stop.DOES_NOT_ROLL`).
    """
    places: list[tuple[BudgetLevel, str]] = [(BudgetLevel.COMPANY, one) for one in companies]
    if asker.department:
        places.append((BudgetLevel.DEPARTMENT, asker.department))
    places.append((BudgetLevel.USER, asker.principal_id))
    if asker.agent_id:
        places.append((BudgetLevel.AGENT, asker.agent_id))
    return tuple((level, subject, period) for level, subject in places for period in WINDOWS)


def used_up(allowances: Sequence[Allowance]) -> Allowance | None:
    """The budget that has run out and binds, or None when none has.

    Run out is the next minor unit not fitting, which is `budgets.tightest` asked about a cost of
    one: spend that has reached the ceiling leaves no headroom for it. When several have,
    `tightest` names the one with least headroom, the widest on a tie, which is the one a person
    relieving it has to start with.
    """
    return tightest(allowances, ONE_MINOR_UNIT)


def place_of(level: BudgetLevel, subject: str, asker: Asker) -> dict[str, Any]:
    """The row a budget admin's grant is matched against: the budget's department, or nothing.

    A grant that admits a row naming no department is one held over the whole company, so the
    company's budget and an agent's are warned to whoever holds the authority over everything.
    """
    if level is BudgetLevel.DEPARTMENT:
        return {"department": subject}
    if level is BudgetLevel.USER and asker.department:
        return {"department": asker.department}
    return {}


def holding_over(grants: Sequence[tuple[str, Scope]], place: dict[str, Any]) -> list[str]:
    """Whoever holds the budget authority in a scope that admits this place, once each, in order."""
    return list(dict.fromkeys(who for who, scope in grants if scope.matches(place)))


# ------------------------------------------------------------------------ the reads
async def company_subjects(session: AsyncSession) -> list[str]:
    """Every subject a company-level ceiling has ever been written for."""
    found = await session.execute(
        select(BudgetVersionRow.subject)
        .where(BudgetVersionRow.level == BudgetLevel.COMPANY.value)
        .distinct()
    )
    return [str(one) for one in found.scalars().all()]


async def spent_in(
    session: AsyncSession, key: BudgetKey, *, since: datetime, until: datetime
) -> int:
    """What the ceiling's subject spent in the window, in minor units, from the spend ledger."""
    level, subject, _ = key
    statement = select(func.coalesce(func.sum(SpendActualRow.cost_minor), 0)).where(
        SpendActualRow.at >= since, SpendActualRow.at < until
    )
    if level is BudgetLevel.DEPARTMENT:
        statement = statement.where(SpendActualRow.department == subject)
    elif level is BudgetLevel.USER:
        statement = statement.where(SpendActualRow.principal_id == subject)
    elif level is BudgetLevel.AGENT:
        statement = statement.where(SpendActualRow.agent_id == subject)
    return int((await session.execute(statement)).scalar_one())


async def allowances_for(
    session: AsyncSession, asker: Asker, *, at: datetime, zone: ZoneInfo
) -> list[Allowance]:
    """Every ceiling in force over this question, with what its subject spent in its window."""
    found: list[Allowance] = []
    for key in keys_for(asker, await company_subjects(session)):
        row: BudgetRow | None = await ceiling_in_force(session, key, at)
        if row is None:
            continue
        since = period_start(key[2], at, zone=zone)
        found.append(
            Allowance(row=row, spent_minor=await spent_in(session, key, since=since, until=at))
        )
    return found


async def recorded_stops(
    session: AsyncSession, keys: Sequence[BudgetKey], *, at: datetime
) -> list[tuple[Stop, bool]]:
    """Every stop recorded against these ceilings whose period has not ended, and if enforced."""
    if not keys:
        return []
    matching = or_(
        *(
            (BudgetStopRow.level == level.value)
            & (BudgetStopRow.subject == subject)
            & (BudgetStopRow.period == period.value)
            for level, subject, period in keys
        )
    )
    rows = (
        await session.execute(select(BudgetStopRow).where(matching, BudgetStopRow.until > at))
    ).scalars()
    return [
        (
            Stop(
                level=BudgetLevel(one.level),
                subject=one.subject,
                period=BudgetPeriod(one.period),
                since=one.since,
                until=one.until,
            ),
            one.enforced,
        )
        for one in rows
    ]


async def budget_admins(session: AsyncSession, *, at: datetime) -> list[tuple[str, Scope]]:
    """Every person holding the budget authority now, with the scope they hold it in."""
    rows = (
        await session.execute(
            select(CapabilityGrantRow.principal_id, CapabilityGrantRow.scope).where(
                CapabilityGrantRow.capability == BUDGET_AUTHORITY.value,
                CapabilityGrantRow.principal_id.is_not(None),
                CapabilityGrantRow.deleted_at.is_(None),
                or_(CapabilityGrantRow.not_after.is_(None), CapabilityGrantRow.not_after > at),
            )
        )
    ).all()
    return [(str(who), Scope.model_validate(scope)) for who, scope in rows]


# ------------------------------------------------------------------------ the write
async def record(
    session: AsyncSession,
    consequence: Consequence,
    *,
    enforced: bool,
    asker: Asker,
    trace_id: str,
) -> None:
    """Record a used-up budget's period once, in the asker's name. A second finding writes nothing.

    See `A_USED_UP_BUDGET_IS_RECORDED_BY_ITS_KEY_AND_IDS_ONLY`.
    """
    stop, notice = consequence.stop, consequence.notice
    await session.execute(
        text("SELECT set_config('app.principal_id', :principal, true)"),
        {"principal": asker.principal_id},
    )
    await session.execute(
        insert(BudgetStopRow)
        .values(
            level=stop.level.value,
            subject=stop.subject,
            period=stop.period.value,
            since=stop.since,
            until=stop.until,
            enforced=enforced,
            addressing=notice.addressing.value,
            addressed_to=list(notice.to),
            principal_id=asker.principal_id,
            trace_id=trace_id,
        )
        .on_conflict_do_nothing(constraint="one_stop_per_period")
    )


# ------------------------------------------------------------------------ the question
async def judged(
    session: AsyncSession,
    asker: Asker,
    *,
    at: datetime,
    zone: ZoneInfo,
    enforce: bool,
    trace_id: str,
) -> bool:
    """Whether this question is stopped, recording a budget that has just run out.

    A stop already in force refuses while `enforce` holds. Otherwise the budget that has run out,
    if one has, is warned about and recorded once per period, enforced or only said, and refuses
    while `enforce` holds.
    """
    allowances = await allowances_for(session, asker, at=at, zone=zone)
    if not allowances:
        return False
    keys = [one.row.key for one in allowances]
    recorded = await recorded_stops(session, keys, at=at)
    if enforce and stopped(allowances, [stop for stop, kept in recorded if kept], at=at):
        return True
    binding = used_up(allowances)
    if binding is None:
        return False
    until = next_period_start(binding.row.period, at, zone=zone)
    if any(
        stop.key == binding.row.key and stop.until == until and kept == enforce
        for stop, kept in recorded
    ):
        return enforce
    grants = await budget_admins(session, at=at)
    row = binding.row
    wider = wider_than(row.level)
    above = [] if wider is None else holding_over(grants, place_of(wider, row.subject, asker))
    consequence = consequence_of(
        binding,
        at=at,
        zone=zone,
        admins=holding_over(grants, place_of(row.level, row.subject, asker)),
        above=above,
    )
    if consequence is None:
        return False
    await record(session, consequence, enforced=enforce, asker=asker, trace_id=trace_id)
    log.info(
        "budget used up",
        level=row.level.value,
        period=row.period.value,
        enforced=enforce,
        addressing=consequence.notice.addressing.value,
    )
    return enforce


async def budget_refusal_for(
    sessions: async_sessionmaker[AsyncSession] | None,
    asker: Asker,
    *,
    at: datetime,
    trace_id: str,
) -> str | None:
    """The sentence a question stopped by a budget is answered with, or None to answer it.

    Reads `budget_enforcement` and judges in one transaction. Never raises: see
    `BUDGET_ENFORCEMENT_FAILS_SAFE_FOR_THE_ASKER`.
    """
    from brain.locale import time_zone
    from brain.ops.features import BUDGET_ENFORCEMENT, is_on

    if sessions is None:
        return None
    try:
        zone = time_zone()
        async with sessions() as session, session.begin():
            enforce = await is_on(session, BUDGET_ENFORCEMENT)
            stops = await judged(
                session, asker, at=at, zone=zone, enforce=enforce, trace_id=trace_id
            )
    except Exception as failed:
        # Broad on purpose: whatever stopped the budget being judged, the question is answered.
        log.warning("budget not judged", error=type(failed).__name__)
        return None
    return SPENDING_LIMIT_REACHED if stops else None
