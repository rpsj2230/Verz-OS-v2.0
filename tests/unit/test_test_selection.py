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

from brain.ops import test_plan, test_selection
from brain.ops.test_plan import PLAN_DEPTH, WHOLE_SUITE_REQUESTED, plan
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
    scoped_tests,
    select,
    support_readers,
)
from brain.ops.test_shards import ShardError, collected, partition, units_run
from brain.ops.test_timings import units

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


@pytest.mark.parametrize("path", ["pyproject.toml", "uv.lock"])
def test_the_dependencies_every_test_runs_on_run_the_full_suite(path: str) -> None:
    """A changed dependency reaches every test at once and no import says so. Delete this and a
    lock-file change selects the handful of files that name the lock file. The sibling tests
    below show the shared test infrastructure, which used to be here, no longer does."""
    assert select([path], depth=2, suite=SUITE).full


def test_the_full_suite_list_is_the_dependencies_and_nothing_else() -> None:
    """**This is the line the lighter pull request gate is drawn on.** Delete this and a conftest,
    a fixture, a helper or a workflow can be added back to `FULL_SUITE` and every pull request that
    touches one costs the whole suite again (127 to 222 job-minutes), with every other test
    green."""
    assert set(FULL_SUITE) == {"pyproject.toml", "uv.lock"}


@pytest.mark.parametrize(
    "path",
    [
        "tests/fixtures/company.py",
        "tests/fixtures/scratch_postgres.py",
        "tests/fixtures/cassettes/cloudflare.py",
        ".github/workflows/ci.yml",
        ".github/workflows/nightly-suite.yml",
        "src/brain/ops/test_selection.py",
        "src/brain/ops/test_plan.py",
        "src/brain/ops/test_shards.py",
        "src/brain/ops/guards.py",
    ],
)
def test_shared_test_infrastructure_selects_what_reads_it_and_no_longer_the_whole_suite(
    path: str,
) -> None:
    """A fixture, a workflow and the planner's own code used to run everything. Delete this and
    they do again, or they select nothing: the sibling assertions are that the selection is a
    strict subset of the suite and still holds the invariants and the readers."""
    chosen = select([path], depth=PLAN_DEPTH, suite=SUITE)
    assert not chosen.full
    assert 0 < len(chosen.files) < len(SUITE)
    assert {one for one in SUITE if one.startswith(ALWAYS)} <= set(chosen.files)


def test_a_support_module_selects_the_tests_that_import_it_directly_or_through_another() -> None:
    """The source graph does not follow `tests/`, so support modules are followed by text, to a
    fixed point. Delete this and a changed fixture selects nothing that uses it, or only the files
    naming it and not the ones reaching it through a second fixture."""
    direct = support_readers("tests/fixtures/company.py", SUITE)
    assert direct and direct <= set(SUITE)
    assert all("tests.fixtures" in (REPO / one).read_text(encoding="utf-8") for one in direct)
    chosen = select(["tests/fixtures/company.py"], depth=PLAN_DEPTH, suite=SUITE)
    assert direct <= set(chosen.files)


