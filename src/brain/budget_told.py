"""Whoever administers a budget is told when it is nearing its ceiling and when it has run out.

A budget row stores the fractions of its ceiling at which somebody should be told
(`BudgetRow.alert_fractions`) and `brain.ops.budget_stop_store` records a used-up budget with the
principals it was to be told to (`addressed_to`), and until this module nothing sent either to
anyone. The Spend screen listed a stop for a person who thought to open it. This is the sender,
the one `brain.ops.notices` had marked "no channel is chosen for it yet".

**Two messages, one pass.** A budget at a company or department level that has crossed a warning
fraction, and not yet run out, tells its administrators once per period about the highest fraction
it has reached; a budget that has run out tells the principals the stop recorded, once per stop.
A budget that jumps from sixty to ninety-five per cent tells about ninety and not about seventy as
well, because a message about a threshold already passed is noise. See
`A_WARNING_IS_ABOUT_THE_HIGHEST_FRACTION_REACHED`.

**Who is told is whoever holds `admin:budget` over the budget's place, and nobody else.** The same
rule `budget_stop_store` applies when it records a stop (`place_of`, `holding_over`), with the same
escalation: a department nobody administers is told to whoever administers everything. A person's
own allowance and an agent's ceiling warn nobody here, since a stop on them already says who was
told and the person is told the sentence they are refused with.

**The message names the budget and how far it has got, never an amount.** A chat message is
forwarded and read over a shoulder, and the figure is on the Spend screen behind its own grant. It
names no question, no person who spent and no other budget. See `A_BUDGET_MESSAGE_NAMES_NO_AMOUNT`.

**It ships off, and the notice does not.** `BUDGET_WARNINGS_TOLD` is a feature, so an install turns
the sending on after the owner has seen it work, as it did for the control alerts
(`brain.control_not_run_told`). The notices themselves have a switch each on the Notices screen
(`brain.ops.notices.NoticeKind.BUDGET_NEARING` and `BUDGET_STOPPED`), and this sender asks both at
the moment it sends, as every sender does.

**The web process tells and the worker records.** The warning is recorded by the request that found
the budget used up, in the web process, and told by the loop that process starts, for the reason
`brain.automation_paused_told` gives: the worker holds no channel's token.

Rejected: telling at the instant a question crosses a fraction. It puts a database read and a chat
send on the answer path of a question for a figure that is correct a quarter of an hour later, and a
failed send would then be a failed answer; `budget_stop_store` already refuses to let the budget
store's faults reach the asker. Rejected: a table of alerts already sent. The chat ledger's
idempotency key is that table, and a second table would be a second place for "was this sent" to
disagree.

Task ids: M21.1.1, M21.2.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

import structlog
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from brain.chat_answer import console_link
from brain.ops.budget_stop import WINDOWS, period_start
from brain.ops.budget_stop_store import (
    Asker,
    budget_admins,
    holding_over,
    place_of,
    spent_in,
)
from brain.ops.budget_store import in_force, subjects_of
from brain.ops.budgets import BudgetLevel, BudgetPeriod
from brain.ops.features import is_on
from brain.ops.features_declared.budget_warnings_told import BUDGET_WARNINGS_TOLD
from brain.ops.notices import NoticeKind, notice_is_on
from brain.tables.budget_stop import BudgetStopRow
from brain.tables.channel import DeliveryOutcome
from brain.tell_later import tell

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a jump past two fractions tells about the higher.
A_WARNING_IS_ABOUT_THE_HIGHEST_FRACTION_REACHED: Final = (
    "A budget that goes from sixty to ninety-five per cent between two passes has passed seventy "
    "and ninety. The message is about ninety: telling about seventy as well is a second message "
    "about something already overtaken, and the key carries the fraction so each is told at most "
    "once in the period."
)

#: Why the message carries no amount.
A_BUDGET_MESSAGE_NAMES_NO_AMOUNT: Final = (
    "A chat message is forwarded, pasted and read over a shoulder. It says which budget and how "
    "far it has got as a share of its ceiling, and the amounts are on the Spend screen behind its "
    "own grant. It names no question and no person who spent."
)

# ------------------------------------------------------------------------ the figures
#: How often each web process asks which budgets are near their ceiling. Spend moves in minutes
#: and a warning is useful within the hour, so a quarter of an hour is prompt without being a poll.
TELL_EVERY: Final = timedelta(minutes=15)

#: The most subjects at one level one pass reads. A resource bound; an install has tens of
#: departments, and a pass beyond this is told at the next one.
MOST_SUBJECTS_PER_LEVEL: Final = 500

#: The most recorded stops one pass reads.
MOST_STOPS_PER_PASS: Final = 500

#: The levels that warn here. See the module docstring on why a person's and an agent's do not.
WARNED_LEVELS: Final = (BudgetLevel.COMPANY, BudgetLevel.DEPARTMENT)

#: The key words that begin an intent reference, one per message.
NEARING_KEY: Final = "budget_nearing"
USED_UP_KEY: Final = "budget_used_up"

#: The page of the console where the figures are, for the people who may read them.
SPEND_PATH: Final = "/company/consumption"


@dataclass(frozen=True)
class Nearing:
    """One budget that has reached a warning fraction in its current period and is not yet spent."""

    level: BudgetLevel
    subject: str
    period: BudgetPeriod
    fraction: float
    began: datetime
    holders: tuple[str, ...]


@dataclass(frozen=True)
class UsedUp:
    """One recorded stop still in its period, and the principals it was to be told to."""

    level: BudgetLevel
    subject: str
    period: BudgetPeriod
    since: datetime
    until: datetime
    enforced: bool
    holders: tuple[str, ...]


@dataclass(frozen=True)
class Told:
    """What one pass did. Counts of messages and never of people."""

    nearing: int = 0
    used_up: int = 0
    switched_off: bool = False


# ------------------------------------------------------------------------- the pure half
def whose(level: BudgetLevel, subject: str) -> str:
    """The budget's owner as a person reads it: the company, or a department by its slug."""
    return "the company" if level is BudgetLevel.COMPANY else f"the {subject} department"


