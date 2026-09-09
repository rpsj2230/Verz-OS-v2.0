"""One implementation each of the rules the whole system rests on.

Every module in this repository argues against reimplementing a central rule, and several
record it as a rejected alternative in their own docstrings. Nothing checked it.

**This exists because of how the code is now being written.** Large parts of tonight's build
were produced by several agents working in parallel on files they could not see each other
touch. That is a good way to get work done and a very good way to end up with two functions
that compile a scope predicate, two enumerations of freshness, or a second way to intersect
an entitlement set. Each copy is reasonable in isolation. The damage is that they drift, and
the one that drifts is discovered by a permission being wrong rather than by a test.

The audit that prompted this was manual and it came out clean: `knowledge/rows.py` and
`knowledge/search.py` both import `core.scope_sql.compile_where` rather than rendering scope
SQL themselves, and `connectors/projection.py` reuses `gate.provenance.Freshness` rather than
declaring its own bands. A manual audit is worth exactly as much as the last time somebody
ran it, which is why it is written down here instead.

**Most of what is here counts definitions by name, and that is not enough on its own.** A
name check catches somebody writing `compile_where` a second time because they did not know
the first one existed. It misses somebody writing it once and calling it something else, and
that is not hypothetical: `core/scope.py` carried a complete second scope-to-SQL renderer
called `to_sql` from the first commit until 2026-09-09, in plain sight, in `core/`, invisible
to the invariant guarding the rule it reimplemented.

So the last three tests in this file count by *shape* instead, reading each function's own
code for what it does rather than for what it is called. That is still not a general
duplicate detector and is not meant to be: it knows one shape, the one that decides who sees
a row, because that is the rule this repository can least afford two answers to. A conceptual
duplicate of anything else still needs a reader.

Task ids: M0.6.4
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "brain"

#: Name to the one module allowed to define it. The value is the argument, so a second
#: definition fails with the reason rather than with a count.
SOLE_DEFINITIONS: dict[str, tuple[str, str]] = {
    "compile_where": (
        "core/scope_sql.py",
        "a second scope-to-SQL renderer is a second place for the LIKE escaping and the "
        "IN-versus-string trap to be got wrong, and the wrong one decides who sees a row",
    ),
    "Freshness": (
        "gate/provenance.py",
        "two freshness scales means an answer described as ageing by one half of the system "
        "and live by the other, and a reader cannot tell which they were shown",
    ),
    "compute_mask": (
        "core/redaction.py",
        "the mask is the whole of field-level permission; a second one is a second answer to "
        "what a person may read",
    ),
    "identity_hash": (
        "gate/ingress.py",
        "the channel salt is what stops a binding on a weak channel being used to find one "
        "on a strong channel, and an unsalted second copy would not obviously look wrong",
    ),
}


def _definitions(name: str) -> list[str]:
    """Every module defining a function or class with this name, as a path relative to the
    package root. Parsed rather than grepped, so a mention in a docstring or a comment is not
    a definition."""
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a file that will not parse fails elsewhere
            continue
        for node in ast.walk(tree):
            # Matched on the node type first so `node.name` is reachable without a
            # suppression: only these three carry a name, and asking mypy to take that on
            # trust is how a real type error gets silenced later by the same comment.
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            if node.name == name:
                found.append(path.relative_to(SRC).as_posix())
                break
    return found


@pytest.mark.parametrize(("name", "expected"), sorted(SOLE_DEFINITIONS.items()))
def test_a_central_rule_is_implemented_exactly_once(name: str, expected: tuple[str, str]) -> None:
    """Delete this and the next parallel build produces a second one, which reads as
    reasonable in the file it appears in and is wrong the day the two disagree.

    Asserted against the module as well as the count: moving the definition is a decision
    somebody should have to make deliberately, because everything importing it is written
    against where it lives."""
    home, why = expected
    found = _definitions(name)

    assert found == [home], f"{name} should exist once, in {home}, because {why}. Found: {found}"


def _intersections() -> dict[str, tuple[str, ...]]:
    """Every function in the source that intersects anything, by module.

    Parsed rather than grepped, for the same reason `_definitions` is: a docstring saying a
    module calls `intersect` is precisely what this exists to disbelieve, and one did.

    Deliberately not narrowed to entitlement sets. Filtering on the enclosing function's
    return annotation gives a tidier list of four and drops `gate/leash.py`, because `decide`
    and `resume` return a decision rather than a reach, and those two are the gate's call
    sites and the whole reason this was written. A scope intersection is worth a reader's
    attention on the same grounds anyway.
    """
    found: dict[str, set[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a file that will not parse fails elsewhere
            continue
        for holder in ast.walk(tree):
            if not isinstance(holder, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(holder):
                called = node.func if isinstance(node, ast.Call) else None
                if isinstance(called, ast.Attribute) and called.attr == "intersect":
                    found.setdefault(path.relative_to(SRC).as_posix(), set()).add(holder.name)
    return {where: tuple(sorted(names)) for where, names in sorted(found.items())}


def test_intersect_is_defined_only_where_a_type_owns_its_own_meaning() -> None:
    """`intersect` is the exception that proves the rule, and it is here so nobody deletes
    the parametrised test above on the grounds that this name breaks it.

    Three types define it and all three are correct: an entitlement set, a scope, and a
    residency requirement each intersect with their own kind and mean something different by
    it. A single generic `intersect` over all three would be a function that had to know
    about every type it might be handed, which is the shape that ends up with a default.

    What matters is that `EntitlementSet.intersect` is the only one anything computes reach
    with, and `gate.leash.decide` and `ops.automation.flow_reach` both call it rather than
    doing the set arithmetic themselves. Delete this and a fourth `intersect` looks like it
    belongs.

    This docstring named the wrong module until 2026-09-08, along with five others and a
    named constant. See the test below, which reads the call sites out of the source."""
    owners = set(_definitions("intersect"))

    assert owners == {
        "core/entitlement.py",
        "core/scope.py",
        "models/routing.py",
    }, "a new intersect appeared; it needs its own argument for owning that meaning"


def test_the_reach_is_computed_where_this_file_says_and_nowhere_else() -> None:
    """**Ten documents said the gate computes the run reach in `brain.gate.invoke.invoke`,
    and that module has never contained that call.** CLAUDE.md said it, `console/reads.py` and
    `console/reach_view.py` said it, the docstring above said it, and once those four were
    corrected an agent reading the source found six more: `agents/catalogue.py`,
    `agents/model.py`, `ops/automation_piece.py`, `tools/run_skill.py`, a named constant in
    `console/workspace.py` and its own test. They agreed with one another because each was
    copied from the last, and none agreed with the code. The gate computes it in
    `gate/leash.py`, in `decide` and again in `resume`.

    `reads.py` had additionally turned "two call sites" into "two implementations", and that
    is the drift worth catching rather than the wrong module name: a document saying there are
    two implementations of the central rule makes writing a second one sound like the status
    quo instead of the thing the rule forbids.

    A sentence naming a module cannot go stale loudly, so this reads the call sites out of the
    source. Moving the computation fails here, and the failure names where it moved to.

    Pinned exactly rather than as a superset, which is what `SOLE_DEFINITIONS` and the test
    above already do and for the same reason: a new place that intersects two reaches is a new
    place the central rule is applied, and whether that is right is a question for a person.
    The answer to a failure here is to read the new entry and then add it, not to loosen the
    comparison.

    Delete this and the prose can drift again, and the next reader looking for where an
    agent's reach is decided is sent to a module that does not decide it."""
    assert _intersections() == {
        "agents/install.py": ("rehearse",),
        "channels/room.py": ("floor",),
        "console/reach_view.py": ("run_reach",),
        "console/reads.py": ("audience",),
        "core/department.py": (
            "admits_department",
            "compose",
            "plan_cross_department",
            "starter_scopes",
        ),
        "core/entitlement.py": ("intersect", "scope_for"),
        "demo.py": ("record_grants",),
        "gate/leash.py": ("decide", "resume"),
        "identity/sessions.py": ("reach_for",),
        "knowledge/verification.py": ("may_name_verifier",),
        "memory/formation.py": ("may_recall",),
        "memory/review.py": ("agent_memory",),
        "ops/automation.py": ("flow_reach",),
        "ops/denial_alerts.py": ("reach",),
        "ops/feedback.py": ("may_flag",),
        "tools/run_skill.py": ("handler", "run_skill_script"),
    }


