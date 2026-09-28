"""What a stored document's lifecycle keeps: the tasks it opens for people, and captured solutions.

`0120_knowledge_lifecycle` argues both tables, their policies and the triggers that write them;
this is the model half, held to the migration by `tests/unit/test_knowledge_lifecycle_db.py`,
which compares every constraint, index and column.

**`know.steward_task` has no writer in the application.** Every task is opened by a trigger in the
transaction that made it true, and the application role may read and close its own and nothing
else, so the model carries no default for anything a trigger fills in. Rejected: a task written by
the route that caused it, which leaves the task to be remembered by every route and forgotten by
the one written next.

**`know.solution` holds the capturer's words until a named person decides them.** The problem and
the answer are text, bounded, and read under a policy of three branches; the approved solution's
document is `item_id`, which is the solution's own id, so the two rows name each other without a
foreign key between two writers.

Task ids: M7.4.6, M7.6.2, M7.7.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base, TimestampMixin
from brain.knowledge.lifecycle import Outcome, TaskKind
from brain.knowledge.search import DEPARTMENT_CHARS, REFERENCE_SQL_PATTERN, SLUG_SQL_PATTERN
from brain.knowledge.solutions import ANSWER_CHARS, PROBLEM_CHARS, SolutionState
from brain.tables.identity import one_of

#: The widest task kind and outcome, and room for a kind the owner adds.
TASK_KIND_CHARS: Final = 24
OUTCOME_CHARS: Final = 16

#: Identifiers on these rows: an item, a person, a solution. The reference grammar's width.
REFERENCE_CHARS: Final = 128


class StewardTaskRow(TimestampMixin, Base):
    """`know.steward_task`. One thing one person is asked about one document or solution."""

    __tablename__ = "steward_task"

    task_id: Mapped[str] = mapped_column(String(REFERENCE_CHARS), primary_key=True)
    #: Who is asked. The policy admits this person's own rows and nobody else's.
    principal_id: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    kind: Mapped[str] = mapped_column(String(TASK_KIND_CHARS), nullable=False)
    #: The document, or for a solution's task the solution, whose id its document shares.
    item_id: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    #: Who did the thing the task reports. None for a review, which nobody did.
    actor_id: Mapped[str | None] = mapped_column(String(REFERENCE_CHARS), nullable=True)
    #: The review date a review task fell due on.
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(OUTCOME_CHARS), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"task_id ~ '{REFERENCE_SQL_PATTERN}'", name="task_id_is_a_reference"),
        CheckConstraint(f"item_id ~ '{REFERENCE_SQL_PATTERN}'", name="item_id_is_a_reference"),
        CheckConstraint("length(btrim(principal_id)) > 0", name="addressed"),
        CheckConstraint(one_of("kind", TaskKind), name="kind"),
        CheckConstraint(f"outcome IS NULL OR {one_of('outcome', Outcome)}", name="outcome"),
        CheckConstraint("kind <> 'reverify' OR due_at IS NOT NULL", name="a_review_names_its_date"),
        CheckConstraint(
            "(outcome IS NOT NULL) = (kind IN ('promotion_decided', 'solution_decided'))",
            name="a_decision_says_how_it_went",
        ),
        Index("ix_steward_task_open", "principal_id", postgresql_where=text("done_at IS NULL")),
        Index("ix_steward_task_item_id", "item_id"),
        {"schema": "know"},
    )


class SolutionRow(TimestampMixin, Base):
    """`know.solution`. A captured solution, and who decided it and when."""

    __tablename__ = "solution"

    solution_id: Mapped[str] = mapped_column(String(REFERENCE_CHARS), primary_key=True)
    department: Mapped[str] = mapped_column(String(DEPARTMENT_CHARS), nullable=False)
    #: What it solved, in the capturer's words.
    problem: Mapped[str] = mapped_column(String(PROBLEM_CHARS), nullable=False)
    #: The solution itself, in the capturer's words.
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    #: The conversation it was captured from, when the capturer named one.
    conversation_ref: Mapped[str | None] = mapped_column(String(REFERENCE_CHARS), nullable=True)
    captured_by: Mapped[str] = mapped_column(String(REFERENCE_CHARS), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(REFERENCE_CHARS), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: The document an approved solution became. Its id is the solution's.
    item_id: Mapped[str | None] = mapped_column(String(REFERENCE_CHARS), nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"solution_id ~ '{REFERENCE_SQL_PATTERN}'", name="solution_id_is_a_reference"
        ),
        CheckConstraint(f"department ~ '{SLUG_SQL_PATTERN}'", name="department_is_a_slug"),
        CheckConstraint("length(btrim(problem)) > 0", name="says_what_it_solved"),
        CheckConstraint(
            f"length(btrim(answer)) > 0 AND length(answer) <= {ANSWER_CHARS}", name="says_how"
        ),
        CheckConstraint(
            f"conversation_ref IS NULL OR conversation_ref ~ '{REFERENCE_SQL_PATTERN}'",
            name="conversation_ref_is_a_reference",
        ),
        CheckConstraint("length(btrim(captured_by)) > 0", name="captured_by_somebody"),
        CheckConstraint(one_of("state", SolutionState), name="state"),
        CheckConstraint(
            "(decided_by IS NULL) = (decided_at IS NULL)",
            name="a_decision_is_a_person_and_a_date",
        ),
        CheckConstraint(
            "(decided_by IS NULL) = (state = 'pending')",
            name="only_a_decided_solution_names_its_decider",
        ),
        CheckConstraint(
            "(item_id IS NOT NULL) = (state = 'approved')",
            name="an_approved_solution_is_a_document",
        ),
        CheckConstraint(
            "decided_by IS NULL OR decided_by <> captured_by", name="decided_by_somebody_else"
        ),
        Index("ix_solution_department_state", "department", "state"),
        {"schema": "know"},
    )
