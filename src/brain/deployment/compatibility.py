"""Whether a migration leaves a schema the release before it can still use.

A deploy is not an instant. The migrations run, and for as long as it takes the old
container to stop and the new one to answer, the **new schema is serving the old code**. On
a single-host install that window is the whole restart; behind a load balancer it is however
long the rollout takes. A migration that drops a column the previous release still selects,
renames one it writes, or narrows a constraint it can still violate turns that window into an
outage, and every check in this repository passes while it happens: the migration is valid
SQL, the models agree with it, the tests run against a database where only the new code
exists, and the failure needs two versions in the same room to appear at all.

**This is not `brain.ops.migration_policy` with more rules.** That module asks whether a
migration is well formed: reviewed, reversible, not a rename in disguise, not mixing schema
with data. Every one of its rules is about the file. This asks a question about two releases
at once, which is why it lives beside the delivery chain rather than beside the schema rules,
and why its answer is three-valued rather than pass or fail.

**The three verdicts, and why there are three.** A change is `SAFE` when the reading proves
it accepts everything the previous schema accepted, `BREAKING` when the reading proves it
does not, and `UNREADABLE` when the reading cannot decide. A two-valued check has to fold the
third case into one of the other two, and both foldings are wrong in a way that costs
somebody a Saturday: called safe, an unreadable narrowing ships silently under a green tick;
called breaking, the check is red on arrival and gets switched off, which
`brain.ops.sweeps` records happening. So the count of statements this check could not read is
printed on every run beside the count it could, and `WHAT_THIS_CHECK_CANNOT_SEE` says in
words where the reading stops. See
`A_STATEMENT_THIS_CHECK_CANNOT_READ_IS_REPORTED_AND_NEVER_PASSED`.

**The rule that makes it quiet enough to be a gate.** Almost every narrowing in this
repository is applied to a table the same migration has just created: a policy, a unique
index, a not-null column, a foreign key. None of those narrow anything, because the previous
release had no such table to narrow. So a narrowing is measured against the set of tables the
same body creates, and only a narrowing on a table that was already there is a finding. See
`A_NARROWING_ON_A_TABLE_THIS_MIGRATION_CREATED_IS_NOT_A_NARROWING`. Measured with the rule
switched off on 2026-09-09, thirteen of the twenty three migrations here are findings and
`0002` alone accounts for twenty two of them, which is a check nobody would keep.

**Where the previous predicate comes from is the migration's own downgrade.** A check
constraint replaced in `upgrade` is compared against the one `downgrade` puts back, because
that is the only record inside a single file of what the constraint used to say. It also
means one function answers both directions: `changes_in(text)` reads the upgrade against the
downgrade, and swapping the two arguments reads the rollback instead. `0022` and `0023` are
the worked example and their docstrings argue it themselves, widening a check constraint so
that the new schema accepts everything the old code writes while the old schema rejects what
the new code writes. Their upgrades come back `SAFE` and the same function called the other
way round comes back `BREAKING`, which is the shape of every widening ever written.

Rejected: comparing the migration against `brain.tables` to find out whether anything still
reads the dropped column. It answers a different question and reads as if it answered this
one. A column dropped by a migration and removed from the model in the same commit passes
that comparison and breaks the rolling deploy anyway, because the release that still selects
it is not in this checkout at all. The model comparison is worth having and
`tests/unit/test_tables.py` already has it.

Rejected: a per-migration escape hatch, some `BREAKS_PREVIOUS_RELEASE = "reason"` a file
could declare to buy itself a pass. There is no migration in this repository that needs one,
and a suppression that exists is a suppression that gets copied into the next file by
somebody who read the first as precedent. When one is genuinely needed the right move is a
two-release change, which is the actual answer to a column that has to go: stop reading it in
release N, drop it in release N plus one.

Task ids: M30.2.6
"""

from __future__ import annotations

import ast
import enum
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO: Final = Path(__file__).resolve().parents[3]
VERSIONS: Final = REPO / "migrations" / "versions"

#: Why the window exists at all, and why nothing else in the pipeline can see into it.
A_ROLLING_DEPLOY_RUNS_THE_NEW_SCHEMA_AGAINST_THE_OLD_CODE: Final = (
    "Migrations run before the new container answers, so for the length of the swap the "
    "previous release's code is issuing its own queries against the schema the new release "
    "asked for. On a single-host install that is the whole restart. Every other gate here "
    "tests one version against its own schema, so the pair is never in the same room and the "
    "failure only ever appears in production."
)

#: Why a narrowing on a brand new table is not a narrowing.
A_NARROWING_ON_A_TABLE_THIS_MIGRATION_CREATED_IS_NOT_A_NARROWING: Final = (
    "A policy, a unique index, a not-null column or a foreign key restricts what a table "
    "accepts, and on a table that arrived in the same migration it restricts nothing: the "
    "previous release never wrote to it and cannot start now. Measuring narrowings against "
    "the tables the same body creates is the difference between a check with no findings "
    "here and one with thirteen of twenty three migrations flagged for building a schema."
)

