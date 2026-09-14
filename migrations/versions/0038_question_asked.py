"""Who asked a question gets a table, one row per trace, with row-level security on.

`brain.tables.adoption` holds the argument for the shape: it is `brain.adoption.Asked` field for
field, keyed on the trace id so that a question which fanned out to several agents is one row.
What is here is the table, its read and append policies, and its grants.

**`USING (true)` on the read, for the reason `0034` gives about `ops.spend_actual`, and the
reason is the same one because the reader is the same one.** Which departments a reader may see
adoption figures for is decided by `brain.console.spend_view.may_read_spend`, through
`brain.console.adoption_view`, which asks the reader's live `EntitlementSet` for their usage
scope. A scope is not a list of departments: it can be unrestricted, it can expire, and
`intersect` narrows it with an instant, so a predicate written here would be a second and
different implementation of that rule. The usage report and the adoption report answer "may
this reader know how much this department did" with one function, so they cannot disagree.

**SELECT and INSERT, and no UPDATE or DELETE.** Who asked a question does not change after it
was asked. Removal belongs to erasure, which `brain.ops.erasure` records as unbuilt, and granting
DELETE ahead of it would be a permission waiting for a caller.

**Nothing for the fast lane role.** It answers from the local projection and has no business
reading who else asked anything.

The downgrade is real and discards every recorded question.

Task ids: M37.3.2.4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.question_asked",)

APP_ROLE = "brain_app"

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.question_asked TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.question_asked ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY question_asked_readable ON ops.question_asked
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY question_asked_appendable ON ops.question_asked
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "question_asked",
        sa.Column("trace_id", sa.String(64), primary_key=True),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("principal_kind", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("department", sa.String(120), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("principal_kind IN ('human', 'service')", name="principal_kind"),
        sa.CheckConstraint(
            "channel IN ('api', 'console', 'email', 'lark', 'scheduler', 'slack', 'teams', "
            "'telegram', 'webhook', 'whatsapp', 'widget')",
            name="channel",
        ),
        sa.CheckConstraint("length(btrim(trace_id)) >= 1", name="trace_present"),
        sa.CheckConstraint("length(btrim(principal_id)) >= 1", name="principal_present"),
        sa.CheckConstraint("length(btrim(department)) >= 1", name="department_present"),
        schema="ops",
    )
    op.create_index("ix_question_asked_at", "question_asked", ["at"], schema="ops")
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The index and the policies go with the table.
    op.drop_table("question_asked", schema="ops")
