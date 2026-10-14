"""Assemble open pull requests into one merge train, so the whole suite runs once on all of them.

Why this exists. A pull request now runs lint, types, invariants and the test files its diff can
reach, and no more (`ops/DEPLOY.md`, "What a normal pull request no longer proves"). The whole
suite runs on a pull request whose branch starts with `train/`, and every night. Measured on
2026-10-14, a pull request that fell back to the whole suite cost 127 to 222 job-minutes and 45 to
50 minutes of wall clock, and nine of them queued at once took over an hour each on a plan that
runs 20 jobs at a time. One train carrying nine pull requests pays that once. This tool makes the
train, so nobody does it by hand, in the wrong order, with a squash.

**What it does.** Given pull request numbers, in the order to merge them, it creates
`train/<date>-<n>` from the default branch, merges each pull request's head into it with a **merge
commit**, in the order given, pushes the branch and opens one pull request for it with auto-merge
off. Every original commit therefore survives on the branch with its `Closes:` and
`Proved-on-install:` lines, which the tracker reads from commit messages and which a squash would
collapse into one.

**What it never does.** It never squashes and never rebases (both rewrite or collapse the commits
whose trailers are the point). It never pushes with a force flag, never pushes to the default
branch, never merges the pull request it opens and never turns auto-merge on: the train is
reviewed and merged by a person, with a merge commit. It never reads a secret; it uses the `gh`
login already on the machine, and the repository and its default branch come from `gh repo view`,
so no name is written into this file.

**It stops at the first conflict and leaves the checkout as it found it.** The pull request and
the files in conflict are reported, the half-made merge is aborted, the checkout goes back to
where it was and the train branch it made is deleted locally. Nothing has been pushed by then.
Resolving it is a human decision: fix the conflict on the pull request itself and run the tool
again. **A dirty working tree is refused up front**, because switching branches over local edits is
how work is lost.

**Migration numbers are checked before anything is merged and again on what was merged.** Two
pull requests that each added `0232_...` merge without a git conflict (the file names differ) and
then break at the first `alembic upgrade`. So the numbers the pull requests add are read from
their file lists, and the train is refused when two carry the same number, when one reuses a
number already on the default branch, or when the numbers do not continue exactly from the default
branch's highest. After the merges the same check is run over the assembled tree, which is what
catches a number that arrived some other way. The numbers a train carries are listed, in order, in
the pull request it opens.

**Dry run is the default.** Without `--apply` it fetches the default branch (a read) and reports
what it would do and any refusal, and changes no branch, pushes nothing and opens nothing.

**Rejected: a GitHub Actions workflow.** It would push with the workflow token, and a branch
pushed that way does not start CI (the same reason `keep_prs_fresh.py` runs on a developer's
machine), so the train would sit with no checks, which is the thing it exists to prevent.

**Rejected: merging the pull requests into one branch by squash for a cleaner history.** The
tracker's claims are commit trailers; one squashed commit carries one set of them and the rest are
lost. A merge commit per pull request keeps all of them and costs one extra line of history each.

Run it as `uv run python ops/dev/assemble_train.py 590 592 594` (dry run) and add `--apply` to act.
`ops/dev/README.md` has the rest.

Task ids: none, developer tooling approved by the owner on 2026-10-14 (item 1 of the CI speed-up
list).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

#: The only branches this tool will ever push: a train's own.
TRAIN_PREFIX = "train/"

#: Where migrations live, and the shape of a file name in it: a number, an underscore, a name.
MIGRATIONS_DIR = "migrations/versions"
MIGRATION_NAME = re.compile(r"^(\d+)_[^/]+\.py$")

#: What the pull request needs to be before it can ride a train.
PR_FIELDS = "number,title,state,isDraft,isCrossRepository,baseRefName,headRefName,headRefOid,url"

#: Flags this tool never passes to git. A command built here is checked against them before it
#: runs, so a later edit that adds one fails loudly instead of rewriting somebody's history.
FORBIDDEN_GIT_FLAGS = frozenset(
    {
        "--squash",
        "--rebase",
        "--force",
        "-f",
        "--force-with-lease",
        "--force-if-includes",
        "--mirror",
        "--delete",
        "--no-verify",
    }
)


class Outcome(StrEnum):
    DRY_RUN = "dry run"
    REFUSED = "refused"
    CONFLICT = "conflict"
    PUSHED = "pushed"


@dataclass(frozen=True)
class Carried:
    """A migration file a pull request adds: which pull request, which number, which file."""

    pr: int
    number: int
    path: str


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    detail: str
    train: str = ""
    url: str = ""


@dataclass(frozen=True)
class GitResult:
    code: int
    out: str
    err: str = ""


Gh = Callable[[Sequence[str]], str]
Git = Callable[[Sequence[str]], GitResult]


# ---------------------------------------------------------------- the decisions, all pure


def refusal(pr: Mapping[str, Any], base: str) -> str | None:
    """Why this pull request cannot ride a train, or None when nothing forbids it."""
    if str(pr.get("state", "")).upper() != "OPEN":
        return f"it is {str(pr.get('state', 'not open')).lower()}, not open"
    if pr.get("isDraft"):
        return "it is a draft"
    if pr.get("isCrossRepository"):
        return "its branch is in a fork, which a train cannot merge by commit id from here"
    if pr.get("baseRefName") != base:
        return f"it targets {pr.get('baseRefName')}, not {base}"
    if str(pr.get("headRefName", "")).startswith(TRAIN_PREFIX):
        return "it is itself a train"
    return None


def list_problem(numbers: Sequence[int]) -> str | None:
    """Why the list of pull request numbers cannot be used at all."""
    if not numbers:
        return "no pull request numbers were given"
    seen: set[int] = set()
    for number in numbers:
        if number in seen:
            return f"#{number} is listed twice"
        seen.add(number)
    return None


def train_name(day: date, existing: Iterable[str]) -> str:
    """`train/<date>-<n>` with the lowest n not already taken, locally or on the remote."""
    taken = set(existing)
    n = 1
    while f"{TRAIN_PREFIX}{day.isoformat()}-{n}" in taken:
        n += 1
    return f"{TRAIN_PREFIX}{day.isoformat()}-{n}"


def migration_files(paths: Iterable[str]) -> dict[int, list[str]]:
    """The migration files among `paths`, by number. A number with two files is a collision."""
    found: dict[int, list[str]] = {}
    for path in paths:
        directory, _, name = path.rpartition("/")
        match = MIGRATION_NAME.match(name)
        if directory == MIGRATIONS_DIR and match is not None:
            found.setdefault(int(match.group(1)), []).append(path)
    return found


def migration_problems(main_numbers: Iterable[int], carried: Sequence[Carried]) -> list[str]:
    """Everything wrong with the migration numbers a train would carry; empty when it is sound.

    A number must be carried by one file only, must not already exist on the default branch, and
    the carried numbers must continue exactly from the default branch's highest, with no gap.
    """
    on_main = set(main_numbers)
    head = max(on_main, default=0)
    problems: list[str] = []
    by_number: dict[int, list[Carried]] = {}
    for one in carried:
        by_number.setdefault(one.number, []).append(one)
    for number in sorted(by_number):
        files = by_number[number]
        if len(files) > 1:
            who = ", ".join(f"#{one.pr} ({one.path.rpartition('/')[2]})" for one in files)
            problems.append(f"number {number:04d} is carried by more than one file: {who}")
        if number in on_main:
            problems.append(
                f"number {number:04d} already exists on the default branch "
                f"(carried by #{files[0].pr})"
            )
    fresh = sorted(n for n in by_number if n not in on_main)
    expected = head + 1
    for number in fresh:
        if number != expected:
            problems.append(
                f"the numbers do not continue from the default branch's highest, {head:04d}: "
                f"expected {expected:04d}, found {number:04d} "
                f"(carried by #{by_number[number][0].pr})"
            )
            break
        expected += 1
    return problems


def title(name: str, numbers: Sequence[int]) -> str:
    """The train pull request's title, from its name and the pull requests it carries."""
    return f"Merge train {name.removeprefix(TRAIN_PREFIX)}: " + ", ".join(f"#{n}" for n in numbers)


