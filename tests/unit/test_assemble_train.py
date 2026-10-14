"""The merge train tool: what it refuses, the exact commands it runs, and that real git agrees.

`ops/dev/assemble_train.py` merges several open pull requests into one `train/` branch and opens one
pull request for it. The properties worth pinning are the ones that protect history (a merge commit
for each pull request, never a squash, never a rebase, never a force push, never a push to the
default branch), the refusals (a conflict, a duplicate migration number, a dirty tree) and that a
refusal leaves the checkout as it found it. The positive case is pinned beside each refusal, since a
tool tested only by what it declines is satisfied by one that declines everything.

The script lives under `ops/dev`, which is not a package, so it is loaded by path. Its decisions
are pure and tested directly; its commands are pinned through a fake `gh` and a fake `git`; and one
group of tests runs the real `git` against a local bare repository, because a fake that agrees with
the code proves nothing about git.

Task ids: none, developer tooling.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "ops" / "dev" / "assemble_train.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("assemble_train_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses and enums look the module up by name
    spec.loader.exec_module(module)
    return module


train = load()
DAY = date(2999, 1, 1)
BASE = "trunk"
REPO = "owner/repo"


def pr(number: int, **over: Any) -> dict[str, Any]:
    """A pull request as `gh pr view --json` prints it: open, in this repository, aimed at BASE."""
    made: dict[str, Any] = {
        "number": number,
        "title": f"Change {number}",
        "state": "OPEN",
        "isDraft": False,
        "isCrossRepository": False,
        "baseRefName": BASE,
        "headRefName": f"M1/change-{number}",
        "headRefOid": f"{number:040d}",
        "url": f"https://example.test/pull/{number}",
    }
    made.update(over)
    return made


def mig(number: int, name: str = "x") -> str:
    return f"migrations/versions/{number:04d}_{name}.py"


# ------------------------------------------------------------------ the pure decisions


def test_an_open_pull_request_into_the_default_branch_may_ride_a_train() -> None:
    """The positive half. Delete this and a `refusal` that returned a reason for everything
    would satisfy every refusal test below, and no train could ever be made."""
    assert train.refusal(pr(1), BASE) is None


@pytest.mark.parametrize(
    "over",
    [
        {"state": "CLOSED"},
        {"state": "MERGED"},
        {"isDraft": True},
        {"isCrossRepository": True},
        {"baseRefName": "elsewhere"},
        {"headRefName": "train/2999-01-01-1"},
    ],
)
def test_a_pull_request_that_cannot_ride_a_train_is_refused_with_a_reason(
    over: dict[str, Any],
) -> None:
    """A closed or merged one has nothing to merge, a draft is not ready, a fork's head is not in
    this repository to fetch by commit id, one aimed elsewhere would drag another branch's work in,
    and a train inside a train defeats the point. Delete this and each is merged silently."""
    why = train.refusal(pr(1, **over), BASE)
    assert why is not None and why != ""


def test_an_empty_or_repeated_list_of_numbers_is_refused_and_a_plain_one_is_not() -> None:
    """Delete this and a repeated number merges the same branch twice (a no-op that reads as a
    success) and an empty list opens a train carrying nothing."""
    assert train.list_problem([]) is not None
    assert "#7" in train.list_problem([7, 8, 7])
    assert train.list_problem([7, 8, 9]) is None


def test_the_train_takes_the_lowest_free_number_for_the_day_locally_or_remotely() -> None:
    """Delete this and a second train on the same day collides with the first and the push is
    refused, or worse, a name taken only on the remote is reused."""
    assert train.train_name(DAY, []) == "train/2999-01-01-1"
    taken = ["train/2999-01-01-1", "train/2999-01-01-2", "train/2998-12-31-1"]
    assert train.train_name(DAY, taken) == "train/2999-01-01-3"
    assert train.train_name(DAY, ["train/2999-01-01-2"]) == "train/2999-01-01-1"


def test_only_numbered_migration_files_directly_in_the_migrations_directory_count() -> None:
    """Delete this and a helper, a cache directory or a file elsewhere with a number in its name
    is read as a migration and a perfectly good train is refused for a gap that is not there."""
    found = train.migration_files(
        [
            mig(5),
            "migrations/versions/env.py",
            "migrations/versions/__pycache__/0006_x.py",
            "docs/0007_notes.py",
            "migrations/versions/0008_ok.sql",
            mig(9, "second"),
            "migrations/versions/0009_other.py",
        ]
    )
    assert found == {
        5: [mig(5)],
        9: [mig(9, "second"), "migrations/versions/0009_other.py"],
    }


def carried(*pairs: tuple[int, int]) -> list[Any]:
    return [train.Carried(p, n, mig(n, f"from{p}")) for p, n in pairs]


def test_migration_numbers_that_continue_from_the_default_branch_are_accepted() -> None:
    """The positive half, and the empty case. Delete this and a check that refused every train
    carrying a migration would pass the refusals below."""
    assert train.migration_problems({1, 2, 3}, carried((10, 4), (11, 5), (12, 6))) == []
    assert train.migration_problems({1, 2, 3}, []) == []
    assert train.migration_problems(set(), carried((1, 1))) == []


def test_two_pull_requests_carrying_the_same_migration_number_are_refused() -> None:
    """They merge without a git conflict, because the file names differ, and then fail at the first
    `alembic upgrade`. Delete this and that is how the train reaches the server."""
    problems = train.migration_problems({1, 2}, carried((10, 3), (11, 3)))
    assert any("0003" in p and "#10" in p and "#11" in p for p in problems)


def test_a_migration_reusing_a_number_already_on_the_default_branch_is_refused() -> None:
    """Delete this and a pull request opened before another merged carries a number that now
    exists twice, which Alembic reports only when somebody upgrades."""
    problems = train.migration_problems({1, 2, 3}, carried((10, 3)))
    assert any("0003" in p and "already exists" in p for p in problems)


@pytest.mark.parametrize(
    ("main", "pairs", "expected", "found"),
    [
        ({1, 2, 3}, ((10, 5),), "0004", "0005"),  # a gap straight after main's highest
        ({1, 2, 3}, ((10, 4), (11, 6)), "0005", "0006"),  # a gap between two pull requests
    ],
)
def test_a_gap_in_the_migration_numbers_is_refused_and_named(
    main: set[int], pairs: tuple[tuple[int, int], ...], expected: str, found: str
) -> None:
    """The numbers must continue exactly from the default branch's highest. Delete this and a
    pull request whose neighbour was dropped from the train leaves a hole that the next author
    fills with a number that no longer sorts after what is deployed."""
    problems = train.migration_problems(main, carried(*pairs))
    assert any(f"expected {expected}" in p and f"found {found}" in p for p in problems)


def test_a_duplicate_number_that_is_already_on_the_default_branch_is_not_the_trains_fault() -> None:
    """The default branch has had a repeated number before (a second `0095`). The check judges what
    the train adds, so it must not refuse a train for what was there. Delete this and the first
    such duplicate on main blocks every train for ever."""
    assert train.migration_problems({94, 95, 96}, carried((10, 97))) == []


def test_the_description_lists_every_pull_request_and_migration_in_order_and_how_to_merge() -> None:
    """The reader of the train pull request needs the order, the migration numbers, the fact that
    the whole suite runs and that it must not be squashed. Delete this and the description can
    lose any of those and nothing notices."""
    prs = [pr(30), pr(10), pr(20)]
    text = train.body(prs, carried((30, 4), (20, 5)), 3, BASE)
    assert text.index("#30") < text.index("#10") < text.index("#20")
    assert text.index("0004 from #30") < text.index("0005 from #20")
    assert "0003" in text and f"`{BASE}`" in text
    assert "full suite runs" in text and "never a squash" in text and "Auto-merge is off" in text
    assert "None." in train.body(prs, [], 3, BASE)
    assert train.title("train/2999-01-01-1", [30, 10]) == "Merge train 2999-01-01-1: #30, #10"


def test_a_force_flag_a_squash_a_rebase_and_a_plus_refspec_are_forbidden_in_a_git_command() -> None:
    """The three things that rewrite or collapse the history this tool exists to preserve. Delete
    this and a later edit adds one with every other test still green. The sibling shows the
    commands the tool does run are not caught."""
    for bad in ("--force", "-f", "--force-with-lease", "--squash", "--rebase", "--no-verify"):
        assert train.forbidden_in(["merge", bad, "x"]) == bad
    assert train.forbidden_in(["push", "--force-with-lease=trunk:abc"]) == (
        "--force-with-lease=trunk:abc"
    ), "a force flag with a value is not in the list and is still a force flag"
    assert train.forbidden_in(["push", "origin", "+train/x"]) == "+train/x"
    assert train.forbidden_in(["push", "--set-upstream", "origin", "train/x"]) is None
    assert train.forbidden_in(["merge", "--no-ff", "-m", "Merge #1: +fix", "abc"]) is None


def test_the_real_git_wrapper_refuses_a_forbidden_flag_before_running_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard is in the one function that runs git, so no caller can skip it. Delete this and
    the check exists only in a helper nobody has to call."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="--force"):
        train.git(["push", "--force", "origin", "train/x"])
    assert train.git(["--version"]).code == 0


def test_only_a_train_branch_can_be_pushed_and_never_the_default_branch() -> None:
    """Delete this and a bug in naming pushes whatever branch name arrives, `trunk` included, and
    every push to the default branch deploys. The sibling is the one push the tool makes."""
    assert train.push_args("train/2999-01-01-1", "origin", BASE) == [
        "push",
        "--set-upstream",
        "origin",
        "train/2999-01-01-1",
    ]
    for bad in (BASE, "feature/x", "train"):
        with pytest.raises(ValueError, match="only train/"):
            train.push_args(bad, "origin", BASE)
    with pytest.raises(ValueError):
        train.push_args("train/", "origin", "train/")


# ------------------------------------------------------------------ the commands, with fakes


class FakeGh:
    """`gh` as the tool calls it: pull request views, file lists, the repository's settings."""

    def __init__(
        self,
        prs: Sequence[dict[str, Any]],
        files: dict[int, list[tuple[str, str]]] | None = None,
        merge_commits_allowed: bool = True,
    ) -> None:
        self.prs = {int(p["number"]): p for p in prs}
        self.files = files or {}
        self.allowed = merge_commits_allowed
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> str:
        a = list(args)
        self.calls.append(a)
        if a[:2] == ["pr", "view"]:
            return json.dumps(self.prs[int(a[2])])
        if a[0] == "api" and a[1].endswith("/files"):
            number = int(a[1].split("/")[4])
            return "".join(f"{s}\t{f}\n" for s, f in self.files.get(number, []))
        if a[0] == "api" and a[2:3] == ["--jq"]:
            return "true\n" if self.allowed else "false\n"
        if a[:2] == ["pr", "create"]:
            return "https://example.test/pull/900\n"
        msg = f"unexpected gh call {a}"
        raise AssertionError(msg)


