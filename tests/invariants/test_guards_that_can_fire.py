"""No clause in this repository may read as a guard and guard nothing.

This is the single defect that has recurred most often here, and it has arrived by four
different routes in one week: an empty-capability check placed behind `Capability`'s own
validation, so the input it refused could never reach it; a wildcard-entity guard behind the
same validation; a field scan that duplicated a direct test; and a Pydantic `field_validator`
whose entire body was `return v`, with the real check four lines below in `model_post_init`.

Every one of them passed review, because a guard that cannot fire looks exactly like a guard.
It is worse than its absence: the next person to touch the file reads it, believes the
property is enforced, and writes code that depends on it.

**Structural rather than a reviewer's habit, and deliberately narrow.** This finds the literal
shape, a validator that returns its argument unchanged. It cannot tell that a check is
unreachable because something upstream already refuses the input, which needs a reader and is
why the mutation discipline in CLAUDE.md exists. Catching one shape mechanically does not
retire that discipline; it removes the one instance a reader keeps missing.

Task ids: none
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "brain"

VALIDATOR_DECORATORS = frozenset({"field_validator", "model_validator", "validator"})


def decorator_name(node: ast.expr) -> str:
    """The bare name of a decorator, whether it was called or not."""
    if isinstance(node, ast.Call):
        return decorator_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def returns_its_argument_unchanged(fn: ast.FunctionDef) -> bool:
    """True when the whole body is `return <one of my own parameters>`.

    A docstring ahead of it does not count as a body, because a validator that explains
    itself and does nothing is the exact case this looks for rather than an exception to it.
    """
    body = list(fn.body)
    leading = body[0] if body else None
    if (
        isinstance(leading, ast.Expr)
        and isinstance(leading.value, ast.Constant)
        and isinstance(leading.value.value, str)
    ):
        body = body[1:]
    if len(body) != 1:
        return False
    only = body[0]
    if not isinstance(only, ast.Return) or not isinstance(only.value, ast.Name):
        return False
    names = {one.arg for one in fn.args.args} | {one.arg for one in fn.args.posonlyargs}
    return only.value.id in names


def validators() -> list[tuple[Path, ast.FunctionDef]]:
    found: list[tuple[Path, ast.FunctionDef]] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if any(decorator_name(one) in VALIDATOR_DECORATORS for one in node.decorator_list):
                found.append((path, node))
    return found


def test_no_validator_in_this_repository_returns_its_argument_unchanged() -> None:
    """**Written from a live one.** `core.principal.Principal._bounded_engagements` was a
    `@field_validator("employment")` whose entire body was `return v`. The rule it is named
    for, that a contractor or a partner must carry an expiry, was enforced in
    `model_post_init` immediately below, and could not have been enforced where it stood: a
    field validator sees one field, and the rule needs `employment` and `not_after` together.

    So the validator was not merely redundant. It was a promise that the field alone was
    checked, sitting on the class that decides who this system thinks somebody is.

    Delete this and the shape comes back, which it has four times in a week. A refactor that
    moves a check out of a validator and leaves the shell behind produces exactly this, and
    the suite stays green because nothing was ever asserted about the shell.

    The positive case is the rest of the repository: this passes today with real validators in
    it, several of which raise, so it is not satisfied by a tree that has none."""
    found = validators()

    empty = [
        f"{path.relative_to(SRC.parents[1])}: {fn.name} returns its argument unchanged"
        for path, fn in found
        if returns_its_argument_unchanged(fn)
    ]

    assert empty == [], empty
    assert len(found) > 10, f"only {len(found)} validators found; the scan is not reading the tree"


def test_the_scan_recognises_the_shape_it_is_looking_for() -> None:
    """The test for the test. `returns_its_argument_unchanged` is the whole content of the
    invariant above, and an assertion over a tree that satisfies it proves nothing about a
    function that always answers False.

    Both directions, and the docstring case explicitly: a validator that explains itself at
    length and then returns its input is the one a reader is most likely to trust.

    Delete this and the invariant above can be defeated by a scan that finds nothing, which is
    the same failure it exists to catch, one level up."""
    empty = ast.parse("def f(cls, v):\n    return v\n").body[0]
    documented = ast.parse('def f(cls, v):\n    """Why."""\n    return v\n').body[0]
    raising = ast.parse("def f(cls, v):\n    if not v:\n        raise ValueError\n    return v\n")
    other = ast.parse("def f(cls, v):\n    return v.strip()\n").body[0]

    assert isinstance(empty, ast.FunctionDef) and returns_its_argument_unchanged(empty)
    assert isinstance(documented, ast.FunctionDef) and returns_its_argument_unchanged(documented)
    assert isinstance(raising.body[0], ast.FunctionDef)
    assert not returns_its_argument_unchanged(raising.body[0])
    assert isinstance(other, ast.FunctionDef) and not returns_its_argument_unchanged(other)
