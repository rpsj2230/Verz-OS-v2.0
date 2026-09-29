"""How `/answer` reads the stored agents: every agent, each with the tools it carries now.

Moved out of `brain.app` on 2026-09-29 so that an install acceptance check can ask the very reader
the answer route is built with, which nothing under `src/brain` may do by importing the
application. `brain.app` builds its roster with this function and nothing else, so the check and
the route read one function.

**Each record is narrowed by its stored attachments before a run's ceiling is built from it**, which
is `brain.agents.attachments`' argument: a detached tool is absent from every catalogue from the
next question on, and the configuration hash `brain.gate.roster.setup_of` computes moves with it.

**Which channels each agent answers on is read beside it, by `agent_channels_for`**, and
`brain.api_routes.roster_of` keeps only the agents switched on for the channel a question arrived
on, for `brain.agents.channel_switches`' argument. Two readers rather than one that takes the
channel, because `AgentRoster` is also what the install checks and the routing check ask for the
records alone.

Task ids: M39.8.6, M39.2.4.1
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import every_agent, record_of
from brain.agents.attachments import narrowed
from brain.agents.channel_switches import switched_on
from brain.agents.model import AgentRecord
from brain.gate.context import Channel
from brain.gate.roster import AgentChannels, AgentRoster
from brain.ops.attachment_store import changes_in
from brain.ops.channel_switch_store import switches_in


def agent_roster_for(
    sessions: async_sessionmaker[AsyncSession] | None,
) -> AgentRoster | None:
    """How `/answer` reads the stored agents, or None on a process with no database.

    Every agent, as the Agents screen reads them; `brain.gate.roster.answer_roster` keeps the ones
    the person asking may run. A row that does not construct is left out, for
    `brain.agent_routes.record_of`'s reason.
    """
    if sessions is None:
        return None
    factory = sessions

    async def read() -> Sequence[AgentRecord]:
        async with factory() as session:
            rows = (await session.execute(every_agent())).scalars().all()
            records = [one for one in (record_of(row) for row in rows) if one is not None]
            changes = await changes_in(session, (one.agent_id for one in records))
        return [narrowed(one, changes) for one in records]

    return read


def agent_channels_for(
    sessions: async_sessionmaker[AsyncSession] | None,
) -> AgentChannels | None:
    """How `/answer` reads which channels each agent answers on, or None with no database."""
    if sessions is None:
        return None
    factory = sessions

    async def read(agent_ids: Sequence[str]) -> Mapping[str, frozenset[Channel]]:
        async with factory() as session:
            return switched_on(await switches_in(session, agent_ids))

    return read
