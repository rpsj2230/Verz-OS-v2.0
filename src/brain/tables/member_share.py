"""`agent.artifact_share` and `agent.agent_request`: two things a member does that need a record.

An artifact handed to a colleague (M40.3.3.3) and a request for an agent the person cannot yet run
(M40.2.2.5). **Neither row decides anything.** A share is an artifact, two people and an instant,
and the read is decided at the moment of reading by `brain.member_library.open_share`; a request
has no answer column, so it cannot be approved by filling one in. Both point at nothing.

Task ids: M40.3.3.3, M40.2.2.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base

#: As `0229` states them, held equal by `tests/unit/test_tables.py`.
PRINCIPAL_ID_CHARS: Final = 128
ARTIFACT_ID_CHARS: Final = 128
AGENT_ID_CHARS: Final = 128
DEPARTMENT_CHARS: Final = 60


class ArtifactShareRow(Base):
    """One artifact shared with one colleague by one person."""

    __tablename__ = "artifact_share"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    artifact_id: Mapped[str] = mapped_column(String(ARTIFACT_ID_CHARS), nullable=False)
    shared_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    shared_with: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    shared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("artifact_id", "shared_by", "shared_with", name="one_share_each"),
        CheckConstraint("shared_by <> shared_with", name="not_with_oneself"),
        CheckConstraint("length(btrim(artifact_id)) > 0", name="artifact_present"),
        CheckConstraint("length(btrim(shared_by)) > 0", name="sharer_present"),
        CheckConstraint("length(btrim(shared_with)) > 0", name="colleague_present"),
        Index("ix_agent_artifact_share_shared_with", "shared_with"),
        {"schema": "agent"},
    )


class AgentRequestRow(Base):
    """One person's request to be able to run one agent, addressed to its department."""

    __tablename__ = "agent_request"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    department: Mapped[str] = mapped_column(String(DEPARTMENT_CHARS), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("agent_id", "requested_by", name="one_request_each"),
        CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        CheckConstraint("length(btrim(requested_by)) > 0", name="asker_present"),
        CheckConstraint("length(btrim(department)) > 0", name="department_present"),
        Index("ix_agent_agent_request_department", "department"),
        {"schema": "agent"},
    )
