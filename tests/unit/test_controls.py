"""The scheduled control registry, its derived checks, and the alert for one that has not run.

The invariant this serves lives in `tests/invariants/test_no_safety_mechanism_lacks_a_caller.py`
and asserts the property over the real registry. This file tests the machinery underneath it
against registries built for the purpose, which is the only way to see it say no.

Task ids: M37.4.3.4, M37.5.1.1, M37.5.1.2, M37.5.1.3
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from brain.ops.alerting import Severity
from brain.ops.controls import (
    CONTROLS,
    ESCALATE_AFTER_UNANSWERED,
    HANDOVER_RESIDUE,
    MISSED_RUN_GRACE,
    NOT_A_SCHEDULE,
    Control,
    ControlsError,
    Invocation,
    Missed,
    advisories,
    cadence_is_declared_elsewhere,
    call_sites,
    control,
    externally_scheduled,
    handover_lines,
    is_declared,
    measured_invocation,
    missing_symbols,
    orphans,
    overdue,
    recurrence_predicates,
    registry_gaps,
    route_is_declared,
    runbook_for,
    runbook_gaps,
)

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def _control(**changes: object) -> Control:
    """A minimal valid control, with whatever the test needs changed.

    Built here rather than by copying a real row, so that a test asserting a refusal is not
    accidentally satisfied by something else on the real row being wrong.
    """
    fields: dict[str, object] = {
        "name": "example",
        "symbols": ("brain.ops.canaries:due",),
        "guards": "an example guarantee",
        "lost_silently": "the example guarantee, with nothing saying so",
        "every": timedelta(hours=1),
        "severity": Severity.NOTICED,
        "invoked_by": Invocation.NOTHING,
    }
    fields.update(changes)
    return Control(**fields)  # type: ignore[arg-type]


# --------------------------------------------------------------------- the declared shape
def test_a_control_with_no_name_is_refused() -> None:
    """Delete this and a row can be added that cannot be alerted on, listed or handed over.

    Both the empty string and a string of spaces, because a validator tested only with `""`
    passes with `strip()` removed.
    """
    with pytest.raises(ControlsError, match="no name"):
        _control(name="")
    with pytest.raises(ControlsError, match="no name"):
        _control(name="  ")


def test_a_control_naming_no_function_is_refused() -> None:
    """Delete this and a row can exist that nothing can be asked about, which is the only
    question this registry is for."""
    with pytest.raises(ControlsError, match="names no function"):
        _control(symbols=())


def test_a_symbol_that_is_not_module_and_function_is_refused() -> None:
    """Delete this and a row can name something nothing resolves.

    A symbol nothing can resolve has no callers either, so it presents as an orphan on a
    registry where twelve rows genuinely are orphans, and it would be believed.
    """
    with pytest.raises(ControlsError, match="not module:function"):
        _control(symbols=("brain.ops.canaries.due",))
    with pytest.raises(ControlsError, match="not module:function"):
        _control(symbols=("brain.ops.canaries:DUE",))


def test_a_control_that_does_not_say_what_it_guards_is_refused() -> None:
    """Delete this and the registry becomes a list of module names.

    A scheduled job nobody can explain is the one that gets disabled during an incident and
    never restored, which is the argument `brain.ops.storage.Bucket.retention_reason` makes
    about its own field.
    """
    with pytest.raises(ControlsError, match="does not say what it guards"):
        _control(guards="")
    with pytest.raises(ControlsError, match="does not say what it guards"):
        _control(guards="   ")


def test_a_control_that_does_not_say_what_is_lost_is_refused() -> None:
    """Delete this and an alert arrives with nothing saying why the mechanism matters."""
    with pytest.raises(ControlsError, match="does not say what stops being true"):
        _control(lost_silently="")
    with pytest.raises(ControlsError, match="does not say what stops being true"):
        _control(lost_silently=" ")


def test_a_cadence_that_is_always_owed_is_refused() -> None:
    """Delete this and a control can be added that is permanently overdue and therefore
    permanently ignored, which reaches the same place as having no alert at all while
    looking healthy in the registry."""
    with pytest.raises(ControlsError, match="always owed"):
        _control(every=timedelta(0))
    with pytest.raises(ControlsError, match="always owed"):
        _control(every=timedelta(seconds=-1))


def test_a_control_started_from_outside_must_name_the_route_and_the_schedule() -> None:
    """Delete this and a row can claim it is started by something outside the process while
    naming nothing that could be checked, which is a claim resting on whoever wrote it."""
    with pytest.raises(ControlsError, match="names no route or no schedule"):
        _control(invoked_by=Invocation.ON_A_ROUTE)
    with pytest.raises(ControlsError, match="names no route or no schedule"):
        _control(invoked_by=Invocation.ON_A_ROUTE, route="/api/audit/anchor")


def test_a_cadence_source_that_is_not_a_name_is_refused() -> None:
    """Delete this and provenance becomes a sentence rather than a claim.

    `cadence_from` exists so that nothing can say where its number came from without the
    check being able to look. A value that is not `module:name` cannot be looked up, so the
    field would read as evidence and be prose.
    """
    with pytest.raises(ControlsError, match="not module:name"):
        _control(cadence_from="the canaries module")


def test_the_entry_point_is_the_first_symbol() -> None:
    """Delete this and the entry point can be stored separately from the list it is drawn
    from, which is two fields that can disagree about which function a scheduler calls."""
    one = _control(symbols=("brain.ops.canaries:due", "brain.ops.canaries:scan_stores"))
    assert one.entry_point == "brain.ops.canaries:due"


# ----------------------------------------------------------------- reading the source
def test_a_symbol_the_tree_does_not_declare_is_found() -> None:
    """Delete this and a typo in the registry reads as a mechanism nothing runs.

    The positive case is asserted beside it, because a check tested only by its refusals is
    satisfied by a function that refuses everything.
    """
    assert is_declared("brain.ops.canaries:due")
    assert is_declared("brain.ops.canaries:CANARY_INTERVAL_SECONDS")
    assert not is_declared("brain.ops.canaries:nothing_of_the_sort")
    assert not is_declared("brain.ops.no_such_module:due")
    assert missing_symbols(_control(symbols=("brain.ops.canaries:nope",))) == (
        "brain.ops.canaries:nope",
    )
    assert missing_symbols(_control()) == ()


def test_a_name_bound_inside_a_function_is_not_declared_at_module_level() -> None:
    """Delete this and the registry can name something no scheduler could import.

    `brain.docs_routes` imports `take_anchor` inside a function body, so a check that walked
    the whole tree rather than the module's top level would report every locally bound name
    as importable from that module.
    """
    assert not is_declared("brain.docs_routes:take_anchor")
    assert is_declared("brain.audit.anchor:take_anchor")


def test_a_call_from_inside_a_function_body_is_still_a_call_site() -> None:
    """Delete this and the one control that actually runs reads as an orphan.

    `brain.docs_routes.audit_anchor` imports and calls `take_anchor` inside the handler, and
    a scan that only looked at module-level imports would have found nothing.
    """
    assert "brain.docs_routes" in call_sites("brain.audit.anchor:take_anchor")


def test_a_function_called_only_from_its_own_module_has_no_call_site() -> None:
    """Delete this and a module with a private helper reports itself as wired.

    A function called from the file that defines it is an implementation detail of that file
    rather than something running it on a schedule.
    """
    assert call_sites("brain.ops.canaries:leaked_fields") == ()


def test_the_route_is_read_off_the_decorator_and_not_out_of_the_prose() -> None:
    """Delete this and a check can be satisfied by a docstring.

    `brain.docs_routes` names the workflow that reads the anchor route in the handler's own
    docstring, so a scan of the file's text would pass whether or not the route existed.
    This repository has had that failure twice already, in `sweep_tool_registry` and in a
    test searching for `filter="data"`.
    """
    assert route_is_declared("/api/audit/anchor") == ("brain.docs_routes",)
    assert route_is_declared("/api/nothing/here") == ()


def test_every_recurrence_predicate_is_module_level_and_named_for_being_due() -> None:
    """Delete this and the converse check silently stops finding things.

    The set is asserted against two known members and two known non-members rather than
    against itself: `brain.ops.retention.RetentionReport.due` is a property of a value and
    `brain.ops.jobs.JobRecord.is_due` is a method, and including either would put rows in the
    list that no scheduler could ever call.
    """
    found = recurrence_predicates()
    assert "brain.ops.canaries:due" in found
    assert "brain.ops.recovery:drill_due" in found
    assert not any(one.startswith("brain.ops.retention:") for one in found)
    assert not any(one.startswith("brain.ops.jobs:") for one in found)


def test_a_missing_schedule_file_is_reported() -> None:
    """Delete this and a control can claim an external schedule that is not there.

    The loud one of the three, and the one a rename produces.
    """
    absent = _control(
        invoked_by=Invocation.ON_A_ROUTE,
        route="/api/audit/anchor",
        schedule_file=".github/workflows/not-a-file.yml",
    )
    assert any("does not exist" in one for one in externally_scheduled(absent))


def test_a_schedule_file_with_no_cron_entry_is_reported(tmp_path: Path) -> None:
    """Delete this and a workflow that only runs when somebody presses the button reads as a
    schedule.

    That is the state a schedule decays into while somebody is debugging it, and nothing
    about the file afterwards says it used to fire on its own.
    """
    workflow = tmp_path / "manual.yml"
    workflow.write_text(
        "on:\n  workflow_dispatch:\nsteps:\n  - run: curl /api/audit/anchor\n",
        encoding="utf-8",
        newline="\n",
    )
    manual = _control(
        invoked_by=Invocation.ON_A_ROUTE, route="/api/audit/anchor", schedule_file="manual.yml"
    )
    findings = externally_scheduled(manual, tmp_path)
    assert any("carries no schedule entry" in one for one in findings)


def test_a_schedule_that_does_not_name_the_route_is_reported(tmp_path: Path) -> None:
    """Delete this and a scheduled workflow pointed at something else reads as wired.

    The failure a reader cannot see from either end: the workflow is scheduled, the route
    exists, and they are not connected to each other.
    """
    workflow = tmp_path / "elsewhere.yml"
    workflow.write_text(
        'on:\n  schedule:\n    - cron: "17 */6 * * *"\nsteps:\n  - run: curl /api/other\n',
        encoding="utf-8",
        newline="\n",
    )
    pointed_away = _control(
        invoked_by=Invocation.ON_A_ROUTE,
        route="/api/audit/anchor",
        schedule_file="elsewhere.yml",
    )
    findings = externally_scheduled(pointed_away, tmp_path)
    assert any("does not name" in one for one in findings)


def test_a_workflow_with_a_cron_and_the_route_passes(tmp_path: Path) -> None:
    """Delete this and the three refusals above are satisfied by a function that refuses
    every workflow file there is."""
    workflow = tmp_path / "good.yml"
    workflow.write_text(
        'on:\n  schedule:\n    - cron: "17 */6 * * *"\nsteps:\n  - run: curl /api/audit/anchor\n',
        encoding="utf-8",
        newline="\n",
    )
    wired = _control(
        invoked_by=Invocation.ON_A_ROUTE, route="/api/audit/anchor", schedule_file="good.yml"
    )
    assert externally_scheduled(wired, tmp_path) == ()


def test_the_word_cron_in_a_comment_is_not_a_schedule(tmp_path: Path) -> None:
    """Delete this and a workflow explaining why it no longer has a cron passes as one that
    does.

    The line rather than the word, which is the difference between reading a file for a
    schedule and reading it for a mention of one.
    """
    workflow = tmp_path / "commented.yml"
    workflow.write_text(
        "# the cron was removed while debugging\non:\n  workflow_dispatch:\n"
        "steps:\n  - run: curl /api/audit/anchor\n",
        encoding="utf-8",
        newline="\n",
    )
    one = _control(
        invoked_by=Invocation.ON_A_ROUTE, route="/api/audit/anchor", schedule_file="commented.yml"
    )
    findings = externally_scheduled(one, tmp_path)
    assert any("carries no schedule entry" in finding for finding in findings)


def test_a_control_is_in_process_only_when_every_part_of_it_is_called() -> None:
    """Delete this and a system asks whether a sweep is due, for ever, and never sweeps.

    A control is usually a predicate plus the work, and counting it as wired because one of
    them has a caller is the failure being avoided. `due_for_reverification` genuinely has a
    caller and `open_reverification_tasks` does not, so the pair measures as unreached.
    """
    partly = _control(
        symbols=(
            "brain.knowledge.verification:open_reverification_tasks",
            "brain.knowledge.item:due_for_reverification",
        )
    )
    assert call_sites("brain.knowledge.item:due_for_reverification") != ()
    assert call_sites("brain.knowledge.verification:open_reverification_tasks") == ()
    assert measured_invocation(partly) is Invocation.NOTHING


def test_a_route_backed_control_measures_as_on_a_route_and_not_as_in_process() -> None:
    """Delete this and the one control that runs is reported as running in this process.

    Technically true and operationally wrong: nothing in this process calls that route, and
    the thing that does is a cron file outside the tree. A reader following the in-process
    answer would go looking for a scheduler in Python and find none.
    """
    anchor = control("audit_anchor")
    assert measured_invocation(anchor) is Invocation.ON_A_ROUTE
    assert call_sites(anchor.entry_point) == ("brain.docs_routes",)
    assert route_is_declared(anchor.route) == ("brain.docs_routes",)


def test_a_route_that_does_not_reach_the_control_is_not_an_invocation() -> None:
    """Delete this and "a route exists" and "something calls this" become one claim.

    They are two unrelated facts and either can be true without the other connecting them.
    A control declared as reached by a route in one module while its function is called from
    another the schedule never touches would measure as started from outside, with no path
    between the two ends. Here the route is the anchor's and the symbol is one that
    `brain.docs_routes` does not call.
    """
    disconnected = _control(
        symbols=("brain.knowledge.item:due_for_reverification",),
        invoked_by=Invocation.ON_A_ROUTE,
        route="/api/audit/anchor",
        schedule_file=".github/workflows/anchor.yml",
    )
    assert call_sites("brain.knowledge.item:due_for_reverification") != ()
    assert route_is_declared("/api/audit/anchor") == ("brain.docs_routes",)
    assert measured_invocation(disconnected) is Invocation.IN_PROCESS


# ------------------------------------------------------------------- the registry itself
def test_a_control_whose_only_caller_is_itself_uncalled_is_reported() -> None:
    """Delete this and a chain of three uncalled functions reads as wired at every link.

    The check exists because `brain.knowledge.verification.open_reverification_tasks` is
    exactly that shape, and asserting only that it currently finds nothing would leave a
    function that could return nothing for every input. This is the case it was written for,
    declared as in-process so the finding can be produced.
    """
    from brain.ops.controls import chains_worth_checking

    inner_only = _control(
        symbols=("brain.knowledge.item:due_for_reverification",),
        invoked_by=Invocation.IN_PROCESS,
    )
    findings = chains_worth_checking((inner_only,))
    assert any("as unreached as the control" in one for one in findings)
    assert chains_worth_checking((control("audit_anchor"),)) == ()


def test_a_duplicate_control_name_is_reported() -> None:
    """Delete this and two rows alert as one, and which of them a lookup returns depends on
    the order somebody wrote them in."""
    twice = (_control(), _control(guards="a different guarantee"))
    assert any("declared twice" in one for one in registry_gaps(twice))


def test_a_declared_invocation_that_disagrees_with_the_source_is_reported() -> None:
    """Delete this and the registry becomes a document rather than a check.

    Both directions. A control recorded as running that nothing calls is the console lying
    about the estate; a control recorded as an orphan that something now calls is a record
    that has fallen behind good news, which is how a record stops being read.
    """
    overclaiming = (_control(invoked_by=Invocation.IN_PROCESS),)
    assert any("recorded as in_process" in one for one in registry_gaps(overclaiming))
    understating = (
        _control(
            name="anchor_copy",
            symbols=("brain.audit.anchor:take_anchor",),
            invoked_by=Invocation.NOTHING,
        ),
    )
    assert any("the source says" in one for one in registry_gaps(understating))


def test_a_cadence_source_the_tree_no_longer_declares_is_reported() -> None:
    """Delete this and a row can keep claiming a provenance for a number after the constant
    it came from has been deleted, which leaves this registry as the only statement of the
    cadence with nothing saying so."""
    stale = (_control(cadence_from="brain.ops.canaries:NO_SUCH_INTERVAL"),)
    assert any("does not declare" in one for one in registry_gaps(stale))


def test_a_route_no_module_declares_is_reported() -> None:
    """Delete this and a schedule can be pointed at a route that does not exist, and the
    workflow will go on succeeding: a request that 404s is still a request."""
    nowhere = (
        _control(
            invoked_by=Invocation.ON_A_ROUTE,
            route="/api/nothing/here",
            schedule_file=".github/workflows/anchor.yml",
        ),
    )
    assert any("no module declares that route" in one for one in registry_gaps(nowhere))


def test_a_recurrence_predicate_belonging_to_nothing_is_reported() -> None:
    """Delete this and a scheduled mechanism can be added that nothing describes.

    The converse, asked of a registry that describes none of the tree's predicates so the
    finding can be seen rather than being absent because everything happens to be covered.
    """
    empty = (_control(symbols=("brain.ops.canaries:scan_stores",)),)
    findings = registry_gaps(empty)
    assert any("brain.ops.canaries:due" in one for one in findings)
    assert any("NOT_A_SCHEDULE" in one for one in findings)


def test_an_exemption_naming_nothing_would_be_reported() -> None:
    """Delete this and the exemption list rots into a hole.

    An entry naming a deleted function is an exemption waiting to cover whatever takes that
    name next, and the next `report_is_due` will not necessarily be a growth trigger. Asked
    of the real list too, which is the assertion that keeps it perishable.
    """
    assert set(NOT_A_SCHEDULE) <= set(recurrence_predicates())
    assert registry_gaps() == ()


def test_control_refuses_a_name_nothing_declares() -> None:
    """Delete this and a caller with a stale name in their hand is told nothing is wrong."""
    with pytest.raises(ControlsError, match="no control is called"):
        control("a_control_that_never_existed")
    assert control("audit_anchor").name == "audit_anchor"


def test_a_cadence_taken_from_elsewhere_is_distinguished_from_one_written_here() -> None:
    """Delete this and a control can look as though its number came from beside the code.

    This was first written as a comparison of values, which two controls satisfy by
    coincidence: a day is a day, so a retention sweep matched the knowledge cadence and
    reported a provenance it did not have. Provenance is not a property of a number.
    """
    assert cadence_is_declared_elsewhere(control("canary_run"))
    assert not cadence_is_declared_elsewhere(control("audit_anchor"))
    assert not cadence_is_declared_elsewhere(_control(every=timedelta(days=1)))


def test_the_advisories_name_every_orphan_and_every_local_cadence() -> None:
    """Delete this and the honest state of the estate becomes a count nobody prints.

    A count is a number somebody reads once; a list is a thing somebody works down. Every
    orphan appears by name, and so does every control whose cadence exists nowhere else.
    """
    lines = advisories()
    for one in orphans():
        assert any(line.startswith(f"{one.name} guards") for line in lines)
    assert any("audit_anchor runs every" in line for line in lines)


def test_nothing_an_installed_system_would_call_reads_the_repository_from_disk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete this and the alerting stops working on a container without a source tree.

    Half of this module reads the repository, which is right for the checks CI runs and wrong
    for anything a running installation asks. A container is built from a wheel; `REPO` there
    points at whatever sits four levels above the installed package, which is site-packages
    or nothing. So the functions an operator's estate depends on have to be pure, and this is
    what keeps them that way: the check runs each one against a directory that does not exist
    and expects an answer rather than an error.
    """
    from brain.ops import controls as module

    nowhere = Path("no-such-repository-anywhere")
    monkeypatch.setattr(module, "REPO", nowhere)
    monkeypatch.setattr(module, "SRC", nowhere / "src" / "brain")
    # The caches are keyed on the argument, and every reader below passes none, so a result
    # from the real tree would still be sitting there to be returned. Clearing them is what
    # makes a disk read fail rather than quietly succeed from before, and clearing them again
    # afterwards is what stops a cache full of nowhere outliving this test: monkeypatch puts
    # the paths back and cannot know that a memoised answer was taken against the old ones.
    caches = (module._sources, module._parsed, module._call_index)
    for cached in caches:
        cached.cache_clear()
    try:
        assert len(orphans()) == len(CONTROLS) - 1
        assert len(handover_lines()) == len(CONTROLS)
        assert advisories()
        assert overdue(last_run={}, now=NOW)
        assert runbook_for(control("canary_run"), Missed.UNREACHABLE).then_do
        # And the other half genuinely does read, so the check above is not passing because
        # nothing in this module ever touches a file.
        assert recurrence_predicates() == ()
    finally:
        for cached in caches:
            cached.cache_clear()


