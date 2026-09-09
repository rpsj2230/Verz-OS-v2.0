"""What the rolling-deploy check can prove, and where it stops.

Two halves and they are here for different reasons.

The first half asks the twenty three migrations in this repository, because a static reader
of SQL is only worth what it says about real files: `0022` and `0023` widen a check
constraint and are the worked example, `0015` replaces one written as a regular expression
and is the example of the boundary, `0002` builds seven tables through helper functions the
reader has to follow, and `0001` runs against an empty database with no release before it.

The second half asks synthetic bodies, because every finding worth having is a shape no
migration here has yet: a dropped column, a rename, a not-null column with no default, a
unique index on a table that was already there. A guard tested only against a corpus that
never trips it is a guard nobody has watched fire.

**Both halves matter and the second is the one that would rot.** The first would keep passing
if `changes_in` returned nothing at all, which is why every rule below is asserted against a
body written to break it and a sibling body written not to.

Task ids: M30.2.6
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from brain.deployment.compatibility import (
    A_NARROWING_ON_A_TABLE_THIS_MIGRATION_CREATED_IS_NOT_A_NARROWING,
    MOST_UNROLLED_ROWS,
    VERSIONS,
    WHAT_THIS_CHECK_CANNOT_SEE,
    Change,
    Verdict,
    breaking_changes,
    changes_in,
    check_all,
    main,
    unreadable_changes,
)

REPO = Path(__file__).resolve().parents[2]


def _source(name: str) -> str:
    return (VERSIONS / name).read_text(encoding="utf-8")


def _migration(upgrade: str, downgrade: str = "    pass") -> str:
    """A migration file with a predecessor, which is the only kind this check judges."""
    return (
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        'revision = "9001"\n'
        'down_revision = "9000"\n'
        "def upgrade() -> None:\n"
        f"{upgrade}\n"
        "def downgrade() -> None:\n"
        f"{downgrade}\n"
    )


def _verdicts(text: str) -> list[Verdict]:
    return [one.verdict for one in changes_in(text)]


def _rules(changes: tuple[Change, ...]) -> set[str]:
    return {one.rule for one in changes}


# ------------------------------------------------------- the migrations in this repository
def test_no_migration_here_breaks_the_release_before_it() -> None:
    """The claim the gate makes, asked of the files the gate actually guards.

    Delete this and the module can be wired into CI while disagreeing with the repository it
    is wired into, which is a red build nobody can attribute and the reason it would be
    switched off rather than read.
    """
    findings = {
        name: [str(one) for one in changes if one.verdict is Verdict.BREAKING]
        for name, changes in check_all().items()
    }
    assert not any(findings.values()), findings


def test_widening_a_check_constraint_is_safe_and_narrowing_the_same_one_is_not() -> None:
    """`0022`, read forwards and backwards. The whole design in one assertion.

    Its own docstring says the migration is safe in one direction and not the other: applied
    before the code that writes `compose_change`, the new schema accepts everything the old
    code writes; reversed without reverting the code, the old schema rejects what the new code
    writes. A check that could not tell those two apart would be reading the file rather than
    the property, and every widening ever written has this shape.

    Delete this and the two directions can collapse into one answer, which is the single
    mistake that would make the whole module worthless while leaving it green.
    """
    text = _source("0022_compose_change_action.py")

    forwards = changes_in(text)
    assert "constraint widened" in _rules(forwards)
    assert Verdict.BREAKING not in [one.verdict for one in forwards]

    backwards = changes_in(text, applying="downgrade", reversing="upgrade")
    narrowed = [one for one in backwards if one.verdict is Verdict.BREAKING]
    assert [one.rule for one in narrowed] == ["constraint narrowed"]
    assert "compose_change" in narrowed[0].detail


def test_a_constraint_written_as_a_regular_expression_is_unreadable_and_never_safe() -> None:
    """`0015` is the boundary, and it is the file that caught the first version of this module.

    It replaces four check constraints whose predicate is `slug ~ '<pattern>'`, correcting a
    mangled pattern that had made the constrained tables reject every write. Whether the
    corrected pattern accepts everything the mangled one did is a question about two regular
    expressions, and no reading of the migration answers it. The first version of this module
    rendered both f-strings with a `?` placeholder, which made them compare equal and returned
    safe: the one file here that genuinely cannot be read was the one it was most confident
    about.

    Delete this and that failure comes back silently, because every other test in this file
    passes with the placeholder in place.
    """
    text = _source("0015_slug_grammar.py")
    unreadable = unreadable_changes(text)

    assert not breaking_changes(text)
    assert _rules(unreadable) == {"constraint predicate this cannot order"}
    # One per row of the migration's own CONSTRAINED tuple, which is what proves the reader
    # unrolled the loop rather than judging it once with every table's name at the same time.
    assert len(unreadable) == _rows_of_constrained("0015_slug_grammar.py")
    assert all("~" in one.detail for one in unreadable)


def test_the_reader_follows_the_helpers_that_build_a_migrations_tables() -> None:
    """`0002` creates seven tables through module-level helpers, and `upgrade` itself holds
    five `op` calls out of the sixty this reader finds.

    A reader that stopped at the function it was pointed at would find no tables at all, so
    every policy and index that migration enables would look like a restriction on a table
    that was already there: measured with the created-here rule switched off, `0002` alone
    produces twenty two findings. The assertion is on the verdicts and on the size of what was
    read, because a body read as five operations and a body read as sixty are the two
    outcomes, and the wrong one is the quiet one.

    Delete this and the reader can quietly stop following calls, at which point every
    migration that builds its schema through helpers passes by having been read as empty.
    """
    text = _source("0002_core_tables.py")
    changes = changes_in(text)

    assert not breaking_changes(text)
    assert "restriction on a table created here" in _rules(changes)
    assert len(changes) > 50, "a body read as almost empty is a body that was not followed"


def test_the_first_revision_is_safe_because_there_is_no_release_before_it() -> None:
    """`0001` builds its `ALTER ROLE ... PASSWORD` through the driver connection.

    That statement cannot be read from the source and, on any other file, would be reported
    unreadable. On the first revision there is no previous release to be compatible with: it
    runs against an empty database on an install. Reporting it would be a permanent unreadable
    line in every run for a file that cannot break anything.

    Delete this and the shortcut can be removed without anything noticing, which puts a
    finding nobody can act on at the top of the report for ever.
    """
    changes = changes_in(_source("0001_foundation.py"))
    assert [one.rule for one in changes] == ["first revision"]
    assert changes[0].verdict is Verdict.SAFE


@pytest.mark.parametrize("named", ["0015", "0001"])
def test_every_migration_the_stated_limits_name_still_behaves_that_way(named: str) -> None:
    """The prose in `WHAT_THIS_CHECK_CANNOT_SEE` names two files, and it has to keep being true.

    A boundary written down once and never re-measured is the drift this repository has
    already had: four documents agreed with each other about `intersect` and none of them with
    the code. The limits are the deliverable here, so the two they cite are asserted rather
    than trusted.

    Delete this and the limits become a paragraph that was accurate on the day it was written.
    """
    assert any(named in limit for limit in WHAT_THIS_CHECK_CANNOT_SEE)
    path = next(one for one in sorted(VERSIONS.glob("*.py")) if one.name.startswith(named))
    changes = changes_in(path.read_text(encoding="utf-8"))
    if named == "0001":
        assert [one.rule for one in changes] == ["first revision"]
    else:
        assert any(one.verdict is Verdict.UNREADABLE for one in changes)


def _rows_of_constrained(name: str) -> int:
    """How many rows the migration's `CONSTRAINED` tuple holds, read from the file itself.

    An external anchor for `MOST_UNROLLED_ROWS`: the count comes out of the migration rather
    than out of this test, so it moves when the migration does.
    """
    tree = ast.parse(_source(name))
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue
        targets = [node.target] if isinstance(node, ast.AnnAssign) else list(node.targets)
        if not any(isinstance(one, ast.Name) and one.id == "CONSTRAINED" for one in targets):
            continue
        assert isinstance(node.value, ast.Tuple)
        return len(node.value.elts)
    raise AssertionError(f"{name} no longer declares CONSTRAINED")


def test_the_unrolling_limit_is_large_enough_for_the_migrations_here() -> None:
    """`MOST_UNROLLED_ROWS` compared against a figure that comes from somewhere else.

    A constant asserted against itself is green for every value it could hold, which cost
    three authors an afternoon here. This compares it against the longest tuple any migration
    in this repository loops over while placing a constraint, which is what the limit has to
    clear for the four channel migrations to be readable at all.

    Delete this and the limit can be lowered to one, at which point every constraint placed in
    a loop stops being read and the whole file comes back safe by having been skipped.
    """
    assert _rows_of_constrained("0015_slug_grammar.py") <= MOST_UNROLLED_ROWS


# ------------------------------------------------------------------- the shapes, on bodies
def test_a_dropped_column_breaks_the_release_that_still_selects_it() -> None:
    """The plainest finding there is, and no migration here performs it in an upgrade.

    Delete this and the drop can stop being classified, which is the finding the whole module
    exists for.
    """
    changes = breaking_changes(
        _migration('    op.drop_column("chunk", "embedding_model", schema="know")')
    )
    assert [one.rule for one in changes] == ["op.drop_column"]


def test_a_renamed_column_breaks_the_release_that_reads_the_old_name() -> None:
    """A rename is a drop and an add to everything still running.

    `brain.ops.migration_policy` already refuses a rename written as a drop plus an add, on a
    different ground: that it destroys data on a populated table. This is the other ground and
    it fires on the correct spelling, which that rule deliberately passes.

    Delete this and `alter_column(new_column_name=...)` becomes the way to rename a column
    without either check having an opinion.
    """
    body = '    op.alter_column("chunk", "model", new_column_name="embedding_model", schema="know")'
    assert [one.rule for one in breaking_changes(_migration(body))] == ["column renamed"]


def test_a_not_null_column_with_no_default_breaks_the_previous_release_insert() -> None:
    """The old code's INSERT names no such column, so the row is rejected.

    Delete this and the one shape that fails on the very first write after a deploy stops
    being classified.
    """
    body = (
        '    op.add_column("chunk", sa.Column("kind", sa.String(8), nullable=False), schema="know")'
    )
    assert [one.rule for one in breaking_changes(_migration(body))] == [
        "not-null column with no default"
    ]


def test_the_same_column_with_a_default_is_accepted() -> None:
    """The sibling. A guard tested only by its refusals is satisfied by refusing everything.

    Delete this and `add_column` can be classified as breaking unconditionally, which makes
    the check red on the next perfectly ordinary column somebody adds.
    """
    body = (
        '    op.add_column("chunk", sa.Column("kind", sa.String(8), nullable=False, '
        'server_default="text"), schema="know")'
    )
    assert not breaking_changes(_migration(body))
    assert _verdicts(_migration(body)) == [Verdict.SAFE]


def test_a_column_widened_to_nullable_is_accepted_and_narrowed_to_not_null_is_not() -> None:
    """One pair, because the two differ by a single keyword and go opposite ways.

    Delete this and `nullable=` stops being read at all, which passes the narrowing by
    treating it the same as the widening.
    """
    widened = '    op.alter_column("chunk", "model", nullable=True, schema="know")'
    narrowed = '    op.alter_column("chunk", "model", nullable=False, schema="know")'
    assert _verdicts(_migration(widened)) == [Verdict.SAFE]
    assert [one.rule for one in breaking_changes(_migration(narrowed))] == [
        "column narrowed to not null"
    ]


def test_a_restriction_on_a_table_this_migration_created_is_not_a_restriction() -> None:
    """The rule that makes the check quiet enough to be a gate, and its counter-case.

    A unique index on a table nobody could have written to yet restricts nothing. The same
    index on a table that was already there can reject a row the previous release is about to
    insert. Both bodies below are one line different.

    Delete this and one of two things happens: the rule is dropped and twenty two of the
    twenty three migrations here become findings, or it is widened and a real narrowing on a
    live table passes.
    """
    fresh = _migration(
        '    op.create_table("chunk", schema="know")\n'
        '    op.create_index("uq", "chunk", ["digest"], unique=True, schema="know")'
    )
    existing = _migration(
        '    op.create_index("uq", "chunk", ["digest"], unique=True, schema="know")'
    )

    assert not breaking_changes(fresh)
    found = breaking_changes(existing)
    assert [one.rule for one in found] == ["restriction on a table that was already there"]
    assert A_NARROWING_ON_A_TABLE_THIS_MIGRATION_CREATED_IS_NOT_A_NARROWING in found[0].detail


def test_row_level_security_switched_on_over_an_existing_table_is_a_finding() -> None:
    """The same rule through raw SQL rather than through an alembic operation.

    Every table in this repository is created and secured in one migration, which
    `brain.ops.migration_policy` requires. A migration that enabled it on a table already
    carrying rows would hide those rows from the previous release, which reads as data loss
    and is the quietest possible outage.

    Delete this and the raw-SQL half of the rule goes unexercised, which is the half every
    migration here actually uses.
    """
    fresh = _migration(
        '    op.execute("CREATE TABLE know.chunk (id text)")\n'
        '    op.execute("ALTER TABLE know.chunk ENABLE ROW LEVEL SECURITY")'
    )
    existing = _migration('    op.execute("ALTER TABLE know.chunk ENABLE ROW LEVEL SECURITY")')
    assert not breaking_changes(fresh)
    assert [one.rule for one in breaking_changes(existing)] == [
        "restriction on a table that was already there"
    ]


@pytest.mark.parametrize(
    ("statement", "verdict"),
    [
        ("GRANT SELECT ON know.chunk TO brain_app", Verdict.SAFE),
        ("REVOKE SELECT ON know.chunk FROM brain_app", Verdict.BREAKING),
        ("DROP TABLE know.chunk", Verdict.BREAKING),
        ("DROP FUNCTION know.digest()", Verdict.BREAKING),
        ("ALTER TABLE know.chunk DROP COLUMN model", Verdict.BREAKING),
        ("ALTER TABLE know.chunk RENAME COLUMN model TO embedding_model", Verdict.BREAKING),
        ("ALTER TABLE know.chunk ALTER COLUMN model SET NOT NULL", Verdict.BREAKING),
        ("ALTER TABLE know.chunk ALTER COLUMN model DROP NOT NULL", Verdict.SAFE),
        ("ALTER TABLE know.chunk ADD COLUMN model text", Verdict.SAFE),
        ("ALTER TABLE know.chunk ADD COLUMN model text NOT NULL", Verdict.BREAKING),
        ("CREATE TABLE know.chunk (id text)", Verdict.SAFE),
        ("CREATE INDEX ix_chunk ON know.chunk (model)", Verdict.SAFE),
        ("CREATE UNIQUE INDEX uq_chunk ON know.chunk (digest)", Verdict.BREAKING),
        (
            "CREATE POLICY chunk_live ON know.chunk FOR ALL TO brain_app USING (true)",
            Verdict.BREAKING,
        ),
        ("CREATE POLICY chunk_live ON chunk FOR ALL TO brain_app USING (true)", Verdict.UNREADABLE),
        ("DROP INDEX know.ix_chunk", Verdict.SAFE),
        ("ALTER TABLE know.chunk ALTER COLUMN model TYPE varchar(8)", Verdict.UNREADABLE),
        ("VACUUM FULL know.chunk", Verdict.UNREADABLE),
    ],
)
def test_a_statement_is_read_as_what_it_does(statement: str, verdict: Verdict) -> None:
    """One row per statement shape, written out rather than taken from the module's own lists.

    Parametrising from `_REMOVING_HEADS` would compare the module against itself and pass for
    every list it could hold, which is exactly how `hubspot.CEILING_NAME` survived being
    repointed at another connector. These are typed here so that removing a head from the
    module makes a named row go red.

    Delete this and the three statement lists become unchecked, at which point a `REVOKE` in
    an upgrade reads as a statement nobody classified.
    """
    body = f'    op.execute("{statement}")'
    assert _verdicts(_migration(body)) == [verdict], statement


def test_a_semicolon_inside_a_function_body_does_not_split_the_statement() -> None:
    """PL/pgSQL is full of semicolons and none of them ends the `CREATE FUNCTION`.

    The first version of this module split on every `;` and reported forty fragments of
    function bodies as statements it could not classify: `END IF`, `RETURN NULL`, `v_part
    TEXT`. A report of forty things nobody wrote is a report nobody reads.

    **The drop after the function body is what makes this a test and not a smoke check.**
    Without it a splitter that never closes the dollar quote passes too: the whole string
    becomes one statement, it still starts with `CREATE FUNCTION`, and it still reads safe.
    The second statement is the one that has to be seen, and it is the one a swallowed
    function body would hide.

    Delete this and the splitter can go back to `sql.split(";")`, which makes every migration
    that defines a trigger function unreadable, or stop closing the quote, which makes
    everything after one invisible.
    """
    body = (
        '    op.execute("""\n'
        "CREATE FUNCTION obs.stamp() RETURNS trigger AS $$\n"
        "BEGIN\n"
        "  IF NEW.at IS NULL THEN NEW.at := now(); END IF;\n"
        "  RETURN NEW;\n"
        "END;\n"
        "$$ LANGUAGE plpgsql;\n"
        "DROP TABLE know.other;\n"
        '""")'
    )
    assert _verdicts(_migration(body)) == [Verdict.SAFE, Verdict.BREAKING]


