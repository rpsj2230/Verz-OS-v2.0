"""The accent fold is indexable, held to PostgreSQL's rule rather than to our own wrapper.

M14.2.4 asks for accent folding "via an immutable wrapper so it can be indexed", and the trap
in that sentence is specific: an expression index and a stored generated column both require
every function in the expression to be IMMUTABLE, `unaccent()` is STABLE because its dictionary
can be reloaded while the server runs, and 0009 records that this is why
`to_tsvector('english', unaccent(body))` is refused.

**These tests are written against that rule and not against the wrapper.**
`normalise.PG_VOLATILITY` is what PostgreSQL declares, `indexable` reads it, and the wrapper is
admitted for the reason the server would admit it rather than because it is ours. The anchor
that stops the table being an opinion is that the same check has to refuse the expression 0009
independently records as refused, and has to admit the expression migration 0021 actually
executes.

**What is not checked here, said plainly.** No server has confirmed a line of
`PG_VOLATILITY`, nobody has run 0021, and the IMMUTABLE label on the wrapper is an assertion
the planner trusts and never verifies. `normalise.NOTHING_HERE_IS_INSTALLED_IN_POSTGRES` is the
statement of record for all three.

Task ids: M14.2.4
"""

from __future__ import annotations

import importlib.util
import io
import re
import types
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations

from brain.db import metadata
from brain.resolution.normalise import (
    IMMUTABLE_UNACCENT_SQL,
    PG_VOLATILITY,
    Volatility,
    calls_in,
    indexable,
)

MIGRATION = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0021_accent_fold_index.py"
)

#: The expression 0009's header records PostgreSQL as refusing, and the one-argument form it
#: records in the same paragraph. Written here rather than read out of that file, because
#: reading it out would make this test pass on 0009's prose; the point is that two files in this
#: repository have to agree about one fact.
REFUSED_BY_0009 = "to_tsvector('english', unaccent(body))"
ALSO_REFUSED_BY_0009 = "to_tsvector(body)"


def migration() -> types.ModuleType:
    """The migration as a module. Importing runs nothing: `upgrade` is a function."""
    spec = importlib.util.spec_from_file_location("migration_0021", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rendered(direction: str) -> str:
    """The SQL the migration emits, rendered without a database.

    Read from what `upgrade` executes rather than from the file's text, for the reason
    `tests/unit/test_resolution_tables.py` gives about 0020: a statement sitting in a constant
    that nothing executes passes a source search and builds nothing.
    """
    buffer = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": buffer, "target_metadata": metadata},
    )
    module = migration()
    with Operations.context(context):
        getattr(module, direction)()
    return buffer.getvalue()


def _index_expressions(sql: str) -> tuple[str, ...]:
    """Whatever every CREATE INDEX in this SQL is built over.

    The bracket is matched by depth rather than by a lazy regular expression, because the
    expression that matters here contains brackets of its own and a lazy match would stop at
    the first one, hand back `er.immutable_unaccent(name`, and find no function calls in it at
    all. That failure would be silent and green.
    """
    found: list[str] = []
    for match in re.finditer(r"CREATE\s+INDEX\b", sql, flags=re.IGNORECASE):
        opened = sql.find("(", match.end())
        assert opened != -1, "a CREATE INDEX with no bracket"
        depth = 0
        for position in range(opened, len(sql)):
            if sql[position] == "(":
                depth += 1
            elif sql[position] == ")":
                depth -= 1
                if depth == 0:
                    found.append(sql[opened + 1 : position].strip())
                    break
    return tuple(found)