def test_a_cadence_restated_from_a_cron_expression_is_said_out_loud() -> None:
    """Delete this and the one gap this registry cannot close stops being visible.

    The anchor's schedule is a cron expression in a workflow file and the figure here is a
    restatement of it, not a derivation from it. Nothing compares the two, so somebody moving
    the cron from six-hourly to twelve-hourly leaves the alerting window behind and the alert
    is quiet for exactly as long as the mistake lasts. It is said rather than closed, because
    closing it means a cron parser in a module that ships.
    """
    lines = advisories()
    assert any(
        "audit_anchor's schedule is a cron expression" in line and "nothing compares" in line
        for line in lines
    )
    assert [one.name for one in CONTROLS if one.schedule_file] == ["audit_anchor"]


# ------------------------------------------------------------ a control that has not run
def test_a_control_that_ran_within_its_grace_is_not_reported() -> None:
    """Delete this and the alert fires on the ordinary jitter of a mechanism that works.

    A twelve-hourly sweep that runs at 09:00 and then at 09:04 is a sweep that is working,
    and an alert on it is how an operator learns to ignore the whole category. The threshold
    is the cadence times `MISSED_RUN_GRACE` and this pins both sides of it.
    """
    one = control("audit_anchor")
    assert MISSED_RUN_GRACE > 1
    assert one.alert_after == one.every * MISSED_RUN_GRACE
    just_inside = overdue(last_run={one.name: NOW - one.alert_after}, now=NOW, controls=(one,))
    assert just_inside == ()
    one_interval = overdue(last_run={one.name: NOW - one.every}, now=NOW, controls=(one,))
    assert one_interval == ()
    outside = overdue(
        last_run={one.name: NOW - one.alert_after - timedelta(seconds=1)},
        now=NOW,
        controls=(one,),
    )
    assert [row.missed for row in outside] == [Missed.BEHIND]


