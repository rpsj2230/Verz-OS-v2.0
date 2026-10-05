"""A mark a person puts on an answer, and a pause somebody puts on what an agent's runs teach.

Two rows the learning loop was missing. `brain.ops.learning_signal_store` writes both; migration
`0154` builds them.

**A mark is a pointer and one bit** (M16.6.4). It names the answer by the trace it ran under, says
whether it helped, and says who marked it and when. There is no column for a reason, a correction
or a word of the answer, for `brain.ops.feedback.A_FREE_TEXT_NOTE_IS_WHERE_THE_ANSWER_GETS_PASTED`'s
reason, and none for what the answer drew on: reading that means going back to the trace, where
the trace's own permissions apply.

**A mark is counted and changes nothing by itself** (M16.7.4). No reader of retrieval, memory,
rules, knowledge or an agent's settings reads this table; `tests/unit/test_learning_signal.py`
holds that nothing under `brain.gate`, `brain.memory` or `brain.knowledge` imports it. So a later
answer is retrieved exactly as it would have been with no mark, which is the owner's rule that a
thumbs up or down is counted and what changes behaviour is a reviewed correction.

**A pause is a row, and the latest row for an agent is where it stands** (M16.7.13). Nothing is
updated: pausing and resuming are two rows with who and why, so "who stopped this agent learning,
and was it resumed" has its whole history. A pause only stops memories forming from the agent's
runs, which is the one thing learning does automatically, so it can narrow what is learned and
never widen it.

**Both are SELECT and INSERT only, and written in the session's own name**, `0149`'s shape, and
**stamped with the statement's own instant**, so the latest of two rows written in one transaction
is the one written second.

Task ids: M16.6.4, M16.7.4, M16.7.13
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.agents.model import AGENT_ID_CHARS
from brain.db import Base
from brain.tables.identity import PRINCIPAL_ID_CHARS

#: How wide a trace id is, which is `brain.tables.audit.TRACE_ID_CHARS`.
TRACE_ID_CHARS: Final = 64

#: The longest reason a pause or a resume may give.
REASON_CHARS: Final = 400


def _present(column: str) -> str:
    return f"length(btrim({column})) > 0"


class MarkRow(Base):
    """`mem.mark`. One person's helpful or unhelpful mark on one answer of theirs."""

    __tablename__ = "mark"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: The trace the answer ran under: a pointer, and the only way back to what was answered.
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    #: Who marked it, which is who asked: a person marks their own answers and nobody else's.
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    marked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.statement_timestamp(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(_present("trace_id"), name="trace_present"),
        CheckConstraint(_present("principal_id"), name="principal_present"),
        Index("ix_mem_mark_trace_id", "trace_id"),
        {"schema": "mem"},
    )


class LearningPauseRow(Base):
    """`agent.learning_pause`. One pause or resume of what one agent's runs may teach."""

    __tablename__ = "learning_pause"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    #: True for a pause, false for a resume.
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)
    set_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.statement_timestamp(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(_present("agent_id"), name="agent_present"),
        CheckConstraint(_present("reason"), name="reason_present"),
        CheckConstraint(_present("set_by"), name="set_by_present"),
        Index("ix_agent_learning_pause_agent_id_at", "agent_id", "at"),
        {"schema": "agent"},
    )
