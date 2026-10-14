"""What the fan-out gate decided for a plan, kept: `ops.fanout_gate`.

`brain.orchestration.fanout` weighs a plan by six arithmetic conditions before any child starts
and decides `single_loop` or `parallel`. The decision was a value that ended with the process, so
"why did this run split" had no answer afterwards. This is the table that keeps it (M18.2.4);
`brain.tables.fanout_gate` holds the argument for each column.

**Numbers and a verdict only.** The five inputs, the conditions evaluated and the ones that
failed, and the verdict. No objective, no subtask name, no asker: a record of how a plan was
weighed is not a record of what anybody asked.

**The table keeps the rule `GateRecord` keeps.** `parallel` only after all six conditions were
evaluated and none failed, as a check constraint, so a row written by any other route cannot say
`parallel` for a plan that failed one.

**SELECT and INSERT only, written in the session's own name**, `0217`'s shape: the insert policy
admits a row whose `decided_by` is the session's principal, and no UPDATE or DELETE is granted, so
a decision is never rewritten. **No ledger entry of its own**: weighing a plan changes nobody's
access and no configuration, and the row is its own record of who and when.

The downgrade drops the table. The decisions it held are lost, which is the state before this.

Task ids: M18.2.4

Revision ID: 0240
Revises: 0231
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0240"
# The head of main when this was landed (0231). The number leaves a gap after it, so a migration
# that lands first does not take this one.
down_revision = "0231"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: a run and an administrator are values, so
#: a decision outlives both.
TABLES: tuple[str, ...] = ("ops.fanout_gate",)

APP_ROLE = "brain_app"

#: Held equal to `brain.tables.fanout_gate`.
RUN_ID_CHARS = 128
PRINCIPAL_ID_CHARS = 128
CONDITION_CHARS = 40
VERDICT_CHARS = 16

#: `brain.orchestration.fanout.Verdict` and how many conditions there are, on the day this ran.
VERDICTS: tuple[str, ...] = ("parallel", "single_loop")
HOW_MANY_CONDITIONS = 6

PRINCIPAL = "current_setting('app.principal_id', true)"


def _one_of(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{one}'" for one in sorted(values))
    return f"{column} IN ({listed})"


RLS: tuple[str, ...] = (
    "ALTER TABLE ops.fanout_gate ENABLE ROW LEVEL SECURITY",
    # Read by the screen for whoever may see the rehearsals; who may is decided where it is shown.
    """
    CREATE POLICY fanout_gate_readable ON ops.fanout_gate
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY fanout_gate_written_in_the_sessions_name ON ops.fanout_gate
        FOR INSERT TO brain_app
        WITH CHECK (decided_by = {PRINCIPAL})
    """,
)

#: SELECT and INSERT, and never UPDATE or DELETE.
GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.fanout_gate TO brain_app",)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)
    op.create_table(
        "fanout_gate",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(RUN_ID_CHARS), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("branches", sa.Integer(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("cost_multiplier", postgresql.DOUBLE_PRECISION(), nullable=False),
        sa.Column("speedup", postgresql.DOUBLE_PRECISION(), nullable=False),
        sa.Column("largest_share", postgresql.DOUBLE_PRECISION(), nullable=False),
        sa.Column("evaluated", sa.ARRAY(sa.String(CONDITION_CHARS)), nullable=False),
        sa.Column("failed", sa.ARRAY(sa.String(CONDITION_CHARS)), nullable=False),
        sa.Column("verdict", sa.String(VERDICT_CHARS), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.CheckConstraint(_one_of("verdict", VERDICTS), name="verdict"),
        sa.CheckConstraint("length(btrim(run_id)) > 0", name="run_present"),
        sa.CheckConstraint("length(btrim(decided_by)) > 0", name="an_actor_decided"),
        sa.CheckConstraint("branches >= 0 AND depth >= 0", name="counts_not_negative"),
        sa.CheckConstraint("failed <@ evaluated", name="failed_were_evaluated"),
        sa.CheckConstraint(
            "verdict <> 'parallel' OR (cardinality(failed) = 0 AND "
            f"cardinality(evaluated) = {HOW_MANY_CONDITIONS})",
            name="parallel_only_after_all_six",
        ),
        schema="ops",
    )
    op.create_index("ix_fanout_gate_by_decision", "fanout_gate", ["decided_at"], schema="ops")
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies and the grant go with the table.
    op.drop_table("fanout_gate", schema="ops")
