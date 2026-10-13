"""Two kinds of agent: a team agent, and a personal agent that is one person's alone.

The owner's direction on needs item 173 (2026-10-12) is that a person makes their own personal
agent without asking anybody, that a department administrator or a super administrator makes
both kinds, and that a personal agent is listed and used by its owner and by nobody else. Most of
that was already true of the data and none of it was a choice a person could see: an agent's
audience was `personal`, `department` or `company`, and who may make which was one capability
(`brain.agents.creation.AGENT_INSTALL_CAPABILITY`) that every route asked of everybody.

**The kind is derived from the audience, never stored beside it.** A `kind` column next to the
audience would be a second answer to "who may use this agent", and the day the two disagreed the
wrong one would be in force. A personal agent is an agent whose audience level is personal; every
other agent belongs to a department or the company and is a team agent. See
`THE_KIND_IS_THE_AUDIENCE_NAMED`.

**A person may make a personal agent only while the `personal_agents` switch is on, and the switch
ships off.** It widens who may start the builder from "holds the install authority" to "anybody
signed in", so it is a new behaviour in the repository's own sense and goes in behind a flag. An
administrator who holds the install authority makes both kinds with the switch off or on, as
before; the switch never narrows anybody. See `A_PERSON_MAKES_ONLY_THEIR_OWN_PERSONAL_AGENT`.

**What a person may make is decided here once, from two facts, and a route that needs it asks
this module.** Rejected: each route re-deriving it from the capability and the audience, which is
how the roster, the builder and the lifecycle would each have come to answer a little
differently. The authority over a team agent stays the install authority over the agent's row,
read through the caller's own reach, so a department administrator makes a team agent for their
department and a super administrator for any.

**A personal agent never reaches beyond its owner.** An agent is a lens: a run is the caller's
reach intersected with the agent's ceiling, so a personal agent whose ceiling is wide still
reaches only what its owner reaches. This module adds no second rule about reach.

Task ids: M39.10.1, M39.10.2, M39.10.3
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.model import AgentAudience
from brain.knowledge.visibility import Visibility

# ------------------------------------------------------------------ written-down reasons

#: Why there is no stored kind.
THE_KIND_IS_THE_AUDIENCE_NAMED: Final = (
    "A personal agent is an agent whose audience is personal; every other agent belongs to a "
    "department or the company. A kind stored beside the audience would be a second answer to "
    "who may use the agent, and the day they disagreed the wrong one would be in force."
)

#: Why a member's authority is the narrow one.
A_PERSON_MAKES_ONLY_THEIR_OWN_PERSONAL_AGENT: Final = (
    "Without the install authority a person may make an agent that only they can find, and "
    "nothing else: a team agent is seen by people other than its maker, so making one is the "
    "act the install authority exists to hold. With it, both kinds, as before."
)

#: What a person without the authority is told when they ask for a team agent.
ONLY_AN_ADMINISTRATOR_MAKES_A_TEAM_AGENT: Final = (
    "Nothing was made: only an administrator makes an agent for a team. You may make one that "
    "only you can use."
)

#: What a person is told when the switch is off and they have no install authority.
PERSONAL_AGENTS_ARE_NOT_SWITCHED_ON: Final = (
    "Nothing was made: making your own agent is not switched on for this company yet."
)

#: The words the page draws for each kind.
KIND_LABELS: Final[dict[str, str]] = {
    "team": "Team agent",
    "personal": "Personal agent",
}


class AgentKind(enum.StrEnum):
    """What an agent is for: a department's or the company's people, or one person."""

    TEAM = "team"
    PERSONAL = "personal"


def kind_of(audience: AgentAudience) -> AgentKind:
    """The kind an audience names. See `THE_KIND_IS_THE_AUDIENCE_NAMED`."""
    return AgentKind.PERSONAL if audience.level is Visibility.PERSONAL else AgentKind.TEAM


def kinds_a_person_may_make(*, installs: bool, personal_on: bool) -> tuple[AgentKind, ...]:
    """The kinds this person may make: both for the install authority, the personal one alone for
    anybody else while the switch is on, and none otherwise.

    `installs` is whether the caller's reach holds the install authority over anything at all; the
    route still asks the authority over the particular row for a team agent.
    """
    if installs:
        return (AgentKind.PERSONAL, AgentKind.TEAM)
    if personal_on:
        return (AgentKind.PERSONAL,)
    return ()


def refusal_for(kind: AgentKind, allowed: Iterable[AgentKind], *, personal_on: bool) -> str | None:
    """Why `kind` may not be made by somebody allowed `allowed`, or None when it may."""
    if kind in set(allowed):
        return None
    if kind is AgentKind.TEAM:
        return ONLY_AN_ADMINISTRATOR_MAKES_A_TEAM_AGENT
    return PERSONAL_AGENTS_ARE_NOT_SWITCHED_ON if not personal_on else None


async def personal_agents_on(sessions: async_sessionmaker[AsyncSession] | None) -> bool:
    """Whether a person may make their own agent now. Off with no database or no row."""
    from brain.ops.features import PERSONAL_AGENTS, is_on

    if sessions is None:
        return False
    async with sessions() as session:
        return await is_on(session, PERSONAL_AGENTS)
