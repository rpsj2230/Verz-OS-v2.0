"""No safety mechanism in this repository may quietly stop having a caller.

This is the invariant that every other gate here is blind to. `mypy` passes on a guard
nothing runs. The unit suite passes on it, because the unit suite calls it. The sweeps pass
on it, because it is correct code with a correct docstring and a task id. And the console
reports the estate as protected, because a retention window is a declaration rather than a
measurement. A mechanism with no caller is worse than its absence: an absence is visible as
an absence.

`brain.ops.worker` calls this "the most common defect in this repository and the one that is
hardest to see in review", and `brain.ops.jobs` says the same sentence about itself. Both
were written by somebody who found it in their own module and wrote it down. This is the
first thing in the tree that asks the question of every module at once.

**What this asserts is that the registry and the source agree, not that everything is
wired.** Twelve of the thirteen controls have no caller of any kind today. A test asserting
that they do would be red on arrival, and `brain.ops.sweeps.sweep_house_style` records at
length what happens to a check that is red the day it lands. So the assertion is agreement in
both directions, which is green now and goes red on three different regressions: a control
recorded as running that nothing calls, a control that was wired and stops being, and a
recurrence predicate added to the tree that no control describes. The orphans are not hidden
by that choice; `test_the_orphans_are_the_ones_the_registry_names` pins the exact set.

Task ids: M37.5.1.2, M37.5.1.4
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from brain.ops.alerting import Severity, route_for, runbook_gaps
from brain.ops.controls import (
    CONTROLS,
    NOT_A_SCHEDULE,
    Control,
    Invocation,
    Missed,
    call_sites,
    handover_lines,
    measured_invocation,
    missing_symbols,
    orphans,
    recurrence_predicates,
    registry_gaps,
    runbook_for,
)

#: The controls nothing calls today, named rather than counted.
#:
#: A count would go on passing while one control was wired and another quietly unwired, which
#: is the regression this whole file exists for. Pinning the set means the test names which
#: control moved and in which direction, and the direction is the interesting half: a control
#: leaving this set is somebody's good afternoon and one joining it is an incident.
KNOWN_ORPHANS = frozenset(
    {
        "retention_sweep",
        "canary_run",
        "restore_drill",
        "backup_exposure",
        "denial_digest",
        "directory_sync",
        "knowledge_reverification",
        "resolution_calibration",
        "queue_redrive",
        "side_effect_resume",
        "model_health_probes",
    }
)

#: Controls that have a caller and are still not run, which is the state between the two.
#:
#: `spend_correction` left `KNOWN_ORPHANS` on 2026-09-09 because the cost review section of
#: `brain.console.spend_view` asks for it, and it is not thereby running: nothing opens that
#: screen on a schedule. The set exists so that leaving the orphan list is recorded as the
#: small move it is rather than as an arrival, and so that a control moving here and then
#: quietly back is visible.
WIRED_BUT_NOT_SCHEDULED = frozenset({"spend_correction"})


def test_every_control_names_functions_that_exist() -> None:
    """Delete this and a typo in the registry becomes an orphan nobody questions.

    A symbol that does not resolve has no callers either, so a misspelled entry point reads
    exactly like a mechanism nothing runs, on a registry where twelve rows genuinely are
    that. This is the check that makes the other twelve believable.
    """
    absent = {one.name: missing_symbols(one) for one in CONTROLS if missing_symbols(one)}
    assert absent == {}, f"controls naming functions this tree does not declare: {absent}"


def test_the_registry_agrees_with_the_source_about_what_calls_each_control() -> None:
    """Delete this and the registry becomes a document rather than a check.

    This is the assertion M37.5.1.2 asks for. Every control declares how it is started and
    the source is asked whether that is true, in both directions: a control claiming a caller
    it does not have is the console lying about the estate, and a control recorded as an
    orphan that something now calls is a record that has fallen behind, which is how a record
    stops being read at all.
    """
    disagreements = {
        one.name: (one.invoked_by.value, measured_invocation(one).value)
        for one in CONTROLS
        if measured_invocation(one) is not one.invoked_by
    }
    assert disagreements == {}, (
        "the registry and the source disagree about what starts these controls, as "
        f"(recorded, measured): {disagreements}"
    )


def test_no_safety_mechanism_lacks_a_caller_without_the_registry_saying_so() -> None:
    """Delete this and a guard can stop being run with nothing anywhere recording it.

    The leaf, stated as the property rather than as an aspiration. A control that is not
    `Invocation.NOTHING` has, by the check above, a call site that the source can be shown to
    contain; a control that is `NOTHING` is in `KNOWN_ORPHANS` and therefore in the handover
    pack as a mechanism that is not protecting anything. There is no third state, and the
    third state is the one this repository has been shipping: a guard nobody runs and nothing
    says is not being run.
    """
    unrecorded = {
        one.name
        for one in CONTROLS
        if one.invoked_by is Invocation.NOTHING and one.name not in KNOWN_ORPHANS
    }
    assert unrecorded == set(), (
        f"these controls have no caller and are not recorded as orphans: {sorted(unrecorded)}"
    )
    wired = {one.name for one in CONTROLS if one.invoked_by is not Invocation.NOTHING}
    assert wired & KNOWN_ORPHANS == set(), (
        "these controls are recorded as orphans and are wired up; move them out of "
        f"KNOWN_ORPHANS: {sorted(wired & KNOWN_ORPHANS)}"
    )
    for one in CONTROLS:
        if one.invoked_by is Invocation.IN_PROCESS:
            assert all(call_sites(symbol) for symbol in one.symbols), (
                f"{one.name} is recorded as running in this process and part of it has no "
                "caller, which is how a system asks whether a sweep is due and never sweeps"
            )


def test_the_orphans_are_the_ones_the_registry_names() -> None:
    """Delete this and the orphan set can grow one at a time with nothing noticing.

    `KNOWN_ORPHANS` is the honest state of the estate written down. Asserting equality rather
    than containment is what makes it a ratchet in both directions: a thirteenth orphan fails
    here and so does an orphan that has been fixed and not recorded as fixed, and the second
    is what keeps the list from becoming a thing nobody trusts.
    """
    assert {one.name for one in orphans()} == KNOWN_ORPHANS


def test_every_recurrence_predicate_in_the_tree_belongs_to_a_control_or_is_excused() -> None:
    """Delete this and a scheduled mechanism can be added that nothing describes.

    The converse, and the half that is derived rather than declared. The control set cannot
    be generated from the code, so the protection against the list falling behind is this:
    every module-level `due` predicate in the tree is either part of a control, with a
    sentence saying what it guards, or in `NOT_A_SCHEDULE` with a sentence saying why it is a
    growth trigger instead. Neither is optional and there is no third answer.
    """
    described = {symbol for one in CONTROLS for symbol in one.symbols}
    undescribed = [
        predicate
        for predicate in recurrence_predicates()
        if predicate not in described and predicate not in NOT_A_SCHEDULE
    ]
    assert undescribed == [], (
        "these say when something is due and nothing records what they guard: "
        f"{undescribed}. Add a row to CONTROLS, or an entry to NOT_A_SCHEDULE"
    )


def test_an_excused_predicate_that_no_longer_exists_is_refused() -> None:
    """Delete this and the exemption list rots into a hole.

    An entry in `NOT_A_SCHEDULE` naming a function that has been deleted is an exemption
    waiting to cover whatever takes that name next, and the next thing to be called
    `report_is_due` will not necessarily be a growth trigger. The exemption list has to be as
    perishable as the thing it exempts.
    """
    present = set(recurrence_predicates())
    stale = sorted(set(NOT_A_SCHEDULE) - present)
    assert stale == [], f"exemptions naming functions this tree no longer declares: {stale}"


def test_the_registry_has_nothing_else_wrong_with_it() -> None:
    """Delete this and the checks above are the only ones that run in CI.

    `registry_gaps` is the whole check and the tests above are the parts of it worth naming
    separately, because a failure that says only "one finding" sends somebody to read a
    function rather than to fix a control. This asserts the rest: duplicate names, a cadence
    whose source has been deleted, a route nothing declares, and a workflow file that has
    lost its schedule entry.
    """
    assert registry_gaps() == ()


def test_a_control_with_a_caller_and_no_schedule_is_recorded_as_neither() -> None:
    """**The state between an orphan and a running control, named so it cannot be skipped
    over in either direction.**

    `spend_correction` has a caller: the cost review section of `brain.console.spend_view`
    asks `brain.ops.retune.post_launch_correction` for it. It is not running, because nothing
    opens that screen on a schedule, and the registry records `IN_PROCESS` rather than
    anything stronger.

    Asserted as a set equality against the registry, in both directions, for the same reason
    `KNOWN_ORPHANS` is: a control that quietly slid back to having no caller would otherwise
    pass, and so would one that became genuinely scheduled without anybody moving it.

    Delete this and leaving the orphan list reads as arriving, which is the overstatement this
    whole file is written against."""
    from brain.ops.controls import Invocation as Started

    in_process = {one.name for one in CONTROLS if one.invoked_by is Started.IN_PROCESS}

    assert in_process == WIRED_BUT_NOT_SCHEDULED
    assert set() == WIRED_BUT_NOT_SCHEDULED & KNOWN_ORPHANS


def test_a_control_that_is_reachable_is_reachable_from_something_reachable() -> None:
    """Delete this and a chain of three uncalled functions reads as wired at every link.

    `brain.knowledge.verification.open_reverification_tasks` is exactly that shape: it calls
    `brain.knowledge.item.due_for_reverification`, so the inner function has a caller, and
    nothing calls the outer one. Counting the inner function as reached would have put a
    knowledge control in the wired column while nothing ran it. This asserts the one level
    that can be measured exactly.
    """
    from brain.ops.controls import chains_worth_checking

    assert chains_worth_checking() == ()


def test_the_handover_pack_says_which_mechanisms_are_not_running() -> None:
    """Delete this and a client is handed a list of thirteen protections, twelve of which are
    not happening.

    This is the difference between a handover pack and a brochure. The pack a client reads is
    the artefact this repository never re-checks, so a line claiming a mechanism protects
    something it is not running is a false statement that leaves the building and stays true
    for as long as anybody keeps the document.
    """
    lines = handover_lines()
    assert len(lines) == len(CONTROLS)
    for one in orphans():
        matching = [line for line in lines if line.startswith(f"{one.name}:")]
        assert len(matching) == 1
        assert "NOTHING" in matching[0], (
            f"the handover line for {one.name} does not say that nothing runs it: {matching[0]}"
        )


def test_every_alert_this_registry_can_raise_has_a_runbook_that_escalates_after_the_window() -> (
    None
):
    """Delete this and an alert can arrive with no next step, or with one that escalates
    immediately.

    The alerts are the product of the controls and the four reasons a control has not run,
    and a reason covered for twelve controls and not the thirteenth is a gap that only
    appears during the incident on the thirteenth. The escalation clock is checked against
    the route's own acknowledgement window, because a runbook that climbs while the first
    responder is still inside the time they were given makes the rung above them the first
    responder.
    """
    for one in CONTROLS:
        for missed in Missed:
            book = runbook_for(one, missed)
            assert book.first_check and book.then_do
            assert runbook_gaps(book, route_for(one.severity)) == ()


def test_a_control_nothing_calls_is_reported_as_unreachable_and_never_as_late() -> None:
    """Delete this and every orphan alerts for ever as a schedule that did not fire.

    The two send a person to opposite ends of the system. Late means there is a scheduler to
    look at; unreachable means the scheduler is the one place with nothing in it. An hour
    spent there is an hour spent confirming that a thing which was never wired is not wired,
    and the alert that caused it will be raised again on the next pass.
    """
    from brain.ops.controls import overdue

    now = datetime(2026, 9, 8, tzinfo=UTC)
    # Every control recorded as having run a moment ago, which would clear a lateness check.
    recent = {one.name: now - timedelta(seconds=1) for one in CONTROLS}
    reported = {row.control.name: row.missed for row in overdue(last_run=recent, now=now)}
    for one in orphans():
        assert reported[one.name] is Missed.UNREACHABLE, (
            f"{one.name} has no caller and was reported as {reported.get(one.name)}, which "
            "sends the reader to a scheduler that has nothing to find"
        )


def test_an_overdue_alert_body_names_a_mechanism_and_never_a_subject() -> None:
    """Delete this and the operational alert becomes the disclosure surface.

    Everything else in this system keeps DENIED and ABSENT indistinguishable and then the
    alert says "the retention sweep has not run, so 4 records in finance are past their
    window". An operational alert is read by whoever is on call, who is frequently entitled
    to nothing here, and it is forwarded, pasted and read over a shoulder.
    `brain.ops.denial_alerts` keeps this rule for denials; there is no reason it should be
    weaker for a control.
    """
    from brain.ops.alerting import disclosure_findings
    from brain.ops.controls import overdue

    now = datetime(2026, 9, 8, tzinfo=UTC)
    every = {one.name: now - one.every * 10 for one in CONTROLS}
    rows = overdue(last_run=every, now=now)
    assert rows, "the fixture is meant to make every control overdue"
    for row in rows:
        assert disclosure_findings(row.text) == (), (
            f"{row.control.name}'s alert body discloses something: {disclosure_findings(row.text)}"
        )


def test_a_control_may_not_be_declared_with_a_cadence_that_is_always_owed() -> None:
    """Delete this and a control can be added with a zero interval.

    A control owed on every pass is permanently overdue and therefore permanently ignored,
    which is the same end state as having no alert at all and reaches it while looking
    healthy in the registry. Refused in the constructor rather than in a gap function,
    because a value that cannot be built wrongly needs no check downstream.
    """
    with pytest.raises(Exception, match="always owed"):
        Control(
            name="never_satisfied",
            symbols=("brain.ops.canaries:due",),
            guards="nothing at all",
            lost_silently="nothing, because it can never be up to date",
            every=timedelta(0),
            severity=Severity.NOTICED,
            invoked_by=Invocation.NOTHING,
        )