def test_one_missed_run_is_silent_and_two_consecutive_misses_alert() -> None:
    """Delete this and `MISSED_RUN_GRACE` can be tuned to any value above one.

    The behaviour is what the constant means, and asserting `alert_after == every * grace`
    compares the constant against itself: both sides move together and the test is green for
    every value it could hold. These two readings bracket it exactly. One missed run is a
    deployment, a restart or a busy host and must be silent; two in a row is the schedule
    being gone and must not be.
    """
    one = control("audit_anchor")
    after_one_miss = overdue(
        last_run={one.name: NOW - one.every - timedelta(seconds=1)}, now=NOW, controls=(one,)
    )
    assert after_one_miss == ()
    after_two_misses = overdue(
        last_run={one.name: NOW - one.every * 2 - timedelta(seconds=1)},
        now=NOW,
        controls=(one,),
    )
    assert [row.missed for row in after_two_misses] == [Missed.BEHIND]


def test_the_controls_that_wake_somebody_are_the_ones_named_here() -> None:
    """Delete this and a control's severity can be lowered with nothing noticing.

    Severity is a judgement, and a judgement is exactly the thing that gets changed in a hurry
    by whoever is being woken. Pinning the set rather than each row means a change has to be
    argued for in a diff that names it, and the three here are the three whose failure is
    visible outside this installation: a leak the gate should have refused, a stretch of work
    with no copy anywhere, and a side effect that may have been done twice to somebody else's
    system.
    """
    assert {one.name for one in CONTROLS if one.severity is Severity.WOKEN} == {
        "canary_run",
        "backup_exposure",
        "side_effect_resume",
    }
    assert {one.severity for one in CONTROLS} == set(Severity)


