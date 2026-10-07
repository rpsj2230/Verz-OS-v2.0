"""The scheduled thirty-day review: what it decides, what it refuses to, and what it writes.

The decision is `brain.agents.supervision.review`, which has its own tests. What is held here is
the second caller: that it finds due pins and no others, asks the one function the Review button
asks, writes under the system's name only with the switch on, and never writes `eligible` for a
date.

Dates are fixed in 2019 and passed in as `now`, for the reason `CLAUDE.md` gives about a fixture
with a date in it: nothing here is about the present, so no wall clock may cross it.

Task ids: M13.5.18, M39.8.2
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import inspect
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from brain.agents.supervision import (
    MINIMUM_REVIEWED_ACTIONS,
    SHADOW_REVIEW_PERIOD,
    ShadowPin,
    ShadowReview,
)
from brain.audit.record import ApprovalVerdict
from brain.gate.injection import AutonomyTier
from brain.gate.leash import ActionRecord, Route
from brain.ops import supervision_review as sr
from brain.ops.controls import control
from brain.ops.leash_store import LeashState, PinState
from brain.ops.supervision_review import (
    NO_REACH,
    REVIEW_EVERY,
    SYSTEM_REVIEWER,
    Answer,
    Refusal,
    ReviewRun,
    StoredReviews,
    SupervisionReviewError,
    answer_review,
    run_supervision_review,
)
from brain.tables.leash import PinOutcome

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
T0 = datetime(2019, 3, 1, 12, 0, tzinfo=UTC)
#: One day past the first review date of a pin made at `T0`.
NOW = T0 + SHADOW_REVIEW_PERIOD + timedelta(days=1)

TARGET = "invoice.chase"
PRINCIPAL_ID = r"^[A-Za-z0-9_.@-]{1,128}$"


def state(
    agent: str,
    *,
    pinned_at: datetime = T0,
    outcome: PinOutcome = PinOutcome.PINNED,
    simulated: int = MINIMUM_REVIEWED_ACTIONS,
    approved: int = 0,
    amended: int = 0,
) -> LeashState:
    """One agent's stored state: a pin, shadow actions, and verdicts on the first few of them."""
    actions = tuple(
        ActionRecord(
            trace_id=f"t{n}",
            agent_id=agent,
            tool_name=TARGET,
            target=TARGET,
            principal_id="u_asker",
            ent_hash="0" * 32,
            action_digest=hashlib.sha256(f"{agent}-{n}".encode()).hexdigest(),
            route=Route.SIMULATE,
            tier=AutonomyTier.SHADOW,
            at=pinned_at + timedelta(days=1),
        )
        for n in range(simulated)
    )
    verdicts = tuple(
        ShadowReview(
            agent_id=agent,
            action_digest=one.action_digest,
            verdict=ApprovalVerdict.APPROVED if n < approved else ApprovalVerdict.AMENDED,
            reviewer_id="u_reviewer",
            at=pinned_at + timedelta(days=2),
        )
        for n, one in enumerate(actions[: approved + amended])
    )
    return LeashState(
        moves=(),
        actions=actions,
        verdicts=verdicts,
        pin=PinState(
            pin=ShadowPin(
                agent_id=agent,
                pinned_at=pinned_at,
                review_due_at=pinned_at + SHADOW_REVIEW_PERIOD,
            ),
            outcome=outcome,
            understood=None,
            reviewed=None,
            simulated=None,
            decided_at=pinned_at,
        ),
    )


class Fake:
    """`ReviewStore` over a dictionary, recording every write and optionally failing one."""

    def __init__(
        self,
        states: dict[str, LeashState],
        *,
        on: bool = True,
        fail_writing: str | None = None,
    ) -> None:
        self.states = states
        self.on = on
        self.fail_writing = fail_writing
        self.writes: list[dict[str, object]] = []

    async def switched_on(self) -> bool:
        return self.on

    async def due_agents(self, now: datetime, limit: int) -> Sequence[str]:
        # Every agent, due or not: the filter a real store applies is tested on PostgreSQL, and
        # here the decision itself has to refuse a pin whose date has not come.
        return list(self.states)[:limit]

    async def state(self, agent_id: str) -> LeashState:
        return self.states[agent_id]

    async def write_pin(
        self,
        pin: ShadowPin,
        outcome: PinOutcome,
        *,
        by: str,
        counts: tuple[int, int, int] | None,
        at: datetime,
        ent_hash: str,
        trace_id: str,
    ) -> None:
        if pin.agent_id == self.fail_writing:
            msg = "the database went away"
            raise RuntimeError(msg)
        self.writes.append(
            {
                "pin": pin,
                "outcome": outcome,
                "by": by,
                "counts": counts,
                "at": at,
                "ent_hash": ent_hash,
                "trace_id": trace_id,
            }
        )


