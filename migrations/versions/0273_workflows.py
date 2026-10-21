"""Stored workflows: their versions, who they are assigned to, and how each run went.

Four tables and one widened vocabulary for the first workflow engine.

**`ops.workflow_version`, M17.6.1.** One saved version of one workflow, insert-only. A run names the
version it ran, so the definition a run used is still there when the workflow has moved on.

**`agent.workflow_assignment`, M17.7.7.** A workflow an agent may run. A link and not reach, with
`agent.agent_callee`'s shape: the row stays when the link is withdrawn.

**`ops.workflow_run` and `ops.workflow_step_run`, M17.6.8.** How a run ended and what became of each
step: a status, a cause from a closed list and, for a skipped step, the condition in the definition's
own words. No output value, no argument, no record. Written once in the session's own name; a step
row is admitted only for a run the same person wrote.

**`ops.evaluation_candidate.source` admits `workflow`, M17.6.7.** A step that failed in each of its
last runs opens a candidate for a person to decide, and nothing opens it against the workflow's
definition: the candidate names the agent and a case reference, as every candidate does.

**Nothing here narrows what the previous release writes.** The four tables are new, the check on
`source` only gains a word, and the switch that gates running a workflow ships off.

The downgrade drops the tables and narrows the check back `NOT VALID`, so a `workflow` candidate
already written stays as history and the narrower list holds every write after it.

Task ids: M17.6.1, M17.6.7, M17.6.8, M17.7.7

Revision ID: 0273
Revises: 0272
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0273"
# The head of main when this was written: the agent-coordination migration.
down_revision = "0272"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: an agent, a workflow and a person are
#: values, so a version, a run and its steps outlive all three.
TABLES: tuple[str, ...] = (
    "ops.workflow_version",
    "agent.workflow_assignment",
    "ops.workflow_run",
    "ops.workflow_step_run",
)

APP_ROLE = "brain_app"
PRINCIPAL = "current_setting('app.principal_id', true)"

#: Held equal to `brain.tables.workflow`.
AGENT_ID_CHARS = 60
WORKFLOW_ID_CHARS = 60
STEP_ID_CHARS = 32
PRINCIPAL_ID_CHARS = 128
RUN_ID_CHARS = 128
DETAIL_CHARS = 200
NAME_CHARS = 120

#: `brain.orchestration.workflow_run.Outcome`, `Status` and `Cause`, on the day this ran.
OUTCOMES: tuple[str, ...] = ("failure", "partial", "success")
STATUSES: tuple[str, ...] = ("failed", "ok", "skipped")
CAUSES: tuple[str, ...] = (
    "condition_not_met",
    "failed_after_retries",
    "handler_not_needed",
    "input_missing",
    "invalid_output",
    "refused",
    "run_stopped",
    "write_not_offered",
)

#: `brain.tables.quality.CandidateSource`, before and after.
SOURCES_BEFORE = "source IN ('canary', 'golden', 'sampled')"
SOURCES_AFTER = "source IN ('canary', 'golden', 'sampled', 'workflow')"

WORKFLOW_ID_GRAMMAR = "workflow_id ~ '^[a-z][a-z0-9_-]{1,59}$'"


def _one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{one}'" for one in sorted(values))
    return f"{column} IN ({listed})"


RLS: tuple[str, ...] = (
    "ALTER TABLE ops.workflow_version ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY workflow_version_readable ON ops.workflow_version
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY workflow_version_saved_in_the_sessions_name ON ops.workflow_version
        FOR INSERT TO brain_app
        WITH CHECK (saved_by = {PRINCIPAL})
    """,
    "ALTER TABLE agent.workflow_assignment ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY workflow_assignment_readable ON agent.workflow_assignment
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY workflow_assignment_made_in_the_sessions_name ON agent.workflow_assignment
        FOR INSERT TO brain_app
        WITH CHECK (assigned_by = {PRINCIPAL} AND removed_at IS NULL)
    """,
    f"""
    CREATE POLICY workflow_assignment_withdrawn_in_the_sessions_name ON agent.workflow_assignment
        FOR UPDATE TO brain_app
        USING (removed_at IS NULL)
        WITH CHECK (removed_by = {PRINCIPAL})
    """,
    "ALTER TABLE ops.workflow_run ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY workflow_run_readable ON ops.workflow_run
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY workflow_run_written_in_the_sessions_name ON ops.workflow_run
        FOR INSERT TO brain_app
        WITH CHECK (run_by = {PRINCIPAL})
    """,
    "ALTER TABLE ops.workflow_step_run ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY workflow_step_run_readable ON ops.workflow_step_run
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY workflow_step_run_for_the_sessions_own_run ON ops.workflow_step_run
        FOR INSERT TO brain_app
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM ops.workflow_run r
                WHERE r.run_id = workflow_step_run.run_id AND r.run_by = {PRINCIPAL}
            )
        )
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON ops.workflow_version TO brain_app",
    "GRANT SELECT, INSERT ON agent.workflow_assignment TO brain_app",
    "GRANT UPDATE (removed_by, removed_at) ON agent.workflow_assignment TO brain_app",
    "GRANT SELECT, INSERT ON ops.workflow_run TO brain_app",
    "GRANT SELECT, INSERT ON ops.workflow_step_run TO brain_app",
)


