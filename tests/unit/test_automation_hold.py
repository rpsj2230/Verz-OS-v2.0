"""An unattended run's hold: the windows a task declares, a hold raised through the approvals
machinery's own `suspend`, and the stop when nobody answers.

Over values only: the install check (`tests/unit/test_acceptance_checks_unattended_approval.py`)
runs the same hold through the approvals queue against PostgreSQL.

Task ids: M17.4.5
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from brain.console.agent_automations import Automation
from brain.console.automation_gallery import BUILT_IN, Cadence, Every
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.field_policy import FieldPolicy
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.leash import (
    MAX_APPROVAL_WINDOW,
    Action,
    ApprovalState,
    Leash,
    LeashEntry,
    SuspendedAction,
    decide,
)
from brain.ops.automation_hold import (
    HoldRefusedError,
    hold_refusals,
    hold_step,
    stopped_for_want_of_approval,
)
from brain.ops.automation_run import (
    TASKS,
    ApprovalPoint,
    approval_gaps,
    shortest_gap,
    task_gaps,
)
from brain.orchestration.unattended import ApprovalStep, approval_refusals, window_refusals

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 1, 3, 10, 30, tzinfo=UTC)
OWNER = "u_owner"
AGENT = "quote_helper"
WRITE = "write:ticket.status"
DEAL_CAPTURE = next(one for one in BUILT_IN if one.task == "automation.deal_capture")
DAILY = Cadence(every=Every.DAY, hour_utc=18)
WEEKLY = Cadence(every=Every.WEEK, hour_utc=9, weekday=4)


def automation() -> Automation:
    return Automation(
        automation_id="deal_capture_1",
        agent_id=AGENT,
        name=DEAL_CAPTURE.name,
        runs_as=Principal(
            id=OWNER, kind=PrincipalKind.HUMAN, employment=Employment.STAFF, display_name="Owner"
        ),
        task=DEAL_CAPTURE.task,
    )


def held_action() -> tuple[Action, object]:
    """A write the automation would make, and the leash's decision about it: held for a person."""
    target = "acceptance.update_status"
    action = Action(
        agent_id=AGENT,
        tool=ToolDefinition(
            name=target,
            description="A write that changes nothing anywhere",
            entity="ticket",
            required_capability=WRITE,
            side_effect=SideEffect.WRITE,
        ),
        target=target,
        row={},
        touched_fields=("status",),
        args={"status": "open"},
    )
    owner = EntitlementSet(
        principal_id=OWNER,
        grants=(Grant(capability=Capability(value=WRITE), scope=Scope.unrestricted()),),
    )
    decision = decide(
        action,
        caller=owner,
        agent_ceiling=EntitlementSet(
            principal_id=AGENT,
            grants=(Grant(capability=Capability(value=WRITE), scope=Scope.unrestricted()),),
        ),
        policy=FieldPolicy(rules=()),
        leash=Leash(
            entries=(
                LeashEntry(
                    agent_id=AGENT,
                    target=target,
                    scope=Scope.unrestricted(),
                    rung=AutonomyTier.ASSISTED,
                ),
            )
        ),
        assessment=RiskAssessment(score=0, matched=()),
        now=NOW,
    )
    return action, decision


def raised(point: ApprovalPoint, cadence: Cadence = DAILY) -> SuspendedAction:
    action, decision = held_action()
    return hold_step(
        automation(),
        point,
        cadence=cadence,
        requires=Capability(value=WRITE),
        action=action,
        decision=decision,  # type: ignore[arg-type]
        run_id="run_" + "a" * 32,
        now=NOW,
    )


# ---------------------------------------------------------------- the declarations
def test_every_drafting_task_declares_a_window_inside_its_cadence_and_the_maximum() -> None:
    """**Checked against numbers outside the module.** Each task a template says drafts declares an
    approval point, and its window is under the platform's maximum (leash's own constant) and
    under a day, which is the shortest gap between two runs of either drafting template. Delete
    this and a declaration can drift past either bound while `approval_gaps` and the figure it is
    held to move together."""
    drafting = {one.task for one in BUILT_IN if one.drafts}
    assert drafting == {"automation.deal_capture", "automation.email_replies"}
    declared = {one.task: one for one in TASKS}
    for task in drafting:
        points = declared[task].approvals
        assert points
        for point in points:
            assert point.window <= MAX_APPROVAL_WINDOW
            assert point.window < timedelta(days=1)
    assert approval_gaps() == ()
    assert task_gaps() == ()