def run(fake: Fake, *, report_only: bool = False) -> ReviewRun:
    return asyncio.run(run_supervision_review(fake, now=NOW, report_only=report_only))


# ------------------------------------------------------------ the decision, with nothing to say yes
def test_a_due_pin_nobody_reviewed_is_extended_and_never_released() -> None:
    """**Nothing is released because a date passed.** Thirty-one days in, ten simulated actions and
    no verdict on any: the pin is extended from now, keeps its start, and is written as the system.
    Delete this and the worker can mark an unreviewed agent eligible because its date came."""
    fake = Fake({"chaser": state("chaser", approved=0, amended=0)})

    ran = run(fake)

    assert [one["outcome"] for one in fake.writes] == [PinOutcome.EXTENDED]
    written = fake.writes[0]
    pin = written["pin"]
    assert isinstance(pin, ShadowPin)
    assert pin.pinned_at == T0
    assert pin.review_due_at == NOW + SHADOW_REVIEW_PERIOD
    assert written["by"] == SYSTEM_REVIEWER
    assert written["counts"] == (0, 0, MINIMUM_REVIEWED_ACTIONS)
    assert (ran.due, ran.extended, ran.eligible, ran.wrote) == (1, 1, 0, True)


def test_a_due_pin_short_of_the_bar_is_extended_with_its_counts() -> None:
    """Eight accepted of ten reviewed is eighty percent, under ninety: the pin extends and the row
    carries 8, 10 and 10. Delete this and a short confidence is released, or extended with the
    wrong counts on the row a person later reads."""
    fake = Fake({"chaser": state("chaser", approved=8, amended=2)})

    run(fake)

    assert [one["outcome"] for one in fake.writes] == [PinOutcome.EXTENDED]
    assert fake.writes[0]["counts"] == (8, 10, 10)


def test_a_due_pin_at_the_bar_is_marked_eligible_and_its_dates_do_not_move() -> None:
    """The positive sibling: nine of ten is ninety percent, so the pin is marked eligible and left
    as it is, with no new review date. Delete this and a run that extends everything passes every
    refusal test above."""
    fake = Fake({"chaser": state("chaser", approved=9, amended=1)})

    ran = run(fake)

    assert [one["outcome"] for one in fake.writes] == [PinOutcome.ELIGIBLE]
    written = fake.writes[0]
    pin = written["pin"]
    assert isinstance(pin, ShadowPin)
    assert (pin.pinned_at, pin.review_due_at) == (T0, T0 + SHADOW_REVIEW_PERIOD)
    assert written["counts"] == (9, 10, 10)
    assert written["ent_hash"] == NO_REACH
    assert (ran.extended, ran.eligible) == (0, 1)


def test_a_pin_whose_thirty_days_are_not_up_writes_nothing() -> None:
    """A pin made ten days before `NOW` is not due however good its figure: nothing is written and
    nothing is counted as due. Delete this and a run can review an agent early."""
    fake = Fake({"chaser": state("chaser", pinned_at=NOW - timedelta(days=10), approved=10)})

    ran = run(fake)

    assert fake.writes == []
    assert (ran.due, ran.held, ran.failed) == (0, 0, 0)
    assert ran.summary() == "no pin is due for review"


def test_a_pin_already_found_eligible_is_not_reviewed_again() -> None:
    """An eligible pin waits for a person to raise a rung, and the worker does not touch it: a
    second answer could only be a step back. Delete this and the daily run keeps rewriting an
    agent that is already waiting for its promotion."""
    fake = Fake({"chaser": state("chaser", outcome=PinOutcome.ELIGIBLE, approved=10)})

    ran = run(fake)

    assert fake.writes == []
    assert ran.due == 0


# ------------------------------------------------------------------------------- the switch
def test_with_the_switch_off_nothing_is_written_and_the_run_says_what_it_would_have_done() -> None:
    """Three due pins, one of each answer: switched off, no row is written and the report counts
    one eligible and two extended, in words saying nothing was written. Delete this and a new
    behaviour writes on every install the day it ships."""
    fake = Fake(
        {
            "ready": state("ready", approved=10),
            "short": state("short", approved=5, amended=5),
            "unseen": state("unseen"),
        },
        on=False,
    )

    ran = run(fake)

    assert fake.writes == []
    assert (ran.due, ran.extended, ran.eligible, ran.wrote) == (3, 2, 1, False)
    said = ran.summary()
    assert "nothing was written" in said
    assert "3 due, 2 extended, 1 eligible" in said