class FakeGit:
    """`git` as the tool calls it, recording every command and answering from a script."""

    def __init__(
        self,
        *,
        main_tree: Sequence[str] = (),
        head_tree: Sequence[str] | None = None,
        dirty: str = "",
        branch: str = "work",
        conflict_on: int | None = None,
        conflicted: Sequence[str] = (),
        fail_fetch_of: int | None = None,
        existing_local: Sequence[str] = (),
        existing_remote: Sequence[str] = (),
    ) -> None:
        self.main_tree = list(main_tree)
        self.head_tree = list(head_tree) if head_tree is not None else list(main_tree)
        self.dirty = dirty
        self.branch = branch
        self.conflict_on = conflict_on
        self.conflicted = list(conflicted)
        self.fail_fetch_of = fail_fetch_of
        self.local = list(existing_local)
        self.remote = list(existing_remote)
        self.calls: list[list[str]] = []
        self.fetched = 0

    def __call__(self, args: Sequence[str]) -> Any:
        a = list(args)
        self.calls.append(a)
        ok = train.GitResult
        if a[0] == "fetch" and a[2].startswith("refs/pull/"):
            self.fetched = int(a[2].split("/")[2])
            if self.fetched == self.fail_fetch_of:
                return ok(1, "", "fatal: couldn't find remote ref")
        if a[:2] == ["ls-tree", "-r"]:
            return ok(0, "\n".join(self.head_tree if "HEAD" in a else self.main_tree))
        if a[0] == "status":
            return ok(0, self.dirty)
        if a[:2] == ["rev-parse", "--abbrev-ref"]:
            return ok(0, f"{self.branch}\n")
        if a == ["rev-parse", "FETCH_HEAD"]:
            return ok(0, f"{self.fetched:040d}\n")
        if a == ["rev-parse", "HEAD"]:
            return ok(0, "f" * 40 + "\n")
        if a[0] == "branch" and a[1] == "--list":
            return ok(0, "\n".join(self.local))
        if a[0] == "ls-remote":
            return ok(0, "\n".join(f"{'0' * 40}\trefs/heads/{one}" for one in self.remote))
        if a[0] == "merge" and a[1] == "--no-ff" and self.fetched == self.conflict_on:
            return ok(1, "CONFLICT", "")
        if a[0] == "diff":
            return ok(0, "\n".join(self.conflicted))
        return ok(0, "")

    def verbs(self) -> list[str]:
        return [c[0] for c in self.calls]


