"""The two ends of a scope predicate: where it arrives from, and where it goes.

A scope is authored in a console, stored as jsonb, read back by a worker that never met
the author, and finally becomes the WHERE clause deciding what a person may read. Four
things go wrong along that path and none of them show up in a diff.

**A stored predicate can arrive in a shape the two evaluators read differently.** A clause
of `op=IN, value="abc"` is refused by `Clause.matches`, which wants a tuple, and admitted
by SQL rendering, where `list("abc")` becomes `["a", "b", "c"]`. One scope, two answers,
and the SQL answer is the wider one. `assert_conjunctive` refuses any clause whose value
shape disagrees with its operator, so such a scope reaches neither evaluator.

**A prefix can carry a wildcard.** SQL LIKE reads `%` and `_`; Python `str.startswith`
does not. A stored prefix of `web_` narrows in Python and widens in SQL. Every value bound
here is escaped and the escape character is declared, so the two agree on every input.

**A predicate document can smuggle in disjunction.** Conjunction-only is the property that
makes a grant set readable by inspection rather than by solving for satisfiability. The
document grammar has no `or` and no `not`, and names them explicitly when refusing, so an
author learns the rule rather than guessing at a parse error.

**An empty predicate and an impossible one look alike and mean opposite things.** No
clauses means unrestricted. Contradictory clauses mean nothing at all. Compiling either
one to a missing WHERE clause is the difference between a person seeing nothing and a
person seeing the whole company, so both are named here rather than left to the caller.

Nothing here performs I/O or imports a database driver. It emits a fragment and its bound
parameters as data; binding them is the caller's job.

---

**The second half of this module is a refusal rather than a renderer, and the distinction is
the whole argument for it existing.** `E_run(caller, agent) = E(caller) intersect
agent_ceiling` is implemented once, in `EntitlementSet.intersect`, and CLAUDE.md forbids a
second implementation because the wrong copy is the one in production.
`brain.orchestration.delegation` declined M18.3.1 on exactly that reading and the reading was
right about what it refused: **a second computation whose answer a run is executed at is a
second answer to the platform's central question.**

What is here is not that. `gate.delegated_reach` computes `parent intersect agent intersect
subtask` in SQL and no caller may run at what it returns: its only consumer is
`gate.delegation_narrows`, which compares it against the reach a row *claims* and raises. A
second implementation used to compute hands out a reach; a second implementation used only to
disagree is a check. The failure modes are not symmetrical either, and that is what makes the
copy affordable: an SQL copy narrower than the Python one refuses a legitimate row, which is
loud and is an availability bug, and an SQL copy wider than the Python one admits a row that
the Python path had already checked, which is the state before this existed.

What must not happen is the two drifting silently, so they are measured against each other
rather than trusted: `tests/unit/test_delegation_sql.py` runs the same sets through
`EntitlementSet.intersect` twice over and through `gate.delegated_reach` once, on a real
PostgreSQL, and compares the reaches by meaning. `not_after` is compared as an instant and not
as text, because pydantic renders UTC as `Z` and PostgreSQL renders it as `+00:00`; those are
the same instant and a byte comparison would have failed on a difference that means nothing.

**A trigger that repeats what the application already checked is worth very little, so this
one is built to catch the row the application never saw.** Two things make it that rather than
a restatement of `narrowing_refusals`:

- **A row may not supply its own parent reach unless it is the root of a chain.** `parent_id`
  and `parent_grants` are mutually exclusive by check constraint, so every row below the root
  is measured against the reach its parent row *recorded*, which the trigger already refused
  to widen. An inserter that controls every column of its own row therefore still cannot
  widen: the left-hand side of its intersection is not a column it writes. That is the half a
  Python check standing beside the same insert could not do, because Python would be reading
  the same attacker-supplied value.
- **A delegation row is written once.** The trigger refuses every UPDATE, so the reach a
  parent recorded cannot be edited after its children were measured against it. Without that,
  widening is a two-statement job: insert a narrow parent, insert the children, widen the
  parent.

**What it cannot do is check the root.** The root row's `parent_grants` is the asker's reach
and nothing in the database can confirm that it was: entitlements are resolved from several
tables plus the directory sync, by `brain.gate.entitle`, and a trigger re-resolving them would
be the second implementation this module has just argued against. So the guarantee is stated
narrowly and honestly: **below the root, no row widens; at the root, the row is as true as
whoever wrote it.** A root row is one insert to audit, and a chain of them is none.

Those four arguments are written down as `THE_SQL_REACH_IS_ONLY_EVER_A_SECOND_OPINION`,
`A_ROW_MAY_NOT_SUPPLY_ITS_OWN_PARENT_REACH`, `A_DELEGATION_ROW_RECORDS_ONE_DECISION` and
`THE_ROOT_OF_A_CHAIN_IS_AS_TRUE_AS_ITS_WRITER`, because a paragraph is deleted by the next
person who tidies a docstring and a named constant has to be argued with.

**Rejected, and it is the reason the intersection has to be computed rather than merely
asked about: checking containment against each of the three sides separately.** Containment in
an intersection is containment in each side, so `child subset (P and A and S)` looks like
three independent subset tests that need nothing materialised, and that is the cheaper design.
It does not work, because the containment this check uses is grant for grant on the
capability's own value, for the reason `narrowing_refusals` records: `scope_for` conjoins the
scopes of every grant that *covers* a capability, so comparing through it reports a correct
narrowing as a widening. A ceiling holding `read:client.*` covers a child holding
`read:client.name` and has no grant equal to it, so the direct test refuses a row that is
plainly narrower. Only the intersection has the wildcard resolved down to the concrete
capability the parent held, which is what the child can be compared against at all.
`test_the_intersection_cannot_be_replaced_by_three_containment_tests` is that measured on a
live server, so the argument is a demonstration rather than a paragraph.

Rejected: a second table holding one grant per row, joined for the check. It reads better as
SQL and it loses the property that matters: a delegation and its grants would then arrive in
separate statements, and a row-level trigger would pass on each half. A constraint trigger
deferred to commit closes that and adds a failure mode where the refusal arrives detached from
the statement that caused it. One row cannot be half written.

Rejected: enforcing the depth cap and the fan-out cap here too. Both are already decided in
`brain.orchestration.delegation` against `brain.ops.admission`'s configured budget, and a
constant compiled into a trigger is a budget that changes in two places or in neither.

Task ids: M2.1.2, M2.1.3, M18.3.1, M18.3.2
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from pydantic import ValidationError

from brain.core.scope import Clause, Op, Scope

#: SQL identifiers cannot be parameterised, so they are constrained rather than quoted.
#: Same reasoning as the field pattern on `Clause`: a name that cannot contain a quote
#: cannot close one.
IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

#: Document keys that would introduce disjunction or negation. They are refused by name
#: rather than by falling through to "unknown field", because an author who writes `$or`
#: has a model of the grammar in their head and deserves to be told it is wrong.
DISJUNCTION_KEYS = frozenset(
    {
        "or",
        "$or",
        "not",
        "$not",
        "nor",
        "$nor",
        "any_of",
        "anyof",
        "one_of",
        "oneof",
        "either",
        "except",
        "unless",
        "union",
    }
)

#: Matcher object keys the document grammar understands. Anything else is refused.
MATCHER_KEYS = frozenset({"prefix", "any"})

#: LIKE needs an escape character and Postgres defaults to backslash. It is declared
#: explicitly in the rendered fragment anyway, because the default depends on a server
#: setting and a permission predicate should not.
LIKE_ESCAPE = "\\"


class PredicateRefusedError(Exception):
    """Raised when a predicate could widen, diverge, or match nothing.

    Deliberately not part of the user-facing error taxonomy in `brain.core.errors`. Nobody
    asking a question ever sees this: it is an authoring-time and load-time failure, and it
    should stop a scope from being saved rather than degrade an answer.
    """


@dataclass(frozen=True)
class GrammarViolation:
    """One reason a predicate is not allowed."""

    where: str
    reason: str

    def __str__(self) -> str:
        return f"{self.where}: {self.reason}"


# --------------------------------------------------------------- the grammar
def check_grammar(scope: Scope) -> list[GrammarViolation]:
    """Every reason this scope may not be used, not just the first.

    Returning one at a time turns authoring a scope into a guessing game, where each fix
    reveals the next objection. The same reasoning as `projection.check_projection`.
    """
    violations: list[GrammarViolation] = []
    for clause in scope.clauses:
        violations.extend(_check_clause(clause))
    return violations


def _check_clause(clause: Clause) -> list[GrammarViolation]:
    """The value shape must match the operator, on both evaluators.

    **Two pairings are not checked here and the reason is that `Clause` refuses them.** Its
    validator takes exactly the shapes where SQL is wider than Python, `IN` with a bare string
    and `PREFIX` with a non-string, because those are the two where the database admits rows
    the in-process check does not. A `Clause` therefore cannot carry either, and the branches
    that used to test for them here were unreachable: a mutation audit found them on
    2026-09-09 and this is what the removal is.

    That leaves this function the job it actually has, which is the wider one. `Clause` refuses
    only the divergent shapes and says so; every other odd pairing constructs cleanly, matches
    nothing in both evaluators, and is a scope somebody wrote by mistake. Refusing those is
    authoring-time sanity and belongs here, at the moment a scope is saved, rather than in a
    type that has to keep them representable so a test can be written about them.
    """
    out: list[GrammarViolation] = []
    where = f"{clause.field} {clause.op}"

    match clause.op:
        case Op.ANY:
            if clause.value is not None:
                out.append(
                    GrammarViolation(
                        where,
                        "carries a value, which nothing reads; write it as a real test "
                        "or drop the clause",
                    )
                )
        case Op.EQ:
            if not isinstance(clause.value, str):
                out.append(
                    GrammarViolation(where, "needs a string value; anything else never matches")
                )
            elif clause.value == "":
                out.append(
                    GrammarViolation(where, "has an empty value, which no projected row carries")
                )
        case Op.IN:
            # No `isinstance(clause.value, tuple)` branch: `Clause` refuses a bare string,
            # because that is one of the two shapes where SQL is wider than Python, and a
            # second copy here could only ever be reached by a clause built through
            # `model_construct`. See this function's docstring.
            if not clause.value:
                out.append(
                    GrammarViolation(where, "has an empty member list, so it can never match")
                )
            elif any(not isinstance(v, str) or v == "" for v in clause.value):
                out.append(GrammarViolation(where, "has a member that is not a non-empty string"))
        case Op.PREFIX:
            if not isinstance(clause.value, str) or clause.value == "":
                out.append(
                    GrammarViolation(
                        where,
                        "needs a non-empty string; an empty prefix matches every row and "
                        "is a scope written as a no-op",
                    )
                )
    return out


def assert_conjunctive(scope: Scope) -> None:
    """Raise with every violation at once. Called wherever a scope enters the system.

    The name is the invariant: this is what stands between a stored predicate and a scope
    that could widen. There is no disjunction to check for, because `Op` has none; what is
    checked is everything that would let a clause mean one thing to `Clause.matches` and
    another thing to `compile_where`.
    """
    violations = check_grammar(scope)
    if not violations:
        return
    listed = "\n".join(f"  - {v}" for v in violations)
    msg = f"predicate refused:\n{listed}"
    raise PredicateRefusedError(msg)


# ------------------------------------------------------- the document form
def parse_predicate(document: object) -> Scope:
    """Turn the stored jsonb form into a validated Scope.

    Typed as `object` rather than as a mapping because this is the boundary: the argument
    is whatever the jsonb column held, and a column that used to hold an object can hold a
    list the moment a migration or a hand-written UPDATE says so. Narrowing it here means
    the wrong shape is a refusal with a sentence in it rather than an AttributeError.

    The document is an object mapping a field to a matcher, and the object itself is the
    conjunction. Four matcher forms, and no fifth:

    - `"web"`                 field equals web
    - `["web", "sales"]`      field is one of these
    - `{"prefix": "web."}`    field starts with this
    - `{"any": true}`         field is not tested, only declared

    Values must already be strings. Coercing them here looks helpful and is not: jsonb
    `->>` renders a boolean as `true` and Python `str()` renders it as `True`, so a
    coerced boolean is a predicate that means different things on the two evaluators. The
    author is told to store a string instead.
    """
    if not isinstance(document, Mapping):
        msg = "a predicate is a json object mapping a field to a matcher"
        raise PredicateRefusedError(msg)

    clauses: list[Clause] = []
    violations: list[GrammarViolation] = []

    for key, matcher in document.items():
        name = str(key)
        if name.lower() in DISJUNCTION_KEYS:
            violations.append(
                GrammarViolation(
                    name,
                    "disjunction and negation are not in the grammar; two narrow grants "
                    "must never combine into a wider one",
                )
            )
            continue
        clause_or_violation = _matcher_to_clause(name, matcher)
        if isinstance(clause_or_violation, GrammarViolation):
            violations.append(clause_or_violation)
        else:
            clauses.append(clause_or_violation)

    if violations:
        listed = "\n".join(f"  - {v}" for v in violations)
        msg = f"predicate refused:\n{listed}"
        raise PredicateRefusedError(msg)

    scope = Scope(clauses=tuple(clauses))
    assert_conjunctive(scope)
    return scope


def _matcher_to_clause(name: str, matcher: object) -> Clause | GrammarViolation:
    try:
        if isinstance(matcher, str):
            return Clause(field=name, op=Op.EQ, value=matcher)
        if isinstance(matcher, list | tuple):
            members = tuple(matcher)
            if any(not isinstance(m, str) for m in members):
                return GrammarViolation(name, "every member of a list matcher must be a string")
            return Clause(field=name, op=Op.IN, value=members)
        if isinstance(matcher, Mapping):
            return _object_matcher_to_clause(name, matcher)
    except ValidationError as exc:
        # Pydantic's message names the pattern, which is the useful half; the field name is
        # the other half and it is not in there.
        return GrammarViolation(name, f"is not a usable field name or value ({exc.error_count()})")
    return GrammarViolation(
        name,
        "must be a string, a list of strings, {'prefix': ...} or {'any': true}; numbers "
        "and booleans must be stored as strings, because jsonb renders them as text and "
        "Python does not render them the same way",
    )


def _object_matcher_to_clause(name: str, matcher: Mapping[Any, Any]) -> Clause | GrammarViolation:
    keys = {str(k) for k in matcher}
    unknown = keys - MATCHER_KEYS
    if unknown:
        return GrammarViolation(name, f"unknown matcher key(s) {sorted(unknown)}")
    if len(keys) != 1:
        return GrammarViolation(name, "a matcher object carries exactly one key")
    if "prefix" in keys:
        value = matcher["prefix"]
        if not isinstance(value, str) or value == "":
            return GrammarViolation(name, "a prefix matcher needs a non-empty string")
        return Clause(field=name, op=Op.PREFIX, value=value)
    if matcher["any"] is not True:
        return GrammarViolation(name, "an any matcher is written {'any': true}")
    return Clause(field=name, op=Op.ANY)


def to_predicate(scope: Scope) -> dict[str, Any]:
    """Render a Scope back to the stored form.

    The round trip has to be lossless in both directions or the console shows an author
    something other than what they saved. Two clauses on the same field cannot be
    represented, because the document is keyed by field; that is a limit of the stored
    form and not of `Scope`, and it is why this raises rather than silently dropping one.
    """
    out: dict[str, Any] = {}
    for clause in scope.clauses:
        if clause.field in out:
            msg = (
                f"{clause.field} carries more than one clause, which the document form "
                "cannot hold; store the composed scope by reference instead"
            )
            raise PredicateRefusedError(msg)
        match clause.op:
            case Op.ANY:
                out[clause.field] = {"any": True}
            case Op.EQ:
                out[clause.field] = clause.value
            case Op.IN:
                out[clause.field] = list(clause.value or ())
            case Op.PREFIX:
                out[clause.field] = {"prefix": clause.value}
    return out


# ------------------------------------------------------------ satisfiability
def is_unsatisfiable(scope: Scope) -> bool:
    """True when no row can satisfy this scope, whatever the data.

    Composition intersects, so a person holding `department = sales` and `department = web`
    as two separate grants ends up with a scope that matches nothing. That is the correct
    conservative answer and it is also indistinguishable, at the far end of a query, from
    a permission bug or an empty table. Naming it here lets a caller say "your scopes do
    not overlap" instead of "no results".

    Sound, not complete: when it answers True the scope really is impossible, and when it
    answers False the scope may still return nothing for reasons in the data. That is the
    safe direction, since the only thing this decides is whether to bother asking.
    """
    # There is deliberately no `if clause.op is Op.ANY: continue` here, and there was one
    # until a mutation showed it could not change an answer. An `ANY` clause carries no value,
    # so it joins neither the equalities, the prefixes nor the membership intersection below,
    # and a field whose only clause is `ANY` comes back satisfiable either way. The branch
    # read as though it were keeping an unrestricted clause from making a scope look
    # impossible, which is a thing it was never able to do.
    by_field: dict[str, list[Clause]] = {}
    for clause in scope.clauses:
        by_field.setdefault(clause.field, []).append(clause)
    return any(_field_is_unsatisfiable(clauses) for clauses in by_field.values())


def _field_is_unsatisfiable(clauses: Sequence[Clause]) -> bool:
    equals = {c.value for c in clauses if c.op is Op.EQ and isinstance(c.value, str)}
    if len(equals) > 1:
        return True
    prefixes = [c.value for c in clauses if c.op is Op.PREFIX and isinstance(c.value, str)]
    for one in prefixes:
        for other in prefixes:
            # Every value satisfying both must have one prefix as a prefix of the other.
            if not one.startswith(other) and not other.startswith(one):
                return True

    candidates: set[str] | None = None
    for clause in clauses:
        if clause.op is Op.IN and isinstance(clause.value, tuple):
            members = set(clause.value)
            candidates = members if candidates is None else candidates & members
    if candidates is not None:
        # One emptiness test rather than two. The first used to sit above the prefix filter
        # and a mutation showed it could not change an answer: an empty intersection stays
        # empty through the filter and is caught below. Two tests read as two cases and are
        # one, which is the shape this repository removes rather than keeps.
        candidates = {v for v in candidates if all(v.startswith(p) for p in prefixes)}
        if not candidates:
            return True

    if equals:
        only = next(iter(equals))
        if candidates is not None and only not in candidates:
            return True
        if any(not only.startswith(p) for p in prefixes):
            return True
    return False


def clause_entails(narrow: Clause, wide: Clause) -> bool:
    """True when every row matching `narrow` also matches `wide`.

    Sound and incomplete, and the incompleteness is deliberate: a False answer costs a
    caller a shortcut, while a wrong True answer would let a narrow grant stand in for a
    wide one. Only one of those is a security bug, so the analysis is written to fail
    towards False.
    """
    if wide.op is Op.ANY:
        return True
    if narrow.field != wide.field:
        return False

    # There is no `if narrow.op is Op.ANY: return False` here and there was one, which a
    # mutation showed could not fire: the match below has no arm beginning with `ANY`, so an
    # unrestricted narrow clause falls through to the same False. The property it was standing
    # next to is the one that matters and it is asserted directly by
    # `test_an_unrestricted_clause_entails_nothing_narrower_than_itself`: an unrestricted
    # clause entails nothing except another unrestricted one, because a wrong True here is
    # what would let a narrow grant stand in for a wide one. If an `ANY` arm is ever added to
    # that match, this is the sentence that says why it must return False.
    match (narrow.op, wide.op):
        case (Op.EQ, Op.EQ):
            return narrow.value == wide.value
        case (Op.EQ, Op.IN):
            return isinstance(wide.value, tuple) and narrow.value in wide.value
        case (Op.EQ, Op.PREFIX):
            return (
                isinstance(narrow.value, str)
                and isinstance(wide.value, str)
                and narrow.value.startswith(wide.value)
            )
        case (Op.IN, Op.IN):
            return (
                isinstance(narrow.value, tuple)
                and isinstance(wide.value, tuple)
                and set(narrow.value) <= set(wide.value)
            )
        case (Op.IN, Op.EQ):
            return isinstance(narrow.value, tuple) and set(narrow.value) == {wide.value}
        case (Op.IN, Op.PREFIX):
            return (
                isinstance(narrow.value, tuple)
                and isinstance(wide.value, str)
                and all(v.startswith(wide.value) for v in narrow.value)
            )
        case (Op.PREFIX, Op.PREFIX):
            return (
                isinstance(narrow.value, str)
                and isinstance(wide.value, str)
                and narrow.value.startswith(wide.value)
            )
    # A prefix admits unboundedly many values, so it never entails an equality or a
    # membership test.
    return False


def scope_narrows(narrow: Scope, wide: Scope) -> bool:
    """True when every row matching `narrow` also matches `wide`.

    Both sides are conjunctions, so it is enough that each clause of the wider scope is
    entailed by some clause of the narrower one. An unrestricted `wide` is vacuously
    satisfied, which is right: everything narrows the unrestricted scope.
    """
    return all(any(clause_entails(n, w) for n in narrow.clauses) for w in wide.clauses)


# ------------------------------------------------------------- compilation
@dataclass(frozen=True)
class ColumnLayout:
    """Where a predicate field lives in a particular table.

    Two shapes, because both exist in this schema. A field in `promoted` is a real column
    and compiles to one, which is what makes an index usable; everything else compiles to
    a jsonb lookup. The architecture's note about pgvector filtering after the index scan
    is the same problem one layer up: a scope that cannot use an index turns into a scan
    that quietly returns thin results.
    """

    jsonb_column: str = "row_data"
    promoted: frozenset[str] = field(default_factory=frozenset)
    alias: str = ""

    def __post_init__(self) -> None:
        for name in (self.jsonb_column, *sorted(self.promoted)):
            if not IDENT_RE.match(name):
                msg = f"{name!r} is not a plain lowercase identifier and cannot be a column"
                raise PredicateRefusedError(msg)
        if self.alias and not IDENT_RE.match(self.alias):
            msg = f"{self.alias!r} is not a plain lowercase identifier and cannot be an alias"
            raise PredicateRefusedError(msg)

    def column_for(self, name: str) -> str:
        prefix = f"{self.alias}." if self.alias else ""
        if name in self.promoted:
            return f"{prefix}{name}"
        # The key is looked up literally, dots included, because `Clause.matches` does
        # `row.get(name)` on a flat dict. Rendering `a.b` as a jsonb path here would make
        # the SQL evaluator read a nested object the Python one never looks at.
        return f"{prefix}{self.jsonb_column} ->> '{name}'"


@dataclass(frozen=True)
class CompiledPredicate:
    """A WHERE fragment and its bound parameters, as data.

    `certainly_empty` carries the one fact the fragment cannot: `FALSE` is a correct
    compilation of an impossible scope, and a caller that runs it gets an empty result set
    with no way to tell it apart from a table with nothing in it.
    """

    where: str
    params: dict[str, Any]
    certainly_empty: bool = False

    def and_(self, other: CompiledPredicate) -> CompiledPredicate:
        """Conjunction, mirroring `Scope.intersect` at the SQL level."""
        collisions = sorted(set(self.params) & set(other.params))
        if collisions:
            # Silently merging would bind one scope's value into the other's placeholder,
            # which is a permission bug that looks like a typo.
            msg = (
                f"parameter name(s) {collisions} are used by both fragments; "
                "give them distinct prefixes"
            )
            raise PredicateRefusedError(msg)
        return CompiledPredicate(
            where=f"({self.where} AND {other.where})",
            params={**self.params, **other.params},
            certainly_empty=self.certainly_empty or other.certainly_empty,
        )


def _escape_like(value: str) -> str:
    """Neutralise LIKE's wildcards so a prefix means what `str.startswith` means."""
    out = value.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
    for wildcard in ("%", "_"):
        out = out.replace(wildcard, f"{LIKE_ESCAPE}{wildcard}")
    return out