def _timed_intersections() -> dict[str, tuple[str, ...]]:
    """Every function that hands `intersect` an instant, by module.

    A second argument, positional or `now=`. `Scope.intersect` takes one argument and
    therefore never appears here, which is what makes this a list of entitlement
    intersections without having to resolve a type.
    """
    found: dict[str, set[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a file that will not parse fails elsewhere
            continue
        for holder in ast.walk(tree):
            if not isinstance(holder, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(holder):
                if not isinstance(node, ast.Call):
                    continue
                called = node.func
                if not (isinstance(called, ast.Attribute) and called.attr == "intersect"):
                    continue
                # A second argument, positional or by name. `Scope.intersect` takes one.
                timed = len(node.args) > 1 or any(one.arg == "now" for one in node.keywords)
                if timed:
                    found.setdefault(path.relative_to(SRC).as_posix(), set()).add(holder.name)
    return {where: tuple(sorted(names)) for where, names in sorted(found.items())}


def test_every_intersection_that_knows_the_instant_passes_it() -> None:
    """**`EntitlementSet.intersect` evaluates the right-hand side's expiry, and until
    2026-09-08 it had no way to be told what time it was.** It read the process clock, and
    the four surfaces that ask "may this reader be told this" put the reader on the right, so
    the reader's expiry was the thing judged against the wrong instant. It failed permissive.

    It was found by a test whose fixture expired at noon: green on the day it was written and
    red the next, with nothing about the code having changed. That is the only reason anybody
    looked, which is worth saying plainly, because a defect that only shows up as a clock
    passing a fixture is a defect that can sit for a year.

    This is pinned as an exact map rather than as "every site passes it", because five sites
    have no instant in scope and inventing one for them would be worse than the wall clock:

      channels/room.py floor, console/reach_view.py run_reach, console/reads.py audience,
      ops/automation.py flow_reach

    Each of those would need `now` threaded from its own callers, which is a wider change
    than the defect required and is the sort of thing that gets done badly at the end of a
    long day. They are listed here so the gap is a decision with a name on it rather than an
    omission, and adding one to the map above is how it gets closed.

    A function that acquires a `now` and does not pass it fails nothing here, which is the
    limit of this check: what it catches is a site that *stops* passing one.

    Delete this and the instant an intersection is evaluated at goes back to being whatever
    the process clock happened to say, in the one function the whole platform rests on."""
    assert _timed_intersections() == {
        "agents/install.py": ("rehearse",),
        "gate/leash.py": ("decide", "resume"),
        "identity/sessions.py": ("reach_for",),
        "knowledge/verification.py": ("may_name_verifier",),
        "memory/formation.py": ("may_recall",),
        "memory/review.py": ("agent_memory",),
        "ops/denial_alerts.py": ("reach",),
        "ops/feedback.py": ("may_flag",),
        "tools/run_skill.py": ("handler", "run_skill_script"),
    }


def test_the_module_the_documents_used_to_name_still_computes_no_reach() -> None:
    """The specific claim, asserted on its own so a failure says what went wrong rather than
    handing the reader a sixteen-entry diff to compare by eye.

    `gate/invoke.py` is a real module doing real work on the request path, and it is entirely
    reasonable that somebody would expect the intersection to live there. It does not, and the
    day it does, the four documents corrected on 2026-09-08 become right again by accident,
    which is a worse state than being wrong: nobody would then know the sentence had ever been
    checked.

    **Guarded by what was read.** A mutation found this: the first version asserted the
    absence against `_intersections()` and nothing stopped that becoming an absence asserted
    against an empty mapping, which is true for every state the source could be in. An absent
    key and an empty scan are the same answer, so the module that does compute the reach is
    asserted present in the same breath.

    Delete this and the correction survives only as a paragraph."""
    found = _intersections()

    assert "gate/leash.py" in found, "nothing was read, so the absence below proves nothing"
    assert "gate/invoke.py" not in found


# --- a second renderer, whatever it is called ------------------------------------------------

#: The one module that may turn a scope into SQL.
#:
#: `core/scope.py` held `Scope.to_sql` and `Clause.to_sql`, a complete second renderer of the
#: rule that decides who can see what. The owner decided on 2026-09-09 to delete them, as item
#: 40 of `docs/needs-rupash.md`, on three grounds that are all about the second copy being the
#: *worse* one rather than merely redundant: it hard-coded `row_data ->> field` so it could
#: never use a promoted column, it never called `assert_conjunctive`, which is the check that
#: stops a scope widening rather than narrowing, and it had nowhere to record that an
#: impossible scope was impossible.
SANCTIONED_RENDERER = "core/scope_sql.py"

#: Every function under `src/brain` allowed to turn a scope or a clause into SQL, by module.
#:
#: Two, not one, and both live in the sanctioned module. `compile_where` walks the clauses and
#: emits the predicate; `ColumnLayout.column_for` decides whether a field is a real column or a
#: jsonb lookup. They are pinned separately because splitting a renderer across two functions is
#: how the next one arrives without either half looking like a renderer.
SANCTIONED_RENDERING_FUNCTIONS: dict[str, tuple[str, ...]] = {
    SANCTIONED_RENDERER: ("column_for", "compile_where"),
}

#: The jsonb text operator. Building one in code means turning a field named in a predicate
#: into a column expression, which is the first half of rendering a scope whatever else the
#: function goes on to do.
JSON_FIELD_REFERENCE = "->>"

#: The comparison shapes a compiled predicate is made of, each written against a bound
#: parameter. Bound rather than bare, deliberately: `ops/sweeps.py` and `ops/schema_check.py`
#: both hold catalogue queries containing `LIKE` and `= ANY(`, and neither is rendering a
#: scope. The `:` is what makes this the shape of a predicate compiled from somebody's grant.
PREDICATE_FRAGMENT_MARKERS = (" = :", " = ANY(:", " LIKE :", " ESCAPE ")

#: How a function shows that it is reading the clause grammar rather than writing SQL of its
#: own: it dispatches on `Op`, or it walks `.clauses`.
GRAMMAR_ATTRIBUTES = frozenset({"clauses"})


def _code_strings(
    holder: ast.FunctionDef | ast.AsyncFunctionDef, documented: set[int]
) -> list[str]:
    """Every string constant in this function's code, with docstrings left out.

    Parsed rather than grepped, and that distinction is the whole reason this works:
    `knowledge/rows.py` mentions `fields ->> 'name'` twice, in a comment and in a docstring,
    explaining what `compile_where` produces. Prose about the rule is not a second copy of it,
    and a grep cannot tell the difference, which is how a check like this ends up either
    useless or switched off.
    """
    return [
        node.value
        for node in ast.walk(holder)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in documented
    ]


def _reads_the_clause_grammar(holder: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Whether this function takes a scope apart: `Op.SOMETHING`, or an attribute `.clauses`."""
    for node in ast.walk(holder):
        if not isinstance(node, ast.Attribute):
            continue
        if isinstance(node.value, ast.Name) and node.value.id == "Op":
            return True
        if node.attr in GRAMMAR_ATTRIBUTES:
            return True
    return False


def _scope_sql_renderers() -> dict[str, tuple[str, ...]]:
    """Every function under `src/brain` that turns a scope or a clause into SQL, by module.

    Two shapes count, and the second is the one a name check cannot see.

    A function builds a **column expression** when its code contains `->>`. There is exactly
    one reason to write that operator: a field named in a predicate has to become something a
    WHERE clause can compare. That alone is enough, without any other evidence, because it is
    the half of rendering that a second implementation would most plausibly extract into a
    helper of its own and thereby hide.

    A function **compiles a predicate** when it both emits one of the bound-parameter
    comparison shapes and reads the clause grammar. Either signal alone is ordinary: `seed.py`
    deletes rows with `= ANY(:targets)` and never looks at a clause, while a dozen modules
    build scopes out of `Op.EQ` and emit no SQL at all. Together they are a renderer, whatever
    it is called, because there is nothing else that walks a grant's clauses and produces SQL
    from them.
    """
    found: dict[str, set[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a file that will not parse fails elsewhere
            continue
        documented = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for holder in ast.walk(tree):
            if not isinstance(holder, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            strings = _code_strings(holder, documented)
            builds_a_column = any(JSON_FIELD_REFERENCE in one for one in strings)
            emits_a_fragment = any(
                marker in one for one in strings for marker in PREDICATE_FRAGMENT_MARKERS
            )
            if builds_a_column or (emits_a_fragment and _reads_the_clause_grammar(holder)):
                where = str(path.relative_to(SRC)).replace(chr(92), "/")
                found.setdefault(where, set()).add(holder.name)
    return {where: tuple(sorted(names)) for where, names in sorted(found.items())}


def test_no_second_scope_to_sql_renderer_arrives_under_another_name() -> None:
    """**The gap this file had, found by an agent building the match cascade, and widened on
    2026-09-09 when the renderer it had recorded as an exception was deleted.**

    Every test above counts definitions by *name*. That catches somebody writing
    `compile_where` twice and misses somebody writing it once and calling it `to_sql`, which is
    exactly what `core/scope.py` did: a full scope-to-SQL renderer, sitting in `core/`,
    invisible to the invariant guarding the rule it reimplements.

    So this counts by shape instead, and by function rather than by module. The earlier version
    asked which *modules* contained a `->>` in code, which was enough to name the second
    renderer once somebody already suspected it and not enough to catch the next one: a module
    can hold a renderer and a hundred other things, and half a renderer looks like neither.
    `_scope_sql_renderers` reads what each function does instead.

    Pinned as an exact map rather than as "no more than two", because a check that tolerates
    two tolerates three on the day somebody adds one, and the whole value here is that the
    number is watched. The answer to a failure here is to read the new entry and decide, not to
    loosen the comparison. If the new entry really is part of the one renderer, it belongs in
    `SANCTIONED_RENDERING_FUNCTIONS` with a sentence saying why.

    Delete this and the next renderer is discovered by a permission being wrong."""
    found = _scope_sql_renderers()

    assert found == SANCTIONED_RENDERING_FUNCTIONS, (
        "a function builds scope SQL that compile_where does not own; read it and decide, "
        "rather than adding it to the constant to make this pass"
    )


def test_the_renderer_deleted_from_core_scope_has_not_come_back() -> None:
    """The specific claim, asserted on its own so a failure says what went wrong rather than
    handing the reader a map to compare by eye. Written in the same shape as
    `test_the_module_the_documents_used_to_name_still_computes_no_reach` above, and for the
    same reason a mutation found there: an absence asserted against a scan that read nothing is
    true for every state the source could be in, so what was read is asserted first.

    `core/scope.py` is where the second renderer lived, and it is a completely reasonable place
    to put one back. `Scope` is the object a person needing scope SQL is already holding, and a
    method on it is easier to find than a function in another module, which is precisely why the
    copy that skipped `assert_conjunctive` was the one anybody new would have reached for.

    Both assertions name what was read. This file is read out of a working tree that other
    sessions write to, and on 2026-09-09 this test went red once inside a sixty-second run and
    green on every run after it, while the test above it passed in the same run off the same
    scan function. A bare `assert x not in y` failing there tells the next reader only that it
    failed, which is indistinguishable from the renderer genuinely being back.

    Delete this and the deletion survives only as a paragraph in a docstring."""
    found = _scope_sql_renderers()

    assert SANCTIONED_RENDERER in found, (
        f"nothing was read, so the absence below proves nothing. Found: {found}"
    )
    assert "core/scope.py" not in found, (
        f"core/scope.py renders scope SQL again, in {found.get('core/scope.py')}"
    )


def test_the_sanctioned_renderer_is_the_one_everything_actually_calls() -> None:
    """The positive half. The test above counts who *renders*, and would pass just as happily
    on a tree where `compile_where` had been deleted and nothing rendered a scope at all.

    So this counts who *calls*. Every module needing scope SQL imports `compile_where` from the
    sanctioned module, and more than a couple of them do, which is what makes it the live
    implementation rather than a module somebody could quietly stop using.

    Delete this and the one renderer can be orphaned without any test having an opinion, which
    is the state the deleted one was in for as long as it existed."""
    callers = {
        str(path.relative_to(SRC)).replace(chr(92), "/")
        for path in sorted(SRC.rglob("*.py"))
        if "compile_where" in path.read_text(encoding="utf-8")
    }

    assert len(callers) > 2, f"only {sorted(callers)} mention compile_where"
    assert SANCTIONED_RENDERER in callers
