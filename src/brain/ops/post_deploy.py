"""After a staging deploy, the permission canaries and the RLS sweep, and a verdict CI can read.

Both checks already existed and neither ran at the moment M38.5.1 names. The row-level security
sweep ran in CI against a database CI had just built, and the canaries ran on the worker's
schedule twice a day. A deploy that shipped a table with row-level security off, or a resolver that
widened a reach, reached staging, looked healthy, and could be tagged as a release in the hours
before either noticed.

**The server runs the checks, and GitHub reads the verdict.** Nothing on the internet may reach
this server's database or its deployment panel (see `ops/deploy/brain-deploy`), so a workflow
cannot run them. `ops/deploy/brain-autodeploy` runs `python -m brain.ops.post_deploy` inside the
application container it has just deployed, which writes `RESULT` in that container, and the
application serves it at `/api/deploy-checks.json`. The Deploy workflow waits for that document to
name the commit it published, and the Release workflow refuses to tag a commit whose Deploy run did
not see both checks pass. Rejected: an SSH key in GitHub able to run the checks, which is the
deployment credential `brain-deploy` argues out of existence.

**The document says passed or failed and nothing else.** No finding, no table name, no asker, no
count: what the canaries found goes to this process's stderr, which is the server's log, for the
reason `brain.ops.canary_run.A_RED_RUN_IS_RECORDED_FAILED_AND_ITS_SUBJECTS_REACH_ONLY_THE_ALERT`
gives. A public page naming the table without row-level security would be the leak it reports.

**A container that never ran the checks says so.** The file lives in the container, so a new
container starts with no verdict, and the page reports `not run` for the commit it is serving
rather than the last container's pass. See `A_VERDICT_BELONGS_TO_THE_CONTAINER_THAT_EARNED_IT`.

Task ids: M38.5.1
"""

from __future__ import annotations

import json
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

#: Where the verdict is written, inside the container the checks ran in.
RESULT: Final = Path(tempfile.gettempdir()) / "brain-post-deploy.json"

PASSED: Final = "passed"
FAILED: Final = "failed"
NOT_RUN: Final = "not run"

A_VERDICT_BELONGS_TO_THE_CONTAINER_THAT_EARNED_IT: Final = (
    "The verdict is a file in the container the checks ran in, and the page reports it only when "
    "it names the commit that container is serving. A verdict kept outside the container would "
    "outlive it, and the first thing a failed deploy would show is the previous commit's pass."
)


@dataclass(frozen=True)
class Verdict:
    commit: str
    rls: str
    canaries: str
    checked_at: str

    @property
    def passed(self) -> bool:
        return self.rls == PASSED and self.canaries == PASSED


def _outcome(check: Callable[[], object], name: str) -> str:
    """Run one check; anything it raises is a failure, and its words go to the log only."""
    try:
        check()
    except SystemExit as stopped:
        if stopped.code in (0, None):
            return PASSED
        print(f"! post_deploy {name} exited {stopped.code}", file=sys.stderr)
        return FAILED
    except Exception as exc:
        findings = getattr(exc, "findings", None)
        for line in findings or (f"{type(exc).__name__}: {exc}",):
            print(f"! post_deploy {name} {line}", file=sys.stderr)
        return FAILED
    return PASSED


def run_checks(
    commit: str,
    *,
    rls: Callable[[], object],
    canaries: Callable[[], object],
    now: datetime,
) -> Verdict:
    """Both checks, each run whatever the other found, so one red run reports both halves."""
    return Verdict(
        commit=commit,
        rls=_outcome(rls, "rls"),
        canaries=_outcome(canaries, "canaries"),
        checked_at=now.isoformat(timespec="seconds"),
    )


def served(serving: str, recorded: Mapping[str, Any] | None) -> dict[str, str]:
    """The public document: this container's verdict for the commit it serves, or `not run`."""
    if recorded is None or str(recorded.get("commit", "")) != serving:
        return {"commit": serving, "rls": NOT_RUN, "canaries": NOT_RUN, "checked_at": ""}
    return {
        "commit": serving,
        "rls": PASSED if recorded.get("rls") == PASSED else FAILED,
        "canaries": PASSED if recorded.get("canaries") == PASSED else FAILED,
        "checked_at": str(recorded.get("checked_at", "")),
    }


def read_recorded(path: Path = RESULT) -> Mapping[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def main() -> int:
    """Run both against this container's database and record the verdict. Non-zero on a failure."""
    from brain.ops.canary_run import run_canaries_now
    from brain.ops.sweeps import sweep_rls
    from brain.settings import Settings

    settings = Settings()
    if not settings.database_url:
        print("! post_deploy no database is configured, so nothing was checked", file=sys.stderr)
        return 1
    now = datetime.now(UTC)
    verdict = run_checks(
        settings.resolved_commit(),
        rls=sweep_rls,
        canaries=lambda: run_canaries_now(
            settings.database_url, now=now, tool_source=settings.tool_source
        ),
        now=now,
    )
    RESULT.write_text(json.dumps(asdict(verdict)) + "\n", encoding="utf-8", newline="\n")
    print(f"post_deploy {verdict.commit}: rls {verdict.rls}, canaries {verdict.canaries}")
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
