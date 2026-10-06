"""Whether a question is stopped by a used-up budget, and the record of every budget that ran out.

The decisions are tested as values, the orchestration over stand-in reads so each branch is shown
without a database, and the store against PostgreSQL at head, where the policy, the uniqueness and
the switch are the real ones.

Task ids: M27.12.5, M27.7.15
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from brain.core.scope import Scope
from brain.db import normalise_database_url
from brain.ops import budget_stop_store as store
from brain.ops.budget_stop import (
    Addressing,
    Stop,
    next_period_start,
    period_start,
)
from brain.ops.budget_stop_store import (
    BUDGET_ENFORCEMENT_FAILS_SAFE_FOR_THE_ASKER,
    SPENDING_LIMIT_REACHED,
    Asker,
    budget_refusal_for,
    holding_over,
    judged,
    keys_for,
    place_of,
    used_up,
)
from brain.ops.budgets import Allowance, BudgetLevel, BudgetPeriod, BudgetRow

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
AT = datetime(2999, 3, 15, 10, 0, tzinfo=UTC)
ZONE = ZoneInfo("Asia/Singapore")
ASKER = Asker(principal_id="u_asker", department="finance", agent_id="quote_helper")


def ceiling(
    level: BudgetLevel, subject: str, period: BudgetPeriod, ceiling_minor: int = 1000
) -> BudgetRow:
    return BudgetRow(
        level=level,
        subject=subject,
        period=period,
        ceiling_minor=ceiling_minor,
        version=1,
        author="u_setter",
        effective_from=AT - timedelta(days=400),
        reason="the test's ceiling",
    )


# ------------------------------------------------------------------------ the decisions
def test_the_keys_are_company_department_person_and_agent_in_each_rolling_period() -> None:
    """Every ceiling that could cover a question, and no per-run ceiling. Delete this and a
    department's budget can be left out of the keys, so it never stops anybody."""
    keys = keys_for(ASKER, ["acme"])
    places = {(level, subject) for level, subject, _ in keys}
    assert places == {
        (BudgetLevel.COMPANY, "acme"),
        (BudgetLevel.DEPARTMENT, "finance"),
        (BudgetLevel.USER, "u_asker"),
        (BudgetLevel.AGENT, "quote_helper"),
    }
    assert {period for _, _, period in keys} == {BudgetPeriod.DAY, BudgetPeriod.MONTH}
    lone = keys_for(Asker(principal_id="u_lone"), [])
    assert {(level, subject) for level, subject, _ in lone} == {(BudgetLevel.USER, "u_lone")}


def test_a_budget_is_used_up_when_its_spend_reaches_the_ceiling_and_not_before() -> None:
    """Spend at the ceiling has used it up; a minor unit under it has not. Delete this and a
    budget stops one question early or one late, which on a monthly budget is a day of questions."""
    month = ceiling(BudgetLevel.DEPARTMENT, "finance", BudgetPeriod.MONTH)
    assert used_up([Allowance(row=month, spent_minor=999)]) is None
    reached = used_up([Allowance(row=month, spent_minor=1000)])
    assert reached is not None and reached.row == month


def test_of_two_used_up_budgets_the_widest_is_the_one_that_binds() -> None:
    """Both run out and the department's binds rather than the person's, because relieving the
    person changes nothing while the department is out. Delete this and the warning goes to the
    person who cannot fix it."""
    person = Allowance(
        row=ceiling(BudgetLevel.USER, "u_asker", BudgetPeriod.MONTH), spent_minor=1000
    )
    department = Allowance(
        row=ceiling(BudgetLevel.DEPARTMENT, "finance", BudgetPeriod.MONTH), spent_minor=1000
    )
    binding = used_up([person, department])
    assert binding is not None and binding.row.level is BudgetLevel.DEPARTMENT


def test_a_budget_admin_is_matched_by_the_place_the_budget_belongs_to() -> None:
    """A department's budget is warned to whoever holds the authority over that department or
    everything, a person's to whoever holds it over their department, the company's to whoever
    holds it over everything. Delete this and a warning reaches another department's admin."""
    grants = [
        ("u_finance_admin", Scope.department("finance")),
        ("u_sales_admin", Scope.department("sales")),
        ("u_owner", Scope.unrestricted()),
    ]
    department = place_of(BudgetLevel.DEPARTMENT, "finance", ASKER)
    assert holding_over(grants, department) == ["u_finance_admin", "u_owner"]
    person = place_of(BudgetLevel.USER, "u_asker", ASKER)
    assert holding_over(grants, person) == ["u_finance_admin", "u_owner"]
    assert holding_over(grants, place_of(BudgetLevel.COMPANY, "acme", ASKER)) == ["u_owner"]
    assert holding_over(grants, place_of(BudgetLevel.AGENT, "quote_helper", ASKER)) == ["u_owner"]


