"""An agent's channel switches, read and written.

`brain.agents.channel_switches` decides which channels an agent answers on and whether a switch may
be made; this keeps the switches in `agent.channel_switch` and decides nothing. A switch is written
in its presser's own name, with the three settings `0159`'s trigger reads for its ledger entry, and
a row that no longer constructs is absent rather than a fault, for `brain.ops.skill_store`'s reason:
a channel whose row does not construct is then off, which is the direction an unreadable switch has
to fail in.

Task ids: M39.2.4.1, M39.2.4.2
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.channel_switches import ChannelSwitch
from brain.gate.context import Channel
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.tables.audit import attributed_to
from brain.tables.channel_switch import ChannelSwitchRow, switch_row

log = structlog.get_logger()

#: The most switches one agent's channels are folded from. A resource bound on the read.
MAX_ROWS: Final = 2_000


def switch_of(row: ChannelSwitchRow) -> ChannelSwitch | None:
    try:
        return ChannelSwitch(
            agent_id=row.agent_id,
            channel=Channel(row.channel),
            switched_on=row.switched_on,
            at=row.changed_at,
            changed_by=row.changed_by,
        )
    except ValueError as exc:
        log.warning("channel switch does not construct", error=type(exc).__name__)
        return None


async def switches_in(session: AsyncSession, agent_ids: Iterable[str]) -> tuple[ChannelSwitch, ...]:
    """Every switch on these agents, oldest first."""
    wanted = sorted(set(agent_ids))
    if not wanted:
        return ()
    rows = (
        (
            await session.execute(
                select(ChannelSwitchRow)
                .where(ChannelSwitchRow.agent_id.in_(wanted))
                .order_by(ChannelSwitchRow.changed_at)
                .limit(MAX_ROWS * len(wanted))
            )
        )
        .scalars()
        .all()
    )
    return tuple(one for one in (switch_of(row) for row in rows) if one is not None)


def _as(principal_id: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(
        name=PRINCIPAL_SETTING, value=principal_id
    )


class StoredChannelSwitches:
    """`agent.channel_switch` over the application's sessions."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def switches(self, agent_id: str) -> tuple[ChannelSwitch, ...]:
        async with self._sessions() as session:
            return await switches_in(session, (agent_id,))

    async def switch(
        self,
        *,
        agent_id: str,
        channel: Channel,
        switched_on: bool,
        by: str,
        reason_code: str,
        ent_hash: str,
        trace_id: str,
        at: datetime,
    ) -> None:
        """Keep one switch, and the ledger entry its trigger appends, in `by`'s name."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(by))
            for statement in attributed_to(actor_id=by, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            session.add(
                switch_row(
                    agent_id=agent_id,
                    channel=channel,
                    switched_on=switched_on,
                    by=by,
                    reason_code=reason_code,
                    ent_hash=ent_hash,
                    trace_id=trace_id,
                    at=at,
                )
            )