def _squash(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------- the rule, held against 0009's record
def test_an_index_over_the_built_in_unaccent_is_refused_for_the_reason_0009_records() -> None:
    """**The real rule, and the one fact two files in this repository have to agree about.**

    0009's header states that `to_tsvector('english', unaccent(body))` is refused in a stored
    generated column because `unaccent()` is STABLE, and that folding accents into an index
    therefore needs an immutable wrapper of the sort M14's normalisation leaf calls for. That
    is an independent statement about PostgreSQL made elsewhere in this repository, and it is
    what stops `PG_VOLATILITY` being a table that agrees only with itself.

    The one-argument `to_tsvector` is here too, from the same paragraph, and it is the reason
    the table is keyed by arity: the two-argument form takes a `regconfig` and is IMMUTABLE.

    The positive sibling is the point of the whole leaf: the wrapper is admitted, and so is a
    bare column, so this is a check that distinguishes rather than one that refuses everything.

    Delete this and the volatility table can say whatever makes the wrapper look necessary."""
    refused = indexable(REFUSED_BY_0009)
    assert len(refused) == 1
    assert "unaccent" in refused[0]
    assert "STABLE" in refused[0]

    assert indexable(ALSO_REFUSED_BY_0009) != ()

    assert indexable("er.immutable_unaccent(name)") == ()
    assert indexable("to_tsvector('english', er.immutable_unaccent(name))") == ()
    assert indexable("name") == ()


def test_the_verdict_depends_on_how_many_arguments_the_call_was_given() -> None:
    """The same name, two arities, two answers, and the permissive one is the wrong default.

    A table keyed by name alone would have to pick one verdict for `to_tsvector`, and whichever
    it picked would be wrong for the other form: STABLE refuses the index that actually works,
    IMMUTABLE admits the one PostgreSQL rejects outright. 0009 hit exactly this and its header
    records both halves.

    Delete this and the key can be simplified to the name, which reads as tidying up and makes
    one of the two forms silently wrong."""
    assert PG_VOLATILITY[("to_tsvector", 2)] is Volatility.IMMUTABLE
    assert PG_VOLATILITY[("to_tsvector", 1)] is Volatility.STABLE
    assert indexable("to_tsvector('english', name)") == ()
    assert indexable("to_tsvector(name)") != ()


def test_an_unlisted_function_is_refused_rather_than_assumed_immutable() -> None:
    """Fail closed, because assuming immutability for an unknown name is the failure the check
    exists to prevent.

    The cost is real and is the right cost: somebody adding a function to an index has to add a
    line saying what the server declares about it, which is a decision made deliberately rather
    than a default taken silently. A volatile function is refused too, and separately, so the
    two findings do not collapse into one message that fits both.

    Delete this and the checker passes any expression naming a function nobody has looked
    up."""
    unknown = indexable("similarity(a.name, b.name)")
    assert len(unknown) == 1
    assert "no declared volatility" in unknown[0]

    volatile = indexable("random()")
    assert len(volatile) == 1
    assert "VOLATILE" in volatile[0]


def test_a_comma_inside_a_quoted_literal_is_not_an_argument_separator() -> None:
    """Arity is what decides the verdict, so miscounting arguments picks the wrong row.

    A comma inside `'a,b'` would make a one-argument call look like two, and for `to_tsvector`
    that is the difference between the form PostgreSQL refuses and the form it accepts. The
    scanner therefore skips quoted literals whole, doubled quotes included.

    Delete this and the arity is whatever the punctuation in a literal happens to be."""
    assert calls_in("to_tsvector('a,b')") == (("to_tsvector", 1),)
    assert calls_in("to_tsvector('it''s, fine', name)") == (("to_tsvector", 2),)
    assert calls_in("now()") == (("now", 0),)
    assert calls_in("er.immutable_unaccent(lower(name))") == (
        ("er.immutable_unaccent", 1),
        ("lower", 1),
    )


# ------------------------------------------------------ what migration 0021 actually builds
def test_every_index_the_migration_builds_is_one_postgres_would_accept() -> None:
    """**The leaf.** The wrapper exists so that an index over a folded name can be built, and
    the only way to know it can is to check the expression the migration executes against the
    rule the server applies.

    Read from the rendered SQL rather than from the file's constants, so an index defined in a
    constant that `upgrade` never runs proves nothing, and so a second index added later is
    checked by the same test without anybody remembering to extend it.

    Delete this and somebody adds an index over `unaccent(name)` directly, which fails at
    deploy time on a migration that passed review."""
    expressions = _index_expressions(rendered("upgrade"))

    assert expressions, "the migration built no index at all"
    for expression in expressions:
        assert indexable(expression) == (), expression


def test_the_index_is_built_on_the_wrapper_and_not_on_the_built_in() -> None:
    """The positive half of the test above: an expression with no functions in it also passes
    `indexable`, so "accepted" on its own would be satisfied by indexing the raw column.

    The claim is that the index is over the fold. Asserted on the parsed call rather than on a
    substring, because `er.immutable_unaccent(name)` contains the string `unaccent(name)` and a
    search for either one matches the other.

    Delete this and the migration can quietly index the unfolded name while every other test
    here goes on passing."""
    expressions = _index_expressions(rendered("upgrade"))

    assert expressions == ("er.immutable_unaccent(name)",)
    assert calls_in(expressions[0]) == (("er.immutable_unaccent", 1),)


def test_the_wrapper_the_migration_installs_is_the_one_the_normaliser_declares() -> None:
    """The migration copies the DDL rather than importing it, which is the house rule, and this
    is what turns the copy into a check rather than a duplication.

    Compared on the rendered statement with whitespace collapsed, so a reformatting is not a
    failure and a changed dictionary, a changed function name or a dropped label is.

    Delete this and the two drift: the module goes on documenting a wrapper that names the
    dictionary explicitly while the database holds one that resolves it through
    `search_path`."""
    declared = IMMUTABLE_UNACCENT_SQL.split(";", 1)[1].strip().rstrip(";")
    emitted = rendered("upgrade")

    assert _squash(declared) in _squash(emitted)
    assert "CREATE EXTENSION IF NOT EXISTS unaccent" in emitted


def test_the_table_calls_the_wrapper_immutable_only_because_the_migration_declares_it() -> None:
    """`PG_VOLATILITY` says what the server declares, and for our own function the server
    declares whatever this migration told it.

    That is the one row in the table with a source inside this repository, so the two are tied
    together here: drop the word IMMUTABLE from the wrapper and the row becomes a claim about a
    function that no longer makes it. Without this the index check would go on passing over a
    function PostgreSQL would refuse.

    Delete this and the label can be lost in a reformat while the volatility table still says
    the wrapper is immutable."""
    module = migration()

    assert PG_VOLATILITY[("er.immutable_unaccent", 1)] is Volatility.IMMUTABLE
    assert re.search(r"\bIMMUTABLE\b", module.WRAPPER)
    assert "er.immutable_unaccent" in module.WRAPPER
    assert "regdictionary" in module.WRAPPER


def test_the_downgrade_removes_what_it_built_and_leaves_the_extension_alone() -> None:
    """An extension is shared and this migration cannot know what came to depend on it.

    The index and the function are this migration's, in that order because the index depends on
    the function. Dropping the extension would remove something the migration asked for rather
    than something it owns, which is the same distinction 0020's downgrade draws about the `er`
    schema.

    Delete this and a downgrade takes `unaccent` away from whatever else started using it."""
    emitted = rendered("downgrade")

    assert "DROP INDEX IF EXISTS er.ix_alias_name_folded" in emitted
    assert "DROP FUNCTION IF EXISTS er.immutable_unaccent(text)" in emitted
    assert emitted.index("DROP INDEX") < emitted.index("DROP FUNCTION")
    assert "DROP EXTENSION" not in emitted


def test_the_migration_follows_the_one_that_built_the_tables_it_indexes() -> None:
    """The index is on `er.alias`, which 0020 creates, so the chain has to run in that order.

    A revision that came before its table would fail on a fresh database and pass on every
    developer machine where the tables already exist, which is the shape of failure that
    reaches production.

    Delete this and a renumbering leaves an index looking for a table that does not exist
    yet."""
    module = migration()

    assert module.revision == "0021"
    assert module.down_revision == "0020"
    assert "er.alias" in rendered("upgrade")


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
def test_the_migration_creates_no_table_and_therefore_grants_and_policies_nothing(
    direction: str,
) -> None:
    """Every migration here that adds a table enables row-level security on it. This one adds
    none, and the check is that it also adds no grant and no policy: an index inherits the
    policies on the table it is built over, and a GRANT appearing in a migration that creates
    nothing to grant on would be a widening nobody asked for.

    Delete this and a later edit adds a table here without the policy block 0020 established,
    because this file is where an author would learn the pattern from and there is none in
    it."""
    emitted = rendered(direction)

    assert "CREATE TABLE" not in emitted
    assert "GRANT" not in emitted
    assert "CREATE POLICY" not in emitted
    assert "ENABLE ROW LEVEL SECURITY" not in emitted
