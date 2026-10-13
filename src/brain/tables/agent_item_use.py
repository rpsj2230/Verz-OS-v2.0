"""`ops.agent_item_use`: how many answers of one agent cited one document on one day (M39.2.3.5).

The agent's Knowledge section shows beside each document how often the agent drew on it, and which
documents it never touched, so a person deciding what to prune is not guessing. Nothing recorded
that: `ops.retrieval_event` keeps no document by design, because it is the learning signal's record
and a document reference in it would let a ranking boost formed from one person's reach leak into
the next person's results (`brain.console.agent_tabs.
A_PER_ITEM_COUNT_IS_A_REPORT_AND_NEVER_A_RANKING_INPUT`).

**Read the absences first.** No question, no principal, no reach, no trace, no passage and no text:
the row is an agent, a document, a day and how many answers cited it. A log from which what a
person asked or read could be reconstructed is the thing this refuses to be. Nothing reads these
rows into a ranking; the one reader is `brain.agent_knowledge_routes`, and it asks only for the
documents the reader may already open, so a document the reader cannot see contributes to no figure
they are shown.

**A day, not an instant.** Two answers on one day are one row with a count, so the table grows with
the agent's documents and days rather than with its questions, and a row cannot be matched to a
moment a particular person asked.

**Points at nothing.** The agent and the document are values, so a row outlives a document that is
archived and an agent that is retired, which is what lets a count be read for an old answer. The
erasure store records the table as about nobody.

Task ids: M39.2.3.5
"""

from __future__ import annotations

from datetime import date
from typing import Final

from sqlalchemy import CheckConstraint, Date, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base

#: As `agent.agent.id` and `know.item.item_id` are wide, copied for `0009`'s reason.
AGENT_ID_CHARS: Final = 128
ITEM_ID_CHARS: Final = 128


class AgentItemUseRow(Base):
    """One agent, one document, one day. See the module docstring."""

    __tablename__ = "agent_item_use"

    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(ITEM_ID_CHARS), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    __table_args__ = (
        CheckConstraint("uses >= 1", name="used_at_least_once"),
        CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        CheckConstraint("length(btrim(item_id)) > 0", name="item_present"),
        Index("ix_agent_item_use_day", "agent_id", "day"),
        {"schema": "ops"},
    )
