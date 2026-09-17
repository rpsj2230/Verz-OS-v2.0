"""What an installed automation did, and every time its schedule changed and why.

`brain.ops.automation_run` decides a run and `migrations/versions/0067_automation_run.py` argues the
policies and the trigger. What is here is the two models that mirror them.

**`agent.automation_run` is one row per slot.** The key is the run id `automation_run.run_id`
derives from the automation and the instant it was due, so a slot written twice is refused by the
key rather than recorded twice, and there is no second way to name one run. Written by the worker
on the database owner's connection and read by the application, so the application role holds
SELECT alone.

**`agent.automation_schedule` is why an automation has the next run it has.** One row per start,
stop and pause, written in the transaction that moves `agent.automation.next_run_at`, and its
trigger is what reaches the ledger. Rejected: a `paused_because` column on `agent.automation`. It
is a second fact beside the next run, which
`brain.console.agent_automations.A_PAUSED_FLAG_BESIDE_A_NEXT_RUN_TIME_IS_TWO_FACTS_THAT_DISAGREE`
refuses, and it would forget the reason for the previous pause the moment it was overwritten.
Rejected too: an update trigger on the automation reading the reason from a transaction setting,
which is a reason nothing validates and a ledger entry for an update nobody meant as a change.

**Both point at the automation by value**, for the reason `brain.tables.agent_automation` gives:
the record of what ran in a person's name outlives anything that would delete the automation.

**No count columns and no failure text.** A run keeps its outcome, a closed reason when it was
refused, the digest of the reach it ran at and, when it succeeded, the task's own lines at that
reach. A failure's message is `brain.ops.jobs.DeadLetter`'s case: somebody's data copied onto an
operational surface with a different retention.

Task ids: M39.6.2.1, M39.6.2.3, M38.2.2.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.ops.automation_owner import AUTOMATION_ID
from brain.tables.agent_automation import AGENT_ID_CHARS, AUTOMATION_ID_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: `brain.ops.automation_run.RunOutcome`, `PausedBecause`, `RUN_ID_PREFIX` and
#: `RUN_ID_DIGEST_CHARS`, restated rather than imported because that module reaches the console
#: and this package sits underneath it; `tests/unit/test_automation_run_store.py` holds them equal.
RUN_OUTCOMES: Final[tuple[str, ...]] = ("succeeded", "failed", "refused")
REFUSED: Final = "refused"
SUCCEEDED: Final = "succeeded"
PAUSE_REASONS: Final[tuple[str, ...]] = (
    "stopped",
    "failed_repeatedly",
    "owner_gone",
    "agent_unavailable",
    "task_unbuilt",
    "owner_lost_reach",
)
RUN_ID_PREFIX: Final = "run_"
RUN_ID_DIGEST_CHARS: Final = 32

#: A run id's shape, from the two constants `automation_run.run_id` builds it with.
RUN_ID_PATTERN: Final = f"^{RUN_ID_PREFIX}[0-9a-f]{{{RUN_ID_DIGEST_CHARS}}}$"
RUN_ID_CHARS: Final = len(RUN_ID_PREFIX) + RUN_ID_DIGEST_CHARS

#: A reason's width. The longest member is well inside it.
REASON_CHARS: Final = 32

#: A reach digest, `EntitlementSet.ent_hash`, which is 32 hex characters.
ENT_HASH_PATTERN: Final = r"^[0-9a-f]{32}$"
ENT_HASH_CHARS: Final = 32

#: The word a start is recorded under. Every other schedule change is a `PausedBecause`.
STARTED: Final = "started"

#: Every reason a schedule row may carry: a start, or why the automation has no next run.
SCHEDULE_REASONS: Final[tuple[str, ...]] = (STARTED, *PAUSE_REASONS)


class AutomationRunRow(Base):
    """`agent.automation_run`. One slot of one automation: as whom, how it ended, what it found."""

    __tablename__ = "automation_run"

    run_id: Mapped[str] = mapped_column(String(RUN_ID_CHARS), primary_key=True)
    automation_id: Mapped[str] = mapped_column(String(AUTOMATION_ID_CHARS), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    #: The principal it ran as. A value, for the module docstring's reason.
    principal_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: The slot: the next run the automation carried when the run was claimed.
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Why it was refused. Null exactly when it was not.
    reason: Mapped[str | None] = mapped_column(String(REASON_CHARS), nullable=True)
    #: The digest of the reach it ran at, null when it was refused before one was computed.
    ent_hash: Mapped[str | None] = mapped_column(String(ENT_HASH_CHARS), nullable=True)
    #: The task's lines at the run's reach. Empty unless it succeeded.
    result: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )

    __table_args__ = (
        CheckConstraint(f"run_id ~ '{RUN_ID_PATTERN}'", name="run_id_shape"),
        CheckConstraint(f"automation_id ~ '{AUTOMATION_ID}'", name="automation_id_shape"),
        CheckConstraint(f"agent_id ~ '{IDENTIFIER}'", name="agent_id_is_an_identifier"),
        CheckConstraint(f"principal_id ~ '{IDENTIFIER}'", name="principal_id_is_an_identifier"),
        CheckConstraint(one_of("outcome", RUN_OUTCOMES), name="outcome"),
        CheckConstraint(
            f"(outcome = '{REFUSED}') = (reason IS NOT NULL)",
            name="a_reason_exactly_when_refused",
        ),
        CheckConstraint(f"reason IS NULL OR {one_of('reason', PAUSE_REASONS)}", name="reason"),
        CheckConstraint(
            f"cardinality(result) = 0 OR outcome = '{SUCCEEDED}'",
            name="a_result_only_from_a_success",
        ),
        CheckConstraint(f"ent_hash IS NULL OR ent_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash"),
        CheckConstraint("finished_at >= started_at", name="finished_after_it_started"),
        Index("ix_automation_run_automation_finished", "automation_id", "finished_at"),
        {"schema": "agent"},
    )


class AutomationScheduleRow(Base):
    """`agent.automation_schedule`. One start, stop or pause of one automation, by whom and why."""

    __tablename__ = "automation_schedule"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    automation_id: Mapped[str] = mapped_column(String(AUTOMATION_ID_CHARS), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    #: The next run the change left, null for a stop or a pause.
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: `STARTED` or a `PausedBecause`.
    reason: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)
    #: Who changed it. The ledger entry's actor, read off this column by the trigger.
    changed_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: The change's own instant.
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"automation_id ~ '{AUTOMATION_ID}'", name="automation_id_shape"),
        CheckConstraint(f"agent_id ~ '{IDENTIFIER}'", name="agent_id_is_an_identifier"),
        CheckConstraint(f"changed_by ~ '{IDENTIFIER}'", name="changed_by_is_an_identifier"),
        CheckConstraint(one_of("reason", SCHEDULE_REASONS), name="reason"),
        CheckConstraint(
            f"(reason = '{STARTED}') = (next_run_at IS NOT NULL)",
            name="a_start_has_a_next_run_and_nothing_else_does",
        ),
        Index("ix_automation_schedule_automation_at", "automation_id", "at"),
        {"schema": "agent"},
    )