def test_the_same_pins_are_written_once_the_switch_is_on() -> None:
    """The positive sibling of the switch: the identical three pins, switched on, are three rows.
    Delete this and a run that never writes passes the test above."""
    fake = Fake(
        {
            "ready": state("ready", approved=10),
            "short": state("short", approved=5, amended=5),
            "unseen": state("unseen"),
        },
        on=True,
    )

    ran = run(fake)

    assert sorted(str(one["outcome"]) for one in fake.writes) == [
        "eligible",
        "extended",
        "extended",
    ]
    assert ran.wrote is True
    assert ran.summary().startswith("reviewed pins:")


def test_report_only_mode_writes_nothing_even_with_the_switch_on() -> None:
    """The schedule's report-only flag means decide and do not act. Delete this and a runner told
    to only report writes anyway, ignoring the mode it was given."""
    fake = Fake({"ready": state("ready", approved=10)}, on=True)

    ran = run(fake, report_only=True)

    assert fake.writes == []
    assert ran.wrote is False
    assert ran.eligible == 1


# ---------------------------------------------------------------------------- the refusals
def test_a_pin_whose_evidence_contradicts_itself_is_held_and_the_rest_are_still_reviewed() -> None:
    """Two different verdicts on one action cannot be turned into a figure. That agent is counted as
    held and left exactly as it was, and the other pin is reviewed. Delete this and the worker
    either picks a winner between two reviewers or stops at the first contradiction."""
    broken = state("broken", approved=10)
    second = ShadowReview(
        agent_id="broken",
        action_digest=broken.verdicts[0].action_digest,
        verdict=ApprovalVerdict.REJECTED,
        reviewer_id="u_other",
        at=T0 + timedelta(days=3),
    )
    broken = LeashState(
        moves=(),
        actions=broken.actions,
        verdicts=(*broken.verdicts, second),
        pin=broken.pin,
    )
    fake = Fake({"broken": broken, "fine": state("fine", approved=10)})

    ran = run(fake)

    assert [one["pin"].agent_id for one in fake.writes] == ["fine"]  # type: ignore[attr-defined]
    assert (ran.due, ran.held, ran.eligible) == (1, 1, 1)


def test_one_pin_that_cannot_be_written_does_not_stop_the_others_and_the_run_fails_after() -> None:
    """A write that raises is counted, the next pin is still reviewed, and the run raises at the
    end so the control's run is recorded as failed. Delete this and one bad row stops the day's
    reviews, or a run that reviewed fewer pins than it found is recorded as a success."""
    fake = Fake(
        {"bad": state("bad", approved=10), "good": state("good", approved=10)},
        fail_writing="bad",
    )

    with pytest.raises(SupervisionReviewError, match="1 pins could not be reviewed"):
        run(fake)

    assert [one["pin"].agent_id for one in fake.writes] == ["good"]  # type: ignore[attr-defined]


def test_what_a_run_says_names_no_agent() -> None:
    """The report is read by whoever reads the control runs. Delete this and an agent's name turns
    up in a sentence shown to people who were never entitled to know it exists."""
    fake = Fake({"quarterly_chaser_for_acme": state("quarterly_chaser_for_acme", approved=10)})

    ran = run(fake)

    assert "quarterly_chaser_for_acme" not in ran.summary()
    assert "acme" not in ran.summary()


# ------------------------------------------------------------- one decision, two callers
def test_answer_review_refuses_in_three_distinct_ways_and_answers_in_two() -> None:
    """The shared function directly: no pin and an eligible pin are not supervised, an early pin is
    not due, and a due one answers. Delete this and the route and the run can disagree about which
    of four states an agent is in."""
    assert answer_review(LeashState((), (), (), None), now=NOW) is Refusal.NOT_SUPERVISED
    eligible = state("a", outcome=PinOutcome.ELIGIBLE)
    assert answer_review(eligible, now=NOW) is Refusal.NOT_SUPERVISED
    early = state("a", pinned_at=NOW - timedelta(days=1))
    assert answer_review(early, now=NOW) is Refusal.NOT_DUE
    answered = answer_review(state("a", approved=10), now=NOW)
    assert isinstance(answered, Answer)
    assert answered.outcome is PinOutcome.ELIGIBLE