def body(
    prs: Sequence[Mapping[str, Any]], carried: Sequence[Carried], main_head: int, base: str
) -> str:
    """The train pull request's description: what is in it, in order, and how to merge it."""
    lines = ["This is a merge train. It carries these pull requests, merged in this order:", ""]
    for pr in prs:
        lines.append(f"{pr['number']}. #{pr['number']} {pr['title']} (`{pr['headRefName']}`)")
    lines += ["", "Migrations carried, in the order of the pull requests above:", ""]
    if carried:
        lines.append(f"The highest on `{base}` is {main_head:04d}.")
        lines.append("")
        for one in carried:
            lines.append(f"- {one.number:04d} from #{one.pr} (`{one.path.rpartition('/')[2]}`)")
    else:
        lines.append("None.")
    lines += [
        "",
        "**The full suite runs on this pull request**, because its branch starts with "
        f"`{TRAIN_PREFIX}`. An ordinary pull request runs only the test files its diff reaches.",
        "",
        "**Merge it with a merge commit, never a squash**, so every original commit and its "
        "`Closes:` and `Proved-on-install:` lines reach the default branch. Auto-merge is off on "
        "purpose. The pull requests above are usually marked merged by GitHub once this lands; "
        "if one is not, close it by hand.",
        "",
        "Assembled by `ops/dev/assemble_train.py`.",
    ]
    return "\n".join(lines)


