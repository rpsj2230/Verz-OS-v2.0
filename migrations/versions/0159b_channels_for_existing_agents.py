"""Every agent that existed before channels keeps answering everywhere it answered, with its reason.

`0159` built `agent.channel_switch`, and an agent no switch names answers nowhere. Before it, every
agent answered wherever it could be addressed, so without this upgrade every one of them would go
quiet at once on every surface. **Nothing that answers today stops answering, on any install**: this
writes one switch per agent that exists when it runs and per channel it could be reached on then,
with the migration as its actor and the reason `answered_here_before_channels_existed`, so `0159`'s
trigger puts each on the ledger and nothing is switched on silently.

**Where an agent could be reached before this, which is what is switched on:**

- **The web page** (`console`), for every agent: every signed-in person could name any agent they
  may use on the Ask page.
- **Every chat this install has connected and this release receives on**, for every agent: a
  message there opening with `@agent_id` reached that agent through `brain.gate.addressing.
  from_mention`. Connected is a row in `ops.channel`, on or off, because a channel switched off
  today answers as it did the moment it is switched back on, and this must not change that.
  `RECEIVING_CHANNELS` is the channels this release has a wire for, held to
  `brain.channels.adapter.channel_wires` by `tests/unit/test_channel_switch_store.py`; a channel
  with no wire never delivered a message to anybody, so there is nothing there to keep.
- **The API**, for every agent, on an install that has a service account that is not retired: a
  caller with no session asks `/answer` on `Channel.API` and could name an agent.

Nothing else. A surface nothing could reach an agent through (a widget, email, a scheduler) had no
answer to keep, and switching it on here would be the on-every-channel default the owner refused.
An agent created after this has the web page switched on by whoever makes it, unless they untick
it, and any other channel by the connector administrator.

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

#: The backfill's own words: who and why. Held equal to `brain.tables.channel_switch` by
#: `tests/unit/test_channel_switch_store.py`.
BACKFILL_ACTOR = "migration.0159b"
BACKFILL_REASON = "answered_here_before_channels_existed"
WEB = "console"
API = "api"

#: The channels this release receives a message on and reads a leading mention in. Written out
#: rather than imported, for the reason `0009` gives about a migration reading application code.
RECEIVING_CHANNELS: tuple[str, ...] = ("lark", "webhook")

#: One switch per agent and per channel it could be reached on. Written out rather than formatted,
#: and held to the constants above by `upgrade`.
BACKFILL = """
    INSERT INTO agent.channel_switch
        (id, agent_id, channel, switched_on, changed_by, reason_code, entitlement_hash, trace_id)
    SELECT gen_random_uuid(), a.id, reached.channel, true, 'migration.0159b',
           'answered_here_before_channels_existed', repeat('0', 32), 'migration.0159b'
    FROM agent.agent a
    CROSS JOIN (
        SELECT 'console'::text AS channel
        UNION
        SELECT c.channel::text FROM ops.channel c WHERE c.channel IN ('lark', 'webhook')
        UNION
        SELECT 'api'::text
        WHERE EXISTS (SELECT 1 FROM auth.service_account s WHERE s.deleted_at IS NULL)
    ) AS reached
    ORDER BY a.id, reached.channel
"""

#: The rows this migration wrote and no others.
UNDONE = """
    DELETE FROM agent.channel_switch
    WHERE changed_by = 'migration.0159b'
      AND reason_code = 'answered_here_before_channels_existed'
"""


def upgrade() -> None:
    assert all(f"'{word}'" in BACKFILL for word in (WEB, API, BACKFILL_ACTOR, BACKFILL_REASON))
    assert f"IN ({', '.join(repr(one) for one in RECEIVING_CHANNELS)})" in BACKFILL
    op.execute(BACKFILL)


def downgrade() -> None:
    assert all(f"'{word}'" in UNDONE for word in (BACKFILL_ACTOR, BACKFILL_REASON))
    op.execute(UNDONE)
