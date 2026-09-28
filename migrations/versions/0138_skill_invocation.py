"""Each skill a run used is recorded, by digest, with the request, the person, the agent and when.

**`agent.skill_invocation` is new** (M27.15.9, M39.2.2.4): one row for each skill whose card a
run offered to a model, written when that run's request finishes by
`brain.ops.usage_store.UsageRecorder`. `brain.tables.skill_invocation` argues the shape: the digest
rather than the name, the person so a count is taken at the reader's own basis, and one row per
skill per finished request, which the unique key on the trace, the instant and the digest holds.

**SELECT and INSERT, and no UPDATE or DELETE**: a use that happened is not edited, and an erasure
keeps these rows and reports them kept. **`USING (true)`**: the readers are the stats routes, which
put the reader's basis in their WHERE clause, and the one writer is the recorder, which writes what
the lane measured.

**Nothing here touches `ops.spend_actual`.** A cost is written once by the same recorder, but a
unique index on that table's existing trace column would narrow what the previous release may
insert, which `brain.deployment.compatibility` refuses, and a caller may propose its own trace id,
so a key on the trace alone would drop a second request's cost. The recorder holds a cost to one
row per request under a lock instead; see `brain.ops.usage_store`.

**The downgrade** drops the table and every use recorded in it, which is the state before this
release: nothing was recorded.

Task ids: M27.15.9, M39.2.2.4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0138"
# The head of origin/main when this was written. The queue ahead of it holds 0118, 0133, 0136 and
# 0137, and whoever lands this after them re-points it at the newest.
down_revision = "0120"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("agent.skill_invocation",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.skill_invocation` by `tests/unit/test_usage_store.py`.
TRACE_ID_CHARS = 64
PRINCIPAL_ID_CHARS = 128
AGENT_ID_CHARS = 128
NAME_CHARS = 80
DIGEST_CHARS = 64
DIGEST_PATTERN = "^[0-9a-f]{64}$"

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON agent.skill_invocation TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE agent.skill_invocation ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY skill_invocation_readable ON agent.skill_invocation
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY skill_invocation_recordable ON agent.skill_invocation
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    op.create_table(
        "skill_invocation",
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
        sa.Column("skill_name", sa.String(NAME_CHARS), nullable=False),
        sa.Column("digest", sa.String(DIGEST_CHARS), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"digest ~ '{DIGEST_PATTERN}'", name="digest_shape"),
        sa.CheckConstraint("length(btrim(trace_id)) >= 1", name="trace_present"),
        sa.CheckConstraint("length(btrim(principal_id)) >= 1", name="principal_present"),
        sa.CheckConstraint("length(btrim(agent_id)) >= 1", name="agent_present"),
        sa.CheckConstraint("length(btrim(skill_name)) >= 1", name="skill_name_present"),
        sa.UniqueConstraint("trace_id", "used_at", "digest"),
        schema="agent",
    )
    op.create_index(
        "ix_skill_invocation_skill_used_at",
        "skill_invocation",
        ["skill_name", "used_at"],
        schema="agent",
    )
    op.create_index(
        "ix_skill_invocation_agent_used_at",
        "skill_invocation",
        ["agent_id", "used_at"],
        schema="agent",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The indexes, the policies and the grant go with the table.
    op.drop_table("skill_invocation", schema="agent")