def run_tool(
    fake_git: FakeGit,
    fake_gh: FakeGh,
    numbers: Sequence[int],
    *,
    apply: bool,
    base: str = BASE,
) -> tuple[Any, list[str]]:
    said: list[str] = []
    result = train.assemble(
        fake_gh,
        fake_git,
        repo=REPO,
        base=base,
        remote="origin",
        numbers=numbers,
        day=DAY,
        apply=apply,
        say=said.append,
    )
    return result, said


def three() -> FakeGh:
    return FakeGh(
        [pr(30), pr(10), pr(20)],
        {
            30: [("added", mig(4, "a")), ("modified", "src/a.py")],
            10: [("added", mig(5, "b"))],
            20: [("added", "src/new.py")],
        },
    )


def test_a_migration_a_pull_request_only_edits_is_not_a_number_it_carries() -> None:
    """Only added or renamed files bring a number. Delete this and a pull request that edits an
    existing migration is refused as reusing a number already on the default branch. The sibling
    is a renamed file, which does carry one."""
    fake_git = FakeGit(main_tree=[mig(1, "first")])
    edits = FakeGh([pr(1)], {1: [("modified", mig(1, "first")), ("removed", mig(1, "first"))]})
    result, _ = run_tool(fake_git, edits, [1], apply=False)
    assert result.outcome is train.Outcome.DRY_RUN
    renamed = FakeGh([pr(1)], {1: [("renamed", mig(2, "second"))]})
    _, said = run_tool(FakeGit(main_tree=[mig(1, "first")]), renamed, [1], apply=False)
    assert any("0002 (#1)" in line for line in said)


