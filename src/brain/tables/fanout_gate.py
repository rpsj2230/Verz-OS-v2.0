"""`ops.fanout_gate`: what the fan-out gate was given, evaluated and decided for one plan (M18.2.4).

The row behind `brain.ops.fanout_gate_store`. `0240` builds it. A run's plan is weighed by six
arithmetic conditions before any child starts, and the verdict is one of two words
(`brain.orchestration.fanout.Verdict`). Until this table the record
(`brain.orchestration.fanout.GateRecord`) existed as a value and nothing kept it, so "why did this
run split" had no answer after the process ended.

**Numbers and a verdict, and nothing that could be a question.** The columns are the five inputs
the conditions are evaluated over, the conditions that were evaluated and the ones that failed,
and the verdict. There is no objective, no subtask name, no asker and no text: the same boundary
`brain.orchestration.fanout.A_GATE_RECORD_IS_NUMBERS_AND_NEVER_A_QUESTION` draws for the value.
`decided_by` is the administrator who asked for the rehearsal and is an actor, not an owner.

**The database holds the one rule a record exists to keep.** A `parallel` verdict is a record that
evaluated all six conditions and failed none, which `GateRecord`'s constructor refuses to build
otherwise. The check constraint says the same in the table, so a row written by another route
cannot say `parallel` for a plan that failed a condition.

**Written once, in the session's own name, never edited.** `0240`'s insert policy admits only a row
whose `decided_by` is the session's principal, and no UPDATE or DELETE is granted.

Task ids: M18.2.4
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Double,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.orchestration.fanout import CONDITION_ORDER, HOW_MANY_CONDITIONS, Verdict
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: Wide enough for the longest condition name, with room.
CONDITION_CHARS: Final = 40

#: A run's name as the gate records it. A rehearsal's id is one the route generates.
RUN_ID_CHARS: Final = 128


class FanoutGateRow(Base):
    """One decision of the fan-out gate: six conditions, which failed, and what followed."""

    __tablename__ = "fanout_gate"
    __table_args__ = (
        CheckConstraint(one_of("verdict", Verdict), name="verdict"),
        CheckConstraint("length(btrim(run_id)) > 0", name="run_present"),
        CheckConstraint("length(btrim(decided_by)) > 0", name="an_actor_decided"),
        CheckConstraint("branches >= 0 AND depth >= 0", name="counts_not_negative"),
        CheckConstraint("failed <@ evaluated", name="failed_were_evaluated"),
        # The rule `GateRecord` holds in its constructor, held by the table: parallel means all six
        # were evaluated and none failed.
        CheckConstraint(
            f"verdict <> 'parallel' OR (cardinality(failed) = 0 AND "
            f"cardinality(evaluated) = {HOW_MANY_CONDITIONS})",
            name="parallel_only_after_all_six",
        ),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_id: Mapped[str] = mapped_column(String(RUN_ID_CHARS), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    branches: Mapped[int] = mapped_column(Integer, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_multiplier: Mapped[float] = mapped_column(Double, nullable=False)
    speedup: Mapped[float] = mapped_column(Double, nullable=False)
    largest_share: Mapped[float] = mapped_column(Double, nullable=False)
    evaluated: Mapped[list[str]] = mapped_column(ARRAY(String(CONDITION_CHARS)), nullable=False)
    failed: Mapped[list[str]] = mapped_column(ARRAY(String(CONDITION_CHARS)), nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )


#: The conditions as the gate evaluates them, in order, for the constraint's reader.
CONDITIONS_IN_ORDER: Final[tuple[str, ...]] = tuple(one.value for one in CONDITION_ORDER)
