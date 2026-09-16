"""Who changed a webhook subscriber from the console, what they changed, and when.

`ops.webhook_subscriber` records who registered a subscriber and when it stopped, and nothing
about who stopped it or who replaced its signing secret: a switch-off is an instant on the row and
a rotation changes no row at all, because the secret is a vault path. The Subscribers screen
declined to offer either control for that reason, since a change nobody can attribute afterwards
is a change nobody should be able to make from a browser. This table is the attribution: one row
per change, written in the transaction that makes it, never edited and never retired.

**One row per change, and the three changes are one vocabulary.** Registering, replacing the
secret and switching off are the three acts `brain.webhook_routes` performs, and a reader asking
"what happened to this subscriber, and who did it" reads one table in time order rather than
joining a registration column, a deactivation instant and a vault's audit device.

**It is not the audit ledger, and says so.** `brain.audit.ledger.AuditAction` has no member a
subscriber change could honestly be recorded under, and `SUBJECT_KINDS` no kind a subscriber id
fits, so no trigger here appends to `obs.audit_entry`. Adding both is the audit package's decision.
When it is made, a trigger on this table is the whole of the wiring, which is the shape `0050` and
`0052` already take: the row names its author, so the trigger has nothing to infer.

**No foreign key to `auth.principal` on `changed_by`**, for the reason `brain.tables.review`
gives: a key into the principal table would make retiring a person refuse, or delete, the record of
what they changed.

Task ids: M27.8.12
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.outbox import MAX_IDENTIFIER_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: Wide enough for the longest of the three words and no wider.
CHANGE_CHARS: Final = 16


class WebhookChange(enum.StrEnum):
    """What one console change did to one subscriber."""

    #: The subscriber was registered, and its first signing secret written.
    REGISTERED = "registered"
    #: Its signing secret was replaced with a new one.
    SECRET_REPLACED = "secret_replaced"  # noqa: S105
    #: It was switched off, for good. Switching back on is registering again under a new id.
    SWITCHED_OFF = "switched_off"


class WebhookChangeRow(Base):
    """`ops.webhook_change`. One change to one subscriber, by a named person, never edited."""

    __tablename__ = "webhook_change"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    subscriber_id: Mapped[str] = mapped_column(
        String(MAX_IDENTIFIER_CHARS),
        ForeignKey("ops.webhook_subscriber.subscriber_id", ondelete="RESTRICT"),
        nullable=False,
    )
    change: Mapped[str] = mapped_column(String(CHANGE_CHARS), nullable=False)
    changed_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: The time the vault stamped on the secret version this change wrote. None for a
    #: switch-off, which writes no secret, and when the vault's answer carried no readable time.
    secret_written_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(one_of("change", WebhookChange), name="change"),
        CheckConstraint("length(btrim(changed_by)) > 0", name="changed_by_present"),
        CheckConstraint(
            f"change <> '{WebhookChange.SWITCHED_OFF.value}' OR secret_written_at IS NULL",
            name="a_switch_off_writes_no_secret",
        ),
        Index("ix_ops_webhook_change_subscriber", "subscriber_id", "changed_at"),
        {"schema": "ops"},
    )
