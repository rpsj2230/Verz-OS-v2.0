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

**A partial unique index that replaces a unique constraint over the same columns is read
against the chain, and the downgrade is not asked.** `0219` drops `0055`'s unique constraint over
agent, template and person and writes a unique index over the same three columns for every row
whose template is not `authored`. That refuses a subset of what the constraint refused, so every
insert the previous release makes still succeeds, and an index with a WHERE clause on a table
that was already there used to be read as a narrowing all the same. It is `SAFE` now when four
things hold and `BREAKING` when any one does not: the statement is a `CREATE UNIQUE INDEX` over
plain columns with a WHERE clause and nothing else after the column list; this body drops a
unique constraint or index by name (an `op.drop_constraint`, an `ALTER TABLE ... DROP
CONSTRAINT`, a `DROP INDEX`, or the one `DO` block that drops a named unique constraint when it
is there); an earlier migration reached by `down_revision` created that name as a plain unique
over the same table; and its columns are exactly the new index's. See
`A_PARTIAL_UNIQUE_INDEX_OVER_THE_COLUMNS_OF_THE_ONE_IT_REPLACES_ONLY_WIDENS`.

Rejected: reading the old columns from this file's own downgrade, which is where a replaced
check constraint's predicate comes from. A downgrade says what its author intends to put back
and proves nothing about what was there. The `DO` block `0219` uses drops the constraint only
`IF` it exists, so a migration that dropped a name that never existed and put a different
constraint back in its downgrade would be read as having replaced something, and a narrowing
would pass. The chain is the record of what the previous release's schema held, so the old
constraint is found in it by name, newest migration first, and the first one that mentions the
name decides.

Rejected: passing any partial unique index over a column set that some constraint on the table
already covers, with no drop in the body. Without the drop the old constraint is still there and
the new index narrows nothing, but this check would then be reading the rest of the chain to
prove that a constraint survives it, which is a different and larger claim than the one that
was needed.

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