def test_the_gaps_a_declaration_can_have_are_each_said() -> None:
    """A drafting task with no point, a task declaring one no template drafts for, a window as long
    as the cadence and a window past the platform's maximum, each its own sentence. Delete this and
    `approval_gaps` returns nothing for a declaration that is wrong, which is the check this is."""
    point = ApprovalPoint(step_id="approve", window=timedelta(hours=12))
    without = [
        replace(one, approvals=()) if one.task == DEAL_CAPTURE.task else one for one in TASKS
    ]
    assert any("declares no point" in one for one in approval_gaps(without))
    elsewhere = [
        replace(one, approvals=(point,)) if one.task == "automation.unanswered_questions" else one
        for one in TASKS
    ]
    assert any("no template drafts for it" in one for one in approval_gaps(elsewhere))
    as_long = [
        replace(one, approvals=(replace(point, window=timedelta(days=1)),))
        if one.task == DEAL_CAPTURE.task
        else one
        for one in TASKS
    ]
    assert any(
        "deal_capture" in one and "runs every 1 day" in one for one in approval_gaps(as_long)
    )
    past_the_maximum = [
        replace(one, approvals=(replace(point, window=MAX_APPROVAL_WINDOW + timedelta(hours=1)),))
        if one.task == DEAL_CAPTURE.task
        else one
        for one in TASKS
    ]
    assert any("platform maximum" in one for one in approval_gaps(past_the_maximum))


def test_a_point_with_no_id_or_no_time_is_refused_when_it_is_declared() -> None:
    """The step's own constructor refuses, at the declaration. Delete this and a task can declare a
    window of nothing that expires the moment it is raised."""
    from brain.orchestration.unattended import UnattendedError

    with pytest.raises(UnattendedError):
        ApprovalPoint(step_id=" ", window=timedelta(hours=1))
    with pytest.raises(UnattendedError):
        ApprovalPoint(step_id="approve", window=timedelta(0))


def test_the_shortest_gap_between_two_runs_is_a_day_unless_the_cadence_is_weekly() -> None:
    """Stated as numbers. Delete this and a weekday cadence is measured as a week, so a window of
    three days is allowed on a schedule that runs every day."""
    assert shortest_gap(Cadence(every=Every.DAY, hour_utc=1)) == timedelta(days=1)
    assert shortest_gap(Cadence(every=Every.WEEKDAY, hour_utc=1)) == timedelta(days=1)
    assert shortest_gap(WEEKLY) == timedelta(days=7)


def test_a_declaration_is_held_to_the_rule_a_run_is_held_to() -> None:
    """One rule and two doors: `window_refusals` over an id and a gap says what `approval_refusals`
    says over a run with that id and that gap. Delete this and the two drift into two rules."""
    from brain.orchestration.unattended import Trigger, TriggerKind, UnattendedRun

    steps = (
        ApprovalStep("long", "deal_capture_1", timedelta(days=2)),
        ApprovalStep("elsewhere", "another", timedelta(hours=1)),
        ApprovalStep("fine", "deal_capture_1", timedelta(hours=1)),
    )
    run = UnattendedRun(
        automation_id="deal_capture_1",
        template_id="deal_capture",
        principal_id=OWNER,
        agent_id=AGENT,
        trigger=Trigger(kind=TriggerKind.SCHEDULE, every=timedelta(days=1)),
        requires=(Capability(value=WRITE),),
    )
    assert approval_refusals(run, steps) == window_refusals(
        "deal_capture_1", timedelta(days=1), steps
    )
    assert len(window_refusals("deal_capture_1", timedelta(days=1), steps)) == 3


# ------------------------------------------------------------------- the hold
def test_a_hold_is_the_approvals_machinerys_own_suspension_for_the_owner_and_the_run() -> None:
    """The hold runs as the automation's owner, carries the run's id as its trace and its own id
    from the run and the step, and stands exactly as long as the point says. Delete this and the
    run cannot be found from what it is waiting on, or stands for another window than declared."""
    point = ApprovalPoint(step_id="approve_the_draft", window=timedelta(hours=12))
    held = raised(point)
    assert held.principal_id == OWNER
    assert held.trace_id == "run_" + "a" * 32
    assert held.id == "run_" + "a" * 32 + "_approve_the_draft"
    assert held.expires_at - held.raised_at == timedelta(hours=12)
    assert held.state is ApprovalState.PENDING