#: Why an unreadable statement is a third answer rather than a lenient second one.
A_STATEMENT_THIS_CHECK_CANNOT_READ_IS_REPORTED_AND_NEVER_PASSED: Final = (
    "A statement assembled at run time, a check constraint written as a regular expression, "
    "a DO block: each of these can narrow a schema and none of them can be read from the "
    "source. Counting them as safe makes a green run a claim the reading does not support, "
    "and counting them as breaking makes the check red the day it lands. So they are their "
    "own verdict, they are printed on every run, and the exit code is decided by the "
    "findings that were actually proven."
)

#: Why the first revision cannot break a release that does not exist.
THE_FIRST_REVISION_HAS_NO_PREVIOUS_RELEASE: Final = (
    "A migration with no `down_revision` runs against an empty database on an install, and "
    "there is no earlier release of the code to be compatible with. Everything it does is "
    "additive by construction, including the role and password statements 0001 builds "
    "through a driver connection, which no reading of the source could classify."
)

#: Where the reading stops. Printed on every run, because a limit nobody is told is a claim.
WHAT_THIS_CHECK_CANNOT_SEE: Final[tuple[str, ...]] = (
    "Whether the previous release actually used what was removed. Every removal is a "
    "finding, used or not, which is the direction a gate has to err in.",
    "A check constraint that is not a literal IN list. `0015` narrows and widens a regular "
    "expression and comes back unreadable, which is the honest answer.",
    "A statement built at run time, or executed through a connection rather than through "
    "`op`. `0001` does exactly that for the role password.",
    "A DO block, a trigger body, or a function redefined by CREATE OR REPLACE. Any of them "
    "can reject what the previous release wrote and none of them is DDL a reader can order.",
    "A column type widened or narrowed. `varchar(64)` to `varchar(200)` is safe and the "
    "reverse is not, and this check does not order types.",
    "A backfill that changes what a value means without changing the schema at all.",
    "Anything applied outside `migrations/versions/`: a statement run by hand, or by the "
    "application at startup.",
    "The other direction. That the new code works against the old schema is a different "
    "property, and it is what a rollback needs; ask for it by swapping this check's two "
    "function arguments.",
    "Performance. A dropped index is named by no query, so the previous release's SQL still "
    "runs; whether it still runs in time is a question about load.",
    "A dropped unique or primary key constraint. It widens what the table accepts and it "
    "removes the target an `ON CONFLICT` names, and which statements name one is a fact "
    "about the previous release's code rather than about this file.",
)


class Verdict(enum.StrEnum):
    """What the reading was able to prove about one operation."""

    #: Proven to accept everything the previous schema accepted.
    SAFE = "safe"
    #: Proven not to. The previous release's code can fail against this schema.
    BREAKING = "breaking"
    #: Not decidable from the source. See `WHAT_THIS_CHECK_CANNOT_SEE`.
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class Change:
    """One schema operation, and what the reading made of it.

    `rule` names the shape that was recognised rather than the verdict, so two findings with
    the same verdict and different causes do not read as duplicates, and `detail` carries the
    statement or call it came from. A finding that will not say which statement it is about
    is a finding somebody has to re-derive before they can act on it.
    """

    verdict: Verdict
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.verdict.value}: {self.rule}, {self.detail}"


# ------------------------------------------------------------------ reading the source

#: How many rows of a loop over a literal tuple this reader will unroll.
#:
#: Two hundred rather than unbounded, and rather than one. Unbounded lets a generated tuple
#: turn one file into a report nobody reads; refusing to unroll at all costs the four channel
#: migrations, whose constraint is placed on a table named by a loop variable and is provably
#: safe once that variable is read. A loop longer than this falls back to the flattened
#: reading, which is what the `RLS` tuples get and is enough for a statement that is already
#: literal.
MOST_UNROLLED_ROWS: Final = 200

#: A dollar-quoted body, which is where a function's own semicolons live.
_DOLLAR = re.compile(r"\$[A-Za-z_]*\$")

#: `col IN ('a', 'b')`, the one predicate shape two constraints can be ordered by.
_IN_LIST = re.compile(r"^(?P<column>[\w.]+)\s+IN\s*\((?P<items>[^()]*)\)$", re.IGNORECASE)

#: `schema.table`, as every statement in this repository qualifies it.
_QUALIFIED = r"[A-Za-z_][\w]*\.[A-Za-z_][\w]*"

_CREATE_TABLE = re.compile(rf"^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?({_QUALIFIED})", re.I)
_ALTER_TABLE = re.compile(rf"^ALTER\s+TABLE\s+(?:ONLY\s+)?({_QUALIFIED})\s+(?P<rest>.*)$", re.I)
_ON_TABLE = re.compile(rf"\bON\s+({_QUALIFIED})\b", re.IGNORECASE)


@dataclass(frozen=True)
class _Names:
    """What the names visible at one point hold. See `_substitution` for why there are two."""

    #: Name to the SQL text it could contribute.
    text: dict[str, tuple[str, ...]]
    #: Name to what it renders to inside an f-string, for the figures a statement embeds.
    numbers: dict[str, str]

    def with_local(self, bound: dict[str, tuple[str, ...]]) -> _Names:
        return _Names(text={**self.text, **bound}, numbers=self.numbers)