def test_the_spend_and_the_stop_cover_one_period_in_the_installs_zone() -> None:
    """A month in Singapore begins and ends at local midnight on the first, and the spend's window
    starts where the stop's previous period would have ended. Delete this and a monthly budget is
    summed over a month eight hours away from the one it stops."""
    begins = period_start(BudgetPeriod.MONTH, AT, zone=ZONE)
    ends = next_period_start(BudgetPeriod.MONTH, AT, zone=ZONE)
    assert (begins.year, begins.month, begins.day, begins.hour) == (2999, 3, 1, 0)
    assert (ends.year, ends.month, ends.day, ends.hour) == (2999, 4, 1, 0)
    assert begins.utcoffset() == ends.utcoffset() == timedelta(hours=8)
    assert (
        next_period_start(BudgetPeriod.MONTH, begins - timedelta(microseconds=1), zone=ZONE)
        == begins
    )


def test_the_person_refused_is_told_no_figure_no_person_and_no_other_budget() -> None:
    """The sentence holds no number, no id and no level's name beyond "spending limit". Delete this
    and a refusal can carry what is left, which two refusals subtract into everybody else's
    spend."""
    assert not re.search(r"\d", SPENDING_LIMIT_REACHED)
    for word in ("department", "company", "agent", "u_", "XXX"):
        assert word not in SPENDING_LIMIT_REACHED
    assert "spending limit" in SPENDING_LIMIT_REACHED


