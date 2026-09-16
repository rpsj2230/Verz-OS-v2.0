"""What a person's pause and a person's request to run now change about the worker's tick.

`chosen_this_tick` is the rule and is tested over instants alone. `tick_controls` is then driven
with its reads and its run replaced, so what is under test is that the tick asks the rule and
starts exactly what it chose through `start_owed`, which is the run: the same lock and the same
run record. The database half of a tick is `tests/unit/test_worker_schedule.py`'s, against a real
PostgreSQL in CI.

The clock is 2999, for the reason CLAUDE.md records.

Task ids: M27.8.13
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.ops import worker
from brain.ops.schedule import DESTRUCTIVE, Owed, schedulable
from brain.ops.schedule_control import (
    Chosen,
    ScheduleControlError,
    chosen_this_tick,
    control_refusal,
    paused_in,
    request_run,
    requested_at,
    set_paused,
)
from brain.ops.schedule_runner import RUNNERS
from brain.ops.setting_store import SettingState
from brain.ops.worker import ControlTick, Ticked, tick_controls

NOW = datetime(2999, 3, 1, 9, 0, tzinfo=UTC)

#: The controls whose runner can start, and one the worker ticks that cannot.
WIRED = [one.name for one in RUNNERS if one.run is not None]
UNWIRED = next(one.name for one in RUNNERS if one.run is None)
SWEEP = "retention_sweep"
REFRESH = "spend_report_refresh"


def owed(name: str, *, report_only: bool = False) -> Owed:
    return Owed(
        name=name, due_since=NOW, late_by=timedelta(0), first_run=True, report_only=report_only
    )


def row(value: Any, value_type: str) -> SettingState:
    return SettingState(
        key="schedule.x",
        value_type=value_type,
        value=value,
        updated_by="u_admin",
        updated_at=NOW,
    )


# ------------------------------------------------------------------------ the rule


def test_an_owed_control_nobody_paused_is_chosen_and_a_paused_one_is_not() -> None:
    """Delete this and a pause is a row the tick never reads, or every owed control stops."""
    both = [owed(REFRESH), owed("knowledge_reverification")]

    assert chosen_this_tick(both, now=NOW, paused=(), requested={}, last_attempt={}) == (
        Chosen("knowledge_reverification", False, False),
        Chosen(REFRESH, False, False),
    )
    assert chosen_this_tick(both, now=NOW, paused={REFRESH}, requested={}, last_attempt={}) == (
        Chosen("knowledge_reverification", False, False),
    )


def test_a_run_asked_for_starts_a_control_the_schedule_does_not_owe_and_one_that_is_paused() -> (
    None
):
    """A request is honoured whether or not the cadence owes it, and a pause does not stop it.

    Delete this and run now does nothing for a control that ran an hour ago, which is the only
    case anybody presses it for."""
    asked = {REFRESH: NOW - timedelta(seconds=5)}
    earlier = {REFRESH: NOW - timedelta(hours=1)}

    assert chosen_this_tick(
        (), now=NOW, paused={REFRESH}, requested=asked, last_attempt=earlier
    ) == (Chosen(REFRESH, False, True),)


def test_a_request_is_answered_by_any_run_that_started_at_or_after_it() -> None:
    """Once a run has started since the request, the request asks for nothing more.

    Delete this and a pressed button starts the control on every tick for ever, because nothing
    consumes a request and the run record is the only thing that says it was answered."""
    asked = {REFRESH: NOW - timedelta(minutes=2)}

    for started in (NOW - timedelta(minutes=2), NOW - timedelta(minutes=1)):
        assert (
            chosen_this_tick(
                (), now=NOW, paused=(), requested=asked, last_attempt={REFRESH: started}
            )
            == ()
        )
    assert chosen_this_tick(
        (), now=NOW, paused=(), requested=asked, last_attempt={REFRESH: NOW - timedelta(minutes=3)}
    ) == (Chosen(REFRESH, False, True),)


def test_a_request_dated_after_the_tick_waits_for_its_instant() -> None:
    """Delete this and a request stamped by a server clock running ahead fires before its time,
    and one written by hand for tomorrow fires now."""
    asked = {REFRESH: NOW + timedelta(minutes=1)}

    assert chosen_this_tick((), now=NOW, paused=(), requested=asked, last_attempt={}) == ()


def test_a_destructive_control_asked_for_and_not_released_runs_report_only() -> None:
    """The report-only rule is the schedule's for a pressed button too.

    Delete this and run now deletes with a retention sweep nobody released."""
    assert SWEEP in DESTRUCTIVE
    asked = {SWEEP: NOW}

    assert chosen_this_tick((), now=NOW, paused=(), requested=asked, last_attempt={}) == (
        Chosen(SWEEP, True, True),
    )
    assert chosen_this_tick(
        (), now=NOW, paused=(), requested=asked, last_attempt={}, released=(SWEEP,)
    ) == (Chosen(SWEEP, False, True),)


def test_only_the_json_true_pauses_and_only_a_zoned_instant_is_a_request() -> None:
    """Delete this and the string "false" typed at a prompt pauses a control, or a naive instant
    fires hours early by the host's offset."""
    assert paused_in({REFRESH: row(True, "boolean")}) == {REFRESH}
    assert paused_in({REFRESH: row("false", "string"), SWEEP: row(False, "boolean")}) == frozenset()
    assert requested_at(row(NOW.isoformat(), "string")) == NOW
    assert requested_at(row("2999-03-01T09:00:00", "string")) is None
    assert requested_at(row("not an instant", "string")) is None
    assert requested_at(row(True, "boolean")) is None


