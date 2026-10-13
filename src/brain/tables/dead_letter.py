"""`ops.dead_letter`: a job the recovery sweep set aside for a person (M17.1.5, M17.1.1).

`brain.ops.recovery_run` decides, every minute, which orphaned jobs are put back on their queue and
which are set aside, and until `0228` the second kind was a line in a run's report and a failed row
in the driver's own tables, which the application is refused. This is the row the console reads
instead: **the job's id, task, traffic class, why it was set aside, how many times it was
re-driven and when**, and nothing the job carried.

**No arguments and no failure text**, for `brain.ops.jobs.DeadLetter`'s reason: a copy of somebody's
data with a different retention. **The principal is the system's** unless the driver row names one,
because a queued job carries references and never a reach, and an owner invented for it would put
it in front of the wrong person under the own-job rule.

**Written once, by the worker's queue connection, and read by the application.** The key is the
job id, so a second sweep over the same job writes nothing.

Task ids: M17.1.5, M17.1.1
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.gate.context import TrafficClass
from brain.ops.jobs import DeadLetterReason
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: The driver's job id as text: an integer today, and wide enough for a bigint.
JOB_ID_CHARS: Final = 32

#: A task name, which `brain.ops.queue` bounds well inside this.
TASK_CHARS: Final = 200

#: Wide enough for the longest traffic class and reason word, with room.
VOCABULARY_CHARS: Final = 32

#: The principal a job with none is recorded under.
SYSTEM_PRINCIPAL: Final = "system"


class DeadLetterRow(Base):
    """One job set aside for a person. See the module docstring."""

    __tablename__ = "dead_letter"
    __table_args__ = (
        CheckConstraint(
            one_of("traffic_class", [one.value for one in TrafficClass]), name="traffic_class"
        ),
        CheckConstraint(one_of("reason", [one.value for one in DeadLetterReason]), name="reason"),
        CheckConstraint("length(btrim(job_id)) > 0", name="job_present"),
        CheckConstraint("length(btrim(task)) > 0", name="task_present"),
        CheckConstraint("length(btrim(principal_id)) > 0", name="principal_present"),
        CheckConstraint("attempts >= 0", name="attempts_not_negative"),
        Index("ix_ops_dead_letter_set_aside_at", "set_aside_at"),
        {"schema": "ops"},
    )

    job_id: Mapped[str] = mapped_column(String(JOB_ID_CHARS), primary_key=True)
    task: Mapped[str] = mapped_column(String(TASK_CHARS), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    traffic_class: Mapped[str] = mapped_column(String(VOCABULARY_CHARS), nullable=False)
    reason: Mapped[str] = mapped_column(String(VOCABULARY_CHARS), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    set_aside_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