def compile_where(
    scope: Scope,
    layout: ColumnLayout | None = None,
    param_prefix: str = "s",
) -> CompiledPredicate:
    """Compile a scope to a parameterised WHERE fragment.

    Values are never interpolated, at any operator. Identifiers are validated instead,
    because they cannot be parameterised at all and quoting them would only move the
    problem to the quote character.

    The grammar is checked first, so nothing that would mean two different things on the
    two evaluators can be compiled at all.
    """
    if not IDENT_RE.match(param_prefix):
        msg = f"{param_prefix!r} is not a usable parameter prefix"
        raise PredicateRefusedError(msg)
    assert_conjunctive(scope)
    columns = layout if layout is not None else ColumnLayout()

    if scope.is_unrestricted():
        return CompiledPredicate(where="TRUE", params={})
    if is_unsatisfiable(scope):
        # FALSE rather than a raise: an impossible scope is a correct, fail-closed answer,
        # and refusing here would turn a narrow principal into a 500 rather than an empty
        # list. The flag is how the caller says why it was empty.
        return CompiledPredicate(where="FALSE", params={}, certainly_empty=True)

    fragments: list[str] = []
    params: dict[str, Any] = {}
    for i, clause in enumerate(scope.clauses):
        name = f"{param_prefix}{i}"
        column = columns.column_for(clause.field)
        match clause.op:
            case Op.ANY:
                fragments.append("TRUE")
            case Op.EQ:
                fragments.append(f"{column} = :{name}")
                params[name] = clause.value
            case Op.IN:
                fragments.append(f"{column} = ANY(:{name})")
                params[name] = list(clause.value or ())
            case Op.PREFIX:
                fragments.append(f"{column} LIKE :{name} ESCAPE '{LIKE_ESCAPE}'")
                params[name] = f"{_escape_like(str(clause.value))}%"
    return CompiledPredicate(where="(" + " AND ".join(fragments) + ")", params=params)


