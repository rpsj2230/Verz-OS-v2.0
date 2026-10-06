"""The install acceptance check for approved actions: run once, with nobody present, and only then.

One check, over the worker's own run (`brain.ops.approved_runs.run_approved`) inside the check's
transaction. An agent of acceptance_a is installed from a template the check signs, with its
leash at Assisted on the check's own action, so its standing is read from the stored record and
install exactly as the worker reads it. Four of its actions are raised for a person and put in the
approval queue through the suspension store: one approved, one left pending, one rejected, and
one approved and then left to lapse. The worker's run is made twice.

**The action is the check's own and changes nothing anywhere.** Its executor is
`approved_runs.ToolExecutor` over a handler that counts its calls, so what is proved is the
worker's part: which approvals it finds through `gate.approved_to_run`, the reach it reads each at,
the agent it reads, and `brain.gate.leash.resume` running the approved one once. A connector's
write is the same run with `ConnectorWrites` as the executor, which the Cloudflare and Freshdesk
checks send through `send_approved` themselves.

**Each held action names itself in its row**, so the handler records which one ran and at whose
reach. A count alone could not tell the approved action running from the pending one running in
its place, and that substitution is exactly the failure this check exists to see.

**The ledger is the check's own.** The once is keyed in the operation ledger, and the install's is
on an autocommit connection, which would keep the check's rows after its transaction is rolled
back. So the run is handed the in-memory ledger the Cloudflare check uses, with the same rules, and
the second run is answered by it.

Task ids: M13.7.6
"""

from __future__ import annotations

from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import _HeldLedger, _in
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 395

A, _ = RESERVED_DEPARTMENTS

#: The capability the check's action needs, held in acceptance_a by its asker and its approver.
CAPABILITY: Final = "write:ticket.status"

# What the check says, one sentence for each way the property can fail.
THE_AGENT_HAS_NO_STANDING: Final = (
    "the check's agent was installed and the worker read no standing for it"
)
AN_ACTION_WAS_NOT_HELD: Final = "the check's action was not held for a person at Assisted"
THE_APPROVED_ACTION_DID_NOT_RUN: Final = (
    "the worker did not run the approved action exactly once on its first run"
)
THE_APPROVED_ACTION_RAN_AGAIN: Final = "the worker ran an approved action a second time"
AN_UNAPPROVED_ACTION_RAN: Final = (
    "the worker ran an action that was pending, rejected or past its window"
)


