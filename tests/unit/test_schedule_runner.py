"""The lock, the two clocks, and the list of what each control still needs.

The dates here are 2999 for the reason CLAUDE.md records: a fixture with a plausible date in
it is a clock and it goes off on a morning nobody chose.

Task ids: M37.5.1.3
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from brain.ops.alerting import Severity
from brain.ops.controls import CONTROLS, Control, Invocation
from brain.ops.retention import Store
from brain.ops.schedule import TICK, schedulable
from brain.ops.schedule_runner import (
    A_DISPATCH_IN_REPORT_ONLY_MODE_SENDS_NOTHING,
    A_NAG_IN_REPORT_ONLY_MODE_RECORDS_NOTHING,
    A_REFRESH_IN_REPORT_ONLY_MODE_REBUILDS_NOTHING,
    RUNNERS,
    SCHEDULER_LOCK_NAMESPACE,
    STALLED_AFTER,
    Runner,
    RunnerError,
    due_now,
    lock_id,
    next_tick,
    runner_for,
    runner_gaps,
    spend_report_refresh,
    stalled_runs,
    start_control,
)
from tests.fixtures.scratch_postgres import (
    RETENTION_TABLES,
    add_modelled,
    drop,
    fresh,
    migrate,
    sql,
)

NOW = datetime(2999, 6, 1, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def a_control(name: str, **changes: object) -> Control:
    """A valid control, so each case below is reached by changing exactly one thing."""
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


# --- the two clocks ----------------------------------------------------------------------


def test_a_control_that_keeps_failing_is_retried_on_its_cadence_and_reported_as_long_late() -> None:
    """**The whole reason there are two columns rather than one.**

    A daily control attempted an hour ago and last successful a week ago is not due, because
    something tried it recently and retrying every thirty seconds would hammer whatever is
    broken. When it does become due, it is late by however long it has not worked, not by
    however long since the last attempt.

    One column can say only one of those. The version that says only "attempted recently"
    produces a mechanism that is permanently on time and permanently broken, which is exactly
    the failure `brain.ops.controls` was written about.

    Delete this and the two clocks silently become one, and the one that survives is the
    flattering one."""
    control = a_control("sweep")
    attempted = {"sweep": NOW - timedelta(hours=1)}
    succeeded = {"sweep": NOW - 8 * DAY}

    assert (
        due_now(now=NOW, last_attempt=attempted, last_success=succeeded, controls=[control]) == ()
    )

    later = NOW + DAY
    result = due_now(now=later, last_attempt=attempted, last_success=succeeded, controls=[control])

    assert [one.name for one in result] == ["sweep"]
    assert result[0].late_by == later - (succeeded["sweep"] + DAY), "late since it last worked"
    assert result[0].late_by > 7 * DAY


def test_a_control_that_has_always_worked_reads_the_same_on_both_clocks() -> None:
    """The positive case. A rule tested only by its awkward input is satisfied by one that
    always takes the awkward branch, and here that would be a scheduler reporting every
    healthy control as long overdue.

    Delete this and the failure path could be the only path with the suite green."""
    control = a_control("sweep")
    same = {"sweep": NOW - 3 * DAY}

    result = due_now(now=NOW, last_attempt=same, last_success=same, controls=[control])

    assert [one.name for one in result] == ["sweep"]
    assert result[0].late_by == 2 * DAY
    assert result[0].first_run is False


def test_a_control_that_has_never_succeeded_but_has_been_tried_is_not_a_first_run() -> None:
    """The case the two maps disagree about most sharply: something has attempted it, so it is
    not new, and nothing has ever worked, so there is no success to measure lateness from.

    Reported as a first run rather than as decades overdue, which is the same argument
    `brain.ops.schedule.A_CONTROL_THAT_HAS_NEVER_RUN_IS_OWED_AND_IS_NOT_LATE` makes, arriving
    from the other direction: an install where the sweep has been failing since setup should
    say so, not claim it is behind by the age of the epoch.

    Delete this and a control that has never once worked reports a lateness nobody can read."""
    control = a_control("sweep")

    result = due_now(
        now=NOW, last_attempt={"sweep": NOW - 2 * DAY}, last_success={}, controls=[control]
    )

    assert [one.name for one in result] == ["sweep"]
    assert result[0].first_run is True
    assert result[0].late_by == timedelta(0)


def test_a_destructive_control_is_still_held_back_when_it_is_reached_through_two_clocks() -> None:
    """The report-only rule survives the extra layer, which is the only thing this can assert.

    **A mutation says the two sources of this flag are the same source.** `due_now` asks `owed`
    twice and both answers carry a `report_only`; taking it from the other one changes nothing
    and no test can distinguish them, because `owed` computes it from the control's name and
    the released set and neither depends on the instant or on the map it was handed. That is a
    genuinely equivalent mutation rather than a missing test, it is recorded as one in
    `due_now`, and this test is renamed to claim only what it can show.

    Delete this and the two-clock layer could drop the flag entirely, which would release
    every destructive control."""
    control = a_control("retention_sweep")

    held = due_now(now=NOW, last_attempt={}, last_success={}, controls=[control])
    assert held[0].report_only is True

    let_go = due_now(
        now=NOW,
        last_attempt={},
        last_success={},
        controls=[control],
        released=["retention_sweep"],
    )
    assert let_go[0].report_only is False


# --- the lock ----------------------------------------------------------------------------


def test_two_controls_never_share_a_lock_and_one_control_always_takes_the_same_one() -> None:
    """**The second half is the one that would break silently across replicas.**

    `hash()` is salted per process, so two replicas would compute two different locks for one
    control and both would run it, which is the failure the lock exists to prevent and which
    no single-process test would ever show. CRC32 is stable across processes and machines.

    The first half is ordinary and worth pinning anyway: two mechanisms behind one lock
    serialise, and a retention sweep is the slowest thing here.

    Delete this and the lock derivation can move to something per-process with the suite
    green."""
    every = {one.name: lock_id(one.name) for one in schedulable()}

    assert len(set(every.values())) == len(every), "no two controls share a lock"
    assert lock_id("retention_sweep") == lock_id("retention_sweep")
    assert all(namespace == SCHEDULER_LOCK_NAMESPACE for namespace, _ in every.values())


def test_every_lock_fits_the_signed_integers_postgres_actually_takes() -> None:
    """`pg_advisory_xact_lock(int, int)` takes signed 32-bit integers and refuses a value
    above 2^31 rather than wrapping it. CRC32 produces an unsigned 32-bit value, so a control
    whose name happens to hash high would fail at the database and only for that one control.

    Asserted over every real control name and over a name chosen because its CRC32 is above
    the boundary, because the real thirteen might all hash low today and this must not depend
    on that.

    Delete this and adding a control is a fifty-fifty chance of a lock that cannot be taken."""
    boundary = 1 << 31
    names = [one.name for one in schedulable()] + ["a", "zzzz", "control_run", "sweep"]

    for name in names:
        namespace, key = lock_id(name)
        assert -boundary <= namespace < boundary, name
        assert -boundary <= key < boundary, name


def test_an_unnamed_control_cannot_be_given_a_lock() -> None:
    """Every caller of a lock derived from an empty name would share one lock, which is a
    single mutex across the whole scheduler wearing the appearance of thirteen.

    Delete this and a control whose name is somehow blank serialises everything behind it."""
    with pytest.raises(RunnerError, match="has no lock"):
        lock_id("   ")


# --- what this process can actually start ------------------------------------------------


def test_every_control_this_process_schedules_has_a_runner_saying_what_it_needs() -> None:
    """**The list and the registry have to stay the same length or the report is a fiction.**

    A control with no runner at all would be found owed on every tick and started by nothing,
    and `runner_gaps` would not mention it, because it iterates the runners. A runner with no
    control is a sentence about work nobody needs.

    Delete this and adding a control to the registry produces a scheduler that silently skips
    it."""
    assert {one.name for one in RUNNERS} == {one.name for one in schedulable()}
    assert "audit_anchor" not in {one.name for one in RUNNERS}, "an external timer runs it"


def test_every_control_the_schedule_cannot_start_yet_says_what_it_is_waiting_for() -> None:
    """**The honest state on 2026-09-09, asserted so it cannot quietly stay that way.**

    Every control entry point in the registry is a policy function taking its inputs, and
    nothing in this system gathers those inputs, so a scheduler alone does not switch the
    eleven orphans on. This test will fail on the day the first control is wired, and that
    failure is the notification: the number here comes down by one and the module header stops
    being true in that respect.

    Asserted as a count and a name list rather than as "at least one", because "some controls
    are unwired" is a sentence that stays true for ever.

    **Twelve on 2026-09-15**, when the worker's schedule began starting the retention sweep and
    the spend report refresh, which are the two controls this list no longer names.

    **Eleven later the same day**, when `knowledge_reverification` was given the store its
    sentence here said it waited for, and a runner that reads it.

    **Ten on 2026-09-17**, when `outbox_dispatch` was given the sender, the resolver and the
    worker's reader of signing secrets its sentence here said nothing implemented.

    **Nine later the same day**, when `canary_run` was given the askers its sentence here said it
    waited for, as every reach the install holds, and a runner that asks as them.

    Delete this and the gap report can go empty because the list went empty."""
    found = runner_gaps()

    assert len(found) == 9
    assert not any("outbox_dispatch" in one for one in found)
    assert not any("canary_run" in one for one in found)
    assert all("cannot be started yet: it needs" in one for one in found)
    assert not any("retention_sweep" in one for one in found)
    assert not any("spend_report_refresh" in one for one in found)
    assert not any("knowledge_reverification" in one for one in found)


def test_a_control_with_no_runner_is_reported_rather_than_skipped_in_silence() -> None:
    """The branch that fires when the two lists drift, which the test two up makes impossible
    in the real tree and which therefore no real run can reach.

    Delete this and the branch that catches a registry addition is never executed, which is
    this repository's most common defect."""
    found = runner_gaps(controls=[a_control("newcomer")], runners=RUNNERS)

    assert any("has no runner at all" in one for one in found)
    assert any("newcomer" in one for one in found)


