"""Every budget level as rows nobody edits: one row per version of one ceiling.

`brain.ops.budgets` holds the versioning rules and said "the persistence half is unbuilt: there
is no table, no migration and no store". This is the table. `brain.ops.budget_store` reads and
appends, and neither of them decides anything `brain.ops.budgets` already decides.

**One table for all four levels, and not a table per level.** A company ceiling, a department's
share, a person's two allowances and an agent's two ceilings are the same shape in the domain,
`BudgetRow`, and they are compared with each other on every request by `admits` and `tightest`.
Four tables would be four places for the version rule to be written, and the tie-break in
`tightest` reads across levels, so a query answering it would have to union them back together.

**A row is appended and never updated, in the database rather than in a convention.** The
application role is granted SELECT and INSERT and nothing else, row-level security admits no
UPDATE or DELETE, and a statement trigger refuses both for every role including the owner, which
is the arrangement `obs.audit_entry` has and argues for. The whole of `brain.ops.budgets.
A_BUDGET_ROW_IS_SUPERSEDED_NEVER_EDITED` is the question asked after an overspend, "what was the
ceiling at the time", and an UPDATE is exactly the thing that makes it unanswerable.

**So a bad row has to be refused before it lands, because nothing can take it away afterwards.**
A second trigger refuses a version that does not follow the last one for its ceiling by exactly
one, and an effective-from that is not strictly later. That is `BudgetHistory`'s ordering written
in SQL, and it is not a second implementation of it in the sense this repository refuses: the
domain type is the message and the trigger is the seal, the split `brain.tables.template` makes
about its own check constraints. Without it, one disordered insert makes that ceiling's history
refuse to construct for ever, on a table where the remedy of deleting the row does not exist.
See `A_ROW_NOBODY_CAN_REMOVE_IS_REFUSED_BEFORE_IT_LANDS`.

**What the row carries is its own audit.** `author`, `reason` and `effective_from` are the
domain's, and `recorded_at` is the database's clock, which is the one timestamp on the row the
author did not choose. Who set a ceiling, why, from when, and when that was written down are all
answerable from the row, and none of them can be changed.

**What is not here is an entry in `obs.audit_entry`**, and the gap is stated rather than hidden.
`brain.audit.ledger.AuditAction` has no member for a budget change and `SUBJECT_KINDS` no kind for
a budget, and both are closed on purpose. Adding the kind is not a two-line change:
`brain.identity.staff_sync.AUDIT_KIND_DECISIONS` holds, per kind, whether a department head's
audit reach covers it, which is Needs Rupash item 48's decision, and a new kind is a new
question for the same owner. `0004` records the identical gap for `ops.setting`.

Task ids: M21.1.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Double,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.budgets import BudgetLevel, BudgetPeriod
from brain.tables.identity import one_of

#: Why the ordering rule is enforced by a trigger as well as by `BudgetHistory`.
A_ROW_NOBODY_CAN_REMOVE_IS_REFUSED_BEFORE_IT_LANDS: Final = (
    "The table takes no UPDATE and no DELETE from anybody, so a version that skips a number or "
    "takes effect no later than the one before it would be permanent. BudgetHistory refuses "
    "to construct over such a history, which is correct and would make that ceiling "
    "unreadable for ever. So the database refuses the row at insert, where refusing costs a "
    "failed write rather than a budget nobody can load."
)

#: How long a subject may be. A principal id, a department slug, an agent id or a company id.
SUBJECT_CHARS: Final = 128

#: How long a reason may be. A sentence for whoever asks later, never a document.
REASON_CHARS: Final = 2000


class BudgetVersionRow(Base):
    """`ops.budget_version`. One version of one ceiling, at one of the four levels (M21.1.5).

    Mirrors `brain.ops.budgets.BudgetRow` field for field, plus the surrogate id and the database's
    `recorded_at`. The natural key is `(level, subject, period, version)` and it is unique, which is
    also what refuses two writers racing to append the same next version: the trigger's view of
    "the last version" is taken before either commits, so the unique index is the half that holds
    under concurrency.
    """

    __tablename__ = "budget_version"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    subject: Mapped[str] = mapped_column(String(SUBJECT_CHARS), nullable=False)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Whole minor units. See `brain.ops.budgets.MONEY_IS_COUNTED_IN_MINOR_UNITS`.
    ceiling_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    author: Mapped[str] = mapped_column(String(SUBJECT_CHARS), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    #: Fractions of the ceiling at which somebody is told, each strictly between nought and one.
    alert_fractions: Mapped[list[float]] = mapped_column(
        ARRAY(Double), nullable=False, server_default=text("'{}'::double precision[]")
    )
    #: When the database wrote the row. The one timestamp here its author did not choose.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(one_of("level", BudgetLevel), name="level"),
        CheckConstraint(one_of("period", BudgetPeriod), name="period"),
        CheckConstraint("length(btrim(subject)) >= 1", name="subject_present"),
        # A ceiling of nothing is a suspension wearing a budget's clothes; `BudgetRow` says so.
        CheckConstraint("ceiling_minor >= 1", name="ceiling_is_something"),
        CheckConstraint("version >= 1", name="versions_start_at_one"),
        CheckConstraint("length(btrim(author)) >= 1", name="author_present"),
        CheckConstraint(f"length(reason) <= {REASON_CHARS}", name="reason_is_a_sentence"),
        # `ALL` over an empty array is true, so a row with no alerts passes, which is right.
        CheckConstraint(
            "0 < ALL (alert_fractions) AND 1 > ALL (alert_fractions)",
            name="alerts_below_the_ceiling",
        ),
        UniqueConstraint("level", "subject", "period", "version"),
        {"schema": "ops"},
    )
