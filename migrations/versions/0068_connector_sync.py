"""The worker's reads of a connected source get a table, and the schedule a control to run them.

`brain.tables.connector_sync` holds the argument for the shape: one row per attempt, appended when
it ends, naming the connection it read with, carrying a closed outcome, a health word, two
counts, the failures in a row, when the next attempt may be made and a constant sentence. What is
here is the table, its policies, its grants, and the control-run name `connector_sync`.

**`USING (true)` on the read, for `0057`'s reason.** Which sources a reader may be told were read,
and how that went, is `brain.console.connector_trust`'s question asked against the reader's own
grants, the same question that decides whether the connection itself is listed. A predicate here
would be a second and different implementation of it.

**SELECT and INSERT, and no UPDATE or DELETE.** An attempt that failed does not become a success
when a later one works, and the Connectors screen's "failed six times in a row" is only true while
the six rows are kept. The worker appends as the database's owner, as `brain.ops.erasure_store` and
`brain.ops.webhook_delivery` already do, and the application role is granted the append as well so
a worker configured with that role's login is not refused.

**Nothing for the fast lane role.** It answers from the projection and has no business reading how
the projection was filled.

**The control-run names widen by one, `connector_sync`**, replacing `0067`'s list, which is the one
in the database, so the worker can record the schedule's run of the control that does the reading.

The downgrade is real, discards every recorded attempt, and narrows the names again `NOT VALID`:
a run of `connector_sync` already recorded in `ops.control_run` is kept and not re-checked, because
a run that happened is not deleted to make a constraint fit, and only a run written after the
downgrade is refused. Re-checking the old rows would make the downgrade fail on every install whose
worker has run the sync.

Task ids: M42.6.5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0068"
# Written against 0064 and re-pointed at 0067 when it was integrated, after 0066 widened the
# control-run names with `vault_token_renewal` and 0067 with `automation_run`. Nothing here depends
# on a table either builds, and the control-run names below carry both of their names.
down_revision = "0067"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.connector_sync",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.connector_sync` by `tests/unit/test_tables.py`'s model-versus-migration check.
CONNECTOR_CHARS = 64
CONNECTOR_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,62}$"
DETAIL_CHARS = 500

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.connector_sync TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.connector_sync ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY connector_sync_readable ON ops.connector_sync
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY connector_sync_appendable ON ops.connector_sync
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)

#: The control-run names, with and without `connector_sync`. The second is `0067`'s.
WITH_CONNECTOR_SYNC = (
    "name IN ('audit_anchor', 'automation_run', 'backup_exposure', 'canary_run', "
    "'connector_sync', 'denial_digest', 'directory_sync', 'erasure_queue', "
    "'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', 'queue_redrive', "
    "'resolution_calibration', 'restore_drill', 'retention_sweep', 'side_effect_resume', "
    "'spend_correction', 'spend_report_refresh', 'vault_token_renewal')"
)
WITHOUT_CONNECTOR_SYNC = (
    "name IN ('audit_anchor', 'automation_run', 'backup_exposure', 'canary_run', "
    "'denial_digest', 'directory_sync', 'erasure_queue', 'knowledge_reverification', "
    "'model_health_probes', 'outbox_dispatch', 'queue_redrive', 'resolution_calibration', "
    "'restore_drill', 'retention_sweep', 'side_effect_resume', 'spend_correction', "
    "'spend_report_refresh', 'vault_token_renewal')"
)

#: What this migration replaces: `0067`'s control names, which are the ones in the database.
SUPERSEDES: dict[str, str] = {WITHOUT_CONNECTOR_SYNC: WITH_CONNECTOR_SYNC}

#: Drops the control-run name constraint by whichever name it has. See `0030`, which `0060` copies.
DROP_THE_NAME_CONSTRAINT = """
DO $$
DECLARE
    v_name text;
BEGIN
    FOR v_name IN
        SELECT c.conname FROM pg_constraint c
         WHERE c.conrelid = 'ops.control_run'::regclass
           AND c.contype = 'c'
           AND right(c.conname, 16) = 'control_run_name'
    LOOP
        EXECUTE 'ALTER TABLE ops.control_run DROP CONSTRAINT ' || quote_ident(v_name);
    END LOOP;
END
$$
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "connector_sync",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("connection_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("connector", sa.String(CONNECTOR_CHARS), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("health", sa.String(16), nullable=False),
        sa.Column("records", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.CheckConstraint(f"connector ~ '{CONNECTOR_NAME_PATTERN}'", name="connector_shape"),
        sa.CheckConstraint("outcome IN ('failed', 'quota', 'synced')", name="outcome"),
        sa.CheckConstraint("health IN ('degraded', 'down', 'ok')", name="health"),
        sa.CheckConstraint(
            "records >= 0 AND documents >= 0 AND consecutive_failures >= 0",
            name="counts_are_not_negative",
        ),
        sa.CheckConstraint(
            "(outcome <> 'synced' OR consecutive_failures = 0) "
            "AND (outcome <> 'failed' OR consecutive_failures > 0)",
            name="failures_follow_the_outcome",
        ),
        sa.CheckConstraint("finished_at >= started_at", name="finished_after_it_started"),
        sa.CheckConstraint("next_attempt_at >= finished_at", name="next_attempt_is_after_this_one"),
        sa.CheckConstraint(
            f"length(btrim(detail)) > 0 AND length(detail) <= {DETAIL_CHARS}",
            name="detail_is_a_sentence",
        ),
        schema="ops",
    )
    op.create_index(
        "ix_connector_sync_connection_finished",
        "connector_sync",
        ["connection_id", "finished_at"],
        schema="ops",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)

    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint("control_run_name", "control_run", WITH_CONNECTOR_SYNC, schema="ops")


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_CONNECTOR_SYNC,
        schema="ops",
        postgresql_not_valid=True,
    )
    # The index, the policies and the grants go with the table.
    op.drop_table("connector_sync", schema="ops")