def test_a_dry_run_changes_nothing_and_says_what_it_would_do() -> None:
    """Dry run is the default because the tool writes to a shared remote. Delete this and a flag
    default flipped by an edit creates branches and opens pull requests unasked. The sibling below
    shows the same inputs do act with `apply`."""
    fake_git = FakeGit(main_tree=[mig(1), mig(2), mig(3)])
    fake_gh = three()
    result, said = run_tool(fake_git, fake_gh, [30, 10, 20], apply=False)
    assert result.outcome is train.Outcome.DRY_RUN and result.train == "train/2999-01-01-1"
    assert set(fake_git.verbs()) <= {"fetch", "ls-tree", "branch", "ls-remote"}
    assert all(c[:2] != ["fetch", "origin"] or c[2] == BASE for c in fake_git.calls)
    assert not any(c[:2] == ["pr", "create"] for c in fake_gh.calls)
    assert any("0004 (#30)" in line and "0005 (#10)" in line for line in said)


def test_apply_merges_each_pull_request_with_a_merge_commit_in_the_order_given() -> None:
    """**The exact commands.** The train is created from the default branch, each pull request's
    head is fetched by its pull request ref and merged with `--no-ff` in the order given, the one
    push is the train branch, and one pull request is opened. Delete this and the order, the merge
    commit or the base can change with every other test green."""
    fake_git = FakeGit(
        main_tree=[mig(1), mig(2), mig(3)],
        head_tree=[mig(1), mig(2), mig(3), mig(4, "a"), mig(5, "b")],
    )
    fake_gh = three()
    result, _ = run_tool(fake_git, fake_gh, [30, 10, 20], apply=True)
    assert result.outcome is train.Outcome.PUSHED and result.url == "https://example.test/pull/900"
    name = "train/2999-01-01-1"
    calls = fake_git.calls
    assert ["switch", "--create", name, "--no-track", f"origin/{BASE}"] in calls
    merges = [c for c in calls if c[0] == "merge"]
    assert [c[:2] for c in merges] == [["merge", "--no-ff"]] * 3
    assert [c[-1] for c in merges] == [f"{n:040d}" for n in (30, 10, 20)]
    fetches = [c[2] for c in calls if c[0] == "fetch" and c[2].startswith("refs/pull/")]
    assert fetches == ["refs/pull/30/head", "refs/pull/10/head", "refs/pull/20/head"]
    assert [c for c in calls if c[0] == "push"] == [["push", "--set-upstream", "origin", name]]
    assert calls[-1] == ["switch", "work"], "the checkout goes back to where it was"
    assert not any(c[0] == "branch" and "-D" in c for c in calls), "a pushed train is kept"
    create = next(c for c in fake_gh.calls if c[:2] == ["pr", "create"])
    assert create[create.index("--head") + 1] == name
    assert create[create.index("--base") + 1] == BASE
    assert create[create.index("--title") + 1] == "Merge train 2999-01-01-1: #30, #10, #20"
    assert "0004 from #30" in create[create.index("--body") + 1]


