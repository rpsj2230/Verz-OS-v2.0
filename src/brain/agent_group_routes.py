"""An agent installed into a group chat the bot is in, and taken out of one, from its page.

`brain.console.agent_tabs` decided the install (`install_to_group`: the surface must declare
`Feature.GROUP_INSTALL` and the agent must already answer on that channel) and what it is not (a
grant to the room: `INSTALLING_INTO_A_ROOM_IS_NOT_A_GRANT_TO_THE_ROOM`). Nothing could make one,
because no surface declared the feature and nothing held a room. Lark now reads the bot's own
joining and leaving events into `ops.channel_room`, and this is the route over the rest.

**Who installs is who switches the agent's channels.** A group install moves where people who may
already ask the agent can ask it, exactly as switching a channel does, so it is the same question,
`agent_lifecycle_routes.may_change_channels`: the agent's steward or a holder of the lifecycle
authority over its row. Anybody else is the one 404 an agent that does not exist gets, for reading
the rooms as for writing them, because a room's name is a fact about the company's conversations.

**What is said in the room is not decided here, or by the install.** A message there is answered by
the installed agent at `brain.channels.room.floor`, the intersection of everybody present,
recomputed for every answer. See `A_ROOM_ANSWERS_AT_ITS_FLOOR_WHICHEVER_AGENT_IS_INSTALLED`.

Task ids: M39.2.4.4
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.agent_lifecycle_routes import (
    _TOLD,
    REFUSED,
    _no_agent_here,
    _not_changed,
    lifecycles_of,
    may_change_channels,
    visible,
)
from brain.agent_routes import declared_channels, product_field_policy
from brain.agents.model import AgentRecord
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.attribution import trace_of_request
from brain.channels.adapter import Feature, adapter_for
from brain.console.agent_tabs import AgentTabError, channel_rows, install_to_group
from brain.core.errors import Failed
from brain.gate.context import Channel
from brain.identity.role_store import Attribution
from brain.ops.group_install_store import Installed, Room, StoredGroupInstalls
from brain.routing_routes import sessions_of
from brain.tables.group_install import ROOM_REF_CHARS

log = structlog.get_logger()

#: Why the room's floor, and not the install, decides what is said there.
A_ROOM_ANSWERS_AT_ITS_FLOOR_WHICHEVER_AGENT_IS_INSTALLED: Final = (
    "Installing an agent into a group chat chooses which agent answers a message there that names "
    "no agent, and nothing else. What it may say is computed at the room's floor, the "
    "intersection of everybody present, for every answer, exactly as for any agent asked there; "
    "the install carries no reach, so it cannot widen what a room is told."
)

GROUPS_PATH: Final = "/agents/{agent_id}/groups"
REMOVAL_PATH: Final = "/agents/{agent_id}/groups/removal"

#: What an install that could not be made is told: a room with an agent already, a room the bot
#: has left, or a channel the agent does not answer on, in one sentence.
NOT_INSTALLED: Final = (
    "That group chat could not take this agent, so nothing was changed. It may already have an "
    "agent, the bot may have left it, or this agent may not answer on that channel."
)


class GroupRoomView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    room_ref: str
    name: str


class GroupInstallView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    channel: str
    room_ref: str
    name: str
    #: False once the bot has been removed from the room; the install stays until removed.
    present: bool
    installed_at: datetime


class AgentGroupsView(BaseModel):
    """This agent's group installs, and the rooms it could be installed into. No counts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    installs: list[GroupInstallView]
    rooms: list[GroupRoomView]


class InstallAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: Channel
    room_ref: str = Field(min_length=1, max_length=ROOM_REF_CHARS)


class RemovalAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    install_id: uuid.UUID


def _store(request: Request) -> StoredGroupInstalls:
    found = getattr(request.app.state, "group_installs", None)
    if isinstance(found, StoredGroupInstalls):
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredGroupInstalls(sessions)


def _by(asked: Asking) -> Attribution:
    return Attribution(
        actor=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
    )


