"""The deployment history: one row per deploy, chained, readable by the Version and updates screen.

`brain.tables.deployment_record` argues the table and `brain.ops.deployments` argues why it is a
chain of its own rather than entries in `obs.audit_entry`. What is here is the table, its checks,
row-level security and the one grant.

**SELECT for `brain_app` and nothing else.** The row is written by the deploy script running
`python -m brain.ops.deployment_store` inside the container, on the database login, which owns the
table and is not subject to its policies. So no request the console serves can add a deploy, edit
one or remove one, and the screen reads with `USING (true)`: a deploy belongs to nobody, and who
may open the screen is `brain.console.screens`' decision about `updates`.

**No trigger into the ledger and no subject kind added.** That is the requirement, not an
omission: the deployment history is kept apart from the permission audit trail and out of the
compliance export, and the cheapest way to keep it out is for nothing to put it in.

The downgrade drops the table; the policy and the grant go with it. The deploys it recorded are
still in the host's `deployments.jsonl`, which is the source this table is derived from, so a
later upgrade reconciles them back.

Task ids: M38.1.3.5

Revision ID: 0091
Revises: 0086
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0091"
# The head of origin/main when this was written. Re-pointed at whichever migration is the head
# when it is integrated: nothing here depends on a table any later migration builds.
down_revision = "0086"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.deployment_record",)

APP_ROLE = "brain_app"

#: Copied for the reason `0009` gives about reading live code from a migration, and held equal to
#: `brain.tables.deployment_record` by `tests/unit/test_tables.py`.
DIGEST_PATTERN = "^[0-9a-f]{64}$"
OUTCOME_IN = (
    "outcome IN ('deployed', 'failed_no_rollback', 'held_back', 'refused', 'rollback_failed', "
    "'rolled_back')"
)

GRANTS: tuple[str, ...] = ("GRANT SELECT ON ops.deployment_record TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.deployment_record ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY deployment_record_readable ON ops.deployment_record
        FOR SELECT TO brain_app
        USING (true)
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all(
        verb not in statement for statement in GRANTS for verb in ("INSERT", "UPDATE", "DELETE")
    )

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "deployment_record",
        sa.Column("seq", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("commit", sa.String(64), nullable=False),
        sa.Column("image", sa.String(255), nullable=False),
        sa.Column("previous", sa.String(255), nullable=False),
        sa.Column(
            "task_ids",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.CheckConstraint("seq >= 0", name="seq_is_not_negative"),
        sa.CheckConstraint(OUTCOME_IN, name="outcome"),
        sa.CheckConstraint(f"prev_hash ~ '{DIGEST_PATTERN}'", name="prev_hash_is_a_digest"),
        sa.CheckConstraint(f"entry_hash ~ '{DIGEST_PATTERN}'", name="entry_hash_is_a_digest"),
        sa.CheckConstraint(f"fingerprint ~ '{DIGEST_PATTERN}'", name="fingerprint_is_a_digest"),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("fingerprint"),
        schema="ops",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The policy and the grant go with the table.
    op.drop_table("deployment_record", schema="ops")