def _statements(sql: str) -> tuple[str, ...]:
    """One SQL string split into statements, respecting dollar quotes and literals.

    A plain `split(";")` tears every `CREATE FUNCTION` in this repository into fragments of
    PL/pgSQL, and the fragments then classify as unreadable statements that nobody wrote. The
    first version of this module did exactly that and reported forty of them.
    """
    out: list[str] = []
    buffer: list[str] = []
    index = 0
    tag: str | None = None
    quoted = False
    while index < len(sql):
        char = sql[index]
        if tag is not None:
            if sql.startswith(tag, index):
                buffer.append(tag)
                index += len(tag)
                tag = None
                continue
            buffer.append(char)
            index += 1
            continue
        if quoted:
            buffer.append(char)
            quoted = char != "'"
            index += 1
            continue
        if char == "'":
            quoted = True
            buffer.append(char)
            index += 1
            continue
        opened = _DOLLAR.match(sql, index)
        if opened is not None:
            tag = opened.group(0)
            buffer.append(tag)
            index += len(tag)
            continue
        if char == ";":
            out.append("".join(buffer))
            buffer = []
            index += 1
            continue
        buffer.append(char)
        index += 1
    out.append("".join(buffer))
    return tuple(" ".join(one.split()) for one in out if one.strip())


def _strings_of(node: ast.expr, names: _Names) -> tuple[str, ...] | None:
    """Every string this expression could be, or None when it cannot be read.

    None and an empty tuple are different answers and the caller depends on the difference:
    empty means "this holds no SQL", None means "this may hold SQL nobody here can see".

    **An f-string with a substitution this cannot resolve is unreadable, and it is not
    rendered with a placeholder.** `brain.ops.migration_policy._sql_literals` renders `?` for
    each substitution, which is right there because it matches statement shapes. It is wrong
    here and it produced a false pass: `0015` writes its check constraint as
    `f"{column} ~ '{SLUG_SQL_PATTERN}'"` in both directions, and rendering both with `?`
    made the corrected pattern and the broken one it replaces compare equal, so the one
    migration in this repository that genuinely cannot be read came back safe.
    """
    if isinstance(node, ast.Constant):
        return (node.value,) if isinstance(node.value, str) else ()
    if isinstance(node, ast.Name):
        return names.text.get(node.id)
    if isinstance(node, ast.JoinedStr):
        rendered: list[str] = []
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                rendered.append(part.value)
                continue
            # The grammar admits nothing else here: `JoinedStr.values` holds constants and
            # substitutions and no third thing. Asserted rather than branched on, because a
            # branch nothing can reach is a branch no test can watch, and this file has
            # already been through one round of driving those to zero.
            assert isinstance(part, ast.FormattedValue)
            substituted = _substitution(part.value, names)
            if substituted is None:
                return None
            rendered.append(substituted)
        return ("".join(rendered),)
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        found: list[str] = []
        for element in node.elts:
            inner = _strings_of(
                element.value if isinstance(element, ast.Starred) else element, names
            )
            if inner is None:
                return None
            found.extend(inner)
        return tuple(found)
    return None


def _substitution(node: ast.expr, names: _Names) -> str | None:
    """What one `{...}` in an f-string renders to, or None when nothing here knows.

    **`numbers` is a separate map from `text` and it is only ever read here.** A migration
    interpolating a figure is ordinary: `0020` bounds its recursive view with
    `{MAX_FORWARD_DEPTH}`, and without this the whole `CREATE VIEW` comes back unreadable for
    the sake of one integer. Rendering that integer into `text` instead, so one map could do
    both jobs, is the version that is quietly wrong: `_one` reads `text` to decide whether a
    call passed `unique=True`, and a boolean constant stored there as `"True"` is not `True`,
    so a unique index would classify as an ordinary one and a real narrowing would pass.
    """
    if isinstance(node, ast.Constant):
        return format(node.value)
    if isinstance(node, ast.Name):
        held = names.text.get(node.id)
        if held is not None and len(held) == 1:
            return held[0]
        return names.numbers.get(node.id)
    return None


def _rows_of(
    node: ast.expr, rows: dict[str, tuple[tuple[str, ...], ...]]
) -> tuple[tuple[str, ...], ...] | None:
    """An iterable read as rows rather than as a flat list of strings.

    `for schema, table, name, column in CONSTRAINED` needs the four values that belong
    together, and flattening loses exactly that. Without it `0015` and the four channel
    migrations name no table this reader can place, and four widenings that are provably safe
    come back unreadable instead.

    **A row this cannot read is None for the whole iterable rather than a shorter list.** A
    loop read as three rows when it has four places a constraint on three tables and says
    nothing at all about the fourth, and saying nothing is what a pass looks like. None sends
    the caller to the flattened reading, which is worse at naming tables and does not invent
    a row that is not there.
    """
    if isinstance(node, ast.Name):
        return rows.get(node.id)
    if not isinstance(node, ast.Tuple | ast.List):
        return None
    out: list[tuple[str, ...]] = []
    for element in node.elts:
        if isinstance(element, ast.Tuple | ast.List):
            values = [one.value for one in element.elts if isinstance(one, ast.Constant)]
            if len(values) != len(element.elts) or not all(isinstance(x, str) for x in values):
                return None
            out.append(tuple(str(one) for one in values))
        elif isinstance(element, ast.Constant) and isinstance(element.value, str):
            out.append((element.value,))
        else:
            return None
    return tuple(out)


