"""Which channels an agent answers on, once people have switched them on and off.

An agent answers only on the channels an administrator switched on for it, never on every channel
by default (`docs/requirements/register.json` OWN-7, ARC-A-171, OWN-56). `brain.console.agent_tabs`
decided what the page offers (`channel_rows`: the surfaces a run could be carried on, each with a
profile derived from its capabilities and whether it takes a group install), and nothing stored
whether a surface was switched on, so every stored agent answered wherever it could be addressed.
This module is the fold over stored switches, the one decision a press becomes, and the filter the
answer route applies.

**The web page is a channel, and it is switched on like any other.** `Channel.CONSOLE` has no
adapter, because the page is the product's own screen and is laid out by it, so it is not one of
`channel_rows`' offers; it is a row of its own, always offered, whose on and off are stored exactly
as a chat's are. The rejected shape was treating the web page as always on: an agent an
administrator meant for one chat would then answer on the page to everybody who can see it, which
is the default the requirement refuses. See `THE_WEB_PAGE_IS_A_CHANNEL_THAT_IS_SWITCHED_ON`.

**A channel no switch names is off.** The newest switch for an agent and a channel decides, and
nothing else: an agent nobody switched on answers nowhere, and its page says so in plain words
(`NOT_REACHABLE`). `0159b` switched on, for every agent that existed when it ran, the web page and
every channel it could be reached on then (each connected chat that reads a leading mention, and
the API where a service account could ask), so nothing that answered before stops answering
anywhere. The create flow switches the web page on for a new agent unless the person creating it
unticks it, and nothing else.

**An agent switched off for a channel is refused there in the shape of an agent the person cannot
use.** `answering_on` drops it from the roster before `brain.gate.roster.answer_roster` sees it, so
an address naming it falls through to the default agent exactly as an address naming an agent the
person may not use does (`brain.gate.select`). A distinct refusal ("that agent is not on this
channel") would tell a person on a chat which agents exist that they cannot reach from there. See
`A_CHANNEL_SWITCHED_OFF_IS_REFUSED_AS_AN_AGENT_NOBODY_MAY_USE`.

Task ids: M39.2.4.1, M39.2.4.2, M39.2.4.3, M39.2.4.4
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.agents.model import AgentRecord
from brain.console.agent_tabs import ChannelRow, RenderProfile
from brain.gate.context import Channel

# ------------------------------------------------------------------ written-down reasons
THE_WEB_PAGE_IS_A_CHANNEL_THAT_IS_SWITCHED_ON: Final = (
    "The web page is switched on and off for an agent as a chat is. An agent that answered on the "
    "page whatever was switched would answer everybody who can see it there, which is the "
    "on-every-channel default the owner refused."
)
A_CHANNEL_SWITCHED_OFF_IS_REFUSED_AS_AN_AGENT_NOBODY_MAY_USE: Final = (
    "An agent that is not switched on for the channel a question arrives on is left out of the "
    "roster that question is answered from, so naming it reaches the default agent as naming an "
    "agent the person may not use does, and nothing tells a person which agents exist elsewhere."
)

# ------------------------------------------------------------ what the page says
#: The page's words for an agent no channel is switched on for.
NOT_REACHABLE: Final = "Not reachable: no channel is switched on"
#: One refusal for a channel this agent is not offered on here, whichever reason is the true one.
NOT_A_CHANNEL_HERE: Final = "That is not a channel this agent can be switched on for."
ALREADY_ON: Final = "That channel is already switched on for this agent."
ALREADY_OFF: Final = "That channel is already switched off for this agent."

#: The web page, as the gate names the channel a signed-in browser asks on.
WEB: Final = Channel.CONSOLE


class ChannelSwitchError(ValueError):
    """A switch that cannot be made, in words a person can be shown."""


@dataclass(frozen=True)
class ChannelSwitch:
    """One press: a channel switched on or off for one agent, by whom and when."""

    agent_id: str
    channel: Channel
    switched_on: bool
    at: datetime
    changed_by: str


@dataclass(frozen=True)
class ChannelState:
    """One channel the page draws for this agent, and whether it is switched on."""

    channel: Channel
    on: bool
    #: How an answer is laid out there, or None on the web page, which lays out its own.
    profile: RenderProfile | None
    #: Whether an install into a shared conversation is possible there (M39.2.4.4).
    group_installable: bool


def switched_on(switches: Iterable[ChannelSwitch]) -> dict[str, frozenset[Channel]]:
    """The channels each agent is switched on for: the newest switch per agent and channel.

    Ordered by the switches' own instants, and for two at one instant by the order given, which is
    the order the store read them in; so a list read newest first decides as one read oldest first.
    An agent with no switch on is absent, never mapped to an empty set a caller could mistake for
    "not asked".
    """
    newest: dict[tuple[str, Channel], bool] = {}
    for one in sorted(switches, key=lambda switch: switch.at):
        newest[(one.agent_id, one.channel)] = one.switched_on
    on: dict[str, set[Channel]] = {}
    for (agent_id, channel), state in newest.items():
        if state:
            on.setdefault(agent_id, set()).add(channel)
    return {agent_id: frozenset(channels) for agent_id, channels in on.items()}


def answering_on(
    records: Iterable[AgentRecord], on: Mapping[str, frozenset[Channel]], channel: Channel
) -> tuple[AgentRecord, ...]:
    """The stored agents that answer on this channel, in the order given.

    See `A_CHANNEL_SWITCHED_OFF_IS_REFUSED_AS_AN_AGENT_NOBODY_MAY_USE`.
    """
    return tuple(one for one in records if channel in on.get(one.agent_id, frozenset()))


def states(rows: Sequence[ChannelRow], on: frozenset[Channel]) -> tuple[ChannelState, ...]:
    """The web page first, then every surface `channel_rows` offered, each with its switch.

    `rows` is `brain.console.agent_tabs.channel_rows` at this reader's run reach, built with
    `enabled=on`, so a surface is drawn only where a run of this agent by this reader could be
    carried on it; the web page is always drawn, for
    `THE_WEB_PAGE_IS_A_CHANNEL_THAT_IS_SWITCHED_ON`.
    """
    web = ChannelState(channel=WEB, on=WEB in on, profile=None, group_installable=False)
    return (
        web,
        *(
            ChannelState(
                channel=one.channel,
                on=one.enabled,
                profile=one.profile,
                group_installable=one.group_installable,
            )
            for one in rows
            if one.channel is not WEB
        ),
    )


def reachable(on: frozenset[Channel]) -> bool:
    """Whether this agent answers anywhere at all. False is `NOT_REACHABLE`."""
    return bool(on)


def to_switch(shown: Sequence[ChannelState], channel: Channel, switched: bool) -> None:
    """Refuse a switch that cannot be made, or return having refused nothing.

    A channel with no row is refused in one sentence whether this install has no such surface or a
    run of this agent could not be carried there, for `agent_tabs.enable`'s reason: answering the
    two differently would make the switch a way of asking which adapters are configured. A switch
    to the state the channel is already in is refused too, so every row on the ledger is a change.
    """
    found = next((one for one in shown if one.channel is channel), None)
    if found is None:
        raise ChannelSwitchError(NOT_A_CHANNEL_HERE)
    if found.on and switched:
        raise ChannelSwitchError(ALREADY_ON)
    if not found.on and not switched:
        raise ChannelSwitchError(ALREADY_OFF)