# ------------------------------------------- the delegation refusal (M18.3.1, M18.3.2)
#: Why a second implementation of the central rule is affordable here and nowhere else.
THE_SQL_REACH_IS_ONLY_EVER_A_SECOND_OPINION: Final = (
    "gate.delegated_reach computes parent intersect agent intersect subtask in SQL, and the "
    "one thing it may never do is hand that reach to something that runs at it. Its only "
    "consumer is the trigger, which compares it against the reach a row claims and raises. A "
    "second implementation used to compute is a second answer to who may see what; a second "
    "implementation used only to disagree is a check. The two are measured against each "
    "other on a real server rather than trusted to agree, because silent drift is the one "
    "failure this arrangement does not survive."
)

#: Why the trigger is not a restatement of the Python check standing beside the same insert.
A_ROW_MAY_NOT_SUPPLY_ITS_OWN_PARENT_REACH: Final = (
    "Below the root of a chain, the left-hand side of the intersection is not a column the "
    "inserter writes: parent_id and parent_grants are mutually exclusive, so a child row is "
    "measured against the reach its parent row recorded and that row was already refused if "
    "it widened. An inserter in control of every column of its own row therefore still "
    "cannot widen. A check written in the application beside the same insert cannot say "
    "that, because it would be reading the same supplied value."
)

