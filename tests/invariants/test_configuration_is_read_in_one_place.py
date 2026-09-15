"""Configuration is read in one place, and reading it builds nothing.

CLAUDE.md has said "nothing reads the environment directly" since the day it was written, and
until 2026-09-15 ten modules did. Nobody was careless. The settings object lived in
`brain.app`, which builds the web application when imported, so the cheap way to one value was
`os.environ`, and six readers of the database address grew three different rules about which
of its two names wins. See `brain.settings`.

Two checks, because each half without the other decays. A rule that nothing reads the
environment, with the settings module still expensive to import, is a rule people route around
with the next direct read. A cheap settings module with no rule is an invitation nobody has to
accept.

**Parsed, not searched.** A substring test for `os.environ` is satisfied by this docstring and
by every module docstring that explains why it does not read the environment, several of which
now exist. The shapes below are the ones Python can actually read the environment through.

Task ids: M41.1.2
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "brain"
THE_READER = SRC / "settings.py"
#: Outside `src/brain` and scanned all the same. Alembic executes it with the application's
#: address already on its config, and until 2026-09-15 it overwrote that address with
#: `DATABASE_URL` read from the process. See `brain.migrate.alembic_url`.
#:
#: The migration versions are not scanned, and one of them does read the environment:
#: `0001_foundation.py` reads `APP_ROLE_PASSWORD` to create the application role. A shipped
#: migration is history an installed database has already run, so it is recorded here rather
#: than edited or exempted in silence.
ALSO_SCANNED = (REPO / "migrations" / "env.py",)

#: The modules the environment lives on. `posix` and `nt` are what `os` re-exports it from.
ENVIRONMENT_MODULES = frozenset({"os", "posix", "nt"})
#: Every attribute of those modules that reads or writes the process environment.
ENVIRONMENT_NAMES = frozenset({"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"})


def environment_reads(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """Every place this module touches the process environment, as line and expression.

    Aliases are followed, so `import os as system` then `system.environ` is found. A mapping
    handed in as a parameter and merely called `env` or `environ` is not a read, which is the
    difference from `brain.ops.independence.environment_reads`: that check is about `INSTALL_`
    names wherever they are looked up, and this one is about where the lookup starts.
    """
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in ENVIRONMENT_MODULES:
                    bound.add(alias.asname if alias.asname and "." not in alias.name else root)
        if isinstance(node, ast.ImportFrom) and node.module in ENVIRONMENT_MODULES:
            for alias in node.names:
                if alias.name in ENVIRONMENT_NAMES:
                    yield node.lineno, f"from {node.module} import {alias.name}"

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in ENVIRONMENT_NAMES
            and isinstance(node.value, ast.Name)
            and node.value.id in bound
        ):
            yield node.lineno, f"{node.value.id}.{node.attr}"


def imports_of_the_application(tree: ast.AST) -> Iterator[int]:
    """Every line importing `brain.app`, in any of the three spellings that reach it."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "brain.app" or alias.name.startswith("brain.app.") for alias in node.names
        ):
            yield node.lineno
        if isinstance(node, ast.ImportFrom) and (
            node.module == "brain.app"
            or (node.module == "brain" and any(alias.name == "app" for alias in node.names))
        ):
            yield node.lineno


def _modules() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _scanned() -> tuple[Path, ...]:
    """Every file the rule reads: each module under `src/brain`, and `ALSO_SCANNED`.

    Named so the rule and its positive sibling ask the same question. A mutation run on
    2026-09-15 dropped `ALSO_SCANNED` from the rule's own loop and survived, because the
    sibling read `env.py` directly and nothing checked that the rule did."""
    return (*_modules(), *ALSO_SCANNED)


def _imported_by(module: str) -> set[str]:
    """Which of `brain.app` and `fastapi` a fresh interpreter holds after importing `module`.

    A fresh interpreter, because this one has imported the application a hundred times over by
    the time any test runs and `sys.modules` here can only ever say yes.
    """
    probe = (
        f"import sys, importlib; importlib.import_module({module!r}); "
        "print(','.join(m for m in ('brain.app', 'fastapi') if m in sys.modules))"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        cwd=REPO,
    )
    return {one for one in done.stdout.strip().split(",") if one}


# ----------------------------------------------------------------- nothing else reads it
def test_no_module_under_src_reads_the_environment_except_the_settings_module() -> None:
    """The rule itself, over the real tree.

    Delete this and the next module that needs a value reads `os.environ` for it, with its own
    idea of the variable's name and its own default, which is how the worker and the application
    came to disagree about which database they were in."""
    found = [
        f"{path.relative_to(REPO).as_posix()}:{line}: {expression}"
        for path in _scanned()
        if path != THE_READER
        for line, expression in environment_reads(ast.parse(path.read_text(encoding="utf-8")))
    ]

    assert found == [], "read a field of brain.settings.Settings instead:\n" + "\n".join(found)


