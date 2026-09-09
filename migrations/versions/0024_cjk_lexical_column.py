"""The Han bigram column, its generated tsvector and its index, plus the language column.

**Why a lexical column at all.** PostgreSQL's default parser has no Chinese dictionary, so a
run of Han characters is one token: a query for a two-character term inside a longer phrase
matches nothing, and the symptom is a Chinese query returning fewer rows rather than an error.
`brain.locale.lexical_tokens` segments a Han run into overlapping bigrams, which is the
segmentation that needs no extension, and `chunk.cjk` is where those tokens live.

**Three columns and only one of them is written by anything.** `cjk` is text the application
writes, `tsv_cjk` is generated from it by the database, and `language` records what
`brain.locale.detect` made of the chunk. The application-written one is the deviation and
`brain.knowledge.search` argues it there: the tokeniser is Python, a PL/pgSQL copy would be a
second implementation of a rule this repository refuses to duplicate, and an extension would
make the product depend on something a client's managed database may not offer.

**Every column is nullable and that is what makes this safe to deploy.** The release running
while this applies knows none of these columns and inserts none of them, and a NOT NULL with
no default would refuse every one of its inserts. `brain.deployment.compatibility` reads that
rule off this file, and it is the whole reason it reads migrations at all.

**No backfill here.** `brain.ops.migration_policy` refuses a migration that mixes schema with
data, and the reason applies exactly: the tokens for an existing corpus are one call per row
in Python, which is a job with a progress bar and a retry, not a statement inside a
transaction that holds a lock on the table the request path reads. Existing chunks therefore
have a NULL `cjk` and are absent from the Han index until something rewrites them, and absent
is honest: they were never findable by a Chinese query before this migration either.

**The index is partial on the same predicate as the English one**, because a retired chunk in
a GIN index is postings nobody may read, and re-chunking a document retires a document's worth
at once.

The downgrade drops all three and is real. Nothing else depends on them: the Han query leg is
the only reader and it is new in the same release.

Task ids: none
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

#: Rendered from the module that owns them, so the migration and the model cannot disagree
#: about the expression, the configuration or the width. A literal here would be a second
#: copy of three decisions, and the copy is the one that goes stale.
from brain.knowledge.search import (  # noqa: E402 - after the revision identifiers, on purpose
    CJK_TSVECTOR,
    LANGUAGE_TAG_CHARS,
)

INDEX_NAME = "ix_chunk_tsv_cjk"

#: The columns this migration adds, read by `tests/unit/test_search.py` so that the test
#: comparing `0009` against the declaration knows which columns are not `0009`'s to build.
#:
#: Declared here rather than listed in the test, for the reason that test's own docstring
#: gives: adding a column is then one file to edit and not two, and a list in the test is the
#: copy that goes stale.
ADDS_COLUMNS: tuple[str, ...] = ("cjk", "tsv_cjk", "language")


def upgrade() -> None:
    # Nullable, all three. See the docstring: the release this deploys alongside inserts none
    # of them, so a NOT NULL with no default refuses its every write.
    op.add_column("chunk", sa.Column("cjk", sa.Text(), nullable=True), schema="know")
    op.add_column(
        "chunk",
        sa.Column("tsv_cjk", postgresql_tsvector(), sa.Computed(CJK_TSVECTOR, persisted=True)),
        schema="know",
    )
    op.add_column(
        "chunk",
        sa.Column("language", sa.String(LANGUAGE_TAG_CHARS), nullable=True),
        schema="know",
    )
    op.create_index(
        INDEX_NAME,
        "chunk",
        ["tsv_cjk"],
        schema="know",
        postgresql_using="gin",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="chunk", schema="know")
    op.drop_column("chunk", "language", schema="know")
    op.drop_column("chunk", "tsv_cjk", schema="know")
    op.drop_column("chunk", "cjk", schema="know")


def postgresql_tsvector() -> sa.types.TypeEngine[object]:
    """The `tsvector` type, imported through a function so the import order above stays plain.

    `sqlalchemy.dialects.postgresql.TSVECTOR` at module scope would sit above the revision
    identifiers or below them and read as clutter either way; the identifiers are what a
    person opens this file to check.
    """
    from sqlalchemy.dialects.postgresql import TSVECTOR

    return TSVECTOR()