def test_a_runner_for_a_control_this_process_no_longer_schedules_is_reported() -> None:
    """The other direction. A control moved onto an external timer leaves a runner behind, and
    a runner that will never be dispatched to is a sentence somebody maintains for nothing.

    Delete this and moving a control to a route leaves dead work in this module."""
    found = runner_gaps(
        controls=[a_control("sweep")],
        runners=[Runner(name="sweep", needs="x"), Runner(name="gone", needs="y")],
    )

    assert any("is either dead or the registry has moved it" in one for one in found)


def test_a_runner_that_can_neither_run_nor_say_what_it_needs_is_refused() -> None:
    """A blank runner is indistinguishable from a control somebody forgot, and it would be
    counted as present by the length check above while doing nothing and reporting nothing.

    Delete this and the gap list can be padded with entries that say nothing."""
    with pytest.raises(RunnerError, match="does not say what it needs"):
        Runner(name="sweep")


def test_a_runner_that_can_run_and_also_says_what_it_needs_is_refused() -> None:
    """The positive-shaped mistake: somebody wires a control and leaves the sentence behind, so
    the gap report goes on naming work that is done.

    Delete this and a wired control can stay on the list of unwired ones for ever."""
    with pytest.raises(RunnerError, match="is wired and is not"):
        Runner(name="sweep", needs="something", run=lambda _now, _report_only, _url: "done")


