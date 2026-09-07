"""What an install starting from nothing builds, and what it is allowed to read to do it.

M41.2.1 asks that the migrations build every schema, table, index, constraint, trigger and
row-level security policy from an empty database, and M41.2.3 asks that no install step
depends on a Verz database, dump, backup or export. Both are properties of a whole tree
rather than of one file, which is why they are here and not in
`brain.ops.migration_policy`, where the per-migration rules live.

**The half that needs a database and the half that does not are different questions and are
answered in different places.** What a migration *declares* is readable from the source with
no PostgreSQL anywhere: which revisions exist, whether they form one chain reaching an empty
database, which schemas they create, which extensions they require, and whether every table
they create lands in a schema they also create. What a migration *produces* is only knowable
by running it, and running it is what the CI job does. This module is deliberately the first
half only, and it says so rather than implying it covers both: see
`A_DECLARATION_IS_NOT_A_SCHEMA`.

**The chain is the part nobody checks and the part that breaks an install from empty.** An
upgrade on a live database starts from whatever revision it is on and applies what is left,
so a second root or a fork in the middle is invisible: nothing on that machine ever walks
past it. An install from empty walks the whole thing. A tree with two roots has two
migrations claiming to be first and Alembic refuses to resolve a head; a tree with a gap has
a revision naming a parent that does not exist. Neither shows up in any test that starts from
a database that already exists, which is every test until this one.

**And what the install reads is the other half of "from empty".** Building the schema from
nothing is worth nothing if the next step restores somebody else's data into it. The rule is
narrow enough to be a hard gate: nothing under `src` may import from `tests`, and no install
artefact may name a dump, a restore or a backup as an input. The first of those is not
hypothetical. `brain.seed` imported `tests.fixtures.company` until 2026-09-07, and the image
does not copy `tests`, so `make seed` on a client's install was a `ModuleNotFoundError`. What
it would have written if it had worked is worse than the failure: the fixture is Verz's own
org chart with a canary in every restricted field. See
`AN_INSTALL_STEP_READING_A_TEST_FIXTURE_IS_AN_INSTALL_STEP_READING_SOMEBODY_ELSES_COMPANY`.

Task ids: M41.2.1, M41.2.3
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Final

from brain.db import EXTENSIONS, SCHEMAS
from brain.ops.migration_policy import tables_created

REPO: Final = Path(__file__).resolve().parents[3]
VERSIONS: Final = REPO / "migrations" / "versions"

#: Why this module reads declarations and not a database.
A_DECLARATION_IS_NOT_A_SCHEMA: Final = (
    "Reading the migrations tells you what the migrations say. It does not tell you that "
    "PostgreSQL accepted them, that a generated column's expression was immutable enough to "
    "be stored, or that an index built. Only running them says that, and CI runs them "
    "against an empty database on every commit. So this module is the half that can be "
    "checked on a laptop with no PostgreSQL on it, and naming the half it is not covering is "
    "part of being that half honestly."
)

#: Why a second root or a gap is a finding rather than an Alembic problem.
AN_UPGRADE_FROM_A_LIVE_DATABASE_NEVER_WALKS_THE_WHOLE_CHAIN: Final = (
    "A deploy applies the revisions between where the database is and head, so a break "
    "earlier than that is never traversed and never reported. An install from empty "
    "traverses all of them. That is why a tree can be broken for months on every running "
    "system and discovered by the first client, which is the failure M41 exists to prevent."
)

#: Why an install step that reads a test fixture is the failure this rule is written for.
AN_INSTALL_STEP_READING_A_TEST_FIXTURE_IS_AN_INSTALL_STEP_READING_SOMEBODY_ELSES_COMPANY: Final = (
    "A test fixture is one company written to break a permission model: canary values, a "
    "lapsed contractor, a real org chart. It is also not in the image, because the Dockerfile "
    "copies src, migrations and docs and not tests. So an install step importing one either "
    "fails on the client's server or, if somebody helpfully adds the directory to the image, "
    "succeeds and writes another company's people into theirs. Both outcomes are the same "
    "mistake and the second is the one nobody notices."
)

#: What the built image contains, from the Dockerfile's own COPY lines. Anything under `src`
#: importing outside this set is importing something the running system does not have.
SHIPPED_TOP_LEVEL: Final[frozenset[str]] = frozenset({"src", "migrations", "docs", "ops"})

#: Files that are part of installing rather than of developing. Read as text and checked for
#: a reference to somebody else's data.
INSTALL_ARTEFACTS: Final[tuple[str, ...]] = (
    "Dockerfile",
    "Makefile",
    "alembic.ini",
    "docker-compose*.yml",
    "ops/*.sh",
    "ops/deploy/*",
    "ops/vps/*",
)

#: Ways of naming somebody else's database as an input. `pg_dump` is here as well as
#: `pg_restore`, because a step that takes a dump is a step somebody wrote a restore for.
RESTORE_SHAPED: Final[re.Pattern[str]] = re.compile(
    r"\b(pg_dump|pg_restore|pg_basebackup)\b|\.(dump|bak)\b|\bCOPY\s+\w+\s+FROM\b",
    re.IGNORECASE,
)


class InstallError(Exception):
    """Raised when the tree cannot describe an install from empty at all."""


@dataclass(frozen=True)
class Revision:
    """One migration, as the chain sees it."""

    #: The file, for a finding that points somewhere.
    name: str
    revision: str
    down_revision: str | None


@dataclass(frozen=True)
class InstallPlan:
    """Everything an install from empty would build, as the migrations declare it.

    Counts and names rather than DDL. What this is for is comparison: against
    `brain.db.SCHEMAS`, against `brain.db.EXTENSIONS`, and in CI against the database the
    migrations actually produced. A plan carrying rendered DDL would be a second copy of the
    migrations, which is the thing `brain.ops.schema_check` was written to stop being.
    """

    revisions: tuple[Revision, ...]
    schemas: frozenset[str]
    extensions: frozenset[str]
    tables: tuple[str, ...]
    indexes: tuple[str, ...]
    secured: frozenset[str]

    @property
    def root(self) -> Revision | None:
        """The revision an empty database starts at, or None when there is not exactly one."""
        roots = [one for one in self.revisions if one.down_revision is None]
        return roots[0] if len(roots) == 1 else None

    def lines(self) -> tuple[str, ...]:
        """What an install builds, for whoever is about to run one."""
        return (
            f"{len(self.revisions)} revision(s) from empty",
            f"{len(self.schemas)} schema(s): {', '.join(sorted(self.schemas))}",
            f"{len(self.extensions)} extension(s): {', '.join(sorted(self.extensions))}",
            f"{len(self.tables)} table(s), {len(self.indexes)} index(es)",
            f"{len(self.secured)} table(s) with row-level security enabled",
        )


def _constant_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _module_assignment(tree: ast.Module, name: str) -> ast.expr | None:
    """The value assigned to a module-level name, or None.

    Module level only. A revision identifier assigned inside a function would not be read by
    Alembic either, so finding one there and treating it as the answer would make this module
    agree with a file Alembic disagrees with.
    """
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
        if isinstance(node, ast.AnnAssign):
            target_name = node.target
            if isinstance(target_name, ast.Name) and target_name.id == name:
                return node.value
    return None


#: How many renderings one interpolated statement may produce. A migration writing one
#: statement per schema is nine; anything past this is a shape nobody here writes, and
#: rendering it would be this module guessing rather than reading.
MAX_RENDERINGS: Final = 64


def _string_values(node: ast.expr | None) -> tuple[str, ...]:
    """A module-level name's possible string values: one for a string, many for a sequence."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return (node.value,)
    if isinstance(node, ast.Tuple | ast.List):
        values = [one.value for one in node.elts if isinstance(one, ast.Constant)]
        if values and all(isinstance(one, str) for one in values):
            return tuple(str(one) for one in values)
    return ()


