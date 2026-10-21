"""`ops.deletion_request`: a person's ask to be deleted, until the retention owner acts.

Not the erasure queue's row. `ops.erasure_request` is carried out by the worker on its next run with
nobody asked again, so a person's own click filed there would be an erase and not a request. This
row is only the ask: who, when, and once the retention owner has filed the erasure, who did and
which erasure it became. **It holds no reason and no list of what a deletion reaches**, because that
list is `brain.ops.erasure`'s answer at the time it runs. See `0273` for the row-level rules.

Task ids: M40.4.2.3
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base

#: As `0273` states them, held equal by `tests/unit/test_tables.py`.
PRINCIPAL_ID_CHARS: Final = 128
ERASURE_REQUEST_ID_CHARS: Final = 128


class DeletionRequestRow(Base):
    """One person's ask to be deleted. Waiting while `decided_at` is empty."""

    __tablename__ = "deletion_request"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    subject_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    erasure_request_id: Mapped[str | None] = mapped_column(
        String(ERASURE_REQUEST_ID_CHARS), nullable=True
    )

    __table_args__ = (
        CheckConstraint("length(btrim(subject_id)) > 0", name="subject_present"),
        CheckConstraint(
            "(decided_by IS NULL) = (decided_at IS NULL)"
            " AND (decided_at IS NULL) = (erasure_request_id IS NULL)",
            name="decided_whole_or_not_at_all",
        ),
        Index(
            "uq_deletion_request_one_waiting",
            "subject_id",
            unique=True,
            postgresql_where=text("decided_at IS NULL"),
        ),
        {"schema": "ops"},
    )