def test_asking_for_a_runner_that_does_not_exist_refuses_rather_than_answering_none() -> None:
    """A caller handed None writes `if runner is None: return` and the control silently stops
    being scheduled, which is the failure this whole area exists to report.

    Delete this and a typo in a control name is a mechanism that quietly stops running."""
    with pytest.raises(RunnerError, match="no runner named"):
        runner_for("not_a_control")

    assert runner_for("retention_sweep").name == "retention_sweep"


# --- runs that did not come back ---------------------------------------------------------


def test_a_run_that_started_and_never_finished_is_reported_once_it_is_old_enough() -> None:
    """A row with a start and no finish is either a run still going or a process that died
    holding it, and this does not pretend to tell them apart: the lock does. What it answers
    is which are old enough to be worth asking about.

    The boundary is asserted on both sides, because a check that reports everything and one
    that reports nothing both pass a test of one side.

    Delete this and a control that never returns is invisible for as long as nobody looks."""
    just_now = {"sweep": NOW - STALLED_AFTER}
    older = {"sweep": NOW - STALLED_AFTER - timedelta(seconds=1)}

    assert stalled_runs(just_now, now=NOW) == ()
    assert stalled_runs(older, now=NOW) == ("sweep",)


def test_a_stall_threshold_of_nothing_would_call_every_run_stalled() -> None:
    """Zero or less means a run is stalled the instant it starts, so every tick reports every
    control as stuck and the signal is worth nothing.

    Delete this and the threshold can be configured to a value that makes the check noise."""
    with pytest.raises(RunnerError, match="every run the moment it starts"):
        stalled_runs({}, now=NOW, after=timedelta(0))


