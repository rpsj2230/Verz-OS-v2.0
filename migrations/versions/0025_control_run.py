"""One row per attempt to run a scheduled control, with row-level security on.

`brain.ops.controls` has said since it was written that eleven of the thirteen mechanisms
that have to keep running have no caller of any kind. Needs Rupash item 47 chose the answer:
a scheduler inside the application container. `brain.ops.schedule` decides what is owed and
this is where the answer to "when did it last run" survives a restart.

**Nothing is backfilled and nothing needs to be.** Every control has an empty history, which
`brain.ops.schedule.owed` reads as a first run: owed immediately and not late. That is the
state the module was written for and it is why the alerting does not fire on a fresh install.

**The table is appended to and never updated**, so there is an INSERT policy and an UPDATE
policy and no DELETE policy. The UPDATE exists for one field: a run is inserted when it starts
and its outcome is written when it returns, which is what makes a row with no `finished_at`
mean "this did not come back" rather than "nobody recorded it". A DELETE policy would be
somewhere to put the fact that a mechanism failed all week.

**`USING (true)` is not an absence of a permission check**, for the reason `0018` gives about
`mem.persistent` and `0020` repeats about `er.canonical`. Which runs a reader may see is a
console question decided against their live entitlements; these rows carry a control name and
two timestamps and no field a predicate here could read. A policy that pretended otherwise
would be a second and different implementation of the rule.

`brain.ops.sweeps.sweep_rls` does not check the `ops` schema, which `brain.tables.routing`
already records as a gap in the sweep rather than in the schema. The security is enabled here
and `tests/unit/test_tables.py` asserts it; widening the sweep is its own change.

The downgrade is real and drops the table. Nothing depends on it: a scheduler with no history
starts every control once, which is the state before this migration.

Task ids: none
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

#: The table this migration creates, read by `tests/unit/test_tables.py` so the test and the
#: migration cannot disagree about what shipped. Every migration that creates a table exports
#: its own slice this way and the package tuple is their concatenation, which is what stops a
#: table existing in one and not the other.
TABLES: tuple[str, ...] = ("ops.control_run",)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.control_run ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY control_run_readable ON ops.control_run
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY control_run_writable ON ops.control_run
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    # The only update a run ever takes: it finished, and this is what it ended as.
    """
    CREATE POLICY control_run_finishable ON ops.control_run
        FOR UPDATE TO brain_app
        USING (finished_at IS NULL)
        WITH CHECK (true)
    """,
)


def upgrade() -> None:
    op.create_table(
        "control_run",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("report_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "name IN ('audit_anchor', 'backup_exposure', 'canary_run', 'denial_digest', "
            "'directory_sync', 'knowledge_reverification', 'model_health_probes', "
            "'queue_redrive', 'resolution_calibration', 'restore_drill', 'retention_sweep', "
            "'side_effect_resume', 'spend_correction')",
            name="ck_control_run_control_run_name",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('failed', 'ok', 'refused')",
            name="ck_control_run_control_run_outcome",
        ),
        sa.CheckConstraint(
            "(finished_at IS NULL AND outcome IS NULL) OR "
            "(finished_at IS NOT NULL AND outcome IS NOT NULL)",
            name="ck_control_run_control_run_finished_with_an_outcome",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_control_run_control_run_finished_after_it_started",
        ),
        sa.CheckConstraint(
            "detail IS NULL OR length(detail) <= 2000",
            name="ck_control_run_control_run_detail_is_a_sentence",
        ),
        schema="ops",
    )
    op.create_index(
        "ix_control_run_by_control",
        "control_run",
        ["name", "started_at"],
        schema="ops",
        postgresql_using="btree",
    )
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_index("ix_control_run_by_control", table_name="control_run", schema="ops")
    op.drop_table("control_run", schema="ops")
