"""How often an agent's answers cited each document, by day, and nothing about who asked.

One table, `ops.agent_item_use`, behind the `agent_item_counts` feature that ships off.
`brain.tables.agent_item_use` argues the absences: no question, no person, no passage, only an
agent, a document, a day and a count of answers.

**Read by the application with `USING (true)`**, for `0193`'s reason: a row names nobody and no
words, so there is nothing in one a reader could be refused, and the route that reads it
(`brain.agent_knowledge_routes`) asks only for documents the reader may already open. **Inserted at
one, and only ever grown by one**: the insert policy holds a new row to a count of one, the update
policy holds the new count to the old one's successor, and `brain_app` may update `uses` alone.
Never DELETE: a count an old answer was explained by stays.

**The downgrade** drops the table; its policy and grants go with it. What it held is a report and
is counted again from the next answer.

Task ids: M39.2.3.5

Revision ID: 0213
Revises: 0212
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0213"
down_revision = "0212"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice. Points at
#: nothing: the agent and the document are values.
TABLES: tuple[str, ...] = ("ops.agent_item_use",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason and held equal to `brain.tables.agent_item_use` by
#: `tests/unit/test_agent_item_use.py`.
AGENT_ID_CHARS = 128
ITEM_ID_CHARS = 128

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.agent_item_use ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY agent_item_use_readable ON ops.agent_item_use
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY agent_item_use_first_of_the_day ON ops.agent_item_use
        FOR INSERT TO brain_app
        WITH CHECK (uses = 1)
    """,
    """
    CREATE POLICY agent_item_use_one_more ON ops.agent_item_use
        FOR UPDATE TO brain_app
        USING (true)
        WITH CHECK (uses >= 2)
    """,
)

#: SELECT and INSERT, and UPDATE of `uses` alone. Never DELETE.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON ops.agent_item_use TO brain_app",
    "GRANT UPDATE (uses) ON ops.agent_item_use TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "agent_item_use",
        sa.Column("agent_id", sa.String(AGENT_ID_CHARS), nullable=False),
        sa.Column("item_id", sa.String(ITEM_ID_CHARS), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("uses", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.PrimaryKeyConstraint("agent_id", "item_id", "day"),
        sa.CheckConstraint("uses >= 1", name="used_at_least_once"),
        sa.CheckConstraint("length(btrim(agent_id)) > 0", name="agent_present"),
        sa.CheckConstraint("length(btrim(item_id)) > 0", name="item_present"),
        schema="ops",
    )
    op.create_index("ix_agent_item_use_day", "agent_item_use", ["agent_id", "day"], schema="ops")

    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_index("ix_agent_item_use_day", table_name="agent_item_use", schema="ops")
    # The policies and the grants go with the table.
    op.drop_table("agent_item_use", schema="ops")
