"""A budget's administrators are told when it nears its ceiling and when it has run out, once each.

The pure half holds the sentences, the keys and the fraction a spend has reached. The sending half
drives `brain.budget_told.tell_budget_administrators` with the sender and the two switches replaced
by fakes that keep what they were asked, so a second pass is seen to send nothing. The database
half reads real budgets, real spend and real grants and shows who is found to be told. Dates are
far outside any wall clock, because none of this is about the present.

Task ids: M21.1.1, M21.2.5
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from brain import budget_told as told_module
from brain.budget_told import (
    NEARING_KEY,
    TELL_EVERY,
    USED_UP_KEY,
    WARNED_LEVELS,
    Nearing,
    UsedUp,
    highest_reached,
    nearing_budgets,
    nearing_ref,
    nearing_text,
    percent,
    tell_budget_administrators,
    used_up_budgets,
    used_up_ref,
    used_up_text,
    whose,
)
from brain.db import normalise_database_url
from brain.ops.budgets import BudgetLevel, BudgetPeriod, BudgetRow
from brain.ops.notices import NoticeKind, notice
from brain.tables.channel import DeliveryOutcome

AT = datetime(2999, 3, 15, 10, 0, tzinfo=UTC)
ZONE = ZoneInfo("Asia/Singapore")
SRC = Path(told_module.__file__).parent


def near(
    fraction: float = 0.7,
    *,
    level: BudgetLevel = BudgetLevel.DEPARTMENT,
    subject: str = "finance",
    period: BudgetPeriod = BudgetPeriod.MONTH,
    holders: tuple[str, ...] = ("u_head",),
) -> Nearing:
    return Nearing(
        level=level,
        subject=subject,
        period=period,
        fraction=fraction,
        began=AT - timedelta(days=14),
        holders=holders,
    )


def gone(
    *, enforced: bool = True, holders: tuple[str, ...] = ("u_head",), subject: str = "finance"
) -> UsedUp:
    return UsedUp(
        level=BudgetLevel.DEPARTMENT,
        subject=subject,
        period=BudgetPeriod.MONTH,
        since=AT - timedelta(days=1),
        until=AT + timedelta(days=17),
        enforced=enforced,
        holders=holders,
    )


# ------------------------------------------------------------------------ the pure half
def test_a_spend_reports_the_highest_warning_fraction_it_has_reached_and_none_when_spent() -> None:
    """Under the first fraction nothing; between the two the first; past both the second; and at the
    ceiling nothing, because a budget with no headroom is at its ceiling and the stop tells about
    that. Delete this and a jump past two fractions tells about both, or a spent budget is told as
    'nearing' as well as 'run out'."""
    fractions = (0.7, 0.9)
    assert highest_reached(fractions, 600, 1000) is None
    assert highest_reached(fractions, 700, 1000) == 0.7
    assert highest_reached(fractions, 899, 1000) == 0.7
    assert highest_reached(fractions, 950, 1000) == 0.9
    assert highest_reached(fractions, 1000, 1000) is None
    assert highest_reached((), 950, 1000) is None


def test_the_message_names_the_budget_and_a_share_and_never_an_amount() -> None:
    """Whatever the ceiling and the spend, the sentence carries the owner of the budget, its period
    and a per cent, and no other number. Delete this and a warning forwarded out of the chat tells
    a stranger how much a department is allowed to spend."""
    text = nearing_text(near(0.9, subject="finance"), link="")
    assert "finance department" in text and "monthly" in text and "90%" in text
    assert re.sub(r"90%", "", text).count("0") == 0 and not re.search(
        r"\d", text.replace("90%", "")
    )
    company = nearing_text(near(0.7, level=BudgetLevel.COMPANY, subject="c_1"), link="")
    assert "the company" in company and "c_1" not in company and "70%" in company


def test_a_used_up_budget_says_whether_questions_are_being_refused_for_it() -> None:
    """An enforced stop says questions are refused until the period ends; one that is only said
    tells the administrator questions are still answered because limits are not enforced. Delete
    this and an administrator is told a budget ran out and then finds people still answered."""
    on = used_up_text(gone(enforced=True), zone=ZONE, link="")
    off = used_up_text(gone(enforced=False), zone=ZONE, link="")
    assert "refused until" in on and "not being enforced" not in on
    assert "still being answered" in off and "not being enforced" in off
    assert "refused" not in off
    assert "2999" in on and "2999" in off


def test_a_link_follows_the_sentence_only_when_the_install_has_an_address() -> None:
    """The console link is appended when there is one and absent when there is not. Delete this and
    a message on an install with no address ends on a dangling colon."""
    assert nearing_text(near(), link="").endswith("ceiling.")
    assert nearing_text(near(), link="https://brain.test/company/consumption").endswith(
        "https://brain.test/company/consumption"
    )


def test_a_percent_is_the_whole_number_a_person_reads() -> None:
    """Seventy per cent is '70%', not '0.7%' and not '70.0%'. Delete this and a warning reads as
    a fraction of a per cent."""
    assert (percent(0.7), percent(0.9), percent(0.75)) == ("70%", "90%", "75%")


def test_each_fraction_of_each_period_of_each_budget_is_its_own_key() -> None:
    """Two fractions, two budgets, two periods and two period starts each give their own key, so
    each is told once and none is hidden by another; and the key for a stop and for a warning
    cannot be confused. Delete this and a second month's warning is swallowed by the first's."""
    base = near(0.7)
    refs = {
        nearing_ref(base),
        nearing_ref(near(0.9)),
        nearing_ref(near(0.7, subject="web")),
        nearing_ref(near(0.7, period=BudgetPeriod.DAY)),
        nearing_ref(
            Nearing(
                base.level,
                base.subject,
                base.period,
                base.fraction,
                base.began - timedelta(days=31),
                (),
            )
        ),
    }
    assert len(refs) == 5
    assert all(one.startswith(NEARING_KEY) for one in refs)
    assert used_up_ref(gone()).startswith(USED_UP_KEY)
    assert used_up_ref(gone()) not in refs
    assert used_up_ref(gone()) != used_up_ref(gone(subject="web"))


def test_only_company_and_department_budgets_warn_here() -> None:
    """A person's allowance and an agent's ceiling are told in the sentence the person is refused
    with, not to an administrator. Delete this and a hundred allowances each message a department
    head."""
    assert set(WARNED_LEVELS) == {BudgetLevel.COMPANY, BudgetLevel.DEPARTMENT}
    assert whose(BudgetLevel.COMPANY, "c_1") == "the company"
    assert whose(BudgetLevel.DEPARTMENT, "web") == "the web department"


def test_the_loop_asks_often_enough_to_be_prompt_and_not_so_often_as_to_be_a_poll() -> None:
    """A quarter of an hour. Delete this and the loop becomes a poll or a daily digest."""
    assert timedelta(minutes=5) <= TELL_EVERY <= timedelta(hours=1)


# ------------------------------------------------------------------------ the sending half
@dataclass
class Sessions:
    async def __aenter__(self) -> Sessions:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def __call__(self) -> Sessions:
        return self


@dataclass
class Sent:
    outcome: DeliveryOutcome
    issued: bool


@dataclass
class Teller:
    """`brain.tell_later.tell` in memory, with the operation ledger's rule: a key already sent is
    handed back its first record and issues nothing."""

    told: list[tuple[str, str, str]] = field(default_factory=list)
    kinds: list[Any] = field(default_factory=list)
    keys: set[tuple[str, str]] = field(default_factory=set)
    unaddressed: set[str] = field(default_factory=set)

    async def __call__(
        self,
        request: Any,
        person: str,
        said: str,
        *,
        intent_ref: str,
        now: datetime,
        kind: Any = None,
    ) -> Sent | None:
        self.kinds.append(kind)
        if person in self.unaddressed:
            return None
        first = (person, intent_ref) not in self.keys
        self.keys.add((person, intent_ref))
        if first:
            self.told.append((person, said, intent_ref))
        return Sent(DeliveryOutcome.SENT, issued=first)


def world(
    monkeypatch: pytest.MonkeyPatch,
    *,
    feature: bool = True,
    off: frozenset[NoticeKind] = frozenset(),
) -> Teller:
    teller = Teller()

    async def switched(_: Any) -> bool:
        return feature

    async def notice_switched(session: Any, kind: NoticeKind) -> bool:
        return kind not in off

    monkeypatch.setattr(told_module, "budget_warnings_are_on", switched)
    monkeypatch.setattr(told_module, "notice_is_on", notice_switched)
    monkeypatch.setattr(told_module, "tell", teller)
    return teller


def run_pass(nearing: list[Nearing], used_up: list[UsedUp]) -> told_module.Told:
    return asyncio.run(
        tell_budget_administrators(
            None,  # type: ignore[arg-type]
            Sessions(),  # type: ignore[arg-type]
            now=AT,
            zone=ZONE,
            nearing=nearing,
            used_up=used_up,
        )
    )


def test_each_administrator_is_told_once_about_a_warning_and_once_about_a_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The positive case, and once.** Two administrators of a department each get the warning and
    the stop; a second pass over the same budget sends nothing and counts nothing. Delete this and
    the loop tells nobody while it reads on, or tells them every quarter of an hour."""
    teller = world(monkeypatch)
    nearing, stops = [near(holders=("u_head", "u_deputy"))], [gone(holders=("u_head", "u_deputy"))]

    first = run_pass(nearing, stops)
    second = run_pass(nearing, stops)

    assert (first.nearing, first.used_up) == (2, 2)
    assert (second.nearing, second.used_up) == (0, 0)
    assert sorted(person for person, _, _ in teller.told) == [
        "u_deputy",
        "u_deputy",
        "u_head",
        "u_head",
    ]
    assert set(teller.kinds) == {None}


