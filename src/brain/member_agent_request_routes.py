"""Asking for an agent you can see and cannot yet run, and seeing what you have asked for.

`GET /me/agents/requestable` lists the agents this person's audience reaches and nothing lets them
run; `POST /me/agents/{agent_id}/request` asks the department that answers for one; `GET
/me/agent-requests` lists what they have asked. All three are for the person asking, take no
parameter that names whose page it is, and are gated on the member grant, so DENIED and ABSENT are
the page's one refusal.

**An agent outside this person's audience is not one they may ask for, and the refusal is the one
a missing agent gets.** `member_activity.request_agent` decides, through `visible_agent_ids`, so a
request form is not a catalogue the agent list refuses to be. Asking for something already runnable,
or for an agent no department answers for, is refused in the same words.

**The department's lead is told once, in the chat they last used**, through `brain.tell_later`, the
one sender for a message with no request behind it, under an intent naming the asker and the agent,
so asking again sends nothing. What the message carries is the asker's name and the agent's, which
the lead is entitled to when somebody asks them for something. Nobody is told anything about an
answer, because there is none to give here: what the department decides is a change to the agent's
audience, made where those are.

Task ids: M40.2.2.5
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Path, Request
from pydantic import BaseModel, ConfigDict

from brain.agent_routes import every_agent, record_of, viewer_of
from brain.agents.model import AgentRecord, runnable_agent_ids, visible_agent_ids
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.reads import permitted
from brain.core.errors import Absent, Failed
from brain.member.shell import member_screen
from brain.member_activity import MemberError, request_agent
from brain.mine_routes import MEMBER_HOME
from brain.ops.agent_request_store import StoredAgentRequests
from brain.routing_routes import sessions_of
from brain.tell_later import tell

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["member"])

AgentIdPath = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^\S+$")]

#: What a lead is told. Names the asker and the agent and nothing else.
ASKED_FOR_AN_AGENT: Final = (
    "{asker} has asked to be able to run the agent {agent}. Nothing has changed."
)


def _not_answerable() -> Absent:
    return Absent("your agent requests are not answerable for this caller")


def _guard(asked: Asked) -> None:
    if not permitted(member_screen(MEMBER_HOME).read, asked.reach, asked.now):
        log.info("own agent requests not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()


class RequestableAgent(BaseModel):
    """One agent this person can see and cannot run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str
    asked: bool


class RequestablePage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    agents: list[RequestableAgent]


class AgentRequestView(BaseModel):
    """One request this person made, and which department it went to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    department: str
    requested_at: datetime


class AgentRequestsView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requests: list[AgentRequestView]


class AgentRequestedView(BaseModel):
    """That the request is kept, and whether the department's lead was told."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    department: str
    first_time: bool


async def _records(request: Request) -> list[AgentRecord]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        rows = (await session.execute(every_agent())).scalars().all()
    return [one for one in (record_of(row) for row in rows) if one is not None]


def _store(request: Request) -> StoredAgentRequests:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredAgentRequests(factory)


@router.get("/me/agents/requestable", response_model=RequestablePage, responses=COMMON_RESPONSES)
async def requestable_agents(request: Request, asked: Asked) -> RequestablePage:
    """The agents this person's audience reaches and that they cannot run yet."""
    _guard(asked)
    records = await _records(request)
    viewer = viewer_of(asked)
    seen, runnable = visible_agent_ids(records, viewer), runnable_agent_ids(records, viewer)
    mine = {one.agent_id for one in await _store(request).of(asked.caller.principal.id)}
    return RequestablePage(
        agents=[
            RequestableAgent(
                agent_id=one.agent_id, display_name=one.display_name, asked=one.agent_id in mine
            )
            for one in records
            if one.agent_id in seen - runnable
        ]
    )


@router.post(
    "/me/agents/{agent_id}/request", response_model=AgentRequestedView, responses=COMMON_RESPONSES
)
async def ask_for_an_agent(
    request: Request, agent_id: AgentIdPath, asked: Asked
) -> AgentRequestedView:
    """Ask the department that answers for an agent to let this person run it."""
    _guard(asked)
    me = asked.caller.principal.id
    records = await _records(request)
    try:
        made = request_agent(
            agent_id, records, principal_id=me, viewer=viewer_of(asked), at=asked.now
        )
    except MemberError:
        log.info("own agent request not answerable", principal=me)
        raise _not_answerable() from None
    store = _store(request)
    first = await store.record(made)
    if first:
        lead = await store.leads_of(made.department)
        if lead is not None:
            name = next(one.display_name for one in records if one.agent_id == agent_id)
            await tell(
                request,
                lead,
                ASKED_FOR_AN_AGENT.format(asker=asked.caller.principal.display_name, agent=name),
                intent_ref=f"agent_request:{me}:{agent_id}",
                now=asked.now,
            )
    return AgentRequestedView(agent_id=agent_id, department=made.department, first_time=first)


@router.get("/me/agent-requests", response_model=AgentRequestsView, responses=COMMON_RESPONSES)
async def my_agent_requests(request: Request, asked: Asked) -> AgentRequestsView:
    """What this person has asked to be able to run."""
    _guard(asked)
    mine = await _store(request).of(asked.caller.principal.id)
    return AgentRequestsView(
        requests=[
            AgentRequestView(agent_id=one.agent_id, department=one.department, requested_at=one.at)
            for one in mine
        ]
    )
