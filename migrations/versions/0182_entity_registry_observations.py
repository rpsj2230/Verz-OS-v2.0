"""Each source record's comparison keys, and the join keys this install blocks.

Two tables beside the entity graph 0020 built. `brain.tables.resolution_registry` holds the
argument for each column.

**`er.observation`**: one row per source record the registry has read, holding what
`brain.resolution.entities.observe` made of it: a normalised name in its two keys, the name's
verdict and the fold that made it, Daitch-Mokotoff codes, one digest per identifier kind and two
comparison tokens. These are the columns `brain.resolution.cascade.SQL_PREDICATES` names, which
nothing created until now. **A digest column refuses anything but a digest**, so a raw email cannot
be stored here by any route, `er.identifier.key_hash`'s rule.

**`ops.control_run` admits `entity_resolution`**, the worker control that runs the registry,
superseding `0169`'s names, which are the newest list in the database. The downgrade puts those
back `NOT VALID`, for `0026`'s reason: a run already recorded stays.

**`er.blocked_value`**: a join key this install refuses (M14.6.1), held as the same peppered digest
`er.identifier` holds. SELECT and INSERT, written in the session's own name, `0154`'s shape: a
blocked value names its author, and nothing updates or deletes one.

**SELECT, INSERT and UPDATE on `er.observation`**: a record read again after it changed is
observed again, and its row says what it says now. Nothing deletes from either, and nothing at
all is granted to `brain_fastlane`, for 0020's reason: reach over a resolved entity is decided per
record in `brain.resolution.canonical.resolved_view`, not by a role.

**A person's email or telephone digest has no table here**, deliberately: whether a sync may ask a
source for one is the owner's question (item 155). See `brain.tables.resolution_registry`.

**The downgrade drops both.** An observation is remade from its record on the next run, and the
blocked values are an administrator's list, which an install downgraded past this migration does
not apply anyway.

Task ids: M14.1.3, M14.6.1, M14.7.3

Revision ID: 0182
Revises: 0154
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0182"
down_revision = "0154"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. None points at anything: each names a source record or a
#: digest by value, so each outlives what it names.
TABLES: tuple[str, ...] = ("er.observation", "er.blocked_value")

APP_ROLE = "brain_app"
FAST_ROLE = "brain_fastlane"

#: `brain.core.envelope.OBJECT_NAME_PATTERN`, copied for the reason 0020 gives.
NAME = "^[a-z][a-z0-9_]*$"
ENTITY_TYPE_IN = "entity_type IN ('company', 'person', 'project')"
KIND_IN = "kind IN ('domain', 'email', 'phone', 'tax_id', 'uen')"
VERDICT_IN = "name_verdict IN ('entirely a suffix', 'nothing left', 'too short', 'usable')"
KEY_HASH_IS_A_DIGEST = "key_hash ~ '^[0-9a-f]{64}$'"
HASH_COLUMNS: tuple[str, ...] = (
    "uen_hash",
    "tax_id_hash",
    "domain_hash",
    "email_hash",
    "phone_hash",
)

PRINCIPAL = "current_setting('app.principal_id', true)"

#: The control-run names, with and without `entity_resolution`. The second is `0169`'s.
WITH_ENTITY_RESOLUTION = (
    "name IN ('acceptance_run', 'audit_anchor', 'automation_run', 'backup_exposure', "
    "'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', 'entity_resolution', "
    "'erasure_queue', 'escalation_expiry', 'evening_digest', 'knowledge_reverification', "
    "'model_health_probes', 'outbox_dispatch', 'queue_redrive', 'resolution_calibration', "
    "'restore_drill', 'retention_sweep', 'side_effect_resume', 'spend_correction', "
    "'spend_report_refresh', 'vault_audit_ship', 'vault_token_renewal')"
)
WITHOUT_ENTITY_RESOLUTION = (
    "name IN ('acceptance_run', 'audit_anchor', 'automation_run', 'backup_exposure', "
    "'canary_run', 'connector_sync', 'denial_digest', 'directory_sync', 'erasure_queue', "
    "'escalation_expiry', 'evening_digest', 'knowledge_reverification', 'model_health_probes', "
    "'outbox_dispatch', 'queue_redrive', 'resolution_calibration', 'restore_drill', "
    "'retention_sweep', 'side_effect_resume', 'spend_correction', 'spend_report_refresh', "
    "'vault_audit_ship', 'vault_token_renewal')"
)

#: What this migration replaces: `0169`'s control-run names.
SUPERSEDES: dict[str, str] = {WITHOUT_ENTITY_RESOLUTION: WITH_ENTITY_RESOLUTION}

#: Drops the control-run name constraint by whichever name it has. See `0030`, which `0169` copies.
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

RLS: tuple[str, ...] = (
    "ALTER TABLE er.observation ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE er.blocked_value ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY observation_readable ON er.observation
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY observation_writable ON er.observation
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY observation_reobserved ON er.observation
        FOR UPDATE TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
    """
    CREATE POLICY blocked_value_readable ON er.blocked_value
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY blocked_value_added_in_the_sessions_name ON er.blocked_value
        FOR INSERT TO brain_app
        WITH CHECK (blocked_by = {PRINCIPAL})
    """,
)

#: No DELETE on anything, and nothing for `brain_fastlane`.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON er.observation TO brain_app",
    "GRANT SELECT, INSERT ON er.blocked_value TO brain_app",
)


def _source_ref_columns() -> list[sa.Column[str]]:
    return [
        sa.Column("source", sa.String(60), primary_key=True, nullable=False),
        sa.Column("entity", sa.String(60), primary_key=True, nullable=False),
        sa.Column("source_id", sa.String(200), primary_key=True, nullable=False),
    ]


def _source_ref_constraints() -> list[sa.schema.SchemaItem]:
    return [
        sa.CheckConstraint(f"source ~ '{NAME}'", name="source_is_a_name"),
        sa.CheckConstraint(f"entity ~ '{NAME}'", name="entity_is_a_name"),
        sa.CheckConstraint("length(btrim(source_id)) > 0", name="source_id_present"),
    ]


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    assert all(FAST_ROLE not in statement for statement in GRANTS + RLS)
    op.create_table(
        "observation",
        *_source_ref_columns(),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("name_collapsed", sa.String(200), nullable=True),
        sa.Column("name_key", sa.String(200), nullable=True),
        sa.Column("name_verdict", sa.String(24), nullable=False),
        sa.Column("name_fold", sa.String(64), nullable=False),
        sa.Column(
            "name_dm",
            sa.ARRAY(sa.String(16)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        *(sa.Column(column, sa.String(64), nullable=True) for column in HASH_COLUMNS),
        sa.Column("country_key", sa.String(120), nullable=True),
        sa.Column("postcode_key", sa.String(120), nullable=True),
        sa.Column(
            "verified",
            sa.ARRAY(sa.String(16)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        *_source_ref_constraints(),
        sa.CheckConstraint(ENTITY_TYPE_IN, name="entity_type_known"),
        sa.CheckConstraint(VERDICT_IN, name="name_verdict_known"),
        *(
            sa.CheckConstraint(
                f"{column} IS NULL OR {column} ~ '^[0-9a-f]{{64}}$'",
                name=f"{column}_is_a_digest",
            )
            for column in HASH_COLUMNS
        ),
        schema="er",
    )
    op.create_index("ix_observation_domain_hash", "observation", ["domain_hash"], schema="er")
    op.create_index("ix_observation_uen_hash", "observation", ["uen_hash"], schema="er")
    op.create_index("ix_observation_name_key", "observation", ["name_key"], schema="er")
    op.create_table(
        "blocked_value",
        sa.Column("kind", sa.String(16), primary_key=True, nullable=False),
        sa.Column("key_hash", sa.String(64), primary_key=True, nullable=False),
        sa.Column("reason", sa.String(400), nullable=False),
        sa.Column("blocked_by", sa.String(128), nullable=False),
        sa.Column(
            "blocked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(KIND_IN, name="kind_known"),
        sa.CheckConstraint(KEY_HASH_IS_A_DIGEST, name="key_hash_is_a_digest"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="reason_present"),
        sa.CheckConstraint("length(btrim(blocked_by)) > 0", name="blocked_by_present"),
        schema="er",
    )
    for statement in RLS + GRANTS:
        op.execute(statement)
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name", "control_run", WITH_ENTITY_RESOLUTION, schema="ops"
    )


def downgrade() -> None:
    op.execute(DROP_THE_NAME_CONSTRAINT)
    op.create_check_constraint(
        "control_run_name",
        "control_run",
        WITHOUT_ENTITY_RESOLUTION,
        schema="ops",
        postgresql_not_valid=True,
    )
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