def test_a_warning_goes_to_nobody_when_nobody_holds_the_authority() -> None:
    """A budget nobody administers produces no message, which is what the stop's `unaddressed`
    records. Delete this and an empty list of holders is read as everybody."""
    assert near(holders=()).holders == ()


def test_a_second_fraction_in_the_same_period_is_a_second_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Seventy per cent, then ninety in the same month, are two messages to the same person; the
    same fraction again is not a third. Delete this and the ninety per cent warning, which is the
    one that matters, is swallowed by the seventy."""
    teller = world(monkeypatch)
    run_pass([near(0.7)], [])
    run_pass([near(0.7)], [])
    after = run_pass([near(0.9)], [])
    assert (after.nearing, len(teller.told)) == (1, 2)


def test_a_person_with_no_chat_address_is_not_counted_as_told(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sender hands back nothing for a person with no address, which is not a delivered
    message. Delete this and the log says a warning was told that reached nobody."""
    teller = world(monkeypatch)
    teller.unaddressed.add("u_head")
    assert run_pass([near()], [gone()]) == told_module.Told(nearing=0, used_up=0)


def test_a_switched_off_feature_sends_nothing_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the feature off, no message is sent for either. Delete this and the switch the Features
    page offers stops nothing."""
    teller = world(monkeypatch, feature=False)
    told = run_pass([near()], [gone()])
    assert told == told_module.Told(switched_off=True)
    assert teller.told == []


def test_each_notice_has_its_own_switch_and_only_its_own_message_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Switching the 'nearing' notice off stops warnings and leaves the stop told, and the other
    way round. Delete this and one switch silences both, or neither."""
    teller = world(monkeypatch, off=frozenset({NoticeKind.BUDGET_NEARING}))
    only_stop = run_pass([near()], [gone()])
    assert (only_stop.nearing, only_stop.used_up) == (0, 1)
    teller2 = world(monkeypatch, off=frozenset({NoticeKind.BUDGET_STOPPED}))
    only_warning = run_pass([near()], [gone()])
    assert (only_warning.nearing, only_warning.used_up) == (1, 0)
    assert len(teller.told) == 1 and len(teller2.told) == 1


