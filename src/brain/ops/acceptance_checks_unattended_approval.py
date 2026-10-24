"""The install acceptance check for a step an unattended run holds for a person (M17.4.5).

**It raises a hold of its own, through the same calls a performer will make, and reads it back
through the approvals route everybody else's goes through.** `brain.ops.automation_hold.hold_step`
refuses a window that reaches the next run or outlasts the platform's maximum, and otherwise
raises the approvals machinery's own `SuspendedAction` for the automation's owner with the run's
id as its trace. The check keeps one, reads its card as an approver of the owner's department and
as an approver of another, then lets another lapse and asks what became of it.

**What it shows.** The window the task declares is accepted; a day on the task's daily schedule
is refused for reaching the next run, and a day and an hour on a weekly one for outlasting the
platform's maximum, each with its own reason. The approver of the owner's department is shown the
hold's card; the approver of another is not. A hold whose window has gone has no card for anybody,
cannot be decided, and is the stop `stopped_for_want_of_approval` answers, naming the automation
and the step; a hold a person approved in time is not a stop whenever the clock is read.

**What it does not show**, stated: that a performer of this install raises a hold, because none
does. Every performer reads, a flow's tool calls go through the gate with no leash, and the tasks
that draft are unbuilt, one behind an owner question about unattended model calls (needs-rupash
210). The leaf is therefore not closed by this check; it is the proof, on the install, that when
one does, the person it needs is shown it and the run stops when they do not answer.

Task ids: M17.4.5
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2062

# ------------------------------------------------------------------------ the figures
#: A window as long as the shortest gap on a daily schedule, and a day and an hour: each refused.
AS_LONG_AS_THE_GAP: Final = timedelta(days=1)
PAST_THE_MAXIMUM: Final = timedelta(days=1, hours=1)

#: How long before the check's instant the lapsed hold was raised beyond its own window.
LAPSED_BY: Final = timedelta(minutes=5)

# ----------------------------------------------------------------------- the sentences
THE_DECLARED_WINDOW_WAS_REFUSED: Final = (
    "the window the task declares for its approval was refused for the schedule it runs on"
)
A_WINDOW_AS_LONG_AS_THE_GAP_WAS_ALLOWED: Final = (
    "an approval window as long as the gap between two runs was allowed, so two runs could wait "
    "on one person"
)
A_WINDOW_PAST_THE_MAXIMUM_WAS_ALLOWED: Final = (
    "an approval window past the platform's maximum was allowed"
)
THE_HOLD_WAS_NOT_THE_OWNERS_AND_THE_RUN_S: Final = (
    "the hold did not run as the automation's owner, carry the run's id, or stand as long as the "
    "task declares"
)
THE_HOLD_COULD_NOT_BE_KEPT: Final = "a hold raised for an unattended run could not be kept"
THE_APPROVER_WAS_NOT_SHOWN_THE_HOLD: Final = (
    "the approver of the owner's department was not shown the hold's card"
)
ANOTHER_DEPARTMENT_WAS_SHOWN_THE_HOLD: Final = (
    "an approver of another department was shown the hold"
)
A_LAPSED_HOLD_WAS_STILL_THERE: Final = (
    "a hold whose window had gone was still shown to an approver or could still be decided"
)
NOBODY_ANSWERING_DID_NOT_STOP_THE_RUN: Final = (
    "a hold nobody answered in its window did not stop the run, or did not name the automation "
    "and the step"
)
A_HOLD_STOPPED_BEFORE_ITS_WINDOW_WAS_UP: Final = (
    "a hold still inside its window was reported as a stop"
)
A_DECIDED_HOLD_WAS_A_STOP: Final = (
    "a hold a person approved in time was reported as a run that stopped for want of an answer"
)


async def _a_write_held_for_a_person(h: Harness, asker: str, now: Any) -> tuple[Any, Any]:
    """A write the automation's agent would make for its owner, and the leash's decision on it,
    which is that it waits for a person. It changes nothing anywhere, as the approvals checks' own
    action changes nothing."""
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.envelope import SideEffect, ToolDefinition
    from brain.core.field_policy import FieldPolicy
    from brain.core.scope import Scope
    from brain.gate.injection import AutonomyTier, RiskAssessment
    from brain.gate.leash import Action, Leash, LeashEntry, decide
    from brain.ops.acceptance_checks_governance_2 import ACTION_CAPABILITY

    agent = f"acceptance_{h.run}_agent"
    target = f"acceptance_{h.run}.update_status"
    action = Action(
        agent_id=agent,
        tool=ToolDefinition(
            name=target,
            description="The acceptance check's own action, which changes nothing anywhere",
            entity="ticket",
            required_capability=ACTION_CAPABILITY,
            side_effect=SideEffect.WRITE,
        ),
        target=target,
        row={"department": A},
        touched_fields=("status",),
        args={"status": h.word()},
    )
    decision = decide(
        action,
        caller=await h.reach(asker),
        agent_ceiling=EntitlementSet(
            principal_id=agent,
            grants=(
                Grant(capability=Capability(value=ACTION_CAPABILITY), scope=Scope.unrestricted()),
            ),
        ),
        policy=FieldPolicy(rules=()),
        leash=Leash(
            entries=(
                LeashEntry(
                    agent_id=agent,
                    target=target,
                    scope=Scope.unrestricted(),
                    rung=AutonomyTier.ASSISTED,
                ),
            )
        ),
        assessment=RiskAssessment(score=0, matched=()),
        now=now,
    )
    return action, decision


@check(
    leaves=("M17.4.5",),
    sentence=(
        "A step an unattended run holds for a person is refused a window that reaches the next run "
        "or outlasts the platform's maximum, is shown to the approver of "
        "the owner's department and not to another's, and when nobody answers in its window it is "
        "has no card, cannot be decided and is the stop naming the automation and the step; "
        "one approved in time is never a stop."
    ),
)
async def a_step_an_unattended_run_holds_waits_for_a_person_and_expires(
    h: Harness,
) -> None:
    from brain.approval_routes import (
        DecidableVerdict,
        DecisionAsked,
        approval,
        take_decision,
    )
    from brain.console.agent_automations import Automation
    from brain.console.automation_gallery import Cadence, Every, template_by_id
    from brain.core.entitlement import Capability
    from brain.core.errors import Absent
    from brain.gate.leash import ApprovalState
    from brain.gate.suspension_store import StoredSuspensions, put_suspension
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.acceptance_checks_governance import _asking, _refused, _request
    from brain.ops.acceptance_checks_governance_2 import (
        ACTION_CAPABILITY,
        _approvals_app,
        _two_people,
    )
    from brain.ops.automation_hold import (
        HoldRefusedError,
        hold_refusals,
        hold_step,
        stopped_for_want_of_approval,
    )
    from brain.ops.automation_run import ApprovalPoint, task_declaration

    template = template_by_id("deal_capture")
    declaration = task_declaration("automation.deal_capture")
    if template is None or declaration is None or not declaration.approvals:
        raise CheckFailedError(THE_DECLARED_WINDOW_WAS_REFUSED)
    declared = declaration.approvals[0]
    asker, approver, other = await _two_people(h)
    owner = await StoredPrincipals(h.sessions).live_principal(asker)
    if owner is None:
        raise CheckFailedError(THE_HOLD_COULD_NOT_BE_KEPT)
    automation = Automation(
        automation_id=f"acceptance_{h.run}_deal",
        agent_id=f"acceptance_{h.run}_agent",
        name=template.name,
        runs_as=owner,
        task=template.task,
    )
    requires = Capability(value=ACTION_CAPABILITY)

    if hold_refusals(automation, declared, template.cadence, requires=requires):
        raise CheckFailedError(THE_DECLARED_WINDOW_WAS_REFUSED)
    reaching = hold_refusals(
        automation,
        ApprovalPoint(step_id=declared.step_id, window=AS_LONG_AS_THE_GAP),
        template.cadence,
        requires=requires,
    )
    if not any("runs every" in one for one in reaching):
        raise CheckFailedError(A_WINDOW_AS_LONG_AS_THE_GAP_WAS_ALLOWED)
    outlasting = hold_refusals(
        automation,
        ApprovalPoint(step_id=declared.step_id, window=PAST_THE_MAXIMUM),
        Cadence(every=Every.WEEK, hour_utc=9, weekday=4),
        requires=requires,
    )
    if not any("the platform maximum is" in one for one in outlasting):
        raise CheckFailedError(A_WINDOW_PAST_THE_MAXIMUM_WAS_ALLOWED)

    asked = await _asking(h, approver)
    now = asked.now
    action, decision = await _a_write_held_for_a_person(h, asker, now)
    fresh_run, lapsed_run = f"run_{h.run}_fresh", f"run_{h.run}_lapsed"
    try:
        fresh = hold_step(
            automation,
            declared,
            cadence=template.cadence,
            requires=requires,
            action=action,
            decision=decision,
            run_id=fresh_run,
            now=now,
        )
        lapsed = hold_step(
            automation,
            declared,
            cadence=template.cadence,
            requires=requires,
            action=action,
            decision=decision,
            run_id=lapsed_run,
            now=now - declared.window - LAPSED_BY,
        )
    except HoldRefusedError as refused:
        raise CheckFailedError(THE_DECLARED_WINDOW_WAS_REFUSED) from refused
    if (
        fresh.principal_id != asker
        or fresh.trace_id != fresh_run
        or fresh.expires_at - fresh.raised_at != declared.window
    ):
        raise CheckFailedError(THE_HOLD_WAS_NOT_THE_OWNERS_AND_THE_RUN_S)
    try:
        asking = await h.reach(asker)
        async with StoredSuspensions(h.sessions).holding(asking, now) as rows:
            await put_suspension(rows.session, fresh)
            await put_suspension(rows.session, lapsed)
    except Exception as exc:
        raise CheckFailedError(THE_HOLD_COULD_NOT_BE_KEPT) from exc

    request = _request(_approvals_app(h))
    # One card by its id and not the queue, which is cut at a page: with many approvals waiting a
    # hold lapsing in half a day could fall off the end of the queue and be missing for a reason
    # that is not the product's.
    try:
        card = await approval(request, fresh.id, asked)
    except Absent as missing:
        raise CheckFailedError(THE_APPROVER_WAS_NOT_SHOWN_THE_HOLD) from missing
    if card.suspension_id != fresh.id:
        raise CheckFailedError(THE_APPROVER_WAS_NOT_SHOWN_THE_HOLD)
    if not await _refused(approval(request, lapsed.id, asked)):
        raise CheckFailedError(A_LAPSED_HOLD_WAS_STILL_THERE)
    if not await _refused(approval(request, fresh.id, await _asking(h, other))):
        raise CheckFailedError(ANOTHER_DEPARTMENT_WAS_SHOWN_THE_HOLD)

    approve = DecisionAsked(verdict=DecidableVerdict.APPROVED)
    store = StoredSuspensions(h.sessions)
    if not await _refused(
        take_decision(
            store, lapsed.id, await h.reach(approver), approve, trace_id=h.trace_id, now=now
        )
    ):
        raise CheckFailedError(A_LAPSED_HOLD_WAS_STILL_THERE)

    if (
        stopped_for_want_of_approval(
            fresh, automation_id=automation.automation_id, step_id=declared.step_id, now=now
        )
        is not None
    ):
        raise CheckFailedError(A_HOLD_STOPPED_BEFORE_ITS_WINDOW_WAS_UP)
    stopped = stopped_for_want_of_approval(
        lapsed, automation_id=automation.automation_id, step_id=declared.step_id, now=now
    )
    if (
        stopped is None
        or automation.automation_id not in stopped.render()
        or declared.step_id not in stopped.render()
    ):
        raise CheckFailedError(NOBODY_ANSWERING_DID_NOT_STOP_THE_RUN)

    await take_decision(
        store, fresh.id, await h.reach(approver), approve, trace_id=h.trace_id, now=now
    )
    decided = await store.reading_as(await h.reach(approver), now).suspension(fresh.id)
    if decided is None or decided.state is not ApprovalState.APPROVED:
        raise CheckFailedError(A_DECIDED_HOLD_WAS_A_STOP)
    if (
        stopped_for_want_of_approval(
            decided,
            automation_id=automation.automation_id,
            step_id=declared.step_id,
            now=now + declared.window + timedelta(days=30),
        )
        is not None
    ):
        raise CheckFailedError(A_DECIDED_HOLD_WAS_A_STOP)