Task ids: M30.2.6, M31.2.2.3
"""

from __future__ import annotations

import ast
import enum
import re
import sys
from collections.abc import Callable, Iterable
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

#: Why a permissive policy on a table that was already there is a widening and not a narrowing.
A_PERMISSIVE_POLICY_CAN_ONLY_WIDEN: Final = (
    "PostgreSQL ORs every permissive policy for a command and role together, and permissive is "
    "what CREATE POLICY writes unless it says AS RESTRICTIVE. So a permissive policy added to a "
    "table that was already there admits every row the table's policies admitted before and "
    "possibly more: the previous release's queries return what they returned and its writes pass "
    "the checks they passed. Only a restrictive policy, which is ANDed with the rest, takes "
    "anything away, and it stays a finding. 0162 and 0163 were refused for a permissive read "
    "and a permissive update until this was read."
)

#: Why taking a privilege on a brand new function away from PUBLIC is not a narrowing.
A_REVOKE_ON_A_FUNCTION_THIS_MIGRATION_CREATED_IS_NOT_A_NARROWING: Final = (
    "PostgreSQL grants EXECUTE to PUBLIC on every function it creates, so a SECURITY DEFINER "
    "function is callable by every role with USAGE on its schema until that is revoked. A "
    "REVOKE on a function the same body creates takes away something no earlier release could "
    "call, because the function did not exist for it. 0036 and 0040 left the default grant in "
    "place because this check read every REVOKE as a narrowing; a revoke on a function that "
    "was already there still is one."
)

#: Why a restriction that binds only rows naming a column this migration added is not a narrowing.
A_RESTRICTION_ON_A_COLUMN_THE_PREVIOUS_RELEASE_NEVER_WRITES_IS_NOT_A_NARROWING: Final = (
    "The previous release never names a column this migration added, so every row it writes "
    "holds a null there. A unique index over that column never compares such rows, because "
    "nulls are distinct; a check reading `<added> IS NULL OR ...` is true for them; and a check "
    "reading `<column> IS NOT NULL OR ...` is true for them when this body only widened that "
    "column from not null, since the previous release could write nothing else."
)

#: Why a restriction that binds only rows whose added flag is true is not a narrowing.
A_RESTRICTION_ON_A_FLAG_THE_PREVIOUS_RELEASE_NEVER_SETS_IS_NOT_A_NARROWING: Final = (
    "A check reading `NOT <flag> OR ...` over a boolean column this migration added with a default "
    "of false is true for every row whose flag is false. The previous release never names the "
    "column, so every row it writes holds false there and the new check binds none of them; it "
    "binds only the rows the new release marks, which is how a rule is given to a state the old "
    "release cannot produce. 0221 is the first to need it."
)

#: Why a restriction that binds only a word the previous release could not write is not a narrowing.
A_RESTRICTION_ON_A_WORD_THE_PREVIOUS_RELEASE_NEVER_WRITES_IS_NOT_A_NARROWING: Final = (
    "A check reading `<column> <> 'word' OR ...` is true for every row whose column is not that "
    "word, so it binds only rows that hold it. When the opposite direction restores an IN list "
    "for the same column that does not contain the word, the previous release's own constraint "
    "refused it, so it never wrote one and the new check binds nothing it can write. This is "
    "how a new state is given its own invariant, and 0210 is the first to need it."
)

#: Why a partial unique index that replaces a unique constraint over the same columns is not one.
A_PARTIAL_UNIQUE_INDEX_OVER_THE_COLUMNS_OF_THE_ONE_IT_REPLACES_ONLY_WIDENS: Final = (
    "A unique index with a WHERE clause compares only the rows the clause selects, so over the "
    "same table and the same columns as a unique constraint the same body drops, it refuses a "
    "subset of what the constraint refused and nothing more: every INSERT the previous release "
    "could make under the constraint still succeeds under the index. It is a narrowing when the "
    "columns differ, when the table differs, when nothing is dropped that it replaces, or when "
    "the dropped constraint cannot be found by name in an earlier migration, because only then "
    "is there no proof that the old one was the stricter. 0219 replaced its automation "
    "constraint this way and was refused until this was read."
)

#: Why a policy dropped and written again is unreadable rather than breaking.
A_POLICY_REPLACED_IN_THE_SAME_BODY_CANNOT_BE_ORDERED: Final = (
    "A policy dropped and written again in one body changes which rows each command admits, "
    "and whether the new policies admit everything the old one did is an ordering of boolean "
    "expressions this check does not attempt. Breaking would refuse every repair of a policy "
    "ever written, and 0045 is one; safe would pass a narrowing unread. A policy written on "
    "an existing table whose policies this body did not drop is still a restriction on a "
    "table that was already there."
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
    "A policy dropped and written again. `0045` replaces the policies on sixteen tables that "
    "were already there, and every statement comes back unreadable, because ordering two "
    "policy expressions is a proof this check does not attempt.",
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
    "about the previous release's code rather than about this file. That includes the "
    "partial unique index that replaces one: `ON CONFLICT (columns)` with no predicate, or "
    "`ON CONFLICT ON CONSTRAINT name`, finds no arbiter among a partial index and is an error "
    "in the previous release's code, and this check does not read that code.",
    "Which constraint a partial unique index replaced, when the old one was built another way "
    "than a literal. The old constraint is found by its literal name in an earlier migration's "
    "`upgrade`, as a plain unique over plain columns, created once and touched nowhere else in "
    "that body. A name built at run time, a chain with a gap, an expression, a deferrable "
    "constraint or an index with an INCLUDE list is not found, and the new index is then a "
    "finding. Only the `CREATE UNIQUE INDEX` statement is read, not `op.create_index` with a "
    "`postgresql_where`.",
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

#: A table or a materialised view, the two relations a restriction can be placed on. A unique
#: index on a materialised view the same body creates restricts nothing the previous release
#: ever wrote, for the reason a policy on a new table does not.
_CREATE_TABLE = re.compile(
    rf"^CREATE\s+(?:TABLE|MATERIALIZED\s+VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?({_QUALIFIED})", re.I
)
_ALTER_TABLE = re.compile(rf"^ALTER\s+TABLE\s+(?:ONLY\s+)?({_QUALIFIED})\s+(?P<rest>.*)$", re.I)
_ON_TABLE = re.compile(rf"\bON\s+({_QUALIFIED})\b", re.IGNORECASE)
#: The clause that makes a policy restrictive. Its absence is permissive, PostgreSQL's default.
_RESTRICTIVE = re.compile(r"\bAS\s+RESTRICTIVE\b", re.IGNORECASE)
#: A function a body creates, and the function a REVOKE takes a privilege from. `CREATE OR REPLACE`
#: is not the first: a function it replaces was already there for the previous release to call.
_CREATE_FUNCTION = re.compile(rf"^CREATE\s+FUNCTION\s+({_QUALIFIED})\s*\(", re.I)
_REVOKE_ON_FUNCTION = re.compile(rf"^REVOKE\s+.*?\bON\s+FUNCTION\s+({_QUALIFIED})\s*\(", re.I)


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
    """Every `schema.table` this body creates, from both spellings, materialised views included.

    Read before anything is classified rather than as the body is walked, because the
    ordering inside a migration says nothing: a policy written above the table it protects
    still protects a table the previous release never saw.

    A materialised view counts because
    `A_NARROWING_ON_A_TABLE_THIS_MIGRATION_CREATED_IS_NOT_A_NARROWING` is about the relation
    being new, not about it being a table: the unique index `REFRESH
    MATERIALIZED VIEW CONCURRENTLY` requires is written in the migration that creates the view,
    and the previous release never read or refreshed a view that did not exist. A view an
    earlier migration created is not in this set, so an index added to it later is still a
    restriction on something that was already there.
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


