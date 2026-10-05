"""The install acceptance check for taking an agent's work over, and the rung it lowers (M8.3.5).

M8.3.5 asks that a person taking an agent's work over is fed to the circuit breaker, and M33.6.1.3
that an approver may approve, reject with a reason, or take over. On an install that is one flow:
an agent's action waits for a person, the approver takes it over from its card, and after the third
takeover inside a week that agent's next action on that target is simulated rather than suspended.
This check performs it inside its rolled-back transaction, with the product's own functions in the
order the product calls them.

**Each step is the product's own.** The action is decided by `brain.gate.leash.decide` and raised by
`brain.gate.leash.suspend`, stored by `brain.gate.suspension_store.put_suspension` at the asker's
reach, offered on the approver's queue by `brain.approval_routes.queue`, taken over through the
Approvals route's own `take_decision`, and the standing the next decision is handed is read by
`brain.gate.takeover_store.StoredTakeovers` through `0172`'s function on the install's own schema.
The leash is the check's own, one entry for the check's own agent and target, because what is being
proved is the feed and the fall rather than any agent's configuration. See
`THE_CHECK_LEASHES_ITS_OWN_AGENT_AND_NO_OTHER`.

**Both halves of the rule.** After the second takeover the next action still waits for a person,
and after the third it is simulated; a check that saw only the second would pass a breaker that
never opens, and one that saw only the third would pass one that opens on the first.

Task ids: M38.5.1
"""

from __future__ import annotations

from typing import Final

from brain.gate.abstain import TAKEOVER_DEMOTION_THRESHOLD
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import _in
from brain.ops.acceptance_run import Harness

A, _B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 330

#: Why the leash in this check is its own.
THE_CHECK_LEASHES_ITS_OWN_AGENT_AND_NO_OTHER: Final = (
    "The check's agent and target are named for its run and exist nowhere else on the install, "
    "and its leash holds that agent at Assisted on that target and nothing more, so the three "
    "takeovers it records lower no agent anybody uses, and roll back with the check."
)

#: What the check says when an action before the threshold was not held for a person.
BEFORE_THE_THIRD_TAKEOVER_THE_ACTION_DID_NOT_WAIT: Final = (
    "before the third takeover inside the week the check's action was not held for a person, so "
    "the breaker lowered the agent too soon or the leash did not hold it at Assisted"
)

#: What the check says when the approver's card does not offer the choice.
THE_CARD_DID_NOT_OFFER_TAKING_OVER: Final = (
    "the approver's card for an agent's action did not offer taking it over"
)

#: What the check says when a takeover is kept as another verdict.
A_TAKEOVER_WAS_KEPT_AS_ANOTHER_VERDICT: Final = (
    "a takeover was recorded in the ledger as something other than a takeover"
)

#: What the check says when the third takeover does not lower the agent.
THE_THIRD_TAKEOVER_DID_NOT_LOWER_THE_AGENT: Final = (
    "after the third takeover inside the week the check's action was not simulated, so the "
    "breaker did not lower the agent a step"
)

#: The capability the check's action needs, which its asker and its approver hold in acceptance_a.
CAPABILITY: Final = "write:ticket.status"


@check(
    leaves=("M8.3.5", "M33.6.1.3"),
    sentence=(
        "An agent's action held at Assisted waits for a person, the approver's card offers taking "
        "it over and the takeover is recorded as one; after two takeovers the next action still "
        "waits, and after the third inside the week it is simulated instead, read through the one "
        "function that sees takeovers past the approvals policy."
    ),
)
async def a_third_takeover_in_a_week_lowers_the_agent_a_step(h: Harness) -> None:
    from brain.approval_routes import (
        DecidableVerdict,
        DecisionAsked,
        TakeoverReason,
        queue,
        take_decision,
    )
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.envelope import SideEffect, ToolDefinition
    from brain.core.field_policy import FieldPolicy
    from brain.core.scope import Scope
    from brain.gate.injection import AutonomyTier, RiskAssessment
    from brain.gate.leash import Action, Leash, LeashEntry, Route, decide, route_for, suspend
    from brain.gate.suspension_store import StoredSuspensions, put_suspension
    from brain.gate.takeover_store import StoredTakeovers

    asker, approver = h.principal(A, "asker"), h.principal(A, "approver")
    for one in (asker, approver):
        await h.person(one, department=A, grants=_in(A, CAPABILITY))
    asking, approving = await h.reach(asker), await h.reach(approver)
    agent = f"acceptance_{h.run}_agent"
    target = f"acceptance_{h.run}.update_status"
    action = Action(
        agent_id=agent,
        tool=ToolDefinition(
            name=target,
            description="The acceptance check's own action, which changes nothing anywhere",
            entity="ticket",
            required_capability=CAPABILITY,
            side_effect=SideEffect.WRITE,
        ),
        target=target,
        row={"department": A},
    )
    ceiling = EntitlementSet(
        principal_id=agent,
        grants=(Grant(capability=Capability(value=CAPABILITY), scope=Scope.unrestricted()),),
    )
    leash = Leash(
        entries=(
            LeashEntry(
                agent_id=agent,
                target=target,
                scope=Scope.unrestricted(),
                rung=AutonomyTier.ASSISTED,
            ),
        )
    )
    suspensions = StoredSuspensions(h.sessions)
    standings = StoredTakeovers(h.sessions)

    async def next_route() -> Route:
        standing = await standings.standing(agent, target, h.now)
        return route_for(
            decide(
                action,
                caller=asking,
                agent_ceiling=ceiling,
                policy=FieldPolicy(rules=()),
                leash=leash,
                assessment=RiskAssessment(score=0, matched=()),
                now=h.now,
                standing=standing,
            )
        )

    for n in range(TAKEOVER_DEMOTION_THRESHOLD):
        route = await next_route()
        if route is not Route.SUSPEND:
            raise CheckFailedError(BEFORE_THE_THIRD_TAKEOVER_THE_ACTION_DID_NOT_WAIT)
        raised = suspend(
            action,
            decide(
                action,
                caller=asking,
                agent_ceiling=ceiling,
                policy=FieldPolicy(rules=()),
                leash=leash,
                assessment=RiskAssessment(score=0, matched=()),
                now=h.now,
            ),
            principal_id=asker,
            trace_id=h.trace_id,
            now=h.now,
            suspension_id=f"acceptance_{h.run}_takeover_{n}",
        )
        async with suspensions.holding(asking, h.now) as rows:
            await put_suspension(rows.session, raised)
        offered = queue(
            await suspensions.reading_as(approving, h.now).open_suspensions(), approving, h.now
        )
        card = next((one for one in offered.items if one.suspension_id == raised.id), None)
        if card is None or not card.may_take_over:
            raise CheckFailedError(THE_CARD_DID_NOT_OFFER_TAKING_OVER)
        decided = await take_decision(
            suspensions,
            raised.id,
            approving,
            DecisionAsked(
                verdict=DecidableVerdict.TAKEN_OVER, reason_code=TakeoverReason.NEEDS_CHANGES
            ),
            trace_id=h.trace_id,
            now=h.now,
        )
        if decided.entry.details.get("verdict") != DecidableVerdict.TAKEN_OVER.value:
            raise CheckFailedError(A_TAKEOVER_WAS_KEPT_AS_ANOTHER_VERDICT)

    if await next_route() is not Route.SIMULATE:
        raise CheckFailedError(THE_THIRD_TAKEOVER_DID_NOT_LOWER_THE_AGENT)
