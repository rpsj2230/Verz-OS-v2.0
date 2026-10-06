"""`mem.signal`: what was noticed about an answer, naming it and never quoting it.

`migrations/versions/0197_signal_log.py` builds it and holds the argument for its policies;
`brain.ops.signal_store` writes and reads it. What is here is the model that mirrors the
migration, and the reason each column has the type it has.

**No column could hold a sentence.** A signal is a kind from `brain.memory.signals.Signal`'s
closed vocabulary, two UUIDs naming a conversation and a message, a trace id held to the ledger's
grammar, a principal and an instant. The obvious design has a `question` column, because learning
wants to read it later, and that is
`brain.memory.signals.A_SIGNAL_LOG_MUST_NOT_BECOME_A_SECOND_TRANSCRIPT`: a second copy of what
somebody asked, under this table's permissions rather than the conversation's. **Typing the
references as UUIDs is the structural half of that rule**, because a UUID column refuses words
where a text column named `message_id` would accept them the first time somebody was in a hurry.

**One piece of evidence per kind per answer** (`ONE_ANSWER_IS_ONE_PIECE_OF_EVIDENCE_PER_KIND`).
The unique key is the kind and the message, so a person pressing "wrong" twice on one answer, or a
re-ask detected twice by a retried request, is one corrected answer and one re-asked answer. The
alternative, a row per event, lets one person's repeated clicks weigh as several people's
judgement, which is the per-person weighting `brain.memory.signals.counts_by` refuses from the
other side.

Task ids: M16.2.8
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import TRACE_ID
from brain.db import Base
from brain.memory.signals import Signal
from brain.tables.audit import TRACE_ID_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: The widest signal kind, with room. `contradicted` is twelve characters.
SIGNAL_CHARS: Final = 16

#: Why a second signal of one kind about one answer is not a second row.
ONE_ANSWER_IS_ONE_PIECE_OF_EVIDENCE_PER_KIND: Final = (
    "A signal is evidence about an answer, so one answer corrected twice is one corrected answer "
    "and one answer re-asked twice is one re-asked answer. A row per event would let one "
    "person's repeated clicks, or a retried request, weigh as several people's judgement."
)

#: The closed vocabulary, generated from the enum so the two cannot drift.
SIGNAL_IN: Final = one_of("signal", (one.value for one in Signal))

#: The trace grammar the ledger keeps, or no trace at all.
TRACE_SHAPE: Final = f"trace_id IS NULL OR trace_id ~ '{TRACE_ID}'"


def _present(column: str) -> str:
    return f"length(btrim({column})) > 0"


class SignalRow(Base):
    """`mem.signal`. One thing noticed about one answer, naming it and never quoting it."""

    __tablename__ = "signal"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    signal: Mapped[str] = mapped_column(String(SIGNAL_CHARS), nullable=False)
    #: Which conversation: the permission boundary for reading what was actually said.
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    #: Which answer the signal is about.
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    #: The request on which it was noticed, or None where it was noticed on none.
    trace_id: Mapped[str | None] = mapped_column(String(TRACE_ID_CHARS), nullable=True)
    #: Who it happened for. On the row, and never grouped by.
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(SIGNAL_IN, name="signal_kind"),
        CheckConstraint(TRACE_SHAPE, name="trace_shape"),
        CheckConstraint(_present("principal_id"), name="principal_present"),
        UniqueConstraint("signal", "message_id"),
        Index("ix_mem_signal_at", "at"),
        Index("ix_mem_signal_principal_id_at", "principal_id", "at"),
        {"schema": "mem"},
    )
