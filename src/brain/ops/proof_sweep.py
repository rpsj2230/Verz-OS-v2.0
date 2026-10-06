"""Which tasks an install's own acceptance runs prove, written out as the commit that closes them.

A task in this repository closes when a commit names it and carries the proof
(`brain.status.PROOF_REQUIRED_FROM`), and for a task that lives on an install the proof is the
install's own acceptance run (`ops.acceptance_result`, written by the worker after every deploy).
Reading two runs, deciding which tasks they prove, and writing the evidence rows and `Closes:`
lines was done by hand twice (#394, #422), and the second time 66 commits had merged since the
first with no task closed, because the step depended on somebody remembering it. This is that
step as a command anybody can run after a deploy.

**What closes is the rule both sweeps used, and nothing looser.** A task closes only when every
check naming it passed on both of the two newest runs
(`A_TASK_CLOSES_ONLY_WHEN_EVERY_CHECK_PASSED_ON_TWO_RUNS`). A check that did not run, failed, or
appears on only the newest run holds every task it names, and the report says which and why,
because those are the real blockers.

**A pass on something made up for the check is held, by a list a person keeps.** Most checks
prove the product on the install's own database with reserved people, which is the install doing
the work. Some pass against a vendor account, channel secret or stand-in the check made itself,
which shows the code and not that the install can reach the real thing. Telling the two apart is a
judgement about each check, not something a row says, so it lives in
`docs/proof-sweep-holds.json`, each held task with its reason
(`A_RESULT_ON_SOMETHING_MADE_UP_IS_HELD`). Rejected: inferring it from the check's sentence,
which would hold or release a task because of a word in a description.

**It reads, and never writes.** From a database URL it reads inside a read-only transaction;
from a file it reads the rows a read-only query printed as JSON lines. It knows no install: the
URL or file is the caller's, and nothing about an install is in this repository.

Task ids: none
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import groupby
from pathlib import Path
from typing import Any, Final

#: Why a task closes on two runs and every check, and not on one check passing once.
A_TASK_CLOSES_ONLY_WHEN_EVERY_CHECK_PASSED_ON_TWO_RUNS: Final = (
    "A task closes only when every acceptance check naming it passed on both of the install's "
    "two newest runs. One check of several, or one run, is a result that has not yet been seen "
    "twice, and a task closed on it is reopened by the next run that disagrees."
)

#: Why a pass is not always proof the install can do the thing.
A_RESULT_ON_SOMETHING_MADE_UP_IS_HELD: Final = (
    "A check that passes against an account, secret or stand-in it made up for itself proves the "
    "code and not the install's reach to the real thing, so the tasks it names are held, each "
    "with its reason, until the install shows them on its own."
)

PASSED: Final = "passed"
NOT_RUN: Final = "not run"
FAILED: Final = "failed"

HOLDS_PATH: Final = Path("docs/proof-sweep-holds.json")

#: The read-only query whose output `rows_from_lines` reads: the two newest runs, one JSON object
#: per row. Written so a look that refuses any statement but a SELECT can run it as it is.
ROWS_QUERY: Final = (
    "select to_jsonb(r) - 'id' from ops.acceptance_result r where run_id in ("
    "select run_id from ops.acceptance_result group by run_id "
    "order by max(started_at) desc limit 2) order by started_at, check_name"
)


class SweepError(Exception):
    """The rows cannot be read as two runs."""


@dataclass(frozen=True)
class Result:
    """One check's outcome on one run."""

    check: str
    leaves: tuple[str, ...]
    outcome: str
    reason: str


@dataclass(frozen=True)
class Run:
    """One run of the acceptance suite on an install."""

    run_id: str
    commit: str
    started_at: datetime
    results: Mapping[str, Result]


@dataclass(frozen=True)
class Sweep:
    """What two runs prove, and every task they leave open with the reason."""

    latest: Run
    previous: Run
    #: Task to the checks that proved it.
    closes: Mapping[str, tuple[str, ...]]
    #: Task to (check, outcome on the newest run, reason) for every check that held it.
    blocked: Mapping[str, tuple[tuple[str, str, str], ...]]
    #: Task to the check seen on the newest run only.
    one_run: Mapping[str, tuple[str, ...]]
    #: Task to the reason a person gave for holding it.
    held: Mapping[str, str]
    #: Proved, and already closed by an earlier commit.
    already_closed: tuple[str, ...] = field(default=())


