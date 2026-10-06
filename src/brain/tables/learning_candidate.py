"""Two tables: what a person said the right answer is, and every correction that said it.

`brain.knowledge.candidates` holds the rules and `0198` the database's half: the policies, the one
write function, the steward's task and the ledger entry. These models are the same two tables as
values, held equal to the migration by `tests/unit/test_tables.py`.

**The words live here and nowhere else.** `brain.chat.turns.Correction` has no field for them and
never will, and no search, recall or prompt reads this table: see
`brain.knowledge.candidates.A_CORRECTION_S_WORDS_CHANGE_NOTHING_UNTIL_SOMEBODY_APPROVES_THEM`.

**The application role holds SELECT and a four-column UPDATE, and no INSERT.** Every row is written
by `know.propose_correction`, which takes the proposer from the session and refuses a conversation
that is not theirs, so the only way in is in the proposer's own name.

Task ids: M16.6.5, M16.6.6, M16.7.6
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base, TimestampMixin
from brain.knowledge.candidates import GROUP_KEY_CHARS, REASON_CHARS, WORDS_CHARS, CandidateState
from brain.knowledge.search import REFERENCE_SQL_PATTERN
from brain.tables.identity import one_of

#: How wide an id, a person and a document are here: `know.item`'s and `know.solution`'s width.
REFERENCE_CHARS: Final = 128


class LearningCandidateRow(TimestampMixin, Base):
    """`know.learning_candidate`. One proposed fix to one document, and how it was decided."""

    __tablename__ = "learning_candidate"

    candidate_id: Mapped[str] = mapped_column(String(REFERENCE_CHARS), primary_key=True)
    #: The document the corrected answer cited, taken from the answer and never typed.
    item_id: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    #: What the first person to propose it said the right answer is, in their words.
    words: Mapped[str] = mapped_column(String(WORDS_CHARS), nullable=False)
    #: The document and the words' key: one pending candidate per fix.
    group_key: Mapped[str] = mapped_column(String(GROUP_KEY_CHARS), nullable=False)
    raised_by: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(REFERENCE_CHARS), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Why a rejected candidate was rejected. Kept, so it is not proposed again for no reason.
    reason: Mapped[str | None] = mapped_column(String(REASON_CHARS), nullable=True)
    #: The new version an approved candidate became. Once, by the table's key.
    applied_item_id: Mapped[str | None] = mapped_column(String(REFERENCE_CHARS), nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"candidate_id ~ '{REFERENCE_SQL_PATTERN}'", name="candidate_id_is_a_reference"
        ),
        CheckConstraint(f"item_id ~ '{REFERENCE_SQL_PATTERN}'", name="item_id_is_a_reference"),
        CheckConstraint("length(btrim(words)) > 0", name="says_what_is_right"),
        CheckConstraint(f"group_key ~ '^[0-9a-f]{{{GROUP_KEY_CHARS}}}$'", name="group_key"),
        CheckConstraint("length(btrim(raised_by)) > 0", name="raised_by_somebody"),
        CheckConstraint(one_of("state", CandidateState), name="state"),
        CheckConstraint(
            "(decided_by IS NULL) = (decided_at IS NULL)",
            name="a_decision_is_a_person_and_a_date",
        ),
        CheckConstraint(
            "(decided_by IS NULL) = (state = 'pending')",
            name="only_a_decided_candidate_names_its_decider",
        ),
        CheckConstraint(
            "(applied_item_id IS NOT NULL) = (state = 'approved')",
            name="an_approved_candidate_is_a_version",
        ),
        CheckConstraint(
            "(reason IS NOT NULL) = (state = 'rejected') "
            "AND (reason IS NULL OR length(btrim(reason)) > 0)",
            name="a_rejection_keeps_its_reason",
        ),
        CheckConstraint(
            "decided_by IS NULL OR decided_by <> raised_by", name="decided_by_somebody_else"
        ),
        UniqueConstraint("applied_item_id", name="applied_once"),
        Index(
            "ix_learning_candidate_one_pending_per_fix",
            "group_key",
            unique=True,
            postgresql_where=sql_text("state = 'pending'"),
        ),
        Index("ix_learning_candidate_item_state", "item_id", "state"),
        {"schema": "know"},
    )


class CandidateEvidenceRow(Base):
    """`know.candidate_evidence`. One correction that proposed or grew a candidate.

    Keyed by the corrected answer itself, so one answer is evidence once and ever.
    """

    __tablename__ = "candidate_evidence"

    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    answer_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        String(REFERENCE_CHARS),
        ForeignKey("know.learning_candidate.candidate_id"),
        nullable=False,
    )
    principal_id: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("length(btrim(principal_id)) > 0", name="evidence_of_somebody"),
        Index("ix_candidate_evidence_candidate_id", "candidate_id"),
        {"schema": "know"},
    )
