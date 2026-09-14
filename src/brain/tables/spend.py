"""What runs actually cost, as rows, and when the report built over them was last rebuilt.

`brain.ops.spend.Actual` has been the accounting row since M21.2.3 and nothing has held one:
`brain.console.spend_view` and `brain.console.usage_view` are written over sequences a caller
hands them, and no caller had anywhere to read them from. This is the table, and it mirrors
`Actual` field for field and adds nothing to it.

**Nothing is added, and the absence is the design that was already made.** `Actual` carries
no question, no answer and no record identifier, because a cost ledger holding them is a
second copy of the business activity with its own retention; see
`brain.console.spend_view.A_COST_LEDGER_HAS_NO_QUESTION_IN_IT`. A column for a question shape
would be that decision taken again by whoever wrote a migration, so there is no such column,
and M21.3.4's question shapes stay unanswered until somebody decides what shape the ledger may
carry.

**Machine is not a column.** `Actual.machine` is derived from the principal's kind and the
traffic class through `brain.ops.limits.is_automated`, and the two inputs are stored rather
than the answer. A stored boolean would be a second copy of that lookup frozen at write time,
and the materialised report groups on the two inputs for the same reason, so the one
implementation stays in Python.

**`ops.report_refresh` is how a report says how old it is.** A materialised view holds no
record of when it was built, so a screen read over one cannot tell a reader whether its
figures are from a minute ago or from last month. One row per view, written by the refresh
function in the transaction that rebuilds the view, so the timestamp and the contents cannot
disagree about which refresh they came from. See
`brain.console.spend_report_view.STALENESS_IS_A_FIGURE_ON_THE_REPORT_AND_NEVER_A_CAPTION`.

Task ids: M36.1.3.1, M36.1.3.2
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.db import Base
from brain.gate.context import TrafficClass
from brain.tables.identity import one_of

#: A principal identifier, at the width `auth.principal` gives one.
PRINCIPAL_ID_CHARS: Final = 128

#: A department slug, an agent identifier or a model name. The widest of the three with room.
NAME_CHARS: Final = 120

#: The views whose refreshes are recorded. Closed, so a timestamp cannot be written for a view
#: that does not exist and read by a screen as the age of one that does.
REFRESHED_VIEWS: Final[tuple[str, ...]] = ("ops.spend_daily",)


class SpendActualRow(Base):
    """`ops.spend_actual`. One completed run and what it actually cost (M21.2.3's `Actual`).

    Appended at the point a run completes, where the department is already known. There is no
    update: a cost that was wrong is a correction to the estimator, which `brain.ops.retune`
    owns, and not an edit to what was paid.
    """

    __tablename__ = "spend_actual"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    principal_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    traffic: Mapped[str] = mapped_column(String(24), nullable=False)
    department: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    #: Null for a run no agent took part in. Reported under `brain.ops.spend.NO_AGENT`.
    agent_id: Mapped[str | None] = mapped_column(String(NAME_CHARS), nullable=True)
    model: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    lane: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Whole minor units. See `brain.ops.budgets.MONEY_IS_COUNTED_IN_MINOR_UNITS`.
    cost_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: When the run completed. The report's day is taken from this, in UTC.
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(one_of("principal_kind", PrincipalKind), name="principal_kind"),
        CheckConstraint(one_of("traffic", TrafficClass), name="traffic"),
        CheckConstraint(one_of("lane", Lane), name="lane"),
        CheckConstraint("length(btrim(principal_id)) >= 1", name="principal_present"),
        CheckConstraint("length(btrim(department)) >= 1", name="department_present"),
        CheckConstraint("length(btrim(model)) >= 1", name="model_present"),
        CheckConstraint("cost_minor >= 0", name="cost_is_not_negative"),
        Index("ix_spend_actual_at", "at"),
        {"schema": "ops"},
    )


class ReportRefreshRow(Base):
    """`ops.report_refresh`. When one materialised report was last rebuilt (M36.1.3.2).

    Written only by the refresh function, which runs as the view's owner; the application role
    may read it and nothing else. A row the application could write is a staleness figure the
    application could make up.
    """

    __tablename__ = "report_refresh"

    view_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: The instant the rebuild's snapshot was taken, which is what its figures are as of.
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(one_of("view_name", REFRESHED_VIEWS), name="view_name"),
        {"schema": "ops"},
    )
