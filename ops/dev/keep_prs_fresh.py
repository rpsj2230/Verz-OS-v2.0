"""Keep open pull requests up to date with the branch they target, without touching a conflict.

Why this exists. Whenever the default branch moves, every open pull request behind it is stale.
A stale pull request stops auto-merge, and one that would now conflict gets no CI at all, so a
branch that was green waits for a person to notice. Measured on 2026-10-14: three pull requests
lost thirty to sixty minutes each in one day. Updating a branch is mechanical and safe when the
merge is clean, and a human decision when it is not, so this tool does the first and only
reports the second.

**Why it is a script on a developer's machine and not a GitHub Actions workflow.** A branch
updated with the workflow's own `GITHUB_TOKEN` does not trigger CI on that branch (GitHub
refuses to let a token-made push start more runs, so workflows cannot loop). The update would
land and the pull request would sit with no checks, which is the fault being fixed. An update
made with the developer's own `gh` login does trigger CI. So this runs where that login is.

**What it will do, and nothing else.** For each open pull request targeting the default branch
it asks one pure question, `decide`, and acts on the answer:

* `UPDATE`: the branch is behind and GitHub says it merges cleanly. It runs
  `gh pr update-branch <n>`, which is a **merge commit**, never a rebase and never a force push,
  so the author's commits are not rewritten and nothing they have not already pushed is lost.
* `REPORT`: the branch would conflict. It is named with the files both sides changed (an
  estimate from the two file lists, since GitHub does not say which files conflict) and is
  **not touched**.
* `SKIP`: everything else, with the reason, which is how a skip can be audited.

**What it refuses to touch.** A draft, a pull request from a fork (its branch is not ours to
push to), a pull request not aimed at the branch being kept fresh, a pull request labelled
`hold`, and one whose title or body says do not update. It never pushes to the default branch,
never closes, merges or enables auto-merge on anything, and never reads a secret: it uses the
`gh` login that is already there.

**Dry run is the default.** Nothing is changed unless `--apply` is given. A tool that writes to
other people's branches should have to be asked to, once, by the person running it.

**A cap per pass.** CI on the free plan queues at about twenty jobs a run, and every update
starts a run, so updating thirty branches at once buys a queue rather than speed. At most
`--max-updates` (default 3) are made per pass, the rest are reported as deferred, and the next
pass of `--loop` takes them. Deferred is not skipped: the order is by pull request number so
the same ones are not starved.

**Rejected: relying on `mergeStateStatus == BEHIND`.** GitHub only reports BEHIND when the
branch protection rule requires branches to be up to date. Where it does not, a stale branch
reads CLEAN or BLOCKED and the tool would do nothing. The comparison endpoint's `behind_by` is
the fact, so it is asked for.

Run it as `uv run python ops/dev/keep_prs_fresh.py` (dry run), add `--apply` to act and
`--loop 300` to repeat every five minutes. `ops/dev/README.md` has the rest.

Task ids: none, developer tooling approved by the owner on 2026-10-14 (item 4 of the
keep-pull-requests-fresh goal).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

#: A label that means a person is working on the branch and nothing should push to it.
HOLD_LABEL = "hold"

#: Title or body wording that opts a pull request out, in any of the usual spellings.
DO_NOT_UPDATE = re.compile(r"do[\s_-]*not[\s_-]*update", re.IGNORECASE)

#: How many branches are updated in one pass, see the module docstring for why it is capped.
DEFAULT_MAX_UPDATES = 3

#: The fields asked of `gh pr list`. Named once so the tool and its tests agree on the shape.
PR_FIELDS = (
    "number,title,body,isDraft,isCrossRepository,labels,headRefName,headRefOid,"
    "baseRefName,mergeable,mergeStateStatus,files,url"
)

#: GitHub's own words for mergeability, as `gh pr list` prints them.
MERGEABLE = "MERGEABLE"
CONFLICTING = "CONFLICTING"


class Action(StrEnum):
    UPDATE = "update"
    REPORT = "report"
    SKIP = "skip"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class Decision:
    """What to do about one pull request, and why, in words a person can read in a log."""

    number: int
    action: Action
    reason: str
    #: For a REPORT: the files both the pull request and the base changed.
    files: tuple[str, ...] = ()


def refusal(pr: Mapping[str, Any], base: str) -> str | None:
    """Why this pull request must not be touched, or None if nothing forbids it.

    Pure, and checked before any network call about the pull request is made, so a held draft
    costs nothing.
    """
    labels = {str(label.get("name", "")).strip().lower() for label in pr.get("labels") or []}
    if pr.get("isDraft"):
        return "a draft is not ready to be kept fresh"
    if pr.get("isCrossRepository"):
        return "its branch is in a fork, which is not ours to push to"
    if pr.get("baseRefName") != base:
        return f"it targets {pr.get('baseRefName')}, not {base}"
    if HOLD_LABEL in labels:
        return f"it is labelled {HOLD_LABEL}"
    if DO_NOT_UPDATE.search(f"{pr.get('title') or ''}\n{pr.get('body') or ''}"):
        return "its title or description says do not update"
    return None


def decide(
    pr: Mapping[str, Any],
    *,
    base: str,
    behind_by: int | None,
    base_files: frozenset[str] = frozenset(),
) -> Decision:
    """The whole policy: update, report or skip one pull request.

    `behind_by` is how many commits of the base the branch lacks (None when it could not be
    found out) and `base_files` the files the base changed since the branch left it, used only
    to name the likely conflict. Everything is passed in, so this has no clock, no network and
    nothing to mock.
    """
    number = int(pr["number"])
    forbidden = refusal(pr, base)
    if forbidden is not None:
        return Decision(number, Action.SKIP, forbidden)
    mergeable = pr.get("mergeable")
    if mergeable == CONFLICTING:
        own = {str(f.get("path", "")) for f in pr.get("files") or []}
        both = tuple(sorted(own & base_files))
        return Decision(number, Action.REPORT, f"it conflicts with {base}", both)
    if mergeable != MERGEABLE:
        return Decision(number, Action.SKIP, "GitHub has not yet worked out whether it merges")
    if behind_by is None:
        return Decision(number, Action.SKIP, "how far behind it is could not be found out")
    if behind_by <= 0:
        return Decision(number, Action.SKIP, f"already up to date with {base}")
    return Decision(
        number, Action.UPDATE, f"{behind_by} commit(s) behind {base} and merges cleanly"
    )


def plan(decisions: Sequence[Decision], max_updates: int) -> list[Decision]:
    """Cap the updates made in one pass, lowest number first, and mark the rest as deferred."""
    out: list[Decision] = []
    made = 0
    for d in sorted(decisions, key=lambda x: x.number):
        if d.action is Action.UPDATE:
            if made >= max_updates:
                out.append(
                    Decision(
                        d.number, Action.DEFERRED, f"{d.reason}; over the cap of {max_updates}"
                    )
                )
                continue
            made += 1
        out.append(d)
    return out


# ---------------------------------------------------------------- the gh side, kept thin

Runner = Callable[[Sequence[str]], str]


def gh(args: Sequence[str]) -> str:
    """Run `gh` with the caller's own login and return stdout, raising on a failure."""
    done = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)  # noqa: S603, S607
    if done.returncode != 0:
        msg = f"gh {' '.join(args[:3])} failed: {done.stderr.strip()[:300]}"
        raise RuntimeError(msg)
    return done.stdout