def test_a_semicolon_inside_a_quoted_value_does_not_split_the_statement() -> None:
    """The other half of the splitter, and the cheaper mistake of the two.

    A predicate or a default holding a semicolon is ordinary SQL. Split there, the first
    fragment still classifies as whatever it started as and the tail becomes a statement
    nobody wrote, which puts a permanent unreadable line in the report for a file that is
    fine.

    Delete this and quote handling can be dropped, at which point the report grows a line per
    literal semicolon in the whole migration history.
    """
    body = "    op.execute(\"INSERT INTO know.chunk (note) VALUES ('a;b')\")"
    assert _verdicts(_migration(body)) == [Verdict.SAFE]


def test_two_statements_in_one_string_are_two_statements() -> None:
    """The positive side of the splitter: it has to split where a statement really ends.

    A splitter that never split would read a migration's whole DDL as one statement, take its
    verdict from the first word, and pass everything after it.

    Delete this and the dollar-quote and quote tests above are satisfied by a function that
    never splits at all.
    """
    body = '    op.execute("CREATE TABLE know.chunk (id text); DROP TABLE know.other")'
    assert _verdicts(_migration(body)) == [Verdict.SAFE, Verdict.BREAKING]


def test_a_migration_with_no_downgrade_is_read_rather_than_skipped() -> None:
    """The counterpart body is where a replaced constraint's old predicate comes from.

    A file with no `downgrade` at all is a real shape, and `migration_policy` reports it as a
    deploy with no way back rather than refusing to read it. This check has to go on reading
    the upgrade when there is nothing to compare a constraint against, and a constraint with
    no counterpart is a finding rather than a crash.

    Delete this and the missing-function case can start raising, which turns a migration that
    is merely one-way into a check that cannot run at all.
    """
    text = (
        "from alembic import op\n"
        'revision = "9001"\n'
        'down_revision = "9000"\n'
        "def upgrade() -> None:\n"
        '    op.create_check_constraint("kind", "chunk", "kind IN (\'a\')", schema="know")\n'
    )
    changes = changes_in(text)
    assert [one.rule for one in changes] == ["constraint added to a table that was already there"]
    assert changes[0].verdict is Verdict.BREAKING


