"""The decision logic of `ops/dev/keep_prs_fresh.py`, and the one place it is allowed to write.

The tool updates other people's branches, so the properties worth pinning are the refusals (what
it will never touch) and the single positive case (a behind, clean branch is updated), because
a policy tested only by its refusals is satisfied by one that refuses everything.

The script lives under `ops/dev`, which is not a package, so it is loaded by path.

Task ids: none, developer tooling.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "ops" / "dev" / "keep_prs_fresh.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("keep_prs_fresh_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses and enums look the module up by name
    spec.loader.exec_module(module)
    return module


fresh = load()
BASE = "trunk"


def pr(number: int = 1, **over: Any) -> dict[str, Any]:
    """A pull request as `gh pr list --json` prints it: open, clean, in this repository."""
    base: dict[str, Any] = {
        "number": number,
        "title": "A change",
        "body": "What it does.",
        "isDraft": False,
        "isCrossRepository": False,
        "labels": [],
        "headRefName": f"M1/branch-{number}",
        "headRefOid": f"{number:040d}",
        "baseRefName": BASE,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "BLOCKED",
        "files": [{"path": "a.py"}],
        "url": f"https://example.test/pull/{number}",
    }
    base.update(over)
    return base


def decide(
    p: dict[str, Any], behind_by: int | None = 3, files: frozenset[str] = frozenset()
) -> Any:
    return fresh.decide(p, base=BASE, behind_by=behind_by, base_files=files)


# ------------------------------------------------------------------ the positive case


def test_a_branch_that_is_behind_and_merges_cleanly_is_updated() -> None:
    """The one case the tool exists for.

    If deleted, a policy that skips everything (and so fixes nothing) is green on every refusal
    test below.
    """
    d = decide(pr(), behind_by=3)
    assert d.action is fresh.Action.UPDATE
    assert d.number == 1


def test_a_branch_that_is_up_to_date_is_left_alone() -> None:
    """A branch with nothing to merge must not get an empty merge commit and a fresh CI run.

    If deleted, updating at behind_by == 0 (or any non-positive) is unnoticed and every pass of
    the loop would push to every branch.
    """
    assert decide(pr(), behind_by=0).action is fresh.Action.SKIP
    assert decide(pr(), behind_by=-1).action is fresh.Action.SKIP


# ------------------------------------------------------------------ what it never touches


@pytest.mark.parametrize(
    "over",
    [
        {"isDraft": True},
        {"isCrossRepository": True},
        {"baseRefName": "elsewhere"},
        {"labels": [{"name": "hold"}]},
        {"labels": [{"name": "Hold"}]},
        {"labels": [{"name": " hold "}]},
        {"title": "Do not update this branch"},
        {"body": "Please DO-NOT-UPDATE while I rebase locally"},
        {"body": "do_not_update"},
    ],
)
def test_a_pull_request_that_must_not_be_touched_is_never_updated(over: dict[str, Any]) -> None:
    """Draft, fork, wrong target, hold label and an opt-out in the text each refuse an update.

    If deleted, any one of these guards can be removed and the tool pushes a merge commit into
    a branch somebody asked it to leave alone, which they find out when their push is rejected.
    """
    d = decide(pr(**over), behind_by=5)
    assert d.action is fresh.Action.SKIP
    assert fresh.refusal(pr(**over), BASE) is not None


def test_a_forbidden_pull_request_is_not_reported_as_a_conflict_either() -> None:
    """A held branch that conflicts is skipped, not listed, so the report is only actionable items.

    If deleted, the refusal can be moved after the conflict check and held branches start
    appearing in the conflict report, which is noise that teaches people to ignore it.
    """
    d = decide(pr(labels=[{"name": "hold"}], mergeable="CONFLICTING"))
    assert d.action is fresh.Action.SKIP


def test_an_unrelated_label_does_not_hold_a_pull_request() -> None:
    """Labels other than hold are ignored, and a title that merely mentions updating is fine.

    If deleted, the hold check can be widened to any label or to the word update and nothing
    notices, which would silently exempt most of the open pull requests.
    """
    p = pr(labels=[{"name": "bug"}, {"name": "needs-review"}], title="Update the docs")
    assert decide(p).action is fresh.Action.UPDATE


# ------------------------------------------------------------------ conflicts and unknowns


def test_a_conflicting_branch_is_reported_with_the_files_both_sides_changed() -> None:
    """A conflict is named, with the overlap of the two file lists, and never updated.

    If deleted, a conflicting branch could be sent to update-branch (which GitHub refuses, with
    noise) or reported with no files, leaving the person to find the overlap themselves.
    """
    p = pr(mergeable="CONFLICTING", files=[{"path": "a.py"}, {"path": "b.py"}, {"path": "c.py"}])
    d = decide(p, behind_by=4, files=frozenset({"b.py", "c.py", "z.py"}))
    assert d.action is fresh.Action.REPORT
    assert d.files == ("b.py", "c.py")


def test_a_conflict_is_reported_even_when_how_far_behind_is_unknown() -> None:
    """The conflict does not depend on the comparison call succeeding.

    If deleted, a failed comparison silences the very report the tool is for.
    """
    d = decide(pr(mergeable="CONFLICTING"), behind_by=None)
    assert d.action is fresh.Action.REPORT
    assert d.files == ()


def test_a_pull_request_whose_mergeability_is_not_yet_known_is_skipped() -> None:
    """GitHub computes mergeability lazily; UNKNOWN must wait for the next pass, not be updated.

    If deleted, updating on anything other than an explicit MERGEABLE is unnoticed, and a branch
    that is about to be found conflicting is sent an update.
    """
    assert decide(pr(mergeable="UNKNOWN")).action is fresh.Action.SKIP
    assert decide(pr(mergeable="")).action is fresh.Action.SKIP


def test_a_branch_whose_distance_cannot_be_found_is_skipped_not_updated() -> None:
    """Without a measured behind_by the tool does not guess.

    If deleted, treating None as behind updates every branch whenever the comparison call fails.
    """
    assert decide(pr(), behind_by=None).action is fresh.Action.SKIP


# ------------------------------------------------------------------ the cap


def decisions(n: int) -> list[Any]:
    return [fresh.Decision(i, fresh.Action.UPDATE, "behind") for i in range(n, 0, -1)]


def test_only_the_lowest_numbered_updates_are_made_and_the_rest_are_deferred() -> None:
    """The cap bounds how many CI runs one pass starts, taking the oldest first.

    If deleted, the cap can be removed or reversed and thirty branches are updated at once,
    queueing the CI that the update was meant to speed up, or the newest are always chosen and
    the oldest starve.
    """
    planned = fresh.plan(decisions(5), 2)
    assert [(d.number, d.action) for d in planned] == [
        (1, fresh.Action.UPDATE),
        (2, fresh.Action.UPDATE),
        (3, fresh.Action.DEFERRED),
        (4, fresh.Action.DEFERRED),
        (5, fresh.Action.DEFERRED),
    ]


def test_the_cap_counts_updates_and_not_skips_or_reports() -> None:
    """A pass full of skips and conflicts still makes its updates.

    If deleted, counting every decision against the cap means one conflicting branch with a low
    number uses the pass's allowance and nothing is ever updated.
    """
    mixed = [
        fresh.Decision(1, fresh.Action.REPORT, "conflict"),
        fresh.Decision(2, fresh.Action.SKIP, "draft"),
        fresh.Decision(3, fresh.Action.UPDATE, "behind"),
    ]
    planned = fresh.plan(mixed, 1)
    assert [d.action for d in planned] == [
        fresh.Action.REPORT,
        fresh.Action.SKIP,
        fresh.Action.UPDATE,
    ]


# ------------------------------------------------------------------ what is actually run


class FakeGh:
    """Stands in for `gh`: answers the listing and the comparison, and records every write."""

    def __init__(self, prs: list[dict[str, Any]], behind: dict[str, int]) -> None:
        self.prs = prs
        self.behind = behind
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, args: Sequence[str]) -> str:
        self.calls.append(tuple(args))
        if args[:2] == ["pr", "list"]:
            return json.dumps(self.prs)
        if args[0] == "api":
            oid = args[1].split("/compare/")[1].split("...")[0]
            return json.dumps({"ahead_by": self.behind[oid], "files": [{"filename": "a.py"}]})
        if args[:2] == ["pr", "update-branch"]:
            return ""
        if args[:2] == ["repo", "view"]:
            return json.dumps({"nameWithOwner": "o/r", "defaultBranchRef": {"name": BASE}})
        msg = f"unexpected gh call {args}"
        raise AssertionError(msg)

    def writes(self) -> list[tuple[str, ...]]:
        return [c for c in self.calls if c[:2] == ("pr", "update-branch")]


def fleet() -> FakeGh:
    stale = pr(1)
    conflicted = pr(2, mergeable="CONFLICTING")
    held = pr(3, labels=[{"name": "hold"}])
    return FakeGh([stale, conflicted, held], {stale["headRefOid"]: 2, conflicted["headRefOid"]: 2})


def test_a_dry_run_changes_nothing_and_says_what_it_would_do(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The default pass makes no update-branch call at all.

    If deleted, the dry run can start writing and the first person to try the tool out finds
    their branches changed.
    """
    gh = fleet()
    fresh.one_pass(gh, "o/r", BASE, apply=False, max_updates=3)
    assert gh.writes() == []
    assert "#1: would update" in capsys.readouterr().out


