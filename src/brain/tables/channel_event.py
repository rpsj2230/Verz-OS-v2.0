"""`gate.channel_event`: every inbound message a channel delivered, keyed so redelivery is refused.

`brain.gate.ingress.ChannelEvent.dedupe_key` is `(channel, external_id)` and has been since the
ingress module was written; nothing held it. A channel that redelivers, which is every webhook
provider on a timeout, would answer the same question twice, and for a message that asks for a
side effect that is the side effect done twice. The primary key is the unique index on the two
columns, so a second delivery is refused by the database rather than by a check someone could
race (M3.2.2).

**Two columns and not one joined string**, for the reason `dedupe_key` gives: an identifier
containing the separator could otherwise be forged into another channel's.

**No sender and no text.** The row proves a message arrived, which is all dedupe needs. A sender
identity is on the projection denylist and a message is the person's own words; neither belongs in
a table whose only reader is the insert that tries to add a second copy.

Task ids: M3.2.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.gate.context import Channel
from brain.tables.identity import one_of

#: The longest external id kept. Every channel this repository ships builds ids far shorter; a
#: longer one is refused by `brain.gate.event_store` rather than truncated into a collision.
EXTERNAL_ID_CHARS: Final = 255
CHANNEL_CHARS: Final = 16


class ChannelEventRow(Base):
    """`gate.channel_event`. One delivered message, once."""

    __tablename__ = "channel_event"

    channel: Mapped[str] = mapped_column(String(CHANNEL_CHARS), nullable=False)
    external_id: Mapped[str] = mapped_column(String(EXTERNAL_ID_CHARS), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("channel", "external_id"),
        CheckConstraint(one_of("channel", Channel), name="channel"),
        CheckConstraint("length(btrim(external_id)) >= 1", name="external_id_present"),
        {"schema": "gate"},
    )