def test_the_notices_page_says_both_are_sent_by_this_function_and_can_be_switched() -> None:
    """The two rows name this sender, are switchable, and no longer say no channel sends them.
    Delete this and the page keeps saying nothing sends a budget warning."""
    for kind in (NoticeKind.BUDGET_STOPPED, NoticeKind.BUDGET_NEARING):
        row = notice(kind.value)
        assert row.sent_by == "brain.budget_told:tell_budget_administrators"
        assert row.switchable
        assert "no channel" not in row.how.lower()


def test_the_feature_ships_off_and_names_the_function_that_asks() -> None:
    """The feature is declared with its reader. Delete this and the loop is gated by a switch the
    Features screen does not list."""
    from brain.ops.features import FEATURES
    from brain.ops.features_declared.budget_warnings_told import BUDGET_WARNINGS_TOLD

    assert BUDGET_WARNINGS_TOLD in FEATURES
    assert BUDGET_WARNINGS_TOLD.read_by == ("brain.budget_told:budget_warnings_are_on",)


def test_the_sender_is_the_one_later_sender_and_the_worker_sends_nothing() -> None:
    """The web process tells: this module sends through `brain.tell_later.tell` alone, and the
    worker's modules import neither it nor that. Delete this and a second path to a chat appears
    beside the one that re-checks reach, or the worker starts needing the channels' tokens."""
    told = ast.parse((SRC / "budget_told.py").read_text(encoding="utf-8"))
    imported = {
        (node.module, alias.name)
        for node in ast.walk(told)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert ("brain.tell_later", "tell") in imported
    assert not any(module == "brain.channels.outbound" for module, _ in imported)
    for worker in ("ops/worker.py", "ops/schedule_runner.py", "ops/schedule_store.py"):
        text = (SRC / worker).read_text(encoding="utf-8")
        assert "budget_told" not in text and "tell_later" not in text, worker


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


def _administrators(url: str, only: tuple[str, ...] | None = None) -> None:
    """Three people who hold the budget authority: a head of finance, a head of web and a person
    who holds it over everything. Written as the superuser, which the grant trigger allows."""
    from tests.fixtures.scratch_postgres import sql

    for who, scope in (
        ("u_head", '{"clauses": [{"field": "department", "op": "eq", "value": "finance"}]}'),
        ("u_root", '{"clauses": []}'),
        ("u_web", '{"clauses": [{"field": "department", "op": "eq", "value": "web"}]}'),
    ):
        if only is not None and who not in only:
            continue
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name)"
            " VALUES (%s, 'human', 'staff', %s)",
            who,
            who,
        )
        sql(
            url,
            "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by,"
            " reason) VALUES (%s, 'admin:budget', %s, 'u_seed', 'the test''s administrator')",
            who,
            scope,
        )