#: `<column> <> 'word' OR ...`, the head of a check that binds only rows holding one word.
_WORD_GUARD = re.compile(r"^\s*(?P<column>\w+)\s*<>\s*'(?P<word>[^']+)'\s+OR\s", re.IGNORECASE)


def _binds_only_a_new_word(
    condition: str, schema: str, table: str, reversed_by: dict[tuple[str, str, str], str]
) -> bool:
    """Whether a check binds only a word the opposite direction's IN list for that column lacks.

    See `A_RESTRICTION_ON_A_WORD_THE_PREVIOUS_RELEASE_NEVER_WRITES_IS_NOT_A_NARROWING`.
    """
    head = _WORD_GUARD.match(condition)
    if head is None:
        return False
    for (one_schema, one_table, _), predicate in reversed_by.items():
        if (one_schema, one_table) != (schema.lower(), table.lower()):
            continue
        listed = _IN_LIST.match(predicate.strip())
        if listed is None or listed.group("column").lower() != head.group("column").lower():
            continue
        words = {one.strip() for one in listed.group("items").split(",")}
        if f"'{head.group('word')}'" not in words:
            return True
    return False


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


def _functions_created(calls: tuple[_Call, ...]) -> frozenset[str]:
    """Every `schema.function` this body creates with a plain `CREATE FUNCTION`, by name.

    By name and not by signature, as `_tables_created` reads a table by name: a body that creates
    one overload and revokes on another of the same name has revoked on a function it made, and
    this repository writes no overloads.
    """
    return frozenset(
        found.group(1).lower()
        for call in calls
        for statement in call.sql
        if (found := _CREATE_FUNCTION.match(statement)) is not None
    )