def forbidden_in(args: Sequence[str]) -> str | None:
    """The forbidden flag in a git command, or a `+` refspec (a forced update), else None."""
    for arg in args:
        if arg in FORBIDDEN_GIT_FLAGS or arg.startswith("--force"):
            return arg
        if args and args[0] == "push" and arg.startswith("+"):
            return arg
    return None


def push_args(branch: str, remote: str, base: str) -> list[str]:
    """The one push this tool makes: its own train branch, by name, with no force and no default."""
    if not branch.startswith(TRAIN_PREFIX) or branch == base:
        msg = f"refusing to push {branch!r}: only {TRAIN_PREFIX} branches are pushed from here"
        raise ValueError(msg)
    return ["push", "--set-upstream", remote, branch]


# ---------------------------------------------------------------- the git and gh side, thin


def gh(args: Sequence[str]) -> str:
    """Run `gh` with the caller's own login and return stdout, raising on a failure."""
    done = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)  # noqa: S603, S607
    if done.returncode != 0:
        msg = f"gh {' '.join(args[:3])} failed: {done.stderr.strip()[:300]}"
        raise RuntimeError(msg)
    return done.stdout


def git(args: Sequence[str]) -> GitResult:
    """Run `git` in the current checkout. Refuses a forbidden flag before it runs anything."""
    bad = forbidden_in(args)
    if bad is not None:
        msg = f"refusing to run git with {bad}"
        raise ValueError(msg)
    done = subprocess.run(["git", *args], capture_output=True, text=True, check=False)  # noqa: S603, S607
    return GitResult(done.returncode, done.stdout, done.stderr)


def repo_and_base(run: Gh) -> tuple[str, str]:
    """The repository and its default branch, read from `gh`, never written into the source."""
    info = json.loads(run(["repo", "view", "--json", "nameWithOwner,defaultBranchRef"]))
    return str(info["nameWithOwner"]), str(info["defaultBranchRef"]["name"])


def _lines(text: str) -> list[str]:
    return [one for one in text.splitlines() if one.strip()]


def added_migrations(run: Gh, repo: str, number: int) -> list[Carried]:
    """The migration files pull request `number` adds or renames into place, from its file list."""
    raw = run(
        [
            "api",
            f"repos/{repo}/pulls/{number}/files",
            "--paginate",
            "--jq",
            ".[] | [.status, .filename] | @tsv",
        ]
    )
    paths = []
    for line in _lines(raw):
        status, _, filename = line.partition("\t")
        if status in ("added", "renamed"):
            paths.append(filename)
    return [
        Carried(number, n, path)
        for n, files in sorted(migration_files(paths).items())
        for path in files
    ]


def _need(git_run: Git, args: Sequence[str]) -> str:
    done = git_run(args)
    if done.code != 0:
        msg = f"git {' '.join(args[:3])} failed: {(done.err or done.out).strip()[:300]}"
        raise RuntimeError(msg)
    return done.out


def _restore(git_run: Git, start: str, detached: bool, train: str | None) -> None:
    """Go back to where the checkout was, and drop the local train branch if none was pushed."""
    git_run(["switch", "--detach", start] if detached else ["switch", start])
    if train is not None:
        git_run(["branch", "-D", train])


