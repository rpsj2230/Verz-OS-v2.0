"""An agent's tool and connector presses, read and written.

`brain.agents.attachments` decides which tools an agent carries and whether a press may be made;
this keeps the presses in `agent.tool_attachment` and decides nothing. A press is written in its
presser's own name, with the three settings `0160`'s trigger reads for its ledger entry, and a row
that no longer constructs is absent rather than a fault, for `brain.ops.skill_store`'s reason.

Task ids: M39.8.6, M39.1.1.3
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.attachments import AttachmentChange
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.tables.attachment import AttachmentPart, ToolAttachmentRow
from brain.tables.audit import attributed_to

log = structlog.get_logger()

#: The most presses one agent's tools are folded from. A resource bound on the read.
MAX_ROWS: Final = 2_000


def change_of(row: ToolAttachmentRow) -> AttachmentChange | None:
    try:
        return AttachmentChange(
            agent_id=row.agent_id,
            part=AttachmentPart(row.part),
            reference=row.reference,
            attached=row.attached,
            tools=tuple(row.tools),
            at=row.changed_at,
            changed_by=row.changed_by,
        )
    except ValueError as exc:
        log.warning("tool attachment does not construct", error=type(exc).__name__)
        return None


async def changes_in(
    session: AsyncSession, agent_ids: Iterable[str]
) -> tuple[AttachmentChange, ...]:
    """Every press on these agents, oldest first."""
    wanted = sorted(set(agent_ids))
    if not wanted:
        return ()
    rows = (
        (
            await session.execute(
                select(ToolAttachmentRow)
                .where(ToolAttachmentRow.agent_id.in_(wanted))
                .order_by(ToolAttachmentRow.changed_at)
                .limit(MAX_ROWS * len(wanted))
            )
        )
        .scalars()
        .all()
    )
    return tuple(one for one in (change_of(row) for row in rows) if one is not None)


def _as(principal_id: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(
        name=PRINCIPAL_SETTING, value=principal_id
    )


class StoredAttachments:
    """`agent.tool_attachment` over the application's sessions."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def changes(self, agent_id: str) -> tuple[AttachmentChange, ...]:
        async with self._sessions() as session:
            return await changes_in(session, (agent_id,))

    async def press(
        self,
        *,
        agent_id: str,
        part: AttachmentPart,
        reference: str,
        attached: bool,
        tools: Sequence[str],
        by: str,
        reason_code: str,
        ent_hash: str,
        trace_id: str,
        at: datetime,
    ) -> None:
        """Keep one press, and the ledger entry its trigger appends, in `by`'s name."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(by))
            for statement in attributed_to(actor_id=by, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            session.add(
                ToolAttachmentRow(
                    id=uuid.uuid4(),
                    agent_id=agent_id,
                    part=part.value,
                    reference=reference,
                    attached=attached,
                    tools=list(tools),
                    changed_by=by,
                    reason_code=reason_code,
                    entitlement_hash=ent_hash,
                    trace_id=trace_id,
                    changed_at=at,
                )
            )