def _from_statement(
    statement: str,
    made: frozenset[str],
    replaced: frozenset[str] = frozenset(),
    functions: frozenset[str] = frozenset(),
    replacing: _Replacing | None = None,
) -> Change:
    """One SQL statement, read against the tables and functions this body creates."""
    upper = statement.upper()
    revoked = _REVOKE_ON_FUNCTION.match(statement)
    if revoked is not None and revoked.group(1).lower() in functions:
        return Change(
            Verdict.SAFE,
            "privilege taken from a function created here",
            f"{statement}. {A_REVOKE_ON_A_FUNCTION_THIS_MIGRATION_CREATED_IS_NOT_A_NARROWING}",
        )
    if upper.startswith("DROP INDEX"):
        return Change(
            Verdict.SAFE,
            "index dropped",
            f"no query names an index, so the previous release's SQL still runs: {statement}",
        )
    if upper.startswith("DROP POLICY"):
        return Change(
            Verdict.UNREADABLE,
            "policy replaced",
            f"{statement}. {A_POLICY_REPLACED_IN_THE_SAME_BODY_CANNOT_BE_ORDERED}",
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
            if head == "CREATE UNIQUE INDEX" and replacing is not None:
                narrowing_that_widens = _replaces_a_unique(statement, replacing)
                if narrowing_that_widens is not None:
                    return narrowing_that_widens
            if head == "CREATE POLICY" and table in replaced:
                return Change(
                    Verdict.UNREADABLE,
                    "policy replaced",
                    f"{statement}. {A_POLICY_REPLACED_IN_THE_SAME_BODY_CANNOT_BE_ORDERED}",
                )
            if head == "CREATE POLICY" and _RESTRICTIVE.search(statement) is None:
                return Change(
                    Verdict.SAFE,
                    "permissive policy, which only widens",
                    f"{statement}. {A_PERMISSIVE_POLICY_CAN_ONLY_WIDEN}",
                )
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


def _columns(calls: tuple[_Call, ...], name: str, flag: str, value: object) -> frozenset[str]:
    """`schema.table.column` for every `op.<name>` whose column carries `flag=value`."""
    found: set[str] = set()
    for call in calls:
        if call.name != name or len(call.node.args) < 2:
            continue
        table = _one(call.node.args[0], call.names)
        schema = _one(_keyword(call.node, "schema"), call.names)
        target: ast.Call = call.node
        if name == "add_column":
            column = call.node.args[1]
            if not (isinstance(column, ast.Call) and column.args):
                continue
            named = _one(column.args[0], call.names)
            target = column
        else:
            named = _one(call.node.args[1], call.names)
        if _one(_keyword(target, flag), call.names) is not value:
            continue
        if isinstance(table, str) and isinstance(schema, str) and isinstance(named, str):
            found.add(f"{schema}.{table}.{named}".lower())
    return frozenset(found)


def _false_flags(calls: tuple[_Call, ...]) -> frozenset[str]:
    """`schema.table.column` for every boolean column added not null with a default of false.

    Read off the column's own call: a `sa.Boolean()` type, `nullable=False` and a
    `server_default` that unparses as `sa.false()` or `sa.text("false")`. A column with any other
    default is not one, because the previous release's rows would hold something else.
    """
    found: set[str] = set()
    for call in calls:
        if call.name != "add_column" or len(call.node.args) < 2:
            continue
        column = call.node.args[1]
        if not (isinstance(column, ast.Call) and len(column.args) >= 2):
            continue
        kind = ast.unparse(column.args[1]).replace(" ", "")
        default = _keyword(column, "server_default")
        said = "" if default is None else ast.unparse(default).replace(" ", "").replace("'", '"')
        if (
            kind in {"sa.Boolean()", "sa.Boolean"}
            and _one(_keyword(column, "nullable"), call.names) is False
            and said in {"sa.false()", 'sa.text("false")'}
        ):
            table = _one(call.node.args[0], call.names)
            schema = _one(_keyword(call.node, "schema"), call.names)
            named = _one(column.args[0], call.names)
            if isinstance(table, str) and isinstance(schema, str) and isinstance(named, str):
                found.add(f"{schema}.{table}.{named}".lower())
    return frozenset(found)


def _never_written(
    node: ast.Call,
    names: _Names,
    added: frozenset[str],
    widened: frozenset[str],
    flags: frozenset[str] = frozenset(),
) -> bool:
    """Whether a unique index or check binds only rows the previous release cannot write.

    See `A_RESTRICTION_ON_A_COLUMN_THE_PREVIOUS_RELEASE_NEVER_WRITES_IS_NOT_A_NARROWING`.
    """
    schema = _one(_keyword(node, "schema"), names)
    table = _at(node, 1, names)
    if not (isinstance(schema, str) and isinstance(table, str)):
        return False
    prefix = f"{schema}.{table}.".lower()
    if isinstance(node.func, ast.Attribute) and node.func.attr == "create_index":
        columns = node.args[2] if len(node.args) > 2 else None
        listed = columns.elts if isinstance(columns, ast.List | ast.Tuple) else []
        return any(f"{prefix}{_one(one, names)}".lower() in added for one in listed)
    condition = _strings_of(node.args[2], names) if len(node.args) > 2 else None
    if not condition or len(condition) != 1:
        return False
    flag = re.match(r"^\s*NOT (\w+) OR ", condition[0])
    if flag is not None:
        # `NOT <added flag> OR ...`: true for every row whose flag is false, and the previous
        # release writes none other, since it never names the column and a flag added with a
        # default of false holds false.
        # See `A_RESTRICTION_ON_A_FLAG_THE_PREVIOUS_RELEASE_NEVER_SETS_IS_NOT_A_NARROWING`.
        return f"{prefix}{flag.group(1)}".lower() in flags
    head = re.match(r"^\s*(\w+) IS (NOT )?NULL OR ", condition[0])
    if head is None:
        return False
    column = f"{prefix}{head.group(1)}".lower()
    return column in widened if head.group(2) else column in added


def _from_call(
    call: _Call,
    made: frozenset[str],
    reversed_by: dict[tuple[str, str, str], str],
    added: frozenset[str] = frozenset(),
    widened: frozenset[str] = frozenset(),
    flags: frozenset[str] = frozenset(),
) -> Change:
    """One `op.<something>` call that is not `execute`."""
    node = call.node
    if call.name in {"create_index", "create_check_constraint"} and _never_written(
        node, call.names, added, widened, flags
    ):
        return Change(
            Verdict.SAFE,
            "restriction on a column the previous release never writes",
            ast.unparse(node),
        )
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
    if previous is None and _binds_only_a_new_word(condition[0], schema, table, reversed_by):
        return Change(
            Verdict.SAFE,
            "restriction on a word the previous release never writes",
            ast.unparse(node),
        )
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


# ------------------------------------------------------------------ a partial index for a unique

#: `CREATE UNIQUE INDEX name ON schema.table (columns) [WHERE predicate]` and nothing after the
#: column list but the predicate. An INCLUDE list, NULLS NOT DISTINCT or a storage option does not
#: match, so a statement carrying one is left to the ordinary reading and stays a finding.
_UNIQUE_INDEX = re.compile(
    r"^CREATE\s+UNIQUE\s+INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>\w+)\s+ON\s+"
    rf"(?:ONLY\s+)?(?P<table>{_QUALIFIED})\s*(?:USING\s+btree\s*)?\((?P<columns>[^()]*)\)"
    r"(?:\s+WHERE\s+(?P<where>.+))?$",
    re.IGNORECASE,
)
_ADD_UNIQUE = re.compile(
    rf"^ALTER\s+TABLE\s+(?:ONLY\s+)?(?P<table>{_QUALIFIED})\s+ADD\s+CONSTRAINT\s+(?P<name>\w+)\s+"
    r"UNIQUE\s*\((?P<columns>[^()]*)\)$",
    re.IGNORECASE,
)
_DROP_CONSTRAINT = re.compile(
    rf"^ALTER\s+TABLE\s+(?:ONLY\s+)?(?P<table>{_QUALIFIED})\s+DROP\s+CONSTRAINT\s+"
    r"(?:IF\s+EXISTS\s+)?(?P<name>\w+)$",
    re.IGNORECASE,
)
_DROP_INDEX = re.compile(
    r"^DROP\s+INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+EXISTS\s+)?(?P<schema>\w+)\.(?P<name>\w+)$",
    re.IGNORECASE,
)

#: The one `DO` block that drops a unique constraint by name when it is there, whole and in the
#: form `0219` writes it. A block with anything else in it does not match, which is the point:
#: this reads what the block says and gives no opinion on a block that says more.
_DROP_IN_A_DO_BLOCK = re.compile(
    r"^DO \$\$ DECLARE (?P<var>\w+) text; BEGIN "  # noqa: S608
    r"SELECT c\.conname INTO (?P=var) FROM pg_constraint c "
    rf"WHERE c\.conrelid = '(?P<table>{_QUALIFIED})'::regclass AND c\.contype = 'u' "
    r"AND c\.conname = '(?P<name>\w+)'; "
    r"IF (?P=var) IS NOT NULL THEN "
    r"EXECUTE format\('ALTER TABLE (?P=table) DROP CONSTRAINT %I', (?P=var)\); "
    r"END IF; END \$\$$",
    re.IGNORECASE,
)

#: A column this reader can compare by name. An expression, a direction or a quoted name is not
#: one, so an index over it is never read as covering the same columns as anything.
_IDENTIFIER = re.compile(r"^[a-z_]\w*$")


@dataclass(frozen=True)
class _Gone:
    """A unique constraint or index this body drops, by the name it drops."""

    schema: str
    name: str
    #: None for an index, whose name is unique in its schema and is not tied to a table.
    table: str | None


@dataclass(frozen=True)
class _Defined:
    """A unique constraint or index an earlier migration created."""

    schema: str
    table: str
    name: str
    #: None when it is partial or carries anything else this does not compare.
    columns: frozenset[str] | None


#: Schema, name and table (None for any) to the table and columns the migration chain gave it.
_Lookup = Callable[[str, str, str | None], tuple[str, frozenset[str]] | None]


@dataclass(frozen=True)
class _Replacing:
    """What this body drops, and how to find out what each dropped thing used to cover."""

    dropped: tuple[_Gone, ...]
    lookup: _Lookup


def _plain_columns(names: Iterable[str]) -> frozenset[str] | None:
    """The columns of an index as a set of names, or None when any of them is not a plain name."""
    found = [one.strip().lower() for one in names]
    if not found or not all(_IDENTIFIER.match(one) for one in found):
        return None
    return frozenset(found)


def _listed(node: ast.expr | None, names: _Names) -> frozenset[str] | None:
    """A literal list of column names as a set, or None when it is anything else."""
    if not isinstance(node, ast.List | ast.Tuple):
        return None
    values = [_one(one, names) for one in node.elts]
    strings = [one for one in values if isinstance(one, str)]
    return _plain_columns(strings) if len(strings) == len(values) else None


def _callee(node: ast.Call) -> str | None:
    callee = node.func
    if isinstance(callee, ast.Attribute):
        return callee.attr
    return callee.id if isinstance(callee, ast.Name) else None


def _uniques_dropped(calls: tuple[_Call, ...]) -> tuple[_Gone, ...]:
    """Every constraint or index these calls drop by a name this can read, whatever its kind.

    The kind is not asked, because the answer decides nothing here: what a dropped name was is
    decided by the migration that created it, in `_unique_from_chain`, and a dropped check
    constraint or plain index is never found there as a unique one.
    """
    out: list[_Gone] = []
    for call in calls:
        node, names = call.node, call.names
        schema = _one(_keyword(node, "schema"), names)
        name = _at(node, 0, names)
        if call.name == "drop_constraint" and isinstance(schema, str) and isinstance(name, str):
            table = _at(node, 1, names)
            if isinstance(table, str):
                out.append(_Gone(schema.lower(), name.lower(), table.lower()))
        elif call.name == "drop_index" and isinstance(schema, str) and isinstance(name, str):
            held = _one(_keyword(node, "table_name"), names) or _at(node, 1, names)
            out.append(
                _Gone(schema.lower(), name.lower(), held.lower() if isinstance(held, str) else None)
            )
        for statement in call.sql:
            block = _DROP_IN_A_DO_BLOCK.match(statement)
            if block is not None:
                found = block.group("table").lower().partition(".")
                out.append(_Gone(found[0], block.group("name").lower(), found[2]))
            constraint = _DROP_CONSTRAINT.match(statement)
            if constraint is not None:
                found = constraint.group("table").lower().partition(".")
                out.append(_Gone(found[0], constraint.group("name").lower(), found[2]))
            index = _DROP_INDEX.match(statement)
            if index is not None:
                out.append(_Gone(index.group("schema").lower(), index.group("name").lower(), None))
    return tuple(out)


def _unique_definitions(calls: tuple[_Call, ...]) -> tuple[_Defined, ...]:
    """Every unique constraint or unique index these calls create under a name this can read.

    The four spellings this repository uses. A definition with a predicate, an INCLUDE list or
    any option this does not compare comes back with no columns, which makes it something that
    exists and cannot be compared, and that is a different answer from not being there.
    """
    out: list[_Defined] = []
    for call in calls:
        node, names = call.node, call.names
        schema = _one(_keyword(node, "schema"), names)
        if call.name == "create_table":
            table = _at(node, 0, names)
            for inner in ast.walk(node):
                if not (isinstance(inner, ast.Call) and _callee(inner) == "UniqueConstraint"):
                    continue
                name = _one(_keyword(inner, "name"), names)
                if isinstance(name, str) and isinstance(table, str) and isinstance(schema, str):
                    listed = [_one(one, names) for one in inner.args]
                    strings = [one for one in listed if isinstance(one, str)]
                    plain = {one.arg for one in inner.keywords} == {"name"}
                    columns = (
                        _plain_columns(strings) if plain and len(strings) == len(listed) else None
                    )
                    out.append(_Defined(schema.lower(), table.lower(), name.lower(), columns))
        elif call.name in {"create_unique_constraint", "create_index"}:
            name = _at(node, 0, names)
            table = _at(node, 1, names)
            if call.name == "create_index" and _one(_keyword(node, "unique"), names) is not True:
                continue
            allowed = (
                {"schema"} if call.name == "create_unique_constraint" else {"schema", "unique"}
            )
            plain = {one.arg for one in node.keywords} <= allowed
            if isinstance(name, str) and isinstance(table, str) and isinstance(schema, str):
                columns = _listed(node.args[2] if len(node.args) > 2 else None, names)
                out.append(
                    _Defined(
                        schema.lower(), table.lower(), name.lower(), columns if plain else None
                    )
                )
        for statement in call.sql:
            added = _ADD_UNIQUE.match(statement)
            if added is not None:
                found = added.group("table").lower().partition(".")
                columns = _plain_columns(added.group("columns").split(","))
                out.append(_Defined(found[0], found[2], added.group("name").lower(), columns))
            created = _UNIQUE_INDEX.match(statement)
            if created is not None:
                found = created.group("table").lower().partition(".")
                columns = _plain_columns(created.group("columns").split(","))
                whole = created.group("where") is None
                out.append(
                    _Defined(
                        found[0],
                        found[2],
                        created.group("name").lower(),
                        columns if whole else None,
                    )
                )
    return tuple(out)


def _text_of(call: _Call) -> str:
    """What a call says, as lower case text, for asking whether it mentions a name."""
    if call.name == "execute" and call.readable:
        return " ".join(call.sql).lower()
    return ast.unparse(call.node).lower()


def _settle(
    calls: tuple[_Call, ...], schema: str, name: str, table: str | None
) -> tuple[bool, tuple[str, frozenset[str]] | None]:
    """Whether one migration's `upgrade` mentions a name, and what it made of it.

    The first element is whether it was mentioned at all, which decides whether the walk
    through the chain stops here. The second is the answer, and it is given only for the one
    clean shape: the name created once, as a plain unique constraint or index, and never
    dropped or touched by any other statement in the same body. Anything else that names it
    ends the walk with no answer, because a name that was touched somewhere this does not
    understand is a name whose columns this cannot vouch for.
    """
    named = [one for one in _unique_definitions(calls) if one.name == name and one.schema == schema]
    dropped = any(one.name == name and one.schema == schema for one in _uniques_dropped(calls))
    touching = [one for one in calls if name in _text_of(one)]
    if not (named or dropped or touching):
        return False, None
    if dropped or len(touching) != 1 or len(named) != 1:
        return True, None
    one = named[0]
    if one.columns is None or (table is not None and one.table != table):
        return True, None
    return True, (one.table, one.columns)


def _revisions(versions: Path) -> dict[str, tuple[str | None, str]]:
    """Every migration in a directory by its revision: what it revises, and its source."""
    found: dict[str, tuple[str | None, str]] = {}
    for path in sorted(versions.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        revision = _declared(tree, "revision")
        if isinstance(revision, str):
            before = _declared(tree, "down_revision")
            found[revision] = (before if isinstance(before, str) else None, text)
    return found


def _declared(tree: ast.Module, name: str) -> object:
    """The constant a module assigns to `name` at the top level, or None."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if name in [one.id for one in node.targets if isinstance(one, ast.Name)]:
            return node.value.value if isinstance(node.value, ast.Constant) else None
    return None


def _unique_from_chain(
    versions: Path, down: object, schema: str, name: str, table: str | None
) -> tuple[str, frozenset[str]] | None:
    """The table and columns a unique constraint or index was given, found by its name.

    Walks back from the migration before this one, newest first, and the first migration whose
    `upgrade` mentions the name is the one that decides, so a constraint created, dropped and
    created again is judged by the last of those. A chain with a gap, a name built at run time
    and a migration the reading cannot place all end in None, which the caller reads as
    "cannot be shown to have been there".
    """
    revisions = _revisions(versions)
    seen: set[str] = set()
    current = down
    while isinstance(current, str) and current in revisions and current not in seen:
        seen.add(current)
        before, text = revisions[current]
        current = before
        if name not in text.lower():
            continue
        calls, _ = _calls(ast.parse(text), "upgrade")
        mentioned, answer = _settle(calls, schema, name, table)
        if mentioned:
            return answer
    return None


_PARTIAL_UNIQUE_REASON: Final = (
    A_PARTIAL_UNIQUE_INDEX_OVER_THE_COLUMNS_OF_THE_ONE_IT_REPLACES_ONLY_WIDENS
)


def _replaces_a_unique(statement: str, replacing: _Replacing) -> Change | None:
    """Whether a statement is a partial unique index that replaces a unique constraint.

    See `A_PARTIAL_UNIQUE_INDEX_OVER_THE_COLUMNS_OF_THE_ONE_IT_REPLACES_ONLY_WIDENS`. All four
    must hold or this answers None and the statement is read as it was before: it has a WHERE
    clause over plain columns, this body drops something by name, the chain says what that name
    was a unique constraint or index over, and that is this table and exactly these columns.
    """
    parsed = _UNIQUE_INDEX.match(statement)
    if parsed is None or parsed.group("where") is None:
        return None
    columns = _plain_columns(parsed.group("columns").split(","))
    if columns is None:
        return None
    schema, _, table = parsed.group("table").lower().partition(".")
    for gone in replacing.dropped:
        if gone.schema == schema and replacing.lookup(gone.schema, gone.name, gone.table) == (
            table,
            columns,
        ):
            return Change(
                Verdict.SAFE,
                "partial unique index replacing a unique constraint over the same columns",
                f"{statement}. {_PARTIAL_UNIQUE_REASON}",
            )
    return None


# ------------------------------------------------------------------ the two entry points


def changes_in(
    text: str,
    *,
    applying: str = "upgrade",
    reversing: str = "downgrade",
    versions: Path = VERSIONS,
) -> tuple[Change, ...]:
    """Every operation `applying` performs, judged against the release before it.

    `reversing` is read for one thing only: the predicate a replaced check constraint used to
    hold, which lives nowhere else inside a single file. Swapping the two names asks the
    other direction, and that is the whole of how `0022` is tested from both sides.

    `versions` is the directory the earlier migrations are read from, and it is asked only
    when a body drops a unique constraint or index and writes a partial unique index: that is
    the one reading that needs a migration other than this one.
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
    functions = _functions_created(calls)
    replaced = frozenset(
        table
        for call in calls
        if call.name == "execute"
        for one in call.sql
        if one.upper().startswith("DROP POLICY") and (table := _table_of(one)) is not None
    )
    reversed_by = _check_predicates(counterpart)
    added = _columns(calls, "add_column", "nullable", True)
    widened = _columns(calls, "alter_column", "nullable", True)
    flags = _false_flags(calls)
    before = _declared(tree, "down_revision")

    def lookup(schema: str, name: str, table: str | None) -> tuple[str, frozenset[str]] | None:
        return _unique_from_chain(versions, before, schema, name, table)

    replacing = _Replacing(_uniques_dropped(calls), lookup)
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
            out.append(_from_call(call, made, reversed_by, added, widened, flags))
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
        out.extend(_from_statement(one, made, replaced, functions, replacing) for one in call.sql)
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
        path.name: changes_in(path.read_text(encoding="utf-8"), versions=versions)
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