def _called_names(function: object) -> set[str]:
    tree = ast.parse(inspect.getsource(function))  # type: ignore[arg-type]
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_the_review_route_and_the_scheduled_run_both_call_the_one_decision() -> None:
    """Read from the source: `review_agent` and `run_supervision_review` each call `answer_review`
    by name, and the route no longer calls `review` itself. Delete this and the two callers can
    drift into two decisions, which is what a shared function exists to prevent."""
    from brain.agent_leash_routes import review_agent

    assert "answer_review" in _called_names(review_agent)
    assert "review" not in _called_names(review_agent)
    assert "answer_review" in _called_names(sr.run_supervision_review)


# ----------------------------------------------------------------------------- the constants
def test_the_system_reviewer_fits_the_principal_grammar_the_table_policy_compares() -> None:
    """`0195`'s insert policy compares `decided_by` with the session's principal, and the ledger's
    grammar is the one a principal id has. Delete this and a name with a space or a colon is
    refused by the database on the first scheduled run."""
    assert re.fullmatch(PRINCIPAL_ID, SYSTEM_REVIEWER)
    assert re.fullmatch(r"^[0-9a-f]{32}$", NO_REACH)


def test_the_system_reviewer_is_named_for_the_control_and_the_reach_is_the_ledgers_none() -> None:
    """Asserted against things outside the constants: the reviewer is the control's own name, so a
    row can be traced to what wrote it, and the reach is the ledger's value for no reach in force.
    Delete this and either constant can be changed to anything that fits its grammar, such as a
    person's id, with every other test comparing the constant with itself."""
    assert control("supervision_review").name.replace("_", "-") == SYSTEM_REVIEWER
    assert NO_REACH == "0" * 32


def test_the_control_is_owed_daily_and_names_the_cadence_it_restates() -> None:
    """The registry's `every` is a day and its `cadence_from` names this module's constant, with
    the two equal. Delete this and the schedule and the module can disagree about how often a
    thirty-day review is looked for."""
    row = control("supervision_review")
    assert row.every == REVIEW_EVERY == timedelta(days=1)
    assert row.cadence_from == "brain.ops.supervision_review:REVIEW_EVERY"
    assert REVIEW_EVERY < SHADOW_REVIEW_PERIOD


# --------------------------------------------------------------------------- PostgreSQL
def _seed(url: str) -> None:
    """Five agents against the real tables, through the store, as the application role.

    `ready`: ten reviewed and all accepted. `short`: eight of ten. `unseen`: ten simulated and no
    verdict. `early`: pinned ten days before `NOW`, so not due. `waiting`: already found eligible.
    """
    from brain.ops.leash_store import StoredLeash
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run as run_async
    from tests.unit.test_automation_owner_store import app_engine

    async def go() -> None:
        engine = app_engine(url)
        try:
            leash = StoredLeash(make_session_factory(engine))
            plans = {
                "ready": state("ready", approved=10),
                "short": state("short", approved=8, amended=2),
                "unseen": state("unseen"),
                "early": state("early", pinned_at=NOW - timedelta(days=10)),
                "waiting": state("waiting", outcome=PinOutcome.ELIGIBLE, approved=10),
            }
            for agent, planned in plans.items():
                assert planned.pin is not None
                started = planned.pin.pin
                await leash.write_pin(
                    started,
                    PinOutcome.PINNED,
                    by="u_admin",
                    counts=None,
                    at=started.pinned_at,
                    ent_hash="0" * 32,
                    trace_id=f"seed-{agent}",
                )
                for action in planned.actions:
                    assert await leash.record_action(action)
                for verdict in planned.verdicts:
                    assert await leash.give_verdict(verdict)
            waiting = plans["waiting"].pin
            assert waiting is not None
            await leash.write_pin(
                waiting.pin,
                PinOutcome.ELIGIBLE,
                by="u_admin",
                counts=(10, 10, 10),
                at=waiting.pin.review_due_at,
                ent_hash="0" * 32,
                trace_id="seed-waiting-eligible",
            )
        finally:
            await engine.dispose()

    run_async(go)


def _pin_rows(url: str) -> list[tuple[object, ...]]:
    from tests.fixtures.scratch_postgres import sql

    return sql(
        url,
        "SELECT agent_id, outcome, decided_by, understood, reviewed, simulated, pinned_at,"
        " review_due_at, decided_at FROM agent.supervision_pin ORDER BY decided_at, agent_id,"
        " outcome",
    )