@check(
    leaves=("M13.7.6",),
    sentence=(
        "Four of an installed agent's actions held for a person, one approved, one pending, one "
        "rejected and one approved and lapsed: the worker's run carries out the approved one "
        "once at its requester's reach as it is now, a second run carries out nothing, and the "
        "other three are never carried out."
    ),
)
async def an_approved_action_runs_once_and_no_other_does(h: Harness) -> None:
    from datetime import timedelta

    from brain.agents.template import LeashRung, ManifestGuardrails
    from brain.approval_routes import (
        DecidableVerdict,
        DecisionAsked,
        RejectionReason,
        take_decision,
    )
    from brain.core.entitlement import EntitlementSet
    from brain.core.envelope import SideEffect, ToolDefinition, TypedResult
    from brain.core.scope import Scope
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.gate.injection import AutonomyTier
    from brain.gate.leash import Action, Route, decide, route_for, suspend
    from brain.gate.suspension_store import StoredSuspensions, put_suspension
    from brain.ops.acceptance_workspace import installed_agent
    from brain.ops.approved_runs import (
        ApprovedRun,
        Ran,
        StoredStandings,
        ToolExecutor,
        assessment_of,
        policy_of,
        run_approved,
    )

    asker, approver = h.principal(A, "asker"), h.principal(A, "approver")
    for one in (asker, approver):
        await h.person(one, department=A, grants=_in(A, CAPABILITY))
    target = f"acceptance_{h.run}.approved_step"
    agent = await installed_agent(
        h,
        asker,
        capabilities=(CAPABILITY,),
        allowed_tools=(target,),
        suffix="_approved",
        guardrails=ManifestGuardrails(
            max_side_effect=SideEffect.WRITE,
            leash=(LeashRung(target=target, scope=Scope(), rung=AutonomyTier.ASSISTED),),
        ),
    )
    standings = StoredStandings(h.sessions)
    standing = await standings.standing(agent, h.now)
    if standing is None:
        raise CheckFailedError(THE_AGENT_HAS_NO_STANDING)

    def action_for(name: str) -> Action:
        # Each held action carries its own name in its row, so the handler can say which ran.
        return Action(
            agent_id=agent,
            tool=ToolDefinition(
                name=target,
                description="The acceptance check's own action, which changes nothing anywhere",
                entity="ticket",
                required_capability=CAPABILITY,
                side_effect=SideEffect.WRITE,
            ),
            target=target,
            row={"department": A, "held": name},
        )

    asking, approving = await h.reach(asker), await h.reach(approver)
    store = StoredSuspensions(h.sessions)

    async def raised(name: str, *, at: timedelta, window: timedelta) -> str:
        when = h.now - at
        action = action_for(name)
        decision = decide(
            action,
            caller=asking,
            agent_ceiling=standing.ceiling,
            policy=policy_of(action),
            leash=standing.leash,
            assessment=assessment_of(action),
            now=when,
        )
        if route_for(decision) is not Route.SUSPEND:
            raise CheckFailedError(AN_ACTION_WAS_NOT_HELD)
        held = suspend(
            action,
            decision,
            principal_id=asker,
            trace_id=h.trace_id,
            now=when,
            window=window,
            suspension_id=f"acceptance_{h.run}_{name}",
        )
        async with store.holding(asking, when) as rows:
            await put_suspension(rows.session, held)
        return held.id

    hour = timedelta(hours=1)
    approved = await raised("approved", at=timedelta(minutes=10), window=4 * hour)
    await raised("pending", at=timedelta(minutes=10), window=4 * hour)
    rejected = await raised("rejected", at=timedelta(minutes=10), window=4 * hour)
    lapsed = await raised("lapsed", at=3 * hour, window=hour)
    approve = DecisionAsked(verdict=DecidableVerdict.APPROVED)
    for one, at in ((approved, h.now), (lapsed, h.now - 2 * hour - timedelta(minutes=30))):
        await take_decision(store, one, approving, approve, trace_id=h.trace_id, now=at)
    await take_decision(
        store,
        rejected,
        approving,
        DecisionAsked(
            verdict=DecidableVerdict.REJECTED, reason_code=RejectionReason.NO_LONGER_NEEDED
        ),
        trace_id=h.trace_id,
        now=h.now,
    )

    ran: list[str] = []

    def handler(one: Action, reach: EntitlementSet) -> TypedResult[Any]:
        ran.append(f"{one.row.get('held')} as {reach.principal_id}")
        return TypedResult(records=(), source="acceptance")

    executor = ToolExecutor({target: handler})
    ledger = _HeldLedger()
    reaches = StoredEntitlements(h.sessions)

    async def once() -> ApprovedRun:
        return await run_approved(
            h.sessions,
            now=h.now,
            executors=(executor,),
            standings=standings,
            reaches=reaches,
            ledger=ledger,
        )

    only = [f"approved as {asker}"]
    first = await once()
    if set(ran) - set(only):
        raise CheckFailedError(AN_UNAPPROVED_ACTION_RAN)
    if ran != only or dict(first.outcomes) != {Ran.DONE: 1}:
        raise CheckFailedError(THE_APPROVED_ACTION_DID_NOT_RUN)
    second = await once()
    if set(ran) - set(only):
        raise CheckFailedError(AN_UNAPPROVED_ACTION_RAN)
    if ran != only or dict(second.outcomes) not in ({}, {Ran.ALREADY_RAN: 1}):
        raise CheckFailedError(THE_APPROVED_ACTION_RAN_AGAIN)
