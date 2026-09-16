"""What an agent produced gets a table: one row per artifact, pointing at bytes in the object store.

`brain.console.agent_output` built `Artifact` and `record` and nothing stored one, so
`brain.artifact_routes` answered every reader that no store of those records was attached. This
migration is the store's table. `brain.tables.artifact` holds the argument for the columns, and
`brain.ops.artifact_store` is the one writer: it puts the bytes first and records the row second.

**One table, SELECT and INSERT only.** An artifact is the evidence for something somebody was
told, so a row is never edited and never removed from here, which is
`brain.console.agent_output.SUPERSEDING_KEEPS_THE_ANSWER_EXPLAINABLE_AND_DELETING_DOES_NOT`.

**Read by the application whole, written only in the name of the person it was produced for.**
Who may know an artifact exists is `brain.console.agent_output.may_see`'s decision, applied by
`brain.console.govern_estate.artifact_estate` to every row the screen reads, so the select policy
admits every row, which is `0052`'s and `0056`'s shape for a table the console narrows. The insert
policy admits a row whose `caller_id` is the session's principal, so a run cannot record an
artifact as produced for somebody else, and a session with no principal set admits nothing.

**No ledger entry.** Producing an artifact changes nobody's access, and the audit ledger records
changes to what somebody may do; `brain.audit.ledger.AuditAction` has no member for it and this
migration adds none. An artifact leaving the system is a publish, and nothing here publishes.

**The downgrade drops the table**, and the policies and grant go with it. The bytes it pointed at
stay in the bucket, because a migration does not reach the object store.

Task ids: M39.5.1.1, M39.5.1.2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None

TABLES: tuple[str, ...] = ("agent.artifact",)

PRINCIPAL_ID_CHARS = 128

ARTIFACT_ID_PATTERN = r"^[0-9a-f]{32}$"
OBJECT_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}/artifacts/[a-z_]{1,32}/[0-9a-f]{32}$"
ENT_HASH_PATTERN = r"^[0-9a-f]{32}$"
DIGEST_PATTERN = r"^[0-9a-f]{64}$"

#: `brain.console.agent_output.ArtifactKind`, copied for `0009`'s reason and held by the test.
KINDS = "kind IN ('deck', 'document', 'export', 'image', 'report')"
#: `brain.ops.retention.DataClass`, copied likewise.
DATA_CLASSES = (
    "data_class IN ('audit', 'backup', 'business_record', 'derived', 'export', 'learned', "
    "'metadata_ledger', 'payload', 'recording', 'trace')"
)

PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.artifact ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY artifact_readable ON agent.artifact
        FOR SELECT TO brain_app
        USING (true)
    """,
    f"""
    CREATE POLICY artifact_recorded_for_the_sessions_principal ON agent.artifact
        FOR INSERT TO brain_app
        WITH CHECK (caller_id = {PRINCIPAL})
    """,
)

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON agent.artifact TO brain_app",)


def upgrade() -> None:
    op.create_table(
        "artifact",
        sa.Column("artifact_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("agent_version", sa.String(64), nullable=False),
        sa.Column("caller_id", sa.String(PRINCIPAL_ID_CHARS), nullable=False),
        sa.Column("entitlement_hash", sa.String(32), nullable=False),
        sa.Column("produced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_class", sa.String(32), nullable=False),
        sa.Column("bytes_stored", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(256), nullable=False),
        sa.Column(
            "sources",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "knowledge_items",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.CheckConstraint(f"artifact_id ~ '{ARTIFACT_ID_PATTERN}'", name="artifact_id_shape"),
        sa.CheckConstraint(KINDS, name="kind"),
        sa.CheckConstraint(DATA_CLASSES, name="data_class"),
        sa.CheckConstraint(
            "length(btrim(agent_id)) > 0 AND length(btrim(run_id)) > 0 "
            "AND length(btrim(caller_id)) > 0 AND length(btrim(agent_version)) > 0",
            name="attributed",
        ),
        sa.CheckConstraint(f"entitlement_hash ~ '{ENT_HASH_PATTERN}'", name="ent_hash_shape"),
        sa.CheckConstraint(f"content_digest ~ '{DIGEST_PATTERN}'", name="digest_shape"),
        sa.CheckConstraint(f"object_key ~ '{OBJECT_KEY_PATTERN}'", name="object_key_shape"),
        sa.CheckConstraint("bytes_stored > 0", name="holds_bytes"),
        schema="agent",
    )
    op.create_index(
        "ix_artifact_caller_produced",
        "artifact",
        ["caller_id", "produced_at"],
        schema="agent",
    )
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policies, the grant and the index go with the table.
    op.drop_table("artifact", schema="agent")
