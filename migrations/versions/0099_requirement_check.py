"""A person's check of a requirement on this install is kept, one row per check.

**`ops.requirement_check`: who checked which requirement, on which release, and what they found
(M1.8.8, M2.3.2, M5.6.5, M24.3.6).** The Requirement checks screen lists the register's rows by
area, and a holder of `admin:requirement_check` records a check against one of them: passed or
failed, and a sentence saying what was done and seen. `brain.tables.requirement_check` argues the
columns, and why a check is not written to the ledger.

**SELECT and INSERT, and no UPDATE or DELETE**, for `0093`'s reason: a later check supersedes an
earlier one and never edits it, because a requirement that passed on one release and fails on the
next is two facts. `USING (true)` on the read, because the one reader is the screen, behind the
check authority held over everything.

**The downgrade** drops the table, which discards every recorded check. Nothing else refers to it.

Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0099"
# The newest head on origin/main when this was written is 0101; 0098 is this
# workstream's own, landed in the same change.
down_revision = "0098"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.requirement_check",)

APP_ROLE = "brain_app"

#: Copied for `0009`'s reason about reading live code from a migration, and held equal to
#: `brain.tables.requirement_check` by the rendered-DDL test.
REQUIREMENT_ID_PATTERN = r"^[A-Z][A-Z0-9]*(-[A-Z0-9.]+)+$"
IDENTIFIER = r"^[A-Za-z0-9_.@-]{1,128}$"
COMMIT_PATTERN = r"^[0-9a-f]{7,40}$"
OUTCOMES = "outcome IN ('failed', 'passed')"
NOTE_CHARS = 1000

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.requirement_check TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.requirement_check ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY requirement_check_readable ON ops.requirement_check
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY requirement_check_appendable ON ops.requirement_check
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    op.create_table(
        "requirement_check",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("requirement_id", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(8), nullable=False),
        sa.Column("checked_by", sa.String(128), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("release_commit", sa.String(40), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.CheckConstraint(
            f"requirement_id ~ '{REQUIREMENT_ID_PATTERN}'", name="requirement_id_shape"
        ),
        sa.CheckConstraint(OUTCOMES, name="outcome"),
        sa.CheckConstraint(f"checked_by ~ '{IDENTIFIER}'", name="checked_by_shape"),
        sa.CheckConstraint(
            f"release_commit IS NULL OR release_commit ~ '{COMMIT_PATTERN}'",
            name="release_commit_shape",
        ),
        sa.CheckConstraint(
            f"length(btrim(note)) >= 1 AND length(note) <= {NOTE_CHARS}",
            name="note_is_a_sentence",
        ),
        schema="ops",
    )
    op.create_index(
        "ix_requirement_check_requirement_id",
        "requirement_check",
        ["requirement_id", "checked_at"],
        schema="ops",
    )
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The index, the policies and the grants go with the table.
    op.drop_table("requirement_check", schema="ops")
