"""A fast-lane rule may belong to a department, and a rule is written in its writer's name.

M6.5.1 asks that a department's administrator add, test and retire a fast-lane rule for their own
department from the console, and that it answer from the next request. `0019` built the rule
table for the whole install: one live rule per template, written by anybody holding the
application role, and read once at start. This migration is the table's half of the change;
`brain.gate.rule_store` reads the rules on every question now and `brain.rule_routes` is the
console's surface. `brain.tables.fast_lane` holds the argument for the column.

**`gate.fast_path_rule.department`**, nullable and held to the department slug grammar. Null is a
rule the whole install asks with, which is every rule an install already holds, so nothing that
answers today changes. A department's slug is a rule only that department's askers are matched
against. Nullable rather than defaulted, because no department is the honest description of a
rule nobody scoped, and a default department would hand an existing rule to whichever department
the default named.

**One live rule per template per department.** `0019`'s index admitted one live rule per
template, so a second department writing the words the first had written would be refused, and
the refusal would tell it the first department had written them. The index is replaced by one
over the template and the department with nulls not distinct, so each department holds its own
words and the rules the install asks with are still one per template.

**That index refuses nothing the previous release could write, and the reason is not the
compatibility gate's.** `brain.deployment.compatibility` passes a unique index naming a column
this body adds, on the argument that nulls are distinct and so the previous release's rows are
never compared. With nulls not distinct they are compared, so that argument does not hold here.
The one that does: the previous release writes no department, so every row it writes has a null
there, and among those rows this index is `0019`'s index exactly. Anything `0019`'s schema
accepted from the previous release, this one accepts. An expression over `coalesce(department,
'')` would say the same thing and is not what the gate can read, so it would be refused for a
narrowing it is not. Measured: `breaking_changes` of this file is empty, which
`tests/unit/test_rule_routes.py` holds.

**A rule is written in the name of the person writing it.** `0019`'s insert policy was
`WITH CHECK (true)`, so any session of the application role could insert a rule naming anybody
as its author, and `created_by` is the only accountability a rule answering with no model has.
The policy now requires `created_by` to be the `brain.actor_id` the transaction set, which is
`brain.tables.audit.attributed_to`'s setting every console write already runs first. Which
department a person may write is the grant's question and is decided by the routes at the
grant's scope, as `brain.classification_routes` decides it for an uploaded table; this table
holds the author to the truth, which is the part a route cannot vouch for about a row that
arrived some other way. The compatibility gate reads a policy replaced in one body as
unreadable rather than safe, so the reason it takes nothing from the previous release is
written here: that release writes a rule as the application role only from the install
acceptance checks, each of which runs `Harness.attributed()` and names the same actor in
`created_by`, and the seed and the demo write as the table's owner, whom no policy binds.

**What this does not close: a live rule's words can still be rewritten under its id.** `0045`
left the update policy retire-only for a row's `deleted_at`, and the application role still
holds `UPDATE` on every column, so a statement that keeps a rule live can change its template,
and "which rule answered that question in March" would name a row that no longer says what it
said in March. Narrowing the grant to `deleted_at` was written here first and is refused by
`brain.deployment.compatibility`, rightly by its own rule: a `REVOKE` on a table that was
already there narrows what the previous release may do, and the gate admits no per-file waiver.
Nothing in this product updates a rule's words (`brain.gate.rule_store.StoredRules` retires and
adds), so the gap is one a statement written elsewhere would have to use. Closing it is a
two-release change and is left for that.

**The downgrade** puts back `0019`'s index and insert policy and drops the column. It is refused
while two live rules share a template, which only department rules can have made, so a
downgrade never builds an index the rows it finds would violate.

Task ids: M6.5.1

Revision ID: 0199
Revises: 0198
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0199"
# The head of this branch when it was written; re-pointed at whichever migration is the head
# when it lands, since nothing here depends on anything after 0045.
down_revision = "0198"
branch_labels = None
depends_on = None

#: No table is created: a column, an index, a policy and a grant change on `0019`'s table.
TABLES: tuple[str, ...] = ()

APP_ROLE = "brain_app"

#: `brain.knowledge.search.SLUG_SQL_PATTERN`, copied for the reason `0009` gives about reading
#: live code from a migration, and held equal to `brain.tables.fast_lane` by
#: `tests/unit/test_rule_routes.py`.
DEPARTMENT_IS_A_SLUG = "department IS NULL OR department ~ '^[a-z][a-z0-9]*(_[a-z0-9]+)*$'"

#: `brain.tables.fast_lane.NAME_CHARS`, copied.
NAME_CHARS = 60

#: The author, as the transaction's own setting names them.
ACTOR = "current_setting('brain.actor_id', true)"

UPGRADE_RLS: tuple[str, ...] = (
    "DROP POLICY fast_path_rule_writable ON gate.fast_path_rule",
    f"""
    CREATE POLICY fast_path_rule_written_in_the_writers_name ON gate.fast_path_rule
        FOR INSERT TO brain_app
        WITH CHECK (created_by = {ACTOR})
    """,
)

#: `0019`'s, put back exactly.
DOWNGRADE_RLS: tuple[str, ...] = (
    "DROP POLICY fast_path_rule_written_in_the_writers_name ON gate.fast_path_rule",
    """
    CREATE POLICY fast_path_rule_writable ON gate.fast_path_rule
        FOR INSERT TO brain_app
        WITH CHECK (true)
    """,
)

#: The downgrade's refusal, for rows the one-per-template index would not admit.
REFUSE_TWO_LIVE_RULES_IN_ONE_TEMPLATE = """
DO $$
BEGIN
    IF EXISTS (
        SELECT template FROM gate.fast_path_rule
         WHERE deleted_at IS NULL
         GROUP BY template
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'two live rules share a template; a downgrade would refuse its own index';
    END IF;
END
$$
"""


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in UPGRADE_RLS[1:])
    assert all("brain_fastlane" not in statement for statement in UPGRADE_RLS)
    op.add_column(
        "fast_path_rule",
        sa.Column("department", sa.String(NAME_CHARS), nullable=True),
        schema="gate",
    )
    # A bare constraint name: alembic applies the metadata's naming convention.
    op.create_check_constraint(
        "department_is_a_slug", "fast_path_rule", DEPARTMENT_IS_A_SLUG, schema="gate"
    )
    op.drop_index("uq_fast_path_rule_template_live", table_name="fast_path_rule", schema="gate")
    op.create_index(
        "uq_fast_path_rule_template_department_live",
        "fast_path_rule",
        ["template", "department"],
        schema="gate",
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    for statement in UPGRADE_RLS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(REFUSE_TWO_LIVE_RULES_IN_ONE_TEMPLATE)
    for statement in DOWNGRADE_RLS:
        op.execute(statement)
    op.drop_index(
        "uq_fast_path_rule_template_department_live", table_name="fast_path_rule", schema="gate"
    )
    op.create_index(
        "uq_fast_path_rule_template_live",
        "fast_path_rule",
        ["template"],
        schema="gate",
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # The column's check goes with the column.
    op.drop_column("fast_path_rule", "department", schema="gate")