def _module_names(tree: ast.Module) -> tuple[_Names, dict[str, tuple[tuple[str, ...], ...]]]:
    """What every module-level name holds, which is where every migration keeps its SQL.

    Three maps over the same assignments, because they answer three different questions and
    one map answering all three would have to lie about two of them. `text` answers "what SQL
    could this name contribute", which `op.execute` needs; `numbers` answers "what does this
    render to inside an f-string", which is read nowhere else; and the rows map answers "what
    goes together", which a loop over a tuple of tuples needs and a flat list destroys.
    """
    text: dict[str, tuple[str, ...]] = {}
    numbers: dict[str, str] = {}
    rows: dict[str, tuple[tuple[str, ...], ...]] = {}
    names = _Names(text=text, numbers=numbers)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            bound = [one.id for one in node.targets if isinstance(one, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            bound = [node.target.id]
            value = node.value
        else:
            continue
        found = _strings_of(value, names)
        shaped = _rows_of(value, rows)
        figure = (
            format(value.value)
            if isinstance(value, ast.Constant) and isinstance(value.value, int | float)
            else None
        )
        for name in bound:
            if found:
                text[name] = found
            if shaped:
                rows[name] = shaped
            if figure is not None:
                numbers[name] = figure
    return names, rows


@dataclass(frozen=True)
class _Call:
    """One `op.<something>(...)` reached from the function being read."""

    name: str
    node: ast.Call
    #: The statements `op.execute` was handed, empty for every other call.
    sql: tuple[str, ...]
    #: False when the argument could not be resolved to text.
    readable: bool
    #: The names in scope where the call sits, so a loop's values can still be read.
    names: _Names


def _keyword(node: ast.Call, name: str) -> ast.expr | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _one(node: ast.expr | None, names: _Names) -> object:
    """The single value this expression holds here, or None when it holds several or none.

    Reads `text` and deliberately not `numbers`. A keyword this is asked about is a flag or a
    name, never a figure, and answering `unique=SOME_COUNT` with a string would turn a
    narrowing into an ordinary index. See `_substitution`.
    """
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        held = names.text.get(node.id, ())
        return held[0] if len(held) == 1 else None
    return None


def _calls(tree: ast.Module, function: str) -> tuple[tuple[_Call, ...], bool]:
    """Every operation reachable from one top-level function, and whether all of it was read.

    **Helper functions are followed, and that is not a refinement.** `0002` creates seven
    tables through seven module-level helpers and its `upgrade` body contains no
    `create_table` at all, so a reader that stopped at the function it was pointed at would
    report a migration building the whole core schema as doing nothing. A reader that reports
    nothing is a reader that passes everything.

    The second element is False when a statement was executed through something other than
    `op`. `0001` builds its `ALTER ROLE ... PASSWORD` through the driver connection, which is
    correct there and is unreadable here.
    """
    functions = {one.name: one for one in tree.body if isinstance(one, ast.FunctionDef)}
    start = functions.get(function)
    if start is None:
        return (), True
    outer, rows = _module_names(tree)
    found: list[_Call] = []
    entered: set[str] = set()
    complete = True

    def bindings(target: ast.expr, row: tuple[str, ...]) -> dict[str, tuple[str, ...]] | None:
        """One row's values bound to this loop's target, or None to fall back to flattening.

        Both target shapes, and the single-name one earns its place on a loop whose body is
        not `op.execute`. For `for statement in RLS: op.execute(statement)` the two readings
        are the same statements in the same order, because the flattened binding hands every
        string to one call. For `for name in NAMES: op.create_index(name, ..., unique=True)`
        they are not: flattened, the name holds several values at once, the table cannot be
        pinned to one and the whole loop comes back as a single statement nobody can place.
        """
        if isinstance(target, ast.Name) and len(row) == 1:
            return {target.id: (row[0],)}
        if isinstance(target, ast.Tuple) and len(target.elts) == len(row):
            named = [one.id for one in target.elts if isinstance(one, ast.Name)]
            if len(named) == len(row):
                return {name: (value,) for name, value in zip(named, row, strict=True)}
        return None

    def visit(node: ast.AST, names: _Names) -> None:
        nonlocal complete
        if isinstance(node, ast.For):
            visit(node.iter, names)
            shaped = _rows_of(node.iter, rows)
            if shaped is not None and 0 < len(shaped) <= MOST_UNROLLED_ROWS:
                # Unrolled, one pass per row. A loop's values are what make the call literal,
                # and a binding that held every row's value at once would place a constraint
                # on four tables at the same time.
                for row in shaped:
                    bound = bindings(node.target, row)
                    if bound is None:
                        break
                    for child in [*node.body, *node.orelse]:
                        visit(child, names.with_local(bound))
                else:
                    return
            values = _strings_of(node.iter, names)
            inner = names
            if values and isinstance(node.target, ast.Name):
                inner = names.with_local({node.target.id: values})
            for child in [*node.body, *node.orelse]:
                visit(child, inner)
            return
        if isinstance(node, ast.Call):
            callee = node.func
            if isinstance(callee, ast.Name) and callee.id in functions:
                if callee.id not in entered:
                    entered.add(callee.id)
                    visit(functions[callee.id], outer)
            elif isinstance(callee, ast.Attribute):
                receiver = callee.value
                is_op = isinstance(receiver, ast.Name) and receiver.id == "op"
                if is_op and callee.attr == "execute":
                    text = _strings_of(node.args[0], names) if node.args else None
                    if text is None:
                        found.append(_Call("execute", node, (), readable=False, names=names))
                    else:
                        statements = tuple(one for piece in text for one in _statements(piece))
                        found.append(_Call("execute", node, statements, readable=True, names=names))
                elif is_op:
                    found.append(_Call(callee.attr, node, (), readable=True, names=names))
                elif callee.attr in {"execute", "exec_driver_sql", "execute_options"}:
                    complete = False
        for inside in ast.iter_child_nodes(node):
            visit(inside, names)

    visit(start, outer)
    return tuple(found), complete


# ------------------------------------------------------------------ classifying one body


def _tables_created(calls: tuple[_Call, ...]) -> frozenset[str]:
    """Every `schema.table` this body creates, from both spellings.

    Read before anything is classified rather than as the body is walked, because the
    ordering inside a migration says nothing: a policy written above the table it protects
    still protects a table the previous release never saw.
    """
    made: set[str] = set()
    for call in calls:
        if call.name == "create_table":
            name = _one(call.node.args[0], call.names) if call.node.args else None
            schema = _one(_keyword(call.node, "schema"), call.names)
            if isinstance(name, str) and isinstance(schema, str):
                made.add(f"{schema}.{name}".lower())
        for statement in call.sql:
            found = _CREATE_TABLE.match(statement)
            if found is not None:
                made.add(found.group(1).lower())
    return frozenset(made)


def _accepts_at_least(previous: str, current: str) -> bool | None:
    """Whether `current` accepts everything `previous` did, or None when it cannot be told.

    Decidable for one predicate shape and one only: `column IN (literals)`, which is what
    every widening in this repository is and what `tables.identity.one_of` renders. Anything
    else, a regular expression or a range or a conjunction, is None. A comparison that
    guessed at those would be the check claiming more than it can see, and the guess would be
    wrong in the permissive direction, which is the direction nobody notices.

    Rejected: a fast path returning True when the two predicates are the same text. It looks
    free and it is a claim: two identical regular expressions really do accept the same
    values, but a constraint recreated with the same predicate under a different name is the
    only shape that reaches it, and nothing here does that. An identical IN list already
    compares equal by the set comparison below, so the fast path bought one answer nobody
    asks for and a branch no test could reach.
    """
    before = _IN_LIST.match(previous.strip())
    after = _IN_LIST.match(current.strip())
    if before is None or after is None:
        return None
    if before.group("column").lower() != after.group("column").lower():
        return None
    was = {one.strip() for one in before.group("items").split(",") if one.strip()}
    now = {one.strip() for one in after.group("items").split(",") if one.strip()}
    return was <= now


def _check_predicates(calls: tuple[_Call, ...]) -> dict[tuple[str, str, str], str]:
    """Check constraints this body creates, keyed by schema, table and constraint name."""
    out: dict[tuple[str, str, str], str] = {}
    for call in calls:
        if call.name != "create_check_constraint" or len(call.node.args) < 3:
            continue
        name = _one(call.node.args[0], call.names)
        table = _one(call.node.args[1], call.names)
        schema = _one(_keyword(call.node, "schema"), call.names)
        condition = _strings_of(call.node.args[2], call.names)
        if not (isinstance(name, str) and isinstance(table, str) and isinstance(schema, str)):
            continue
        if condition and len(condition) == 1:
            out[(schema.lower(), table.lower(), name.lower())] = condition[0]
    return out


def _table_of(statement: str) -> str | None:
    """The `schema.table` a `CREATE ... ON <table>` statement restricts, unqualified aside.

    Only the `ON` form. An `ALTER TABLE` names its table in the head and `_from_alter` has
    already matched it there, so a second reading here would be a branch nothing reaches. An
    unqualified name is None rather than a guess: `public` is where anything that forgets to
    say otherwise ends up, and treating a bare name as a table this migration created is the
    permissive answer.
    """
    on = _ON_TABLE.search(statement)
    return on.group(1).lower() if on is not None else None


#: Statement heads that add and never take away. Deny by default: a head not listed here and
#: not recognised below is unreadable, which is the direction `migration_policy` chose for
#: the fast-lane grants and for the same reason.
_ADDITIVE_HEADS: Final[tuple[str, ...]] = (
    "CREATE SCHEMA",
    "CREATE EXTENSION",
    "CREATE TABLE",
    "CREATE INDEX",
    "CREATE FUNCTION",
    "CREATE TRIGGER",
    "CREATE VIEW",
    "CREATE MATERIALIZED VIEW",
    "CREATE SEQUENCE",
    "CREATE TYPE",
    "CREATE ROLE",
    "GRANT ",
    "COMMENT ON",
    "INSERT INTO",
    "ANALYZE",
)

#: Statement heads that take something away outright.
_REMOVING_HEADS: Final[tuple[str, ...]] = (
    "DROP TABLE",
    "DROP SCHEMA",
    "DROP VIEW",
    "DROP MATERIALIZED VIEW",
    "DROP SEQUENCE",
    "DROP TYPE",
    "DROP ROLE",
    "DROP FUNCTION",
    "DROP TRIGGER",
    "REVOKE ",
    "TRUNCATE",
    "DELETE FROM",
)

#: Heads that restrict a table rather than remove it, and are harmless on a table this body
#: created. See `A_NARROWING_ON_A_TABLE_THIS_MIGRATION_CREATED_IS_NOT_A_NARROWING`.
_NARROWING_HEADS: Final[tuple[str, ...]] = (
    "CREATE POLICY",
    "CREATE UNIQUE INDEX",
)


def _from_statement(statement: str, made: frozenset[str]) -> Change:
    """One SQL statement, read against the tables this body creates."""
    upper = statement.upper()
    if upper.startswith("DROP INDEX"):
        return Change(
            Verdict.SAFE,
            "index dropped",
            f"no query names an index, so the previous release's SQL still runs: {statement}",
        )
    for head in _NARROWING_HEADS:
        if upper.startswith(head):
            table = _table_of(statement)
            if table is None:
                return Change(
                    Verdict.UNREADABLE, "restriction on no table this can name", statement
                )
            if table in made:
                return Change(Verdict.SAFE, "restriction on a table created here", statement)
            return Change(
                Verdict.BREAKING,
                "restriction on a table that was already there",
                f"{statement}. {A_NARROWING_ON_A_TABLE_THIS_MIGRATION_CREATED_IS_NOT_A_NARROWING}",
            )
    for head in _ADDITIVE_HEADS:
        if upper.startswith(head):
            return Change(Verdict.SAFE, "additive statement", statement)
    for head in _REMOVING_HEADS:
        if upper.startswith(head):
            return Change(Verdict.BREAKING, "statement removes something", statement)
    altered = _ALTER_TABLE.match(statement)
    if altered is not None:
        return _from_alter(statement, altered.group(1).lower(), altered.group("rest"), made)
    return Change(Verdict.UNREADABLE, "statement this check does not classify", statement)


def _from_alter(statement: str, table: str, rest: str, made: frozenset[str]) -> Change:
    """The `ALTER TABLE` tail, which is the one head that goes both ways."""
    tail = rest.upper()
    if tail.startswith(("DROP ", "RENAME ")):
        return Change(Verdict.BREAKING, "statement removes something", statement)
    if tail.startswith("ADD COLUMN"):
        if "NOT NULL" in tail and "DEFAULT" not in tail:
            return Change(
                Verdict.BREAKING,
                "not-null column with no default",
                f"the previous release's INSERT names no such column: {statement}",
            )
        return Change(Verdict.SAFE, "additive statement", statement)
    if tail.startswith(("ADD ", "ENABLE ROW LEVEL SECURITY", "FORCE ROW LEVEL SECURITY")):
        if table in made:
            return Change(Verdict.SAFE, "restriction on a table created here", statement)
        return Change(
            Verdict.BREAKING,
            "restriction on a table that was already there",
            f"{statement}. {A_NARROWING_ON_A_TABLE_THIS_MIGRATION_CREATED_IS_NOT_A_NARROWING}",
        )
    if tail.startswith("ALTER COLUMN"):
        if "SET NOT NULL" in tail:
            return Change(Verdict.BREAKING, "column narrowed to not null", statement)
        if "DROP NOT NULL" in tail or "DEFAULT" in tail:
            return Change(Verdict.SAFE, "additive statement", statement)
        return Change(Verdict.UNREADABLE, "column altered in a way this cannot order", statement)
    return Change(Verdict.UNREADABLE, "statement this check does not classify", statement)


def _from_call(
    call: _Call, made: frozenset[str], reversed_by: dict[tuple[str, str, str], str]
) -> Change:
    """One `op.<something>` call that is not `execute`."""
    node = call.node
    if call.name in {"drop_column", "drop_table", "rename_table", "drop_schema"}:
        return Change(Verdict.BREAKING, f"op.{call.name}", ast.unparse(node))
    if call.name in {"drop_index", "drop_constraint", "get_bind"}:
        # Dropping a constraint accepts more rows, not fewer, and the replacement that usually
        # follows it is judged on its own below. The exception is written down rather than
        # branched on: a dropped primary key or unique constraint is still a widening of what
        # the table accepts, and it takes away the target an `ON CONFLICT` names, which is a
        # fact about the previous release's statements rather than about this file. See the
        # last entry in `WHAT_THIS_CHECK_CANNOT_SEE`.
        return Change(Verdict.SAFE, f"op.{call.name}", ast.unparse(node))
    if call.name in {"create_table", "create_schema", "bulk_insert"}:
        return Change(Verdict.SAFE, f"op.{call.name}", ast.unparse(node))
    names = call.names
    if call.name == "create_index":
        if _one(_keyword(node, "unique"), names) is not True:
            return Change(Verdict.SAFE, "op.create_index", ast.unparse(node))
        return _restriction(node, _one(_keyword(node, "schema"), names), _at(node, 1, names), made)
    if call.name in {"create_unique_constraint", "create_primary_key", "create_foreign_key"}:
        return _restriction(node, _one(_keyword(node, "schema"), names), _at(node, 1, names), made)
    if call.name == "add_column":
        return _from_add_column(node, names)
    if call.name == "alter_column":
        return _from_alter_column(node, names)
    if call.name == "create_check_constraint":
        return _from_check_constraint(node, names, made, reversed_by)
    return Change(Verdict.UNREADABLE, f"op.{call.name} is not classified here", ast.unparse(node))


def _at(node: ast.Call, index: int, names: _Names) -> object:
    return _one(node.args[index], names) if len(node.args) > index else None


def _restriction(node: ast.Call, schema: object, table: object, made: frozenset[str]) -> Change:
    """A constraint or unique index, judged against the tables this body creates."""
    if not (isinstance(schema, str) and isinstance(table, str)):
        return Change(
            Verdict.UNREADABLE, "restriction on no table this can name", ast.unparse(node)
        )
    if f"{schema}.{table}".lower() in made:
        return Change(Verdict.SAFE, "restriction on a table created here", ast.unparse(node))
    return Change(
        Verdict.BREAKING,
        "restriction on a table that was already there",
        f"{ast.unparse(node)}. {A_NARROWING_ON_A_TABLE_THIS_MIGRATION_CREATED_IS_NOT_A_NARROWING}",
    )


def _from_add_column(node: ast.Call, names: _Names) -> Change:
    """A column addition, which is safe unless the previous release's INSERT cannot satisfy it."""
    column = next(
        (
            one
            for one in ast.walk(node)
            if isinstance(one, ast.Call)
            and isinstance(one.func, ast.Attribute)
            and one.func.attr == "Column"
        ),
        None,
    )
    if column is None:
        return Change(
            Verdict.UNREADABLE, "op.add_column with no readable column", ast.unparse(node)
        )
    nullable = _one(_keyword(column, "nullable"), names)
    if nullable is not False:
        return Change(Verdict.SAFE, "nullable column added", ast.unparse(node))
    if _keyword(column, "server_default") is not None:
        return Change(Verdict.SAFE, "not-null column with a default", ast.unparse(node))
    return Change(
        Verdict.BREAKING,
        "not-null column with no default",
        f"the previous release's INSERT names no such column: {ast.unparse(node)}",
    )


def _from_alter_column(node: ast.Call, names: _Names) -> Change:
    """A column altered. Every interesting case is here and two of them cannot be ordered."""
    if _keyword(node, "new_column_name") is not None:
        return Change(
            Verdict.BREAKING,
            "column renamed",
            f"the previous release reads the old name: {ast.unparse(node)}",
        )
    if _keyword(node, "type_") is not None:
        return Change(Verdict.UNREADABLE, "column type changed", ast.unparse(node))
    nullable = _one(_keyword(node, "nullable"), names)
    if nullable is False:
        return Change(Verdict.BREAKING, "column narrowed to not null", ast.unparse(node))
    if nullable is True:
        return Change(Verdict.SAFE, "column widened to nullable", ast.unparse(node))
    return Change(
        Verdict.UNREADABLE, "column altered in a way this cannot order", ast.unparse(node)
    )


def _from_check_constraint(
    node: ast.Call,
    names: _Names,
    made: frozenset[str],
    reversed_by: dict[tuple[str, str, str], str],
) -> Change:
    """A check constraint, compared against the one the opposite direction puts back."""
    name = _one(node.args[0], names) if node.args else None
    table = _at(node, 1, names)
    schema = _one(_keyword(node, "schema"), names)
    condition = _strings_of(node.args[2], names) if len(node.args) > 2 else None
    if not (isinstance(name, str) and isinstance(table, str) and isinstance(schema, str)):
        return Change(Verdict.UNREADABLE, "check constraint this cannot place", ast.unparse(node))
    if f"{schema}.{table}".lower() in made:
        return Change(Verdict.SAFE, "restriction on a table created here", ast.unparse(node))
    if not condition or len(condition) != 1:
        return Change(
            Verdict.UNREADABLE, "check constraint with no readable predicate", ast.unparse(node)
        )
    previous = reversed_by.get((schema.lower(), table.lower(), name.lower()))
    if previous is None:
        return Change(
            Verdict.BREAKING,
            "constraint added to a table that was already there",
            f"nothing in the opposite direction says what it replaced: {ast.unparse(node)}",
        )
    verdict = _accepts_at_least(previous, condition[0])
    if verdict is None:
        return Change(
            Verdict.UNREADABLE,
            "constraint predicate this cannot order",
            f"{previous!r} against {condition[0]!r} on {schema}.{table}",
        )
    if verdict:
        return Change(
            Verdict.SAFE,
            "constraint widened",
            f"{schema}.{table}.{name} accepts everything it accepted before",
        )
    return Change(
        Verdict.BREAKING,
        "constraint narrowed",
        f"{schema}.{table}.{name} stops accepting what the previous release can still write: "
        f"{previous!r} became {condition[0]!r}",
    )


# ------------------------------------------------------------------ the two entry points


def changes_in(
    text: str, *, applying: str = "upgrade", reversing: str = "downgrade"
) -> tuple[Change, ...]:
    """Every operation `applying` performs, judged against the release before it.

    `reversing` is read for one thing only: the predicate a replaced check constraint used to
    hold, which lives nowhere else inside a single file. Swapping the two names asks the
    other direction, and that is the whole of how `0022` is tested from both sides.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return (Change(Verdict.UNREADABLE, "the file does not parse", str(error)),)
    if _first_revision(tree):
        return (Change(Verdict.SAFE, "first revision", THE_FIRST_REVISION_HAS_NO_PREVIOUS_RELEASE),)
    calls, complete = _calls(tree, applying)
    counterpart, _ = _calls(tree, reversing)
    made = _tables_created(calls)
    reversed_by = _check_predicates(counterpart)
    out: list[Change] = []
    if not complete:
        out.append(
            Change(
                Verdict.UNREADABLE,
                "a statement executed outside op",
                "built at run time and run through a connection, so no reading of the source "
                "says what it does",
            )
        )
    for call in calls:
        if call.name != "execute":
            out.append(_from_call(call, made, reversed_by))
            continue
        if not call.readable:
            out.append(
                Change(
                    Verdict.UNREADABLE,
                    "op.execute with no readable argument",
                    ast.unparse(call.node),
                )
            )
            continue
        out.extend(_from_statement(one, made) for one in call.sql)
    return tuple(out)


def _first_revision(tree: ast.Module) -> bool:
    """Whether this file declares `down_revision = None`. See the constant of that name."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [one.id for one in node.targets if isinstance(one, ast.Name)]
        if "down_revision" in names and isinstance(node.value, ast.Constant):
            return node.value.value is None
    return False


def breaking_changes(text: str) -> tuple[Change, ...]:
    """The proven findings only. What the gate refuses."""
    return tuple(one for one in changes_in(text) if one.verdict is Verdict.BREAKING)


def unreadable_changes(text: str) -> tuple[Change, ...]:
    """The statements the reading could not decide. What the gate prints and does not refuse."""
    return tuple(one for one in changes_in(text) if one.verdict is Verdict.UNREADABLE)


def check_all(versions: Path = VERSIONS) -> dict[str, tuple[Change, ...]]:
    """Every migration in a directory, keyed by file name."""
    return {
        path.name: changes_in(path.read_text(encoding="utf-8"))
        for path in sorted(versions.glob("*.py"))
    }


def main(versions: Path = VERSIONS) -> int:
    """Print what was read, what was refused, and where the reading stops.

    Takes the directory so the failing path is testable. A gate whose only failing case is a
    real broken migration is a gate nobody has ever seen fail, and the whole exercise here is
    that a check nobody has watched fire is a check that does not fire.
    """
    read = check_all(versions)
    breaking = {name: [c for c in cs if c.verdict is Verdict.BREAKING] for name, cs in read.items()}
    unreadable = {
        name: [c for c in cs if c.verdict is Verdict.UNREADABLE] for name, cs in read.items()
    }
    operations = sum(len(cs) for cs in read.values())
    unread = sum(len(cs) for cs in unreadable.values())
    for name, findings in sorted(unreadable.items()):
        for finding in findings:
            print(f"  cannot read  {name}: {finding.rule}, {finding.detail[:120]}")
    print("this check does not see:")
    for limit in WHAT_THIS_CHECK_CANNOT_SEE:
        print(f"  - {limit}")
    found = sum(len(cs) for cs in breaking.values())
    if not found:
        print(
            f"ok: {len(read)} migration(s), {operations} operation(s) read, "
            f"0 that break the previous release, {unread} this check cannot read"
        )
        return 0
    print("migrations that break the release before them:", file=sys.stderr)
    for name, findings in sorted(breaking.items()):
        for finding in findings:
            print(f"  {name}: {finding}", file=sys.stderr)
    print(f"\n{A_ROLLING_DEPLOY_RUNS_THE_NEW_SCHEMA_AGAINST_THE_OLD_CODE}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
