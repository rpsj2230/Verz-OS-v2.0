"""The starter prompts of one agent, for the person about to ask it (M40.7.8).

One read: `GET /me/agents/{agent_id}/starters`, gated on the member grant and on the agent being
one the person may run now. **An agent the person may not run, one that is disabled, one not
enabled on the web and one that does not exist are one answer**, the page's refusal, for the
reason `brain.gate.select` gives about an addressed agent. The prompts are
`brain.member_starters.starters_for` at the reach the run would hold, and the answer carries them
and nothing else: no count, no skill names and no reason a prompt is missing.

Behind the `agent_starter_prompts` switch, which ships off. Off, the answer is the empty list, the
same list an agent with no examples gives, so a switch that is off is not a finding either.

Task ids: M40.7.8
"""

from __future__ import annotations

from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.agent_lifecycle_routes import lifecycles_of
from brain.agents.model import runnable_agent_ids, visible_to
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, agent_run_of
from brain.console.reads import permitted
from brain.core.errors import Absent, Failed
from brain.gate.roster import viewer_for
from brain.member.shell import member_screen
from brain.member_starters import starters_for
from brain.mine_routes import MEMBER_HOME
from brain.ops.features import is_on
from brain.ops.features_declared.agent_starter_prompts import AGENT_STARTER_PROMPTS
from brain.routing_routes import sessions_of
from brain.tools.registry import ToolRegistry

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["member"])

STARTERS_PATH: Final = "/me/agents/{agent_id}/starters"


class MemberStartersView(BaseModel):
    """At most three prompts, in the order they are offered, and nothing else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompts: list[str]


def _not_answerable() -> Absent:
    return Absent("starter prompts are not answerable for this caller")


async def starters_are_on(request: Request) -> bool:
    """Whether starter prompts are switched on. Off with no database, and until turned on."""
    found = getattr(request.app.state, "agent_starter_prompts_on", None)
    if isinstance(found, bool):
        return found
    factory = sessions_of(request)
    if factory is None:
        return False
    async with factory() as session:
        return await is_on(session, AGENT_STARTER_PROMPTS)


@router.get(STARTERS_PATH, response_model=MemberStartersView, responses=COMMON_RESPONSES)
async def agent_starters(request: Request, agent_id: str, asked: Asked) -> MemberStartersView:
    """Up to three prompts this person could ask this agent and have answered."""
    if not permitted(member_screen(MEMBER_HOME).read, asked.reach, asked.now):
        log.info("starters not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    found = await lifecycles_of(request).agent(agent_id)
    viewer = viewer_for(asked.caller.principal)
    if (
        found is None
        or agent_id not in runnable_agent_ids((found.record,), viewer)
        or not visible_to(found.record.audience, viewer)
    ):
        raise _not_answerable()
    if not await starters_are_on(request):
        return MemberStartersView(prompts=[])
    registry = getattr(request.app.state, "tools", None)
    if not isinstance(registry, ToolRegistry):
        raise Failed("no tool registry on this process")
    run = await agent_run_of(request.app.state, found.record, registry)
    if run is None:
        return MemberStartersView(prompts=[])
    return MemberStartersView(prompts=list(starters_for(run, caller=asked.reach, now=asked.now)))