def _bindings(tree: ast.Module) -> dict[str, tuple[str, ...]]:
    """Every name in this migration that stands for one or more literal strings.

    **Without this the whole module reads 0001 as building nothing.** The foundation
    migration creates its schemas as `op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")`
    inside `for schema in SCHEMAS`, which is the right way to write it and leaves no literal
    naming a schema anywhere in the file. A reader that only looks at string constants
    therefore reports that nine schemas are missing, and the version of this module that did
    exactly that is why this function exists.

    Two sources: a module-level assignment of a string or a sequence of strings, and a `for`
    loop whose iterator is one of those. `reversed(...)` is unwrapped because a downgrade
    walks the list backwards and is still naming the same schemas.
    """
    found: dict[str, tuple[str, ...]] = {}
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        values = _string_values(getattr(node, "value", None))
        if values:
            for target in targets:
                if isinstance(target, ast.Name):
                    found[target.id] = values

    for loop in ast.walk(tree):
        if not isinstance(loop, ast.For) or not isinstance(loop.target, ast.Name):
            continue
        source: ast.expr = loop.iter
        if (
            isinstance(source, ast.Call)
            and isinstance(source.func, ast.Name)
            and source.func.id in {"reversed", "sorted", "tuple", "list"}
            and source.args
        ):
            source = source.args[0]
        if isinstance(source, ast.Name) and source.id in found:
            found[loop.target.id] = found[source.id]
        elif direct := _string_values(source):
            found[loop.target.id] = direct
    return found