def percent(fraction: float) -> str:
    """A fraction as the whole per cent a person reads, never a fraction of one."""
    return f"{round(fraction * 100)}%"


def nearing_text(one: Nearing, *, link: str = "") -> str:
    """The sentence a budget's administrator is told as it nears its ceiling.

    See `A_BUDGET_MESSAGE_NAMES_NO_AMOUNT`.
    """
    said = (
        f"The {one.period.value}ly budget for {whose(one.level, one.subject)} has reached "
        f"{percent(one.fraction)} of its ceiling."
    )
    return f"{said} See the figures: {link}" if link else said


def used_up_text(one: UsedUp, *, zone: ZoneInfo, link: str = "") -> str:
    """The sentence a budget's administrator is told when it has run out.

    Says whether the install is refusing questions for it, because an administrator reading that a
    budget ran out who then finds people still being answered would have been told half of it.
    """
    until = one.until.astimezone(zone).strftime("%d %B %Y")
    head = f"The {one.period.value}ly budget for {whose(one.level, one.subject)} has run out."
    if one.enforced:
        said = f"{head} Questions charged to it are refused until {until}."
    else:
        said = (
            f"{head} Questions are still being answered, because spending limits are not being "
            f"enforced on this install. The budget starts again on {until}."
        )
    return f"{said} See the figures: {link}" if link else said


def nearing_ref(one: Nearing) -> str:
    """The key a warning is told under: the budget, its period's start and the fraction reached."""
    began = one.began.astimezone(UTC).isoformat()
    return (
        f"{NEARING_KEY}.{one.level.value}.{one.subject}.{one.period.value}.{began}.{one.fraction}"
    )


def used_up_ref(one: UsedUp) -> str:
    """The key a stop is told under: the budget and when its period began."""
    since = one.since.astimezone(UTC).isoformat()
    return f"{USED_UP_KEY}.{one.level.value}.{one.subject}.{one.period.value}.{since}"


def highest_reached(
    fractions: Sequence[float], spent_minor: int, ceiling_minor: int
) -> float | None:
    """The highest warning fraction this spend has reached, or None when none, or when it is spent.

    A budget with no headroom left is not nearing its ceiling, it is at it, and the stop is what
    tells about that.
    """
    if spent_minor >= ceiling_minor:
        return None
    reached = [one for one in fractions if spent_minor >= ceiling_minor * one]
    return max(reached) if reached else None