def test_a_constraint_that_moves_to_another_column_cannot_be_ordered() -> None:
    """Two IN lists on two different columns say nothing about each other.

    `action IN ('a')` becoming `kind IN ('a', 'b')` looks like a widening if the comparison
    reads only the lists. It is not a widening at all: the old predicate stops applying and a
    new one starts, and whether the previous release can violate the new one is a question
    about a column the old constraint never mentioned.

    Delete this and the item comparison runs across columns, which is a permissive answer
    reached by ignoring half of each predicate.
    """
    text = _migration(
        '    op.create_check_constraint("c", "chunk", "kind IN (\'a\', \'b\')", schema="know")',
        '    op.create_check_constraint("c", "chunk", "action IN (\'a\')", schema="know")',
    )
    changes = unreadable_changes(text)
    assert [one.rule for one in changes] == ["constraint predicate this cannot order"]


def test_a_constraint_on_a_table_created_here_needs_no_predecessor() -> None:
    """The sibling of the finding above, and the case every new table hits.

    A check constraint on a table this migration created restricts nothing the previous
    release could write, so it needs no comparison and must not be reported for lacking one.

    Delete this and every migration that creates a table with a check constraint becomes a
    finding, which is most of them.
    """
    text = _migration(
        '    op.create_table("chunk", schema="know")\n'
        '    op.create_check_constraint("c", "chunk", "kind IN (\'a\')", schema="know")'
    )
    assert not breaking_changes(text)
    assert "restriction on a table created here" in _rules(changes_in(text))


