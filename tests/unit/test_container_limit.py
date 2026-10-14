"""The worker plans its slots against the memory it was given, and spends only a share of it.

On 2026-10-13 the owner's install showed two faults in one line of a log. The worker was killed
about every half hour (thirty times in a day) with one process at about 339 MB of anonymous memory,
and the line it printed at start said `336 MiB of a 384 MiB limit`: the plan spent 87.5% of the
container on itself, and the limit it named was the product's own constant, not the container's,
which had been raised by hand to 768 MiB and went on being reported as 384.

Every limit and every file below is a fixture of a machine that does not exist, so no test depends
on the machine it runs on: the cgroup reader is a parameter, and the worker's own reader is
replaced where the whole of `main` is run.

Task ids: M32.4.1.4
"""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.ops.container_limit import (
    CGROUP_LIMIT_FILES,
    MIB,
    SLOT_SHARE_OF_LIMIT,
    UNLIMITED_BYTES,
    cgroup_limit_mib,
    given_limit_mib,
    limit_findings,
    planned_share_mib,
)
from brain.ops.queue import CONCURRENCY, MIB_PER_SLOT
from brain.ops.wiring import component
from brain.ops.worker import EXIT_MISCONFIGURED, WorkerPlan, main, plan_for

V2, V1 = CGROUP_LIMIT_FILES
SLOTS = sum(CONCURRENCY.values())


def reading(files: dict[str, str]) -> object:
    """A reader that answers from `files` and raises what a missing file raises."""

    def read(path: str) -> str:
        if path not in files:
            raise FileNotFoundError(path)
        return files[path]

    return read


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({V2: f"{768 * MIB}\n"}, 768),
        ({V1: f"{384 * MIB}\n"}, 384),
        ({V2: f"{768 * MIB}\n", V1: f"{384 * MIB}\n"}, 768),
        ({V2: "max\n"}, None),
        ({V2: "max\n", V1: f"{384 * MIB}\n"}, None),
        ({V1: "9223372036854771712\n"}, None),
        ({V2: str(UNLIMITED_BYTES)}, None),
        ({}, None),
        ({V2: "not a number\n", V1: f"{512 * MIB}\n"}, 512),
        ({V2: "0\n", V1: f"{512 * MIB}\n"}, 512),
        ({V2: "-1\n"}, None),
        ({V2: "100\n"}, 1),
    ],
    ids=[
        "v2",
        "v1 only",
        "v2 wins over v1",
        "v2 unlimited",
        "v2 unlimited is not overridden by v1",
        "v1 unlimited number",
        "unlimited threshold",
        "no files at all",
        "garbage in v2 falls to v1",
        "zero in v2 falls to v1",
        "negative",
        "under a mebibyte is one",
    ],
)
def test_the_limit_is_read_from_the_kernel_and_an_unstated_one_is_none(
    files: dict[str, str], expected: int | None
) -> None:
    """Both cgroup layouts, in order, with every way the answer is not a limit: missing, `max`, the
    kernel's number for unlimited, garbage, zero, negative. A reader that returned the machine's
    memory for `max` would plan slots into memory the container cannot count on.

    Delete this and the worker plans against a limit it invented, or against none."""
    assert cgroup_limit_mib(reading(files)) == expected  # type: ignore[arg-type]


def test_an_unreadable_file_is_skipped_like_a_missing_one() -> None:
    """A permission error is `OSError` like a missing file, and a worker that raised on it would
    not start on a host that hides its cgroup from the container. Delete this and the check that
    reads the limit becomes the reason the worker does not run."""

    def read(path: str) -> str:
        raise PermissionError(path)

    assert cgroup_limit_mib(read) is None


def test_the_real_cgroup_files_are_the_two_the_kernel_names() -> None:
    """The paths are a fact about Linux and are written here, not imported, so changing the constant
    cannot change what it is compared with. Delete this and a typo in a path reads as `no limit` on
    every host, and the worker goes on planning against the constant with every other test green."""
    assert CGROUP_LIMIT_FILES == (
        "/sys/fs/cgroup/memory.max",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    )


def test_the_container_limit_wins_over_the_budget_and_the_budget_stands_when_there_is_none() -> (
    None
):
    """The unset case and the set one. Delete this and a limit raised by hand goes on being
    reported as the product's number, or an unlimited container is planned as if it had room."""
    assert given_limit_mib(768, 384) == 384
    assert given_limit_mib(384, 768) == 768
    assert given_limit_mib(768, None) == 768


def test_a_plan_may_spend_three_quarters_of_the_limit_rounded_down() -> None:
    """The arithmetic, with the share written as a number here so that changing the constant is a
    failure. Delete this and the share can drift back up to the whole limit, which is the plan that
    left the process 48 MiB to live in."""
    assert SLOT_SHARE_OF_LIMIT == 0.75
    assert planned_share_mib(768) == 576
    assert planned_share_mib(384) == 288
    assert planned_share_mib(1) == 0
    assert planned_share_mib(7) == 5