def installable_channels(record: AgentRecord) -> tuple[Channel, ...]:
    """The channels this agent answers on whose surface declares group installation."""
    return tuple(
        one.channel
        for one in declared_channels()
        if one.channel.value in record.channels and one.supports(Feature.GROUP_INSTALL)
    )


def groups_view(
    record: AgentRecord, installs: list[Installed], rooms: list[Room]
) -> AgentGroupsView:
    return AgentGroupsView(
        agent_id=record.agent_id,
        installs=[
            GroupInstallView(
                id=str(one.install_id),
                channel=one.channel.value,
                room_ref=one.room_ref,
                name=one.name,
                present=one.present,
                installed_at=one.installed_at,
            )
            for one in installs
        ],
        rooms=[
            GroupRoomView(channel=one.channel.value, room_ref=one.room_ref, name=one.name)
            for one in rooms
        ],
    )


async def _changeable(request: Request, agent_id: str, asked: Asking) -> AgentRecord:
    """The agent, for a caller who may switch its channels, or the one 404."""
    found = await lifecycles_of(request).agent(agent_id)
    if found is None or not visible(found.record, asked):
        raise _no_agent_here(asked, "agent")
    if not may_change_channels(found.record, asked):
        raise _no_agent_here(asked, "scope")
    return found.record


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(GROUPS_PATH, response_model=AgentGroupsView, responses=COMMON_RESPONSES)
async def agent_groups(request: Request, agent_id: str, asked: Asked) -> AgentGroupsView:
    """This agent's group installs and the rooms it could go into, for whoever may install it."""
    record = await _changeable(request, agent_id, asked)
    store = _store(request)
    return groups_view(
        record,
        await store.installs_of(agent_id),
        await store.rooms(installable_channels(record)),
    )


@router.post(GROUPS_PATH, response_model=AgentGroupsView, responses=_TOLD, status_code=201)
async def install_agent_in_group(
    request: Request, agent_id: str, body: InstallAsked, asked: Asked
) -> JSONResponse:
    """Install this agent into one group chat the bot is in (M39.2.4.4).

    `agent_tabs.install_to_group` asks the surface and the channel, over the rows the agent's page
    draws, and the store asks the room. Each refusal is the one sentence `NOT_INSTALLED`.
    """
    record = await _changeable(request, agent_id, asked)
    rows = channel_rows(
        asked.reach,
        record,
        declared_channels(),
        product_field_policy(),
        enabled=[one for one in Channel if one.value in record.channels],
        now=asked.now,
    )
    try:
        decided = install_to_group(
            agent_id, adapter_for(body.channel).capabilities(), body.room_ref, rows=rows
        )
    except (AgentTabError, KeyError, ValueError):
        return _not_changed(REFUSED, NOT_INSTALLED)
    store = _store(request)
    made = await store.install(
        agent_id=decided.agent_id, channel=decided.channel, room_ref=decided.room_ref, by=_by(asked)
    )
    if made is None:
        return _not_changed(REFUSED, NOT_INSTALLED)
    log.info("agent installed in a group", agent=agent_id, channel=body.channel.value)
    view = groups_view(
        record,
        await store.installs_of(agent_id),
        await store.rooms(installable_channels(record)),
    )
    return JSONResponse(status_code=201, content=view.model_dump(mode="json"))


@router.post(REMOVAL_PATH, response_model=AgentGroupsView, responses=_TOLD)
async def remove_agent_from_group(
    request: Request,
    agent_id: Annotated[str, Path()],
    body: RemovalAsked,
    asked: Asked,
) -> JSONResponse:
    """Take this agent out of one group chat. An install that is not this agent's is the 404."""
    record = await _changeable(request, agent_id, asked)
    store = _store(request)
    if not await store.remove(body.install_id, agent_id=agent_id, by=_by(asked)):
        raise _no_agent_here(asked, "install")
    view = groups_view(
        record,
        await store.installs_of(agent_id),
        await store.rooms(installable_channels(record)),
    )
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))