def test_a_constraint_whose_predicate_cannot_be_read_is_unreadable() -> None:
    """A predicate assembled from something outside this file.

    Delete this and a constraint built at run time reads as one with no predicate at all,
    which is a narrowing passing by being illegible.
    """
    text = _migration('    op.create_check_constraint("c", "chunk", predicate(), schema="know")')
    changes = changes_in(text)
    assert [one.rule for one in changes] == ["check constraint with no readable predicate"]
    assert changes[0].verdict is Verdict.UNREADABLE


def test_a_constraint_this_cannot_place_is_unreadable_in_both_directions() -> None:
    """A constraint whose table or name is an argument nothing here resolves.

    Both halves matter: the upgrade's call cannot be classified, and the downgrade's cannot be
    recorded as the predecessor of anything, so a later comparison must not silently use the
    wrong one.

    Delete this and an unplaceable constraint reads as a fresh restriction on an existing
    table, which is a finding with the wrong reason attached.
    """
    text = (
        "from alembic import op\n"
        'revision = "9001"\n'
        'down_revision = "9000"\n'
        "def add(name: str) -> None:\n"
        '    op.create_check_constraint(name, "chunk", "kind IN (\'a\')", schema="know")\n'
        "def upgrade() -> None:\n"
        '    add("c")\n'
        "def downgrade() -> None:\n"
        '    add("c")\n'
    )
    changes = changes_in(text)
    assert [one.rule for one in changes] == ["check constraint this cannot place"]
    assert changes[0].verdict is Verdict.UNREADABLE


