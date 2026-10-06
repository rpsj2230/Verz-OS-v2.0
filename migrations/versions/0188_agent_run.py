"""Every agent run is recorded when it ends: who it was for, which agent, why it stopped, its counts.

`ops.agent_run`, one row per finished run of `brain.gate.runtime`, the one loop that hands a model
tools. `brain.tables.agent_run` holds the argument for each column. **Counts and names from closed
lists, and nothing a run read or wrote**: no question, no argument, no result, no prompt. The stop
reason is the bound a run reached when it reached one (M13.7.2).

**SELECT and INSERT only, written in the session's own name**, `0154`'s shape: a row names its
principal as `app.principal_id`, and a row naming anybody else is refused. A person reads their
own runs. Nothing is updated and nothing may delete a row, so the rows are their own history and
need no ledger trigger.

The lane and the stop reason are checked against `brain.core.lane.Lane` and
`brain.gate.stop.StopReason` as they stand today, written out here as data, because a migration
says what it did on the day it ran; `tests/unit/test_tables.py` holds the model's rendering of the
same constraints to this one.

The downgrade drops the table. A run recorded nowhere still ran; nothing else reads these rows.

Task ids: M13.7.2

Revision ID: 0188
Revises: 0187
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0188"
# #396's 0187 at the time of writing. Re-pointed at whichever migration is the head when it lands.
down_revision = "0187"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: the principal and the agent are values,
#: so a run's row outlives both.
TABLES: tuple[str, ...] = ("ops.agent_run",)

APP_ROLE = "brain_app"

#: Widths held equal to `brain.tables.agent_run` by `tests/unit/test_agent_run_store.py`.
TRACE_ID_CHARS = 64
PRINCIPAL_ID_CHARS = 128
AGENT_ID_CHARS = 60
VOCABULARY_CHARS = 24

#: `Lane` and `StopReason` on the day this ran.
LANES: tuple[str, ...] = ("answer", "fast", "task")
STOP_REASONS: tuple[str, ...] = (
    "answered",
    "declined",
    "faulted",
    "refused",
    "spend_bound",
    "time_bound",
    "tool_call_bound",
    "turn_bound",
)

PRINCIPAL = "current_setting('app.principal_id', true)"


def _one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{one}'" for one in sorted(values))
    return f"{column} IN ({listed})"


RLS: tuple[str, ...] = (
    "ALTER TABLE ops.agent_run ENABLE ROW LEVEL SECURITY",
    f"""
    CREATE POLICY agent_run_own ON ops.agent_run
        FOR SELECT TO brain_app
        USING (principal_id = {PRINCIPAL})
    """,
    f"""
    CREATE POLICY agent_run_written_in_the_sessions_name ON ops.agent_run
        FOR INSERT TO brain_app
        WITH CHECK (principal_id = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.agent_run TO brain_app",)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)
    op.create_table(
        "agent_run",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=False),
        sa.Column("principal_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("lane", sa.String(VOCABULARY_CHARS), nullable=False),
        sa.Column("stop_reason", sa.String(VOCABULARY_CHARS), nullable=False),
        sa.Column("turns", sa.Integer(), nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("steered", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(trace_id)) > 0", name="trace_present"),
        sa.CheckConstraint("length(btrim(principal_id)) > 0", name="principal_present"),
        sa.CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        sa.CheckConstraint(_one_of("lane", LANES), name="lane"),
        sa.CheckConstraint(_one_of("stop_reason", STOP_REASONS), name="stop_reason"),
        sa.CheckConstraint(
            "turns >= 0 AND tool_calls >= 0 AND tokens >= 0 AND steered >= 0",
            name="counts_not_negative",
        ),
        sa.CheckConstraint("ended_at >= started_at", name="ends_after_it_starts"),
        schema="ops",
    )
    op.create_index(
        "ix_ops_agent_run_principal_id_started_at",
        "agent_run",
        ["principal_id", "started_at"],
        schema="ops",
    )
    op.create_index(
        "ix_ops_agent_run_agent_id_started_at",
        "agent_run",
        ["agent_id", "started_at"],
        schema="ops",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grant go with the table.
    op.drop_table("agent_run", schema="ops")
