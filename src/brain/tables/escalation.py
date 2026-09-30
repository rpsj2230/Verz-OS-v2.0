"""`gate.escalation`: one question handed to a person, kept until it is picked up or expires.

`migrations/versions/0168_escalation.py` holds the argument for the table, its policies and why it
appends no ledger entry; what is here is the model that mirrors it.

**The row is the handoff and nothing more.** Who asked, the question in their own words, what was
tried as step names, what the skill's author said is needed, and the trace to quote: exactly
`brain.gate.abstain.Handoff`. There is no column for a passage, a record, a field or the reason the
answer abstained, because the person it is routed to may hold less than the asker, and a refusal and
an absence are one outcome to the asker. See
`brain.gate.escalating.A_HANDOFF_CARRIES_ONLY_WHAT_THE_ASKER_COULD_SEE`.

**No foreign key to `auth.principal`** on either person column, for the reason
`brain.tables.credential` gives: an actor is a value, and the record outlives the person.

Task ids: M8.3.2, M8.3.4
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.gate.abstain import EscalationTrigger
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of
from brain.tables.skill import (
    AGENT_ID_CHARS,
    ESCALATION_NEEDS_CHARS,
    ESCALATION_QUEUE_CHARS,
    ESCALATION_QUEUE_PATTERN,
    NAME_CHARS,
)

#: How wide a trace reference may be.
TRACE_CHARS: Final = 128

#: `brain.gate.caches.MAX_QUESTION_CHARS`, restated because this package sits underneath the gate's
#: callers; `tests/unit/test_escalation_store.py` holds the two equal.
MAX_QUESTION_CHARS: Final = 4000


class EscalationDelivery(enum.StrEnum):
    """How sending the handoff to the named person's channel went.

    The three a channel's vendor can come to (`brain.tables.channel.DeliveryOutcome`), and one
    more for a handoff not sent at all because its notice is switched off.
    """

    SENT = "sent"
    REFUSED = "refused"
    UNKNOWN = "unknown"
    NOT_SENT = "not_sent"


class EscalationRow(Base):
    """`gate.escalation`. One handoff, who it went to, how it was sent and when it expired."""

    __tablename__ = "escalation"

    #: Minted by the application, so the id is known before the row is written.
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    queue: Mapped[str] = mapped_column(String(ESCALATION_QUEUE_CHARS), nullable=False)
    #: The skill whose declaration sent it, and the agent that was asked.
    skill_name: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    asker_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: The asker's own words, which is the only thing that tells a person whether to pick it up.
    question: Mapped[str] = mapped_column(Text, nullable=False)
    #: Step names, never values. See `brain.gate.abstain.Handoff.tried`.
    tried: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    needed: Mapped[str] = mapped_column(String(ESCALATION_NEEDS_CHARS), nullable=False)
    trace_ref: Mapped[str] = mapped_column(String(TRACE_CHARS), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: The person named for the queue when it arrived, or None when nobody was.
    routed_to: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery: Mapped[str | None] = mapped_column(String(16), nullable=True)
    #: Set by the worker's `escalation_expiry` control once `expires_at` has passed.
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(one_of("trigger", EscalationTrigger), name="trigger"),
        CheckConstraint(f"queue ~ '{ESCALATION_QUEUE_PATTERN}'", name="queue_shape"),
        CheckConstraint(f"asker_id ~ '{IDENTIFIER}'", name="asker_id_shape"),
        CheckConstraint(f"routed_to IS NULL OR routed_to ~ '{IDENTIFIER}'", name="routed_to_shape"),
        CheckConstraint(
            f"length(btrim(question)) > 0 AND length(question) <= {MAX_QUESTION_CHARS}",
            name="question_present",
        ),
        CheckConstraint("jsonb_typeof(tried) = 'array'", name="tried_is_a_list"),
        CheckConstraint("length(btrim(needed)) > 0", name="needed_present"),
        CheckConstraint("expires_at > raised_at", name="expires_after_it_is_raised"),
        CheckConstraint(
            f"delivery IS NULL OR {one_of('delivery', EscalationDelivery)}", name="delivery"
        ),
        CheckConstraint(
            "(delivered_at IS NULL) = (delivery IS NULL)", name="a_delivery_says_how_it_went"
        ),
        CheckConstraint(
            "expired_at IS NULL OR expired_at >= expires_at", name="expired_once_it_was_due"
        ),
        Index("ix_escalation_asker", "asker_id", "raised_at"),
        Index("ix_escalation_routed_to", "routed_to", "raised_at"),
        Index("ix_escalation_open", "expires_at", postgresql_where=text("expired_at IS NULL")),
        {"schema": "gate"},
    )