# --- the loop's own clock ----------------------------------------------------------------


def test_the_next_tick_is_aligned_to_the_interval_rather_than_added_to_now() -> None:
    """**Drift is the failure and every individual tick looks fine while it happens.**

    Adding the interval to the moment the tick finished pushes every later tick further out by
    however long the work took, so a one-minute control ends up running every seventy seconds
    by the end of a day and nothing reports a miss.

    Delete this and the cadence quietly becomes the cadence plus the work."""
    ragged = NOW + timedelta(seconds=7)

    assert next_tick(now=ragged) == NOW + TICK
    assert next_tick(now=NOW) == NOW + TICK
    assert next_tick(now=NOW + timedelta(seconds=29)) == NOW + TICK


def test_a_tick_of_nothing_would_wake_the_loop_continuously() -> None:
    """Zero or less is a loop with no wait in it, which is a busy wait against the database.

    Delete this and the tick can be configured to a value that spins."""
    with pytest.raises(RunnerError, match="wake the loop continuously"):
        next_tick(now=NOW, tick=timedelta(0))


# --- the registry has not been told anything is wired ------------------------------------


def test_the_registry_still_reports_every_orphan_this_runner_has_not_wired() -> None:
    """**Only what this runner genuinely calls may leave the orphan list.**

    `brain.ops.controls` reads `ast.Call` nodes and its own docstring says it cannot resolve a
    callable passed as an argument. So a dispatch table of function references would run the
    controls while the registry went on reporting that nothing calls them, which is the same
    lie one layer down, and this test is what would catch it: the day a runner genuinely calls
    a control, this fails and the registry row has to move with it.

    **The figure came down from eleven to ten on 2026-09-11 and this runner is not why.**
    `brain.console.staff_source_view` became the first caller of the roster dry run, so
    `directory_sync` left the orphan list for the state between, which is a caller that nothing
    runs on a schedule. `runner_gaps` is still twelve, asserted above, because what that
    control is waiting for has not changed: somebody has to gather its inputs. The two figures
    moving apart is the point of keeping both.

    **And to nine on 2026-09-14, for the same reason one screen along.**
    `brain.console.recovery_view` asks `drill_due`, so `restore_drill` has a caller that nothing
    runs on a schedule, and nothing performs a drill, which is what its runner still waits for.

    **And back to ten on 2026-09-15, by an arrival rather than a regression.**
    `outbox_dispatch` was registered the day `brain.ops.outbox_store` was written, as a
    control nothing calls, so the control count and the runner gaps each rose by one too.

    **And to nine on 2026-09-15, and this runner is why.** `start_control` calls the retention
    sweep's runner and the worker's schedule calls `start_control`, so `retention_sweep` left the
    orphan list for a reason this file can name. `spend_report_refresh` arrived the same day
    already wired, so the control count rose to fifteen and the orphan count did not.

    **And to eight later that day, for the same reason.** `start_control` calls the
    re-verification runner, so `knowledge_reverification` left the list too.

    **And sixteen controls on 2026-09-17, with eight orphans still.** `erasure_queue` arrived
    already wired, the way `spend_report_refresh` did, so the control count rose and the orphan
    count did not.
    **And to seven on 2026-09-17, for the same reason.** `start_control` calls the webhook
    dispatch runner, so `outbox_dispatch` left the list.

    **And to six later that day, for the same reason.** `start_control` calls the canary runner,
    so `canary_run` left the list.

    **And seventeen controls later still, with six orphans.** `vault_token_renewal` arrived already
    wired, the way `erasure_queue` did.

    **And eighteen controls later that day, with six orphans still.** `automation_run` arrived
    already wired, the way `erasure_queue` did.

    **And nineteen controls later that day, with six orphans still.** `connector_sync` arrived
    already wired, the way `erasure_queue` did, so the control count rose and the orphan count did
    not.

    **And twenty controls later that day, with six orphans still.** `vault_audit_ship` arrived
    already wired, with the worker overlay's read-only mount of the vault's log.

    Delete this and the scheduler can start running mechanisms the handover pack still
    describes as unwired."""
    from brain.ops.controls import orphans

    assert len(orphans()) == 6
    assert "canary_run" not in {one.name for one in orphans()}
    assert "outbox_dispatch" not in {one.name for one in orphans()}
    assert "knowledge_reverification" not in {one.name for one in orphans()}
    assert "directory_sync" not in {one.name for one in orphans()}
    assert "restore_drill" not in {one.name for one in orphans()}
    assert len(CONTROLS) == 20


