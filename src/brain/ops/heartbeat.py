"""The worker's heartbeat, and the readiness check that reads it, with nothing else loaded.

**A healthcheck has a budget, and importing the worker spent all of it.** The worker
container's healthcheck is `python -m brain.ops.worker --ready`, run every fifteen seconds
with five seconds to answer. Answering is one `stat` of a file. Getting to the line that does
it meant importing `brain.ops.worker`, which imports the knowledge layer, the schedule
runner, the queue and through them SQLAlchemy and the route modules: measured on a production
host on 2026-09-28 with `python -X importtime`, 4.4 seconds of imports in front of a check that
takes microseconds, and 5.5 seconds for the whole probe on a busy shared host. Every probe
timed out, Docker marked a working worker unhealthy, the deploy script refused to call the
deploy complete, and so it never ran the post-deploy canaries and row-security sweep. The
Deploy workflow went red on every commit for a week while the site served each one correctly.

**So the check lives here, and importing this module imports only the standard library.**
`brain.ops.worker` answers `--ready` from `main` below before it imports anything of its own
(see the guard at the top of that file), and `brain.ops.queue` takes its staleness from here,
so the figure the recovery sweep uses and the figure the healthcheck uses are still one figure.
The one thing `main` adds is `brain.settings`, for the variable naming the file, because
nothing else under `src/brain` may read the environment: 1.2 seconds on the same host, against
the worker's 4.4. `THE_HEALTHCHECK_DOES_NOT_IMPORT_THE_WORKER` is the rule, and a test runs the
real command in a subprocess and fails if it imports the queue, the database layer or anything
the worker imports for its own work.

**The command stays `python -m brain.ops.worker --ready`, and that is deliberate.** Two
cheaper-looking designs were rejected. Pointing the compose files at `python -m
brain.ops.heartbeat` fixes a fresh install and no existing one: an install's compose file is
the copy its orchestrator stored when it was set up, so the old command keeps running there
until somebody edits it by hand on every server. Raising the timeout instead keeps a check
whose cost grows with every module the worker learns to import, and would have gone red again
the next time the worker grew.

Task ids: M38.5.1
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

THE_HEALTHCHECK_DOES_NOT_IMPORT_THE_WORKER: Final = (
    "the worker's readiness check reads one file's age and the one setting naming that file, "
    "and imports nothing the worker imports for its own work: it runs every fifteen seconds "
    "with five to answer, and importing the worker took 4.4 of them on a production host"
)

#: How often a running worker writes its heartbeat. Written in the worker's own
#: transaction, because a transaction pooler hands the next statement to a different
#: backend and anything held in a session does not survive that.
HEARTBEAT_SECONDS: Final = 15

#: How many missed heartbeats before a job is treated as orphaned. Four rather than one,
#: and the multiple is the whole point: a worker paused by memory pressure on a shared
#: host, or waiting on a slow connector, misses heartbeats while being perfectly alive.
#: Re-driving a job that is still running produces two of it, which for a job with a side
#: effect is worse than the job never finishing.
STALE_AFTER_HEARTBEATS: Final = 4

#: The file a running worker touches. In the container's own filesystem rather than shared,
#: so it says something about this process rather than about the fleet.
HEARTBEAT_PATH_ENV: Final = "BRAIN_WORKER_HEARTBEAT"

#: The directory the heartbeat lives in, under whatever the platform calls temporary.
HEARTBEAT_DIRECTORY: Final = "brain-worker"

#: The healthcheck's failure. Ordinary and expected while the worker is starting.
EXIT_NOT_READY: Final = 1


def stale_after() -> timedelta:
    """How old a heartbeat may be before the worker behind it is treated as gone.

    `brain.ops.queue` re-exports this rather than keeping its own copy. The queue decides when
    a worker has stopped answering, and a readiness check that disagreed with it would produce
    the two states that are both wrong: a container reporting ready while the recovery sweep
    re-drives its jobs, or a container taken out of rotation while it is still holding work
    nothing will reclaim.
    """
    return timedelta(seconds=HEARTBEAT_SECONDS * STALE_AFTER_HEARTBEATS)


def default_heartbeat_path() -> Path:
    """Where the heartbeat goes when nothing says otherwise.

    The temporary directory, asked for rather than spelled. Two reasons, and the second is
    the one that matters. The image runs as a non-root user with no home and no shell, so
    the temporary directory is the one place in it this process can write. And a heartbeat
    must not survive a restart: the file says "a worker is working right now", and a durable
    copy of that sentence left behind by a process that died is exactly the lie the re-drive
    sweep exists to catch, so it belongs somewhere the container forgets.

    `tempfile.gettempdir()` rather than a literal, so the tests can point it somewhere real
    on a machine whose temporary directory is not spelled the same way.
    """
    return Path(tempfile.gettempdir()) / HEARTBEAT_DIRECTORY / "heartbeat"


def heartbeat_path(env: Mapping[str, str]) -> Path:
    """Where this container's heartbeat goes, as its environment says or by default.

    One function rather than the two lines it replaces, because `--ready` and the run mode have
    to agree about the path: a healthcheck reading one file while the loop touches another is a
    container that is never in rotation and whose logs say it is working.
    """
    declared = (env.get(HEARTBEAT_PATH_ENV) or "").strip()
    return Path(declared) if declared else default_heartbeat_path()


def heartbeat_age_seconds(path: Path, *, now: datetime) -> float | None:
    """How long ago the worker last said it was working, or None if it never has.

    None rather than a large number for a missing file. A worker that has not started is not
    a worker that is behind, and collapsing the two would let a container that never opened
    a connection report the same condition as one that is merely slow.
    """
    try:
        modified = path.stat().st_mtime
    except OSError:
        return None
    return (now - datetime.fromtimestamp(modified, tz=UTC)).total_seconds()


def is_ready(path: Path, *, now: datetime) -> bool:
    """Whether this container should be in rotation: its heartbeat is no older than
    `stale_after()`, the same staleness the re-drive sweep uses."""
    age = heartbeat_age_seconds(path, now=now)
    return age is not None and age <= stale_after().total_seconds()


def beat(path: Path) -> None:
    """Say that this process's loop is still going round.

    The directory is created on every beat rather than once at start-up. It costs a stat and it
    survives the case a start-up-only version does not, which is somebody clearing the
    container's temporary directory underneath a running worker: the heartbeat would stop being
    written, the healthcheck would take the container out of rotation, and the loop would be
    perfectly healthy the whole time.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def ready(env: Mapping[str, str]) -> int:
    """The healthcheck: 0 with a line on stdout when the heartbeat is fresh, `EXIT_NOT_READY`
    with a line on stderr when it is missing or stale."""
    path = heartbeat_path(env)
    if is_ready(path, now=datetime.now(tz=UTC)):
        print(f"ready: heartbeat at {path} is fresh")
        return 0
    print(f"not ready: no fresh heartbeat at {path}", file=sys.stderr)
    return EXIT_NOT_READY


def main() -> int:
    """`python -m brain.ops.heartbeat`, and what `python -m brain.ops.worker --ready` runs.

    `brain.settings` is imported here rather than at the top so that importing this module, as
    `brain.ops.queue` and `brain.ops.worker` do, stays at the standard library.
    """
    from brain.settings import process_environment

    return ready(process_environment())


if __name__ == "__main__":
    raise SystemExit(main())
