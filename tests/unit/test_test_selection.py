"""The test selection and the plan that runs it: what it reaches, that it fails safe, and that
the nightly suite still runs everything.

The selection is switched on for pull requests (2026-10-13) at depth 1. These tests hold what that
depends on: the selection reaches the tests the import graph, the readers of a file and the tree
walkers say it reaches; it falls back to the full suite wherever it cannot be sure; the shards'
shares between them are exactly the selection; a selected run never judges the coverage floor; and
the nightly suite runs every file exactly as a pull request's shards do, with no base commit.

Task ids: none
"""

from __future__ import annotations

import fnmatch
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.ops import test_plan
from brain.ops.test_plan import PLAN_DEPTH, plan
from brain.ops.test_selection import (
    ALWAYS,
    DEPTHS,
    FULL_SUITE,
    MAY_BE_ABSENT,
    failed_files,
    main,
    readers_of,
    record,
    scanners,
    select,
)
from brain.ops.test_shards import ShardError, collected, partition

REPO = Path(__file__).resolve().parents[2]
SUITE = collected()


def workflow(name: str) -> dict[Any, Any]:
    loaded = yaml.safe_load((REPO / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_a_module_selects_the_tests_that_import_it_and_the_invariants_and_no_more() -> None:
    """**The positive half.** Delete this and a selection that returned the full suite every time
    would satisfy the fallbacks below, and the shadow would record savings of nothing."""
    chosen = select(["src/brain/ops/limits.py"], depth=0, suite=SUITE)
    assert not chosen.full
    assert "tests/unit/test_limits.py" in chosen.files
    assert all(one in SUITE for one in chosen.files)
    assert {one for one in SUITE if one.startswith(ALWAYS)} <= set(chosen.files)
    assert len(chosen.files) < len(SUITE)
    wider = select(["src/brain/ops/limits.py"], depth=2, suite=SUITE)
    assert set(chosen.files) <= set(wider.files)


def test_a_changed_test_file_is_selected_itself() -> None:
    """Delete this and a pull request changing only a test would run everything but that test."""
    chosen = select(["tests/unit/test_ci_workflow.py"], depth=0, suite=SUITE)
    assert "tests/unit/test_ci_workflow.py" in chosen.files and not chosen.full


@pytest.mark.parametrize(
    "path",
    [
        "pyproject.toml",
        "uv.lock",
        "tests/conftest.py",
        "tests/fixtures/company.py",
        ".github/workflows/ci.yml",
    ],
)
def test_what_the_graph_cannot_see_runs_the_full_suite(path: str) -> None:
    """A conftest, a fixture, the project settings or the workflow reach every test at once.
    Delete this and a changed conftest would select the handful of files that import it."""
    assert select([path], depth=2, suite=SUITE).full


def test_a_support_module_under_tests_and_an_unknown_diff_run_the_full_suite() -> None:
    """A helper module a test imports is not followed by the source graph, and a diff nobody
    computed is not a small one. Delete this and either reads as a change reaching nothing."""
    # Every helper today is a fixture, which `FULL_SUITE` names; a package marker is the one
    # Python file under tests/ the suite does not collect and no pattern names.
    helper = "tests/unit/__init__.py"
    assert select([helper], depth=0, suite=SUITE).full
    assert select([], depth=0, suite=SUITE).full


@pytest.mark.parametrize("pattern", sorted(set(FULL_SUITE) - MAY_BE_ABSENT))
def test_every_full_suite_pattern_names_a_file_that_exists(pattern: str) -> None:
    """Delete this and a renamed fixture directory or settings file stops forcing the full suite.
    The one pattern allowed to match nothing today is `MAY_BE_ABSENT`'s, with its reason."""
    files = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert any(fnmatch.fnmatchcase(one, pattern) for one in files), pattern


def junit(path: Path, cases: list[tuple[str, str]]) -> Path:
    body = "".join(
        f'<testcase classname="{classname}" name="t">{"" if kind == "pass" else f"<{kind}/>"}'
        "</testcase>"
        for classname, kind in cases
    )
    path.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>", encoding="utf-8")
    return path


def test_a_failure_outside_the_selection_is_recorded_as_a_miss(tmp_path: Path) -> None:
    """**The measurement.** A failed file the selection left out is a miss at that depth, and one
    inside it is not. Delete this and the week's record could say "no miss" about failures it
    never compared."""
    report = junit(
        tmp_path / "shard-1.xml",
        [
            ("tests.unit.test_limits", "failure"),
            ("tests.unit.test_status.TestSomething", "error"),
            ("tests.unit.test_compose", "pass"),
        ],
    )
    failed = failed_files([report])
    assert failed == {"tests/unit/test_limits.py", "tests/unit/test_status.py"}
    made = record(["src/brain/ops/limits.py"], failed, SUITE)
    missed = {row["depth"]: row["missed"] for row in made["depths"]}  # type: ignore[attr-defined]
    assert "tests/unit/test_limits.py" not in missed[0]
    assert "tests/unit/test_status.py" in missed[0]
    assert made["would_have_missed"] == {str(d): bool(missed[d]) for d in DEPTHS}


def test_the_shadow_writes_its_record_and_never_fails(tmp_path: Path) -> None:
    """Delete this and a shadow that exits non-zero on a miss could fail a pull request over a
    decision it was built not to make."""
    reports = tmp_path / "junit"
    reports.mkdir()
    junit(reports / "shard-1.xml", [("tests.unit.test_status", "failure")])
    out = tmp_path / "evidence" / "record.json"
    assert main(["--base", "", "--junit", str(reports), "--record", str(out)]) == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["failed"] == ["tests/unit/test_status.py"]
    assert written["would_have_missed"] == dict.fromkeys(map(str, DEPTHS), False)


SHARDS = 8


def _live(step: dict[Any, Any]) -> str:
    return "\n".join(
        line for line in str(step.get("run", "")).splitlines() if not line.strip().startswith("#")
    )


def _shard_step(job: dict[Any, Any]) -> dict[Any, Any]:
    return next(one for one in job["steps"] if "brain.ops.test_plan" in str(one.get("run", "")))


def test_the_selection_depth_is_the_conservative_one_the_record_measured() -> None:
    """Depths 0, 1 and 2 all missed nothing in the seven records; one is the middle, and a
    selection at depth 0 is a subset of it. Delete this and the plan can be narrowed to the
    module's own importers, or widened past what was measured, with every other test green."""
    assert PLAN_DEPTH == 1 and PLAN_DEPTH in DEPTHS
    shallow = select(["src/brain/ops/limits.py"], depth=0, suite=SUITE)
    chosen = select(["src/brain/ops/limits.py"], depth=PLAN_DEPTH, suite=SUITE)
    assert set(shallow.files) <= set(chosen.files) and not chosen.full


def test_a_changed_document_selects_the_tests_that_name_its_directory() -> None:
    """The import graph cannot see a test that reads `docs/architecture.html`, so a changed file
    that is not a source module selects the tests naming its directory. Delete this and a pull
    request that changes only a document merges green over the test that reads it, and the
    nightly is the first thing to say so."""
    readers = readers_of("docs/architecture.html", SUITE)
    assert "tests/unit/test_architecture_doc.py" in readers
    chosen = select(["docs/architecture.html"], depth=PLAN_DEPTH, suite=SUITE)
    assert readers <= set(chosen.files) and not chosen.full
    assert len(chosen.files) < len(SUITE)


def test_a_source_change_also_selects_the_tests_that_walk_the_tree() -> None:
    """A test that refuses a shape anywhere under `src/brain` is linked to no module by an
    import. Delete this and a new function with a forbidden name passes every selected file
    and fails only the night after it merges."""
    walkers = scanners(SUITE)
    assert "tests/unit/test_installation.py" in walkers
    chosen = select(["src/brain/ops/limits.py"], depth=PLAN_DEPTH, suite=SUITE)
    assert walkers <= set(chosen.files)
    only_a_test = select(["tests/unit/test_limits.py"], depth=PLAN_DEPTH, suite=SUITE)
    assert not walkers <= set(only_a_test.files)


def test_a_deleted_source_module_runs_the_full_suite() -> None:
    """The graph is read from files that exist, so a removed module has no importers to ask and
    an importer the diff did not touch is the test that breaks. Delete this and removing a
    module selects nothing but the invariants. The sibling shows a deleted test does not."""
    assert select(["src/brain/ops/no_such_module_anywhere.py"], depth=1, suite=SUITE).full
    assert not select(["tests/unit/test_no_such_test_anywhere.py"], depth=1, suite=SUITE).full


def test_the_shares_between_them_are_exactly_the_selection_and_the_full_suite_in_full() -> None:
    """**The property that makes a split safe, for a selection.** Every selected file in
    exactly one share, none outside it; and with nothing selected-against, every file. Delete
    this and a partition bug drops a selected file from every shard, with every shard green."""
    changed = ["src/brain/ops/limits.py"]
    shares = [plan(n, SHARDS, base="x", head="HEAD", changed=changed) for n in range(1, SHARDS + 1)]
    listed = [name for one in shares for name in one.files]
    expected = select(changed, depth=PLAN_DEPTH, suite=SUITE).files
    assert not any(one.full for one in shares)
    assert sorted(listed) == sorted(expected) and len(listed) == len(set(listed))
    assert 0 < len(listed) < len(SUITE)
    whole = [plan(n, SHARDS, base="", head="HEAD") for n in range(1, SHARDS + 1)]
    assert all(one.full for one in whole)
    assert sorted(name for one in whole for name in one.files) == sorted(SUITE)


@pytest.mark.parametrize(
    "base",
    ["", "0000000000000000000000000000000000000000", "deadbeef" * 5],
)
def test_a_missing_or_unknown_base_commit_runs_the_whole_share(base: str) -> None:
    """Fail safe, first way: the base cannot be established (a push, a shallow clone, a force
    push that moved it). Delete this and such a run selects nothing, or crashes. The positive
    sibling is the test above, where a known diff selects fewer files than the suite."""
    made = plan(1, SHARDS, base=base, head="HEAD")
    assert made.full and made.files


def test_an_empty_diff_and_a_diff_the_graph_cannot_see_run_the_whole_share() -> None:
    """Fail safe, second and third ways: nothing to select from, and a conftest-like change.
    Delete this and an empty diff is read as a change that reaches no test."""
    assert plan(1, SHARDS, base="x", head="HEAD", changed=[]).full
    assert plan(2, SHARDS, base="x", head="HEAD", changed=["pyproject.toml"]).full


def test_an_error_in_the_selection_runs_the_whole_share_and_says_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail safe, last way: the planner raises. It must neither fail the pull request's tests
    nor run none of them. Delete this and a bug in `covering_tests` turns into a red shard on
    every pull request, or into a green one that ran nothing."""

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the graph fell over")

    monkeypatch.setattr(test_plan, "select", broken)
    made = plan(1, SHARDS, base="x", head="HEAD", changed=["src/brain/ops/limits.py"])
    assert made.full and made.files and "RuntimeError" in made.reason


def test_a_shard_with_nothing_selected_is_an_empty_pass_and_the_suite_never_is() -> None:
    """A selection may leave a shard empty and then nothing is run; the whole suite may not,
    because pytest given no file runs everything. Delete this and eight shards fail with "has no
    test files" the day the always-run set is narrowed, or the refusal for the full suite goes."""
    groups = partition({"a.py": 1, "b.py": 1}, 4, allow_empty=True)
    assert sorted(len(one) for one in groups) == [0, 0, 1, 1]
    with pytest.raises(ShardError):
        partition({"a.py": 1, "b.py": 1}, 4)
    step = _live(_shard_step(workflow("ci.yml")["jobs"]["tests"]))
    assert "has nothing to run" in step and "grep -q '^mode=selected$'" in step
    assert 'echo "ran=false"' in step and "exit 0" in step


def test_every_selected_run_gives_every_shard_a_file() -> None:
    """The invariants directory is always selected and has more files than there are shards, so
    no shard of a selection is empty today. Delete this and narrowing `ALWAYS` silently makes
    shards empty, which the workflow handles but which wastes a runner for each."""
    always = [one for one in SUITE if one.startswith(ALWAYS)]
    assert len(always) >= SHARDS
    smallest = select(["README.md"], depth=PLAN_DEPTH, suite=SUITE)
    assert not smallest.full
    for number in range(1, SHARDS + 1):
        assert plan(number, SHARDS, base="x", head="HEAD", changed=["README.md"]).files


def test_the_shard_job_selects_for_a_pull_request_and_falls_back_to_the_whole_share() -> None:
    """The workflow half. The job knows the pull request's base, the step asks the plan and, when
    the plan cannot run, asks `test_shards` for the whole share. Delete this and the switch can
    be turned off by an edit that still looks like it selects, or the fallback can be dropped so
    a planner failure fails every pull request."""
    job = workflow("ci.yml")["jobs"]["tests"]
    assert job["env"]["TEST_SELECTION_BASE"] == "${{ github.event.pull_request.base.sha }}"
    step = _live(_shard_step(job))
    assert '--base "$TEST_SELECTION_BASE" --head "$GITHUB_SHA"' in step
    assert "|| {" in step and "brain.ops.test_shards" in step
    assert 'echo "mode=full" > "$mode_file"' in step
    names = {str(one.get("with", {}).get("name", "")) for one in job["steps"]}
    assert "plan-shard-${{ matrix.shard }}" in names


def test_the_shadow_job_is_retired_because_a_selected_run_cannot_observe_a_miss() -> None:
    """Once a shard runs only the selected files a failure outside them is never seen, so the
    shadow could only say "no miss". The nightly is the measurement now. Delete this and the job
    can come back as a runner spent on a number that cannot be anything but zero."""
    jobs = workflow("ci.yml")["jobs"]
    assert "selection_shadow" not in jobs
    assert not [
        name
        for name, job in jobs.items()
        if "selection_shadow"
        in ([job["needs"]] if isinstance(job.get("needs"), str) else job.get("needs", []))
    ]
    assert not [
        one for one in jobs["tests"]["steps"] if "junit" in str(one.get("with", {}).get("name", ""))
    ]


def test_a_selected_run_never_judges_the_coverage_floor_and_a_full_one_always_does() -> None:
    """A selected run covers a fraction of the code, so the floor is held only when every shard's
    plan says full, never inferred from a missing file, and the floor step reads the data of every
    shard that ran. Delete this and either every small change fails the floor, or a selected run
    passes it by skipping it, and no job is left holding the floor."""
    job = workflow("ci.yml")["jobs"]["coverage"]
    assert job["name"] == "Unit tests and coverage"
    steps = {str(one.get("name", one.get("uses", ""))): one for one in job["steps"]}
    decide = _live(steps["Did every shard run the whole suite"])
    assert "no shard left a plan" in decide and "grep -lx 'mode=full'" in decide
    floor = steps["Coverage floor over the whole suite"]
    assert floor["if"] == "${{ steps.mode.outputs.full == 'true' }}"
    assert "uv run coverage report" in floor["run"]
    assert "--fail-under" not in floor["run"]


def test_the_nightly_suite_is_the_pull_requests_shards_with_no_base_and_holds_the_floor() -> None:
    """The floor under the selection: every file every night, the same steps as the shards, no
    base commit (so the plan is the whole suite), and the coverage floor judged over all of it.
    Delete this and the nightly can drift from the shards, start selecting, skip the floor, or
    deploy: Deploy listens for CI, and this workflow must never be CI."""
    ci, nightly = workflow("ci.yml"), workflow("nightly-suite.yml")
    assert nightly["name"] != ci["name"] == "CI"
    ours, theirs = nightly["jobs"]["tests"], ci["jobs"]["tests"]
    assert ours["steps"] == theirs["steps"]
    assert ours["strategy"] == theirs["strategy"] and ours["services"] == theirs["services"]
    assert "TEST_SELECTION_BASE" in theirs["env"] and "TEST_SELECTION_BASE" not in ours["env"]
    assert {k: v for k, v in theirs["env"].items() if k != "TEST_SELECTION_BASE"} == ours["env"]
    assert "needs" not in ours and "if" not in ours
    assert nightly[True]["schedule"]
    floor = nightly["jobs"]["coverage"]
    assert floor["name"] == "Unit tests and coverage" and floor["needs"] == "tests"
    body = "\n".join(str(one.get("run", "")) for one in floor["steps"])
    assert "uv run coverage report" in body and "--fail-under" not in body
    assert "grep -lx 'mode=full'" in body and "exit 1" in body
