"""The test files one CI shard runs on a pull request: its share of the selection, or of the suite.

GitHub's free plan runs twenty jobs at a time and a pull request costs about twenty, so with
twenty to forty of them queued a run waited over an hour (measured 2026-10-12) and the owner's
work stalled. The unit shards were the largest part of that cost, and every one of them ran every
test file whatever the diff touched. `brain.ops.test_selection` measured, over seven real pull
requests, that choosing the files an import graph says a diff can reach missed nothing, so this
module is where that choice is made for the shard job: **the shard runs its share of the selected
files, and its share of the whole suite whenever it cannot be sure.**

**The failure direction is the whole design.** A selection that errs by running too much costs
minutes; one that errs by running too little is a red test nobody ran, merged. So every way this
can go wrong ends in the full share, and the reason is printed so the log says why:

- no base commit was given, or the checkout does not hold it (a push, a shallow clone, a force
  push that moved the base);
- the diff is empty or git could not compute it;
- the selection says `full`: the diff touched a conftest, a fixture, the project settings, the
  workflow or this planning code, a support module under `tests/`, or deleted a source module;
- anything in the selection raises. The planner is not allowed to be the reason a pull request
  cannot run its tests, and it is not allowed to be the reason it runs none either.

**Every shard computes the plan itself rather than being handed one.** A planning job would have
to build the environment the import graph needs (`brain.ops.guards` imports the application's
settings) and pass a list between jobs, which puts a serial job in front of every shard and gives
the shards one more place to disagree. The plan is a pure function of the tree and the diff, so
eight runners reach the same eight shares, and `tests/unit/test_test_selection.py` holds that the
shares between them are exactly the selection with every file in one.

**An empty share is a pass with its reason printed, not a refusal.** `test_shards` refuses a
shard with nothing in it because a bare `pytest` runs the whole suite; the same emptiness in a
selection is correct (a small diff, a heavy file, eight shards), and the caller then does not
call `pytest` at all. Today a selection always carries the invariants directory, whose files fall
in every shard, so the case is not reachable on this repository; it is still handled, because the
day somebody narrows `ALWAYS` is the day eight shards each fail with "has no test files".

**Selected runs are partial, so they cannot hold the coverage floor.** Each shard writes a small
file saying whether it ran the full suite; the coverage job holds the floor only when every shard
did, and the nightly suite (which always runs everything) holds it every night. See
`.github/workflows/ci.yml` and `nightly-suite.yml`.

**Depth one.** Depths 0, 1 and 2 all missed nothing in the record; one is the conservative
middle, and a deeper graph here is cheaper to measure against the nightly than to argue.

Rejected: a pull request label or comment that forces the full suite. Nobody should have to know
that a failure was hiding behind a selection, and a way to skip it is a way to forget it.

Task ids: none
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from brain.ops.test_selection import changed_files, select
from brain.ops.test_shards import REPO, ShardError, collected, partition, shard, weight

#: How far through the import graph a pull request's selection reaches.
PLAN_DEPTH: Final[int] = 1

#: Why a shard that cannot be sure runs everything it would have run.
WHEN_UNSURE_RUN_THE_FULL_SHARE: Final[str] = (
    "Whatever cannot be established (the base commit, the diff, the selection itself) runs the "
    "shard's whole share of the suite, because running too much costs minutes and running too "
    "little merges a red test nobody ran."
)


@dataclass(frozen=True)
class Plan:
    """What one shard runs, whether that is the full suite's share, and why."""

    files: tuple[str, ...]
    full: bool
    reason: str


def _base_is_known(base: str, root: Path) -> bool:
    done = subprocess.run(  # noqa: S603  a commit id from the workflow's own context, no shell
        ["git", "cat-file", "-e", f"{base}^{{commit}}"],  # noqa: S607  git on PATH, as elsewhere
        cwd=root,
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


def plan(
    number: int,
    of: int,
    *,
    base: str,
    head: str,
    depth: int = PLAN_DEPTH,
    root: Path = REPO,
    changed: Sequence[str] | None = None,
    suite: Sequence[str] | None = None,
) -> Plan:
    """The files shard `number` of `of` runs for the diff `base..head`.

    `changed` and `suite` are for a caller that already knows them (the tests); the workflow
    passes neither and both are read from the checkout.
    """

    def whole(reason: str) -> Plan:
        return Plan(files=shard(number, of, root), full=True, reason=reason)

    try:
        if not base and changed is None:
            return whole("no base commit was given")
        if changed is None and not _base_is_known(base, root):
            return whole("the base commit is not in this checkout")
        names = list(changed) if changed is not None else changed_files(base, head)
        if not names:
            return whole("the diff is empty or git could not compute it")
        everything = tuple(collected(root)) if suite is None else tuple(suite)
        chosen = select(names, depth=depth, suite=everything)
        if chosen.full:
            return whole("the diff touches something the import graph cannot see")
        weights = {name: weight(root / name) for name in chosen.files}
        mine = partition(weights, of, allow_empty=True)[number - 1]
    except ShardError:
        raise
    except Exception as error:  # the planner must never be why the tests do not run
        return whole(f"the selection failed ({type(error).__name__}: {error})")
    return Plan(
        files=mine,
        full=False,
        reason=f"{len(chosen.files)} of {len(everything)} files selected at depth {depth}",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Print one shard's files, one per line, with the mode and its reason on stderr.

    Exit status 2 only when even the full share cannot be computed. A mode file, when asked for,
    holds `mode=full` or `mode=selected` for the coverage job to read.
    """
    parser = argparse.ArgumentParser(
        prog="python -m brain.ops.test_plan",
        description="List the test files one CI shard runs for a pull request's diff.",
    )
    parser.add_argument("--shard", type=int, required=True, help="which shard, counting from 1")
    parser.add_argument("--of", type=int, required=True, help="how many shards there are")
    parser.add_argument("--base", default="", help="the pull request's base commit")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--depth", type=int, default=PLAN_DEPTH)
    parser.add_argument("--mode-file", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        made = plan(args.shard, args.of, base=args.base, head=args.head, depth=args.depth)
    except ShardError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    mode = "full" if made.full else "selected"
    print(f"shard {args.shard} of {args.of}: mode={mode} ({made.reason})", file=sys.stderr)
    if args.mode_file is not None:
        args.mode_file.parent.mkdir(parents=True, exist_ok=True)
        args.mode_file.write_text(f"mode={mode}\n", encoding="utf-8", newline="\n")
    print("\n".join(made.files))
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point CI runs
    raise SystemExit(main())
