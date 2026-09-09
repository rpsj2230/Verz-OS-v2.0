"""What the scheduler is owed, and the four things it refuses to decide quietly.

Every test here builds its own controls rather than reading the registry, for the reason
`brain.ops.schedule.owed` gives about taking its inputs: a decision that can only be exercised
against the real thirteen at the real instant cannot be shown to refuse anything. The two
tests that do read the registry say so in their names, because "the real estate is in this
state today" is a different claim from "this function behaves this way".

The dates are 2019 and 2999 wherever the test is not about the present, which is what
`tests/unit/test_scope_and_capability.py` does and for the reason CLAUDE.md records: a fixture
with a plausible date in it is a clock, and it goes off on a morning nobody chose.

Task ids: M28.2.4, M37.5.1.2
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.ops.alerting import Severity
from brain.ops.controls import CONTROLS, Control, Invocation
from brain.ops.schedule import (
    DESTRUCTIVE,
    TICK,
    Owed,
    ScheduleError,
    owed,
    report_only_now,
    schedulable,
    scheduling_gaps,
)

NOW = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def a_control(name: str, **changes: object) -> Control:
    """A valid control, so each refusal below is reached by changing exactly one thing."""
    values: dict[str, object] = {
        "name": name,
        "symbols": (f"brain.ops.{name}:run",),
        "guards": f"that {name} keeps happening",
        "lost_silently": f"{name} stops and the console goes on saying it is scheduled",
        "every": DAY,
        "severity": Severity.RAISED,
        "invoked_by": Invocation.NOTHING,
    }
    values.update(changes)
    return Control(**values)  # type: ignore[arg-type]


# --- what is owed -----------------------------------------------------------------------


def test_a_control_that_has_never_run_is_owed_now_and_is_not_reported_as_late() -> None:
    """**The alert-fatigue case, and it is the first thing a new install would have hit.**

    Nothing records a run on a fresh system, so subtracting a missing date from now makes
    every control decades overdue on the first tick. Thirteen critical alerts on day one is
    how an operator learns the whole category is noise.

    `first_run` carries the distinction instead, so an alerting rule can say "this has never
    run" without inferring it from an implausible number.

    Delete this and a fresh install pages somebody for every mechanism it has."""
    result = owed(now=NOW, last_run={}, controls=[a_control("sweep")])

    assert [one.name for one in result] == ["sweep"]
    assert result[0].first_run is True
    assert result[0].late_by == timedelta(0)
    assert result[0].due_since == NOW


def test_a_control_inside_its_cadence_is_not_owed_and_one_past_it_is() -> None:
    """The positive case and its boundary in one test, because a scheduler that returns
    everything on every tick and one that returns nothing both pass a test of only one side.

    The boundary is asserted at exactly the cadence rather than near it: a control that ran a
    day ago with a daily cadence is owed now, and one that ran a day ago minus a second is
    not.

    Delete this and a scheduler that starts every control every thirty seconds is green."""
    control = a_control("sweep")

    assert (
        owed(now=NOW, last_run={"sweep": NOW - DAY + timedelta(seconds=1)}, controls=[control])
        == ()
    )

    result = owed(now=NOW, last_run={"sweep": NOW - DAY}, controls=[control])

    assert [one.name for one in result] == ["sweep"]
    assert result[0].first_run is False
    assert result[0].late_by == timedelta(0)
    assert result[0].due_since == NOW - DAY + DAY


def test_lateness_is_measured_past_the_cadence_and_not_since_the_last_run() -> None:
    """**The number this produces is compared against `Control.alert_after` and nothing
    re-derives the cadence at that comparison.**

    A daily control that last ran three days ago is late by two days, not three: it became
    owed a day after it ran. `alert_after` is the cadence times `MISSED_RUN_GRACE`, which is
    two, so two days late is exactly the threshold and that is the arithmetic the registry
    already argues for.

    Measuring since the last run instead would make every control alert one whole interval
    early, which is the jitter case `MISSED_RUN_GRACE` exists to avoid.

    Delete this and the alerting threshold quietly moves by one interval."""
    control = a_control("sweep")

    result = owed(now=NOW, last_run={"sweep": NOW - 3 * DAY}, controls=[control])

    assert result[0].late_by == 2 * DAY
    assert result[0].late_by >= control.alert_after, "two whole misses is the alerting point"


def test_a_run_recorded_after_now_stops_the_control_being_started_twice() -> None:
    """A clock that stepped backwards leaves a last-run timestamp in the future, and nothing is
    started against one.

    **Which line does it is worth knowing, because a mutation run says it is not the obvious
    one.** There was an explicit `if previous > now: continue` here and removing it changed
    nothing: a cadence is refused at or below zero, so a run in the future puts the next due
    time in the future as well and the ordinary cadence check declines it. The explicit guard
    was unreachable, which is the defect CLAUDE.md calls this repository's most common, and it
    is gone. The behaviour is unchanged and is what this test pins.

    The skew itself is not absorbed silently: `scheduling_gaps` reports it, which is the test
    further down.

    Delete this and a host whose clock stepped runs its retention sweep twice in a minute."""
    assert owed(now=NOW, last_run={"sweep": NOW + DAY}, controls=[a_control("sweep")]) == ()


# --- what this scheduler may start ------------------------------------------------------


def test_a_control_something_outside_the_process_starts_is_not_scheduled_here() -> None:
    """**The audit anchor is the one control that has always worked and it is the one this
    must not touch.**

    A GitHub Actions timer calls its route every six hours. A second caller inside the process
    would give it two, at two cadences, and the symptom is a system publishing more seals than
    its schedule says, which reads as a system working harder.

    Delete this and turning the scheduler on doubles the one mechanism that was already
    running."""
    on_a_route = a_control(
        "anchor",
        invoked_by=Invocation.ON_A_ROUTE,
        route="/internal/anchor",
        schedule_file=".github/workflows/anchor.yml",
    )
    controls = [a_control("sweep"), on_a_route]

    assert [one.name for one in schedulable(controls)] == ["sweep"]
    assert [one.name for one in owed(now=NOW, last_run={}, controls=controls)] == ["sweep"]


def test_a_control_another_module_calls_is_still_this_schedulers_to_start() -> None:
    """The other side of that rule, and it is not symmetric.

    `spend_correction` has a caller: the cost review section of the usage screen. A screen is
    not a schedule, so the control runs when somebody opens a page and never otherwise, which
    is what `brain.ops.controls.chains_worth_checking` says about it. Excluding it because it
    has a caller would leave a weekly correction running whenever an administrator happens to
    look.

    Delete this and the rule above widens quietly to cover a case it was not written for."""
    in_process = a_control("correction", invoked_by=Invocation.IN_PROCESS)

    assert [one.name for one in schedulable([in_process])] == ["correction"]


def test_the_real_registry_gives_this_scheduler_twelve_of_the_thirteen_controls() -> None:
    """The state of the estate today, asserted so that wiring a control to a timer outside the
    process shows up here rather than in nothing.

    Named as a fact about the registry rather than about the function, because it is: it will
    change when the estate changes, and that is what it is for.

    Delete this and a control moved onto an external schedule silently keeps a second caller
    inside the process."""
    mine = schedulable()

    assert len(CONTROLS) == 13
    assert len(mine) == 12
    assert "audit_anchor" not in {one.name for one in mine}


# --- the sweep that deletes -------------------------------------------------------------


def test_a_destructive_control_reports_rather_than_acts_until_it_is_released() -> None:
    """**The retention sweep deletes everything past its window, and its first run on a real
    install deletes everything that accumulated before the schedule existed.**

    That is the mechanism working, and from inside the process it is indistinguishable from
    the mechanism being misconfigured. So it is scheduled with `report_only` set until
    somebody names it in the installation's released set, which is a record that a person read
    a report and decided.

    Scheduled rather than withheld, because a sweep that is silently not scheduled is exactly
    the defect this module exists for.

    Delete this and switching the scheduler on deletes a client's backlog on the first tick,
    with the console reporting a healthy retention window throughout."""
    control = a_control("retention_sweep")

    held = owed(now=NOW, last_run={}, controls=[control])
    assert held[0].report_only is True

    let_go = owed(now=NOW, last_run={}, controls=[control], released=["retention_sweep"])
    assert let_go[0].report_only is False


def test_a_destructive_control_stays_held_back_on_every_run_and_not_only_its_first() -> None:
    """**A mutation survived here and this test is what it found.**

    The test above exercises a control that has never run, which is one of the two paths
    through `owed`. Releasing the other one unconditionally passed the whole file: a retention
    sweep would report on its first run and delete on every run after it, which is the failure
    wearing the appearance of the guard working.

    Delete this and the report-only rule holds for exactly one tick."""
    control = a_control("retention_sweep")
    ran_yesterday = {"retention_sweep": NOW - 2 * DAY}

    held = owed(now=NOW, last_run=ran_yesterday, controls=[control])
    assert held[0].first_run is False
    assert held[0].report_only is True

    let_go = owed(now=NOW, last_run=ran_yesterday, controls=[control], released=["retention_sweep"])
    assert let_go[0].report_only is False


def test_a_destructive_name_matching_no_control_is_reported_by_the_gaps_check() -> None:
    """The other survivor. `test_the_only_destructive_control_is_one_the_registry_actually_has`
    asserts the property against `CONTROLS` directly, and the branch in `scheduling_gaps` that
    says it out loud was reached by nothing: the real registry has the control, so the finding
    never appears, and every other test passes controls it built itself without asserting on
    that finding.

    A stale name is a protection sitting on a string rather than on a mechanism, which is the
    state a rename leaves behind, and it is worth a sentence somebody reads rather than only a
    failing assertion in a file about registries.

    Delete this and renaming the retention sweep silently releases it."""
    found = scheduling_gaps(now=NOW, last_run={}, controls=[a_control("canary")])

    assert any("protection is on a name rather than on a mechanism" in one for one in found)
    assert any("retention_sweep" in one for one in found)


def test_a_control_that_deletes_nothing_is_never_held_back() -> None:
    """The positive case for the rule above. A guard tested only by what it holds back is
    satisfied by one that holds everything back, which would be a scheduler that reports and
    never runs.

    Delete this and `DESTRUCTIVE` could be every control with the suite green."""
    assert owed(now=NOW, last_run={}, controls=[a_control("canary")])[0].report_only is False


def test_what_is_switched_on_is_answerable_without_asking_what_is_due() -> None:
    """A console showing "the retention sweep is reporting only" must not have to ask what is
    owed at this instant, because that answer changes every minute and the screen would
    flicker between showing the row and not.

    Delete this and the only way to render that state is a question whose answer depends on
    the clock."""
    assert report_only_now() == ("retention_sweep",)
    assert report_only_now(released=["retention_sweep"]) == ()


def test_the_only_destructive_control_is_one_the_registry_actually_has() -> None:
    """`DESTRUCTIVE` is a set of names, and a name that no longer matches a control is an
    exemption waiting to cover the next control that takes it. `brain.ops.controls.NOT_A_SCHEDULE`
    refuses its own stale entries for the same reason and this is that rule for this set.

    Delete this and renaming the retention sweep leaves it released by accident."""
    assert {one.name for one in CONTROLS} >= DESTRUCTIVE


# --- what would make the schedule report a run that did not happen ----------------------


def test_a_clock_that_stepped_backwards_is_reported_rather_than_absorbed() -> None:
    """`owed` refuses to start the control and says nothing about why, because its return type
    is a list of work. The reason belongs somewhere a person reads.

    Delete this and a control silently stops running for as long as the clock is ahead."""
    found = scheduling_gaps(now=NOW, last_run={"sweep": NOW + DAY}, controls=[a_control("sweep")])

    assert any("which is after" in one for one in found)


def test_a_cadence_the_tick_cannot_meet_is_a_finding_rather_than_a_silent_halving() -> None:
    """A control whose interval is at or below twice the tick is started on some ticks and not
    others, depending on where the two land, so its real cadence is the drift between them and
    every screen reports the declared one.

    Delete this and adding a fifteen-second control halves its own frequency with nothing
    saying so."""
    too_fast = a_control("probe", every=TICK)

    found = scheduling_gaps(now=NOW, last_run={}, controls=[too_fast])

    assert any("its real cadence is the drift" in one for one in found)


def test_the_real_registry_has_no_control_this_scheduler_cannot_meet() -> None:
    """The deployment check: run against the thirteen and the tick as configured. The shortest
    cadence in the registry is a minute and the tick is thirty seconds, so this is green and
    goes red when either moves.

    Delete this and `TICK` can be raised past a real control's interval with the unit tests
    above still green, because they build their own."""
    assert scheduling_gaps(now=NOW, last_run={}) == ()


# --- the shape of one owed run ----------------------------------------------------------


def test_a_run_that_has_never_happened_cannot_also_be_late() -> None:
    """The two states are different sentences and the type refuses to hold both, because the
    combination is what a naive subtraction produces and it is the thing this module exists to
    avoid saying.

    Delete this and the invariant lives only in the function that happens to build these."""
    with pytest.raises(ScheduleError, match="has never run"):
        Owed(
            name="sweep",
            due_since=NOW,
            late_by=DAY,
            first_run=True,
            report_only=False,
        )


def test_a_run_owed_in_the_future_is_refused_by_the_type() -> None:
    """A negative lateness is a control owed later reported as work to do now. Nothing in this
    module produces one; the type refuses it so that a second producer cannot.

    Delete this and the next caller building these by hand can hand the runner work that is
    not due."""
    with pytest.raises(ScheduleError, match="owed in the past"):
        Owed(
            name="sweep",
            due_since=NOW,
            late_by=-DAY,
            first_run=False,
            report_only=False,
        )
