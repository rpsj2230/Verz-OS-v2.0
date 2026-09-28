"""The worker's healthcheck answers without importing the worker.

Every probe of `python -m brain.ops.worker --ready` timed out on a production host from 21 to
28 September 2026: 4.4 seconds of imports in front of a five-second budget, so Docker marked a
working worker unhealthy, the deploy script stopped before the post-deploy checks, and the
Deploy workflow was red for every commit while the site served each one. See
`brain.ops.heartbeat`.

**Measured by what a fresh interpreter imports, not by a clock.** A timing assertion here would
pass on a fast laptop and say nothing about a shared server eight times slower, which is where
the failure was. What the probe imports is the same everywhere, and it is the thing that grew.

Task ids: M38.5.1
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from brain.ops import heartbeat, queue

REPO = Path(__file__).resolve().parents[2]

#: The heartbeat variable, named here as the compose files spell it rather than imported, so a
#: rename in the module shows up as the subprocess reading a different file.
HEARTBEAT_VARIABLE = "BRAIN_WORKER_HEARTBEAT"


def _imports(*arguments: str, env: dict[str, str] | None = None) -> tuple[int, str, set[str]]:
    """Run a fresh interpreter under `-X importtime` and return its exit code, its stdout and
    the name of every module it imported. A fresh interpreter because this one has imported the
    worker long before any test runs, so `sys.modules` here can only ever say yes."""
    done = subprocess.run(
        [sys.executable, "-X", "importtime", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        cwd=REPO,
        env=env,
    )
    names = {
        line.rsplit("|", 1)[1].strip()
        for line in done.stderr.splitlines()
        if line.startswith("import time:") and line.count("|") == 2
    }
    names.discard("imported package")  # the header line's third column
    return done.returncode, done.stdout, names


def _environment(beat_at: Path) -> dict[str, str]:
    return {**os.environ, HEARTBEAT_VARIABLE: str(beat_at)}


def _worker_only_modules() -> set[str]:
    """What importing the worker loads beyond what the healthcheck is allowed to load, outside
    the standard library. The standard library is left out because `brain.ops.worker` imports
    a few of its modules above the guard, which is where they have to be, and they cost
    microseconds; the 4.4 seconds were the database layer, the queue and the route modules."""
    _, _, worker = _imports("-c", "import brain.ops.worker")
    _, _, allowed = _imports("-c", "import brain.settings, brain.ops.heartbeat")
    return {name for name in worker - allowed if name.split(".")[0] not in sys.stdlib_module_names}


def test_the_healthcheck_command_imports_nothing_the_worker_imports_for_its_own_work(
    tmp_path: Path,
) -> None:
    """The real command, as every install's stored compose file spells it, with a fresh
    heartbeat: it answers ready, and not one module it imported is one the worker needs only for
    its own work. The worker-only set is asserted to contain the database layer first, so an
    empty set (a scan that parsed nothing) cannot pass this.

    Delete this and the guard at the top of `brain.ops.worker` can be moved below an import, or
    lose its condition, with every other test green: the probe still answers correctly, only
    slowly, and slowly is the whole failure."""
    worker_only = _worker_only_modules()
    assert "sqlalchemy" in worker_only
    assert "brain.ops.queue" in worker_only

    beat_at = tmp_path / "heartbeat"
    heartbeat.beat(beat_at)
    code, stdout, probe = _imports("-m", "brain.ops.worker", "--ready", env=_environment(beat_at))

    assert code == 0
    assert stdout.startswith("ready:")
    assert "brain.ops.heartbeat" in probe
    assert sorted(probe & worker_only) == []


def test_the_healthcheck_command_still_refuses_a_worker_with_no_heartbeat(tmp_path: Path) -> None:
    """The sibling: the fast path answers "not ready" when there is nothing to read, with the
    exit code Docker counts as a failed probe.

    Delete this and a fast path that answered 0 unconditionally would pass the test above, and
    a worker that never started would be put in rotation."""
    code, stdout, _ = _imports(
        "-m", "brain.ops.worker", "--ready", env=_environment(tmp_path / "absent")
    )

    assert code == heartbeat.EXIT_NOT_READY
    assert code != 0
    assert stdout == ""


def test_importing_the_heartbeat_module_imports_only_the_standard_library() -> None:
    """`brain.ops.queue` and `brain.ops.worker` import this module, and it must not import
    them back or anything heavy of its own: the healthcheck imports it before anything else.
    Compared against a bare interpreter, so what the environment loads at start-up is not
    counted against it.

    Delete this and a convenient import added to `brain.ops.heartbeat` (the settings model at
    the top instead of inside `main`, say) puts its cost back into every probe."""
    _, _, bare = _imports("-c", "pass")
    _, _, loaded = _imports("-c", "import brain.ops.heartbeat")
    added = loaded - bare

    assert "brain.ops.heartbeat" in added
    outside = sorted(
        name
        for name in added
        if name.split(".")[0] not in sys.stdlib_module_names
        and name not in {"brain", "brain.ops", "brain.ops.heartbeat"}
    )
    assert outside == []


def test_the_queue_and_the_healthcheck_judge_staleness_by_one_figure() -> None:
    """The re-drive sweep and the readiness check must agree on when a worker has gone, or a
    container reports ready while its jobs are being re-driven. They are the same object, not
    two equal values: equal values drift apart the first time somebody tunes one of them.

    Delete this and `brain.ops.queue` can grow its own `stale_after` again."""
    assert queue.stale_after is heartbeat.stale_after
    assert queue.HEARTBEAT_SECONDS == heartbeat.HEARTBEAT_SECONDS
    assert queue.STALE_AFTER_HEARTBEATS == heartbeat.STALE_AFTER_HEARTBEATS


@pytest.mark.parametrize(
    "compose",
    ["docker-compose.worker.yml", "docker-compose.parse-worker.yml", "docker-compose.full.yml"],
)
def test_every_worker_healthcheck_is_the_exact_command_the_fast_path_answers(compose: str) -> None:
    """The guard in `brain.ops.worker` answers only `sys.argv[1:] == ["--ready"]`. A compose file
    adding a second argument would fall through to the full import and time out again, with no
    test about the guard noticing. Parsed YAML, every service whose healthcheck runs the worker,
    and at least one such service per file so a file that stopped declaring one fails here.

    Delete this and the command and the guard can drift apart in either direction."""
    raw = yaml.safe_load((REPO / compose).read_text(encoding="utf-8"))
    commands = [
        list(service["healthcheck"]["test"])
        for service in raw["services"].values()
        if isinstance(service, dict)
        and isinstance(service.get("healthcheck"), dict)
        and "brain.ops.worker" in service["healthcheck"].get("test", [])
    ]

    assert commands
    for command in commands:
        assert command == ["CMD", "python", "-m", "brain.ops.worker", "--ready"]