def _render(node: ast.JoinedStr, bindings: dict[str, tuple[str, ...]]) -> list[str]:
    """One f-string as every statement it could be, given what its names stand for.

    A name nothing binds renders as an empty string rather than as a marker, so a statement
    whose object is genuinely unknown produces text that matches no pattern here and is
    quietly not counted. That direction is the safe one: this module reports what it can see
    an install building, and something it cannot resolve is a schema it will report missing,
    which is a finding somebody reads rather than a silent pass.
    """
    parts: list[tuple[str, ...]] = []
    for piece in node.values:
        if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
            parts.append((piece.value,))
        elif isinstance(piece, ast.FormattedValue):
            inner = piece.value
            parts.append(bindings.get(inner.id, ("",)) if isinstance(inner, ast.Name) else ("",))
        else:
            parts.append(("",))
    total = 1
    for one in parts:
        total *= len(one)
    if total > MAX_RENDERINGS:
        return []
    return ["".join(combination) for combination in product(*parts)]


def _statements(text: str) -> list[str]:
    """Every SQL-shaped string in a migration, interpolations resolved, upper-cased.

    Docstrings are included, unlike in `brain.ops.migration_policy._sql_literals`, and the
    difference is deliberate: this reads for schema and extension *names* to build a picture
    of the install rather than for a statement that would be executed. What is checked
    against prose is nothing: `plan_gaps` compares the names found here against
    `brain.db.SCHEMAS` and `brain.db.EXTENSIONS`, so a schema discussed in a comment and
    created nowhere is still reported as created nowhere.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        msg = f"a migration that will not parse cannot be part of an install: {exc}"
        raise InstallError(msg) from exc
    bindings = _bindings(tree)
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(" ".join(node.value.split()).upper())
        elif isinstance(node, ast.JoinedStr):
            out.extend(" ".join(one.split()).upper() for one in _render(node, bindings))
    return out


#: `CREATE SCHEMA [IF NOT EXISTS] <name>`, however a migration spells it.
#:
#: **The negative lookahead is load-bearing and the first version had no reason to think so.**
#: `IF NOT EXISTS` is optional, so against the fragment `CREATE SCHEMA IF NOT EXISTS`, which
#: is exactly what an unresolved interpolation renders to, the optional group is skipped and
#: the name group happily captures `IF`. The plan then reported a schema called `if` and an
#: extension called `if`, and both were sitting in the first run of this module's output.
_CREATE_SCHEMA = re.compile(
    r"CREATE\s+SCHEMA\s+(?:IF\s+NOT\s+EXISTS\s+)?(?!IF\s+NOT\s+EXISTS\b)([A-Z_][A-Z0-9_]*)"
)

#: `CREATE EXTENSION [IF NOT EXISTS] <name>`, with or without quotes round the name. Same
#: lookahead, for the same reason.
_CREATE_EXTENSION = re.compile(
    r"CREATE\s+EXTENSION\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?!IF\s+NOT\s+EXISTS\b)\"?([A-Z_][A-Z0-9_]*)\"?"
)

#: `ALTER TABLE <schema>.<table> ENABLE ROW LEVEL SECURITY`.
_ENABLE_RLS = re.compile(
    r"ALTER\s+TABLE\s+([A-Z_][A-Z0-9_]*\.[A-Z_][A-Z0-9_]*)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY"
)


def read_plan(versions: Path = VERSIONS) -> InstallPlan:
    """Read the whole migration tree into one description of the install it performs."""
    revisions: list[Revision] = []
    schemas: set[str] = set()
    extensions: set[str] = set()
    tables: list[str] = []
    indexes: list[str] = []
    secured: set[str] = set()

    for path in sorted(versions.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            msg = f"{path.name} will not parse: {exc}"
            raise InstallError(msg) from exc

        identifier = _constant_str(_module_assignment(tree, "revision"))
        if identifier is None:
            msg = f"{path.name} declares no revision identifier, so nothing can order it"
            raise InstallError(msg)
        revisions.append(
            Revision(
                name=path.name,
                revision=identifier,
                down_revision=_constant_str(_module_assignment(tree, "down_revision")),
            )
        )

        for statement in _statements(text):
            schemas.update(one.lower() for one in _CREATE_SCHEMA.findall(statement))
            extensions.update(one.lower() for one in _CREATE_EXTENSION.findall(statement))
            secured.update(one.lower() for one in _ENABLE_RLS.findall(statement))

        tables.extend(f"{schema}.{table}" for schema, table in tables_created(text))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create_index"
                and node.args
            ):
                named = _constant_str(node.args[0])
                if named is not None:
                    indexes.append(named)

    return InstallPlan(
        revisions=tuple(revisions),
        schemas=frozenset(schemas),
        extensions=frozenset(extensions),
        tables=tuple(tables),
        indexes=tuple(indexes),
        secured=frozenset(secured),
    )


def chain_gaps(plan: InstallPlan) -> tuple[str, ...]:
    """Everything about the revision order that stops an install from empty resolving.

    See `AN_UPGRADE_FROM_A_LIVE_DATABASE_NEVER_WALKS_THE_WHOLE_CHAIN` for why none of these
    is caught by a deploy.
    """
    findings: list[str] = []
    known = {one.revision for one in plan.revisions}

    if len(known) != len(plan.revisions):
        seen: set[str] = set()
        for one in plan.revisions:
            if one.revision in seen:
                findings.append(f"{one.name}: revision {one.revision!r} is declared twice")
            seen.add(one.revision)

    roots = [one for one in plan.revisions if one.down_revision is None]
    if not roots:
        findings.append(
            "no revision has down_revision None, so nothing claims to run against an empty "
            f"database. {AN_UPGRADE_FROM_A_LIVE_DATABASE_NEVER_WALKS_THE_WHOLE_CHAIN}"
        )
    elif len(roots) > 1:
        named = ", ".join(sorted(one.name for one in roots))
        findings.append(
            f"{len(roots)} revisions claim to be first ({named}); a head cannot resolve"
        )

    for one in plan.revisions:
        if one.down_revision is not None and one.down_revision not in known:
            findings.append(
                f"{one.name}: names parent {one.down_revision!r}, which no revision declares, "
                "so the chain has a gap an install from empty walks straight into"
            )

    parents = [one.down_revision for one in plan.revisions if one.down_revision is not None]
    for parent in sorted(set(parents)):
        if parents.count(parent) > 1:
            children = ", ".join(
                sorted(one.name for one in plan.revisions if one.down_revision == parent)
            )
            findings.append(f"{parent!r} has more than one child ({children}); the chain forks")

    return tuple(findings)


def plan_gaps(plan: InstallPlan) -> tuple[str, ...]:
    """Everything an install from empty would not build that the code expects to exist.

    Compared against `brain.db`, which is where the schema list and the extension list are
    declared, rather than against a list written here. The two would drift the day somebody
    adds a schema, and the direction of the drift is the new one being forgotten, which is
    the direction nobody notices.
    """
    findings: list[str] = [*chain_gaps(plan)]

    for schema in sorted(set(SCHEMAS) - plan.schemas):
        findings.append(
            f"no migration creates the schema {schema!r}, which brain.db.SCHEMAS declares, so "
            "an install from empty has nowhere to put its tables"
        )
    for extension in sorted(set(EXTENSIONS) - plan.extensions):
        findings.append(
            f"no migration creates the extension {extension!r}, which brain.db.EXTENSIONS "
            "declares; the column that needs it fails at the moment it is first written"
        )
    for qualified in sorted(set(plan.tables)):
        schema = qualified.partition(".")[0]
        if schema and schema not in plan.schemas:
            findings.append(f"{qualified} is created in a schema no migration creates")
        if qualified.lower() not in plan.secured:
            findings.append(f"{qualified} is created and nothing enables row-level security on it")
    return tuple(findings)


def install_input_gaps(repo: Path = REPO) -> tuple[str, ...]:
    """Everything on the install path that reads data belonging to somebody else (M41.2.3).

    Two rules, and both are about what the running system can reach rather than about what a
    developer can. See
    `AN_INSTALL_STEP_READING_A_TEST_FIXTURE_IS_AN_INSTALL_STEP_READING_SOMEBODY_ELSES_COMPANY`.
    """
    findings: list[str] = []

    source = repo / "src"
    for path in sorted(source.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        where = path.relative_to(repo).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            top = ""
            if isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
            else:
                top = node.names[0].name.split(".")[0]
            if top and top not in SHIPPED_TOP_LEVEL and top == "tests":
                findings.append(
                    f"{where}:{node.lineno}: imports {top!r}, which the image does not "
                    "contain. "
                    f"{AN_INSTALL_STEP_READING_A_TEST_FIXTURE_IS_AN_INSTALL_STEP_READING_SOMEBODY_ELSES_COMPANY}"
                )

    for pattern in INSTALL_ARTEFACTS:
        for path in sorted(repo.glob(pattern)):
            if not path.is_file():
                continue
            where = path.relative_to(repo).as_posix()
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                stripped = line.split("#", 1)[0]
                match = RESTORE_SHAPED.search(stripped)
                if match:
                    findings.append(
                        f"{where}:{number}: names {match.group(0)!r}, so installing depends "
                        "on a database somebody else already has"
                    )
    return tuple(findings)


def install_gaps(repo: Path = REPO) -> tuple[str, ...]:
    """Both halves, for the sweep and for anything else that wants one answer."""
    plan = read_plan(repo / "migrations" / "versions")
    return (*plan_gaps(plan), *install_input_gaps(repo))


def main() -> int:
    """`python -m brain.ops.install_from_empty`."""
    try:
        findings = install_gaps()
    except InstallError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    if findings:
        print("an install from empty would not work:", file=sys.stderr)
        for one in findings:
            print(f"  {one}", file=sys.stderr)
        return 1
    for line in read_plan().lines():
        print(f"ok: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
