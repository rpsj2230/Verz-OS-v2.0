"""The quality screen's reader decision: when the canaries last ran, to whom, and in what words.

Three properties. A finished run is never a passed one, because the attempt table records that a
control returned and not what it found. A canary run is shown only to a reader whose evaluation
grant covers the whole install, because a failing run is a statement that the gate may be leaking
now. And a reader who may not see a run is answered exactly as an install with no run recorded.

Dates are 2019, far from any wall clock, because nothing here is about the present.

Task ids: M27.7.19
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from brain.console.quality_view import (
    CANARY_CONTROL,
    EVALUATION_AUTHORITY,
    EVALUATION_RUNS_ARE_RECORDED,
    FINDINGS_ARE_RECORDED,
    SCREEN_KEY,
    STATE_OF_OUTCOME,
    CanaryRun,
    QualityViewError,
    RunState,
    canary_run_of,
    may_read_canary_runs,
    quality_for_reader,
    quality_gaps,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.ops.controls import CONTROLS
from brain.tables.schedule import OUTCOMES

#: The grant, written out rather than read from the module under test.
EVALUATION = Capability(value="read:evaluation")

NOW = datetime(2019, 3, 5, 9, 0, tzinfo=UTC)
STARTED = NOW - timedelta(hours=3)
FINISHED = STARTED + timedelta(minutes=2)

#: Twelve hours, the canaries' own figure, as a literal.
TWELVE_HOURS = 12 * 60 * 60


def reader(scope: Scope | None, *, expired: bool = False) -> EntitlementSet:
    """A reader holding the evaluation grant in `scope`, or holding nothing when it is None."""
    grants = () if scope is None else (Grant(capability=EVALUATION, scope=scope),)
    return EntitlementSet(
        principal_id="u_reader",
        grants=grants,
        not_after=datetime(2019, 1, 1, tzinfo=UTC) if expired else None,
    )


def a_run(state: RunState = RunState.FAILED) -> CanaryRun:
    finished = None if state is RunState.UNFINISHED else FINISHED
    return CanaryRun(started_at=STARTED, finished_at=finished, state=state)


# ----------------------------------------------------------------------------- the runs
@pytest.mark.parametrize(
    ("outcome", "state"),
    [("ok", RunState.FINISHED), ("failed", RunState.FAILED), ("refused", RunState.DECLINED)],
)
def test_each_recorded_outcome_is_shown_in_the_attempt_tables_own_terms(
    outcome: str, state: RunState
) -> None:
    """Three outcomes, three states, and none of them is passed.

    What breaks if this is deleted: `ok` shown as a pass, which is a green light on the screen
    read before deciding not to worry, for a run that may have found a leak and returned.
    """
    run = canary_run_of(started_at=STARTED, finished_at=FINISHED, outcome=outcome)

    assert run == CanaryRun(started_at=STARTED, finished_at=FINISHED, state=state)
    assert {one.value for one in RunState} == {"finished", "failed", "declined", "unfinished"}


def test_a_run_with_a_start_and_no_finish_is_unfinished() -> None:
    """A process that died mid-run, or a run still going, is shown as neither ending.

    What breaks if this is deleted: the newest attempt, which never returned, is refused or
    shown as finished, and a canary run that hangs every time looks like one that runs.
    """
    run = canary_run_of(started_at=STARTED, finished_at=None, outcome=None)

    assert run == CanaryRun(started_at=STARTED, finished_at=None, state=RunState.UNFINISHED)


@pytest.mark.parametrize(
    ("finished_at", "outcome"),
    [(FINISHED, None), (None, "ok")],
    ids=["finish_only", "outcome_only"],
)
def test_a_row_the_attempt_table_never_writes_is_refused(
    finished_at: datetime | None, outcome: str | None
) -> None:
    """A finish and its outcome are written together, so one without the other is not a run.

    What breaks if this is deleted: a hand-edited or half-written row is rendered as a run
    somebody then reasons about.
    """
    with pytest.raises(QualityViewError, match="never writes"):
        canary_run_of(started_at=STARTED, finished_at=finished_at, outcome=outcome)


def test_an_outcome_the_attempt_table_does_not_know_is_refused() -> None:
    """No state is invented for a word this module has not decided.

    What breaks if this is deleted: a new outcome is shown as whatever a default made of it.
    """
    with pytest.raises(QualityViewError, match="not an outcome"):
        canary_run_of(started_at=STARTED, finished_at=FINISHED, outcome="passed")


@pytest.mark.parametrize(
    ("started_at", "finished_at"),
    [
        (datetime(2019, 3, 5, 6, 0), None),
        (STARTED, datetime(2019, 3, 5, 6, 2)),
    ],
    ids=["naive_start", "naive_finish"],
)
def test_a_run_with_a_naive_instant_is_refused(
    started_at: datetime, finished_at: datetime | None
) -> None:
    """A run shown at the server's offset rather than its own.

    What breaks if this is deleted: a run is shown hours away from when it happened, on a screen
    whose one figure is when.
    """
    with pytest.raises(QualityViewError, match="naive"):
        canary_run_of(
            started_at=started_at,
            finished_at=finished_at,
            outcome=None if finished_at is None else "ok",
        )


# ---------------------------------------------------------------------------- the reader
def test_a_whole_install_evaluation_reader_is_shown_the_last_run() -> None:
    """The positive case, which every refusal below would pass by showing nobody anything.

    What breaks if this is deleted: a screen that never showed a run passes every test here.
    """
    shown = quality_for_reader(a_run(), reader(Scope.unrestricted()), now=NOW, started=False)

    assert shown.last_canary_run == a_run()


def test_a_department_scoped_evaluation_reader_is_not_shown_a_run() -> None:
    """A run is the whole install's, and a failed one says the gate may be leaking now.

    What breaks if this is deleted: a department admin learns that the permission gate failed
    its canaries this morning, which is worth most to the reader who should not have it.
    """
    shown = quality_for_reader(a_run(), reader(Scope.department("support")), now=NOW, started=False)

    assert shown.last_canary_run is None


@pytest.mark.parametrize(
    "entitlement",
    [reader(None), reader(Scope.department("support")), reader(Scope.unrestricted(), expired=True)],
    ids=["no_grant", "department_scoped", "expired"],
)
def test_a_reader_who_may_not_see_a_run_is_answered_as_an_install_with_no_run(
    entitlement: EntitlementSet,
) -> None:
    """DENIED and ABSENT: the withheld object equals the never-run object, whatever the run was.

    What breaks if this is deleted: a field or a default that differs between the two, and a
    reader can tell a run was withheld from them, which says one happened.
    """
    never_run = quality_for_reader(None, reader(Scope.unrestricted()), now=NOW, started=True)
    for state in RunState:
        withheld = quality_for_reader(a_run(state), entitlement, now=NOW, started=True)
        assert withheld == never_run


def test_whether_the_canaries_are_started_and_their_cadence_are_carried_to_everybody() -> None:
    """Facts about the product's code, identical for every reader.

    What breaks if this is deleted: a refused reader is given a different cadence or schedule
    from a permitted one, which is a difference they can read.
    """
    for entitlement in (reader(None), reader(Scope.unrestricted())):
        shown = quality_for_reader(None, entitlement, now=NOW, started=True)
        assert shown.canaries_started is True
        assert shown.canary_interval_seconds == TWELVE_HOURS
    assert quality_for_reader(None, reader(None), now=NOW, started=False).canaries_started is False


def test_an_expired_reader_may_not_read_a_run() -> None:
    """The instant is passed through.

    What breaks if this is deleted: the decision reads no clock and an expired grant goes on
    being shown the gate's health.
    """
    assert may_read_canary_runs(reader(Scope.unrestricted()), now=NOW) is True
    assert may_read_canary_runs(reader(Scope.unrestricted(), expired=True), now=NOW) is False


def test_the_grant_is_judged_at_the_requests_instant_and_not_the_process_clock() -> None:
    """A grant lapsing after the request's instant and before today's clock still holds.

    The lapse is 2020, after `NOW` and before any wall clock this runs under, so the two
    instants give opposite answers and only the one the request carries is right.

    What breaks if this is deleted: `now` stops being passed to `scope_for`, the process clock
    is used instead, and the expired-reader test above still passes, because a grant that
    lapsed in 2019 is lapsed by either clock.
    """
    lapses_later = EntitlementSet(
        principal_id="u_reader",
        grants=(Grant(capability=EVALUATION, scope=Scope.unrestricted()),),
        not_after=datetime(2020, 1, 1, tzinfo=UTC),
    )

    assert may_read_canary_runs(lapses_later, now=NOW) is True


def test_the_screen_is_the_registrys_quality_screen_read_behind_the_evaluation_grant() -> None:
    """The key, the grant and the control, compared with values written out here.

    What breaks if this is deleted: the screen reads another control's runs as the canaries', or
    another screen's grant.
    """
    assert SCREEN_KEY == "quality"
    assert EVALUATION_AUTHORITY == EVALUATION
    assert CANARY_CONTROL == "canary_run"


def test_nothing_records_a_finding_or_an_evaluation_run() -> None:
    """The two constants the route copies onto the response.

    What breaks if this is deleted: the page stops saying a finished run is not a passed one, or
    that the golden corpus is not on an install, with nothing having changed about either.
    """
    assert FINDINGS_ARE_RECORDED is False
    assert EVALUATION_RUNS_ARE_RECORDED is False


# ------------------------------------------------------------------------------- the gaps
def test_this_screen_reports_no_gaps_about_itself() -> None:
    """Green today, so every gap below is a change somebody made.

    What breaks if this is deleted: the checks below prove the diagnostic can find something
    and nothing proves this module is clean.
    """
    assert set(STATE_OF_OUTCOME) == set(OUTCOMES)
    assert quality_gaps() == ()


def test_a_canary_control_missing_from_the_registry_is_reported() -> None:
    """The runs this screen reads would be nobody's.

    What breaks if this is deleted: the control is renamed in the registry and this screen
    shows no run for ever, which reads as the canaries never having run.
    """
    found = quality_gaps(controls=tuple(one for one in CONTROLS if one.name != CANARY_CONTROL))

    assert found == (
        "canary_run is not a control in the registry, so the runs this screen reads are nobody's "
        "and the canaries' own runs are read by nothing",
    )


def test_a_registry_cadence_other_than_the_canaries_own_is_reported() -> None:
    """The screen quotes one cadence and the scheduler would keep another.

    What breaks if this is deleted: the screen says the canaries are due every twelve hours while
    the scheduler waits a day.
    """
    moved = tuple(
        replace(one, every=timedelta(days=1)) if one.name == CANARY_CONTROL else one
        for one in CONTROLS
    )

    (found,) = quality_gaps(controls=moved)

    assert "every 1 day, 0:00:00" in found


def test_an_outcome_with_no_state_is_reported() -> None:
    """A new way for a run to end, added to the table and not to this screen.

    What breaks if this is deleted: the first run ending the new way is refused on the screen
    rather than shown.
    """
    found = quality_gaps(outcomes=(*OUTCOMES, "skipped"))

    assert len(found) == 1
    assert "'skipped'" in found[0]
