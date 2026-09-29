"""The nightly schema check gets a table, and joins the control-run names.

**`ops.connector_schema_check`: one row per night per kind of record a connection reads.** The
connection and its source's name, the entity, when it was checked, how many records were read, the
fields a record answered and the fields answered before that no record answers now.
`brain.tables.connector_schema` argues the columns and `brain.ops.schema_drift` the finding.

**SELECT and INSERT, and no UPDATE or DELETE**, for `0133`'s reason: a finding is a fact about one
night and nothing edits it. The worker appends as the database's owner, and the application role is
granted the append so a worker configured with that role's login is not refused, and so the install
check can run the check in its own transaction. **`USING (true)` on the read**: a row holds a
source's name and this release's field names, which every reader of the Connectors screen may be
told, and the answer lane reads it at every asker's reach.

**Names only, by a check.** Both lists, read as comma-joined text, must be names and commas, so
nothing a record held can be written here by any path.

**One supersession.** The control-run names gain `connector_schema_check`, replacing `0133`'s,
which is the newest in the database.

**The downgrade** drops the table, which discards every finding, and puts the control-run names back
`NOT VALID`, for `0026`'s reason: a run already recorded stays.

Task ids: M11.8.7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0168"
# The newest migration on origin/main when this was written, 91bf74ae: `0157`. Provisional, and the
# coordinator re-points it at landing behind whatever lands first. Nothing after `0133` touches the
# control-run names.
down_revision = "0157"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.connector_schema_check",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason and held equal to `brain.tables.connector_schema` by a test.
CONNECTOR_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,62}$"
NAME_PATTERN = "[a-z][a-z0-9_]{0,59}"
NAMES_ONLY = f"^({NAME_PATTERN}(,{NAME_PATTERN})*)?$"
NAME_CHARS = 60
CONNECTOR_CHARS = 64

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.connector_schema_check TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.connector_schema_check ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY connector_schema_check_readable ON ops.connector_schema_check
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY connector_schema_check_appendable ON ops.connector_schema_check
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)

#: The control-run names, with and without `connector_schema_check`. The second is `0133`'s.
WITH_SCHEMA_CHECK = (
    "name IN ('acceptance_run', 'audit_anchor', 'automation_run', 'backup_exposure', "
    "'canary_run', 'connector_schema_check', 'connector_sync', 'denial_digest', 'directory_sync', "
    "'erasure_queue', 'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', "
    "'queue_redrive', 'resolution_calibration', 'restore_drill', 'retention_sweep', "
    "'side_effect_resume', 'spend_correction', 'spend_report_refresh', 'vault_audit_ship', "
    "'vault_token_renewal')"
)
WITHOUT_SCHEMA_CHECK = (
    "name IN ('acceptance_run', 'audit_anchor', 'automation_run', 'backup_exposure', "
    "'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', 'erasure_queue', "
    "'knowledge_reverification', 'model_health_probes', 'outbox_dispatch', 'queue_redrive', "
    "'resolution_calibration', 'restore_drill', 'retention_sweep', 'side_effect_resume', "
    "'spend_correction', 'spend_report_refresh', 'vault_audit_ship', 'vault_token_renewal')"
)

#: What this migration replaces: `0133`'s control-run names.
SUPERSEDES: dict[str, str] = {WITHOUT_SCHEMA_CHECK: WITH_SCHEMA_CHECK}

#: Drops the control-run name constraint by whichever name it has. See `0030`, which `0133` copies.
DROP_THE_NAME_CONSTRAINT = """
DO $$
DECLARE
    v_name text;
BEGIN
    FOR v_name IN
        SELECT c.conname
          FROM pg_constraint c
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
    assert all("DELETE" not in statement and "UPDATE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "connector_schema_check",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("connection_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("connector", sa.String(CONNECTOR_CHARS), nullable=False),
        sa.Column("entity", sa.String(NAME_CHARS), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sampled", sa.Integer(), nullable=False),
        sa.Column(
            "answered",
            postgresql.ARRAY(sa.String(NAME_CHARS)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "missing",
            postgresql.ARRAY(sa.String(NAME_CHARS)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.CheckConstraint(f"connector ~ '{CONNECTOR_NAME_PATTERN}'", name="connector_shape"),
        sa.CheckConstraint(f"entity ~ '^{NAME_PATTERN}$'", name="entity_shape"),
        sa.CheckConstraint("sampled >= 0", name="sampled_is_not_negative"),
        sa.CheckConstraint(
            f"array_to_string(answered, ',') ~ '{NAMES_ONLY}' "
            f"AND array_to_string(missing, ',') ~ '{NAMES_ONLY}'",
            name="names_only",
        ),
        schema="ops",
    )
    op.create_index(
        "ix_connector_schema_check_connection_entity",
        "connector_schema_check",
        ["connection_id", "entity", "checked_at"],
        schema="ops",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)

    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint("control_run_name", "control_run", WITH_SCHEMA_CHECK, schema="ops")


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_SCHEMA_CHECK,
        schema="ops",
        postgresql_not_valid=True,
    )
    # The index and the policies go with the table.
    op.drop_table("connector_schema_check", schema="ops")