# ------------------------------------------------------------------------ the reads
async def nearing_budgets(
    session: AsyncSession, *, now: datetime, zone: ZoneInfo
) -> tuple[Nearing, ...]:
    """Every company and department budget that has reached a warning fraction this period."""
    grants = await budget_admins(session, at=now)
    found: list[Nearing] = []
    for level in WARNED_LEVELS:
        for subject in await subjects_of(session, level, limit=MOST_SUBJECTS_PER_LEVEL):
            for period in WINDOWS:
                key = (level, subject, period)
                row = await in_force(session, key, now)
                if row is None or not row.alert_fractions:
                    continue
                began = period_start(period, now, zone=zone)
                spent = await spent_in(session, key, since=began, until=now)
                reached = highest_reached(row.alert_fractions, spent, row.ceiling_minor)
                if reached is None:
                    continue
                place = place_of(level, subject, Asker(principal_id=""))
                # Nobody over this department is told whoever holds it over everything.
                holders = holding_over(grants, place) or holding_over(grants, {})
                found.append(
                    Nearing(
                        level=level,
                        subject=subject,
                        period=period,
                        fraction=reached,
                        began=began,
                        holders=tuple(holders),
                    )
                )
    return tuple(found)


async def used_up_budgets(session: AsyncSession, *, now: datetime) -> tuple[UsedUp, ...]:
    """Every recorded stop whose period has not ended, with the principals it was to be told to."""
    rows = (
        await session.execute(
            select(BudgetStopRow)
            .where(BudgetStopRow.until > now)
            .order_by(BudgetStopRow.since.desc())
            .limit(MOST_STOPS_PER_PASS)
        )
    ).scalars()
    return tuple(
        UsedUp(
            level=BudgetLevel(one.level),
            subject=one.subject,
            period=BudgetPeriod(one.period),
            since=one.since,
            until=one.until,
            enforced=one.enforced,
            holders=tuple(one.addressed_to),
        )
        for one in rows
    )


# ------------------------------------------------------------------------ the sending half
async def budget_warnings_are_on(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether `budget_warnings_told` is switched on now. Off when nobody has said otherwise."""
    async with sessions() as session:
        return await is_on(session, BUDGET_WARNINGS_TOLD)


async def _tell_each(
    request: Request, holders: Sequence[str], text: str, *, ref: str, now: datetime
) -> int:
    """Tell each of these people once under this key. How many messages were issued."""
    issued = 0
    for person in holders:
        delivered = await tell(request, person, text, intent_ref=ref, now=now)
        # A second pass over the same budget is handed the first's record and issues nothing.
        issued += (
            delivered is not None and delivered.issued and delivered.outcome is DeliveryOutcome.SENT
        )
    return issued


async def tell_budget_administrators(
    request: Request,
    sessions: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    zone: ZoneInfo,
    nearing: Sequence[Nearing] | None = None,
    used_up: Sequence[UsedUp] | None = None,
) -> Told:
    """Tell each budget's administrators about a budget near its ceiling and one that has run out.

    `nearing` and `used_up`, when given, replace reading them, which is how an install check tells
    only about a budget of its own.
    """
    if not await budget_warnings_are_on(sessions):
        return Told(switched_off=True)
    async with sessions() as session:
        warn = await notice_is_on(session, NoticeKind.BUDGET_NEARING)
        stop = await notice_is_on(session, NoticeKind.BUDGET_STOPPED)
        close = (
            tuple(nearing)
            if nearing is not None
            else (await nearing_budgets(session, now=now, zone=zone) if warn else ())
        )
        spent = (
            tuple(used_up)
            if used_up is not None
            else (await used_up_budgets(session, now=now) if stop else ())
        )
    link = console_link(SPEND_PATH)
    told_nearing = told_used_up = 0
    if warn:
        for one in close:
            told_nearing += await _tell_each(
                request, one.holders, nearing_text(one, link=link), ref=nearing_ref(one), now=now
            )
    if stop:
        for gone in spent:
            told_used_up += await _tell_each(
                request,
                gone.holders,
                used_up_text(gone, zone=zone, link=link),
                ref=used_up_ref(gone),
                now=now,
            )
    return Told(nearing=told_nearing, used_up=told_used_up)


async def keep_telling_budget_administrators(app: FastAPI) -> None:
    """Tell about budgets every `TELL_EVERY` for as long as the application runs.

    A failure is logged by its kind and the next pass tries again, as the other loops do.
    """
    # Imported here: the mailbox module imports the events route, which imports this package.
    from brain.locale import time_zone
    from brain.mailbox_read import request_for

    while True:
        await asyncio.sleep(TELL_EVERY.total_seconds())
        sessions = getattr(app.state, "db_sessions", None)
        if sessions is None:
            continue
        try:
            told = await tell_budget_administrators(
                request_for(app), sessions, now=datetime.now(UTC), zone=time_zone()
            )
        except Exception as exc:
            log.warning("budgets not told", kind=type(exc).__name__)
            continue
        if told.nearing or told.used_up:
            log.info("budgets told", nearing=told.nearing, used_up=told.used_up)