def test_the_registry_describes_the_part_of_an_install_the_teardown_enumerates() -> None:
    """Delete this and the handover pack and the teardown stop being about the same thing.

    A scheduled job that fires after the client has left is the residue
    `brain.ops.handover` refuses to certify a handover without, and this registry is the list
    of them. Asserted against that module's own member rather than against a string here, so
    the two cannot drift into describing different halves of an installation.
    """
    from brain.ops.handover import Residue

    assert HANDOVER_RESIDUE is Residue.SCHEDULED_WORK


def test_a_run_recorded_in_the_future_is_not_late() -> None:
    """Delete this and clock skew between the recorder and the reader becomes an alert.

    A timestamp ahead of `now` is skew, and the conservative reading of one is silence, which
    is the reading `brain.ops.denial_alerts.digest` takes for the same shape.
    """
    one = control("audit_anchor")
    ahead = overdue(last_run={one.name: NOW + timedelta(days=9)}, now=NOW, controls=(one,))
    assert ahead == ()


def test_a_control_nothing_calls_is_unreachable_rather_than_late() -> None:
    """Delete this and every orphan alerts for ever as a schedule that did not fire, which
    sends a person to the one place with nothing in it.

    Asserted against a fixture where the control has just run, so lateness cannot be what
    produced the finding.
    """
    orphan = _control()
    rows = overdue(last_run={orphan.name: NOW - timedelta(seconds=1)}, now=NOW, controls=(orphan,))
    assert [row.missed for row in rows] == [Missed.UNREACHABLE]
    assert rows[0].late_by is None


