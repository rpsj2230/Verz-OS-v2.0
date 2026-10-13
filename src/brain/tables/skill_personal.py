"""`agent.skill_personal`: a skill a person added for themselves, and whether they offered it.

One row for each skill a person added as their own (M40.3.2.1 to M40.3.2.4). **The row says whose a
skill is and nothing about what it is**: the digest and the person, when it was made and when it was
offered to the department. The skill is in `agent.skill` as every skill is, so accepting it into the
department's library is a decision about the same bytes under the same digest.

Task ids: M40.3.2.1, M40.3.2.3
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base

#: As `0231` states them, held equal by `tests/unit/test_tables.py`.
DIGEST_CHARS: Final = 64
PRINCIPAL_ID_CHARS: Final = 128


class SkillPersonalRow(Base):
    """One personal skill's owner and offer. See the module docstring."""

    __tablename__ = "skill_personal"

    digest: Mapped[str] = mapped_column(String(DIGEST_CHARS), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    made_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("digest ~ '^[0-9a-f]{64}$'", name="digest_shape"),
        CheckConstraint("length(btrim(owner_id)) > 0", name="owner_present"),
        Index("ix_agent_skill_personal_owner_id", "owner_id"),
        {"schema": "agent"},
    )