def test_a_test_reaching_a_fixture_only_through_another_fixture_is_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The fixed point, on a tree small enough to see.** `outer` imports `inner` and `deep`
    imports `outer`, so a test that imports only `deep` is reached by a change to `inner`, and one
    that imports none of them is not. Delete this and the closure is never exercised: a real tree
    has so many direct importers that a closure which does nothing still looks right."""
    texts = {
        "tests/fixtures/inner.py": "x = 1\n",
        "tests/fixtures/outer.py": "from tests.fixtures.inner import x\n",
        "tests/fixtures/deep.py": "from tests.fixtures import outer\n",
        "tests/fixtures/alone.py": "import os\n",
        "tests/unit/test_direct.py": "import tests.fixtures.inner\n",
        "tests/unit/test_via_outer.py": "from tests.fixtures.outer import y\n",
        "tests/unit/test_via_deep.py": "from tests.fixtures.deep import z\n",
        "tests/unit/test_via_alone.py": "from tests.fixtures.alone import w\n",
    }
    suite = [name for name in texts if "/test_" in name]
    monkeypatch.setattr(test_selection, "_text", texts.__getitem__)
    monkeypatch.setattr(
        test_selection, "_support_modules", lambda: tuple(n for n in texts if n not in suite)
    )
    assert support_readers("tests/fixtures/inner.py", suite) == {
        "tests/unit/test_direct.py",
        "tests/unit/test_via_outer.py",
        "tests/unit/test_via_deep.py",
    }
    assert support_readers("tests/fixtures/alone.py", suite) == {"tests/unit/test_via_alone.py"}


def test_an_import_is_recognised_in_each_way_it_can_be_written() -> None:
    """`import a.b.c`, `from a.b.c import x`, `from a.b import c` (one line or parenthesised) and
    `from a.b import c as d` all import `a.b.c`; `from a.b import other` does not. Delete this and
    the second form of import is never exercised, so a fixture imported as `from tests.fixtures
    import company` selects nothing, which no test over a real fixture would notice."""
    module = "tests.fixtures.company"
    for written in (
        "import tests.fixtures.company as c",
        "from tests.fixtures.company import make",
        "from tests.fixtures import company",
        "from tests.fixtures import company as c",
        "from tests.fixtures import (\n    other,\n    company,\n)",
    ):
        assert test_selection._imports(written, module), written
    assert not test_selection._imports("from tests.fixtures import other", module)
    assert not test_selection._imports("from tests.fixtures import company_two", module)
    assert not test_selection._imports("import tests.unit.helpers", module)


def test_a_support_module_that_nothing_imports_selects_no_test_by_import() -> None:
    """The positive sibling: the match is on the module and not on the word `tests`. Delete this
    and `support_readers` returns every test for every module, which satisfies the tests above."""
    assert support_readers("tests/fixtures/no_such_fixture_anywhere.py", SUITE) == set()


def test_a_conftest_or_package_marker_selects_every_test_beneath_its_directory_and_no_more() -> (
    None
):
    """A `conftest.py` applies to the tests under it and an `__init__.py` is the package they are
    imported through. Delete this and a conftest in one directory runs another's tests, or a
    root conftest, which really does reach everything, runs only some."""
    unit = [one for one in SUITE if one.startswith("tests/unit/")]
    other = [one for one in SUITE if not one.startswith("tests/unit/")]
    assert other, "the suite has tests outside tests/unit for this to tell apart"
    assert scoped_tests("tests/unit/conftest.py", SUITE) == set(unit)
    assert scoped_tests("tests/unit/__init__.py", SUITE) == set(unit)
    assert scoped_tests("tests/conftest.py", SUITE) == set(SUITE)
    assert scoped_tests("conftest.py", SUITE) == set(SUITE)
    chosen = select(["tests/unit/conftest.py"], depth=PLAN_DEPTH, suite=SUITE)
    assert not chosen.full and set(unit) <= set(chosen.files)
    outside = set(other) - {one for one in SUITE if one.startswith(ALWAYS)}
    assert outside and not outside <= set(chosen.files)


def test_an_unknown_diff_still_runs_the_full_suite() -> None:
    """A diff nobody computed is not a small one. Delete this and an empty diff reads as a change
    reaching nothing."""
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
    listed = [name for one in shares for name in sorted(units_run(one.files))]
    expected = units(select(changed, depth=PLAN_DEPTH, suite=SUITE).files)
    assert not any(one.full for one in shares)
    assert sorted(listed) == sorted(expected) and len(listed) == len(set(listed))
    assert 0 < len(listed) < len(SUITE)
    whole = [plan(n, SHARDS, base="", head="HEAD") for n in range(1, SHARDS + 1)]
    assert all(one.full for one in whole)
    assert sorted(name for one in whole for name in units_run(one.files)) == sorted(units(SUITE))


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
    only_here = {"TEST_SELECTION_BASE", "WHOLE_SUITE"}
    assert only_here <= set(theirs["env"]) and not only_here & set(ours["env"])
    assert {k: v for k, v in theirs["env"].items() if k not in only_here} == ours["env"]
    assert "needs" not in ours and "if" not in ours
    assert nightly[True]["schedule"] and "workflow_dispatch" in nightly[True]
    floor = nightly["jobs"]["coverage"]
    assert floor["name"] == "Unit tests and coverage" and floor["needs"] == "tests"
    body = "\n".join(str(one.get("run", "")) for one in floor["steps"])
    assert "uv run coverage report" in body and "--fail-under" not in body
    assert "grep -lx 'mode=full'" in body and "exit 1" in body


def _run_mode_step(
    tmp_path: Path, job: str, workflow_name: str, modes: list[str]
) -> tuple[int, str]:
    """Run the coverage job's "which mode" step as the runner's bash would (`-eo pipefail`), over
    plan files written for these modes, and return its exit status and what it wrote to
    `$GITHUB_OUTPUT`."""
    steps = workflow(workflow_name)["jobs"][job]["steps"]
    step = next(one for one in steps if "plan-shard-*.txt" in str(one.get("run", "")))
    temp = tmp_path / "runner-temp"
    data = temp / "plan-data"
    data.mkdir(parents=True)
    for number, mode in enumerate(modes, start=1):
        (data / f"plan-shard-{number}.txt").write_text(f"mode={mode}\n", encoding="utf-8")
    output = tmp_path / "output.txt"
    output.touch()
    script = str(step["run"]).replace("${{ runner.temp }}", str(temp))
    done = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", script],
        env={"GITHUB_OUTPUT": str(output), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, output.read_text(encoding="utf-8")


def test_the_coverage_job_reads_the_plans_as_the_runner_would_in_every_case(
    tmp_path: Path,
) -> None:
    """**The shell logic of the floor job, run.** Every shard full holds the floor; a selected
    run (any shard selected) skips it without failing, which `grep` finding nothing under
    `pipefail` once made a failure; and no plan at all fails. The first run of this change went red
    because the plan files were downloaded into the workspace, which the checkout after them
    deletes, so the directory is under the runner's temp. Delete this and either the required
    check fails every selected pull request, or it passes with nothing said about what ran."""
    for index, (modes, wanted) in enumerate(
        [
            (["full"] * 8, "full=true"),
            (["selected"] * 8, "full=false"),
            (["full", "selected", "full"], "full=false"),
        ]
    ):
        status, written = _run_mode_step(tmp_path / str(index), "coverage", "ci.yml", modes)
        assert status == 0 and wanted in written.splitlines(), (modes, written)
    status, written = _run_mode_step(tmp_path / "none", "coverage", "ci.yml", [])
    assert status != 0 and "full=" not in written


def test_the_plan_files_are_downloaded_where_the_checkout_cannot_delete_them() -> None:
    """The artifact is downloaded before `actions/checkout`, which cleans the workspace, so the
    path must be outside it. Delete this and the plan download goes back into the workspace and
    the floor job fails on every run with a missing directory, as the first run here did."""
    for name in ("ci.yml", "nightly-suite.yml"):
        steps = workflow(name)["jobs"]["coverage"]["steps"]
        plans = next(
            one
            for one in steps
            if str(one.get("uses", "")).startswith("actions/download-artifact")
            and str(one["with"]["pattern"]).startswith("plan-shard")
        )
        assert plans["with"]["path"].startswith("${{ runner.temp }}/"), name


# ------------------------------------------------------------------ the lighter pull request gate


def test_a_merge_train_plans_every_shards_full_share_whatever_the_diff() -> None:
    """**The whole suite on a train, decided in Python and not in YAML.** With `whole_suite` every
    shard's plan is its full share, the shares between them are every file once, and the reason
    says the suite was asked for. Delete this and a train runs the selection like any pull request,
    which makes the train no more than a larger selected run. The sibling is the same diff without
    the request, which is selected."""
    changed = ["src/brain/ops/limits.py"]
    asked = [
        plan(n, SHARDS, base="x", head="HEAD", changed=changed, whole_suite=True)
        for n in range(1, SHARDS + 1)
    ]
    assert all(one.full and one.reason == WHOLE_SUITE_REQUESTED for one in asked)
    assert sorted(name for one in asked for name in units_run(one.files)) == sorted(units(SUITE))
    plain = [plan(n, SHARDS, base="x", head="HEAD", changed=changed) for n in range(1, SHARDS + 1)]
    assert not any(one.full for one in plain)
    assert sum(len(one.files) for one in plain) < len(SUITE)


def test_the_planner_takes_the_whole_suite_request_from_a_flag_and_defaults_to_selecting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The command line is how the workflow asks. Delete this and the flag is parsed and dropped,
    so a train selects, or the flag becomes the default and every pull request runs the suite."""
    seen: list[bool] = []

    def spy(*args: object, **kwargs: Any) -> test_plan.Plan:
        seen.append(bool(kwargs["whole_suite"]))
        return test_plan.Plan(files=("tests/unit/test_x.py",), full=False, reason="spy")

    monkeypatch.setattr(test_plan, "plan", spy)
    common = ["--shard", "1", "--of", "8", "--base", "b", "--mode-file", str(tmp_path / "m")]
    assert test_plan.main(common) == 0
    assert test_plan.main([*common, "--whole-suite"]) == 0
    assert seen == [False, True]


