"""An agent's tool and connector presses, read and written.

`brain.agents.attachments` decides which tools and connectors an agent carries and whether a press
may be made; this keeps them and decides nothing. A tool press is a row of `agent.tool_attachment`
written in its presser's own name, with the three settings `0196`'s trigger reads for its ledger
entry, and a row that no longer constructs is absent rather than a fault, for
`brain.ops.skill_store`'s reason.

**A connector press writes the agent's own `connectors` column and nothing else**
(`brain.agents.attachments.A_CONNECTOR_IS_THE_AGENTS_OWN_LIST_AND_NOTHING_ELSE`). The write is a
compare and set on the list the decision was made from, so two presses made from one read cannot
both land and the second is told the agent moved, rather than one silently undoing the other. The
agent row's own trigger records each connector added or taken away, with the actor, reach and trace
`attributed_to` sets and the reason this sets in `REASON_SETTING`.

Task ids: M39.8.6, M39.1.1.3
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.attachments import AttachmentChange
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.tables.agent import AgentRow
from brain.tables.attachment import AttachmentPart, ToolAttachmentRow
from brain.tables.audit import attributed_to

log = structlog.get_logger()

#: The most presses one agent's tools are folded from. A resource bound on the read.
MAX_ROWS: Final = 2_000

#: The transaction setting a connector press names its reason in, which the agent row's trigger
#: reads (`0196`). Held equal to the migration's copy by `tests/unit/test_attachment_store.py`.
REASON_SETTING: Final = "brain.reason_code"


class AgentMovedError(Exception):
    """The agent's connector list moved between the read a press was decided on and its write."""


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

    async def bind_connectors(
        self,
        *,
        agent_id: str,
        was: Sequence[str],
        becomes: Sequence[str],
        by: str,
        reason_code: str,
        ent_hash: str,
        trace_id: str,
    ) -> None:
        """Write the agent's connector list, when it still reads `was`. See the reason above.

        Raises `AgentMovedError` when it no longer does, or the agent is gone or archived.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(_as(by))
            for statement in attributed_to(actor_id=by, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            await session.execute(
                text("SELECT set_config(:name, :value, true)").bindparams(
                    name=REASON_SETTING, value=reason_code
                )
            )
            written = (
                await session.execute(
                    update(AgentRow)
                    .where(
                        AgentRow.id == agent_id,
                        AgentRow.archived_at.is_(None),
                        AgentRow.connectors == list(was),
                    )
                    .values(connectors=list(becomes))
                    .returning(AgentRow.id)
                )
            ).scalar_one_or_none()
            if written is None:
                raise AgentMovedError(agent_id)
