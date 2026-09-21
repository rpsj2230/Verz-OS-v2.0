"""After a staging deploy: canaries, RLS, schema and database invariants, and a verdict CI reads.

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

**What of the invariant suite runs here, measured on the image rather than hoped (M38.2.1.2).**
`tests/` is in `.dockerignore` and the image is built `--no-dev`, so neither `tests/invariants`
nor pytest is in it, and the owner decided nothing on the internet may reach the database to
run them from GitHub. Almost all of that suite reads source, which is the same commit CI
already judged before `:latest` moved, so running it again here would re-prove the checkout and
say nothing about staging. What only staging can answer is its database, so the verdict carries
`schema` (`brain.ops.schema_check`, every schema the code expects exists) and `invariants`, the
database invariants the image can run: `DATABASE_INVARIANTS`. Rejected: shipping the tests and
pytest in the production image, which enlarges what every client runs to re-run a source check.

**A container that never ran the checks says so.** The file lives in the container, so a new
container starts with no verdict, and the page reports `not run` for the commit it is serving
rather than the last container's pass. See `A_VERDICT_BELONGS_TO_THE_CONTAINER_THAT_EARNED_IT`.

Task ids: M38.5.1, M38.2.1.2
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

from brain.ops.safe_error import describe

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


#: The verdict's checks, in the order they run and the order the page lists them.
CHECKS: Final = ("rls", "canaries", "schema", "invariants")

#: The database invariants that run inside the production image, and what each holds.
DATABASE_INVARIANTS: Final = (
    ("migrations at head", "the database has applied every migration this image carries"),
    ("grant isolation", "no foreign key runs from a grant table to a connector table"),
)


@dataclass(frozen=True)
class Verdict:
    commit: str
    rls: str
    canaries: str
    schema: str
    invariants: str
    checked_at: str

    @property
    def passed(self) -> bool:
        return all(getattr(self, name) == PASSED for name in CHECKS)


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
        for line in findings or (describe(exc),):
            print(f"! post_deploy {name} {line}", file=sys.stderr)
        return FAILED
    return PASSED


def run_checks(
    commit: str,
    *,
    rls: Callable[[], object],
    canaries: Callable[[], object],
    schema: Callable[[], object],
    invariants: Callable[[], object],
    now: datetime,
) -> Verdict:
    """Every check, each run whatever the others found, so one red run reports every half."""
    return Verdict(
        commit=commit,
        rls=_outcome(rls, "rls"),
        canaries=_outcome(canaries, "canaries"),
        schema=_outcome(schema, "schema"),
        invariants=_outcome(invariants, "invariants"),
        checked_at=now.isoformat(timespec="seconds"),
    )


def _public(value: object) -> str:
    """Only the three constants reach the page. A check an older image never ran is `not run`."""
    if value in (None, NOT_RUN):
        return NOT_RUN
    return PASSED if value == PASSED else FAILED


def served(serving: str, recorded: Mapping[str, Any] | None) -> dict[str, str]:
    """The public document: this container's verdict for the commit it serves, or `not run`."""
    if recorded is None or str(recorded.get("commit", "")) != serving:
        return {"commit": serving, **dict.fromkeys(CHECKS, NOT_RUN), "checked_at": ""}
    return {
        "commit": serving,
        **{name: _public(recorded.get(name)) for name in CHECKS},
        "checked_at": str(recorded.get("checked_at", "")),
    }


def database_invariants(checks: Mapping[str, Callable[[], object]]) -> None:
    """Run every named invariant; raise once, naming each that failed, after all have run.

    The names and findings travel in the exception to `_outcome`, which prints them to the log.
    """
    from brain.ops.sweeps import SweepFailure

    failed: list[str] = []
    for name, check in checks.items():
        if _outcome(check, f"invariants {name}") != PASSED:
            failed.append(f"{name} failed")
    if failed:
        raise SweepFailure(failed)


def migrations_at_head(url: str) -> None:
    """The database has applied every revision this image carries in `/app/migrations`."""
    from brain.db import normalise_database_url
    from brain.migrate import pending_revisions
    from brain.ops.sweeps import SweepFailure

    pending = pending_revisions(normalise_database_url(url))
    if pending:
        raise SweepFailure([f"{len(pending)} migration(s) not applied: {', '.join(pending)}"])


def invariant_checks(settings: Any) -> dict[str, Callable[[], object]]:
    """`DATABASE_INVARIANTS`, bound to this container's database. Migrations ask the login the
    application migrates as, since that is the one `brain.app` ran them through."""
    from brain.ops.sweeps import sweep_grant_isolation

    return {
        "migrations at head": lambda: migrations_at_head(settings.owner_database_url()),
        "grant isolation": sweep_grant_isolation,
    }


def schema_present(url: str) -> None:
    from brain.ops.schema_check import check

    if check(url) != 0:
        raise RuntimeError("schema check reported missing schemas")


def read_recorded(path: Path = RESULT) -> Mapping[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def main() -> int:
    """Run every check against this container's database and record the verdict."""
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
        schema=lambda: schema_present(settings.database_url),
        invariants=lambda: database_invariants(invariant_checks(settings)),
        now=now,
    )
    RESULT.write_text(json.dumps(asdict(verdict)) + "\n", encoding="utf-8", newline="\n")
    summary = ", ".join(f"{name} {getattr(verdict, name)}" for name in CHECKS)
    print(f"post_deploy {verdict.commit}: {summary}")
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
