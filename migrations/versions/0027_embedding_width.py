"""The corpus column is set to the vector width this install declared, and refuses to move.

**The width stopped being a number in this repository on 2026-09-10 and became a setting.**
`0009` created `know.chunk.embedding` as `VECTOR(1536)`, which is what a hosted embedding
model produces, and item 31 of `docs/needs-rupash.md` then chose a local model producing
1024. Item 34 is that disagreement and its answer is both halves of this file: narrow the
column, and read the width from `INSTALL_EMBEDDING_DIMENSIONS` rather than from a literal, so
that the next client whose model is a third width sets a value instead of forking the
product. `brain.knowledge.search` carries the long-form argument and owns both the setting
and the statement below; this migration is where the column is actually moved.

**Nothing is being converted here and the refusal is what says so.** A stored vector belongs
to the model that produced it. Narrowing the column does not truncate the corpus into a
usable one, it invalidates every row, and pgvector's own typmod cast would refuse the rewrite
in any case with a message naming two integers and no reason. So `width_change_refusal` runs
first, in both directions, and stops the migration while a single chunk is embedded. Today it
costs nothing: no chunk has ever been embedded, because nothing in this repository calls
anything that writes one, and that window closes on the day the first document is ingested.

**The refusal is SQL rather than Python, deliberately.** `op.get_bind().execute(...)` with a
Python `raise` is shorter and can count the rows. It is also absent from the artefact that
most needs it: `alembic upgrade --sql` renders these files into a script somebody applies to
a production database by hand, and a Python guard renders to nothing, leaving a script that
carries the `ALTER` and not the refusal. A `DO` block is in the script, inside the same
transaction as the `ALTER`, and refuses at the moment of application either way.

**The index is not dropped and rebuilt here.** `ALTER COLUMN ... TYPE` rewrites the table and
reindexes what depends on it, so `ix_chunk_embedding` is rebuilt by PostgreSQL rather than by
this file. Dropping and recreating it by hand would be three statements that say the same
thing and one more place for the HNSW options to drift from the declaration in
`brain.knowledge.search.VECTOR_INDEX`, which is the copy that would go stale.

**The downgrade puts back what `0009` built, not what this install declared.** A downgrade
is for the release before this one, and that release read a hardcoded 1536. It refuses on an
embedded corpus for the same reason the upgrade does, which means a rollback after any
embedding has to be a decision somebody takes with the corpus in front of them rather than
one this file takes for them at three in the morning.

**No `TABLES` here.** This migration creates no table, so it exports no slice of the package
tuple; `tests/unit/test_tables.py` compares the migrations that create tables end to end and
this is not one of them. It exports `ALTERS_COLUMNS` instead, which is how
`tests/unit/test_search.py` knows that `0009` describes the column it built and this file
describes the column that is there now.

Task ids: none

Revision ID: 0027
Revises: 0026
"""

from __future__ import annotations

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

#: Rendered from the module that owns the width, so the migration and the model cannot
#: disagree about it. This is `0024`'s import and not `0009`'s copied literals, and the
#: difference is the point of the change: there is no number here to copy.
from brain.knowledge.search import (  # noqa: E402 - after the revision identifiers, on purpose
    EMBEDDING_DIMENSIONS,
    Vector,
    width_change_refusal,
)

#: The column this migration alters, read by `tests/unit/test_search.py` so that the test
#: comparing the declaration against `0009` knows which column `0009` no longer describes.
#:
#: Declared here rather than listed in the test, for the reason `0024`'s `ADDS_COLUMNS` gives:
#: altering a column is then one file to edit and not two, and the list in the test is the
#: copy that goes stale.
ALTERS_COLUMNS: tuple[str, ...] = ("embedding",)

#: What `0009` created the column with, which is what the downgrade puts back. Held to
#: `0009`'s own constant by `tests/unit/test_search.py` rather than trusted, because a
#: literal about another file is exactly the copy this repository keeps finding rotted.
WIDTH_BEFORE_THIS = 1536


def upgrade() -> None:
    # The refusal before the alteration, and inside the same transaction, so a corpus that
    # has been embedded stops this rather than losing its vectors to a rewrite.
    op.execute(width_change_refusal(EMBEDDING_DIMENSIONS))
    op.alter_column(
        "chunk",
        "embedding",
        type_=Vector(EMBEDDING_DIMENSIONS),
        existing_type=Vector(WIDTH_BEFORE_THIS),
        existing_nullable=True,
        schema="know",
    )


def downgrade() -> None:
    op.execute(width_change_refusal(WIDTH_BEFORE_THIS))
    op.alter_column(
        "chunk",
        "embedding",
        type_=Vector(WIDTH_BEFORE_THIS),
        existing_type=Vector(EMBEDDING_DIMENSIONS),
        existing_nullable=True,
        schema="know",
    )