@pytest.mark.parametrize(
    ("call", "verdict", "rule"),
    [
        ('op.create_table("chunk", schema="know")', Verdict.SAFE, "op.create_table"),
        (
            'op.create_foreign_key("fk", "chunk", "doc", ["a"], ["b"], schema="know")',
            Verdict.BREAKING,
            "restriction on a table that was already there",
        ),
        (
            'op.create_index("uq", "chunk", ["d"], unique=True)',
            Verdict.UNREADABLE,
            "restriction on no table this can name",
        ),
        (
            'op.create_index("ix", "chunk", ["d"], schema="know")',
            Verdict.SAFE,
            "op.create_index",
        ),
        ('op.add_column("chunk", COLUMN, schema="know")', Verdict.UNREADABLE, None),
        (
            'op.alter_column("chunk", "d", type_=sa.String(8), schema="know")',
            Verdict.UNREADABLE,
            "column type changed",
        ),
        (
            'op.alter_column("chunk", "d", server_default="x", schema="know")',
            Verdict.UNREADABLE,
            "column altered in a way this cannot order",
        ),
    ],
)
def test_an_operation_is_read_as_what_it_does(
    call: str, verdict: Verdict, rule: str | None
) -> None:
    """One row per alembic operation, on a body where nothing else is happening.

    A non-unique index on a table that was already there is the row that keeps the unique
    flag honest: without it, reading `unique=` at all could be dropped and every index would
    be judged as a restriction, which is green on the corpus here because every index in it
    sits on a table its own migration created.

    Delete this and half the operations this module claims to classify are claimed and never
    exercised.
    """
    changes = changes_in(_migration(f"    {call}"))
    assert [one.verdict for one in changes] == [verdict], call
    if rule is not None:
        assert changes[0].rule == rule