def _due(url: str, limit: int) -> list[str]:
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run as run_async
    from tests.unit.test_automation_owner_store import app_engine

    async def go() -> list[str]:
        engine = app_engine(url)
        try:
            return list(await StoredReviews(make_session_factory(engine)).due_agents(NOW, limit))
        finally:
            await engine.dispose()

    return run_async(go)


def _run_as_the_worker(url: str, *, report_only: bool = False) -> str:
    from brain.ops.supervision_review import run_supervision_review_now

    return run_supervision_review_now(url, now=NOW, report_only=report_only)


def _switch_on(url: str) -> None:
    from brain.ops.features import SUPERVISION_REVIEW, switch
    from brain.session import make_session_factory
    from tests.fixtures.scratch_postgres import run as run_async
    from tests.unit.test_automation_owner_store import app_engine

    async def go() -> None:
        engine = app_engine(url)
        try:
            async with make_session_factory(engine)() as session, session.begin():
                await switch(session, SUPERVISION_REVIEW, on=True, by="u_owner")
        finally:
            await engine.dispose()

    run_async(go)


@pytest.mark.needs_db
def test_on_postgres_the_worker_reviews_only_due_pins_and_writes_nothing_until_switched_on() -> (
    None
):
    """**The run end to end, through the stores, as the application role.** Five agents: with the
    switch off a run adds no row and says what it would have done; switched on it writes a row for
    each of the three due pins under `supervision-review` with the counts the decision found, and
    nothing for the early pin or the one already eligible; a second run the same instant writes
    nothing, because each extension moved its date. Delete this and the due-pin query, the row's
    policy (`decided_by` is the session's principal), the counts constraint or the switch's read
    can be wrong with every fake-store test green."""
    from tests.unit.test_acceptance import at_head

    with at_head("brain_supervision_review") as url:
        _seed(url)
        before = _pin_rows(url)

        due = _due(url, 500)
        capped = _due(url, 2)
        off = _run_as_the_worker(url)
        after_off = _pin_rows(url)
        reported = _run_as_the_worker(url, report_only=True)

        _switch_on(url)
        reported_while_on = _run_as_the_worker(url, report_only=True)
        after_reports = _pin_rows(url)
        on = _run_as_the_worker(url)
        after_on = _pin_rows(url)
        again = _run_as_the_worker(url)
        after_again = _pin_rows(url)

    assert sorted(due) == ["ready", "short", "unseen"]
    assert len(capped) == 2 and set(capped) <= set(due)
    assert after_off == before
    assert after_reports == before
    assert "nothing was written" in off
    assert "3 due, 2 extended, 1 eligible" in off
    assert "nothing was written" in reported
    assert "nothing was written" in reported_while_on
    assert len(after_on) == len(before) + 3
    assert on.startswith("reviewed pins: 3 due, 2 extended, 1 eligible")
    written = {
        str(row[0]): row for row in after_on if row[2] == SYSTEM_REVIEWER
    }  # agent -> its row by the system
    assert set(written) == {"ready", "short", "unseen"}
    ready, short, unseen = written["ready"], written["short"], written["unseen"]
    assert (ready[1], ready[3:6]) == ("eligible", (10, 10, 10))
    assert (short[1], short[3:6]) == ("extended", (8, 10, 10))
    assert (unseen[1], unseen[3:6]) == ("extended", (0, 0, 10))
    assert ready[7] == T0 + SHADOW_REVIEW_PERIOD
    assert short[6] == T0
    assert short[7] == NOW + SHADOW_REVIEW_PERIOD
    assert short[8] == NOW
    assert all(row[2] != SYSTEM_REVIEWER for row in after_on if row[0] in {"early", "waiting"})
    assert after_again == after_on
    assert again == "no pin is due for review"


@pytest.mark.needs_db
def test_on_postgres_the_control_run_is_admitted_under_its_name_and_a_made_up_name_is_not() -> None:
    """`0212` widens `ops.control_run`'s name constraint. Delete this and the first run the schedule
    records under the new name is refused by the database while every registry test is green, or
    the constraint is widened to admit anything."""
    import psycopg

    from tests.unit.test_acceptance import at_head

    with at_head("brain_supervision_review_name") as url:
        from tests.fixtures.scratch_postgres import sql

        sql(
            url,
            "INSERT INTO ops.control_run (name, report_only) VALUES ('supervision_review', false)",
        )
        names = sql(url, "SELECT name FROM ops.control_run")
        with pytest.raises(psycopg.errors.CheckViolation):
            sql(url, "INSERT INTO ops.control_run (name, report_only) VALUES ('made_up', false)")

    assert names == [("supervision_review",)]
