"""Switching a channel on or off for an agent, from its page.

`brain.agents.channel_switches` decides which channels an agent answers on and whether a switch may
be made, `brain.console.agent_tabs.channel_rows` decides which surfaces the page offers, and
`brain.ops.channel_switch_store` keeps each switch with its ledger entry; this is the route between
the page and them, and it decides only who may press.

**Channels are the connector administrator's, over the agent's department**, or over everything for
an agent no department owns (`agent_workspace_routes.place_of`): a channel is a connection the
install makes to a vendor, which is what `admin:connector` already governs, and where an agent
answers is part of what its department's administrator decides. Anybody else is told which role
would let them, and never whether the switch would have been allowed. See
`SWITCHING_IS_THE_DEPARTMENT_S_CONNECTOR_ROLE`.

**Anybody who may see the agent may see where it answers**, because that is where they can ask it.
The rows are `channel_rows` at the reader's own run reach, so a surface a run of this agent by this
reader could not be carried on is absent rather than drawn off; the web page is always drawn, and
the answer says in words when the agent answers nowhere (`channel_switches.NOT_REACHABLE`).

Task ids: M39.2.4.1, M39.2.4.2, M39.2.4.3, M39.2.4.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from brain.agent_routes import (
    _require_session_factory,
    _visible_record,
    declared_channels,
    product_field_policy,
)
from brain.agent_workspace_routes import place_of
from brain.agents.channel_switches import (
    NOT_REACHABLE,
    ChannelState,
    ChannelSwitchError,
    reachable,
    states,
    switched_on,
    to_switch,
)
from brain.agents.model import AgentRecord
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.attribution import trace_of_request
from brain.console.agent_tabs import channel_rows
from brain.console.scoped_authority import within_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.gate.context import Channel
from brain.ops.channel_switch_store import StoredChannelSwitches, switches_in

log = structlog.get_logger()

SWITCHING_IS_THE_DEPARTMENT_S_CONNECTOR_ROLE: Final = (
    "Where an agent answers is a connection the install makes to a vendor, and a department's "
    "connections are its connector administrator's: a channel is switched on or off for an agent "
    "by whoever holds the connector authority over the agent's department. Anybody else is told "
    "which role, and never whether the switch would have been allowed."
)

SWITCHING_NEEDS_THE_CONNECTOR_ROLE: Final = (
    "Switching this agent's channels needs the connector role for its department."
)

CHANNEL_AUTHORITY: Final = Capability(value="admin:connector")

#: The reason code a switch from the page is recorded with.
FROM_THE_AGENT_PAGE: Final = "switched_on_the_agent_page"

CHANNELS_PATH: Final = "/agents/{agent_id}/channels"


def may_switch(reach: EntitlementSet, record: AgentRecord, now: datetime) -> bool:
    """Whether this reach may switch this agent's channels. See the reason above."""
    return within_reach(reach, CHANNEL_AUTHORITY, place_of(record), now)


class ChannelStateView(BaseModel):
    """One channel the page draws, and whether the agent answers there."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    on: bool
    #: How an answer is laid out there, or None on the web page.
    profile: str | None
    group_installable: bool


class ChannelsView(BaseModel):
    """Where this agent answers, as this reader may see it, and whether they may switch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    channels: list[ChannelStateView]
    #: False when no channel at all is switched on for the agent.
    reachable: bool
    #: `NOT_REACHABLE` when `reachable` is false, and None otherwise.
    unreachable: str | None
    may_switch: bool


class SwitchAsked(BaseModel):
    """One switch: a channel on or off."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: Channel
    on: bool


def _refused(message: str, status: int = 409) -> JSONResponse:
    return JSONResponse(status_code=status, content={"message": message})


def shown_to(
    record: AgentRecord, on: frozenset[Channel], reach: EntitlementSet, now: datetime
) -> tuple[ChannelState, ...]:
    """The web page and every surface a run of this agent by this reach could be carried on.

    `reach` is the reader's own; `channel_rows` computes the run's reach from it and the record.
    """
    rows = channel_rows(
        reach, record, declared_channels(), product_field_policy(), enabled=on, now=now
    )
    return states(rows, on)


def view_of(record: AgentRecord, on: frozenset[Channel], asked: Asking) -> ChannelsView:
    shown = shown_to(record, on, asked.reach, asked.now)
    answers = reachable(on)
    return ChannelsView(
        agent_id=record.agent_id,
        channels=[
            ChannelStateView(
                channel=one.channel.value,
                on=one.on,
                profile=None if one.profile is None else one.profile.value,
                group_installable=one.group_installable,
            )
            for one in shown
        ],
        reachable=answers,
        unreachable=None if answers else NOT_REACHABLE,
        may_switch=may_switch(asked.reach, record, asked.now),
    )


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(CHANNELS_PATH, response_model=ChannelsView, responses=COMMON_RESPONSES)
async def agent_channels(request: Request, agent_id: str, asked: Asked) -> ChannelsView:
    """Where this agent answers, for anybody who may see it (M39.2.4.1, M39.2.4.3)."""
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        on = switched_on(await switches_in(session, (agent_id,))).get(agent_id, frozenset())
    return view_of(record, on, asked)


@router.post(CHANNELS_PATH, response_model=ChannelsView, responses=COMMON_RESPONSES)
async def switch_channel(
    request: Request, agent_id: str, body: SwitchAsked, asked: Asked
) -> JSONResponse | ChannelsView:
    """Switch one channel on or off for this agent, checked now (M39.2.4.1)."""
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        on = switched_on(await switches_in(session, (agent_id,))).get(agent_id, frozenset())
    if not may_switch(asked.reach, record, asked.now):
        return _refused(SWITCHING_NEEDS_THE_CONNECTOR_ROLE, 403)
    try:
        to_switch(shown_to(record, on, asked.reach, asked.now), body.channel, body.on)
    except ChannelSwitchError as refused:
        return _refused(str(refused))
    await StoredChannelSwitches(factory).switch(
        agent_id=agent_id,
        channel=body.channel,
        switched_on=body.on,
        by=asked.caller.principal.id,
        reason_code=FROM_THE_AGENT_PAGE,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
        at=asked.now,
    )
    after = on | {body.channel} if body.on else on - {body.channel}
    return view_of(record, frozenset(after), asked)
