"""`auth.member_preference`: one setting a person keeps about themselves (M40.4.1.4, M40.5.2).

A person, a key from a closed list and a document: whether they learn from them, which channel is
primary, what each channel may tell them, where an envelope waits for them and when digests and
automations are held. The list is the database's (`key_known`) and what each value looks like is
`brain.member.preferences`'s.

**Points at nothing.** The person is a value, so a row can outlive a directory row; the erasure
store names the column and removes the rows with the person.

Task ids: M40.4.1.4, M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

from sqlalchemy import CheckConstraint, DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base

#: As `auth.principal.id`, copied for `0009`'s reason.
PRINCIPAL_ID_CHARS: Final = 128
KEY_CHARS: Final = 32

#: The settings a person may keep. Held equal to `0228`'s list by a test.
KEYS: Final[tuple[str, ...]] = (
    "approval_route",
    "channel_notices",
    "learning_opt_out",
    "primary_channel",
    "quiet_hours",
)


class MemberPreferenceRow(Base):
    """One person's one setting. See the module docstring."""

    __tablename__ = "member_preference"

    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), primary_key=True)
    key: Mapped[str] = mapped_column(String(KEY_CHARS), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("length(btrim(principal_id)) > 0", name="principal_present"),
        CheckConstraint("key IN (" + ", ".join(f"'{one}'" for one in KEYS) + ")", name="key_known"),
        {"schema": "auth"},
    )