# --- the dispatch the worker's schedule starts controls through ---------------------------


def test_the_dispatch_names_exactly_the_runners_that_can_run() -> None:
    """The match arms in `start_control`, read from its source, are the runners with a `run`.

    Delete this and a runner could be given a `run` with no arm, which the worker would refuse
    on every tick, or an arm could outlive its runner, which is a control started by a name the
    table no longer describes."""
    tree = ast.parse(inspect.getsource(start_control))
    arms = {
        node.pattern.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.match_case)
        and isinstance(node.pattern, ast.MatchValue)
        and isinstance(node.pattern.value, ast.Constant)
    }

    assert arms == {one.name for one in RUNNERS if one.run is not None}
    assert arms == {
        "retention_sweep",
        "knowledge_reverification",
        "spend_report_refresh",
        "outbox_dispatch",
        "erasure_queue",
        "canary_run",
        "vault_token_renewal",
        "automation_run",
        "connector_sync",
        "vault_audit_ship",
    }


def test_the_nag_runner_asked_for_a_report_records_nothing_and_reaches_no_database() -> None:
    """Report-only mode: the runner says so before it opens anything, which is why a URL that
    points nowhere is enough here.

    Delete this and a runner could ignore the mode it was handed, which is the property a
    destructive control's safety rests on being true of every runner."""
    said = start_control(
        "knowledge_reverification",
        now=NOW,
        report_only=True,
        database_url="postgresql://nobody@127.0.0.1:1/none",
    )

    assert said.startswith("report only: no re-verification nag was recorded.")
    assert A_NAG_IN_REPORT_ONLY_MODE_RECORDS_NOTHING in said


def test_the_dispatch_runner_asked_for_a_report_sends_nothing_and_reaches_no_database() -> None:
    """Report-only mode for the webhook dispatch: declined before any database or vault is asked,
    which is why a URL that points nowhere is enough here.

    Delete this and the dispatch runner could ignore the mode it was handed, which is the property
    a destructive control's safety rests on being true of every runner."""
    said = start_control(
        "outbox_dispatch",
        now=NOW,
        report_only=True,
        database_url="postgresql://nobody@127.0.0.1:1/none",
    )

    assert said.startswith("report only: no webhook delivery was sent.")
    assert A_DISPATCH_IN_REPORT_ONLY_MODE_SENDS_NOTHING in said