def assemble(
    run: Gh,
    git_run: Git,
    *,
    repo: str,
    base: str,
    remote: str,
    numbers: Sequence[int],
    day: date,
    apply: bool,
    say: Callable[[str], None] = print,
) -> Result:
    """The whole flow. Returns what happened; raises only for a failure it cannot explain."""
    problem = list_problem(numbers)
    if problem is not None:
        return Result(Outcome.REFUSED, problem)
    prs = [
        json.loads(run(["pr", "view", str(n), "--repo", repo, "--json", PR_FIELDS]))
        for n in numbers
    ]
    for pr in prs:
        why = refusal(pr, base)
        if why is not None:
            return Result(Outcome.REFUSED, f"#{pr['number']}: {why}")
    _need(git_run, ["fetch", remote, base])
    tree = _need(
        git_run, ["ls-tree", "-r", "--name-only", f"{remote}/{base}", "--", MIGRATIONS_DIR]
    )
    main_numbers = migration_files(_lines(tree))
    carried = [one for n in numbers for one in added_migrations(run, repo, n)]
    problems = migration_problems(main_numbers, carried)
    if problems:
        return Result(Outcome.REFUSED, "migration numbers: " + "; ".join(problems))
    main_head = max(main_numbers, default=0)
    allowed = run(["api", f"repos/{repo}", "--jq", ".allow_merge_commit"]).strip()
    if allowed == "false":
        say(
            "warning: this repository does not allow merge commits, so the train cannot be "
            "merged the way it must be (a merge commit, never a squash)"
        )
    existing = _lines(
        _need(git_run, ["branch", "--list", f"{TRAIN_PREFIX}*", "--format=%(refname:short)"])
    )
    heads = _lines(_need(git_run, ["ls-remote", "--heads", remote, f"{TRAIN_PREFIX}*"]))
    existing += [one.split("\t")[-1].removeprefix("refs/heads/") for one in heads]
    name = train_name(day, existing)
    if not apply:
        say(f"would create {name} from {remote}/{base} and merge, with a merge commit, in order:")
        for pr in prs:
            say(f"  #{pr['number']} {pr['title']}")
        say(
            "migrations carried: "
            + (", ".join(f"{c.number:04d} (#{c.pr})" for c in carried) or "none")
        )
        say(f"would push {name} and open one pull request with auto-merge off (dry run: not done)")
        return Result(Outcome.DRY_RUN, "nothing was changed", name)
    if _lines(_need(git_run, ["status", "--porcelain", "--untracked-files=no"])):
        return Result(
            Outcome.REFUSED, "the working tree has uncommitted changes; commit or stash them"
        )
    start = _need(git_run, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    detached = start == "HEAD"
    if detached:
        start = _need(git_run, ["rev-parse", "HEAD"]).strip()
    _need(git_run, ["switch", "--create", name, "--no-track", f"{remote}/{base}"])
    pushed = False
    try:
        for pr in prs:
            n = pr["number"]
            _need(git_run, ["fetch", remote, f"refs/pull/{n}/head"])
            oid = _need(git_run, ["rev-parse", "FETCH_HEAD"]).strip()
            merged = git_run(
                ["merge", "--no-ff", "-m", f"Merge #{n}: {pr['title']}\n\nHead {oid}", oid]
            )
            if merged.code != 0:
                files = _lines(git_run(["diff", "--name-only", "--diff-filter=U"]).out)
                git_run(["merge", "--abort"])
                return Result(
                    Outcome.CONFLICT,
                    f"#{n} conflicts with {base} or an earlier pull request in the train: "
                    + (", ".join(files) if files else "files not determined"),
                )
            say(f"merged #{n} ({oid[:10]})")
        final = migration_files(
            _lines(_need(git_run, ["ls-tree", "-r", "--name-only", "HEAD", "--", MIGRATIONS_DIR]))
        )
        on_main = {path for files in main_numbers.values() for path in files}
        arrived = [
            Carried(0, n, path)
            for n, files in sorted(final.items())
            for path in files
            if path not in on_main
        ]
        problems = migration_problems(main_numbers, arrived)
        if problems:
            return Result(
                Outcome.REFUSED, "after merging, the migration numbers: " + "; ".join(problems)
            )
        _need(git_run, push_args(name, remote, base))
        pushed = True
        url = run(
            [
                "pr",
                "create",
                "--repo",
                repo,
                "--base",
                base,
                "--head",
                name,
                "--title",
                title(name, numbers),
                "--body",
                body(prs, carried, main_head, base),
            ]
        ).strip()
        return Result(Outcome.PUSHED, "the train is open; merge it with a merge commit", name, url)
    finally:
        _restore(git_run, start, detached, None if pushed else name)


def _number(text: str) -> int:
    return int(text.lstrip("#"))


def main(argv: Sequence[str] | None = None, run: Gh = gh, git_run: Git = git) -> int:
    parser = argparse.ArgumentParser(description="Assemble pull requests into one merge train.")
    parser.add_argument("numbers", nargs="+", type=_number, metavar="PR", help="in merge order")
    parser.add_argument("--apply", action="store_true", help="make the train (default: dry run)")
    parser.add_argument("--dry-run", action="store_true", help="report only; this is the default")
    parser.add_argument("--remote", default="origin", help="the remote to fetch from and push to")
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run contradict each other")
    try:
        repo, base = repo_and_base(run)
    except RuntimeError as err:
        print(f"cannot read the repository from gh: {err}", file=sys.stderr)
        return 2
    print(f"assembling a train against {base} in {repo} ({'APPLY' if args.apply else 'dry run'})")
    try:
        result = assemble(
            run,
            git_run,
            repo=repo,
            base=base,
            remote=args.remote,
            numbers=args.numbers,
            day=date.today(),
            apply=args.apply,
        )
    except (RuntimeError, ValueError) as err:
        print(f"stopped, nothing was pushed: {err}", file=sys.stderr)
        return 1
    print(f"{result.outcome.value}: {result.detail}")
    if result.url:
        print(result.url)
    return 0 if result.outcome in (Outcome.DRY_RUN, Outcome.PUSHED) else 1


if __name__ == "__main__":
    sys.exit(main())
