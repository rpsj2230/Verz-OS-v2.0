"""`ops.agent_run`: one row per agent run, saying how it ended and what it spent (M13.7.2).

`brain.gate.runtime` is the one loop that hands a model tools, and every run of it ends at a
bound, an answer, a refusal or a fault. This is where that is kept: who the run was for, through
which agent, on which lane, its stop reason, and its turns, tool calls, tokens and steering count.

**No question, no argument, no result and no prompt.** What a run read is the trace's, behind the
trace store's own role (`brain.ops.trace_store`), and a run table holding any of it would be a
second copy of the business with a weaker door. A row is counts and names from closed lists.

**Written once, in the session's own name, and never updated.** A run is recorded when it ends, so
there is nothing to update, and `0188`'s insert policy refuses a row naming anybody but
`app.principal_id`. A person reads their own runs; who may read other people's is a console
decision for the screen that shows them, which is a later change and reads through its own policy.

Task ids: M13.7.2
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.agents.model import AGENT_ID_CHARS
from brain.core.lane import Lane
from brain.db import Base
from brain.gate.stop import StopReason
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: How wide a trace id is, which is `brain.tables.audit.TRACE_ID_CHARS`.
TRACE_ID_CHARS: Final = 64

#: Wide enough for the longest member of `Lane` and of `StopReason`, with room.
VOCABULARY_CHARS: Final = 24


class AgentRunRow(Base):
    """`ops.agent_run`. One finished run of one agent for one person."""

    __tablename__ = "agent_run"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    #: Whose run it was: the person the reach belongs to, never the agent.
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    lane: Mapped[str] = mapped_column(String(VOCABULARY_CHARS), nullable=False)
    stop_reason: Mapped[str] = mapped_column(String(VOCABULARY_CHARS), nullable=False)
    turns: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Results whose text read as steering a model. A count and never the text.
    steered: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("length(btrim(trace_id)) > 0", name="trace_present"),
        CheckConstraint("length(btrim(principal_id)) > 0", name="principal_present"),
        CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        CheckConstraint(one_of("lane", Lane), name="lane"),
        CheckConstraint(one_of("stop_reason", StopReason), name="stop_reason"),
        CheckConstraint(
            "turns >= 0 AND tool_calls >= 0 AND tokens >= 0 AND steered >= 0",
            name="counts_not_negative",
        ),
        CheckConstraint("ended_at >= started_at", name="ends_after_it_starts"),
        Index("ix_ops_agent_run_principal_id_started_at", "principal_id", "started_at"),
        Index("ix_ops_agent_run_agent_id_started_at", "agent_id", "started_at"),
        {"schema": "ops"},
    )
