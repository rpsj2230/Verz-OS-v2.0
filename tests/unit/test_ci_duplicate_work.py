"""What CI repeats between a pull request and main, and what keeps a burst of merges safe.

Measured on 2026-10-14 over the last runs, so the argument has numbers under it. A pull request
runs 21 to 24 jobs: 56 job-minutes when the selection picks the files its diff reaches, 127 to
222 when it falls back to the whole suite. A run on main is 8 jobs and about 12 job-minutes, 7 to
15 minutes of wall clock, because main already runs only what a deploy depends on (the unit
shards, the console, the handover, the scans and the coverage floor are pull-request-only since
2026-09-28). So the duplicate work between the two is the eight gates below, and **nothing
heavier can be reclaimed by reusing the pull request's result**, which was the first idea and is
refused in `ops/DEPLOY.md`: main's gates read two inputs the pull request's tree does not carry
(`previous_release` tests the build before this change, which is `github.event.before` on main
and the pull request's base on a pull request, and `sweeps` and `docs` read the `Closes:`
trailers of the squash commit's own message), and with `strict: false` on the branch protection
only 10 of the last 60 merges had a tree identical to what their pull request ran.

What is left to hold is the part that makes a burst of merges safe: the run on main that is
never cancelled, so the newest commit is always checked and deployed, and the one publish at a
time, so `:latest` cannot end on an older commit than main's tip.

Each test reads the parsed workflow, never a substring of it, because a commented-out line keeps
every word it had.

Task ids: none
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]

#: The jobs a push to main runs. Eight, measured at about 12 job-minutes and 7 to 15 minutes of
#: wall clock on 2026-10-14. A new job on main is a deliberate decision, because every one of
#: them is on the path to a deploy and the free plan runs 20 jobs at a time.
THE_JOBS_MAIN_RUNS = frozenset(
    {
        "changes",
        "static",
        "sweeps",
        "docs",
        "install",
        "stack",
        "migrations_install_shaped",
        "previous_release",
    }
)

MAIN = "refs/heads/main"
A_PULL_REQUEST = "refs/pull/585/merge"
A_FEATURE_BRANCH = "refs/heads/M38/ci-reuse-on-main"


def _workflow(name: str) -> dict[Any, Any]:
    parsed: dict[Any, Any] = yaml.safe_load(
        (REPO / ".github" / "workflows" / name).read_text(encoding="utf-8")
    )
    return parsed


def _needs(job: dict[str, Any]) -> list[str]:
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else list(needs)


def _runs_on_main(jobs: dict[str, Any], name: str) -> bool:
    """Whether a push to main can run this job: no pull-request-only condition on it or on any
    job it needs. A job whose dependency is skipped is skipped, so the chain counts."""
    condition = str(jobs[name].get("if", ""))
    if "github.event_name == 'pull_request'" in condition:
        return False
    return all(_runs_on_main(jobs, parent) for parent in _needs(jobs[name]))


def _cancels(expression: object, ref: str) -> bool:
    """What `cancel-in-progress` means for a run on `ref`.

    The workflow writes either a boolean or the one expression `${{ github.ref != '<ref>' }}`
    (or `==`). Anything else is refused rather than guessed at, so a cleverer expression fails
    this test and makes somebody extend it on purpose.
    """
    if isinstance(expression, bool):
        return expression
    found = re.fullmatch(r"\$\{\{ github\.ref (!=|==) '([^']+)' \}\}", str(expression))
    assert found is not None, (
        f"cancel-in-progress is an expression this test cannot read: {expression!r}"
    )
    same = ref == found.group(2)
    return same if found.group(1) == "==" else not same


def _expressions(group: object) -> list[str]:
    """The `${{ }}` expressions in a concurrency group name, in order."""
    return re.findall(r"\$\{\{\s*([^}]+?)\s*\}\}", str(group))


def test_a_push_to_main_runs_only_the_eight_jobs_a_deploy_depends_on() -> None:
    """The cost of main is its job list. A heavy job added to main without a pull-request-only
    condition doubles CI again, and on the free plan's 20 concurrent jobs that queues every
    deploy behind pull requests, which is what main's trim on 2026-09-28 removed.

    Delete this and the unit shards, the console or the handover can drift back onto main with
    every other test green, because the existing test in `test_ci_workflow.py` that guards main's
    trim names the jobs it expects to be absent and not the whole set that is present."""
    jobs = _workflow("ci.yml")["jobs"]
    assert {name for name in jobs if _runs_on_main(jobs, name)} == THE_JOBS_MAIN_RUNS


def test_a_job_that_runs_only_on_pull_requests_is_recognised_as_not_running_on_main() -> None:
    """The positive and negative cases of the reader above, so the set test cannot pass by the
    reader answering one way for everything.

    Delete this and `_runs_on_main` can be broken to say False (or True) for every job, which
    makes the set test above fail or pass for a reason that has nothing to do with the workflow."""
    jobs = _workflow("ci.yml")["jobs"]
    assert _runs_on_main(jobs, "static")
    assert _runs_on_main(jobs, "sweeps"), "a job that needs a main job also runs on main"
    assert not _runs_on_main(jobs, "tests")
    assert not _runs_on_main(jobs, "coverage")
    assert not _runs_on_main(jobs, "branch_name")


def test_a_run_on_main_is_never_cancelled_by_a_newer_one() -> None:
    """The newest commit on main must always be checked, and so deployed. With a run cancelled by
    every newer merge, a burst of auto-merges spaced closer than a run is long cancels each in
    turn and nothing finishes, so nothing deploys until the burst ends (measured 2026-09-28).
    GitHub already keeps one run going and only the newest waiting, which collapses a burst to
    the running commit and the latest, and the latest is never skipped.

    Delete this and `cancel-in-progress` can be made true everywhere, which looks like the
    saving it is and is the starvation above."""
    cancel = _workflow("ci.yml")["concurrency"]["cancel-in-progress"]
    assert not _cancels(cancel, MAIN)


def test_a_superseded_pull_request_run_is_cancelled_and_a_feature_branch_is_too() -> None:
    """The saving that costs nothing: pushing again to a pull request cancels its older run,
    because nobody merges the older one. The sibling of the test above, so a guard that never
    cancels anything cannot pass both.

    Delete this and the `cancel-in-progress` expression can be set false everywhere, so every
    push to a pull request branch runs its whole 56 to 222 job-minutes to completion for a
    result nobody reads."""
    cancel = _workflow("ci.yml")["concurrency"]["cancel-in-progress"]
    assert _cancels(cancel, A_PULL_REQUEST)
    assert _cancels(cancel, A_FEATURE_BRANCH)


def test_ci_runs_are_grouped_by_the_ref_they_ran_on() -> None:
    """The group is the workflow and the ref, so a pull request's runs queue against each other
    and never against main's, and two pull requests never cancel one another.

    Delete this and a constant group is a one-line change that makes every pull request cancel
    every other pull request and main."""
    assert _expressions(_workflow("ci.yml")["concurrency"]["group"]) == [
        "github.workflow",
        "github.ref",
    ]


def test_only_one_publish_moves_the_latest_tag_at_a_time() -> None:
    """Every green CI run on main starts a Deploy of its own commit, and the server pulls
    `:latest`. A code commit followed by a task-list commit gives two CI runs a minute apart (the
    second takes under one) and two builds of two minutes each, so without a shared group they
    run together and `:latest` ends on whichever finishes last, which can be the older commit.

    Delete this and the group can be removed or keyed by the commit (a group per commit
    serialises nothing), and the server can end on an older image than main's tip with every
    check green until the tip's own live check times out eight minutes later."""
    build = _workflow("deploy.yml")["jobs"]["build"]
    concurrency = build["concurrency"]
    assert not _expressions(concurrency["group"]), (
        "a group built from a commit, run or time is a group of one, and serialises nothing"
    )
    assert str(concurrency["group"]).strip()


