"""`gate.break_glass_notice`: that a standing Super Admin was told a break-glass session opened.

`brain.identity.roles.open_break_glass` has always produced a `Notification` beside the session
and said a session nobody is told about is an unaudited admin account, and the console's
break-glass session, an approved elevation, told nobody: `brain.ops.notices` said "nothing sends
it yet". One row here is one standing Super Admin told about one session, written in the
approval's own transaction by `brain.gate.elevation_store`, so the session and its notices are
both or neither. The recipient reads their own on the Elevation screen, which is how a notice is
delivered, as an access request is delivered on the Access requests screen.

**A record that it was sent, never edited.** SELECT and INSERT, no UPDATE and no DELETE, and no
`deleted_at`. `recipient_id` is never the person who took the access.

Task ids: M1.2.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base, TimestampMixin
from brain.identity.roles import BreakGlassReason
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: Wide enough for the longest `BreakGlassReason`, as `brain.tables.elevation` has it.
REASON_CHARS: Final = 32


class BreakGlassNoticeRow(TimestampMixin, Base):
    """One standing Super Admin told about one break-glass session."""

    __tablename__ = "break_glass_notice"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: The approved elevation that opened the session. Its id is the session's ledger subject.
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("gate.elevation_request.id", ondelete="RESTRICT"),
        nullable=False,
    )
    #: Who was told.
    recipient_id: Mapped[str] = mapped_column(
        String(PRINCIPAL_ID_CHARS),
        ForeignKey("auth.principal.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: Who took the access, and who allowed it: values, copied so the notice reads on its own.
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    authorised_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    reason: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)
    #: When the session's grant lapses on its own.
    lapses_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(one_of("reason", BreakGlassReason), name="reason"),
        CheckConstraint("recipient_id <> principal_id", name="never_told_to_the_person_acting"),
        UniqueConstraint("request_id", "recipient_id"),
        {"schema": "gate"},
    )