def test_nothing_the_tool_runs_squashes_rebases_forces_merges_or_turns_on_auto_merge() -> None:
    """**The history-protecting properties, over every command of a full run.** Delete this and a
    command that squashes, forces, pushes anything but the train or asks `gh` to merge can be
    added behind a test that only looks at the happy path. The checks are on parsed arguments, not
    on substrings."""
    fake_git = FakeGit(main_tree=[mig(1)], head_tree=[mig(1), mig(2)])
    fake_gh = FakeGh([pr(1), pr(2)], {1: [("added", mig(2))]})
    result, _ = run_tool(fake_git, fake_gh, [1, 2], apply=True)
    assert result.outcome is train.Outcome.PUSHED
    for call in fake_git.calls:
        assert train.forbidden_in(call) is None, call
    for call in fake_gh.calls:
        assert call[:2] != ["pr", "merge"], call
        assert not any("auto" in arg for arg in call), call
    pushes = [c for c in fake_git.calls if c[0] == "push"]
    assert len(pushes) == 1 and pushes[0][-1].startswith("train/") and pushes[0][-1] != BASE


def test_the_default_branch_is_whatever_gh_says_and_is_never_written_into_the_tool() -> None:
    """Delete this and `origin/main` creeps in as a literal and the tool breaks, silently, on the
    first install whose default branch has another name."""
    fake_git = FakeGit(main_tree=[mig(1)], head_tree=[mig(1)])
    run_tool(fake_git, FakeGh([pr(1, baseRefName="develop")]), [1], apply=True, base="develop")
    assert ["switch", "--create", "train/2999-01-01-1", "--no-track", "origin/develop"] in (
        fake_git.calls
    )
    info = json.dumps({"nameWithOwner": "x/y", "defaultBranchRef": {"name": "develop"}})
    assert train.repo_and_base(lambda _args: info) == ("x/y", "develop")


def test_the_first_conflict_stops_the_train_and_leaves_the_checkout_as_it_was() -> None:
    """**Stops at the first conflict, reports the pull request and the files, and cleans up.** The
    merge is aborted, the checkout goes back, the local train branch is deleted, and nothing is
    pushed or opened. Delete this and a conflict leaves the developer in a half-merged branch or,
    worse, pushes it."""
    fake_git = FakeGit(
        main_tree=[mig(1)],
        branch="work",
        conflict_on=10,
        conflicted=["src/shared.py", "docs/a.md"],
    )
    fake_gh = FakeGh([pr(30), pr(10), pr(20)])
    result, _ = run_tool(fake_git, fake_gh, [30, 10, 20], apply=True)
    assert result.outcome is train.Outcome.CONFLICT
    assert "#10" in result.detail and "src/shared.py" in result.detail
    assert "docs/a.md" in result.detail
    calls = fake_git.calls
    assert ["merge", "--abort"] in calls
    assert calls[-2:] == [["switch", "work"], ["branch", "-D", "train/2999-01-01-1"]]
    assert not any(c[0] == "push" for c in calls)
    assert not any(c[:2] == ["pr", "create"] for c in fake_gh.calls)
    assert len([c for c in calls if c[0] == "merge" and c[1] == "--no-ff"]) == 2, (
        "nothing after the conflicting pull request is attempted"
    )