def _uuid_key() -> sa.Column[object]:
    return sa.Column(
        "id",
        sa.Uuid(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    op.create_table(
        "workflow_version",
        _uuid_key(),
        sa.Column("workflow_id", sa.String(WORKFLOW_ID_CHARS), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(NAME_CHARS), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("saved_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "saved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint(WORKFLOW_ID_GRAMMAR, name="workflow_id_grammar"),
        sa.CheckConstraint("version >= 1", name="version_is_positive"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="name_present"),
        sa.CheckConstraint("length(btrim(saved_by)) > 0", name="saved_by_present"),
        sa.CheckConstraint("jsonb_typeof(definition) = 'object'", name="definition_is_an_object"),
        sa.UniqueConstraint("workflow_id", "version", name="uq_workflow_version_one_per_number"),
        schema="ops",
    )
    op.create_table(
        "workflow_assignment",
        _uuid_key(),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("workflow_id", sa.String(WORKFLOW_ID_CHARS), nullable=False),
        sa.Column("assigned_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.Column("removed_by", sa.String(PRINCIPAL_ID_CHARS), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        sa.CheckConstraint(WORKFLOW_ID_GRAMMAR, name="workflow_id_grammar"),
        sa.CheckConstraint("length(btrim(assigned_by)) > 0", name="assigned_by_present"),
        sa.CheckConstraint(
            "(removed_at IS NULL) = (removed_by IS NULL)", name="a_removal_is_a_person_and_a_date"
        ),
        schema="agent",
    )
    op.create_index(
        "uq_workflow_assignment_one_live_row_per_pair",
        "workflow_assignment",
        ["agent_id", "workflow_id"],
        unique=True,
        schema="agent",
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.create_table(
        "workflow_run",
        _uuid_key(),
        sa.Column("run_id", sa.String(RUN_ID_CHARS), nullable=False),
        sa.Column("workflow_id", sa.String(WORKFLOW_ID_CHARS), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("run_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("failed_step", sa.String(STEP_ID_CHARS), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint(_one_of("outcome", OUTCOMES), name="outcome"),
        sa.CheckConstraint("length(btrim(run_id)) > 0", name="run_present"),
        sa.CheckConstraint(WORKFLOW_ID_GRAMMAR, name="workflow_id_grammar"),
        sa.CheckConstraint("version >= 1", name="version_is_positive"),
        sa.CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        sa.CheckConstraint("length(btrim(run_by)) > 0", name="an_actor_ran_it"),
        sa.CheckConstraint(
            "(outcome = 'success') = (failed_step IS NULL)", name="a_failure_names_its_step"
        ),
        sa.UniqueConstraint("run_id", name="uq_workflow_run_one_row_per_run"),
        schema="ops",
    )
    op.create_index(
        "ix_workflow_run_by_workflow", "workflow_run", ["workflow_id", "started_at"], schema="ops"
    )
    op.create_table(
        "workflow_step_run",
        _uuid_key(),
        sa.Column("run_id", sa.String(RUN_ID_CHARS), nullable=False),
        sa.Column("step_id", sa.String(STEP_ID_CHARS), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("cause", sa.String(32), nullable=True),
        sa.Column("detail", sa.String(DETAIL_CHARS), nullable=False, server_default=sa.text("''")),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("seconds", postgresql.DOUBLE_PRECISION(), nullable=False),
        sa.CheckConstraint(_one_of("status", STATUSES), name="status"),
        sa.CheckConstraint(
            "cause IS NULL OR " + _one_of("cause", CAUSES), name="cause_is_a_known_word"
        ),
        sa.CheckConstraint(
            "(status = 'ok') = (cause IS NULL)", name="only_a_step_that_did_not_finish_has_a_cause"
        ),
        sa.CheckConstraint(
            "position >= 0 AND attempts >= 0 AND seconds >= 0", name="counts_not_negative"
        ),
        sa.UniqueConstraint("run_id", "step_id", name="uq_workflow_step_run_one_row_per_step"),
        schema="ops",
    )
    op.drop_constraint("source", "evaluation_candidate", schema="ops", type_="check")
    op.create_check_constraint("source", "evaluation_candidate", SOURCES_AFTER, schema="ops")
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_constraint("source", "evaluation_candidate", schema="ops", type_="check")
    # NOT VALID, so a `workflow` candidate already written stays as history and the narrower list
    # holds every write after it (the policy for a downgrade that re-creates a check).
    op.create_check_constraint(
        "source", "evaluation_candidate", SOURCES_BEFORE, schema="ops", postgresql_not_valid=True
    )
    # The policies and the grants go with the tables.
    op.drop_table("workflow_step_run", schema="ops")
    op.drop_table("workflow_run", schema="ops")
    op.drop_table("workflow_assignment", schema="agent")
    op.drop_table("workflow_version", schema="ops")
