"""A tool attached to an agent, or detached from it, on the install.

`brain.console.agent_tabs` decided that attaching is checked at the moment it happens and that
every add and remove reaches the ledger with who, when and why (`attach`, `detach`,
`A_RECORD_WRITTEN_BY_A_SECOND_CALL_IS_A_LINE_SOMEBODY_FORGETS`). An agent's tools were its
manifest's `allowed_tools`, sealed in its install, so nothing could attach or detach one. `0196`
builds this table and `brain.ops.attachment_store` is its one writer.

**One row per press on a tool, never edited, and never a connector.** A connector attached to an
agent is a name in `agent.agent.connectors`, the one list `brain.agents.binding.bound_capabilities`
compiles into its ceiling, so a row here for one would be a second store of the same fact; the
check holds every row to `part = 'tool'` (`brain.agents.attachments.
A_CONNECTOR_IS_THE_AGENTS_OWN_LIST_AND_NOTHING_ELSE`). A row carries the tool name it moved, so the
fold that decides an agent's tools reads rows alone. The newest row naming a tool decides it; a
tool no row names keeps the manifest's word.

**Its trigger writes the ledger entry** `AuditRecorder.compose_change` describes, in the same
transaction, so an attach and its record cannot be separated.

Task ids: M39.8.6, M39.2.1.2, M39.1.1.3
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.tables.identity import PRINCIPAL_ID_CHARS

#: How wide an agent's identifier may be, matching `brain.tables.leash.AGENT_ID_CHARS`.
AGENT_ID_CHARS: Final = 128
#: How wide a tool's or a connector's name may be: `brain.core.envelope.ToolDefinition.name`.
REFERENCE_CHARS: Final = 80
PART_CHARS: Final = 16
TRACE_ID_CHARS: Final = 128
REASON_CHARS: Final = 64
ENT_HASH_PATTERN: Final = r"^[0-9a-f]{32}$"
REASON_PATTERN: Final = r"^[a-z][a-z0-9_]{0,63}$"


class AttachmentPart(enum.StrEnum):
    """What a press is on: one tool, or one connector. Only a tool is ever a row here."""

    TOOL = "tool"
    CONNECTOR = "connector"


#: The one part a row may be on. A connector is the agent row's own list, not a row here.
TOOL_ROWS_ONLY: Final = f"part = '{AttachmentPart.TOOL.value}'"


class ToolAttachmentRow(Base):
    """`agent.tool_attachment`. One attach or detach, with the tools it moved."""

    __tablename__ = "tool_attachment"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    part: Mapped[str] = mapped_column(String(PART_CHARS), nullable=False)
    reference: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    attached: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tools: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)
    entitlement_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(TOOL_ROWS_ONLY, name="part"),
        CheckConstraint("length(btrim(reference)) > 0", name="names_what"),
        CheckConstraint("cardinality(tools) > 0", name="moves_a_tool"),
        CheckConstraint(
            "part <> 'tool' OR tools = ARRAY[reference]::text[]", name="a_tool_moves_itself"
        ),
        CheckConstraint(f"reason_code ~ '{REASON_PATTERN}'", name="reason_is_a_code"),
        CheckConstraint(f"entitlement_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        CheckConstraint("length(btrim(changed_by)) > 0", name="attributed"),
        CheckConstraint("length(btrim(trace_id)) > 0", name="traced"),
        Index("ix_tool_attachment_agent_changed", "agent_id", "changed_at"),
        {"schema": "agent"},
    )
