"""`ops.budget_stop`: every budget that was used up, and whether the install stopped it (M27.12.5).

`brain.ops.budget_stop` decides what follows a budget being used up: a warning to whoever can
raise it, then a stop until the next period. `brain.ops.budget_stop_store` records both here, and
the request path reads the stops in force before a question costs anything.

**`enforced` is the switch's answer at the moment the budget ran out.** While
`budget_enforcement` is off, a used-up budget opens a row with `enforced` false: the install would
have stopped it and did not. That row is the evidence the owner decides the switch on, which is
why it is kept rather than logged, and why it is shown only to a reader of the Spend screen.

**The ceiling's key, the period's two ends, ids and nothing a request said.** Who the warning was
addressed to is a list of principal ids, empty exactly when nobody could be addressed, which the
constraint `addressed_to_somebody_or_said_to_nobody` holds to `addressing`. The principal and trace
are the request that found the budget used up. No figure is kept: how much was spent is the spend
ledger's.

**Written once, in the session's own name, and never updated.** A stop ends when its period
does, so nothing has to change a row, and `0211`'s insert policy refuses one naming anybody but
`app.principal_id`.

Task ids: M27.12.5, M27.7.15
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.budget_stop import WINDOWS, Addressing
from brain.ops.budgets import BudgetLevel
from brain.tables.budget import SUBJECT_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: How wide a trace id is, which is `brain.tables.audit.TRACE_ID_CHARS`.
TRACE_ID_CHARS: Final = 64

#: Wide enough for the longest level, period and addressing word, with room.
VOCABULARY_CHARS: Final = 16


class BudgetStopRow(Base):
    """One used-up budget's period, stopped or only said. See the module docstring."""

    __tablename__ = "budget_stop"
    __table_args__ = (
        CheckConstraint(one_of("level", [one.value for one in BudgetLevel]), name="level"),
        CheckConstraint(one_of("period", [one.value for one in WINDOWS]), name="period"),
        CheckConstraint(one_of("addressing", [one.value for one in Addressing]), name="addressing"),
        CheckConstraint("length(btrim(subject)) > 0", name="subject_present"),
        CheckConstraint("length(btrim(principal_id)) > 0", name="principal_present"),
        CheckConstraint("length(btrim(trace_id)) > 0", name="trace_present"),
        CheckConstraint("until > since", name="ends_after_it_starts"),
        CheckConstraint(
            "(addressing = 'unaddressed') = (cardinality(addressed_to) = 0)",
            name="addressed_to_somebody_or_said_to_nobody",
        ),
        UniqueConstraint(
            "level",
            "subject",
            "period",
            "until",
            "enforced",
            name="uq_budget_stop_one_stop_per_period",
        ),
        Index("ix_ops_budget_stop_until", "until"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    level: Mapped[str] = mapped_column(String(VOCABULARY_CHARS), nullable=False)
    subject: Mapped[str] = mapped_column(String(SUBJECT_CHARS), nullable=False)
    period: Mapped[str] = mapped_column(String(VOCABULARY_CHARS), nullable=False)
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    enforced: Mapped[bool] = mapped_column(Boolean, nullable=False)
    addressing: Mapped[str] = mapped_column(String(VOCABULARY_CHARS), nullable=False)
    addressed_to: Mapped[list[str]] = mapped_column(
        ARRAY(String(PRINCIPAL_ID_CHARS)), nullable=False, server_default=text("'{}'")
    )
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(TRACE_ID_CHARS), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
