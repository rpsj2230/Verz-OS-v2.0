"""Provider health rings, chain-depth alerts, and residency constraints attached to a scope.

**`ops.provider_health`** (M5.4.3): one row per deployment, a live ring the executor appends to
after every attempt that answered or failed on the provider's side, and a probe ring the worker's
prober appends to. Both are jsonb arrays of `{"ok", "at"}`, capped by checks at the windows
`brain.models.health` reads (twenty live, ten probe), and appended by `ops.ring_push` inside one
`UPDATE`, so concurrent appends each land. `brain.tables.model_health` argues the shape.

**`ops.chain_depth_alert`** (M5.4.8): one row per alert the live path raised, append-only: SELECT
and INSERT, no UPDATE or DELETE, because an alert that can be edited is a record of what somebody
later thought happened.

**`ops.residency_constraint`** (M5.5.1): a `Scope` and the regions its requests may be processed in,
retired by `deleted_at` and never deleted, with the policies `0097` gives `ops.model_provider`.

**`ops.ring_push`** appends one entry and keeps the newest `cap`. `IMMUTABLE` and pure SQL: it reads
no table, so it needs no privilege beyond the default `EXECUTE` every role has on a function.

**The worker writes the two health tables as the login**, which owns them, so it needs no grant
here; `brain_app` is granted what the executor and the Models screen use.

**The downgrade** drops the three tables and the function, which is the state before this release:
nothing was stored. No check is re-created, so nothing is narrowed on rows already written.

Task ids: M5.4.3, M5.4.8, M5.5.1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0108"
# The newest migration on origin/main when this was written.
down_revision = "0109"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = (
    "ops.provider_health",
    "ops.chain_depth_alert",
    "ops.residency_constraint",
)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.model_health` and `brain.models.evidence` by
#: `tests/unit/test_model_health_store.py`.
DEPLOYMENT_ID_CHARS = 120
PROVIDER_CHARS = 60
TRACE_ID_CHARS = 64
TRACE_ID = r"^[A-Za-z0-9_.-]{1,64}$"
REASON_CHARS = 600
NOTE_CHARS = 500
PERSON_CHARS = 128
LIVE_RING_CAP = 20
PROBE_RING_CAP = 10
LEVELS = "level IN ('critical', 'warning')"
TIERS = "tier IN ('heavy', 'main', 'none', 'small')"
SCOPE_SHAPE = "jsonb_typeof(scope) = 'object' AND jsonb_typeof(scope -> 'clauses') = 'array'"

RING_PUSH = """
CREATE FUNCTION ops.ring_push(ring jsonb, entry jsonb, cap integer) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $$
    SELECT COALESCE(jsonb_agg(t.e ORDER BY t.i), '[]'::jsonb)
    FROM jsonb_array_elements(COALESCE(ring, '[]'::jsonb) || jsonb_build_array(entry))
        WITH ORDINALITY AS t(e, i)
    WHERE t.i > jsonb_array_length(COALESCE(ring, '[]'::jsonb)) + 1 - cap
$$
"""

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON ops.provider_health TO brain_app",
    "GRANT SELECT, INSERT ON ops.chain_depth_alert TO brain_app",
    "GRANT SELECT, INSERT, UPDATE ON ops.residency_constraint TO brain_app",
)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.provider_health ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY provider_health_readable ON ops.provider_health
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY provider_health_insertable ON ops.provider_health
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    """
    CREATE POLICY provider_health_updatable ON ops.provider_health
        FOR UPDATE TO brain_app
        USING (true)
        WITH CHECK (true)
    """,
    "ALTER TABLE ops.chain_depth_alert ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY chain_depth_alert_readable ON ops.chain_depth_alert
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY chain_depth_alert_recordable ON ops.chain_depth_alert
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    "ALTER TABLE ops.residency_constraint ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY residency_constraint_live ON ops.residency_constraint
        FOR SELECT TO brain_app
        USING (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
    """
    CREATE POLICY residency_constraint_insertable ON ops.residency_constraint
        FOR INSERT TO brain_app
        WITH CHECK (deleted_at IS NULL)
    """,
    """
    CREATE POLICY residency_constraint_updatable ON ops.residency_constraint
        FOR UPDATE TO brain_app
        USING (deleted_at IS NULL)
        WITH CHECK (deleted_at IS NULL OR deleted_at = statement_timestamp())
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    op.execute(RING_PUSH)
    op.create_table(
        "provider_health",
        sa.Column(
            "deployment_id", sa.String(DEPLOYMENT_ID_CHARS), primary_key=True, nullable=False
        ),
        sa.Column("provider", sa.String(PROVIDER_CHARS), nullable=False),
        sa.Column("live", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("probe", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("last_live_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("jsonb_typeof(live) = 'array'", name="live_array"),
        sa.CheckConstraint("jsonb_typeof(probe) = 'array'", name="probe_array"),
        sa.CheckConstraint(f"jsonb_array_length(live) <= {LIVE_RING_CAP}", name="live_capped"),
        sa.CheckConstraint(f"jsonb_array_length(probe) <= {PROBE_RING_CAP}", name="probe_capped"),
        sa.CheckConstraint("length(btrim(deployment_id)) > 0", name="deployment_present"),
        schema="ops",
    )
    op.create_table(
        "chain_depth_alert",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("trace_id", sa.String(TRACE_ID_CHARS), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("depth", sa.SmallInteger(), nullable=False),
        sa.Column("served_by", sa.String(DEPLOYMENT_ID_CHARS), nullable=True),
        sa.Column("reason", sa.String(REASON_CHARS), nullable=False),
        sa.CheckConstraint(LEVELS, name="level"),
        sa.CheckConstraint(TIERS, name="tier"),
        sa.CheckConstraint("depth >= 1", name="depth_positive"),
        sa.CheckConstraint(f"trace_id ~ '{TRACE_ID}'", name="trace_id_shape"),
        schema="ops",
    )
    op.create_index(
        "ix_ops_chain_depth_alert_raised_at", "chain_depth_alert", ["raised_at"], schema="ops"
    )
    op.create_table(
        "residency_constraint",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("scope", JSONB(), nullable=False),
        sa.Column("allowed_regions", JSONB(), nullable=True),
        sa.Column("on_prem_only", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("note", sa.String(NOTE_CHARS), server_default="", nullable=False),
        sa.Column("created_by", sa.String(PERSON_CHARS), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(SCOPE_SHAPE, name="scope_shape"),
        sa.CheckConstraint(
            "allowed_regions IS NULL OR (jsonb_typeof(allowed_regions) = 'array' "
            "AND jsonb_array_length(allowed_regions) > 0)",
            name="regions_non_empty_array",
        ),
        sa.CheckConstraint("allowed_regions IS NOT NULL OR on_prem_only", name="demands_something"),
        schema="ops",
    )
    op.create_index(
        "ix_ops_residency_constraint_deleted_at",
        "residency_constraint",
        ["deleted_at"],
        schema="ops",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The indexes, the policies and the grants go with the tables.
    op.drop_table("residency_constraint", schema="ops")
    op.drop_table("chain_depth_alert", schema="ops")
    op.drop_table("provider_health", schema="ops")
    op.execute("DROP FUNCTION ops.ring_push(jsonb, jsonb, integer)")
