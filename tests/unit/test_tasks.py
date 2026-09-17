"""The task runner, and the reset that refuses an install.

Task ids: M0.1.5, M0.4.5
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from brain import tasks

PYTHON = "/venv/bin/python"


def _recording() -> tuple[list[tuple[str, ...]], tasks.Runner]:
    started: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str]) -> int:
        started.append(tuple(argv))
        return 0

    return started, runner


@pytest.mark.parametrize("name", tasks.REQUIRED_TASKS)
def test_every_task_the_sentence_names_starts_a_module_of_this_interpreter(name: str) -> None:
    """M0.1.5 names six commands. Each has to exist and start something, and start it as
    `python -m`, because a console shim is what Windows Application Control refuses.

    Delete this and a task can be emptied to no steps, which exits 0 and does nothing."""
    started, runner = _recording()

    assert tasks.run(name, runner=runner, python=PYTHON) == 0
    assert started, f"{name} started nothing"
    assert all(argv[:2] == (PYTHON, "-m") for argv in started), started


def test_the_commands_are_the_ones_ci_and_the_hooks_run() -> None:
    """The positive case, whole: what each named task starts. Asserted literally, because these
    are the commands CI and the hooks run by the same spelling, and a changed one is a runner
    that no longer does what CI does.

    Delete this and `test` can lose `--cov`, or `invariants` gain the `-q` that silences the
    count, with every other test green."""
    expected = {
        "dev": [("uvicorn", "brain.app:app", "--reload", "--port", "8000")],
        "test": [("pytest", "--cov")],
        "migrate": [("alembic", "upgrade", "head")],
        "seed": [("brain.seed",)],
        "lint": [("ruff", "check", "src", "tests")],
        "invariants": [("pytest", "tests/invariants")],
    }
    for name, steps in expected.items():
        started, runner = _recording()
        tasks.run(name, runner=runner, python=PYTHON)
        assert [argv[2:] for argv in started] == steps, name


def test_a_failing_step_stops_the_task_and_its_code_is_returned() -> None:
    """`check` is four tasks in a row, and `reset` is a downgrade followed by an upgrade. A
    downgrade that fails half way and is followed by the upgrade anyway rebuilds on top of
    whatever it left, which is the one state a reset exists to get out of.

    Delete this and a runner that ignores exit codes passes every other test here."""
    started: list[tuple[str, ...]] = []

    def failing(argv: Sequence[str]) -> int:
        started.append(tuple(argv))
        return 7 if "ruff" in argv else 0

    assert tasks.run("check", runner=failing, python=PYTHON) == 7
    assert [argv[2:4] for argv in started] == [("ruff", "format")]


def test_check_runs_format_lint_types_and_invariants_in_that_order() -> None:
    """What the pre-push hook runs, in the order that makes `fmt` before `lint` meaningful."""
    started, runner = _recording()

    assert tasks.run("check", runner=runner, python=PYTHON) == 0
    assert [argv[2:4] for argv in started] == [
        ("ruff", "format"),
        ("ruff", "check"),
        ("ruff", "check"),
        ("mypy", "--platform"),
        ("pytest", "tests/invariants"),
    ]


def test_reset_drops_then_rebuilds_then_reseeds_in_that_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`reset` is the remedy `brain.seed` names when it refuses a database the demo was loaded
    into and removed from, so a reset that stops short is a refusal with no way out. Seeding
    before the downgrade writes rows that are then dropped; upgrading before it is a no-op that
    leaves the old schema standing.

    Delete this and the steps can be reordered or lose one, and still be a task."""
    monkeypatch.setenv("BRAIN_ENV", "development")
    started, runner = _recording()
    assert tasks.run("reset", runner=runner, python=PYTHON) == 0

    assert [argv[2:] for argv in started] == [
        ("alembic", "downgrade", "base"),
        ("alembic", "upgrade", "head"),
        ("brain.seed",),
    ]


@pytest.mark.parametrize("env", ["production", "staging", None])
def test_reset_refuses_an_install_that_is_not_a_development_one(
    env: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal, before anything starts, including for a shell that never set BRAIN_ENV: a
    reset that dropped the schema and then refused the seed would have done all the damage.

    Delete this and `make reset` in a shell holding an install's DATABASE_URL drops that
    install's every table."""
    refusal = tasks.reset_refusal(env)
    assert refusal is not None
    assert (f"BRAIN_ENV={env}" if env else "BRAIN_ENV is not set") in refusal

    started, runner = _recording()
    guarded = tasks.Task("reset", steps=(("alembic", "downgrade", "base"),), guard=lambda: refusal)
    monkeypatch.setattr(tasks, "TASKS", {"reset": guarded})

    assert tasks.run("reset", runner=runner, python=PYTHON) == 3
    assert started == []


def test_reset_is_permitted_in_development_and_its_guard_reads_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive half. A guard tested only by its refusals is satisfied by one refusing
    everything, which would make the reset CI runs fail rather than prove anything.

    And the real guard is asserted to be the one on the task, reading `BRAIN_ENV` through the
    settings, so a task whose guard was dropped is caught here and not only in CI."""
    assert tasks.reset_refusal(tasks.RESETTABLE_ENV) is None

    monkeypatch.setenv("BRAIN_ENV", "production")
    started, runner = _recording()
    assert tasks.run("reset", runner=runner, python=PYTHON) == 3
    monkeypatch.delenv("BRAIN_ENV")
    assert tasks.run("reset", runner=runner, python=PYTHON) == 3
    assert started == []

    monkeypatch.setenv("BRAIN_ENV", "development")
    assert tasks.run("reset", runner=runner, python=PYTHON) == 0
    assert len(started) == 3


def test_an_unknown_task_is_refused_rather_than_run() -> None:
    """A typo must not exit 0, or a CI step calling a renamed task goes green doing nothing."""
    started, runner = _recording()
    assert tasks.run("tset", runner=runner, python=PYTHON) == 2
    assert started == []
