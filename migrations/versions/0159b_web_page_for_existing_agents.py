"""Every agent that existed before channels answers on the web page, switched on with its reason.

`0159` built `agent.channel_switch`, and an agent no switch names answers nowhere. Every agent on
an install before it answered on the web page, so without this upgrade every one of them would go
quiet at once. This writes one switch per agent that exists when it runs, turning the web page
(`console`) on, with the migration as its actor and the reason
`answered_on_the_web_before_channels_existed`, so `0159`'s trigger puts each on the ledger and
nothing is switched on silently.

**Only the web page.** It is the one channel every agent was reachable on through the product's
own screens. A chat an agent was answered in by a leading mention is switched on by the connector
administrator, which is the requirement: an agent answers only where somebody switched it on.

**Every agent, archived ones included.** A row for an archived agent changes nothing, since the
roster leaves it out, and one that is later brought back answers where it did before.

**A migration of its own because it changes data.** `brain.ops.migration_policy` refuses a schema
change and a data change in one migration, because the schema half reverses and the data half
usually cannot. This half does reverse: the downgrade deletes the rows it wrote and no others, and
the ledger entries they made stay, as every downgrade here leaves the ledger.

Task ids: M39.2.4.1

Revision ID: 0159b
Revises: 0159
"""

from __future__ import annotations

from alembic import op

revision = "0159b"
down_revision = "0159"
branch_labels = None
depends_on = None

#: The backfill's own words: who, why and the channel every agent was already reachable on. Held
#: equal to `brain.tables.channel_switch` by `tests/unit/test_channel_switch_store.py`.
BACKFILL_ACTOR = "migration.0159b"
BACKFILL_REASON = "answered_on_the_web_before_channels_existed"
WEB = "console"

#: The web page switched on for every agent there is, one row each. Written out rather than
#: formatted, and held to the three constants above by `upgrade`.
BACKFILL = """
    INSERT INTO agent.channel_switch
        (id, agent_id, channel, switched_on, changed_by, reason_code, entitlement_hash, trace_id)
    SELECT gen_random_uuid(), a.id, 'console', true, 'migration.0159b',
           'answered_on_the_web_before_channels_existed', repeat('0', 32), 'migration.0159b'
    FROM agent.agent a
    ORDER BY a.id
"""

#: The rows this migration wrote and no others.
UNDONE = """
    DELETE FROM agent.channel_switch
    WHERE changed_by = 'migration.0159b'
      AND reason_code = 'answered_on_the_web_before_channels_existed'
"""


def upgrade() -> None:
    assert all(f"'{word}'" in BACKFILL for word in (WEB, BACKFILL_ACTOR, BACKFILL_REASON))
    op.execute(BACKFILL)


def downgrade() -> None:
    assert all(f"'{word}'" in UNDONE for word in (BACKFILL_ACTOR, BACKFILL_REASON))
    op.execute(UNDONE)
