"""How `/answer` reads the stored agents: every agent, each with the tools it carries now.

Moved out of `brain.app` on 2026-09-29 so that an install acceptance check can ask the very reader
the answer route is built with, which nothing under `src/brain` may do by importing the
application. `brain.app` builds its roster with this function and nothing else, so the check and
the route read one function.

**Each record is narrowed by its stored attachments before a run's ceiling is built from it**, which
is `brain.agents.attachments`' argument: a detached tool is absent from every catalogue from the
next question on, and the configuration hash `brain.gate.roster.setup_of` computes moves with it.

Task ids: M39.8.6
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import read_stored_agents
from brain.agents.attachments import narrowed
from brain.gate.roster import AgentRoster, StoredAgents
from brain.ops.attachment_store import changes_in


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

    async def read() -> StoredAgents:
        async with factory() as session:
            stored = await read_stored_agents(session)
            changes = await changes_in(session, (one.agent_id for one in stored.records))
        return StoredAgents(
            records=[narrowed(one, changes) for one in stored.records],
            install_hashes=stored.install_hashes,
        )

    return read
