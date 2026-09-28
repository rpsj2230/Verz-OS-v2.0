"""Every knowledge item records its kind, from a closed list, and the library can say which.

**`know.item.kind`** (M7.6.1): one word from `brain.knowledge.kinds.KnowledgeKind`, checked by a
constraint generated from that enum and held equal to it by `tests/unit/test_knowledge_kinds.py`.
Nullable, deliberately, for the reason `0010` gives about the embedding model: the items written
before this release were written by a path that chose no kind, there is no honest value to
backfill, and inventing one would be a classification nobody made. Every item the console adds
carries one, because the upload door refuses an upload naming none; a NULL means an item from
before this release or from the connector leg, and the library says so in words.

**No kind on `know.chunk`.** A search narrowed to some kinds asks `know.item` for them inside the
chunk statement, and `know.item`'s policy reads the same two session settings `know.chunk`'s does,
so the narrowing sees exactly the items the reach already admits. A copied column was rejected: it
would be a second place the kind lives, and a re-upload that changed the kind would have to move
it in two tables inside one transaction or leave them disagreeing.

**`know.library_items_with_kind` is the library read with the kind as its fifth column.** The
Knowledge library is read past the corpus policy through `0069`'s `know.library_items`, and the
kind is shown on its rows. A kind is a word a person chose from twelve and says nothing a
document's text says, so it sits on the existence plane beside the level, which is what that
screen may show. A second function rather than `0069`'s replaced, because PostgreSQL cannot
change the columns a function returns without dropping it, and a release still running during a
deploy reads the old one: `brain.deployment.compatibility` refuses a migration that removes what
the release before it reads. The old function is left for that release and is the next contract
migration's to drop. Its body is `0069`'s with one more column, and EXECUTE is granted as `0069`
granted it.

**The check travels with the column,** under the naming convention, as `0093` and `0100` add
theirs: a constraint added to a table that was already there is one the compatibility gate cannot
order, and one declared on a column that did not exist before narrows nothing the previous release
could write.

**The downgrade** drops the second function, then the column and its check with it. Dropping the
column loses every recorded kind, which is a real loss and the only reversal a column addition
has; no check is re-created, so nothing is narrowed on rows already written.

Task ids: M7.6.1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0115"
# The newest migration on origin/main when this was written.
down_revision = "0108"
branch_labels = None
depends_on = None

#: No table is created.
TABLES: tuple[str, ...] = ()

#: The column this adds to `know.item`, which `0040` built. Named for that table so the chunk
#: table's comparison in `tests/unit/test_search.py`, which reads `ADDS_COLUMNS`, is not told
#: about a column on a different table.
ITEM_COLUMNS_ADDED: tuple[str, ...] = ("kind",)

APP_ROLE = "brain_app"

SCHEMA = "know"
TABLE = "item"
COLUMN = "kind"

#: `brain.knowledge.kinds.KIND_CHARS`, copied for `0009`'s reason about reading live code from
#: a migration and held equal by a test.
KIND_CHARS = 32

#: `brain.knowledge.kinds.KnowledgeKind`, sorted, copied for the same reason and held equal.
KINDS: tuple[str, ...] = (
    "approved_solution",
    "best_practice",
    "brand_guidelines",
    "company_rule",
    "faq",
    "policy",
    "pricing_note",
    "service_information",
    "service_package",
    "sop",
    "template",
    "training_material",
)

#: The check, in the words `brain.tables.knowledge` renders for the model.
KIND_CHECK = "kind IS NULL OR kind IN ({})".format(", ".join(f"'{one}'" for one in KINDS))

LIBRARY_FUNCTION = "know.library_items_with_kind(integer)"

CREATE_LIBRARY = """
CREATE FUNCTION know.library_items_with_kind(p_limit integer)
RETURNS TABLE (
    item_id character varying,
    owner_id character varying,
    visibility character varying,
    department character varying,
    kind character varying
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, know
AS $library$
    SELECT i.item_id, i.owner_id, i.visibility, i.department, i.kind
    FROM know.item AS i
    WHERE i.state IN ('draft', 'published')
    ORDER BY i.item_id
    LIMIT greatest(p_limit, 0)
$library$
"""

GRANTS: tuple[str, ...] = (f"GRANT EXECUTE ON FUNCTION {LIBRARY_FUNCTION} TO brain_app",)


def upgrade() -> None:
    assert all(APP_ROLE in statement for statement in GRANTS)
    # The check travels with the column, under the naming convention; see the docstring.
    op.add_column(
        TABLE,
        sa.Column(
            COLUMN,
            sa.String(KIND_CHARS),
            sa.CheckConstraint(KIND_CHECK, name=COLUMN),
            nullable=True,
        ),
        schema=SCHEMA,
    )
    op.execute(CREATE_LIBRARY)
    for statement in GRANTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {LIBRARY_FUNCTION}")
    # The check goes with the column it constrains, so it is not dropped by name first.
    op.drop_column(TABLE, COLUMN, schema=SCHEMA)
