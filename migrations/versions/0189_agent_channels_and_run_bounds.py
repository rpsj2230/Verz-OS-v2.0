"""An agent answers only on the channels enabled for it, and a run's two bounds have a column each.

**`agent.agent.channels`** holds the channels an administrator switched an agent on for (M13.7.4).
`brain.gate.roster.answer_roster` leaves an agent out of a request's roster when the request's
channel is not among them, so naming it there finds what a name nobody created finds. A new agent
gets the channels the person making it ticked, and none when they ticked none.

**Every existing agent is backfilled with every channel it could be asked on before this release**,
which is what the coordinator decided: nobody's agent goes quiet on upgrade. `ASKING_CHANNELS` below
is that list as it stood the day this was written, kept as data rather than imported because a
migration says what it did on the day it ran; `tests/unit/test_migration_0189.py` holds it equal to
`brain.agents.model.ASKING_CHANNELS`, which derives the same list from `brain.gate.context.Channel`,
so the two cannot have disagreed when this shipped. Only a row still holding the empty default is
backfilled, so running this against a partly migrated install changes nothing it did before, and an
agent somebody has since narrowed is left as they left it.

**`agent.manifest_act.channels`** carries what a builder's author ticked from the publish request to
the publish, because a publish that needs a second person is approved later by somebody else, and
the approval has to publish what the author asked for. Existing acts get none: they are history, and
a new agent's act written before this release published an agent that this migration's backfill
already enabled.

**`agent.agent.max_turns` and `max_tool_calls`** bound one run (M13.7.2). NULL is the product's
default, which the runtime holds; a number is a steward's bound, at least one and at most the cap
`brain.agents.model` names, checked here for a row that arrived some other way.

The downgrade drops the four columns.

Task ids: M13.7.4, M13.7.2

Revision ID: 0189
Revises: 0187
"""

from __future__ import annotations

from alembic import op

revision = "0189"
# This branch's head when this was written. The coordinator re-points it at 0188 on merge; nothing
# here depends on 0188, and the migration's test steps down to whatever this names.
down_revision = "0187"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

#: Every channel a question could reach an agent's roster on, the day this ran. See the module
#: docstring and `brain.agents.model.ASKING_CHANNELS_ARE_EVERY_ROUTE_TO_THE_ROSTER`.
ASKING_CHANNELS: tuple[str, ...] = (
    "console",
    "lark",
    "whatsapp",
    "email",
    "telegram",
    "api",
    "webhook",
    "widget",
    "slack",
    "teams",
)

#: Copied for the reason `0009` gives about reading live code from a migration, and held equal to
#: `brain.agents.model` and `brain.tables.agent` by the migration's test.
CHANNEL_CHARS = 32
MAX_TURNS_CAP = 50
MAX_TOOL_CALLS_CAP = 200


def _between(column: str, cap: int) -> str:
    return f"{column} IS NULL OR ({column} >= 1 AND {column} <= {cap})"


ADD_AGENT_COLUMNS = f"""
ALTER TABLE agent.agent
    ADD COLUMN channels varchar({CHANNEL_CHARS})[] NOT NULL DEFAULT '{{}}',
    ADD COLUMN max_turns integer,
    ADD COLUMN max_tool_calls integer,
    ADD CONSTRAINT ck_agent_max_turns_in_range CHECK ({_between("max_turns", MAX_TURNS_CAP)}),
    ADD CONSTRAINT ck_agent_max_tool_calls_in_range
        CHECK ({_between("max_tool_calls", MAX_TOOL_CALLS_CAP)})
"""

ADD_ACT_COLUMN = f"""
ALTER TABLE agent.manifest_act
    ADD COLUMN channels varchar({CHANNEL_CHARS})[] NOT NULL DEFAULT '{{}}'
"""

#: The backfill. Only a row on the empty default, so a second run writes nothing new.
BACKFILL = "UPDATE agent.agent SET channels = ARRAY[{}]::varchar[] WHERE channels = '{{}}'".format(
    ", ".join(f"'{one}'" for one in ASKING_CHANNELS)
)


def upgrade() -> None:
    op.execute(ADD_AGENT_COLUMNS)
    op.execute(ADD_ACT_COLUMN)
    op.execute(BACKFILL)


def downgrade() -> None:
    op.execute("ALTER TABLE agent.manifest_act DROP COLUMN channels")
    op.execute(
        "ALTER TABLE agent.agent DROP CONSTRAINT ck_agent_max_tool_calls_in_range, "
        "DROP CONSTRAINT ck_agent_max_turns_in_range, DROP COLUMN max_tool_calls, "
        "DROP COLUMN max_turns, DROP COLUMN channels"
    )