async def _seed(sessions: async_sessionmaker[AsyncSession], spent: int, now: datetime) -> None:
    """Finance's monthly budget of 1000 warning at 70 and 90, the spend so far, and who administers
    it: a head of finance, and a person who administers everything."""
    from brain.ops.budget_store import append
    from brain.tables.spend import SpendActualRow

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
                alert_fractions=(0.7, 0.9),
            ),
            ent_hash="0" * 32,
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


@pytest.mark.needs_db
def test_on_postgres_a_department_over_seventy_per_cent_is_found_with_its_administrators() -> None:
    """**Found from the real tables.** Finance has spent 800 of 1000 this month, warning at 70 and
    90: it is found nearing at 0.7, told to the head of finance and the administrator over
    everything, and not to the head of web. Delete this and the read can find nobody, or find a
    department's administrators among another's."""
    from tests.unit.test_acceptance import at_head

    with at_head("brain_budget_told_near") as url:
        _administrators(url)

        async def work(sessions: async_sessionmaker[AsyncSession]) -> tuple[Nearing, ...]:
            now = datetime.now(UTC)
            await _seed(sessions, 800, now)
            async with sessions() as session, session.begin():
                return await nearing_budgets(session, now=now, zone=ZONE)

        found = _as_app(url, work)

    assert [(one.level, one.subject, one.period, one.fraction) for one in found] == [
        (BudgetLevel.DEPARTMENT, "finance", BudgetPeriod.MONTH, 0.7)
    ]
    assert set(found[0].holders) == {"u_head", "u_root"}


