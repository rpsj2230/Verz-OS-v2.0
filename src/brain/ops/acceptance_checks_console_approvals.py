"""Install acceptance check for an approval card naming the agent that raised it.

Two agents of acceptance_a each hold an action for a person. The approver of acceptance_a reads the
Approvals queue as the Approvals page does, and then the same queue narrowed to each agent, which is
what an agent's own page asks for; the approver of acceptance_b reads the queue narrowed to the
same agent and is answered exactly as for an agent that does not exist. **The agent's page is the
queue narrowed, and not a second count**: a reader who may decide none of an agent's cards is sent
an empty page and the page draws nothing, which is absent and never nought.

Everything written is in the check's rolled-back transaction, for reserved people of the two
reserved departments.

Task ids: M27.15.30, M27.11.15
"""

from __future__ import annotations

from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_people_signed_in import console, within
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1340

A, B = RESERVED_DEPARTMENTS

#: What the action the check holds requires, and what its approver decides with.
ACTION_CAPABILITY: Final = "write:ticket.status"


async def _held(h: Harness, asker: str, agent: str, number: int) -> str:
    """One action of `agent` held for a person, as the gate holds it, and the suspension's id."""
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.envelope import SideEffect, ToolDefinition
    from brain.core.field_policy import FieldPolicy
    from brain.core.scope import Scope
    from brain.gate.injection import AutonomyTier, RiskAssessment
    from brain.gate.leash import Action, Leash, LeashEntry, decide, suspend
    from brain.gate.suspension_store import StoredSuspensions, put_suspension

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
    )
    asking = await h.reach(asker)
    decided = decide(
        action,
        caller=asking,
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
        now=h.now,
    )
    raised = suspend(
        action,
        decided,
        principal_id=asker,
        trace_id=h.trace_id,
        now=h.now,
        suspension_id=f"acceptance_{h.run}_approval_{number}",
    )
    async with StoredSuspensions(h.sessions).holding(asking, h.now) as rows:
        await put_suspension(rows.session, raised)
    return raised.id


@check(
    leaves=("M27.15.30", "M27.11.15"),
    sentence=(
        "Two agents of acceptance_a each hold an action for a person: each card on Approvals names "
        "its agent, the queue narrowed to an agent lists that agent's cards only, an approver of "
        "acceptance_b narrowed to the same agent is answered exactly as for an agent that does "
        "not exist, and an agent with nothing waiting for the reader gives an empty page."
    ),
)
async def an_approval_names_its_agent_and_each_agent_lists_only_its_own(h: Harness) -> None:
    from brain.api_routes import FILTER_SEPARATOR
    from brain.approval_routes import approvals
    from brain.listing import ListAsked

    await h.found_departments()
    c = await console(h)
    asker, approver = h.principal(A, "asker"), h.principal(A, "approver")
    elsewhere = h.principal(B, "approver")
    for one, where in ((asker, A), (approver, A), (elsewhere, B)):
        await h.person(
            one, department=where, grants=within(where, ACTION_CAPABILITY, "approve:action")
        )
    first, second = f"acceptance_{h.run}_first", f"acceptance_{h.run}_second"
    held = {
        await _held(h, asker, first, 1): first,
        await _held(h, asker, second, 2): second,
    }
    from brain.gate.suspension_store import StoredSuspensions

    c.app.state.suspensions = StoredSuspensions(h.sessions)

    async def queued(reader: str, agent: str | None) -> dict[str, str]:
        asked = await c.asked(reader)
        narrowed: Any = () if agent is None else (f"agent_id{FILTER_SEPARATOR}{agent}",)
        with c.as_route():
            page = await approvals(c.request(), asked, ListAsked(limit=200, filters=narrowed))
        return {one.suspension_id: one.agent_id for one in page.items}

    everything = await queued(approver, None)
    if {key: everything.get(key) for key in held} != held:
        raise CheckFailedError("an approval card did not name the agent that raised it")
    for agent in (first, second):
        found = await queued(approver, agent)
        if set(found.values()) != {agent} or {
            key for key, who in held.items() if who == agent
        } != set(found):
            raise CheckFailedError("the queue narrowed to an agent did not list its cards only")
    outside = await queued(elsewhere, first)
    nobody = await queued(elsewhere, f"acceptance_{h.run}_nobody")
    if outside or outside != nobody:
        raise CheckFailedError("a reader who may decide none of an agent's cards was told more")