#: Why a delegation row is written once and never edited.
A_DELEGATION_ROW_RECORDS_ONE_DECISION: Final = (
    "Every UPDATE is refused. A parent's recorded reach is the bound its children were "
    "measured against, so a reach that can be edited afterwards makes widening a "
    "two-statement job: insert a narrow parent, insert the children under it, then widen the "
    "parent. Nothing needs to edit one of these rows, and the ability to would remove the "
    "only thing the chain check rests on."
)

#: What the trigger cannot establish, said plainly so nobody reads it as more than it is.
THE_ROOT_OF_A_CHAIN_IS_AS_TRUE_AS_ITS_WRITER: Final = (
    "The root row supplies parent_grants and nothing in the database can confirm that it was "
    "the asker's reach. Entitlements are resolved across several tables and the directory "
    "sync by brain.gate.entitle, and a trigger re-resolving them would be the second "
    "implementation this module argues against. So the guarantee is narrow: below the root "
    "no row widens, and at the root the row is as true as whoever wrote it. That leaves one "
    "insert per chain to audit rather than one per hop."
)

#: The schema the delegation table and its functions live in. `gate` rather than `agent`,
#: because `brain.db.SCHEMAS` classifies `gate` as capabilities, grants and scopes, and every
#: column this check reads is one of those. The row is a permissions document; where it is
#: kept is a classification decision and not a filing one.
DELEGATION_SCHEMA: Final = "gate"

