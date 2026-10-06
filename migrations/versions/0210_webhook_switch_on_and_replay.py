"""A webhook subscriber can be switched back on and an exhausted delivery replayed once, recorded.

Until now `ops.webhook_change` had three words (registered, secret replaced, switched off) and
`ops.webhook_subscriber`'s update policy let a row change only while it was switched on, so the
Webhooks screen drew "Switch back on" and "Replay" as controls with nothing behind them (M27.15.44).
This is the schema half, and every change is a widening.

**Two more words, each recorded by the trigger `0059` already put on the table.** `switched_on`,
and `replayed`, which names the delivery it put back by its event id. The change constraint is
widened to five, and the secret's constraint (under the name it has always had, so the gate can
read what it replaced) is restated so only a registration and a replacement write a secret.
**A replay names its delivery, and one delivery is replayed once**: two checks hold `event_id`
present exactly on a replay (each readable by the compatibility gate, which cannot order an
equality), and a partial unique index on the subscriber and the event over replays refuses a second.

**Two more update policies, each one direction only.** A switched-off subscriber may be switched
back on, and only that: `USING (deactivated_at IS NOT NULL) WITH CHECK (deactivated_at IS NULL)`.
An exhausted delivery may be put back to pending, and only that: `USING (state = 'exhausted')
WITH CHECK (state = 'pending')`. The policies a subscriber and a delivery already had are
unchanged, so nothing that was refused before is allowed except these two moves.

The downgrade drops what this adds and restores the two old constraints `NOT VALID`, which
`0030` argues for its own: a change recorded under a word the old constraint does not know is
history, and refusing to downgrade over it, or deleting it, would both be worse.

Task ids: M27.15.44

Revision ID: 0210
Revises: 0189
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0210"
# main's head at the time of writing. Re-pointed at whichever migration is the head when it lands.
down_revision = "0207"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. This migration creates no table.
TABLES: tuple[str, ...] = ()

#: `brain.ops.outbox.MAX_IDENTIFIER_CHARS`, copied for the reason `0009` gives.
IDENTIFIER_CHARS = 128

#: `brain.tables.webhook_change.WebhookChange`, sorted as `one_of` sorts, before and after.
CHANGE_BEFORE = "change IN ('registered', 'secret_replaced', 'switched_off')"
CHANGE_AFTER = (
    "change IN ('registered', 'replayed', 'secret_replaced', 'switched_off', 'switched_on')"
)

#: Which changes write a signing secret, before and after.
WRITES_BEFORE = "change <> 'switched_off' OR secret_written_at IS NULL"
WRITES_AFTER = "change IN ('registered', 'secret_replaced') OR secret_written_at IS NULL"

#: A replay names its delivery, and nothing else does. Two checks rather than one equality, so the
#: compatibility gate can read each: the first binds only a word the old constraint refused, the
#: second only a column the previous release never writes.
REPLAY_NAMES_ITS_DELIVERY = "change <> 'replayed' OR event_id IS NOT NULL"
ONLY_A_REPLAY_NAMES_A_DELIVERY = "event_id IS NULL OR change = 'replayed'"

#: The secret constraint keeps the name it has always had, so the downgrade restoring it is how
#: the gate knows what it replaced. The name says "a switch off"; it now holds for both new words.
CONSTRAINT_ON_SECRETS = "a_switch_off_writes_no_secret"


#: Drops a check on `ops.webhook_change` by whichever name it has, matched on its suffix, for the
#: reason `0030` gives about a constraint whose name an earlier migration may have prefixed twice.
DROP_BY_SUFFIX = """
DO $$
DECLARE
    v_name text;
BEGIN
    FOR v_name IN
        SELECT c.conname FROM pg_constraint c
         WHERE c.conrelid = 'ops.webhook_change'::regclass
           AND c.contype = 'c'
           AND right(c.conname, LENGTH) = 'SUFFIX'
    LOOP
        EXECUTE 'ALTER TABLE ops.webhook_change DROP CONSTRAINT ' || quote_ident(v_name);
    END LOOP;
END
$$
"""


def _drop_by_suffix(suffix: str) -> str:
    """`DROP_BY_SUFFIX` for one suffix. Every suffix passed is one of this module's literals."""
    return DROP_BY_SUFFIX.replace("LENGTH", str(len(suffix))).replace("SUFFIX", suffix)


POLICIES: tuple[str, ...] = (
    """
    CREATE POLICY webhook_subscriber_reactivatable ON ops.webhook_subscriber
        FOR UPDATE TO brain_app
        USING (deactivated_at IS NOT NULL)
        WITH CHECK (deactivated_at IS NULL)
    """,
    """
    CREATE POLICY outbox_delivery_replayable ON ops.outbox_delivery
        FOR UPDATE TO brain_app
        USING (state = 'exhausted')
        WITH CHECK (state = 'pending')
    """,
)


def upgrade() -> None:
    op.add_column(
        "webhook_change",
        sa.Column("event_id", sa.String(IDENTIFIER_CHARS), nullable=True),
        schema="ops",
    )
    op.execute(_drop_by_suffix("_change"))
    op.create_check_constraint("change", "webhook_change", CHANGE_AFTER, schema="ops")
    op.execute(_drop_by_suffix(CONSTRAINT_ON_SECRETS))
    op.create_check_constraint(CONSTRAINT_ON_SECRETS, "webhook_change", WRITES_AFTER, schema="ops")
    op.create_check_constraint(
        "a_replay_names_its_delivery", "webhook_change", REPLAY_NAMES_ITS_DELIVERY, schema="ops"
    )
    op.create_check_constraint(
        "only_a_replay_names_a_delivery",
        "webhook_change",
        ONLY_A_REPLAY_NAMES_A_DELIVERY,
        schema="ops",
    )
    op.create_index(
        "uq_webhook_change_one_replay",
        "webhook_change",
        ["subscriber_id", "event_id"],
        unique=True,
        schema="ops",
        postgresql_where="change = 'replayed'",
    )
    for statement in POLICIES:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP POLICY outbox_delivery_replayable ON ops.outbox_delivery")
    op.execute("DROP POLICY webhook_subscriber_reactivatable ON ops.webhook_subscriber")
    op.drop_index("uq_webhook_change_one_replay", table_name="webhook_change", schema="ops")
    op.execute(_drop_by_suffix("only_a_replay_names_a_delivery"))
    op.execute(_drop_by_suffix("a_replay_names_its_delivery"))
    op.execute(_drop_by_suffix(CONSTRAINT_ON_SECRETS))
    op.create_check_constraint(
        CONSTRAINT_ON_SECRETS,
        "webhook_change",
        WRITES_BEFORE,
        schema="ops",
        postgresql_not_valid=True,
    )
    op.execute(_drop_by_suffix("_change"))
    op.create_check_constraint(
        "change", "webhook_change", CHANGE_BEFORE, schema="ops", postgresql_not_valid=True
    )
    op.drop_column("webhook_change", "event_id", schema="ops")
