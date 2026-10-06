"""A pair of records the cascade could not settle, kept until a person decides it.

One table, `er.review_item`. `brain.tables.resolution_review` holds the argument for each column:
one row per pair ever, evidence as field names and weights only, no score, and a decision written
once in the deciding person's own name.

**SELECT, INSERT and UPDATE, and the UPDATE is a decision.** The worker raises an item; a reviewer
decides it. The update policy admits only a row still `open` and only a `decided_by` that is the
session's own principal, so nobody records a decision in another person's name and nothing reopens
an item. No DELETE, and nothing for `brain_fastlane`.

**The downgrade drops it.** A pending item is raised again by the next run over the records it
names, and a decided one is recorded where the merge is (`er.merge`), which an install downgraded
past this migration no longer has either.

Task ids: M14.3.4, M14.6.4, M14.8.5

Revision ID: 0184
Revises: 0183
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0184"
down_revision = "0183"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`. Points at nothing: the records and entities are values.
TABLES: tuple[str, ...] = ("er.review_item",)

APP_ROLE = "brain_app"
FAST_ROLE = "brain_fastlane"
NAME = "^[a-z][a-z0-9_]*$"
PRINCIPAL = "current_setting('app.principal_id', true)"

RLS: tuple[str, ...] = (
    "ALTER TABLE er.review_item ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY review_item_readable ON er.review_item
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY review_item_raised ON er.review_item
        FOR INSERT TO brain_app
        WITH CHECK (state = 'open')
    """,
    f"""
    CREATE POLICY review_item_decided_in_the_sessions_name ON er.review_item
        FOR UPDATE TO brain_app
        USING (state = 'open')
        WITH CHECK (decided_by = {PRINCIPAL})
    """,
)

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT, UPDATE ON er.review_item TO brain_app",)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)
    assert all(FAST_ROLE not in statement for statement in GRANTS + RLS)
    op.create_table(
        "review_item",
        sa.Column("item_id", sa.String(40), primary_key=True, nullable=False),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("left_source", sa.String(60), nullable=False),
        sa.Column("left_entity", sa.String(60), nullable=False),
        sa.Column("left_source_id", sa.String(200), nullable=False),
        sa.Column("right_source", sa.String(60), nullable=False),
        sa.Column("right_entity", sa.String(60), nullable=False),
        sa.Column("right_source_id", sa.String(200), nullable=False),
        sa.Column("left_entity_id", sa.String(128), nullable=False),
        sa.Column("right_entity_id", sa.String(128), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("stage", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.String(400), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column(
            "raised_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column("decided_by", sa.String(128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("length(btrim(item_id)) > 0", name="item_id_present"),
        sa.CheckConstraint(
            "entity_type IN ('company', 'person', 'project')", name="entity_type_known"
        ),
        sa.CheckConstraint("origin IN ('cascade', 'held', 'money')", name="origin_known"),
        sa.CheckConstraint("state IN ('merged', 'open', 'rejected')", name="state_known"),
        sa.CheckConstraint(f"left_source ~ '{NAME}'", name="left_source_is_a_name"),
        sa.CheckConstraint(f"right_source ~ '{NAME}'", name="right_source_is_a_name"),
        sa.CheckConstraint(
            "(left_source, left_entity, left_source_id)"
            " < (right_source, right_entity, right_source_id)",
            name="pair_is_ordered",
        ),
        sa.CheckConstraint("stage BETWEEN 1 AND 4", name="stage_is_a_stage"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="reason_present"),
        sa.CheckConstraint("jsonb_typeof(evidence) = 'array'", name="evidence_is_a_list"),
        sa.CheckConstraint(
            "(state = 'open') = (decided_by IS NULL AND decided_at IS NULL)",
            name="decided_once",
        ),
        schema="er",
    )
    op.create_index(
        "uq_review_item_pair",
        "review_item",
        [
            "left_source",
            "left_entity",
            "left_source_id",
            "right_source",
            "right_entity",
            "right_source_id",
        ],
        unique=True,
        schema="er",
    )
    op.create_index("ix_review_item_state", "review_item", ["state"], schema="er")
    for statement in RLS + GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS er.review_item")
