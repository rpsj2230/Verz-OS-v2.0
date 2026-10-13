"""The install acceptance check for the resume point: an approval is decided at the approver's
reach as it is when they press the button, not as it was when the action was held.

**One held action, two people, one revocation between them.** An agent's action is raised for a
person through the leash's own `suspend` and stored at the asker's reach, exactly as the other
approval checks raise one (`brain.ops.acceptance_checks_governance_2._raised`). Two people of
`acceptance_a` hold the capability the action needs. The first has it taken away after the action
is held, and then presses approve: the decision is taken through the Approvals route's own
`take_decision`, which resolves the approver's reach afresh, and must be answered with the one
refusal every missing card gets. The action is still held afterwards, and the second person, who
still holds the capability, approves it. **Without the second half the check is satisfied by a
route that refuses everybody**, which is why it is in the same check. See
`A_RESUME_IS_DECIDED_AT_THE_REACH_HELD_NOW`.

**What is not shown.** That the approved action then runs once is `acceptance_approved_runs`, and
the in-process leash tests hold the intersection itself.

Task ids: M17.2.5
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import func, update

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2030

# ------------------------------------------------------------------ written-down reasons
#: Why the approval is decided at the reach held at the decision.
A_RESUME_IS_DECIDED_AT_THE_REACH_HELD_NOW: Final = (
    "An action held for a person can wait for hours. A person whose grant was taken away in that "
    "time must not be able to release it, so the decision resolves the approver's reach when it "
    "is taken and never reads one stored beside the held action."
)


@check(
    leaves=("M17.2.5",),
    sentence=(
        "An agent's action held for approval cannot be approved by a person whose grant for it was "
        "revoked after it was held, who is answered as if there were no such approval; the action "
        "stays held, and a person who still holds the grant approves it."
    ),
)
async def an_approval_is_decided_at_the_reach_held_when_it_is_pressed(h: Harness) -> None:
    from brain.approval_routes import DecidableVerdict, DecisionAsked, take_decision
    from brain.gate.suspension_store import StoredSuspensions
    from brain.ops.acceptance_checks import _in
    from brain.ops.acceptance_checks_governance import _refused
    from brain.ops.acceptance_checks_governance_2 import (
        ACTION_CAPABILITY,
        WINDOWS,
        _raised,
        _two_people,
    )
    from brain.tables.gate import CapabilityGrantRow

    asker, revoked, _ = await _two_people(h)
    keeper = h.principal(A, "keeper")
    await h.person(keeper, department=A, grants=_in(A, ACTION_CAPABILITY))
    raised = await _raised(
        h, asker, "resume", at=h.now, window=WINDOWS[0], args={"status": h.word()}
    )

    await h.execute(
        *h.attributed(revoked),
        update(CapabilityGrantRow)
        .where(
            CapabilityGrantRow.principal_id == revoked,
            CapabilityGrantRow.capability == ACTION_CAPABILITY,
            CapabilityGrantRow.deleted_at.is_(None),
        )
        .values(deleted_at=func.statement_timestamp()),
    )
    store = StoredSuspensions(h.sessions)
    approve = DecisionAsked(verdict=DecidableVerdict.APPROVED)
    refused = await _refused(
        take_decision(
            store, raised.id, await h.reach(revoked), approve, trace_id=h.trace_id, now=h.now
        )
    )
    if not refused:
        raise CheckFailedError("a person whose grant was revoked approved a held action")
    await take_decision(
        store, raised.id, await h.reach(keeper), approve, trace_id=h.trace_id, now=h.now
    )
