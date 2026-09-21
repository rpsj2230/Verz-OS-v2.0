"""A caught exception's text leaves a database-touching module only through `safe_error.describe`.

Found on the owner's install on 2026-09-21: `brain.ops.post_deploy` printed `{exc}` and psycopg
had quoted a fragment of the database password into it. Any module that opens a connection, or
reads the settings that name one, can catch an exception whose message carries the URL. So in those
modules an `except ... as exc` handler may not put `exc` into an f-string, `str()`, `repr()`,
`print()` or a `%`-format; it hands `exc` to `brain.ops.safe_error.describe`, or logs the class.

A handler catching only this repository's own exception classes is exempt: their messages are
written here, and the one way a driver's text gets into one is a wrap site that caught the
driver's exception, which this check does not exempt.

Parsed, not searched, for the reason `test_configuration_is_read_in_one_place` gives.

Task ids: M38.5.1
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

SRC = Path(__file__).resolve().parents[2] / "src" / "brain"

#: A module is in scope when its source says any of these: it connects, or it holds the address.
DATABASE_MARKERS = (
    "psycopg",
    "create_engine",
    "create_async_engine",
    "database_url",
    "libpq_conninfo",
)
#: Named by the finding whatever their source says today.
ALWAYS_SCANNED = frozenset(
    {
        "ops/post_deploy.py",
        "ops/sweeps.py",
        "ops/schema_check.py",
        "ops/worker.py",
        "ops/log_store.py",
    }
)


#: The calls a handler's exception may pass through: `brain.ops.safe_error`'s two.
REDACTORS = frozenset({"describe", "redact"})


def in_scope() -> list[Path]:
    found = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel == "ops/safe_error.py":
            continue
        text = path.read_text(encoding="utf-8")
        if rel in ALWAYS_SCANNED or any(marker in text for marker in DATABASE_MARKERS):
            found.append(path)
    return found


def own_exception_classes() -> frozenset[str]:
    """Every class name defined in `src/brain`: an exception caught by one of these is ours."""
    names: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names.update(n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    return frozenset(names)


def _caught(handler: ast.ExceptHandler) -> list[str]:
    kinds = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return [
        k.id if isinstance(k, ast.Name) else k.attr if isinstance(k, ast.Attribute) else ""
        for k in kinds
    ]


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def raw_exception_text(
    tree: ast.AST, own: frozenset[str] = frozenset()
) -> Iterator[tuple[int, str]]:
    """Every place a handler's bound exception is turned into text other than by `describe`."""
    for handler in ast.walk(tree):
        if not isinstance(handler, ast.ExceptHandler) or handler.name is None:
            continue
        if all(kind in own for kind in _caught(handler)):
            continue
        name = handler.name
        cleared = {
            id(inner)
            for call in ast.walk(handler)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id in REDACTORS
            for inner in ast.walk(call)
        }
        for stmt in handler.body:
            for node in ast.walk(stmt):
                if id(node) in cleared:
                    continue
                if isinstance(node, ast.FormattedValue) and _is_name(node.value, name):
                    yield node.lineno, f"f-string {{{name}}}"
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    called = node.func.id
                    if called in {"str", "repr"} and any(_is_name(a, name) for a in node.args):
                        yield node.lineno, f"{called}({name})"
                    elif called == "print" and any(_is_name(a, name) for a in node.args):
                        yield node.lineno, f"print({name})"
                elif (
                    isinstance(node, ast.BinOp)
                    and isinstance(node.op, ast.Mod)
                    and any(_is_name(n, name) for n in ast.walk(node.right))
                ):
                    yield node.lineno, f"% {name}"


def test_the_scope_covers_the_modules_that_leaked() -> None:
    """Delete this and a marker list that stopped matching would shrink the scan to nothing,
    and the check below would pass over an empty set."""
    names = {p.relative_to(SRC).as_posix() for p in in_scope()}
    assert names >= ALWAYS_SCANNED
    assert "db.py" in names


def test_no_database_module_turns_a_caught_exception_into_raw_text() -> None:
    """Delete this and the next `print(f"{exc}")` beside a connection is the 2026-09-21 leak."""
    own = own_exception_classes()
    offenders = [
        f"{path.relative_to(SRC).as_posix()}:{line}: {what}"
        for path in in_scope()
        for line, what in raw_exception_text(ast.parse(path.read_text(encoding="utf-8")), own)
    ]
    assert offenders == [], (
        "route these through brain.ops.safe_error.describe(exc), which keeps the class and a "
        "redacted sentence:\n" + "\n".join(offenders)
    )


def test_the_checker_finds_each_shape() -> None:
    """Delete this and a checker that found nothing would keep the check above green for ever."""
    source = (
        "try:\n    pass\nexcept Exception as exc:\n"
        "    print(f'{exc}')\n    log.warning('x', error=str(exc))\n    print(exc)\n"
        "    y = '%s' % exc\n    z = repr(exc)\n    ok = describe(exc)\n"
        "    fine = redact(str(exc))\n"
    )
    found = [what for _, what in raw_exception_text(ast.parse(source))]
    assert found == ["f-string {exc}", "str(exc)", "print(exc)", "% exc", "repr(exc)"]
    ours = source.replace("except Exception", "except OurError")
    assert list(raw_exception_text(ast.parse(ours), frozenset({"OurError"}))) == []
    mixed = source.replace("except Exception", "except (OurError, OSError)")
    assert len(list(raw_exception_text(ast.parse(mixed), frozenset({"OurError"})))) == 5