def test_a_checkout_that_was_detached_is_returned_to_the_same_commit() -> None:
    """Delete this and a developer on a detached head is switched to a branch named `HEAD` or left
    on the train."""
    fake_git = FakeGit(main_tree=[mig(1)], branch="HEAD", conflict_on=1)
    result, _ = run_tool(fake_git, FakeGh([pr(1)]), [1], apply=True)
    assert result.outcome is train.Outcome.CONFLICT
    assert ["switch", "--detach", "f" * 40] in fake_git.calls


def test_a_failure_part_way_still_returns_the_checkout_and_drops_the_unpushed_branch() -> None:
    """A fetch that fails is not a conflict, but the branch exists and the checkout is on it.
    Delete this and an error mid-run leaves the developer on a train that was never pushed."""
    fake_git = FakeGit(main_tree=[mig(1)], fail_fetch_of=2)
    with pytest.raises(RuntimeError, match="fetch"):
        run_tool(fake_git, FakeGh([pr(1), pr(2)]), [1, 2], apply=True)
    assert fake_git.calls[-2:] == [["switch", "work"], ["branch", "-D", "train/2999-01-01-1"]]
    assert not any(c[0] == "push" for c in fake_git.calls)


def test_a_dirty_working_tree_is_refused_before_any_branch_is_touched() -> None:
    """Switching branches over local edits is how work is lost. Delete this and the tool does it.
    The sibling is the clean-tree run in the tests above."""
    fake_git = FakeGit(main_tree=[mig(1)], dirty=" M src/a.py\n")
    result, _ = run_tool(fake_git, FakeGh([pr(1)]), [1], apply=True)
    assert result.outcome is train.Outcome.REFUSED and "uncommitted" in result.detail
    assert not any(c[0] in ("switch", "merge", "push") for c in fake_git.calls)


def test_colliding_migration_numbers_refuse_the_train_before_any_merge() -> None:
    """The refusal happens on the pull requests' file lists, so nothing is created or fetched for
    a train that cannot be right. Delete this and the numbers are found only after a branch exists
    and the merges are done, or never."""
    fake_git = FakeGit(main_tree=[mig(1), mig(2)])
    fake_gh = FakeGh(
        [pr(1), pr(2)],
        {1: [("added", mig(3, "a"))], 2: [("added", mig(3, "b"))]},
    )
    result, _ = run_tool(fake_git, fake_gh, [1, 2], apply=True)
    assert result.outcome is train.Outcome.REFUSED and "0003" in result.detail
    assert not any(c[0] in ("switch", "merge", "push") for c in fake_git.calls)


def test_a_duplicate_that_only_appears_in_the_assembled_tree_is_caught_before_the_push() -> None:
    """The second look, at what was actually merged: a number that arrived some way the file lists
    did not show (a rename, a second file in one pull request). Delete this and only the file
    lists are trusted. The branch is dropped and nothing is pushed."""
    fake_git = FakeGit(
        main_tree=[mig(1), mig(2)],
        head_tree=[mig(1), mig(2), mig(3, "a"), mig(3, "b")],
    )
    fake_gh = FakeGh([pr(1)], {1: [("added", mig(3, "a"))]})
    result, _ = run_tool(fake_git, fake_gh, [1], apply=True)
    assert result.outcome is train.Outcome.REFUSED and "after merging" in result.detail
    assert not any(c[0] == "push" for c in fake_git.calls)
    assert fake_git.calls[-1] == ["branch", "-D", "train/2999-01-01-1"]