#: The table the trigger hangs on, unqualified and then qualified. Both are here so the
#: migration and the SQL below cannot disagree about where the table is, which is the failure
#: `0024` records about rendering an index expression from the module that owns it.
DELEGATION_TABLE: Final = "delegation"
DELEGATION_RELATION: Final = f"{DELEGATION_SCHEMA}.{DELEGATION_TABLE}"

#: Every column the trigger reads off `NEW`. The migration builds the table and this SQL reads
#: it, and a column renamed in one and not the other is a table whose every insert raises at
#: run time rather than at build time. `trigger_columns` reads these back out of the source so
#: a test can hold the two against each other.
DELEGATION_COLUMNS: Final[tuple[str, ...]] = (
    "agent_ceiling",
    "child_grants",
    "child_id",
    "decided_at",
    "parent_grants",
    "parent_id",
    "subtask_ceiling",
)

#: What a delegation refusal is reported as. `check_violation`, because that is what it is: a
#: check the database makes about one row. Which refusal it was belongs in the message and not
#: in a second code, since a caller that has to learn two codes to tell a widened reach from a
#: malformed one will handle neither.
DELEGATION_REFUSED_SQLSTATE: Final = "23514"

#: `Capability.covers`, in SQL. Only a trailing `.*` expands, and it expands to a prefix
#: ending in the dot, so `read:client.*` covers `read:client.name` and never `read:clients`.
#: Written with `left` and `right` rather than with LIKE, because a capability arriving with a
#: `%` in it would otherwise be a pattern rather than a string, which is the same defect
#: `_escape_like` exists for one layer down.
CAPABILITY_COVERS_SQL: Final = """
CREATE OR REPLACE FUNCTION gate.capability_covers(wide text, narrow text)
RETURNS boolean
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
AS $covers$
    SELECT wide = narrow
        OR (right(wide, 2) = '.*'
            AND left(narrow, length(wide) - 1) = left(wide, length(wide) - 1))
$covers$
"""