def test_a_loop_over_names_places_a_restriction_once_per_name() -> None:
    """A restriction inside a loop is as many restrictions as the loop has values.

    Read as one, the name holds several values at once, no table can be pinned and the whole
    loop comes back as something nobody could place. That is not wrong, but it is weaker than
    the file allows: unrolled, each pass names its own table and each is judged.

    Delete this and the single-name unrolling can be removed, which turns provable findings
    into a single line saying the reader could not tell.
    """
    text = (
        "from alembic import op\n"
        'revision = "9001"\n'
        'down_revision = "9000"\n'
        'TABLES = ("chunk", "document")\n'
        "def upgrade() -> None:\n"
        "    for table in TABLES:\n"
        '        op.create_index("uq", table, ["d"], unique=True, schema="know")\n'
        "def downgrade() -> None:\n"
        "    pass\n"
    )
    changes = breaking_changes(text)
    assert len(changes) == 2
    assert all(one.rule == "restriction on a table that was already there" for one in changes)


def test_a_row_this_cannot_read_does_not_become_a_shorter_loop() -> None:
    """A tuple of rows where one value is not a string.

    Read as a row anyway, the loop places a constraint on a table called `1`. Dropped from the
    list, the loop is read as one pass shorter and the row it skipped is never judged. Neither
    is acceptable, so the whole iterable falls back to the flattened reading, where the table
    cannot be pinned and the call says so.

    Delete this and a malformed declaration turns into a confident finding about a table that
    does not exist.
    """
    text = (
        "from alembic import op\n"
        'revision = "9001"\n'
        'down_revision = "9000"\n'
        'ROWS = (("know", 1),)\n'
        "def upgrade() -> None:\n"
        "    for schema, table in ROWS:\n"
        '        op.create_check_constraint("c", table, "kind IN (\'a\')", schema=schema)\n'
        "def downgrade() -> None:\n"
        "    pass\n"
    )
    changes = changes_in(text)
    assert [one.rule for one in changes] == ["check constraint this cannot place"]


