"""`ops.alert_acknowledgement`: who acknowledged an alert, and when (M27.15.45).

The row behind `brain.ops.alert_acknowledgement`. `0224` builds it.

**An alert is identified by what it is about and when it began.** Nothing on this install stores
an alert: an incident is read off the worker's newest attempt at a source, and it began when that
attempt did. So an acknowledgement is keyed on the kind of alert, its subject and its `since`, and
a source that recovers and fails again is a new incident with no acknowledgement. Rejected: keying
on the subject alone, which would silence every later failure of a source for ever after one
person pressed a button once.

**The subject is a value, and so is the person.** The subject is a connector's name and the person
is a principal id, with no key into either table, so an acknowledgement is not deleted by a
connection being removed or a person leaving. It is a record of who said they had seen it.

**Written once, in the session's own name, and never updated.** `0224`'s insert policy admits only
a row naming `app.principal_id`, and the unique key means a second press finds the first person's
row and writes nothing.

Task ids: M27.15.45
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.tables.budget import SUBJECT_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: Wide enough for the longest kind, with room.
KIND_CHARS: Final = 16


class AlertKind(enum.StrEnum):
    """What sort of alert was acknowledged. One today: a degraded or down source."""

    INCIDENT = "incident"


class AlertAcknowledgementRow(Base):
    """One alert instance, acknowledged by one person at one instant."""

    __tablename__ = "alert_acknowledgement"
    __table_args__ = (
        CheckConstraint(one_of("kind", AlertKind), name="kind"),
        CheckConstraint("length(btrim(subject)) > 0", name="subject_present"),
        CheckConstraint("length(btrim(acknowledged_by)) > 0", name="a_person_acknowledged"),
        UniqueConstraint("kind", "subject", "since", name="uq_alert_one_acknowledgement"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(String(KIND_CHARS), nullable=False)
    subject: Mapped[str] = mapped_column(String(SUBJECT_CHARS), nullable=False)
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
