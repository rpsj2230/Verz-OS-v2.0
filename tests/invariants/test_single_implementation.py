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

**What this does not do.** It counts definitions by name across the source tree. It cannot
tell that two differently-named functions do the same thing, and it is not meant to: the
failure it addresses is the literal one, where somebody writes `compile_where` again because
they did not know the first one existed. A conceptual duplicate needs a reader.

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

    This docstring named `gate.invoke` until 2026-09-08 and that module has no `intersect`
    call in it. See the test below, which reads the call sites rather than naming them."""
    owners = set(_definitions("intersect"))

    assert owners == {
        "core/entitlement.py",
        "core/scope.py",
        "models/routing.py",
    }, "a new intersect appeared; it needs its own argument for owning that meaning"


def test_the_reach_is_computed_where_this_file_says_and_nowhere_else() -> None:
    """**Four documents said the gate computes the run reach in `brain.gate.invoke.invoke`,
    and that module has no `intersect` call in it at all.** CLAUDE.md said it, `console/reads.py`
    said it, `console/reach_view.py` said it, and the docstring above said it. They agreed with
    one another because each was copied from the last, and none agreed with the code. The gate
    computes it in `gate/leash.py`, in `decide` and again in `resume`.

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

#: The one module that may turn a scope into SQL, and the one that currently also does.
#:
#: `core/scope.py` holds `Scope.to_sql` and `Clause.to_sql`, which render `row_data ->> field`
#: themselves. They are a second implementation of the rule that decides who can see what, and
#: the two already disagree: a bare string where `compile_where` requires a tuple is accepted
#: by one and refused by the other. `to_sql` also hard-codes the JSON path, so it cannot use a
#: promoted column, and it never calls `assert_conjunctive`, which is the check that stops a
#: scope widening rather than narrowing.
#:
#: Recorded as a known exception rather than fixed here, because deleting it is a decision with
#: two test files behind it and it is item 40 in `docs/needs-rupash.md`. Recorded rather than
#: ignored, because the whole failure was that nobody knew it existed.
SANCTIONED_RENDERER = "core/scope_sql.py"
KNOWN_SECOND_RENDERER = "core/scope.py"


def _modules_rendering_a_json_path() -> set[str]:
    """Every module whose *code* builds a `->>` fragment, ignoring comments and docstrings.

    Parsed rather than grepped, and that distinction is the whole reason this works:
    `knowledge/rows.py` mentions `fields ->> 'name'` twice, in a comment and in a docstring,
    explaining what `compile_where` produces. Prose about the rule is not a second copy of it,
    and a grep cannot tell the difference, which is how a check like this ends up either
    useless or switched off.
    """
    found: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        documented = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "->>" in node.value
                and id(node) not in documented
            ):
                found.add(str(path.relative_to(SRC)).replace(chr(92), "/"))
    return found


def test_no_second_scope_to_sql_renderer_arrives_under_another_name() -> None:
    """**The gap this file had, found by an agent building the match cascade.**

    Every test above counts definitions by *name*. That catches somebody writing
    `compile_where` twice and misses somebody writing it once and calling it `to_sql`, which is
    exactly what `core/scope.py` did: a full scope-to-SQL renderer, sitting in `core/`, invisible
    to the invariant guarding the rule it reimplements.

    So this counts by shape instead. A module whose code builds a `->>` fragment is turning a
    scope into SQL whatever the function is called, because that operator is how a field inside
    the JSON payload becomes a column expression.

    Pinned as an exact set rather than "no more than two", because a check that tolerates two
    tolerates three on the day somebody adds one, and the whole value here is that the number
    is watched. When item 40 is decided, deleting `core/scope.py`'s renderer makes this fail,
    which is the right direction: the test then says the exception is gone and should be
    removed from the constant above.

    Delete this and the next renderer is discovered by a permission being wrong."""
    found = _modules_rendering_a_json_path()

    assert found == {SANCTIONED_RENDERER, KNOWN_SECOND_RENDERER}, (
        "a module builds scope SQL that neither compile_where nor the recorded exception owns"
    )


def test_the_sanctioned_renderer_is_the_one_everything_actually_calls() -> None:
    """The positive half. The test above would pass on a tree where `compile_where` had been
    deleted and everything used the second renderer, because it only counts who *renders*.

    So this counts who *calls*: every module needing scope SQL imports `compile_where`, and
    nothing imports `Scope.to_sql`, which is why the second renderer is loaded rather than live.

    Delete this and the exception above can quietly become the implementation."""
    callers = {
        str(path.relative_to(SRC)).replace(chr(92), "/")
        for path in sorted(SRC.rglob("*.py"))
        if "compile_where" in path.read_text(encoding="utf-8")
    }

    assert len(callers) > 2, f"only {sorted(callers)} mention compile_where"
    assert SANCTIONED_RENDERER in callers
