"""A job the recovery sweep set aside for a person is kept where the console can read it.

The queue's own tables are the driver's and are refused to the application role, so the Jobs screen
could say which controls ran and nothing about a queued job nobody was going to run again
(M17.1.5). `brain.ops.recovery_run` already decides, every minute, which orphaned jobs are put back
and which are set aside for a person; it now also writes each one it sets aside here, and
`GET /jobs/dead` reads them through `brain.ops.jobs.visible_dead_letters`.

**One row per job, written once.** The key is the driver's job id as text, so a sweep that sees the
same job twice writes nothing the second time. The row keeps the job's task name, its traffic class,
why it was set aside (a word from `brain.ops.jobs.DeadLetterReason`), how many times it was
re-driven and when, and **a principal that is the system's whenever the job did not carry one**:
a queued job carries references and never a reach, and inventing an owner for it would put it in
front of the wrong person's own-job rule. **No arguments and no failure text**, for the reason
`brain.ops.jobs.DeadLetter` gives: an operational row that copies somebody's data with a different
retention is the row this refuses to be.

**Read by the application, written by the worker's own queue connection.** The application role is
granted SELECT alone; who may see a row is decided in the route, never by a policy here, which is
the rule `ops.budget_stop` takes for its own.

The downgrade drops the table and discards what it held.

Task ids: M17.1.5, M17.1.1

Revision ID: 0228
Revises: 0227
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0228"
down_revision = "0227"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: the driver's job is a value, so a row
#: outlives the driver's own cleaning of finished jobs.
TABLES: tuple[str, ...] = ("ops.dead_letter",)

APP_ROLE = "brain_app"

#: Widths held equal to `brain.tables.dead_letter`.
JOB_ID_CHARS = 32
TASK_CHARS = 200
PRINCIPAL_ID_CHARS = 128
VOCABULARY_CHARS = 32

#: `brain.gate.context.TrafficClass` and `brain.ops.jobs.DeadLetterReason` on the day this ran.
TRAFFIC_CLASSES: tuple[str, ...] = (
    "automation",
    "human_async",
    "human_interactive",
    "system",
)
REASONS: tuple[str, ...] = (
    "attempts_exhausted",
    "quarantined_after_a_stop",
    "re_driven_too_often",
    "timed_out_every_attempt",
)


def _one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{one}'" for one in sorted(values))
    return f"{column} IN ({listed})"


RLS: tuple[str, ...] = (
    "ALTER TABLE ops.dead_letter ENABLE ROW LEVEL SECURITY",
    # Read for whoever asks; who may be shown a row is the route's decision, made with the one
    # entitlement machinery, so a second statement of it here would be a second place to be wrong.
    """
    CREATE POLICY dead_letter_readable ON ops.dead_letter
        FOR SELECT TO brain_app
        USING (true)
    """,
)

#: SELECT alone: the sweep writes on the queue's own connection, and nothing deletes.
GRANTS: tuple[str, ...] = ("GRANT SELECT ON ops.dead_letter TO brain_app",)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "INSERT" not in statement for statement in GRANTS)
    op.create_table(
        "dead_letter",
        sa.Column("job_id", sa.String(JOB_ID_CHARS), primary_key=True, nullable=False),
        sa.Column("task", sa.String(TASK_CHARS), nullable=False),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("traffic_class", sa.String(VOCABULARY_CHARS), nullable=False),
        sa.Column("reason", sa.String(VOCABULARY_CHARS), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("set_aside_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(_one_of("traffic_class", TRAFFIC_CLASSES), name="traffic_class"),
        sa.CheckConstraint(_one_of("reason", REASONS), name="reason"),
        sa.CheckConstraint("length(btrim(job_id)) > 0", name="job_present"),
        sa.CheckConstraint("length(btrim(task)) > 0", name="task_present"),
        sa.CheckConstraint("length(btrim(principal_id)) > 0", name="principal_present"),
        sa.CheckConstraint("attempts >= 0", name="attempts_not_negative"),
        schema="ops",
    )
    op.create_index(
        "ix_ops_dead_letter_set_aside_at", "dead_letter", ["set_aside_at"], schema="ops"
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policy and the grant go with the table.
    op.drop_table("dead_letter", schema="ops")