def leaf_key(leaf: str) -> tuple[int, ...]:
    """`M13.5.10` after `M13.5.9`: the order the work breakdown numbers them in."""
    return tuple(int(part) for part in leaf.lstrip("M").split("."))


def runs_from_rows(rows: Iterable[Mapping[str, Any]]) -> tuple[Run, Run]:
    """The newest run and the one before it, from rows of `ops.acceptance_result`."""
    by_run: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_run[str(row["run_id"])].append(row)
    runs = []
    for run_id, its in by_run.items():
        started = min(_instant(one["started_at"]) for one in its)
        results = {
            str(one["check_name"]): Result(
                check=str(one["check_name"]),
                leaves=tuple(str(one["leaves"]).split()),
                outcome=str(one["outcome"]),
                reason=str(one.get("reason") or ""),
            )
            for one in its
        }
        runs.append(Run(run_id, str(its[0]["commit"]), started, results))
    if len(runs) < 2:
        msg = f"two runs are needed and the rows hold {len(runs)}"
        raise SweepError(msg)
    runs.sort(key=lambda one: one.started_at, reverse=True)
    return runs[0], runs[1]


def _instant(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def judge(
    latest: Run,
    previous: Run,
    *,
    closed: set[str],
    decided: set[str],
    holds: Mapping[str, str],
) -> Sweep:
    """Apply `A_TASK_CLOSES_ONLY_WHEN_EVERY_CHECK_PASSED_ON_TWO_RUNS` and the held list."""
    naming: dict[str, list[str]] = defaultdict(list)
    for result in latest.results.values():
        for leaf in result.leaves:
            naming[leaf].append(result.check)
    closes: dict[str, tuple[str, ...]] = {}
    blocked: dict[str, tuple[tuple[str, str, str], ...]] = {}
    one_run: dict[str, tuple[str, ...]] = {}
    held: dict[str, str] = {}
    already: list[str] = []
    for leaf in sorted(naming, key=leaf_key):
        if leaf in decided:
            continue
        checks = tuple(sorted(naming[leaf]))
        stopped = tuple(
            (check, latest.results[check].outcome, latest.results[check].reason)
            for check in checks
            if latest.results[check].outcome != PASSED
            or (check in previous.results and previous.results[check].outcome != PASSED)
        )
        if stopped:
            blocked[leaf] = stopped
            continue
        new = tuple(check for check in checks if check not in previous.results)
        if new:
            one_run[leaf] = new
            continue
        if leaf in holds:
            held[leaf] = holds[leaf]
            continue
        if leaf in closed:
            already.append(leaf)
            continue
        closes[leaf] = checks
    return Sweep(latest, previous, closes, blocked, one_run, held, tuple(already))


def closes_lines(leaves: Iterable[str]) -> list[str]:
    """`Closes:` lines, one per module, in the work breakdown's order."""
    ordered = sorted(leaves, key=leaf_key)
    return [
        "Closes: " + ", ".join(group)
        for _, group in groupby(ordered, key=lambda leaf: leaf.split(".")[0])
    ]


def evidence_row(leaf: str, checks: Sequence[str], sweep: Sweep, day: str) -> str:
    """The row `docs/tracker-audit-2026-09-28.md` keeps for one closed task."""
    latest, previous = sweep.latest, sweep.previous
    return (
        f"| {leaf} | install and CI | Read-only on the install on {day}: the worker's acceptance "
        f"run on {latest.commit[:7]} (run at {latest.started_at:%H:%M} UTC) passed "
        f"{', '.join(checks)}, and the run on {previous.commit[:7]} "
        f"({previous.started_at:%H:%M} UTC) passed the same. CI: tests/unit/test_acceptance*.py "
        'in "Unit tests" run each of these checks against PostgreSQL at head and the breaks '
        "that fail them |"
    )


def proof_line(sweep: Sweep) -> str:
    """The commit's `Proved-on-install:` line."""
    latest, previous = sweep.latest, sweep.previous
    return (
        f"Proved-on-install: acceptance runs at {latest.commit[:7]} "
        f"({latest.started_at:%Y-%m-%d %H:%M} UTC) and {previous.commit[:7]} "
        f"({previous.started_at:%H:%M} UTC) passed every install check naming each of these "
        "tasks; evidence rows in docs/tracker-audit-2026-09-28.md"
    )


def report(sweep: Sweep) -> str:
    """Everything a person needs to write the sweep's commit, and the blockers it leaves."""
    out = [
        f"newest run {sweep.latest.commit[:7]} at {sweep.latest.started_at:%Y-%m-%d %H:%M} UTC: "
        + _tally(sweep.latest),
        f"run before {sweep.previous.commit[:7]} at {sweep.previous.started_at:%H:%M} UTC: "
        + _tally(sweep.previous),
        "",
        f"closes {len(sweep.closes)}:",
    ]
    out.extend(closes_lines(sweep.closes))
    out.append(proof_line(sweep))
    out.append(
        'Proved-in-ci: "Unit tests" runs tests/unit/test_acceptance*.py, which run each of '
        "these checks against PostgreSQL at head and the breaks that fail them"
    )
    out.append("")
    out.append(f"blocked by a check that did not pass ({len(sweep.blocked)}):")
    for leaf, stops in sweep.blocked.items():
        for check, outcome, reason in stops:
            out.append(f"  {leaf}: {check} {outcome}: {reason}")
    out.append(f"seen on the newest run only ({len(sweep.one_run)}):")
    for leaf, checks in sweep.one_run.items():
        out.append(f"  {leaf}: {', '.join(checks)}")
    out.append(f"held ({len(sweep.held)}):")
    for leaf, reason in sweep.held.items():
        out.append(f"  {leaf}: {reason}")
    out.append(f"proved and already closed: {len(sweep.already_closed)}")
    return "\n".join(out)


def _tally(run: Run) -> str:
    counts: dict[str, int] = defaultdict(int)
    for result in run.results.values():
        counts[result.outcome] += 1
    shown = ", ".join(f"{counts[one]} {one}" for one in (PASSED, NOT_RUN, FAILED))
    return f"{len(run.results)} checks, {shown}"


def rows_from_lines(lines: Iterable[str]) -> list[dict[str, Any]]:
    """Rows from `ROWS_QUERY`'s output: one JSON object a line, anything else skipped."""
    rows = []
    for line in lines:
        text = line.strip()
        if text.startswith("{"):
            rows.append(json.loads(text))
    return rows


async def rows_from_database(database_url: str) -> list[dict[str, Any]]:
    """`ROWS_QUERY` read inside a read-only transaction. The URL is the caller's."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            found = (await connection.execute(text(ROWS_QUERY))).scalars().all()
    finally:
        await engine.dispose()
    return [dict(one) for one in found]


def holds_at(path: Path) -> dict[str, str]:
    """The held tasks and their reasons. See `A_RESULT_ON_SOMETHING_MADE_UP_IS_HELD`."""
    loaded: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))["held"]
    return loaded


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m brain.ops.proof_sweep (--rows FILE | --database-url-from-stdin) [--day DAY]`."""
    parser = argparse.ArgumentParser(prog="python -m brain.ops.proof_sweep")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--rows", type=Path, help="JSON lines printed by ROWS_QUERY")
    source.add_argument(
        "--database-url-from-stdin",
        action="store_true",
        help="read the database URL from standard input, so it is in no process listing",
    )
    parser.add_argument("--day", default="", help="the day the runs were read, for the rows")
    parser.add_argument("--evidence", type=Path, help="append the evidence rows to this file")
    args = parser.parse_args(argv)

    from brain.status import closed_task_ids, decided_of, load_wbs

    repo = Path()
    if args.rows:
        rows = rows_from_lines(args.rows.read_text(encoding="utf-8").splitlines())
    else:
        rows = asyncio.run(rows_from_database(sys.stdin.readline().strip()))
    try:
        latest, previous = runs_from_rows(rows)
    except SweepError as error:
        print(f"proof sweep: {error}", file=sys.stderr)
        return 1
    closed, _ = closed_task_ids(repo)
    decided: set[str] = set()
    for module in load_wbs(repo / "docs" / "wbs.json").get("modules", []):
        decided |= set(decided_of(module))
    sweep = judge(latest, previous, closed=closed, decided=decided, holds=holds_at(HOLDS_PATH))
    print(report(sweep))
    if args.evidence:
        day = args.day or f"{latest.started_at:%Y-%m-%d}"
        rows_out = [evidence_row(leaf, checks, sweep, day) for leaf, checks in sweep.closes.items()]
        with args.evidence.open("a", encoding="utf-8", newline="\n") as handle:
            handle.writelines(row + "\n" for row in rows_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