def run_shard_step(tmp_path: Path, whole: str | None) -> list[str]:
    """Run the shard job's test step under bash with a stand-in `uv` that logs its commands, and
    return the commands. `whole` is the value of `WHOLE_SUITE`, or None for unset (the nightly)."""
    step = _shard_step(workflow("ci.yml")["jobs"]["tests"])
    script = (
        str(step["run"])
        .replace("${{ matrix.shard }}", "3")
        .replace("${{ strategy.job-total }}", "8")
    )
    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "uv.log"
    fake = tools / "uv"
    fake.write_text(
        '#!/bin/sh\necho "$*" >> "$UV_LOG"\n'
        'case "$*" in *brain.ops.test_plan*) echo tests/unit/test_x.py;; esac\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = {
        "PATH": f"{tools}:/usr/bin:/bin",
        "GITHUB_WORKSPACE": str(tmp_path),
        "GITHUB_OUTPUT": str(tmp_path / "out"),
        "GITHUB_SHA": "head",
        "TEST_SELECTION_BASE": "base",
        "UV_LOG": str(log),
    }
    if whole is not None:
        env["WHOLE_SUITE"] = whole
    done = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", script], env=env, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    return log.read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize(
    ("whole", "flagged"),
    [("true", True), ("false", False), (None, False), ("", False)],
)
def test_the_shard_step_asks_for_the_whole_suite_only_when_the_branch_says_it_is_a_train(
    tmp_path: Path, whole: str | None, flagged: bool
) -> None:
    """**The step, run as the runner's bash would.** `WHOLE_SUITE=true` adds `--whole-suite` to the
    planning command, and anything else, unset included (the nightly suite), does not. Delete this
    and the flag is passed always (every pull request runs everything), never (a train selects), or
    on any non-empty value, `false` included, which is how shell tests of a string usually go
    wrong."""
    commands = run_shard_step(tmp_path, whole)
    planned = next(one for one in commands if "brain.ops.test_plan" in one)
    assert ("--whole-suite" in planned.split()) is flagged
    assert "--base base" in planned and "--head head" in planned
    assert commands[-1].startswith("run pytest ") and commands[-1].endswith("tests/unit/test_x.py")


