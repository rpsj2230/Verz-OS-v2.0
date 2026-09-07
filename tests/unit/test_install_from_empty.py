"""An install that starts from nothing, read from what the repository declares.

Everything here runs without PostgreSQL, which is the point of the module under test: the
other half of M41.2.1 is a database CI builds and this laptop does not have. What can be
proved from the source is proved here, and the boundary is named rather than blurred.

Task ids: M41.2.1, M41.2.3
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.db import EXTENSIONS, SCHEMAS
from brain.ops.install_from_empty import (
    InstallError,
    InstallPlan,
    Revision,
    chain_gaps,
    install_gaps,
    install_input_gaps,
    plan_gaps,
    read_plan,
)

NL = "\n"


def _revision(name: str, identifier: str, parent: str | None) -> Revision:
    return Revision(name=name, revision=identifier, down_revision=parent)


def _plan(*revisions: Revision, **over: object) -> InstallPlan:
    """A plan with everything satisfied, so a test can break exactly one thing."""
    base: dict[str, object] = {
        "revisions": revisions,
        "schemas": frozenset(SCHEMAS),
        "extensions": frozenset(EXTENSIONS),
        "tables": (),
        "indexes": (),
        "secured": frozenset(),
    }
    base.update(over)
    return InstallPlan(**base)  # type: ignore[arg-type]


def _migration(body: str, *, revision: str = "0001", parent: str | None = None) -> str:
    parent_line = "None" if parent is None else f'"{parent}"'
    return (
        f'revision = "{revision}"{NL}'
        f"down_revision = {parent_line}{NL}{NL}"
        f"def upgrade() -> None:{NL}{body}{NL}"
    )


def _versions(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "versions"
    root.mkdir()
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8", newline="\n")
    return root


# ------------------------------------------------------ the repository as it stands
def test_every_schema_the_code_expects_is_created_by_some_migration() -> None:
    """The schema list lives in `brain.db` and the creation lives in the migrations, and
    nothing has ever compared the two. `brain.ops.schema_check` compares the list against a
    running database, which answers the question after the install rather than before it.

    Deleting this test lets a schema be added to `brain.db.SCHEMAS` with no migration
    creating it, and the symptom is an install from empty that fails on the first table.
    """
    plan = read_plan()
    assert plan.schemas, "no schema was found at all, so this comparison proves nothing"
    assert set(SCHEMAS) <= plan.schemas, sorted(set(SCHEMAS) - plan.schemas)


def test_every_extension_the_code_expects_is_created_by_some_migration() -> None:
    """`vector`, `pg_trgm`, `fuzzystrmatch` and `unaccent` are declared in `brain.db` and
    created in 0001. An extension declared and never created fails at the moment the first
    column needing it is written, which on an install from empty is inside the migration
    that creates that column.

    Deleting this lets the two lists drift, in the direction of the new one being forgotten.
    """
    plan = read_plan()
    assert plan.extensions
    assert set(EXTENSIONS) <= plan.extensions, sorted(set(EXTENSIONS) - plan.extensions)


def test_the_revision_chain_in_this_repository_runs_from_empty_to_head_unbroken() -> None:
    """One root, no gaps, no fork. A deploy never walks the whole chain, so nothing else in
    this repository would notice any of the three; an install from empty walks all of it.

    Deleting this is how a fork survives: it is invisible on every running system and shows
    up at the first client.
    """
    plan = read_plan()
    assert chain_gaps(plan) == ()
    assert plan.root is not None
    assert plan.root.name.startswith("0001")


def test_every_table_the_migrations_create_is_secured_by_the_same_migrations() -> None:
    """The whole-tree view of the rule `brain.ops.migration_policy` applies per file. Both
    exist because they fail differently: the per-file rule names the migration to fix, and
    this one is the count that has to come out equal.

    Deleting this leaves the tree-level property asserted nowhere, and a table secured in a
    migration other than its own would pass everything except a live database.
    """
    plan = read_plan()
    assert plan.tables
    assert {one.lower() for one in plan.tables} <= plan.secured


def test_this_repository_installs_without_reading_anything_it_does_not_ship() -> None:
    """The positive half of M41.2.3, and it was red until 2026-09-07: `brain.seed` imported
    `tests.fixtures.company`, which the image does not contain.

    Deleting this lets the import come back, and the failure it produces on a client's server
    reads like a packaging bug rather than like an install step reading another company.
    """
    assert install_input_gaps() == ()


def test_the_whole_gate_is_green_on_this_tree() -> None:
    """What the sweep runs. Kept separate from the parts above so a red one says which half
    broke rather than that something did.

    Deleting this lets `install_gaps` diverge from the functions it composes.
    """
    assert install_gaps() == ()


# ------------------------------------------------------ the chain, broken on purpose
def test_two_revisions_claiming_to_be_first_are_reported() -> None:
    """Alembic cannot resolve a head with two roots, and the error it gives names neither
    file usefully. Deleting this leaves the case detected only by running Alembic, which is
    the thing an install from empty is trying to do."""
    findings = chain_gaps(
        _plan(_revision("0001_a.py", "0001", None), _revision("0002_b.py", "0002", None))
    )
    assert any("claim to be first" in one for one in findings), findings


def test_a_revision_naming_a_parent_nobody_declares_is_reported() -> None:
    """A gap in the chain. The deploy that never walks that far is the reason it can sit
    there for months. Deleting this lets a deleted migration leave an orphan behind."""
    findings = chain_gaps(
        _plan(_revision("0001_a.py", "0001", None), _revision("0003_c.py", "0003", "0002"))
    )
    assert any("gap" in one for one in findings), findings


def test_a_fork_in_the_chain_is_reported() -> None:
    """Two migrations with the same parent is what a merge without a rebase produces, and it
    is the shape that makes `alembic upgrade head` ambiguous. Deleting this lets two branches
    of work land and only fail on a database nobody has built yet."""
    findings = chain_gaps(
        _plan(
            _revision("0001_a.py", "0001", None),
            _revision("0002_b.py", "0002", "0001"),
            _revision("0002_c.py", "0002b", "0001"),
        )
    )
    assert any("forks" in one for one in findings), findings


def test_a_repeated_revision_identifier_is_reported() -> None:
    """Two files claiming one identifier means whichever Alembic reads second is the one that
    exists. Deleting this lets a copied migration keep its parent's id, which reads as a
    missing migration rather than as a duplicated one."""
    findings = chain_gaps(
        _plan(_revision("0002_a.py", "0002", "0001"), _revision("0002_b.py", "0002", "0001"))
    )
    assert any("declared twice" in one for one in findings), findings


def test_a_chain_that_is_one_unbroken_line_reports_nothing() -> None:
    """The positive half. A chain check tested only by broken chains is satisfied by one that
    rejects every chain, and this one runs on every commit."""
    assert (
        chain_gaps(
            _plan(
                _revision("0001_a.py", "0001", None),
                _revision("0002_b.py", "0002", "0001"),
                _revision("0003_c.py", "0003", "0002"),
            )
        )
        == ()
    )


# ------------------------------------------------------ what the plan compares against
def test_a_schema_the_code_expects_and_no_migration_creates_is_reported() -> None:
    """The comparison that matters, driven rather than described. Deleting this leaves the
    schema rule asserted only by a tree that already satisfies it, which a function returning
    an empty tuple also satisfies."""
    plan = _plan(_revision("0001_a.py", "0001", None), schemas=frozenset(set(SCHEMAS) - {"chat"}))
    findings = plan_gaps(plan)
    assert any("'chat'" in one for one in findings), findings


def test_an_extension_the_code_expects_and_no_migration_creates_is_reported() -> None:
    """Same shape, different list. Deleting it leaves `EXTENSIONS` compared against nothing,
    and the failure it guards happens at the first insert into a vector column."""
    plan = _plan(
        _revision("0001_a.py", "0001", None), extensions=frozenset(set(EXTENSIONS) - {"vector"})
    )
    assert any("'vector'" in one for one in plan_gaps(plan)), plan_gaps(plan)


def test_a_table_created_in_a_schema_no_migration_creates_is_reported() -> None:
    """A table in a schema that does not exist is a migration that fails on an empty database
    and succeeds on every developer's, because theirs has the schema from an earlier run.

    Deleting this lets that difference stay invisible until a client installs.
    """
    plan = _plan(
        _revision("0001_a.py", "0001", None),
        tables=("nowhere.thing",),
        secured=frozenset({"nowhere.thing"}),
    )
    assert any("schema no migration creates" in one for one in plan_gaps(plan))


# ------------------------------------------------------ reading an interpolated statement
def test_a_schema_created_through_a_loop_variable_is_still_seen(tmp_path: Path) -> None:
    """The reader's whole reason for existing, and the bug the first version of it had.

    0001 creates its schemas as `op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")` inside
    `for schema in SCHEMAS`, which is the right way to write it and leaves no literal naming
    a schema anywhere in the file. The first version of this module read string constants
    only and reported that nine schemas were created by nobody.

    Deleting this test lets the interpolation reader be simplified away, and the module then
    reports the foundation migration as building nothing at all.
    """
    body = (
        "    for schema in SCHEMAS:"
        + NL
        + '        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")'
    )
    text = 'SCHEMAS = ("alpha", "beta")' + NL + _migration(body)
    plan = read_plan(_versions(tmp_path, {"0001_x.py": text}))
    assert plan.schemas == frozenset({"alpha", "beta"})


def test_a_statement_naming_no_schema_does_not_invent_one(tmp_path: Path) -> None:
    """`IF NOT EXISTS` is optional in the pattern, so an unresolved interpolation renders to
    `CREATE SCHEMA IF NOT EXISTS` and the name group captures `IF`. The first run of this
    module reported a schema called `if` and an extension called `if`, both of them in the
    output.

    Deleting this lets the lookahead be removed, and what comes back is a plan that claims to
    create a schema nothing creates, which is a false pass rather than a false failure.
    """
    body = '    op.execute(f"CREATE SCHEMA IF NOT EXISTS {mystery}")'
    plan = read_plan(_versions(tmp_path, {"0001_x.py": _migration(body)}))
    assert plan.schemas == frozenset()


def test_a_migration_that_will_not_parse_stops_the_plan_rather_than_shrinking_it(
    tmp_path: Path,
) -> None:
    """A file with a syntax error creates nothing this module can read, and reading past it
    would produce a plan that is quietly missing whatever that file built. Refusing is the
    outcome that cannot be mistaken for a clean tree.

    Deleting this lets a broken migration reduce the plan silently, and the sweep would then
    go green by reading less.
    """
    root = _versions(tmp_path, {"0001_x.py": "def upgrade( -> None:"})
    with pytest.raises(InstallError):
        read_plan(root)


def test_a_migration_with_no_revision_identifier_is_refused(tmp_path: Path) -> None:
    """Nothing can order a file that does not say which revision it is, so a plan built round
    one would describe a chain it cannot walk. Deleting this leaves the identifier optional
    and the chain checks reading `None` as a root."""
    root = _versions(tmp_path, {"0001_x.py": "def upgrade() -> None:" + NL + "    pass"})
    with pytest.raises(InstallError, match="no revision identifier"):
        read_plan(root)


# ------------------------------------------------------ what an install may read (M41.2.3)
def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    (tmp_path / "src").mkdir(exist_ok=True)
    return tmp_path


def test_a_module_under_src_that_imports_the_test_suite_is_reported(tmp_path: Path) -> None:
    """The bug that was here. `brain.seed` imported `tests.fixtures.company`, the image does
    not copy `tests`, and what the fixture holds is Verz's org chart with a canary in every
    restricted field.

    Deleting this test makes the import a one-line change again, and it is a change that
    looks like reuse.
    """
    repo = _repo(tmp_path, {"src/brain/seed.py": "from tests.fixtures.company import build"})
    findings = install_input_gaps(repo)
    assert any("src/brain/seed.py" in one for one in findings), findings


def test_a_module_under_src_importing_something_the_image_ships_is_not_reported(
    tmp_path: Path,
) -> None:
    """The positive half. A rule that fired on every import would be switched off within a
    day, and the ordinary case is a module importing another module.

    Deleting this leaves the rule provable only by its refusals.
    """
    repo = _repo(tmp_path, {"src/brain/seed.py": "from brain.demo import demo_rows"})
    assert install_input_gaps(repo) == ()


def test_an_install_step_that_restores_a_database_is_reported(tmp_path: Path) -> None:
    """ "Install from empty" means from empty. A step that restores a dump is an install that
    starts from whatever the dump held, which for the first client is the previous client's
    data.

    Deleting this lets a convenience line into the Makefile, and the convenience is exactly
    the one somebody reaches for when a fresh install is slow to populate.
    """
    repo = _repo(tmp_path, {"Makefile": "seed:" + NL + "\tpg_restore -d brain latest.dump"})
    findings = install_input_gaps(repo)
    assert any("pg_restore" in one for one in findings), findings


def test_a_comment_mentioning_a_restore_is_not_an_install_step(tmp_path: Path) -> None:
    """The runbooks explain what a restore is and why the install does not do one, and a rule
    that reported the explanation would be a rule people stop reading.

    Deleting this makes the check a plain text search, which fires on the documentation that
    exists to keep the rule.
    """
    repo = _repo(tmp_path, {"Makefile": "# never pg_restore into a fresh install" + NL + "all:"})
    assert install_input_gaps(repo) == ()
