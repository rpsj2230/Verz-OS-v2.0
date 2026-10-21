"""Four tables: a workflow's versions, who it is assigned to, and how each run went (M17.6.1).

`0273` builds them. `brain.orchestration.workflow` reads a definition and
`brain.orchestration.workflow_run` runs one; these keep what a person must be able to follow
afterwards.

**A definition is never edited.** `ops.workflow_version` is insert-only: saving a workflow writes
the next version, a run names the version it ran, and the version a run used is therefore still
there to read when the workflow has moved on. The definition column holds exactly what
`read_definition` admitted and the writer re-reads it on the way in; the table checks it is an
object and nothing more, because a constraint that parsed a definition would be a second reader.

**An assignment is a link, and its row stays.** `agent.workflow_assignment` says an agent may run a
workflow (M17.7.7) and, like `agent.agent_callee`, is configuration and not reach: the steps a run
makes are judged by the gate at the run's reach whoever assigned what. Withdrawn by two columns
written once, so what an agent was assigned on the day a run happened can be read back.

**A run is statuses and words from closed lists, and never a value.** `ops.workflow_run` names the
workflow, its version, the agent and who started it, how it ended and the first step that failed.
`ops.workflow_step_run` has a row per step with a status, a cause from `Cause` and, for a skipped
step, the condition in the definition's own words. There is no column an output value, an argument
or a record could be written to. See
`brain.orchestration.workflow_run.A_TRACE_HOLDS_STATUSES_AND_NEVER_VALUES`.

**Insert-only, in the session's own name.** The insert policies admit a row whose writer is the
session's principal, and no UPDATE or DELETE is granted on the three that are history.

Task ids: M17.6.1, M17.6.8, M17.7.7
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Double,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.agents.model import AGENT_ID_CHARS
from brain.db import Base
from brain.orchestration.workflow_run import Cause, Outcome, Status
from brain.tables.fanout_gate import RUN_ID_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: A workflow's slug, as an agent's is. Short enough to be said aloud.
WORKFLOW_ID_CHARS: Final = 60
#: A step's id, held equal to `brain.orchestration.workflow.STEP_ID_RE`'s longest.
STEP_ID_CHARS: Final = 32
#: The widest a stored condition may be: the definition's own words, bounded.
DETAIL_CHARS: Final = 200
NAME_CHARS: Final = 120

#: The slug grammar, escaped for a check constraint (see `brain.tables.agent` for why).
WORKFLOW_ID_GRAMMAR: Final = "workflow_id ~ '^[a-z][a-z0-9_-]{1,59}$'"


def _present(column: str) -> str:
    return f"length(btrim({column})) > 0"


class WorkflowVersionRow(Base):
    """`ops.workflow_version`. One saved version of one workflow. Never edited."""

    __tablename__ = "workflow_version"
    __table_args__ = (
        CheckConstraint(WORKFLOW_ID_GRAMMAR, name="workflow_id_grammar"),
        CheckConstraint("version >= 1", name="version_is_positive"),
        CheckConstraint(_present("name"), name="name_present"),
        CheckConstraint(_present("saved_by"), name="saved_by_present"),
        CheckConstraint("jsonb_typeof(definition) = 'object'", name="definition_is_an_object"),
        UniqueConstraint("workflow_id", "version", name="uq_workflow_version_one_per_number"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workflow_id: Mapped[str] = mapped_column(String(WORKFLOW_ID_CHARS), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(NAME_CHARS), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    saved_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )


class WorkflowAssignmentRow(Base):
    """`agent.workflow_assignment`. A workflow an agent may run, and when it was withdrawn."""

    __tablename__ = "workflow_assignment"
    __table_args__ = (
        CheckConstraint(_present("agent_id"), name="agent_present"),
        CheckConstraint(WORKFLOW_ID_GRAMMAR, name="workflow_id_grammar"),
        CheckConstraint(_present("assigned_by"), name="assigned_by_present"),
        CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL)", name="a_removal_is_a_person_and_a_date"
        ),
        Index(
            "uq_workflow_assignment_one_live_row_per_pair",
            "agent_id",
            "workflow_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        {"schema": "agent"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(WORKFLOW_ID_CHARS), nullable=False)
    assigned_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
    removed_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowRunRow(Base):
    """`ops.workflow_run`. How one run ended, and the first step that failed."""

    __tablename__ = "workflow_run"
    __table_args__ = (
        CheckConstraint(one_of("outcome", Outcome), name="outcome"),
        CheckConstraint(_present("run_id"), name="run_present"),
        CheckConstraint(WORKFLOW_ID_GRAMMAR, name="workflow_id_grammar"),
        CheckConstraint("version >= 1", name="version_is_positive"),
        CheckConstraint(_present("agent_id"), name="agent_present"),
        CheckConstraint(_present("run_by"), name="an_actor_ran_it"),
        CheckConstraint(
            "(outcome = 'success') = (failed_step IS NULL)",
            name="a_failure_names_its_step",
        ),
        UniqueConstraint("run_id", name="uq_workflow_run_one_row_per_run"),
        Index("ix_workflow_run_by_workflow", "workflow_id", "started_at"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_id: Mapped[str] = mapped_column(String(RUN_ID_CHARS), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(WORKFLOW_ID_CHARS), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    run_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    failed_step: Mapped[str | None] = mapped_column(String(STEP_ID_CHARS), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )


class WorkflowStepRunRow(Base):
    """`ops.workflow_step_run`. What became of one step of one run: a status and a word."""

    __tablename__ = "workflow_step_run"
    __table_args__ = (
        CheckConstraint(one_of("status", Status), name="status"),
        CheckConstraint(
            "cause IS NULL OR cause IN ("
            + ", ".join(f"'{one.value}'" for one in sorted(Cause, key=lambda c: c.value))
            + ")",
            name="cause_is_a_known_word",
        ),
        CheckConstraint(
            "(status = 'ok') = (cause IS NULL)", name="only_a_step_that_did_not_finish_has_a_cause"
        ),
        CheckConstraint(
            "position >= 0 AND attempts >= 0 AND seconds >= 0", name="counts_not_negative"
        ),
        UniqueConstraint("run_id", "step_id", name="uq_workflow_step_run_one_row_per_step"),
        {"schema": "ops"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_id: Mapped[str] = mapped_column(String(RUN_ID_CHARS), nullable=False)
    step_id: Mapped[str] = mapped_column(String(STEP_ID_CHARS), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    cause: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detail: Mapped[str] = mapped_column(String(DETAIL_CHARS), nullable=False, server_default="")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    seconds: Mapped[float] = mapped_column(Double, nullable=False)
