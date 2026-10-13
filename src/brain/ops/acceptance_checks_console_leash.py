"""Install acceptance checks for the leash on an agent's page: lowering at once, raising on proof.

The check calls the routes the agent's Profile calls, as the readers it serves, in the shape
`brain.ops.acceptance_agent_console` sets out (`A_CONSOLE_LEAF_IS_PROVED_THROUGH_ITS_ROUTE`), over
the check's own transaction. The actions people are said to have judged are rows of that
transaction, written as the runtime writes them, so **no agent of the install is moved and nothing
is kept**.

Task ids: M27.12.8, M27.3.12
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Final, Literal

from sqlalchemy import insert

from brain.agents.template import LeashRung, ManifestGuardrails
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_agent_console import _asking, _console, _readers, _request
from brain.ops.acceptance_operations_console import refused, screen_grants, traced
from brain.ops.acceptance_run import Harness
from brain.ops.acceptance_workspace import installed_agent

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 960

A, B = RESERVED_DEPARTMENTS

#: The authority that moves a rung. Restated rather than imported, so a change to the route's
#: authority fails the check instead of moving with it.
MOVES_A_RUNG: Final = "admin:leash"

#: How many actions people are said to have approved: the bar's own number and one over, so the
#: evidence clears it by a margin no off-by-one changes.
JUDGED: Final = 11


# ------------------------------------------ 1. a rung lowered at once, raised on proof (M27.12.8)
@check(
    leaves=("M27.12.8", "M27.3.12"),
    sentence=(
        "An agent's rung is lowered by a holder of the leash authority at once with no evidence; "
        "raising it with nothing judged is refused; with eleven actions people approved it is "
        "proposed by one holder and raised only when a second, other holder presses, and the "
        "page's history lists the rise and the fall with who named each."
    ),
)
async def a_rung_falls_at_once_and_rises_only_on_proof_and_a_second_person(h: Harness) -> None:
    from brain.agent_leash_routes import MoveAsked, agent_leash, move_agent_rung
    from brain.tables.leash import ActionVerdictRow, SupervisedActionRow

    await h.found_departments()
    first, second, nobody = (h.principal(A, role) for role in ("leash-a", "leash-b", "nobody"))
    holds = tuple(
        dict.fromkeys((*_readers(), *screen_grants("people"), (MOVES_A_RUNG, Scope.department(A))))
    )
    for one in (first, second):
        await h.person(one, department=A, grants=holds)
    await h.person(nobody, department=A)
    target = f"acceptance_{h.run}.update_status"
    # Published at Assisted, since a rung is raised only as far as the rung it was published at
    # (needs-rupash 179 A): the check lowers it first, and raises it back on proof.
    published = ManifestGuardrails(
        leash=(LeashRung(target=target, scope=Scope(), rung=AutonomyTier.ASSISTED),)
    )
    agent_id = await installed_agent(h, first, guardrails=published)
    request = _request(_console(h))

    def press(to: Literal["shadow", "assisted"]) -> MoveAsked:
        return MoveAsked(target=target, scope=Scope.unrestricted(), to=to)

    minute = [0]

    async def pressed(
        who: str, to: Literal["shadow", "assisted"], *, strong: bool = True
    ) -> tuple[int, str]:
        # Each press a minute after the last, as people's are: a move is keyed by its instant.
        minute[0] += 1
        asking = await _asking(h, who, strong=strong)
        asking.now = h.now + timedelta(minutes=minute[0])
        async with traced(h, minute[0]):
            answer = await move_agent_rung(request, agent_id, press(to), asking)
        status = getattr(answer, "status_code", 200)
        kind = getattr(answer, "kind", "")
        return status, str(kind)

    if not await refused(pressed(nobody, "shadow")):
        raise CheckFailedError("a person who may not move a rung moved one")
    brought_down = await pressed(first, "shadow")
    if brought_down[0] != 200 or brought_down[1] != "lowered":
        raise CheckFailedError("a rung could not be lowered at once")
    status, _ = await pressed(first, "assisted")
    if status == 200:
        raise CheckFailedError("a rung was raised with nothing judged to show for it")

    # After the fall, since a rise is judged on what happened since the rung last moved.
    for n in range(JUDGED):
        digest = hashlib.sha256(f"{h.trace_id}-{n}".encode()).hexdigest()
        await h.execute(
            *h.attributed(first),
            insert(SupervisedActionRow).values(
                action_digest=digest,
                route="suspend",
                agent_id=agent_id,
                tool_name=target,
                target=target,
                principal_id=first,
                ent_hash="0" * 32,
                tier=0,
                checks=[],
                trace_id=f"{h.trace_id}-{n}",
                at=h.now + timedelta(minutes=3, seconds=n),
            ),
            insert(ActionVerdictRow).values(
                action_digest=digest,
                agent_id=agent_id,
                verdict="approved",
                reviewer_id=first,
                at=h.now + timedelta(minutes=3, seconds=n + 30),
            ),
        )

    proposed = await pressed(first, "assisted")
    if proposed[0] != 200 or proposed[1] != "proposed":
        raise CheckFailedError("raising a rung on evidence was not first a proposal")
    if (await pressed(first, "assisted"))[0] == 200:
        raise CheckFailedError("the person who proposed a rise confirmed it themselves")
    raised = await pressed(second, "assisted")
    if raised[0] != 200 or raised[1] != "raised":
        raise CheckFailedError("a second holder's press did not raise the rung")
    lowered = await pressed(first, "shadow")
    if lowered[0] != 200 or lowered[1] != "lowered":
        raise CheckFailedError("a rung could not be lowered at once")

    page = await agent_leash(request, agent_id, await _asking(h, first, strong=True))
    kinds = [one.kind for one in page.history if one.target == target]
    if sorted(kinds) != ["lowered", "lowered", "proposed", "raised"]:
        raise CheckFailedError(
            "the page's history did not list the proposal, the rise and the fall"
        )
    rise = next(one for one in page.history if one.kind == "raised")
    if rise.clean_runs is None or rise.clean_runs < JUDGED:
        raise CheckFailedError("a rise did not carry the evidence it was made on")
    if not rise.approver or not rise.second_approver or rise.approver == rise.second_approver:
        raise CheckFailedError("a rise did not name two different people")
