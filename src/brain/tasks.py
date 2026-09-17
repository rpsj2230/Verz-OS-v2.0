"""The task runner: every developer command, runnable wherever the interpreter runs.

`python -m brain.tasks <task>`, and `make <task>` calls exactly that.

**Why the commands live here and not in the Makefile.** The Makefile was the task runner and
nothing ran it: `make` is not installed on the development machine this repository is built on,
no workflow called a target, and so the commands it held were a description of how somebody
might work rather than how anybody did. The tracker audit of 2026-09-17 reopened M0.1.5 and
M0.4.5 on exactly that. The interpreter is the one program every place this is developed or
tested already has, so the commands are data in this module, the Makefile is a list of
one-line aliases for people who have `make`, and CI's install job runs `reset` from here.

**Each step runs the tool as a module of this interpreter**, `sys.executable -m ruff`, for the
reason the Makefile gave for `uv run python -m`: Windows Application Control intermittently
refuses the console shims uv writes, and importing the tool into the interpreter it already
trusts starts nothing new.

**`reset` refuses any install that is not a development one**, before it drops anything. It
is `alembic downgrade base`, `upgrade head` and the seed, which is every table and every row,
and the only thing between a developer's shell and an install's database is which
`DATABASE_URL` that shell happens to hold. See `A_RESET_IS_FOR_A_DEVELOPMENT_DATABASE_ONLY`.

Rejected: a second copy of the commands in the Makefile held equal by a test. Two copies of one
command are equal only while something compares them, and a Makefile recipe that drifted
would still be the one a person with `make` runs.

Task ids: M0.1.5, M0.4.5
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

#: The one environment `reset` will run in, by `brain.settings.Settings.env`.
RESETTABLE_ENV: Final = "development"

#: Why the guard is on the environment and not on the database's host or name.
A_RESET_IS_FOR_A_DEVELOPMENT_DATABASE_ONLY: Final = (
    "reset drops every table and reloads the demo company. An install's DATABASE_URL reaches a "
    "developer's shell by a copied environment file or an ssh tunnel, and its host and database "
    "name are exactly the values that get copied into a staging configuration and then lie. "
    "BRAIN_ENV is what an install declares itself to be, and every compose file sets it to "
    "production unless told otherwise. So reset runs only where BRAIN_ENV is set, and set to "
    "development, and refuses before the first statement everywhere else: the settings default "
    "is development too, and a shell that never said so is not a shell that knows."
)


@dataclass(frozen=True)
class Task:
    """One named command: its steps, in order, each a module and its arguments."""

    help: str
    steps: tuple[tuple[str, ...], ...] = ()
    #: Other tasks run first, in order, for a task that is a sequence of tasks.
    runs: tuple[str, ...] = ()
    #: Asked before any step; a returned sentence refuses the task.
    guard: Callable[[], str | None] | None = field(default=None, compare=False)


def reset_refusal(env: str | None) -> str | None:
    """Why `reset` must not run in an install declaring `env`, or None when it may.

    `None` is an environment that declares nothing, which is refused rather than read as the
    settings' default.
    """
    if env == RESETTABLE_ENV:
        return None
    if env is None:
        return (
            f"refused: BRAIN_ENV is not set, and reset runs only where it is set to "
            f"{RESETTABLE_ENV}. {A_RESET_IS_FOR_A_DEVELOPMENT_DATABASE_ONLY}"
        )
    return (
        f"refused: this install declares BRAIN_ENV={env}, and reset runs only where it is "
        f"{RESETTABLE_ENV}. {A_RESET_IS_FOR_A_DEVELOPMENT_DATABASE_ONLY}"
    )


def _reset_guard() -> str | None:
    # Imported here so `--help` and every other task do not pay for the settings closure.
    from brain.settings import Settings

    settings = Settings()
    return reset_refusal(settings.env if "env" in settings.model_fields_set else None)


TASKS: Final[Mapping[str, Task]] = MappingProxyType(
    {
        "dev": Task(
            "Run the app locally with reload",
            steps=(("uvicorn", "brain.app:app", "--reload", "--port", "8000"),),
        ),
        "test": Task("Every test, with the coverage floor", steps=(("pytest", "--cov"),)),
        # No `-q`: pytest's addopts already carries one, and a second suppresses the count.
        "invariants": Task(
            "Only the rules that must never break", steps=(("pytest", "tests/invariants"),)
        ),
        # `src tests`, which is what CI and the pre-push hook lint. The Makefile's recipe also
        # named `migrations`, which has eight findings at origin/main that no gate reads, so
        # `make lint` was red for as long as it existed and nobody had run it to see.
        "lint": Task("Ruff", steps=(("ruff", "check", "src", "tests"),)),
        # `--platform linux`: see CLAUDE.md on mypy narrowing `sys.platform` to the machine.
        "types": Task(
            "Mypy, strict, against the platform this ships on",
            steps=(("mypy", "--platform", "linux"),),
        ),
        "types-here": Task("Mypy, strict, against this machine's own platform", steps=(("mypy",),)),
        "fmt": Task(
            "Format in place",
            steps=(
                ("ruff", "format", "src", "tests"),
                ("ruff", "check", "src", "tests", "--fix"),
            ),
        ),
        "check": Task(
            "Everything the pre-push hook runs", runs=("fmt", "lint", "types", "invariants")
        ),
        "migrate": Task(
            "Apply migrations to DATABASE_URL", steps=(("alembic", "upgrade", "head"),)
        ),
        "seed": Task("Load the synthetic company into the database", steps=(("brain.seed",),)),
        "reset": Task(
            "Drop everything and rebuild. Destroys local data; refuses any non-development install",
            steps=(
                ("alembic", "downgrade", "base"),
                ("alembic", "upgrade", "head"),
                ("brain.seed",),
            ),
            guard=_reset_guard,
        ),
    }
)

#: What M0.1.5 names, which the runner may never lose.
REQUIRED_TASKS: Final = ("dev", "test", "migrate", "seed", "lint", "invariants")

Runner = Callable[[Sequence[str]], int]


def _subprocess(argv: Sequence[str]) -> int:
    # Every argv is built from `TASKS`, a constant in this module, and never from input.
    return subprocess.run(list(argv), check=False).returncode  # noqa: S603


def run(name: str, *, runner: Runner = _subprocess, python: str = sys.executable) -> int:
    """Run one task, stopping at the first step that fails and returning its exit code.

    `runner` and `python` are parameters so a test can watch the argv each step would start
    without starting anything.
    """
    task = TASKS.get(name)
    if task is None:
        print(f"no task {name!r}; the tasks are {', '.join(TASKS)}", file=sys.stderr)
        return 2
    if task.guard is not None:
        refusal = task.guard()
        if refusal is not None:
            print(refusal, file=sys.stderr)
            return 3
    for other in task.runs:
        code = run(other, runner=runner, python=python)
        if code:
            return code
    for step in task.steps:
        code = runner((python, "-m", *step))
        if code:
            return code
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        width = max(len(name) for name in TASKS)
        for name, task in TASKS.items():
            print(f"  {name:<{width}}  {task.help}")
        return 0
    return run(args[0])


if __name__ == "__main__":
    raise SystemExit(main())