def test_a_control_nobody_records_is_distinguished_from_one_that_has_never_run() -> None:
    """Delete this and two problems with different fixes become one alert.

    Nothing recording the control may mean it is running perfectly and the name on one side
    has been changed; nothing having happened means the schedule is missing. The remedies do
    not overlap.
    """
    wired = control("audit_anchor")
    absent = overdue(last_run={}, now=NOW, controls=(wired,))
    assert [row.missed for row in absent] == [Missed.NOT_RECORDED]
    never = overdue(last_run={wired.name: None}, now=NOW, controls=(wired,))
    assert [row.missed for row in never] == [Missed.NEVER_RUN]


def test_the_loudest_control_is_reported_first() -> None:
    """Delete this and an operator triaging at three in the morning reads a knowledge badge
    above a side effect that may have happened twice.

    Declaration order groups the registry by subject, which is right for reading it and wrong
    for working down an incident.
    """
    rows = overdue(last_run={}, now=NOW)
    severities = [row.severity for row in rows]
    assert severities == sorted(severities, reverse=True)


def test_an_overdue_row_carries_how_late_it_is_only_when_that_is_knowable() -> None:
    """Delete this and a control that has never run reports a lateness computed from nothing.

    There is no last run to subtract from, so any number would be arithmetic over an absence,
    and a number in that field is one somebody quotes.
    """
    wired = control("audit_anchor")
    behind = overdue(
        last_run={wired.name: NOW - wired.alert_after - timedelta(hours=3)},
        now=NOW,
        controls=(wired,),
    )
    assert behind[0].late_by == timedelta(hours=3)
    for missed in (Missed.NOT_RECORDED, Missed.NEVER_RUN):
        rows = overdue(
            last_run={} if missed is Missed.NOT_RECORDED else {wired.name: None},
            now=NOW,
            controls=(wired,),
        )
        assert rows[0].late_by is None