def test_a_pull_request_that_cannot_ride_a_train_refuses_the_whole_train_and_names_it() -> None:
    """One bad pull request in the list stops all of them rather than building a smaller train
    than was asked for. Delete this and the tool quietly leaves one out."""
    fake_git = FakeGit(main_tree=[mig(1)])
    result, _ = run_tool(fake_git, FakeGh([pr(1), pr(2, isDraft=True)]), [1, 2], apply=True)
    assert result.outcome is train.Outcome.REFUSED and result.detail.startswith("#2:")
    assert fake_git.calls == [], "not even a fetch is made for a list that is refused"


def test_a_repository_that_forbids_merge_commits_is_warned_about_and_the_train_is_still_made() -> (
    None
):
    """A squash-only repository would flatten the train the moment it merged, which is the thing
    to avoid. The tool cannot change that setting, so it says so. Delete this and the first time
    anybody learns is when the trailers are gone from the default branch."""
    fake_git = FakeGit(main_tree=[mig(1)], head_tree=[mig(1)])
    _, said = run_tool(fake_git, FakeGh([pr(1)], merge_commits_allowed=False), [1], apply=False)
    assert any("does not allow merge commits" in line for line in said)
    _, quiet = run_tool(FakeGit(main_tree=[mig(1)]), FakeGh([pr(1)]), [1], apply=False)
    assert not any("merge commits" in line for line in quiet)


def test_trains_already_made_that_day_are_counted_from_the_remote_as_well() -> None:
    """Delete this and a train another developer pushed an hour ago is reused by name and the push
    is refused after all the merging is done."""
    fake_git = FakeGit(
        main_tree=[mig(1)],
        existing_local=["train/2999-01-01-1"],
        existing_remote=["train/2999-01-01-2"],
    )
    result, _ = run_tool(fake_git, FakeGh([pr(1)]), [1], apply=False)
    assert result.train == "train/2999-01-01-3"


# ------------------------------------------------------------------ the entry point


def test_main_refuses_contradictory_flags_and_defaults_to_a_dry_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Delete this and `--apply --dry-run` is accepted with one silently winning, or the default
    flips and a bare invocation writes to the remote."""
    info = json.dumps({"nameWithOwner": REPO, "defaultBranchRef": {"name": BASE}})
    fake_gh = FakeGh([pr(1)])

    def run(args: Sequence[str]) -> str:
        return info if list(args)[:2] == ["repo", "view"] else fake_gh(args)

    fake_git = FakeGit(main_tree=[mig(1)])
    with pytest.raises(SystemExit):
        train.main(["1", "--apply", "--dry-run"], run, fake_git)
    assert train.main(["#1"], run, fake_git) == 0
    assert "dry run" in capsys.readouterr().out
    assert not any(c[0] in ("switch", "merge", "push") for c in fake_git.calls)


def test_main_reports_a_conflict_with_a_failing_status_and_a_clean_run_with_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Delete this and a conflict exits zero, so a script around the tool carries on as if the
    train had been made."""
    info = json.dumps({"nameWithOwner": REPO, "defaultBranchRef": {"name": BASE}})
    fake_gh = FakeGh([pr(1)])

    def run(args: Sequence[str]) -> str:
        return info if list(args)[:2] == ["repo", "view"] else fake_gh(args)

    conflicted = FakeGit(main_tree=[mig(1)], conflict_on=1, conflicted=["a.py"])
    assert train.main(["1", "--apply"], run, conflicted) == 1
    assert "conflict" in capsys.readouterr().out
    clean = FakeGit(main_tree=[mig(1)], head_tree=[mig(1)])
    assert train.main(["1", "--apply"], run, clean) == 0
    assert "https://example.test/pull/900" in capsys.readouterr().out


# ------------------------------------------------------------------ real git, local remote