@pytest.mark.needs_db
def test_on_postgres_a_department_with_no_administrator_goes_to_the_company_wide_one() -> None:
    """Finance has spent 800 of 1000 and only the head of web and the administrator over everything
    hold the authority. It is found nearing, to the administrator over everything and not to the
    head of web. Delete this and a department with no administrator of its own is warned to
    nobody, which is a warning that exists on the screen and reaches no one."""
    from tests.unit.test_acceptance import at_head

    with at_head("brain_budget_told_escalated") as url:
        _administrators(url, only=("u_root", "u_web"))

        async def work(sessions: async_sessionmaker[AsyncSession]) -> tuple[Nearing, ...]:
            now = datetime.now(UTC)
            await _seed(sessions, 800, now)
            async with sessions() as session, session.begin():
                return await nearing_budgets(session, now=now, zone=ZONE)

        found = _as_app(url, work)

    assert [one.holders for one in found] == [("u_root",)]


@pytest.mark.needs_db
def test_on_postgres_the_higher_fraction_wins_and_a_spent_budget_is_not_nearing() -> None:
    """Spend of 950 is found at 0.9 and not also at 0.7; spend of 1000 is found at nothing, and
    spend of 100 at nothing. Delete this and the real read tells twice or tells a spent budget it
    is nearing."""
    from tests.unit.test_acceptance import at_head

    outcomes: dict[int, list[float]] = {}
    for spent in (100, 950, 1000):
        with at_head(f"brain_budget_told_{spent}") as url:
            _administrators(url)

            async def work(
                sessions: async_sessionmaker[AsyncSession], spent: int = spent
            ) -> tuple[Nearing, ...]:
                now = datetime.now(UTC)
                await _seed(sessions, spent, now)
                async with sessions() as session, session.begin():
                    return await nearing_budgets(session, now=now, zone=ZONE)

            outcomes[spent] = [one.fraction for one in _as_app(url, work)]
    assert outcomes == {100: [], 950: [0.9], 1000: []}


@pytest.mark.needs_db
def test_on_postgres_a_recorded_stop_is_found_with_who_it_was_addressed_to() -> None:
    """A stop the question path recorded, in its period, is read back with its addressed
    principals and whether it was enforced; one whose period has ended is not. Delete this and the
    read tells about last month's stop, or tells nobody."""
    from brain.tables.budget_stop import BudgetStopRow
    from tests.unit.test_acceptance import at_head

    with at_head("brain_budget_told_stop") as url:

        async def work(sessions: async_sessionmaker[AsyncSession]) -> tuple[UsedUp, ...]:
            now = datetime.now(UTC)
            async with sessions() as session, session.begin():
                await session.execute(
                    sa.text("SELECT set_config('app.principal_id', 'u_asker', true)")
                )
                for subject, until, to in (
                    ("finance", now + timedelta(days=10), ["u_head"]),
                    ("web", now - timedelta(days=1), ["u_web"]),
                ):
                    await session.execute(
                        sa.insert(BudgetStopRow).values(
                            level="department",
                            subject=subject,
                            period="month",
                            since=until - timedelta(days=30),
                            until=until,
                            enforced=True,
                            addressing="own_admin",
                            addressed_to=to,
                            principal_id="u_asker",
                            trace_id="t-stop",
                        )
                    )
            async with sessions() as session, session.begin():
                return await used_up_budgets(session, now=now)

        found = _as_app(url, work)

    assert [(one.subject, one.holders, one.enforced) for one in found] == [
        ("finance", ("u_head",), True)
    ]
