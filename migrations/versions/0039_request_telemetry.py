"""The metadata ledger gets a table, partitioned by arrival, with row-level security on.

`brain.tables.telemetry` holds the argument for the shape: it is
`brain.ops.telemetry.RequestTelemetry.ledger_row` column for column plus a surrogate id, in
`obs`, partitioned by range on `received_at`. What is here is the table, its default partition,
its read and append policies, and its grants.

**`USING (true)` on the read, for the reason `0034` gives about `ops.spend_actual` and `0038`
repeats.** Who may read a service level reading is not a row predicate: the rows carry no
department and the reading built from them carries no principal, and a predicate written here
would be a second implementation of a reader rule that belongs to a screen. No screen reads this
table yet, which `brain.ops.service_levels` states.

**SELECT and INSERT, and no UPDATE or DELETE.** How a request went does not change after it
finished. A period leaves the ledger when its partition is detached and dropped, which is
`brain.ops.partitioning`'s scheme and M36.1.1.1's executor, and granting DELETE ahead of that
would be a second way out of a table whose retention is decided by the partition.

**The default partition has row-level security enabled and no grant and no policy.** Rows
written through the parent land in it, and a policy on the parent governs every read through the
parent. Enabled on the child as well because a partition is a table in its own right: anything
granted on it later would reach rows with no policy in the way, and the `rls` sweep reads every
ordinary table in `obs`. Named `request_telemetry_default`, which is pg_partman's own naming for
a default child. That has not been checked against pg_partman, which is not installed.

**Nothing for the fast lane role.** It answers from the local projection and has no business
reading how anybody else's requests went.

The downgrade is real, discards every recorded request, and takes the default partition with the
parent.

Task ids: M30.5.2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice. The default
#: partition is not here: it is not a model, and the package tuple mirrors the models.
TABLES: tuple[str, ...] = ("obs.request_telemetry",)

APP_ROLE = "brain_app"

DEFAULT_PARTITION = "obs.request_telemetry_default"

PARTITIONS: tuple[str, ...] = (
    f"CREATE TABLE {DEFAULT_PARTITION} PARTITION OF obs.request_telemetry DEFAULT",
)

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON obs.request_telemetry TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE obs.request_telemetry ENABLE ROW LEVEL SECURITY",
    f"ALTER TABLE {DEFAULT_PARTITION} ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY request_telemetry_readable ON obs.request_telemetry
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY request_telemetry_appendable ON obs.request_telemetry
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)

#: The counts and the optional durations, each refused below zero and allowed to be absent.
NOT_NEGATIVE: tuple[str, ...] = (
    "tokens_in",
    "tokens_out",
    "tool_count",
    "redaction_count",
    "fallback_count",
    "retry_count",
    "time_to_first_token_ms",
    "tool_latency_ms",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "request_telemetry",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("traffic_class", sa.String(24), nullable=False),
        sa.Column("principal", sa.String(128), nullable=False),
        sa.Column("agent_version", sa.String(120)),
        sa.Column("policy_epoch", sa.String(120)),
        sa.Column("entitlement_hash", sa.String(32), nullable=False),
        sa.Column("lane", sa.String(8), nullable=False),
        sa.Column("model", sa.String(120)),
        sa.Column("provider", sa.String(120)),
        sa.Column("time_to_first_token_ms", sa.Float()),
        sa.Column("tokens_in", sa.Integer()),
        sa.Column("tokens_out", sa.Integer()),
        sa.Column("tool_count", sa.Integer()),
        sa.Column("tool_latency_ms", sa.Float()),
        sa.Column("connector", sa.String(120)),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("redaction_count", sa.Integer()),
        sa.Column("fallback_count", sa.Integer()),
        sa.Column("retry_count", sa.Integer()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "traffic_class IN ('automation', 'human_async', 'human_interactive', 'system')",
            name="traffic_class",
        ),
        sa.CheckConstraint("lane IN ('answer', 'fast', 'task')", name="lane"),
        sa.CheckConstraint(
            "status IN ('answered', 'degraded', 'failed', 'nothing_returned', 'unresolved')",
            name="status",
        ),
        sa.CheckConstraint(r"entitlement_hash ~ '^[0-9a-f]{32}$'", name="ent_hash_shape"),
        sa.CheckConstraint("length(btrim(trace_id)) >= 1", name="trace_present"),
        sa.CheckConstraint("length(btrim(principal)) >= 1", name="principal_present"),
        sa.CheckConstraint("duration_ms >= 0", name="duration_not_negative"),
        *(
            sa.CheckConstraint(f"{one} IS NULL OR {one} >= 0", name=f"{one}_not_negative")
            for one in NOT_NEGATIVE
        ),
        schema="obs",
        postgresql_partition_by="RANGE (received_at)",
    )
    op.create_index(
        "ix_request_telemetry_received_at", "request_telemetry", ["received_at"], schema="obs"
    )
    op.create_index(
        "ix_request_telemetry_trace_id", "request_telemetry", ["trace_id"], schema="obs"
    )
    for statement in PARTITIONS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The default partition, the indexes and the policies go with the parent.
    op.drop_table("request_telemetry", schema="obs")
