"""An access review's decisions: one row per decision about one grant, never edited or retired.

`brain.console.govern` decides who may keep or remove a grant in a review round, and
`migrations/versions/0052_review_decision.py` holds the argument for this shape: why a decision is
its own row rather than a column on the grant, why it names exactly one of a direct grant and a pack
assignment, why nobody may decide their own, and why the table is named for the review rather than
for grants. What is here is the model that mirrors it.

**No `deleted_at`, and no `SoftDeleteMixin`.** A decision is a fact about a moment. A second
decision about the same grant is a second row, and the newest is what the Access review screen
reads; retiring the first would be editing the record of who decided what.

**No foreign key to `auth.principal` on `principal_id` or `decided_by`.** Both are values, for the
reason `brain.tables.automation` gives about an owner: a key into the principal table would make
retiring a person delete, or refuse to delete, the record of who reviewed their access.

Task ids: M27.7.9
"""

from __future__ import annotations

import enum
import uuid
from typing import Final

from sqlalchemy import CheckConstraint, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base, TimestampMixin
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: Wide enough for the longer of the two words and no wider.
DECISION_CHARS: Final = 8


class ReviewDecision(enum.StrEnum):
    """What a review can conclude about one grant. `brain.console.govern.Decision`'s two words.

    Restated rather than imported, because this package sits underneath the console and a table
    importing a console module would turn the dependency upside down.
    `tests/unit/test_review_store.py` holds the two enums equal, so neither can gain a third
    member alone.
    """

    KEEP = "keep"
    REMOVE = "remove"


class ReviewDecisionRow(TimestampMixin, Base):
    """`gate.review_decision`. One decision about one grant, by somebody other than its holder."""

    __tablename__ = "review_decision"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: The direct grant decided, or None when the decision was about a pack assignment.
    grant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("gate.capability_grant.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    #: The pack assignment decided, or None when the decision was about a direct grant.
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("gate.capability_pack_assignment.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    #: Whose grant it is. A value; see the module docstring.
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    decision: Mapped[str] = mapped_column(String(DECISION_CHARS), nullable=False)
    #: Who decided. The audit entry's actor, read off this column by the trigger.
    decided_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)

    __table_args__ = (
        CheckConstraint(one_of("decision", ReviewDecision), name="decision"),
        CheckConstraint("(grant_id IS NULL) <> (assignment_id IS NULL)", name="one_row_is_decided"),
        CheckConstraint("length(btrim(decided_by)) > 0", name="decided_by_present"),
        CheckConstraint("decided_by <> principal_id", name="not_decided_by_its_subject"),
        {"schema": "gate"},
    )