def sh(cwd: Path, *args: str) -> str:
    done = subprocess.run(  # git with literal arguments, in a temporary repository
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return done.stdout


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A bare remote and a clone of it, on a default branch with one migration."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    sh(tmp_path, "init", "--bare", "-b", BASE, str(remote))
    sh(tmp_path, "init", "-b", BASE, str(work))
    for key, value in (("user.name", "T"), ("user.email", "t@example.test")):
        sh(work, "config", key, value)
    (work / "migrations" / "versions").mkdir(parents=True)
    (work / "migrations" / "versions" / "0001_first.py").write_text("one\n")
    (work / "shared.txt").write_text("base\n")
    sh(work, "add", ".")
    sh(work, "commit", "-m", "base")
    sh(work, "remote", "add", "origin", str(remote))
    sh(work, "push", "origin", BASE)
    return remote, work


def make_pr(work: Path, number: int, files: dict[str, str], message: str) -> None:
    """Make the pull request's head from the default branch and publish it as refs/pull/N/head."""
    sh(work, "switch", "--create", f"pr-{number}", BASE)
    for name, text in files.items():
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    sh(work, "add", ".")
    sh(work, "commit", "-m", message)
    sh(work, "push", "origin", f"pr-{number}:refs/pull/{number}/head")
    sh(work, "switch", BASE)


def real_gh(numbers: Sequence[int]) -> FakeGh:
    return FakeGh(
        [pr(n) for n in numbers],
        {n: [("added", mig(1 + n, f"p{n}"))] for n in numbers if n != 3},
    )


def test_real_git_makes_one_merge_commit_per_pull_request_and_keeps_every_original_commit(
    repository: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The run against real git, not a fake.** Two pull requests become two merge commits in the
    order given, each original commit and its `Closes:` trailer is reachable on the pushed train,
    the default branch on the remote has not moved and the checkout is back on its own branch.
    Delete this and every command above is only ever checked against a fake that agrees with the
    code."""
    remote, work = repository
    make_pr(work, 1, {mig(2, "p1"): "a\n", "one.txt": "1\n"}, "First change\n\nCloses: M1.1.1")
    make_pr(work, 2, {mig(3, "p2"): "b\n", "two.txt": "2\n"}, "Second change\n\nCloses: M1.1.2")
    monkeypatch.chdir(work)
    before = sh(remote, "rev-parse", BASE).strip()
    result = train.assemble(
        real_gh([2, 1]),
        train.git,
        repo=REPO,
        base=BASE,
        remote="origin",
        numbers=[2, 1],
        day=DAY,
        apply=True,
        say=lambda _line: None,
    )
    assert result.outcome is train.Outcome.PUSHED, result.detail
    name = "train/2999-01-01-1"
    assert sh(work, "branch", "--show-current").strip() == BASE
    assert sh(remote, "rev-parse", BASE).strip() == before, "the default branch did not move"
    log = sh(remote, "log", "--format=%s%n%b", name)
    assert "Closes: M1.1.1" in log and "Closes: M1.1.2" in log
    merges = sh(remote, "log", "--merges", "--reverse", "--format=%s", name).splitlines()
    assert [m.split(":")[0] for m in merges] == ["Merge #2", "Merge #1"]
    assert len(sh(remote, "log", "--merges", "--format=%H", name).split()) == 2


def test_real_git_leaves_a_clean_checkout_and_no_branch_after_a_conflict(
    repository: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """**A conflict against real git.** The second pull request edits the line the first did. The
    merge is aborted, `git status` is clean, the checkout is back on its branch, no `train/` branch
    is left locally or on the remote, and the result names the pull request and the file. Delete
    this and the cleanup is only ever a list of commands in a fake."""
    remote, work = repository
    make_pr(work, 1, {"shared.txt": "one\n"}, "First")
    make_pr(work, 3, {"shared.txt": "three\n"}, "Third")
    monkeypatch.chdir(work)
    result = train.assemble(
        real_gh([1, 3]),
        train.git,
        repo=REPO,
        base=BASE,
        remote="origin",
        numbers=[1, 3],
        day=DAY,
        apply=True,
        say=lambda _line: None,
    )
    assert result.outcome is train.Outcome.CONFLICT
    assert "#3" in result.detail and "shared.txt" in result.detail
    assert sh(work, "status", "--porcelain").strip() == ""
    assert sh(work, "branch", "--show-current").strip() == BASE
    assert sh(work, "branch", "--list", "train/*").strip() == ""
    assert sh(remote, "branch", "--list", "train/*").strip() == ""