def test_the_settings_module_is_found_reading_the_environment_so_the_exemption_is_doing_work() -> (
    None
):
    """The positive case over the real tree. If the scan found nothing in the one module that
    does read the environment, the test above would be green because the scan was blind rather
    than because the tree was clean.

    Delete this and a scan that parses nothing, or walks the wrong directory, passes."""
    reads = list(environment_reads(ast.parse(THE_READER.read_text(encoding="utf-8"))))

    assert reads
    assert len(_modules()) > 300


def test_the_alembic_environment_is_scanned_and_asks_the_migrate_module_for_its_address() -> None:
    """The positive case for the file outside `src/brain`: it is in the scan, it parses, and it
    resolves its address by calling `brain.migrate.alembic_url`, which is the read the rule
    above leaves it.

    Delete this and `ALSO_SCANNED` can be emptied, after which `env.py` goes back to reading
    `DATABASE_URL` for itself with the invariant still green."""
    (env,) = ALSO_SCANNED
    tree = ast.parse(env.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "alembic_url"
    ]

    assert env.is_file()
    assert env in _scanned()
    assert calls
    assert list(environment_reads(tree)) == []


@pytest.mark.parametrize(
    "source",
    [
        "import os\nos.environ['X']",
        "import os\nos.environ.get('X')",
        "import os\nos.getenv('X')",
        "import os\n{**os.environ}",
        "import os\nos.putenv('X', 'y')",
        "from os import environ",
        "from os import getenv as lookup",
        "import os as system\nsystem.environ",
        "import os.path\nos.environ",
        "import posix\nposix.environ",
    ],
)
def test_every_way_python_reads_the_environment_is_recognised(source: str) -> None:
    """Each spelling that reaches the process environment, found.

    Delete this and the scan can be narrowed to `os.environ` alone, after which `from os import
    getenv` is a direct read the invariant cannot see."""
    assert list(environment_reads(ast.parse(source)))


@pytest.mark.parametrize(
    "source",
    [
        "def f(env):\n    return env.get('X')",
        "def f(environ):\n    return environ['X']",
        "import os\nos.name",
        "import os\nos.path.join('a', 'b')",
        "from brain.settings import process_environment\nprocess_environment().get('X')",
        "import os\n'''os.environ is not read here'''",
    ],
)
def test_a_handed_mapping_and_the_rest_of_os_are_not_reads(source: str) -> None:
    """The sibling: what the rule must not refuse. A mapping handed in as a parameter is how
    every command in this repository is made testable, and `os.name` is how a platform branch
    is written so mypy checks both halves.

    Delete this and the scan can be widened to anything named `env`, which refuses the correct
    pattern, and a check that fires on the right usage is the one people switch off."""
    assert not list(environment_reads(ast.parse(source)))


# ------------------------------------------------------- reading it builds nothing
def test_importing_the_settings_module_does_not_import_the_application() -> None:
    """`brain.settings` can be imported by a worker, a script or a sweep without building every
    router. See `brain.settings.SETTINGS_ARE_READ_WITHOUT_BUILDING_THE_APPLICATION`.

    Delete this and one import added to a module the settings depend on makes reading a setting
    expensive again, and the next process to want one reads the environment instead."""
    assert _imported_by("brain.settings") == set()


def test_the_import_probe_sees_the_application_when_it_is_imported() -> None:
    """The positive case for the probe. Importing `brain.app` must be reported as importing it,
    or the test above proves only that the probe prints nothing.

    Delete this and a probe that always prints an empty line passes the test above for ever."""
    assert _imported_by("brain.app") == {"brain.app", "fastapi"}


def test_no_module_under_src_imports_the_application_except_to_serve_it() -> None:
    """Nothing under `src/brain` imports `brain.app`. `brain.serve` hands uvicorn the string
    `"brain.app:app"`, which is how the application is served without being imported here.

    Delete this and a module can import `Settings` from `brain.app` again through the
    re-export, which works, and costs every process that imports that module the application."""
    found = [
        f"{path.relative_to(REPO).as_posix()}:{line}"
        for path in _modules()
        for line in imports_of_the_application(ast.parse(path.read_text(encoding="utf-8")))
    ]

    assert found == []


@pytest.mark.parametrize(
    "source",
    ["import brain.app", "from brain.app import Settings", "from brain import app"],
)
def test_every_spelling_of_importing_the_application_is_recognised(source: str) -> None:
    """The positive case for the scan above. Delete this and a scan matching only `from brain.app
    import` is green while `from brain import app` walks straight past it."""
    assert list(imports_of_the_application(ast.parse(source)))
