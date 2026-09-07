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


def test_intersect_is_defined_only_where_a_type_owns_its_own_meaning() -> None:
    """`intersect` is the exception that proves the rule, and it is here so nobody deletes
    the parametrised test above on the grounds that this name breaks it.

    Three types define it and all three are correct: an entitlement set, a scope, and a
    residency requirement each intersect with their own kind and mean something different by
    it. A single generic `intersect` over all three would be a function that had to know
    about every type it might be handed, which is the shape that ends up with a default.

    What matters is that `EntitlementSet.intersect` is the only one anything computes reach
    with, and `gate.invoke` and `ops.automation.flow_reach` both call it rather than doing
    the set arithmetic themselves. Delete this and a fourth `intersect` looks like it
    belongs."""
    owners = set(_definitions("intersect"))

    assert owners == {
        "core/entitlement.py",
        "core/scope.py",
        "models/routing.py",
    }, "a new intersect appeared; it needs its own argument for owning that meaning"


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
