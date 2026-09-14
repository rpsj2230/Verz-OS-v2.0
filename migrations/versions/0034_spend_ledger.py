"""What runs actually cost gets a table, with row-level security on.

`brain.tables.spend` holds the argument for the shape: it is `brain.ops.spend.Actual` field for
field and nothing more. What is here is the table, its read and append policies, and its grants.

**`USING (true)` on the read is not an absence of a permission check, and `0035` depends on it
being exactly that.** Which runs a reader may see is decided by
`brain.console.spend_view.may_read_spend`, which asks the reader's live `EntitlementSet` for
their usage scope and matches the row's department against it. A scope is not a list of
departments: it can be unrestricted, it can expire, and `intersect` narrows it with an instant,
so a predicate here would be a second and different implementation of that rule, which `0018`
and `0025` refuse for the same reason. The consequence matters for the next migration. Because
the application role already reads every row of this table, a materialised view over it that
the same role reads is no wider than the table. The day this policy becomes narrower, that
stops being true, and `tests/unit/test_spend_report_view.py` reads the policy back from the
server so the day is a red build rather than a leak.

**SELECT and INSERT, and no UPDATE or DELETE.** A cost is appended when a run completes and a
figure that was wrong is a correction to the estimator, not an edit to what was paid. Removal
belongs to erasure, which `brain.ops.erasure` records as unbuilt, and granting DELETE ahead of it
would be a permission waiting for a caller.

**Nothing for the fast lane.** It answers from the local projection without a model, so it has
no cost to record and no business reading anybody else's.

The downgrade is real and discards every recorded cost. `0035` depends on this table, so it has
to come down first, which alembic's ordering guarantees.

Task ids: M36.1.3.1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("ops.spend_actual",)

APP_ROLE = "brain_app"

GRANTS: tuple[str, ...] = ("GRANT SELECT, INSERT ON ops.spend_actual TO brain_app",)

RLS: tuple[str, ...] = (
    "ALTER TABLE ops.spend_actual ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY spend_actual_readable ON ops.spend_actual
        FOR SELECT TO brain_app
        USING (true)
    """,
    """
    CREATE POLICY spend_actual_appendable ON ops.spend_actual
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("UPDATE" not in statement and "DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "spend_actual",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("principal_kind", sa.String(16), nullable=False),
        sa.Column("traffic", sa.String(24), nullable=False),
        sa.Column("department", sa.String(120), nullable=False),
        sa.Column("agent_id", sa.String(120), nullable=True),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("lane", sa.String(16), nullable=False),
        sa.Column("cost_minor", sa.BigInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("principal_kind IN ('human', 'service')", name="principal_kind"),
        sa.CheckConstraint(
            "traffic IN ('automation', 'human_async', 'human_interactive', 'system')",
            name="traffic",
        ),
        sa.CheckConstraint("lane IN ('answer', 'fast', 'task')", name="lane"),
        sa.CheckConstraint("length(btrim(principal_id)) >= 1", name="principal_present"),
        sa.CheckConstraint("length(btrim(department)) >= 1", name="department_present"),
        sa.CheckConstraint("length(btrim(model)) >= 1", name="model_present"),
        sa.CheckConstraint("cost_minor >= 0", name="cost_is_not_negative"),
        schema="ops",
    )
    op.create_index("ix_spend_actual_at", "spend_actual", ["at"], schema="ops")
    for statement in GRANTS:
        op.execute(statement)
    for statement in RLS:
        op.execute(statement)


def downgrade() -> None:
    # The index and the policies go with the table.
    op.drop_table("spend_actual", schema="ops")
