"""The personal agents a reader holding the audit capability may be told exist, for oversight.

`brain.agents.oversight` decides who is listed and why this is a list of its own; this is the route
between the Agents screen and it, and it decides only whether the list is switched on.

**Every reader is answered with the same status and the same shape.** A reader who holds no audit
capability for any agent, a reader whose reach covers no personal agent, an install with no personal
agent and an install with the switch off are one answer: `200` and an empty list. Refusing the first
with a `404` would have told every reader whether the capability exists in their reach, and a list
that is empty only for the people who may not see it is a list that says which people those are. See
`brain.agents.oversight.OVERSIGHT_SAYS_NOTHING_TO_A_READER_WITHOUT_THE_CAPABILITY`.

**The capability is checked before the agents are read.** A reader with no scope for the audit read
of an agent has nothing to be shown, so the estate is not read on their behalf at all, which is also
what keeps this from being a way to measure how many agents there are by how long the answer takes.

**The page carries no total and no count of what the reader was not shown.** `truncated` says that
there are more agents inside this reader's reach than the page carries and nothing about any outside
it, exactly as the roster's does.

**This lists and offers nothing.** The agents it names are not in the reader's roster, and the
workspace, the lifecycle and the answer lane still answer a reader who is not the owner as they
answer an agent that was never made. See
`brain.agents.oversight.OVERSIGHT_OFFERS_THE_AGENT_TO_NOBODY`.

Task ids: M39.10.3
"""

from __future__ import annotations

from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import _require_session_factory, every_agent, record_of, steward_names
from brain.agents.oversight import AGENT_SUBJECT, overseen
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.audit.view import CAPABILITY_BY_KIND
from brain.ops.features import is_on
from brain.ops.features_declared.personal_agent_oversight import PERSONAL_AGENT_OVERSIGHT

log = structlog.get_logger()

OVERSIGHT_PATH: Final = "/agent-oversight"

#: The most personal agents one answer names. A bound on the read, never a figure shown.
MAX_OVERSEEN: Final = 200


class OverseenView(BaseModel):
    """One personal agent as oversight tells of it, and nothing it holds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str
    owner_id: str
    #: The owner's display name, or null for an owner with no principal row.
    owner_name: str | None = None
    #: `enabled`, `disabled` or `archived`.
    state: str


class OversightPage(BaseModel):
    """The personal agents inside this reader's audit reach. Empty for everybody else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[OverseenView]
    #: There are more inside this reader's reach than this answer names. Never how many.
    truncated: bool = False


async def oversight_is_on(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether `personal_agent_oversight` is switched on now. Off when nobody has said otherwise."""
    async with sessions() as session:
        return await is_on(session, PERSONAL_AGENT_OVERSIGHT)


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(OVERSIGHT_PATH, response_model=OversightPage, responses=COMMON_RESPONSES)
async def agent_oversight(request: Request, asked: Asked) -> OversightPage:
    """The personal agents, other people's, that this reader's audit capability covers.

    The same empty answer for a reader outside every audit reach, for an install with the switch
    off and for an estate with none, so it cannot say which of them it is.
    """
    nothing = OversightPage(items=[])
    factory = _require_session_factory(request)
    if asked.reach.scope_for(CAPABILITY_BY_KIND[AGENT_SUBJECT], asked.now) is None:
        return nothing
    if not await oversight_is_on(factory):
        return nothing
    async with factory() as session:
        rows = (await session.execute(every_agent())).scalars().all()
        records = [one for one in (record_of(row) for row in rows) if one is not None]
        found = overseen(records, asked.reach, asked.now)
        shown = found[:MAX_OVERSEEN]
        names = await steward_names(session, [one.owner_id for one in shown])
    log.info("agent oversight read", principal=asked.caller.principal.id)
    return OversightPage(
        items=[
            OverseenView(
                agent_id=one.agent_id,
                display_name=one.display_name,
                owner_id=one.owner_id,
                owner_name=names.get(one.owner_id),
                state=one.state.value,
            )
            for one in shown
        ],
        truncated=len(found) > MAX_OVERSEEN,
    )
