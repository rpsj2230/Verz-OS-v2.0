"""An unattended run that needs a person holds its step in the approvals queue, and says so when
nobody answers (M17.4.5).

**There is one approvals machinery and an unattended run uses it.** A step that needs a person is
a `brain.gate.leash.SuspendedAction` raised by `brain.gate.leash.suspend`, stored by
`brain.gate.suspension_store`, listed to whoever holds the action's capability by
`brain.approval_routes`, and decided there. Rejected: a table of held runs beside it, with its own
list, its own page and its own clock. The approver would have two places to look, and the second
would be the one nobody looked in. What an unattended run adds is only what `brain.orchestration.
unattended` already said and nothing used: the window is refused when it outlasts the platform's
maximum or the cadence (`approval_refusals`), and an approval nobody answered is a value that
stops the run (`expire`).

**The run's id is the hold's trace.** The suspension is raised with `trace_id` set to the run's id
and its own id derived from the run and the step, so a hold is found again from the run that raised
it and a second raise of the same step in the same slot is the same row. Nothing is stored beside
the suspension.

**Nobody answering is a stop, not a skip.** `stopped_for_want_of_approval` answers an
`ExpiredApproval` for a hold still pending past its window and nothing for one a person decided,
approved or rejected, whenever they did. There is no third answer, for
`brain.orchestration.unattended.AN_EXPIRED_APPROVAL_STOPS_THE_RUN`'s reason: a function that could
say "carry on" would be reached by whichever caller wanted the run to finish. The approvals queue
already stops showing a lapsed approval and refuses to decide it
(`SuspendedAction.is_open`), so nothing after the step happens; what this adds is the value that
says the run stopped there, for the owner to be told.

**Nothing raises a hold today, and that is said here and not left to be found.** Every performer
this install has is read-only, a flow's tool calls go through the gate with no leash
(`brain.automation_routes`), and the three tasks that would draft something for a person to decide
are unbuilt, one of them behind an owner question about unattended model calls (needs-rupash 210).
`brain.ops.acceptance_checks_unattended_approval` raises a hold of its own and proves the half
that can be proved before then: it reaches the approver and nobody outside their department, it is
refused when its window is too long, and it stops the run when nobody answers. The performer that
calls `hold_step` for real is the next piece of work, and this is what it calls.

Task ids: M17.4.5
"""

from __future__ import annotations

from datetime import datetime

from brain.console.agent_automations import Automation
from brain.console.automation_gallery import Cadence
from brain.core.entitlement import Capability
from brain.gate.leash import Action, ApprovalState, Decision, SuspendedAction, suspend
from brain.ops.automation_run import ApprovalPoint, AutomationRunError, shortest_gap
from brain.orchestration.unattended import (
    ApprovalStep,
    ExpiredApproval,
    Trigger,
    TriggerKind,
    UnattendedRun,
    approval_refusals,
    expire,
)


class HoldRefusedError(AutomationRunError):
    """A run tried to hold a step in a way that would go wrong with nobody watching."""


def _unattended_run(
    automation: Automation, cadence: Cadence, requires: Capability
) -> UnattendedRun:
    """This automation as `approval_refusals` reads one: who it runs as, and how often."""
    return UnattendedRun(
        automation_id=automation.automation_id,
        template_id=automation.task,
        principal_id=automation.runs_as.id,
        agent_id=automation.agent_id,
        trigger=Trigger(kind=TriggerKind.SCHEDULE, every=shortest_gap(cadence)),
        requires=(requires,),
    )


def hold_refusals(
    automation: Automation, point: ApprovalPoint, cadence: Cadence, *, requires: Capability
) -> tuple[str, ...]:
    """Every reason this automation may not hold a step for this long, in words (M17.4.5)."""
    return approval_refusals(
        _unattended_run(automation, cadence, requires), (point.step(automation.automation_id),)
    )


def hold_step(
    automation: Automation,
    point: ApprovalPoint,
    *,
    cadence: Cadence,
    requires: Capability,
    action: Action,
    decision: Decision,
    run_id: str,
    now: datetime,
) -> SuspendedAction:
    """Hold one step of one run for a person, through the approvals machinery's own `suspend`.

    Refuses, and raises nothing to store, when the window outlasts the platform's maximum or the
    cadence. The held action runs as the automation's owner, because that is whose reach the run
    had, and carries the run's id as its trace so the run is found from it.
    """
    refused = hold_refusals(automation, point, cadence, requires=requires)
    if refused:
        raise HoldRefusedError("; ".join(refused))
    return suspend(
        action,
        decision,
        principal_id=automation.runs_as.id,
        trace_id=run_id,
        now=now,
        window=point.window,
        suspension_id=f"{run_id}_{point.step_id}",
    )


def stopped_for_want_of_approval(
    held: SuspendedAction, *, automation_id: str, step_id: str, now: datetime
) -> ExpiredApproval | None:
    """The stop a hold nobody answered came to, or none (M17.4.5).

    None while it can still be decided and for one a person did decide, approved or rejected: a
    decision is not an expiry however late the clock is read. The window is the hold's own,
    taken from the suspension and not from what the task declared now, so a window changed since
    the hold was raised cannot move a stop that has already happened.
    """
    if held.state is not ApprovalState.PENDING:
        return None
    step = ApprovalStep(
        step_id=step_id, automation_id=automation_id, window=held.expires_at - held.raised_at
    )
    return expire(step, raised_at=held.raised_at, now=now)