#: `EntitlementSet.scope_for`, in SQL: the clauses of every grant in the ceiling that covers
#: this capability, conjoined, or NULL when the ceiling covers it with nothing.
#:
#: NULL and `[]` are the two answers that must not be confused, which is why this is a CASE
#: over an existence test rather than an aggregate. `[]` is a ceiling that admits the
#: capability unrestricted; NULL is a ceiling that does not admit it at all, and an aggregate
#: over no rows returns the same empty array for both.
#:
#: The expiry test is inside the match, mirroring `scope_for` refusing an expired principal
#: before it looks at a grant. An expired ceiling therefore admits nothing rather than
#: everything, which is the direction a mistake here has to fail in.
#:
#: `SET timezone = 'UTC'` is what makes `IMMUTABLE` true rather than merely declared. Casting
#: a text timestamp that carries no offset reads the session's `TimeZone`, so without this the
#: function returns different answers on two connections to one server, and IMMUTABLE is a
#: promise the planner is entitled to act on. Pydantic always writes an offset; a row written
#: by hand may not, and this is what decides that such a row means UTC.
ENTITLEMENT_SCOPE_FOR_SQL: Final = """
CREATE OR REPLACE FUNCTION gate.entitlement_scope_for(
    ceiling jsonb, capability text, at timestamptz)
RETURNS jsonb
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
SET timezone = 'UTC'
AS $scope_for$
    WITH matched AS (
        SELECT coalesce(g.value -> 'scope' -> 'clauses', '[]'::jsonb) AS clauses
        FROM jsonb_array_elements(coalesce(ceiling -> 'grants', '[]'::jsonb)) AS g(value)
        WHERE (ceiling ->> 'not_after' IS NULL
               OR at < (ceiling ->> 'not_after')::timestamptz)
          AND gate.capability_covers(g.value -> 'capability' ->> 'value', capability)
    )
    SELECT CASE
        WHEN NOT EXISTS (SELECT 1 FROM matched) THEN NULL
        ELSE (
            SELECT coalesce(jsonb_agg(DISTINCT c.value), '[]'::jsonb)
            FROM matched AS m, LATERAL jsonb_array_elements(m.clauses) AS c(value)
        )
    END
$scope_for$
"""

#: M18.3.1: the child grant, computed as parent intersect agent intersect subtask.
#:
#: A left fold like the Python one, and flattened into a single pass because intersection is
#: associative: a grant survives when both ceilings cover it, and its scope is the parent's
#: clauses conjoined with what each ceiling narrowed it to. Ordered by the parent's own grant
#: order so a reader diffing this against `chain_reach` is comparing like with like.
#:
#: `LEAST` ignores NULLs in PostgreSQL, which is exactly `min` over the bounds that are set,
#: and matches `intersect` taking the tighter of the two. A ceiling with no expiry therefore
#: does not extend one that has it.
#:
#: `SET timezone = 'UTC'` for the reason `ENTITLEMENT_SCOPE_FOR_SQL` gives, and here it also
#: decides what the returned document says: rendering a timestamptz into jsonb uses the
#: session zone, so without this one server prints `+08:00` and another prints `Z` for the
#: same instant. Both are correct and neither is stable, which is enough to make a function
#: declared IMMUTABLE not be.
DELEGATED_REACH_SQL: Final = """
CREATE OR REPLACE FUNCTION gate.delegated_reach(
    parent jsonb, agent_ceiling jsonb, subtask_ceiling jsonb, at timestamptz)
RETURNS jsonb
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
SET timezone = 'UTC'
AS $reach$
    SELECT jsonb_build_object(
        'principal_id', parent ->> 'principal_id',
        'grants', coalesce((
            SELECT jsonb_agg(jsonb_build_object(
                'capability', g.value -> 'capability',
                'scope', jsonb_build_object('clauses', (
                    SELECT coalesce(jsonb_agg(DISTINCT c.value), '[]'::jsonb)
                    FROM jsonb_array_elements(
                        coalesce(g.value -> 'scope' -> 'clauses', '[]'::jsonb)
                        || narrowed.by_the_agent
                        || narrowed.by_the_subtask) AS c(value)
                ))
            ) ORDER BY g.ordinality)
            FROM jsonb_array_elements(coalesce(parent -> 'grants', '[]'::jsonb))
                 WITH ORDINALITY AS g(value, ordinality),
                 LATERAL (
                     SELECT gate.entitlement_scope_for(
                                agent_ceiling, g.value -> 'capability' ->> 'value', at)
                            AS by_the_agent,
                            gate.entitlement_scope_for(
                                subtask_ceiling, g.value -> 'capability' ->> 'value', at)
                            AS by_the_subtask
                 ) AS narrowed
            WHERE narrowed.by_the_agent IS NOT NULL
              AND narrowed.by_the_subtask IS NOT NULL
        ), '[]'::jsonb),
        'not_after', LEAST(
            (parent ->> 'not_after')::timestamptz,
            (agent_ceiling ->> 'not_after')::timestamptz,
            (subtask_ceiling ->> 'not_after')::timestamptz)
    )
$reach$
"""