# --------------------------------------------------------------------------- runbooks
def test_every_alert_has_a_runbook_that_names_the_control_and_its_entry_point() -> None:
    """Delete this and a reader receives an alert naming a mechanism they have never heard of
    with nothing saying what it is or where to find it.

    The first check is always the control's own identity, because that is what the reader
    needs before any step below it means anything.
    """
    assert runbook_gaps() == ()
    one = control("retention_sweep")
    book = runbook_for(one, Missed.BEHIND)
    assert one.guards in book.first_check[0]
    assert one.entry_point in book.first_check[0]


def test_a_runbook_escalates_after_the_route_would_have_been_acknowledged() -> None:
    """Delete this and a runbook can be written that climbs while the first responder is
    still inside the time they were given.

    Derived from the route rather than declared, which is what makes
    `brain.ops.alerting.runbook_gaps` green by construction rather than by care.
    """
    from brain.ops.alerting import route_for

    for one in CONTROLS:
        book = runbook_for(one, Missed.BEHIND)
        assert book.escalate_after == (
            route_for(one.severity).acknowledge_within * ESCALATE_AFTER_UNANSWERED
        )
        assert book.escalate_after > route_for(one.severity).acknowledge_within


def test_the_unreachable_runbook_does_not_say_to_start_it_and_move_on() -> None:
    """Delete this and the remedy for an orphan becomes one hand-started run.

    One run does not make a mechanism a control, and a single run is exactly what makes the
    alert look resolved: the next pass finds a recent run and says nothing.
    """
    book = runbook_for(control("retention_sweep"), Missed.UNREACHABLE)
    assert any("does not make it a control" in step for step in book.then_do)
    assert any("Escalate" in step for step in book.then_do)