def repo_and_base(run: Runner) -> tuple[str, str]:
    """The repository and its default branch, read from `gh`, never written into the source."""
    info = json.loads(run(["repo", "view", "--json", "nameWithOwner,defaultBranchRef"]))
    return str(info["nameWithOwner"]), str(info["defaultBranchRef"]["name"])


def compare(run: Runner, repo: str, base: str, head_oid: str) -> tuple[int | None, frozenset[str]]:
    """How far behind `head_oid` is and which files the base changed since it left."""
    try:
        raw = run(["api", f"repos/{repo}/compare/{head_oid}...{base}"])
        data = json.loads(raw)
        return int(data["ahead_by"]), frozenset(str(f["filename"]) for f in data.get("files") or [])
    except (RuntimeError, KeyError, ValueError):
        return None, frozenset()


def one_pass(run: Runner, repo: str, base: str, *, apply: bool, max_updates: int) -> list[Decision]:
    """Look at every open pull request once, act on the cap, and return what was decided."""
    prs = json.loads(
        run(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--base",
                base,
                "--limit",
                "200",
                "--json",
                PR_FIELDS,
            ]
        )
    )
    decided: list[Decision] = []
    for pr in prs:
        if refusal(pr, base) is not None or pr.get("mergeable") not in (MERGEABLE, CONFLICTING):
            decided.append(decide(pr, base=base, behind_by=None))
            continue
        # The base is the left side here: ahead_by is how far the base is past the branch.
        behind_by, base_files = compare(run, repo, base, str(pr["headRefOid"]))
        decided.append(decide(pr, base=base, behind_by=behind_by, base_files=base_files))
    planned = plan(decided, max_updates)
    for d in planned:
        if d.action is Action.UPDATE and apply:
            try:
                run(["pr", "update-branch", str(d.number), "--repo", repo])
                print(f"#{d.number}: updated ({d.reason})")
            except RuntimeError as err:
                print(f"#{d.number}: update refused, left as it was ({err})")
        elif d.action is Action.UPDATE:
            print(f"#{d.number}: would update ({d.reason})")
        elif d.action is Action.REPORT:
            files = ", ".join(d.files) if d.files else "files not determined"
            print(f"#{d.number}: CONFLICT, not touched. {d.reason}. Both changed: {files}")
        elif d.action is Action.DEFERRED:
            print(f"#{d.number}: deferred ({d.reason})")
        else:
            print(f"#{d.number}: skipped ({d.reason})")
    return planned


def main(argv: Sequence[str] | None = None, run: Runner = gh) -> int:
    parser = argparse.ArgumentParser(description="Keep open pull requests up to date.")
    parser.add_argument("--apply", action="store_true", help="make the updates (default: dry run)")
    parser.add_argument("--dry-run", action="store_true", help="report only; this is the default")
    parser.add_argument(
        "--loop",
        type=int,
        metavar="SECONDS",
        default=0,
        help="repeat every SECONDS until interrupted",
    )
    parser.add_argument(
        "--max-updates",
        type=int,
        default=DEFAULT_MAX_UPDATES,
        help="branches updated per pass (default %(default)s)",
    )
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run contradict each other")
    if args.loop < 0 or args.max_updates < 1:
        parser.error("--loop must not be negative and --max-updates must be at least 1")
    try:
        repo, base = repo_and_base(run)
    except RuntimeError as err:
        print(f"cannot read the repository from gh: {err}", file=sys.stderr)
        return 2
    mode = "APPLY" if args.apply else "dry run"
    print(f"keeping pull requests fresh against {base} in {repo} ({mode})")
    try:
        while True:
            try:
                one_pass(run, repo, base, apply=args.apply, max_updates=args.max_updates)
            except RuntimeError as err:
                print(f"pass failed, will try again: {err}", file=sys.stderr)
                if not args.loop:
                    return 1
            if not args.loop:
                return 0
            time.sleep(args.loop)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