#: Whether a jsonb column is a reach at all, reported as every fault at once.
#:
#: **This is the fail-closed half and it is here because the alternative fails open.** The SQL
#: above reads `grants`, `capability.value`, `scope.clauses` and `not_after` by name out of
#: what pydantic serialises. Rename one of those fields in `brain.core.entitlement` and every
#: lookup returns NULL, the computed reach comes back holding nothing, and a child claiming
#: nothing passes: the trigger would go on admitting rows while checking nothing at all.
#: Refusing a document it cannot read turns that into a refusal on the first insert.
#:
#: Not STRICT, because a NULL document is one of the faults it exists to name.
ENTITLEMENT_DOCUMENT_FAULTS_SQL: Final = """
CREATE OR REPLACE FUNCTION gate.entitlement_document_faults(label text, doc jsonb)
RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $faults$
    SELECT coalesce(array_agg(fault ORDER BY fault), ARRAY[]::text[])
    FROM (
        SELECT label || ' is not a json object, so no reach can be read out of it' AS fault
        WHERE doc IS NULL OR jsonb_typeof(doc) IS DISTINCT FROM 'object'
        UNION ALL
        SELECT label || ' names no principal_id, and a reach belongs to somebody'
        WHERE jsonb_typeof(doc) = 'object'
          AND jsonb_typeof(doc -> 'principal_id') IS DISTINCT FROM 'string'
        UNION ALL
        SELECT label || ' carries no grants array'
        WHERE jsonb_typeof(doc) = 'object'
          AND jsonb_typeof(doc -> 'grants') IS DISTINCT FROM 'array'
        UNION ALL
        SELECT label || ' carries a grant with no capability value or no scope clauses'
        WHERE jsonb_typeof(doc -> 'grants') = 'array'
          AND EXISTS (
            SELECT 1 FROM jsonb_array_elements(doc -> 'grants') AS g(value)
            WHERE jsonb_typeof(g.value -> 'capability' -> 'value') IS DISTINCT FROM 'string'
               OR jsonb_typeof(g.value -> 'scope' -> 'clauses') IS DISTINCT FROM 'array')
        UNION ALL
        SELECT label || ' carries a not_after that is neither absent nor a timestamp'
        WHERE jsonb_typeof(doc) = 'object'
          AND doc -> 'not_after' IS NOT NULL
          AND jsonb_typeof(doc -> 'not_after') NOT IN ('null', 'string')
    ) AS faults
$faults$
"""

#: `brain.orchestration.delegation.narrowing_refusals`, in SQL. The same four checks, in the
#: same order, and each one is a way a row could widen.
#:
#: The scope check is a containment test on clause sets and deliberately not a comparison of
#: normalised scopes. Clause order and duplication carry no meaning, so a set test needs no
#: agreement about how Python sorts a clause, and there is nothing left to drift: two jsonb
#: clauses are equal when they say the same thing.
#:
#: A capability the parent does not hold at all produces the first finding and not the second,
#: matching the `continue` in the Python original: one missing capability is one refusal, not
#: two ways of saying it.
NARROWING_REFUSALS_SQL: Final = """
CREATE OR REPLACE FUNCTION gate.narrowing_refusals(child jsonb, parent jsonb)
RETURNS text[]
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
SET timezone = 'UTC'
AS $refusals$
    SELECT coalesce(array_agg(finding ORDER BY finding), ARRAY[]::text[])
    FROM (
        SELECT 'the child names principal ' || coalesce(child ->> 'principal_id', '?')
               || ' and the parent names ' || coalesce(parent ->> 'principal_id', '?')
               || '; narrowing keeps the caller''s id, so this row was not produced by '
               || 'narrowing that caller''s reach' AS finding
        WHERE child ->> 'principal_id' IS DISTINCT FROM parent ->> 'principal_id'
        UNION ALL
        SELECT (g.value -> 'capability' ->> 'value')
               || ' is held by the child and by no grant of the parent''s'
        FROM jsonb_array_elements(child -> 'grants') AS g(value)
        WHERE NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(parent -> 'grants') AS p(value)
            WHERE p.value -> 'capability' ->> 'value'
                  = g.value -> 'capability' ->> 'value')
        UNION ALL
        SELECT (g.value -> 'capability' ->> 'value')
               || ' is scoped in the child without every clause the parent''s grant '
               || 'carried, and scopes compose by conjunction only, so a dropped clause '
               || 'is rows the parent could not see'
        FROM jsonb_array_elements(child -> 'grants') AS g(value)
        WHERE EXISTS (
            SELECT 1 FROM jsonb_array_elements(parent -> 'grants') AS p(value)
            WHERE p.value -> 'capability' ->> 'value'
                  = g.value -> 'capability' ->> 'value')
          AND NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(parent -> 'grants') AS p(value)
            WHERE p.value -> 'capability' ->> 'value'
                  = g.value -> 'capability' ->> 'value'
              AND NOT EXISTS (
                SELECT 1 FROM jsonb_array_elements(
                    coalesce(p.value -> 'scope' -> 'clauses', '[]'::jsonb)) AS wanted(value)
                WHERE NOT EXISTS (
                    SELECT 1 FROM jsonb_array_elements(
                        coalesce(g.value -> 'scope' -> 'clauses', '[]'::jsonb)) AS held(value)
                    WHERE held.value = wanted.value)))
        UNION ALL
        SELECT 'the child expires at ' || coalesce(child ->> 'not_after', 'never')
               || ' and the parent at ' || (parent ->> 'not_after')
               || '; a delegated run outliving the reach it came from is a grant with a '
               || 'later expiry than the one it was cut from'
        WHERE parent ->> 'not_after' IS NOT NULL
          AND (child ->> 'not_after' IS NULL
               OR (child ->> 'not_after')::timestamptz
                  > (parent ->> 'not_after')::timestamptz)
    ) AS refusals
$refusals$
"""