# ------------------------------------------------------------------- the orchestration
class Reads:
    """The store's reads and its write, over values a test sets, noting what was recorded."""

    def __init__(
        self,
        allowances: list[Allowance],
        recorded: list[tuple[Stop, bool]] | None = None,
        grants: list[tuple[str, Scope]] | None = None,
    ) -> None:
        self.allowances = allowances
        self.recorded = recorded or []
        self.grants = grants or []
        self.written: list[tuple[Any, bool]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def allowances_for(*args: Any, **kwargs: Any) -> list[Allowance]:
            return self.allowances

        async def recorded_stops(*args: Any, **kwargs: Any) -> list[tuple[Stop, bool]]:
            return self.recorded

        async def budget_admins(*args: Any, **kwargs: Any) -> list[tuple[str, Scope]]:
            return self.grants

        async def record(session: Any, consequence: Any, *, enforced: bool, **kwargs: Any) -> None:
            self.written.append((consequence, enforced))

        monkeypatch.setattr(store, "allowances_for", allowances_for)
        monkeypatch.setattr(store, "recorded_stops", recorded_stops)
        monkeypatch.setattr(store, "budget_admins", budget_admins)
        monkeypatch.setattr(store, "record", record)


def ask(enforce: bool) -> bool:
    return asyncio.run(
        judged(None, ASKER, at=AT, zone=ZONE, enforce=enforce, trace_id="t-1")  # type: ignore[arg-type]
    )


def out_of_money() -> list[Allowance]:
    return [
        Allowance(
            row=ceiling(BudgetLevel.DEPARTMENT, "finance", BudgetPeriod.MONTH), spent_minor=1000
        )
    ]


def test_while_off_a_used_up_budget_is_recorded_as_one_that_would_have_stopped_and_answered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The switch's off half.** The budget is found, warned about and recorded with `enforced`
    false, and the question is answered. Delete this and the evidence the owner decides the switch
    on is never written, or the install starts refusing before anybody switched it on."""
    reads = Reads(out_of_money(), grants=[("u_finance_admin", Scope.department("finance"))])
    reads.install(monkeypatch)
    assert ask(enforce=False) is False
    [(consequence, enforced)] = reads.written
    assert enforced is False
    assert consequence.stop.key == (BudgetLevel.DEPARTMENT, "finance", BudgetPeriod.MONTH)
    assert consequence.stop.until == next_period_start(BudgetPeriod.MONTH, AT, zone=ZONE)
    assert (consequence.notice.addressing, consequence.notice.to) == (
        Addressing.OWN_ADMIN,
        ("u_finance_admin",),
    )


def test_while_on_a_used_up_budget_is_recorded_enforced_and_the_question_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The switch's on half.** The first question to find the budget used up opens the stop and
    is refused. Delete this and enforcement switched on stops nothing."""
    reads = Reads(out_of_money())
    reads.install(monkeypatch)
    assert ask(enforce=True) is True
    [(consequence, enforced)] = reads.written
    assert enforced is True
    assert consequence.notice.addressing is Addressing.UNADDRESSED


def test_a_stop_in_force_refuses_while_on_and_is_recorded_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stop already recorded this period refuses the next question and writes nothing more.
    Delete this and every refused question writes another stop, or a stop stops refusing."""
    until = next_period_start(BudgetPeriod.MONTH, AT, zone=ZONE)
    stop = Stop(
        level=BudgetLevel.DEPARTMENT,
        subject="finance",
        period=BudgetPeriod.MONTH,
        since=AT - timedelta(days=2),
        until=until,
    )
    reads = Reads(out_of_money(), recorded=[(stop, True)])
    reads.install(monkeypatch)
    assert ask(enforce=True) is True
    assert reads.written == []


def test_a_stop_opened_while_on_refuses_nothing_once_the_switch_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stop enforced earlier in the period, and the switch then turned off: the question is
    answered. Delete this and turning enforcement off does not lift the stops it opened, which is
    a switch that only works in one direction."""
    until = next_period_start(BudgetPeriod.MONTH, AT, zone=ZONE)
    stop = Stop(
        level=BudgetLevel.DEPARTMENT,
        subject="finance",
        period=BudgetPeriod.MONTH,
        since=AT - timedelta(days=2),
        until=until,
    )
    reads = Reads(out_of_money(), recorded=[(stop, True)])
    reads.install(monkeypatch)
    assert ask(enforce=False) is False


def test_a_budget_already_said_this_period_is_not_said_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """While off, a budget recorded as one that would have stopped is not recorded again for the
    next question. Delete this and the evidence counts questions rather than budgets."""
    until = next_period_start(BudgetPeriod.MONTH, AT, zone=ZONE)
    stop = Stop(
        level=BudgetLevel.DEPARTMENT,
        subject="finance",
        period=BudgetPeriod.MONTH,
        since=AT - timedelta(days=2),
        until=until,
    )
    reads = Reads(out_of_money(), recorded=[(stop, False)])
    reads.install(monkeypatch)
    assert ask(enforce=False) is False
    assert reads.written == []


def test_a_budget_with_room_left_neither_stops_nor_records(monkeypatch: pytest.MonkeyPatch) -> None:
    """The positive sibling: spend under the ceiling answers and writes nothing, switch on or off.
    Delete this and a guard refusing everything passes every test above."""
    for enforce in (True, False):
        reads = Reads(
            [
                Allowance(
                    row=ceiling(BudgetLevel.DEPARTMENT, "finance", BudgetPeriod.MONTH),
                    spent_minor=10,
                )
            ]
        )
        reads.install(monkeypatch)
        assert ask(enforce=enforce) is False
        assert reads.written == []


class Broken:
    """A session factory whose sessions fail as soon as they are entered."""

    def __call__(self) -> Any:
        raise OSError("the database is not answering")


def test_a_budget_store_that_cannot_be_read_answers_the_question() -> None:
    """**The fail-safe.** `BUDGET_ENFORCEMENT_FAILS_SAFE_FOR_THE_ASKER`: whatever stops the budget
    being judged, the question is answered, and a process with no database is answered too.
    Delete this and a database fault becomes an outage of every question."""
    assert "answered" in BUDGET_ENFORCEMENT_FAILS_SAFE_FOR_THE_ASKER
    broken: Any = Broken()
    assert asyncio.run(budget_refusal_for(broken, ASKER, at=AT, trace_id="t-1")) is None
    assert asyncio.run(budget_refusal_for(None, ASKER, at=AT, trace_id="t-1")) is None


# --------------------------------------------------------------------- on PostgreSQL
def _as_app[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = create_async_engine(
            normalise_database_url(url),
            poolclass=NullPool,
            connect_args={"options": "-c role=brain_app"},
        )
        try:
            return await work(async_sessionmaker(engine, class_=AsyncSession))
        finally:
            await engine.dispose()

    if os.name == "nt":
        return asyncio.run(go(), loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(go())


async def _ceiling_and_spend(sessions: async_sessionmaker[AsyncSession], spent: int) -> None:
    """A month's ceiling for finance through the store, and spend against it in the ledger."""
    from brain.ops.budget_store import append
    from brain.tables.spend import SpendActualRow

    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        await append(
            session,
            BudgetRow(
                level=BudgetLevel.DEPARTMENT,
                subject="finance",
                period=BudgetPeriod.MONTH,
                ceiling_minor=1000,
                version=1,
                author="u_setter",
                effective_from=now - timedelta(days=400),
                reason="the test's ceiling",
            ),
            ent_hash="hash",
            trace_id="t-setter",
        )
        await session.execute(
            sa.insert(SpendActualRow).values(
                principal_id="u_asker",
                principal_kind="human",
                traffic="human_interactive",
                department="finance",
                agent_id=None,
                model="m",
                lane="answer",
                cost_minor=spent,
                at=now - timedelta(seconds=5),
                trace_id="t-spend",
            )
        )


async def _stops(sessions: async_sessionmaker[AsyncSession]) -> list[tuple[str, bool, str]]:
    async with sessions() as session, session.begin():
        from brain.tables.budget_stop import BudgetStopRow

        found = await session.execute(
            sa.select(BudgetStopRow.subject, BudgetStopRow.enforced, BudgetStopRow.principal_id)
        )
        return [tuple(row) for row in found]


@pytest.mark.needs_db
def test_on_postgres_a_used_up_budget_is_said_once_while_off_and_stops_once_switched_on() -> None:
    """**The store end to end.** A department's monthly ceiling, spend reaching it, and two
    questions while the switch is off: both answered, one row saying it would have stopped. Then
    the switch on: refused, and one enforced row beside it. Delete this and the policy, the unique
    key or the switch's read can be wrong with every value-level test green."""
    from tests.unit.test_acceptance import at_head

    with at_head("brain_budget_stop_store") as url:

        async def work(sessions: async_sessionmaker[AsyncSession]) -> Any:
            from brain.ops.features import BUDGET_ENFORCEMENT, switch

            await _ceiling_and_spend(sessions, 1000)
            asker = Asker(principal_id="u_asker", department="finance")
            now = datetime.now(UTC)
            off = [
                await budget_refusal_for(sessions, asker, at=now, trace_id=f"t-{n}")
                for n in range(2)
            ]
            said = await _stops(sessions)
            async with sessions() as session, session.begin():
                await switch(session, BUDGET_ENFORCEMENT, on=True, by="u_owner")
            on = await budget_refusal_for(sessions, asker, at=datetime.now(UTC), trace_id="t-3")
            return off, said, on, await _stops(sessions)

        off, said, on, after = _as_app(url, work)

    assert off == [None, None]
    assert said == [("finance", False, "u_asker")]
    assert on == SPENDING_LIMIT_REACHED
    assert sorted(after) == [("finance", False, "u_asker"), ("finance", True, "u_asker")]


@pytest.mark.needs_db
def test_on_postgres_a_budget_with_room_left_answers_and_records_nothing() -> None:
    """The positive sibling against the real tables: spend under the ceiling, the switch on, the
    question answered and no row written. Delete this and a store refusing everybody passes the
    test above."""
    from tests.unit.test_acceptance import at_head

    with at_head("brain_budget_stop_room") as url:

        async def work(sessions: async_sessionmaker[AsyncSession]) -> Any:
            from brain.ops.features import BUDGET_ENFORCEMENT, switch

            await _ceiling_and_spend(sessions, 10)
            async with sessions() as session, session.begin():
                await switch(session, BUDGET_ENFORCEMENT, on=True, by="u_owner")
            told = await budget_refusal_for(
                sessions,
                Asker(principal_id="u_asker", department="finance"),
                at=datetime.now(UTC),
                trace_id="t-1",
            )
            return told, await _stops(sessions)

        told, stops = _as_app(url, work)

    assert (told, stops) == (None, [])


# ------------------------------------------------------------------------- on the request path
def test_a_question_a_budget_stops_is_turned_away_with_the_sentence_before_any_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`answered_for` asks the budget after the halt and before any lane, and a refusal reaches the
    asker as a halt does, with the one sentence. Delete this and the store can decide a stop that
    nothing on the request path ever asks about, which is where this code was until 2026-10-06."""
    from types import SimpleNamespace

    from fastapi import FastAPI
    from starlette.requests import Request

    from brain import api_routes
    from brain.api_routes import Answering, BudgetStopped, Halted, Question, answered_for
    from brain.gate.context import Channel
    from brain.tools.registry import ToolRegistry

    asked: list[Asker] = []

    async def nothing_halted(*args: Any) -> str:
        return ""

    async def stopped(sessions: Any, asker: Asker, **kwargs: Any) -> str:
        asked.append(asker)
        return SPENDING_LIMIT_REACHED

    monkeypatch.setattr(api_routes, "refusal_for", nothing_halted)
    monkeypatch.setattr(api_routes, "budget_refusal_for", stopped)
    app = FastAPI()
    app.state.tools = ToolRegistry()
    request = Request({"type": "http", "app": app, "headers": [], "method": "POST"})
    person: Any = SimpleNamespace(id="u_asker", primary_department="finance")
    outcome = asyncio.run(
        answered_for(
            request,
            None,  # type: ignore[arg-type]
            Answering(
                principal=person,
                reach=None,  # type: ignore[arg-type]
                channel=Channel.CONSOLE,
                now=AT,
            ),
            Question(question="what did we sell", agent="quote_helper"),
        )
    )
    assert isinstance(outcome, BudgetStopped) and isinstance(outcome, Halted)
    assert outcome.told == SPENDING_LIMIT_REACHED
    assert asked == [Asker(principal_id="u_asker", department="finance", agent_id="quote_helper")]