def test_a_plan_over_the_share_is_an_advisory_and_one_over_the_limit_is_a_refusal() -> None:
    """The split, at its boundaries: exactly the share is fine, one slot over the share advises and
    still starts, and one MiB over the limit refuses. The case that matters is the one the install
    was in, seven slots of 48 inside 384: it must start, and must say why it is short.

    Delete this and either an upgrade turns a stale 384 MiB limit into an outage, or a plan over
    the share goes unsaid."""
    assert limit_findings(SLOTS, MIB_PER_SLOT, 768, where="here") == ((), ())
    assert limit_findings(12, 48, 768, where="here") == ((), ())

    refusals, advice = limit_findings(SLOTS, MIB_PER_SLOT, 384, where="on 'brain-worker'")
    assert refusals == ()
    assert len(advice) == 1
    assert "336 MiB of the 384 MiB limit" in advice[0]
    assert "288 MiB (75%)" in advice[0]
    assert "at least 448 MiB" in advice[0]

    assert limit_findings(13, 48, 768, where="here")[1], "13 slots is 624, over the 576 share"
    refusals, advice = limit_findings(SLOTS, MIB_PER_SLOT, 335, where="here")
    assert len(refusals) == 1 and advice == ()
    assert "over the 335 MiB" in refusals[0]
    assert limit_findings(SLOTS, MIB_PER_SLOT, 336, where="here")[0] == ()


def test_the_product_s_own_budget_for_the_worker_leaves_its_slots_inside_the_share() -> None:
    """The default an install starts from, which is what makes the advisory a statement about a
    server and never about the product: the budget is 768 MiB, the seven slots cost 336, and 336
    is inside 75% of it. Written with the slot figures from the queue and the limit from the
    component, and the number 768 as a fact the owner's measurement set.

    Delete this and the budget can be cut back to a figure at which every fresh install starts
    with the advisory, or with the process squeezed again."""
    budget = component("brain-worker").memory_mib

    assert budget == 768
    assert SLOTS * MIB_PER_SLOT == 336
    assert planned_share_mib(budget) >= SLOTS * MIB_PER_SLOT
    assert limit_findings(SLOTS, MIB_PER_SLOT, budget, where="here") == ((), ())


def test_the_plan_names_the_limit_it_was_made_against_and_what_it_may_spend() -> None:
    """The line an operator reads at start. Given a container limit it prints that one, not the
    budget, and says what the plan may spend. Delete this and the log goes on reporting a figure
    the container does not have, which is how a hand-raised limit looked unraised."""
    plan = plan_for(CONCURRENCY, limit_mib=768)
    default = plan_for(CONCURRENCY)

    assert isinstance(plan, WorkerPlan)
    assert plan.memory_mib == 768
    assert "336 MiB of a 768 MiB limit (a plan may spend 576)" in plan.describe()
    assert default.memory_mib == component("brain-worker").memory_mib
    assert (
        "of a 384 MiB limit (a plan may spend 288)"
        in plan_for(CONCURRENCY, limit_mib=384).describe()
    )


def _env() -> dict[str, str]:
    from tests.unit.test_worker import _sound_environment

    return _sound_environment()


def test_a_worker_on_a_stale_limit_starts_and_says_what_to_raise(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The install's own case through `main`: the kernel says 384, the seven slots cost 336, the
    worker passes its check, and the advisory and the real limit are in its log. Delete this and
    the margin is computed by a function nothing calls, which is where the first version of every
    advisory in the worker lived.

    The same environment on a container with 768 prints no advisory, the positive half."""
    monkeypatch.setattr("brain.ops.worker.cgroup_limit_mib", lambda: 384)
    assert main(["--check"], env=_env()) == 0
    seen = capsys.readouterr()
    assert "over the 288 MiB (75%) a plan may spend" in seen.err
    assert "336 MiB of a 384 MiB limit" in seen.out

    monkeypatch.setattr("brain.ops.worker.cgroup_limit_mib", lambda: 768)
    assert main(["--check"], env=_env()) == 0
    seen = capsys.readouterr()
    assert "a plan may spend" not in seen.err
    assert "336 MiB of a 768 MiB limit" in seen.out


def test_a_worker_with_no_cgroup_limit_plans_against_the_product_s_budget(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The unset case through `main`: a laptop, or a container with no limit, reads None and the
    plan names the budget. Delete this and an unlimited container is planned against nothing."""
    monkeypatch.setattr("brain.ops.worker.cgroup_limit_mib", lambda: None)

    assert main(["--check"], env=_env()) == 0

    assert "336 MiB of a 768 MiB limit" in capsys.readouterr().out


def test_a_worker_whose_container_is_smaller_than_its_slots_will_not_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Over the limit, not over the share, is a refusal with the worker's own exit code: the kernel
    would kill it the first time the slots were busy. Delete this and a container with a 256 MiB
    limit starts, is killed by the first burst, and looks like a database problem."""
    monkeypatch.setattr("brain.ops.worker.cgroup_limit_mib", lambda: 256)

    assert main(["--check"], env=_env()) == EXIT_MISCONFIGURED

    assert "over the 256 MiB limit" in capsys.readouterr().err


def test_this_module_reads_no_file_unless_asked_and_the_worker_asks_once_at_start() -> None:
    """The reader is a parameter, so the arithmetic above runs identically on a laptop and in CI.
    The only caller is `brain.ops.worker.main`, after the preflight, which is what keeps the
    refusals in `preflight` machine-independent. Delete this and a second caller can slip into
    `preflight`, and the same environment passes on one host and fails on another."""
    import ast

    worker = Path(__file__).resolve().parents[2] / "src" / "brain" / "ops" / "worker.py"
    tree = ast.parse(worker.read_text(encoding="utf-8"))
    callers = [
        function.name
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef)
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "cgroup_limit_mib"
    ]

    assert callers == ["main"]
