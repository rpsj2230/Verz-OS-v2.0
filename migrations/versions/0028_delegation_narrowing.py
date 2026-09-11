"""The child grant computed in SQL, and a trigger refusing any row that is not a subset.

`E_run(caller, agent) = E(caller) intersect agent_ceiling` is the one rule the platform rests
on, and until this migration it was enforced in Python only: correct, tested, and reachable
exactly by the callers who chose to call it. A row written by `psql`, by a backfill, by a
worker in another language or by a future code path that forgot is a delegation nothing
checked. This is where that stops being true.

**The table exists so that the refusal has somewhere to stand.** Nothing in `src/brain` reads
a delegation row back, and the only reader of any kind is the trigger, which looks up one
column of the parent row to bound the child. There is therefore a policy for INSERT and none
for SELECT: a `USING (true)` read policy written now, in advance of any screen that wants one,
would grant back exactly what enabling row-level security denied, which is what
`tests/unit/test_queue_driver.py` records about the queue driver's own tables.

**A row below the root cannot supply its own parent reach**, which is the check constraint
`one_source_of_the_parent_reach` and the whole reason the trigger is worth more than the
Python check standing beside the same insert. `parent_id` and `parent_grants` are mutually
exclusive, so the left-hand side of the intersection is either the asker's reach at the root
or a reach a previous row was already refused for widening. The argument in full is in
`brain.core.scope_sql`, which owns every statement this migration executes.

The downgrade is real and reverses both halves, dropping the trigger with the table and then
the six functions in the reverse of their dependency order. Nothing depends on the table
existing: no module imports it, no model declares it, and an install without it is the state
before this migration, where the rule is kept in Python alone.

**No SQLAlchemy model declares this table and that is a gap rather than a decision.**
`src/brain/tables/` is owned elsewhere and a model belongs there, along with its row in
`tests/unit/test_tables.py`. Until then `brain.tables.TABLES_IN_DEPENDENCY_ORDER` does not
name `gate.delegation`, so the metadata comparison in that test is checking a set this table
is absent from on both sides rather than being satisfied by a wrong answer.

Task ids: M18.3.1, M18.3.2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

#: Every statement is rendered from the module that owns the rule, for the reason `0024`
#: gives about the index expression it renders: a literal here would be a second copy of a
#: decision, and the copy is the one that goes stale. The install order is the tuple's order,
#: which is dependency order.
from brain.core.scope_sql import (  # noqa: E402 - after the revision identifiers, on purpose
    DELEGATION_INSTALL,
    DELEGATION_SCHEMA,
    DELEGATION_TABLE,
    DELEGATION_TRIGGER_SQL,
    DELEGATION_UNINSTALL,
)

#: The table this migration creates, in the shape `tests/unit/test_tables.py` reads from every
#: other migration that creates one, so a test and a migration cannot disagree about what
#: shipped.
TABLES: tuple[str, ...] = (f"{DELEGATION_SCHEMA}.{DELEGATION_TABLE}",)

#: The trigger's name, exported so a test can ask the catalogue whether it is really attached
#: rather than infer it from the migration having run without raising.
TRIGGER_NAME = "delegation_narrows"

#: Row-level security, and one policy. INSERT only, deliberately: see the docstring.
RLS: tuple[str, ...] = (
    "ALTER TABLE gate.delegation ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY delegation_writable ON gate.delegation
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
    # No SELECT, UPDATE or DELETE privilege either. The trigger refuses an UPDATE in words,
    # and this is the same refusal said where a privilege check can see it: two mechanisms for
    # one rule because they fail in different directions, since a trigger can be disabled by
    # whoever owns the table and a privilege cannot be talked round.
    "GRANT INSERT ON gate.delegation TO brain_app",
)


def upgrade() -> None:
    op.create_table(
        "delegation",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Self-referential and RESTRICT by omission, which is the default: a parent row whose
        # recorded reach bounded a child may not be deleted while that child stands, or the
        # child's bound would outlive the thing that set it.
        sa.Column(
            "parent_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("gate.delegation.id"),
            nullable=True,
        ),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("child_id", sa.Text(), nullable=False),
        sa.Column("parent_grants", postgresql.JSONB(), nullable=True),
        sa.Column("agent_ceiling", postgresql.JSONB(), nullable=False),
        sa.Column("subtask_ceiling", postgresql.JSONB(), nullable=False),
        sa.Column("child_grants", postgresql.JSONB(), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # The constraint the whole arrangement rests on. Exactly one source of the parent
        # reach: the asker's, supplied at the root, or the row above, which was itself
        # refused if it widened. A row that could do both could choose the wider one.
        sa.CheckConstraint(
            "(parent_id IS NULL) = (parent_grants IS NOT NULL)",
            name="one_source_of_the_parent_reach",
        ),
        sa.CheckConstraint("length(btrim(run_id)) > 0", name="run_id_present"),
        sa.CheckConstraint("length(btrim(child_id)) > 0", name="child_id_present"),
        sa.CheckConstraint("parent_id IS DISTINCT FROM id", name="not_its_own_parent"),
        # One row per child. Two rows for one child would let a narrow one be inserted for the
        # check and a wide one be inserted beside it for whatever reads them.
        sa.UniqueConstraint("run_id", "child_id", name="one_row_per_child"),
        schema="gate",
    )
    op.create_index(
        "ix_delegation_by_parent",
        "delegation",
        ["parent_id"],
        schema="gate",
        postgresql_using="btree",
    )
    for statement in (*DELEGATION_INSTALL, DELEGATION_TRIGGER_SQL, *RLS):
        op.execute(statement)


def downgrade() -> None:
    op.drop_index("ix_delegation_by_parent", table_name="delegation", schema="gate")
    # The trigger goes with the table it hangs on; the functions outlive it and are dropped
    # afterwards, innermost caller first.
    op.drop_table("delegation", schema="gate")
    for statement in DELEGATION_UNINSTALL:
        op.execute(statement)
