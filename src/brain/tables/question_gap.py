"""A question no connected source covers, as a row: which department asked, which source, when.

`brain.adoption.Unanswered` has said since M37.3 that a connector roadmap needs which source would
have answered and for whom, and nothing recorded one, because the answer lane could not tell. It
can now: `brain.gate.fast_lane.unserved_match` finds a rule whose question shape matched and whose
source nothing on the install reads, and the lane abstains with that source named for the ledger.
This is the ledger.

**Only that one kind of unanswered question, and the narrowness is the design.** "I could not find
that" is one sentence for a record that does not exist and a record the asker may not see, and
`brain.console.operate.GAP_REASONS` refuses to count it for that reason. A missing source is
decided from the rules and the readers before anything is read, so it is the same for every asker
and every record, and a row here says nothing about anybody's reach or about what exists. See
`A_GAP_IS_DECIDED_FROM_CONFIGURATION_AND_NEVER_FROM_A_READ`.

**No principal, no question text, no entity and no rule.** A department and a source are what a
roadmap is argued with; a person beside them is a list of what each colleague tried to find out,
and the words they typed are a search history. `AN_UNANSWERED_QUESTION_LOG_THAT_KEEPS_THE_QUESTION_
IS_A_SEARCH_HISTORY` in `brain.adoption` is the argument, and this table has nowhere to put either.

**The trace id is the primary key**, for `brain.tables.adoption`'s reason: a question that fanned
out finishes under one trace, and one question is one row.

Task ids: M27.7.18
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.tables.adoption import TRACE_ID_CHARS
from brain.tables.spend import NAME_CHARS

#: Why a row here discloses nothing about a reach or a record.
A_GAP_IS_DECIDED_FROM_CONFIGURATION_AND_NEVER_FROM_A_READ: Final = (
    "A row is written only when the answer lane found a rule whose shape the question matched "
    "and whose source nothing on the install reads. That is decided from the rules and the "
    "readers, before anything is read, so every asker and every record gives the same answer, "
    "and a count of rows is a count of questions the install is not wired to answer rather "
    "than of anything somebody was refused."
)

#: The widest source name a rule carries, which is `brain.gate.fast_lane.FastPathRule.source`'s.
SOURCE_CHARS: Final = 60


class QuestionGapRow(Base):
    """`ops.question_gap`. One question no connected source covers (M27.7.18).

    Appended when the answer lane finishes a question it declined as nothing connected with a
    source named. There is no update and no delete: a source connected later does not unask the
    question.
    """

    __tablename__ = "question_gap"

    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), primary_key=True)
    #: The department the directory gave the asker when they asked.
    department: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    #: The source the matched rule names and nothing here reads.
    source: Mapped[str] = mapped_column(String(SOURCE_CHARS), nullable=False)
    #: When the request was judged. The screen's window is taken from this.
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("length(btrim(trace_id)) >= 1", name="trace_present"),
        CheckConstraint("length(btrim(department)) >= 1", name="department_present"),
        CheckConstraint("length(btrim(source)) >= 1", name="source_present"),
        Index("ix_question_gap_at", "at"),
        {"schema": "ops"},
    )
