"""A request for an agent a person cannot yet run, kept and read (`0230`).

`record` writes as the asker and answers whether this was the first request for that agent from that
person, because the table holds one row for each and a second ask is not a second row; `of` reads
one person's own; `leads_of` answers who leads the department the request went to, which is the
person told. **A request carries no answer**: what a department does is a change to the agent's
audience made where those are made, so a request cannot be approved by filling a field in.

Task ids: M40.2.2.5
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.identity.organisation_store import current_lead, one_department
from brain.knowledge.search import PRINCIPAL_SETTING
from brain.member_activity import AgentRequest
from brain.tables.member_share import AgentRequestRow


def _as(principal_id: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(
        name=PRINCIPAL_SETTING, value=principal_id
    )


class StoredAgentRequests:
    """`agent.agent_request` read and written."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(self, one: AgentRequest) -> bool:
        """Keep one request as its asker. False when they had already asked for this agent."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(one.requested_by))
            made = await session.execute(
                pg_insert(AgentRequestRow)
                .values(
                    agent_id=one.agent_id,
                    requested_by=one.requested_by,
                    department=one.department,
                    requested_at=one.at,
                )
                .on_conflict_do_nothing(index_elements=["agent_id", "requested_by"])
                .returning(AgentRequestRow.id)
            )
            return made.first() is not None

    async def of(self, principal_id: str) -> tuple[AgentRequest, ...]:
        """This person's own requests, newest first."""
        async with self._sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        select(AgentRequestRow)
                        .where(AgentRequestRow.requested_by == principal_id)
                        .order_by(AgentRequestRow.requested_at.desc(), AgentRequestRow.id)
                    )
                )
                .scalars()
                .all()
            )
        return tuple(
            AgentRequest(
                agent_id=one.agent_id,
                requested_by=one.requested_by,
                department=one.department,
                at=one.requested_at,
            )
            for one in rows
        )

    async def leads_of(self, department: str) -> str | None:
        """Who leads this department now, or None when nobody does."""
        async with self._sessions() as session, session.begin():
            found = (await session.execute(one_department(department))).scalar_one_or_none()
            if found is None:
                return None
            lead = (await session.execute(current_lead(found))).one_or_none()
        return None if lead is None else str(lead[1])