def test_a_publish_in_progress_is_never_cancelled() -> None:
    """A build stopped between pushing the image and signing it leaves an unsigned image under
    `:latest`, which the server then pulls. Waiting is the safe way to be superseded: GitHub keeps
    one build running and only the newest waiting, so a burst still publishes only its newest
    commit after the one already running.

    Delete this and `cancel-in-progress: true` is a plausible tidy-up of the group above, which
    is the unsigned image."""
    concurrency = _workflow("deploy.yml")["jobs"]["build"]["concurrency"]
    assert concurrency["cancel-in-progress"] is False


def test_no_deploy_job_other_than_the_publish_is_serialised_or_cancelled() -> None:
    """The live check and the staging checks wait up to eight and ten minutes for the server and
    each belongs to one commit, so they must not queue behind the next commit's publish, and no
    group anywhere in the workflow may cancel a run.

    Delete this and a workflow-level group (which would hold the live check of one commit behind
    the whole of the next) or a cancelling group can be added beside the publish's."""
    deploy = _workflow("deploy.yml")
    assert "concurrency" not in deploy
    for name, job in deploy["jobs"].items():
        if name == "build":
            continue
        assert "concurrency" not in job, name


def test_a_deploy_is_started_only_by_a_finished_ci_run_on_main() -> None:
    """The trigger the serialisation above is written for, and the gate it leaves alone: Deploy
    listens for CI completing on main and the publish runs only on a success.

    Delete this and the trigger can be widened to every branch, or the success condition dropped,
    with the concurrency tests still green, and a red CI reaches the server."""
    deploy = _workflow("deploy.yml")
    trigger = deploy[True]["workflow_run"]
    assert trigger["workflows"] == ["CI"]
    assert trigger["branches"] == ["main"]
    assert trigger["types"] == ["completed"]
    condition = str(deploy["jobs"]["build"]["if"])
    assert "github.event.workflow_run.conclusion == 'success'" in condition
