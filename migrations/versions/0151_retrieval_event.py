"""A retrieval a person was answered from is logged for the learning signal, and nothing else of it.

`brain.knowledge.quality` has held the record and the signal since M15.3.4 was written, and no
table held a record, so the signal was arithmetic over nothing. `ops.retrieval_event` is that
table, column for field of `RetrievalEvent`: which retrievers ran, how many passages the person was
shown, how many of those two retrievers agreed on, where in that list they followed a citation,
and how long it took. `brain.tables.retrieval` argues the absences.

**Read by the application with `USING (true)`**, for `0041`'s reason: a row names no document, no
question and nobody, so there is nothing in one that a reader could be refused, and the route that
reads the signal decides who may see it. **Inserted with no uses**, which the insert policy holds.
**Updated in one column**: `brain_app` is granted UPDATE on `used` alone, and the statement in
`brain.ops.retrieval_store` only ever adds one position inside `returned`; the check constraints
hold the length and the lower bound. Never DELETE: a record the signal was read from stays.

**The downgrade** drops the table; its policies and grants go with it.

Revises `0150`, the head of main when this was written.

Task ids: M15.3.4

Revision ID: 0151
Revises: 0150
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0151"
down_revision = "0150"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.retrieval_event",)

APP_ROLE = "brain_app"

#: `brain.tables.retrieval.RETRIEVERS_PATTERN`, copied for the reason `0009` gives about reading
#: live code from a migration, and held equal to it by `tests/unit/test_tables.py`.
RETRIEVERS_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.retrieval_event ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY retrieval_event_readable ON ops.retrieval_event
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY retrieval_event_logged_unused ON ops.retrieval_event
        FOR INSERT TO brain_app
        WITH CHECK (cardinality(used) = 0)
    """,
    """
    CREATE POLICY retrieval_event_used ON ops.retrieval_event
        FOR UPDATE TO brain_app
        USING (true)
        WITH CHECK (cardinality(used) <= returned)
    """,
)

#: SELECT and INSERT, and UPDATE of `used` alone. Never DELETE.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT ON ops.retrieval_event TO brain_app",
    "GRANT UPDATE (used) ON ops.retrieval_event TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "retrieval_event",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retrievers", sa.String(64), nullable=False),
        sa.Column("returned", sa.Integer(), nullable=False),
        sa.Column("corroborated", sa.Integer(), nullable=False),
        sa.Column(
            "used",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        sa.CheckConstraint(f"retrievers ~ '{RETRIEVERS_PATTERN}'", name="retrievers_are_names"),
        sa.CheckConstraint("returned >= 0", name="returned_is_a_count"),
        sa.CheckConstraint(
            "corroborated >= 0 AND corroborated <= returned", name="corroborated_of_returned"
        ),
        sa.CheckConstraint("cardinality(used) <= returned", name="used_within_returned"),
        sa.CheckConstraint("1 <= ALL(used)", name="used_is_one_based"),
        sa.CheckConstraint("latency_ms >= 0", name="latency_is_a_duration"),
        schema="ops",
    )
    op.create_index("ix_retrieval_event_at", "retrieval_event", ["at"], schema="ops")

    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.drop_index("ix_retrieval_event_at", table_name="retrieval_event", schema="ops")
    # The policies and the grants go with the table.
    op.drop_table("retrieval_event", schema="ops")