def test_a_tuple_of_statements_is_read_through_the_name_that_holds_it() -> None:
    """Every migration here keeps its SQL in a module-level tuple and executes it by name.

    Delete this and the tuple branch of the name resolver goes unexercised, which is the
    branch every `RLS` and `GRANTS` declaration in `migrations/versions` depends on.
    """
    text = (
        "from alembic import op\n"
        'revision = "9001"\n'
        'down_revision = "9000"\n'
        'STATEMENTS = ("CREATE TABLE know.chunk (id text)", "DROP TABLE know.other")\n'
        "def upgrade() -> None:\n"
        "    op.execute(STATEMENTS)\n"
        "def downgrade() -> None:\n"
        "    pass\n"
    )
    assert _verdicts(text) == [Verdict.SAFE, Verdict.BREAKING]


def test_a_tuple_holding_one_thing_this_cannot_read_is_unreadable_whole() -> None:
    """Half a tuple of statements is worse than none of it.

    Returning the readable half would report a migration as clean while one of its statements
    was never looked at, and the one nobody looked at is the one this exists to find.

    Delete this and a tuple with an unresolvable element quietly shrinks.
    """
    text = (
        "from alembic import op\n"
        'revision = "9001"\n'
        'down_revision = "9000"\n'
        'STATEMENTS = ("CREATE TABLE know.chunk (id text)", build())\n'
        "def upgrade() -> None:\n"
        "    op.execute(STATEMENTS)\n"
        "def downgrade() -> None:\n"
        "    pass\n"
    )
    assert [one.rule for one in changes_in(text)] == ["op.execute with no readable argument"]


def test_a_figure_a_statement_embeds_is_rendered_rather_than_making_it_unreadable() -> None:
    """`0020` bounds a recursive view with `{MAX_FORWARD_DEPTH}` and is otherwise plain DDL.

    A reader that could only substitute strings would call that whole `CREATE VIEW`
    unreadable for the sake of one integer, and an unreadable line nobody can act on is how a
    report full of real findings gets skimmed.

    Delete this and the figures map can be dropped, at which point every statement embedding
    a number joins the list of things this cannot read.
    """
    text = (
        "from alembic import op\n"
        'revision = "9001"\n'
        'down_revision = "9000"\n'
        "DEPTH = 5\n"
        "def upgrade() -> None:\n"
        '    op.execute(f"CREATE VIEW know.deep AS SELECT 1 WHERE depth < {DEPTH}")\n'
        "def downgrade() -> None:\n"
        "    pass\n"
    )
    assert _verdicts(text) == [Verdict.SAFE]


def test_a_literal_a_statement_embeds_is_rendered_too() -> None:
    """The same rule for a value written into the f-string rather than named above it.

    Delete this and a substitution that is already a constant reads as one nothing can
    resolve, which is the strictest possible answer to the easiest possible question.
    """
    body = '    op.execute(f"CREATE VIEW know.deep AS SELECT 1 WHERE depth < {5}")'
    assert _verdicts(_migration(body)) == [Verdict.SAFE]


def test_a_statement_run_through_a_connection_is_unreadable_rather_than_safe() -> None:
    """The escape hatch every static reader has, reported instead of ignored.

    `op.execute` can be read. A statement built at run time and pushed through the driver
    cannot, and `0001` does exactly that. Anywhere but the first revision that has to show up
    in the report, because the alternative is a green run over a file whose only schema change
    was invisible.

    Delete this and a migration can do anything at all as long as it does it through
    `op.get_bind()`.
    """
    body = (
        "    conn = op.get_bind()\n"
        '    conn.exec_driver_sql("ALTER TABLE know.chunk DROP COLUMN model")'
    )
    changes = changes_in(_migration(body))
    assert Verdict.UNREADABLE in [one.verdict for one in changes]
    assert "a statement executed outside op" in _rules(changes)


