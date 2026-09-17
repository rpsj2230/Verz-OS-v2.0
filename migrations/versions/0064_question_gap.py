"""A question no connected source covers gets a table, one row per trace, row-level security on.

`brain.tables.question_gap` holds the argument for the shape: a department, a source and an
instant, keyed on the trace, and nothing about who asked or what they typed. What is here is the
table, its read and append policies, and its grant.

**`USING (true)` on the read, for `0038`'s reason.** Which gaps a reader may be shown is
`brain.console.questions_view.gap_lines`, which asks the reader's live `EntitlementSet` for the
Questions screen's scope over each row's department and for the Connectors screen's scope before
naming a source. A scope can be unrestricted, can expire and is narrowed with an instant, so a
predicate written here would be a second and different implementation of that rule.

**SELECT and INSERT, and no UPDATE or DELETE.** A question that was asked does not become unasked
when a source is connected later, and removal belongs to erasure.

**Nothing for the fast lane role.** It answers from the local projection and has no business
reading which questions went unanswered.

The downgrade is real and discards every recorded gap.

Task ids: M27.7.18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0064"
# The head of origin/main when this was written. Re-pointed at whichever migration is the head
# when it is integrated: nothing here depends on a table any later migration builds.
down_revision = "0063"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.question_gap",)

APP_ROLE = "brain_app"

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.question_gap TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.question_gap ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY question_gap_readable ON ops.question_gap
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY question_gap_appendable ON ops.question_gap
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "question_gap",
        sa.Column("trace_id", sa.String(64), primary_key=True),
        sa.Column("department", sa.String(120), nullable=False),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(btrim(trace_id)) >= 1", name="trace_present"),
        sa.CheckConstraint("length(btrim(department)) >= 1", name="department_present"),
        sa.CheckConstraint("length(btrim(source)) >= 1", name="source_present"),
        schema="ops",
    )
    op.create_index("ix_question_gap_at", "question_gap", ["at"], schema="ops")
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The index and the policies go with the table.
    op.drop_table("question_gap", schema="ops")