def test_only_a_branch_starting_with_train_slash_sets_the_whole_suite_request() -> None:
    """**The condition, parsed.** The job's `WHOLE_SUITE` is exactly `startsWith` over the head
    branch and the prefix `train/`, with no label, comment or input in it, and it is read by the
    step that plans. Delete this and a looser expression (`contains`, a label) lets a pull request
    ask for, or avoid, the whole suite by wording. The nightly sets none of it."""
    job = workflow("ci.yml")["jobs"]["tests"]
    assert job["env"]["WHOLE_SUITE"] == "${{ startsWith(github.head_ref, 'train/') }}"
    assert "WHOLE_SUITE" in str(_shard_step(job)["run"])
    assert "WHOLE_SUITE" not in workflow("nightly-suite.yml")["jobs"]["tests"]["env"]
    assert "train/" in str(workflow("ci.yml")["jobs"]["tests"]["env"]["WHOLE_SUITE"])
    assert not [k for k in job["env"] if "LABEL" in k.upper()]


def test_the_whole_suite_runs_on_a_train_every_night_and_on_demand_and_main_is_left_alone() -> None:
    """**Where the whole suite runs now, and what did not move.** A pull request, a push to main
    (the deploy gates), a train (via the pull request trigger and the branch name), the nightly
    schedule and a manual dispatch of the nightly suite. CI itself is not dispatchable, and Deploy
    still listens for CI completing on main. Delete this and a `workflow_dispatch` on CI, or an
    edit to Deploy's trigger, changes what reaches the server with every other test green."""
    ci, nightly = workflow("ci.yml"), workflow("nightly-suite.yml")
    assert ci[True] == {"push": {"branches": ["main"]}, "pull_request": None}
    assert set(nightly[True]) == {"schedule", "workflow_dispatch"}
    deploy = workflow("deploy.yml")[True]["workflow_run"]
    assert deploy == {"workflows": ["CI"], "branches": ["main"], "types": ["completed"]}
    shard_job = ci["jobs"]["tests"]
    assert "github.event_name == 'pull_request'" in shard_job["if"]
    assert "needs" not in nightly["jobs"]["tests"] and "if" not in nightly["jobs"]["tests"]


def test_what_an_ordinary_pull_request_no_longer_proves_is_written_down_where_the_deploy_is() -> (
    None
):
    """The reader who decides what to trust before a merge needs the trade written next to the
    deploy chain: which kinds of change are now selected rather than run whole, and where the whole
    suite runs. Delete this and the guarantee changes in the workflow and nowhere a person looks."""
    text = (REPO / "ops" / "DEPLOY.md").read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    current = ""
    for line in text.splitlines():
        if line.startswith("#"):
            current = line.lstrip("# ").strip()
            sections[current] = ""
        elif current:
            sections[current] += line + "\n"
    body = sections["What a normal pull request no longer proves"]
    for needed in ("train/", "nightly-suite.yml", "workflow_dispatch", "conftest", "fixture"):
        assert needed in body, needed
    assert "ops/dev/assemble_train.py" in body
