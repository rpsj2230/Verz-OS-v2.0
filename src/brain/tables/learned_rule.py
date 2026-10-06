"""Two tables: the rule a tier-two learning proposes, and every conversation it would have answered.

`brain.memory.promotion` holds the rules and `0206` the database's half: the policies, the checks
that refuse a promotion by its proposer or a two-person promotion by one person, and the ledger
entry. These models are the same two tables as values, held equal to the migration by
`tests/unit/test_tables.py`.

**A held rule answers nothing.** `gate.fast_path_rule` holds rules that answer; a learned rule is
copied there only when it is promoted, so nothing that reads the live rules reads this table, and
the shadow match that counts occurrences reads it only to count.

**An occurrence names no person.** A learning, a conversation and a day, for
`brain.memory.tiers.Occurrence`'s reason; the insert policy admits only the asker's own
conversation.

Task ids: M39.4.2.3
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Final

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from brain.core.fast_path import MAX_TEMPLATE_CHARS
from brain.db import Base, TimestampMixin
from brain.tables.fast_lane import NAME_CHARS
from brain.tables.learning import MEMORY_ID_CHARS

#: How wide a person is here, and a rule id a promotion writes (`<department>__<name>`).
PRINCIPAL_CHARS: Final = 128
RULE_ID_CHARS: Final = 128


class LearnedRuleRow(TimestampMixin, Base):
    """`mem.learned_rule`. One proposed fast-lane rule, held until it is promoted."""

    __tablename__ = "learned_rule"

    memory_id: Mapped[str] = mapped_column(
        String(MEMORY_ID_CHARS), ForeignKey("mem.learning.memory_id"), primary_key=True
    )
    #: The id the rule takes in `gate.fast_path_rule` once promoted.
    rule_id: Mapped[str] = mapped_column(String(RULE_ID_CHARS), nullable=False)
    template: Mapped[str] = mapped_column(String(MAX_TEMPLATE_CHARS), nullable=False)
    slot: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    source: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    entity: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    match_field: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    answer_field: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    #: The department whose askers it would answer, or None for the whole install.
    department: Mapped[str | None] = mapped_column(String(NAME_CHARS), nullable=True)
    #: The person who proposed it, or None when the system did. Never promotes it.
    proposed_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_CHARS), nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Decided at the first press and kept, so the second press is judged by the same rule.
    needs_two: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    first_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_CHARS), nullable=True)
    first_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_CHARS), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_learned_rule_department", "department"),
        {"schema": "mem"},
    )


class RuleOccurrenceRow(Base):
    """`mem.rule_occurrence`. A question a held rule would have answered: which, where and when."""

    __tablename__ = "rule_occurrence"

    memory_id: Mapped[str] = mapped_column(
        String(MEMORY_ID_CHARS), ForeignKey("mem.learned_rule.memory_id"), primary_key=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    on_day: Mapped[date] = mapped_column(Date, primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sql_text("now()")
    )

    __table_args__ = ({"schema": "mem"},)