# --------------------------------------------------------------------------- handover
def test_the_handover_pack_has_one_line_per_control_and_names_what_each_guards() -> None:
    """Delete this and the pack a client is handed stops describing their installation.

    The pack is the artefact this repository never re-checks, so a line that is wrong leaves
    the building and stays wrong for as long as anybody keeps the document.
    """
    lines = handover_lines()
    assert len(lines) == len(CONTROLS)
    for one, line in zip(CONTROLS, lines, strict=True):
        assert line.startswith(f"{one.name}:")
        assert one.guards in line


def test_the_handover_line_for_a_control_nothing_runs_says_so_in_capitals() -> None:
    """Delete this and a client is handed thirteen protections, twelve of which are not
    happening.

    The capital letters are not decoration: the line is read in a list of thirteen, and the
    difference between them has to be visible without reading each one to the end.
    """
    line = handover_lines((_control(),))[0]
    assert "NOTHING" in line
    assert "not currently held" in line


def test_the_handover_line_for_a_wired_control_names_what_starts_it() -> None:
    """Delete this and the pack cannot be checked against anything.

    A client reading "started by nothing" for twelve rows and a name for the thirteenth can
    ask what the name is. "Started by: this installation" for all thirteen cannot be
    questioned at all.
    """
    anchor = handover_lines((control("audit_anchor"),))[0]
    assert ".github/workflows/anchor.yml" in anchor
    assert "/api/audit/anchor" in anchor
    in_process = handover_lines(
        (_control(symbols=("brain.audit.anchor:take_anchor",), invoked_by=Invocation.IN_PROCESS),)
    )[0]
    assert "brain.audit.anchor:take_anchor" in in_process