def test_an_operation_this_module_does_not_classify_is_unreadable_rather_than_safe() -> None:
    """Deny by default, which is the direction `migration_policy` chose for the same reason.

    A new alembic operation, or one nobody here has used, must not pass by not being on a
    list. It costs a line in this module and that line is the review.

    Delete this and the classifier's `else` branch becomes a silent pass for every operation
    somebody adds after today.
    """
    changes = changes_in(_migration('    op.rename_index("a", "b", schema="know")'))
    assert [one.verdict for one in changes] == [Verdict.UNREADABLE]
    assert changes[0].rule == "op.rename_index is not classified here"


def test_an_execute_whose_argument_cannot_be_read_is_reported() -> None:
    """SQL assembled from something this reader cannot resolve.

    Delete this and a statement built by a helper call reads as no statement at all, which is
    a migration passing by being invisible.
    """
    body = "    op.execute(build_the_statement())"
    changes = changes_in(_migration(body))
    assert [one.rule for one in changes] == ["op.execute with no readable argument"]
    assert changes[0].verdict is Verdict.UNREADABLE


def test_a_file_that_does_not_parse_is_reported_and_not_passed_over() -> None:
    """A migration with a syntax error has no readable upgrade in any sense that matters.

    `migration_policy._downgrade_state` made the same choice for the same reason: the one file
    nobody can run must not become the one file nobody checks.

    Delete this and a `SyntaxError` becomes an empty list of changes, which is a clean pass.
    """
    changes = changes_in("def upgrade() -> None\n    pass\n")
    assert [one.verdict for one in changes] == [Verdict.UNREADABLE]
    assert changes[0].rule == "the file does not parse"


# --------------------------------------------------------------------------- the gate
def test_the_gate_passes_on_this_repository_and_fails_on_a_dropped_column(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both exit codes, because a gate that cannot fail is a report.

    The failing case is a directory of one migration that drops a column, so the assertion is
    about the exit code and the stderr line rather than about anything in this repository,
    which is deliberately clean.

    Delete this and `main` can return 0 unconditionally with every other test in this file
    still green: they all call `changes_in`, and none of them runs the thing CI runs.
    """
    assert main() == 0

    (tmp_path / "0002_gone.py").write_text(
        _migration('    op.drop_column("chunk", "model", schema="know")'),
        encoding="utf-8",
        newline="\n",
    )
    assert main(tmp_path) == 1
    assert "op.drop_column" in capsys.readouterr().err


def test_a_passing_run_prints_every_limit_and_says_how_much_it_could_not_read(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A boundary nobody is shown is a claim, and the green line is where a reader stops.

    The output of a passing run has to carry what the pass does not cover, or "0 that break
    the previous release" reads as "nothing can break". The count of unread statements is on
    the same line as the count of clean ones for the same reason.

    Delete this and the limits can be dropped from the output while remaining in the module,
    which is the shape of a document nobody reads.
    """
    assert main() == 0
    printed = capsys.readouterr().out
    for limit in WHAT_THIS_CHECK_CANNOT_SEE:
        assert limit in printed
    unread = sum(len(unreadable_changes(text)) for text in _every_migration())
    assert f"{unread} this check cannot read" in printed
    assert unread > 0, "a corpus with nothing unreadable cannot show that the count is real"


def _every_migration() -> list[str]:
    return [path.read_text(encoding="utf-8") for path in sorted(VERSIONS.glob("*.py"))]


def test_continuous_integration_runs_this_check_on_a_live_step() -> None:
    """A gate nothing runs is a module, and this one is only worth having as a gate.

    Parsed rather than searched, for the reason `tests/unit/test_ci_workflow.py` gives at
    length: a substring search over YAML matches a commented-out line as happily as a live
    one, and a commented-out gate is exactly what this catches. It sits in this file rather
    than in that one because the claim belongs beside the module making it, and because a
    third agent is editing the workflow's tests this week.

    Delete this and the step can be removed from the workflow without one test going red:
    every other test here calls the module directly.
    """
    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    commands = [
        str(step["run"])
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if "run" in step
    ]
    live = [
        line.strip()
        for command in commands
        for line in command.splitlines()
        if not line.strip().startswith("#")
    ]
    assert any("brain.deployment.compatibility" in line for line in live), (
        "CI no longer runs the migration compatibility check"
    )