def test_apply_updates_only_the_clean_stale_branch_with_a_merge_not_a_rebase() -> None:
    """With --apply exactly the clean stale branch is updated, and the call has no rebase flag.

    If deleted, the conflicting or held branch could be sent an update, or --rebase added (which
    rewrites the author's commits), and nothing in the policy tests above would notice because
    they never look at the command that is run.
    """
    gh = fleet()
    fresh.one_pass(gh, "o/r", BASE, apply=True, max_updates=3)
    assert gh.writes() == [("pr", "update-branch", "1", "--repo", "o/r")]


def test_a_refused_update_is_reported_and_the_pass_carries_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One branch GitHub will not update must not stop the others being updated.

    If deleted, a single refusal raises out of the pass and every later branch stays stale.
    """
    a, b = pr(1), pr(2)
    gh = FakeGh([a, b], {a["headRefOid"]: 1, b["headRefOid"]: 1})
    inner = gh.__call__

    def refuse_first(args: Sequence[str]) -> str:
        if args[:3] == ["pr", "update-branch", "1"]:
            gh.calls.append(tuple(args))
            msg = "gh pr update-branch failed: not allowed"
            raise RuntimeError(msg)
        return inner(args)

    fresh.one_pass(refuse_first, "o/r", BASE, apply=True, max_updates=3)
    assert ("pr", "update-branch", "2", "--repo", "o/r") in gh.calls
    assert "#1: update refused" in capsys.readouterr().out


def test_the_repository_and_branch_are_read_from_gh_not_written_in_the_source() -> None:
    """The tool names no repository and no default branch of its own.

    If deleted, a hard-coded repository can be added and the tool quietly acts on one project
    wherever it is run, which is the company-details rule this repository forbids.
    """
    assert fresh.repo_and_base(fleet()) == ("o/r", BASE)


def test_main_refuses_contradictory_flags() -> None:
    """--apply with --dry-run is an error, not a coin toss.

    If deleted, a script wrapping the tool that passes both gets whichever wins by accident.
    """
    with pytest.raises(SystemExit):
        fresh.main(["--apply", "--dry-run"], run=fleet())


def test_main_defaults_to_a_dry_run() -> None:
    """With no flags nothing is written.

    If deleted, the default can flip to applying and the tool becomes dangerous to run bare.
    """
    gh = fleet()
    assert fresh.main([], run=gh) == 0
    assert gh.writes() == []


def test_a_default_pass_updates_at_most_three_branches() -> None:
    """With no cap given, five stale branches get three updates, the oldest three.

    The figure is held against behaviour rather than against the constant, because a test
    comparing the constant with itself passes for every value it could hold. If deleted, the
    default can be raised to any number and the CI queue the cap exists to protect fills.
    """
    stale = [pr(n) for n in range(1, 6)]
    gh = FakeGh(stale, {p["headRefOid"]: 1 for p in stale})
    assert fresh.main(["--apply"], run=gh) == 0
    assert [c[2] for c in gh.writes()] == ["1", "2", "3"]