#: M18.3.2: the trigger that refuses a delegation row which is not a subset.
#:
#: `SECURITY DEFINER` for one read and one reason. The table has no SELECT policy, because
#: nothing in the application reads a delegation row back and a policy of `USING (true)`
#: written in advance of a screen that needs it would grant back what the flag denied. The
#: chain check still has to read one column of one row by primary key, and it is the only
#: reader there is, so it runs as the owner with a fixed `search_path` and everything it calls
#: is schema-qualified.
#:
#: The UPDATE refusal comes first because it is the cheapest and because it is the check the
#: rest depends on: see `A_DELEGATION_ROW_RECORDS_ONE_DECISION`.
#:
#: There is deliberately no `IF refusals IS NULL` guard. Both of the functions it calls are
#: STRICT and would return NULL for a NULL argument, and `array_length(NULL, 1) IS NULL` reads
#: the same as "nothing to refuse", so that would be a fail-open path if it could be reached.
#: It cannot: the fault check above returns before it for any document that is not an object,
#: which is the only way either argument could be NULL. The guard would be unreachable, and an
#: unreachable guard is this repository's commonest defect rather than its remedy, so the
#: reason it is safe is written here instead of being implemented twice.
DELEGATION_TRIGGER_FUNCTION_SQL: Final = """
CREATE OR REPLACE FUNCTION gate.delegation_narrows()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, gate
AS $narrows$
DECLARE
    parent_reach jsonb;
    parent_decided_at timestamptz;
    faults text[];
    refusals text[];
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'a delegation row records one decision and is not edited afterwards',
            DETAIL = 'a parent reach that can be changed after its children were measured '
                     'against it makes widening a two-statement job';
    END IF;
    IF NEW.parent_id IS NULL THEN
        parent_reach := NEW.parent_grants;
    ELSE
        SELECT d.child_grants, d.decided_at INTO parent_reach, parent_decided_at
        FROM gate.delegation AS d
        WHERE d.id = NEW.parent_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING
                ERRCODE = '23514',
                MESSAGE = 'delegation ' || NEW.child_id || ' names a parent row that is '
                          'not there to bound it';
        END IF;
        IF NEW.decided_at < parent_decided_at THEN
            RAISE EXCEPTION USING
                ERRCODE = '23514',
                MESSAGE = 'delegation ' || NEW.child_id || ' was decided before the '
                          'delegation it descends from',
                DETAIL = 'the timestamps are what an auditor reconstructs the order of a '
                         'chain from, and a chain that runs backwards did not happen';
        END IF;
    END IF;
    faults := gate.entitlement_document_faults('the parent reach', parent_reach)
           || gate.entitlement_document_faults('the agent ceiling', NEW.agent_ceiling)
           || gate.entitlement_document_faults('the subtask ceiling', NEW.subtask_ceiling)
           || gate.entitlement_document_faults('the child reach', NEW.child_grants);
    IF array_length(faults, 1) IS NOT NULL THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'delegation ' || NEW.child_id || ' carries a reach this check cannot '
                      'read: ' || array_to_string(faults, '; ');
    END IF;
    refusals := gate.narrowing_refusals(
        NEW.child_grants,
        gate.delegated_reach(
            parent_reach, NEW.agent_ceiling, NEW.subtask_ceiling, NEW.decided_at));
    IF array_length(refusals, 1) IS NOT NULL THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'delegation ' || NEW.child_id || ' widens rather than narrows: '
                      || array_to_string(refusals, '; ');
    END IF;
    RETURN NEW;
END
$narrows$
"""

#: Both statements, because the trigger fires on UPDATE in order to refuse it. A trigger
#: declared `BEFORE INSERT` alone would leave the edit path open with the refusal written and
#: unreachable, which is this repository's most common defect wearing a different hat.
DELEGATION_TRIGGER_SQL: Final = """
CREATE TRIGGER delegation_narrows
BEFORE INSERT OR UPDATE ON gate.delegation
FOR EACH ROW EXECUTE FUNCTION gate.delegation_narrows()
"""

#: Every statement the migration runs, in dependency order: a function is created before the
#: one that calls it, and the trigger last. Exported as one tuple so the migration executes
#: exactly what the tests install and neither can be given a statement the other does not run.
DELEGATION_INSTALL: Final[tuple[str, ...]] = (
    CAPABILITY_COVERS_SQL,
    ENTITLEMENT_SCOPE_FOR_SQL,
    DELEGATED_REACH_SQL,
    ENTITLEMENT_DOCUMENT_FAULTS_SQL,
    NARROWING_REFUSALS_SQL,
    DELEGATION_TRIGGER_FUNCTION_SQL,
)

#: The reverse, for a downgrade, innermost caller first. Named with their argument types
#: because a function is identified by its signature, and `DROP FUNCTION` on a bare name
#: fails once anything is ever overloaded.
DELEGATION_UNINSTALL: Final[tuple[str, ...]] = (
    "DROP FUNCTION IF EXISTS gate.delegation_narrows()",
    "DROP FUNCTION IF EXISTS gate.narrowing_refusals(jsonb, jsonb)",
    "DROP FUNCTION IF EXISTS gate.entitlement_document_faults(text, jsonb)",
    "DROP FUNCTION IF EXISTS gate.delegated_reach(jsonb, jsonb, jsonb, timestamptz)",
    "DROP FUNCTION IF EXISTS gate.entitlement_scope_for(jsonb, text, timestamptz)",
    "DROP FUNCTION IF EXISTS gate.capability_covers(text, text)",
)

#: How a column of the row under test is spelled in the trigger body.
_NEW_COLUMN = re.compile(r"NEW\.([a-z][a-z0-9_]*)")


def trigger_columns(body: str = DELEGATION_TRIGGER_FUNCTION_SQL) -> tuple[str, ...]:
    """Every column of the row under test that the trigger reads, sorted and deduplicated.

    The table is built by a migration and read by a string in this module, and nothing in
    between type checks the join between them. A column renamed on one side and not the other
    produces a table whose every insert raises at run time, which is fail-closed and is still
    a defect discovered by an operator rather than by a gate.

    Takes the body as an argument rather than reading the constant directly, so that the
    interesting case, a trigger naming a column the table does not have, is one a test can
    hand it. That is the argument `brain.orchestration.delegation.grant_verbs_in` records
    about its own signature.
    """
    return tuple(sorted(set(_NEW_COLUMN.findall(body))))
