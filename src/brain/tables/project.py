"""`agent.project` and `agent.project_item`: a person's own project, and what is in it (M40.7.7).

A project is a name, its owner and a list of references to threads and files that stay where they
are. **Nothing here is a copy and nothing here is memory**: the list names a conversation or a
knowledge item by id, a run reads the files through the reach the person holds when it is made, and
`brain.memory` reads none of it.

Task ids: M40.7.7
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base

#: As `0233` states them, held equal by `tests/unit/test_tables.py`.
PRINCIPAL_ID_CHARS: Final = 128
NAME_CHARS: Final = 120
REF_CHARS: Final = 128
KIND_CHARS: Final = 16
KINDS: Final[tuple[str, ...]] = ("file", "thread")


class ProjectRow(Base):
    """One person's project."""

    __tablename__ = "project"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    owner_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    name: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("length(btrim(owner_id)) > 0", name="owner_present"),
        CheckConstraint("length(btrim(name)) > 0", name="name_present"),
        Index("ix_agent_project_owner_id", "owner_id"),
        {"schema": "agent"},
    )


class ProjectItemRow(Base):
    """One thread or file in a project, by id."""

    __tablename__ = "project_item"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent.project.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(KIND_CHARS), nullable=False)
    ref: Mapped[str] = mapped_column(String(REF_CHARS), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        PrimaryKeyConstraint("project_id", "kind", "ref"),
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{one}'" for one in KINDS) + ")", name="kind_known"
        ),
        CheckConstraint("length(btrim(ref)) > 0", name="ref_present"),
        {"schema": "agent"},
    )