def test_a_control_the_worker_can_start_may_be_paused_and_one_it_cannot_is_refused_by_reason() -> (
    None
):
    """Delete this and a pause is accepted for a control the tick never starts, which is a switch
    wired to nothing."""
    assert all(control_refusal(name) == "" for name in WIRED)
    assert "nothing to run yet" in control_refusal(UNWIRED)
    assert "not started by the worker's schedule" in control_refusal("audit_anchor")
    assert "not started by the worker's schedule" in control_refusal("made_up")
    assert {one.name for one in schedulable()} >= set(WIRED)


def test_the_rows_refuse_a_control_that_cannot_be_controlled_before_anything_is_written() -> None:
    """Delete this and the store writes a pause for a name that only the route refused."""

    class Refuses:
        async def execute(self, *_: Any) -> None:
            raise AssertionError("nothing should be written")

    with pytest.raises(ScheduleControlError, match="nothing to run yet"):
        asyncio.run(set_paused(Refuses(), UNWIRED, paused=True, by="u_admin"))  # type: ignore[arg-type]
    with pytest.raises(ScheduleControlError, match="naive instant"):
        asyncio.run(
            request_run(Refuses(), REFRESH, at=datetime(2999, 1, 1), by="u_admin")  # type: ignore[arg-type]
        )


# ------------------------------------------------------------------------ the tick


class Reads:
    """Stands in for the four reads a tick makes and records every start it asks for."""

    def __init__(
        self,
        *,
        attempts: dict[str, datetime] | None = None,
        paused: frozenset[str] = frozenset(),
        requested: dict[str, datetime] | None = None,
    ) -> None:
        self.attempts = attempts or {}
        self.paused = paused
        self.requested = requested or {}
        self.started: list[tuple[str, bool]] = []


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> Reads:
    found = Reads()

    class Session:
        async def __aenter__(self) -> Session:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

    async def clocks(_: Any) -> tuple[dict[str, datetime], dict[str, datetime]]:
        return found.attempts, dict(found.attempts)

    async def released(_: Any, *, now: datetime) -> frozenset[str]:
        return frozenset()

    async def paused(_: Any) -> frozenset[str]:
        return found.paused

    async def requested(_: Any) -> dict[str, datetime]:
        return found.requested

    async def start_owed(_: Any, name: str, *, report_only: bool, **__: Any) -> ControlTick:
        found.started.append((name, report_only))
        return ControlTick(name, Ticked.REFUSED if report_only else Ticked.RAN)

    monkeypatch.setattr(worker, "clocks", clocks)
    monkeypatch.setattr(worker, "released_controls", released)
    monkeypatch.setattr(worker, "paused_controls", paused)
    monkeypatch.setattr(worker, "run_requests", requested)
    monkeypatch.setattr(worker, "start_owed", start_owed)
    found.session = Session  # type: ignore[attr-defined]
    return found


def tick(reads: Reads) -> tuple[ControlTick, ...]:
    return asyncio.run(
        tick_controls(
            reads.session,  # type: ignore[attr-defined]
            now=NOW,
            database_url="postgresql://unused",
        )
    )


def test_a_tick_starts_nothing_it_was_told_is_paused_and_reports_it_paused(reads: Reads) -> None:
    """On a fresh install every wired control is owed; pausing one leaves it unstarted and
    reported, and the others still start.

    Delete this and the worker ignores the pause the Scheduled jobs screen says is in force."""
    reads.paused = frozenset({REFRESH})

    ticked = tick(reads)

    assert (REFRESH, False) not in reads.started
    assert {name for name, _ in reads.started} == set(WIRED) - {REFRESH}
    assert ControlTick(REFRESH, Ticked.PAUSED) in ticked


def test_a_tick_starts_a_control_a_person_asked_for_through_the_run_itself(reads: Reads) -> None:
    """A control that ran a second ago is not owed, and a request since then starts it anyway,
    paused or not, through `start_owed`.

    Delete this and run now writes a row the worker never acts on."""
    ran = NOW - timedelta(seconds=1)
    assert all(one.every > timedelta(seconds=1) for one in schedulable())
    reads.attempts = {one.name: ran for one in schedulable()}
    reads.paused = frozenset({REFRESH})

    assert tick(reads) == ()
    reads.requested = {REFRESH: NOW - timedelta(milliseconds=500)}

    assert tick(reads) == (ControlTick(REFRESH, Ticked.RAN),)
    assert reads.started == [(REFRESH, False)]
