"""Install acceptance check for asking for an agent a person can see and cannot run (M40.2.2.5).

A member of acceptance_a sees an agent their department offers that is switched off. They are
shown it as one they can ask for, ask once, and are shown they have asked; the department's lead is
told in their own Slack conversation, once however often the member asks; and an agent that is
already runnable, one the member cannot see and one that never existed are each refused in the one
sentence, beside the act that works. **What is stood in for is Slack**: a channel the check sets up
whose transport keeps what it is handed and sends nothing, so nobody is written to.

Task ids: M40.2.2.5
"""

from __future__ import annotations

import json
from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_people_signed_in import console
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1940

A, B = RESERVED_DEPARTMENTS


async def _refused(call: Any) -> bool:
    """Whether a call was answered with the one refusal, `Absent`, and nothing else."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent:
        return True
    return False


@check(
    leaves=("M40.2.2.5",),
    sentence=(
        "A member sees an agent of their department that is switched off as one they can ask for "
        "and asks: it is kept once however often they ask, they are shown it, and the department's "
        "lead is told once in their own chat; an agent already runnable, one the member cannot see "
        "and one that does not exist are each refused in the one sentence."
    ),
)
async def a_member_asks_the_department_for_an_agent_they_cannot_run_yet(h: Harness) -> None:
    from functools import partial

    from sqlalchemy import update

    from brain.channels.slack import BOT_TOKEN, SIGNING_SECRET
    from brain.identity.organisation_store import StoredOrganisation
    from brain.member_agent_request_routes import (
        ask_for_an_agent,
        my_agent_requests,
        requestable_agents,
    )
    from brain.ops.acceptance_checks import _HeldLedger, _Secret
    from brain.ops.acceptance_checks_learning_digest import _on_slack, _sent
    from brain.ops.acceptance_escalation import _Kept
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.acceptance_workspace import installed_agent
    from brain.tables.agent import AgentRow

    await h.found_departments()
    c = await console(h)
    asker, head, outsider = (h.principal(A, role) for role in ("asker", "head", "outsider"))
    for one in (asker, head, outsider):
        await h.person(one, department=A)
    off = await installed_agent(h, head, suffix="_off")
    on = await installed_agent(h, head, suffix="_on")
    private = await installed_agent(h, head, suffix="_private", personal=True)
    await h.execute(
        *h.attributed(head), update(AgentRow).where(AgentRow.id == off).values(disabled_at=h.now)
    )
    if (
        await StoredOrganisation(h.sessions).appoint(
            department=A,
            principal_id=head,
            actor=h.actor,
            ent_hash=SET_UP_REACH,
            trace_id=h.trace_id,
            may=partial(lambda *_: True),
        )
        is None
    ):
        raise CheckFailedError("a head could not be appointed to lead a department")
    lead_on = f"UACC{h.run.upper()}H"
    await _on_slack(h, {head: lead_on})

    kept = _Kept()
    c.app.state.channel_transport = kept
    c.app.state.operation_ledger = _HeldLedger()
    c.app.state.channel_secrets = _Secret(
        json.dumps({SIGNING_SECRET: f"acceptance-{h.run}", BOT_TOKEN: f"xoxb-acceptance-{h.run}"})
    )

    async def listed(who: str) -> dict[str, bool]:
        with c.as_route():
            page = await requestable_agents(c.request(), await c.asked(who, strong=False))
        return {one.agent_id: one.asked for one in page.agents}

    async def asking(who: str, agent: str) -> Any:
        with c.as_route():
            return await ask_for_an_agent(
                c.request("POST"), agent, await c.asked(who, strong=False)
            )

    if await listed(asker) != {off: False}:
        raise CheckFailedError("a member was not shown exactly the agent they can see and not run")
    refusals = [
        await _refused(asking(asker, on)),
        await _refused(asking(asker, private)),
        await _refused(asking(asker, f"acceptance_{h.run}_never")),
    ]
    if not all(refusals):
        raise CheckFailedError("an agent that could not be asked for was answered differently")
    if _sent(kept, 0):
        raise CheckFailedError("a lead was told of a request that was refused")

    first = await asking(asker, off)
    if not first.first_time or first.department != A:
        raise CheckFailedError("a request was not kept against the department that answers")
    again = await asking(asker, off)
    if again.first_time:
        raise CheckFailedError("asking twice was kept as two requests")
    if await listed(asker) != {off: True}:
        raise CheckFailedError("a member was not shown that they had asked")
    with c.as_route():
        mine = await my_agent_requests(c.request(), await c.asked(asker, strong=False))
        theirs = await my_agent_requests(c.request(), await c.asked(outsider, strong=False))
    if [(one.agent_id, one.department) for one in mine.requests] != [(off, A)] or theirs.requests:
        raise CheckFailedError("a person was not shown their own requests and nobody else's")
    told = _sent(kept, 0)
    if len(told) != 1 or told[0][0] != lead_on:
        raise CheckFailedError("the department's lead was not told once, in their own chat")
