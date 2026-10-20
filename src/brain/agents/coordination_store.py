"""What a coordinating agent may call and whether it may fan out: the store behind two tables.

`agent.agent_callee` and `agent.agent_fanout` (`0272`) hold two administrator decisions about an
agent: **which agents it may hand a subtask to** (M18.5.1) and **whether it may run them at the same
time** (M18.6.2). `brain.orchestration.coordinator` says what each means; this reads and writes the
rows, in the session's own name, and decides nothing about who may. The caller asks the lifecycle
authority over the agent and hands this the person as a value, as `brain.agents.audience_store`
does.

**Reading is one statement for every agent at once**, `links`, so the run that asks who a
coordinator may call and a roster that draws a badge cost one query and not one per agent.

**Adding what is there is a no-op and withdrawing what is not is a refusal to say so.** A second add
of a live link returns without writing, and a withdrawal of a link that is not live returns False,
which a route answers as it answers an agent that is not there.

**A grant is a live row and a withdrawal is two columns written once**, so which agents a
coordinator was allowed to call on the day a run happened can be read back from the table.

Task ids: M18.5.1, M18.6.2
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from brain.tables.agent_coordination import AgentCalleeRow, AgentFanoutRow


async def _as(session: AsyncSession, principal: str) -> None:
    await session.execute(
        text("SELECT set_config('app.principal_id', :who, true)"), {"who": principal}
    )


async def links(session: AsyncSession) -> Mapping[str, tuple[str, ...]]:
    """Every live link, by coordinator, each list sorted. A coordinator with none is not a key."""
    rows = (
        await session.execute(
            select(AgentCalleeRow.coordinator_id, AgentCalleeRow.callee_id)
            .where(AgentCalleeRow.removed_at.is_(None))
            .order_by(AgentCalleeRow.coordinator_id, AgentCalleeRow.callee_id)
        )
    ).all()
    found: dict[str, list[str]] = {}
    for coordinator_id, callee_id in rows:
        found.setdefault(coordinator_id, []).append(callee_id)
    return {key: tuple(value) for key, value in found.items()}


async def callees_of(session: AsyncSession, coordinator_id: str) -> tuple[str, ...]:
    """The agents this coordinator may hand a subtask to, sorted. Empty when it may call none."""
    return (await links(session)).get(coordinator_id, ())


async def add_callee(
    session: AsyncSession, *, coordinator_id: str, callee_id: str, by: str
) -> bool:
    """Allow `coordinator_id` to hand a subtask to `callee_id`, in the adder's own name.

    True when a row was written, False when the link was already live. An agent is not its own
    callee, and the table says so as well: the refusal here is the one a route can answer in words
    before the database is asked.
    """
    if coordinator_id == callee_id:
        msg = "an agent cannot be allowed to call itself"
        raise ValueError(msg)
    await _as(session, by)
    live = (
        await session.execute(
            select(AgentCalleeRow.id).where(
                AgentCalleeRow.coordinator_id == coordinator_id,
                AgentCalleeRow.callee_id == callee_id,
                AgentCalleeRow.removed_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if live is not None:
        return False
    session.add(AgentCalleeRow(coordinator_id=coordinator_id, callee_id=callee_id, added_by=by))
    await session.flush()
    return True


async def remove_callee(
    session: AsyncSession, *, coordinator_id: str, callee_id: str, by: str
) -> bool:
    """Withdraw a link, in the remover's own name. False when there was none live."""
    await _as(session, by)
    done = await session.execute(
        update(AgentCalleeRow)
        .where(
            AgentCalleeRow.coordinator_id == coordinator_id,
            AgentCalleeRow.callee_id == callee_id,
            AgentCalleeRow.removed_at.is_(None),
        )
        .values(removed_by=by, removed_at=text("statement_timestamp()"))
        .returning(AgentCalleeRow.id)
    )
    return done.first() is not None


async def fan_out_agents(session: AsyncSession) -> frozenset[str]:
    """Every agent an administrator let run its specialists at the same time."""
    rows = (
        await session.execute(
            select(AgentFanoutRow.agent_id).where(AgentFanoutRow.removed_at.is_(None))
        )
    ).scalars()
    return frozenset(rows)


async def fan_out_enabled(session: AsyncSession, agent_id: str) -> bool:
    """Whether this agent may run its specialists at the same time. False unless a row is live."""
    return agent_id in await fan_out_agents(session)


async def set_fan_out(session: AsyncSession, *, agent_id: str, enabled: bool, by: str) -> bool:
    """Let an agent run its specialists together, or take that back, in the caller's own name.

    True when this changed anything, False when it already was as asked.
    """
    await _as(session, by)
    if enabled:
        if await fan_out_enabled(session, agent_id):
            return False
        session.add(AgentFanoutRow(agent_id=agent_id, enabled_by=by))
        await session.flush()
        return True
    done = await session.execute(
        update(AgentFanoutRow)
        .where(AgentFanoutRow.agent_id == agent_id, AgentFanoutRow.removed_at.is_(None))
        .values(removed_by=by, removed_at=text("statement_timestamp()"))
        .returning(AgentFanoutRow.id)
    )
    return done.first() is not None
