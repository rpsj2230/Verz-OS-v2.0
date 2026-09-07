"""The accent fold becomes something an index can be built on, which needs one function.

0020 built the four `er` tables. This adds no table and no column: it installs the wrapper
`brain.resolution.normalise.IMMUTABLE_UNACCENT_SQL` declares, and builds one expression index
over it, which is the whole of M14.2.4.

**PostgreSQL declares `unaccent()` STABLE and that is not an oversight.** Its behaviour depends
on a dictionary file that can be reloaded while the server is running, so the planner is told
the result may change between statements. An expression index and a stored generated column
both require IMMUTABLE, which is why 0009's header records that the obvious
`to_tsvector('english', unaccent(body))` is refused outright, and why folding accents into an
index needs a wrapper. That wrapper is what this migration installs.

**The IMMUTABLE label is an assertion the planner trusts and never verifies, so the dictionary
is part of the schema from here on.** The day somebody edits `unaccent.rules` and reloads,
every index built on this wrapper holds the old folding while every new query computes the new
one, and the two stop meeting. Nothing errors and nothing reports it. The discipline that
follows is not optional: change the rules file only in a migration, and `REINDEX` everything
built on the wrapper in that same migration. `brain.resolution.normalise.
AN_IMMUTABLE_WRAPPER_IS_A_PROMISE_THE_SERVER_DOES_NOT_CHECK` is the long form.

**The two-argument form of `unaccent` is inside the wrapper on purpose.** The one-argument form
resolves its dictionary through `search_path`, so the same call means different things to two
sessions; naming `public.unaccent` as a `regdictionary` removes that, which is one of the two
reasons the built-in is STABLE and the one a wrapper can actually fix. The other, the reloadable
file, is the one the label only promises about.

**A design that would not need any of this, recorded because it is the better one for a new
column.** Fold in the application, store the key in an ordinary column and index the column:
then one implementation computes the fold, once, at write time, and the expression-index
question never arises. It is not what this migration does, because the leaf asks for the
wrapper and because `er.alias.name` already exists and holds observed forms that must stay
verbatim. `brain.resolution.normalise` argues both sides and is where a future author should
start before adding a second index here.

**The Python fold and this one are still not proven to agree.** `normalise.accent_fold` removes
combining marks after mapping the Latin letters that do not decompose;
`public.unaccent` is a lookup table. The overlap is large and the difference is real, and the
failure when they differ is quiet: the index holds one folding, a query computing the other
misses, and two records that are one company stay two. Nothing in this repository compares
them, because no unit test has a server. `THE_TWO_FOLDINGS_ARE_NOT_PROVEN_TO_AGREE` is the
statement of record.

**No table, so no row-level security clause and no grant.** Every migration here that adds a
table enables row-level security on it and 0020 is the pattern; this adds none, and an index
and a function carry no policies of their own. The index inherits the policies already on
`er.alias`, which is the point of putting it there rather than in a table of folded names: a
second table would be a second permission surface holding the same observations.

**Nothing queries this index.** `brain.resolution.cascade` says in
`NOTHING_HERE_IS_CALLED_BY_THE_RUNNING_SYSTEM` that the package has no functional caller, and
building an index for a query nobody writes is a cost with no benefit until they do. It is
built now because the wrapper is what M14.2.4 asks for and an installed wrapper with no index
over it proves nothing about whether an index can be built.

Task ids: M14.2.4

Revision ID: 0021
Revises: 0020
"""

from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

#: The extension the wrapper calls into. Created here and deliberately not dropped in the
#: downgrade: an extension is shared, and this migration cannot know what else came to depend
#: on it. Dropping the function and the index removes everything this migration is responsible
#: for; dropping the extension would remove something it merely asked for.
EXTENSION = "CREATE EXTENSION IF NOT EXISTS unaccent"

#: The wrapper, copied from `brain.resolution.normalise.IMMUTABLE_UNACCENT_SQL` rather than
#: imported, for the reason 0009, 0019 and 0020 all give: a migration describes the database it
#: actually built, and an import would make this file say whatever that module says next year.
#: `tests/unit/test_normalise.py` compares the two, which is what turns the copy into a check.
WRAPPER = """
CREATE OR REPLACE FUNCTION er.immutable_unaccent(text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
"""

#: The name of the index, and the expression it is built on.
#:
#: One expression, and every function in it must be IMMUTABLE or PostgreSQL refuses the index.
#: `brain.resolution.normalise.indexable` is the check, it is written against what the server
#: declares rather than against this wrapper, and a test runs it over exactly this string.
INDEX_NAME = "ix_alias_name_folded"
INDEX_EXPRESSION = "er.immutable_unaccent(name)"
INDEX = f"CREATE INDEX {INDEX_NAME} ON er.alias ({INDEX_EXPRESSION})"


def upgrade() -> None:
    # The label the whole file rests on, asserted rather than left to the docstring: without
    # IMMUTABLE the index below is refused, and a wrapper that lost the word would look
    # identical in review. The same shape 0020 uses for `security_invoker`.
    assert "IMMUTABLE" in WRAPPER
    # The dictionary is named explicitly so the result does not depend on `search_path`.
    assert "regdictionary" in WRAPPER
    # No table, so nothing here may carry a grant or a policy; see the docstring.
    assert "GRANT" not in INDEX and "POLICY" not in INDEX

    op.execute(EXTENSION)
    op.execute(WRAPPER)
    op.execute(INDEX)


def downgrade() -> None:
    """Drop the index, then the function, and leave the extension alone.

    The index depends on the function, so it goes first. The extension stays for the reason
    `EXTENSION` gives: it is shared, and this migration cannot know what else came to depend on
    it while it was installed.
    """
    op.execute(f"DROP INDEX IF EXISTS er.{INDEX_NAME}")
    op.execute("DROP FUNCTION IF EXISTS er.immutable_unaccent(text)")
