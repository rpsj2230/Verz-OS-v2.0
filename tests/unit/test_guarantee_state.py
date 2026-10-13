"""A guarantee is held exactly when the control that keeps it is running.

`brain.ops.guarantee_state` reads the register of controls against the scheduler's record of
successful runs. Every test here builds its own controls, so a rename in the real register cannot
move them, and a date far from any wall clock, for CLAUDE.md's reason about fixtures that expire.

Task ids: M27.15.54
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.ops.alerting import Severity
from brain.ops.controls import CONTROLS, Control, Invocation, Missed
from brain.ops.guarantee_state import Guarantee, guarantees, held_by

NOW = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)
EVERY = timedelta(hours=6)


def a_control(name: str, invoked_by: Invocation = Invocation.IN_PROCESS) -> Control:
    return Control(
        name=name,
        symbols=("brain.ops.fixture:run_it",),
        guards="the thing this control protects",
        lost_silently="nothing else would notice",
        every=EVERY,
        severity=Severity.NOTICED,
        invoked_by=invoked_by,
    )


RUNNING, UNCALLED, UNRECORDED, NEVER, LATE = (
    a_control("running"),
    a_control("uncalled", Invocation.NOTHING),
    a_control("unrecorded"),
    a_control("never"),
    a_control("late"),
)
ALL = (RUNNING, UNCALLED, UNRECORDED, NEVER, LATE)
RECORD: dict[str, datetime | None] = {
    "running": NOW - EVERY,
    "uncalled": NOW,
    "never": None,
    "late": NOW - EVERY * 3,
}


def by_name(states: tuple[Guarantee, ...]) -> dict[str, Guarantee]:
    return {one.control: one for one in states}


def test_a_guarantee_is_held_only_while_its_control_runs_and_each_failure_is_not_held() -> None:
    """All four ways a control fails, and the one that does not, over one register. Delete this and
    a screen shows a guarantee as held for a control nothing calls, one nothing records, one that
    has never run or one that has stopped, which is the claim this module exists to stop."""
    held = by_name(guarantees(RECORD, NOW, ALL))
    assert {name: (one.held, one.because) for name, one in held.items()} == {
        "running": (True, None),
        "uncalled": (False, Missed.UNREACHABLE),
        "unrecorded": (False, Missed.NOT_RECORDED),
        "never": (False, Missed.NEVER_RUN),
        "late": (False, Missed.BEHIND),
    }
    assert held["running"].said.startswith("Held")
    assert "not" not in held["running"].said.split(":")[0].lower()
    assert "every 6:00:00" in held["late"].said


def test_a_run_exactly_at_the_alerting_threshold_is_still_held_and_one_past_it_is_not() -> None:
    """The boundary of `controls.alert_after`, outside the function. Delete this and a control a
    second late reads as lapsed, or one a day late reads as held."""
    edge = RUNNING.alert_after
    assert guarantees({"running": NOW - edge}, NOW, (RUNNING,))[0].held
    assert not guarantees({"running": NOW - edge - timedelta(seconds=1)}, NOW, (RUNNING,))[0].held


def test_every_guarantee_is_not_held_when_the_record_of_runs_could_not_be_read() -> None:
    """`None` for the record is a table nobody could open. Delete this and a screen that failed to
    read the runs shows every protection in force, the reading it draws from looking at nothing."""
    states = guarantees(None, NOW, ALL)
    assert [one.held for one in states] == [False] * len(ALL)
    assert {one.because for one in states} == {Missed.NOT_RECORDED}
    assert all("could not be read" in one.said for one in states)


def test_a_name_nobody_registered_is_not_held_and_a_registered_one_is_what_it_was() -> None:
    """`held_by`, both ways. Delete this and a screen pointing at a renamed control reads as one
    that always holds, or `held_by` answers False for a guarantee that is held."""
    states = guarantees(RECORD, NOW, ALL)
    assert held_by("running", states)
    assert not held_by("late", states)
    assert not held_by("a_control_nobody_registered", states)


def test_a_guarantee_cannot_be_held_with_a_reason_or_lapse_without_one() -> None:
    """The value's own refusal. Delete this and a renderer is handed a held guarantee carrying a
    reason, or a lapsed one that says nothing."""
    with pytest.raises(ValueError, match="held"):
        Guarantee(control="x", guards="y", held=True, because=Missed.BEHIND, said="s")
    with pytest.raises(ValueError, match="held"):
        Guarantee(control="x", guards="y", held=False, because=None, said="s")


def test_the_real_register_gives_one_state_per_control_in_its_own_order() -> None:
    """Over `CONTROLS` itself, with nothing recorded. Delete this and the screen can drop a control
    from the register's list, or list it twice, and shows fewer guarantees than there are."""
    states = guarantees({}, NOW)
    assert [one.control for one in states] == [one.name for one in CONTROLS]
    assert not any(one.held for one in states)