def test_a_control_with_nothing_to_run_is_refused_by_name_with_what_it_needs() -> None:
    """A registered control with no runner that can run is refused with its own sentence, and a
    name nothing registers is refused by `runner_for`.

    Delete this and a control the schedule cannot start could be answered with an empty string,
    which the worker would record as a run that succeeded."""
    with pytest.raises(RunnerError, match="cannot be started by this process: it needs"):
        start_control("backup_exposure", now=NOW, report_only=False, database_url="postgresql://x")
    with pytest.raises(RunnerError, match="no runner named"):
        start_control("no_such_control", now=NOW, report_only=False, database_url="postgresql://x")


@contextmanager
def an_install(database: str) -> Iterator[str]:
    """A database with the spend report and the control-run table, through `0037`."""
    url = fresh(database)
    try:
        migrate(database, "stamp", "0024")
        migrate(database, "upgrade", "0025")
        migrate(database, "stamp", "0033")
        migrate(database, "upgrade", "0037")
        yield url
    finally:
        drop(database)


def test_the_refresh_runner_rebuilds_the_view_and_records_when_it_did() -> None:
    """Started by name through the dispatch: the view is rebuilt and its refresh is recorded.

    Delete this and the runner the schedule starts could return a sentence without having
    refreshed anything, and the schedule would record a run that did nothing as ok."""
    with an_install("brain_schedule_runner_refresh") as url:
        said = start_control("spend_report_refresh", now=NOW, report_only=False, database_url=url)

        assert said.startswith("ops.spend_daily rebuilt")
        assert sql(
            url, "SELECT count(*) FROM ops.report_refresh WHERE view_name = 'ops.spend_daily'"
        ) == [(1,)]


def test_the_refresh_runner_asked_for_a_report_rebuilds_nothing() -> None:
    """Report-only mode: the runner says so and no refresh is recorded.

    Delete this and a runner could ignore the mode it was handed, which is the property a
    destructive control's safety rests on being true of every runner."""
    with an_install("brain_schedule_runner_refresh_report") as url:
        said = spend_report_refresh(NOW, True, url)

        assert A_REFRESH_IN_REPORT_ONLY_MODE_REBUILDS_NOTHING in said
        assert sql(url, "SELECT count(*) FROM ops.report_refresh") == [(0,)]


def test_the_retention_runner_sweeps_the_database_it_is_given_and_reports_every_store() -> None:
    """Started by name through the dispatch, in report-only mode: every store has a line.

    Delete this and the runner could open a connection somewhere other than the URL it was given,
    or return before the report is built, with the loop's own tests still green.

    The sweep reads its holds and writes its report since `0049`, which this chain stops short of,
    so those tables are built from their models as `tests/unit/test_control_task.py` builds them.
    Without them the runner raised on `obs.legal_hold` in CI from the day it read holds, and was
    green on every machine with no server, where this test skips."""
    with an_install("brain_schedule_runner_retention") as url:
        add_modelled(url, RETENTION_TABLES)
        said = start_control("retention_sweep", now=NOW, report_only=True, database_url=url)

    lines = said.splitlines()
    for store in Store:
        assert any(line.startswith(store.value) for line in lines), store


def test_the_automation_runner_asked_for_a_report_runs_nothing_and_reaches_no_database() -> None:
    """Report-only mode: the runner says so before it opens anything, which is why a URL that
    points nowhere is enough here.

    Delete this and the automation runner could ignore the mode it was handed, which is the
    property a destructive control's safety rests on being true of every runner."""
    said = start_control(
        "automation_run",
        now=NOW,
        report_only=True,
        database_url="postgresql://nobody@127.0.0.1:1/none",
    )

    assert said.startswith("report only: no automation was run.")