def test_a_window_that_reaches_the_next_run_or_outlasts_the_maximum_raises_nothing() -> None:
    """Each refusal in its own sentence, and nothing is raised. Delete this and a hold of a day on a
    daily schedule is raised and two runs wait on one person, or one of two days stands as a
    standing grant."""
    daily = ApprovalPoint(step_id="approve", window=timedelta(days=1))
    with pytest.raises(HoldRefusedError, match="runs every 1 day"):
        raised(daily)
    long_weekly = ApprovalPoint(step_id="approve", window=MAX_APPROVAL_WINDOW + timedelta(hours=1))
    with pytest.raises(HoldRefusedError, match="platform maximum"):
        raised(long_weekly, WEEKLY)
    fine = ApprovalPoint(step_id="approve", window=timedelta(hours=12))
    assert hold_refusals(automation(), fine, DAILY, requires=Capability(value=WRITE)) == ()


# ------------------------------------------------------------------- the stop
def test_a_hold_nobody_answered_stops_the_run_and_says_where() -> None:
    """Before the window there is no stop; at its end there is one, naming the automation and the
    step and saying nothing after it happened. Delete this and the run's end is an absence of a
    record, which is how a stopped automation goes unnoticed for a week."""
    held = raised(ApprovalPoint(step_id="approve_the_draft", window=timedelta(hours=12)))
    later = NOW + timedelta(hours=12)
    assert (
        stopped_for_want_of_approval(
            held,
            automation_id="deal_capture_1",
            step_id="approve_the_draft",
            now=later - timedelta(seconds=1),
        )
        is None
    )
    stopped = stopped_for_want_of_approval(
        held, automation_id="deal_capture_1", step_id="approve_the_draft", now=later
    )
    assert stopped is not None
    assert stopped.expires_at == later
    assert "deal_capture_1 stopped at approve_the_draft" in stopped.render()
    assert "Nothing after that step happened." in stopped.render()


def test_a_hold_a_person_decided_is_never_a_stop_however_late_the_clock_is_read() -> None:
    """Approved in time or rejected, the answer is the person's and no clock overrides it. Delete
    this and an approved draft is reported as a run that stopped for want of an answer."""
    held = raised(ApprovalPoint(step_id="approve_the_draft", window=timedelta(hours=12)))
    approved = held.approved_by("u_approver", NOW + timedelta(hours=1))
    rejected = held.rejected_by("u_approver", NOW + timedelta(hours=1))
    long_after = NOW + timedelta(days=30)
    for decided in (approved, rejected):
        assert (
            stopped_for_want_of_approval(
                decided, automation_id="deal_capture_1", step_id="approve_the_draft", now=long_after
            )
            is None
        )
    assert (
        stopped_for_want_of_approval(
            held, automation_id="deal_capture_1", step_id="approve_the_draft", now=long_after
        )
        is not None
    )


def test_the_stop_is_at_the_window_the_hold_was_raised_with() -> None:
    """A hold raised for two hours stops at two hours, whatever a declaration says now. Delete
    this and the stop is measured from somewhere other than the suspension, so a window changed
    later moves a stop that has already come or not yet come."""
    held = raised(ApprovalPoint(step_id="approve_the_draft", window=timedelta(hours=2)))
    stopped = stopped_for_want_of_approval(
        held,
        automation_id="deal_capture_1",
        step_id="approve_the_draft",
        now=NOW + timedelta(hours=3),
    )
    assert stopped is not None
    assert stopped.expires_at == NOW + timedelta(hours=2)


def test_a_declaration_with_a_bad_window_is_a_task_gap_and_not_only_an_approval_gap() -> None:
    """`task_gaps` is what the repository's own gap test and sweep read, so the approval gaps are
    part of it. Delete this and a window that reaches the next run is reported by a function
    nothing reads and passes the gap test."""
    point = ApprovalPoint(step_id="approve", window=timedelta(days=1))
    wrong = [
        replace(one, approvals=(point,)) if one.task == DEAL_CAPTURE.task else one for one in TASKS
    ]
    assert any("runs every 1 day" in one for one in task_gaps(wrong))
    assert task_gaps(TASKS) == ()
