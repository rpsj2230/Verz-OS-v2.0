"""Knowledge items get a table, with the corpus's reach as its policy and one named read past it.

`brain.tables.knowledge` holds the argument for the shape: an item is the document a chunk is
cut from, `know.chunk` copies its permissions from it, and the row holds everything about the
document except its text. What is here is the table, its policy, its grants and the one function
the re-verification sweep reads through.

**The policy is `know.chunk`'s, less the retirement clause this table has no column for.** The
same two session settings, the same draft rule and the same three branches, so an item and its
chunks are reachable by the same people. A connection that set neither setting sees company
items only, which is the direction `0009` records as the default rather than something written.

**`know.items_for_review` is `SECURITY DEFINER`, for one read and one reason.** The sweep that
asks owners to look again has nobody present: there is no principal to set, so under the policy
it would see company items and nothing else, and it would record successful runs while every
department document went unasked. The function returns the review columns of retrievable items
whose date has arrived, and nothing else is read past the policy. Its search path is pinned and
every object is named with its schema, which is the arrangement `0036` makes for its own.

Two cheaper designs were rejected. `USING (true)` on SELECT, which `0038` uses for who asked a
question, would put every title in the knowledge layer in front of any query the application
writes, and a title is the part of a document the wall exists for. A session setting the sweep
sets to switch the policy off is a string any application code can write, which is the wildcard
`brain.knowledge.search.Reach.departments_setting` refuses for exactly that reason.

**`PUBLIC` keeps EXECUTE, as in `0036`, and the schema is what stops anybody else calling it.**
`0001` grants USAGE on `know` to `brain_app` alone. `REVOKE ... FROM PUBLIC` is not written, for
the reason `0036` gives about `brain.deployment.compatibility`.

**SELECT, INSERT and UPDATE, and no DELETE.** An item is archived or superseded and stays on
file. Nothing for the fast lane: it answers from the projection and has no business here.

The downgrade drops the function and then the table, and discards every item.

Task ids: M34.2.1.3

Revision ID: 0040
Revises: 0039
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

#: Read by `tests/unit/test_tables.py`, which concatenates every migration's slice.
TABLES: tuple[str, ...] = ("know.item",)

APP_ROLE = "brain_app"

#: `brain.knowledge.item.ITEM_ID_PATTERN` and `brain.core.department.SLUG_PATTERN`, as `0009`
#: copies them and for its reasons, including the non-capturing group written as a plain one.
REFERENCE_PATTERN = "^[A-Za-z0-9_.@-]{1,128}$"
SLUG_PATTERN = "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"
VISIBILITY_IN = "visibility IN ('company', 'department', 'personal')"
STATE_IN = "state IN ('archived', 'draft', 'published', 'superseded')"

FUNCTION = "know.items_for_review(timestamptz)"

CREATE_FUNCTION = """
CREATE FUNCTION know.items_for_review(p_by timestamptz)
RETURNS TABLE (
    item_id character varying,
    owner_id character varying,
    title character varying,
    state character varying,
    visibility character varying,
    department character varying,
    review_by timestamptz
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $items$
    SELECT i.item_id, i.owner_id, i.title, i.state, i.visibility, i.department, i.review_by
    FROM know.item AS i
    WHERE i.review_by IS NOT NULL
      AND i.review_by <= p_by
      AND i.state IN ('draft', 'published')
    ORDER BY i.review_by, i.item_id
$items$
"""

RLS: tuple[str, ...] = (
    "ALTER TABLE know.item ENABLE ROW LEVEL SECURITY",
    """
    CREATE POLICY item_within_reach ON know.item
        FOR ALL TO brain_app
        USING (
            state IN ('draft', 'published')
            AND (state <> 'draft' OR owner_id = current_setting('app.principal_id', true))
            AND (
                visibility = 'personal'
                    AND owner_id = current_setting('app.principal_id', true)
                OR visibility = 'department'
                    AND department = ANY(
                        string_to_array(current_setting('app.departments', true), ',')
                    )
                OR visibility = 'company'
            )
        )
        WITH CHECK (true)
    """,
)

GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON know.item TO brain_app",
    f"GRANT EXECUTE ON FUNCTION {FUNCTION} TO brain_app",
)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    assert all("DELETE" not in statement for statement in GRANTS)

    # Bare constraint names: alembic applies the naming convention on top. See `0030`.
    op.create_table(
        "item",
        sa.Column("item_id", sa.String(128), primary_key=True, nullable=False),
        sa.Column("title", sa.String(300), nullable=False, server_default=""),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("department", sa.String(60), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("verified_by", sa.String(128), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_by", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes", sa.String(128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"item_id ~ '{REFERENCE_PATTERN}'", name="item_id_is_a_reference"),
        sa.CheckConstraint("length(btrim(owner_id)) > 0", name="owned"),
        sa.CheckConstraint(VISIBILITY_IN, name="visibility"),
        sa.CheckConstraint(STATE_IN, name="state"),
        sa.CheckConstraint(
            f"department IS NULL OR department ~ '{SLUG_PATTERN}'", name="department_is_a_slug"
        ),
        sa.CheckConstraint(
            "visibility <> 'department' OR department IS NOT NULL",
            name="a_department_item_names_its_department",
        ),
        sa.CheckConstraint(
            "(verified_by IS NULL) = (verified_at IS NULL)",
            name="a_verification_is_a_person_and_a_date",
        ),
        schema="know",
    )
    op.create_index(
        "ix_item_review_by",
        "item",
        ["review_by"],
        schema="know",
        postgresql_where=sa.text("review_by IS NOT NULL"),
    )
    op.execute(CREATE_FUNCTION)
    for statement in RLS:
        op.execute(statement)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    # The policy, the index and the grants go with the table; the function has to go first,
    # because it names the table.
    op.execute(f"DROP FUNCTION {FUNCTION}")
    op.drop_table("item", schema="know")
