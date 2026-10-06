"""The test selection's shadow: what it would run, how a miss is recorded, and that it decides
nothing.

The selection is not switched on. These tests hold the three things the week of shadow records
depends on: the selection reaches the tests the import graph says it reaches and falls back to
the full suite where the graph is blind; a failure the shards found outside the selection is
recorded as a miss; and the job that records it can never fail a run or gate a deploy, while the
nightly suite runs every file exactly as a pull request's shards do.

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

from brain.ops.test_selection import (
    ALWAYS,
    DEPTHS,
    FULL_SUITE,
    MAY_BE_ABSENT,
    failed_files,
    main,
    record,
    select,
)
from brain.ops.test_shards import collected

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


def test_the_shadow_job_decides_nothing_and_every_shard_still_runs_every_file() -> None:
    """The job cannot fail a run, nothing waits on it, it never runs on main, and each shard
    writes the report it reads whatever the tests did. Delete this and the shadow can quietly
    become the selection, or starve itself of the red shards it exists to measure."""
    jobs = workflow("ci.yml")["jobs"]
    shadow = jobs["selection_shadow"]
    assert shadow["continue-on-error"] is True
    assert "github.event_name == 'pull_request'" in shadow["if"]
    assert "!cancelled()" in shadow["if"]
    assert "tests" in shadow["needs"]
    assert not [
        name
        for name, job in jobs.items()
        if "selection_shadow"
        in ([job["needs"]] if isinstance(job.get("needs"), str) else job.get("needs", []))
    ]
    steps = jobs["tests"]["steps"]
    shard = next(one for one in steps if "brain.ops.test_shards" in str(one.get("run", "")))
    assert '--junitxml="$GITHUB_WORKSPACE/junit/shard-${{ matrix.shard }}.xml"' in shard["run"]
    kept = next(
        one for one in steps if str(one.get("with", {}).get("name", "")).startswith("junit-shard")
    )
    assert kept["if"] == "${{ always() }}"


def test_the_nightly_suite_is_the_pull_requests_shards_step_for_step() -> None:
    """The floor that keeps every file running once a day when the selection is switched on.
    Delete this and the nightly copy can drift from the shards, or deploy: Deploy listens for CI,
    and this workflow must never be CI."""
    ci, nightly = workflow("ci.yml"), workflow("nightly-suite.yml")
    assert nightly["name"] != ci["name"] == "CI"
    ours, theirs = nightly["jobs"]["tests"], ci["jobs"]["tests"]
    assert ours["steps"] == theirs["steps"]
    assert ours["strategy"] == theirs["strategy"] and ours["services"] == theirs["services"]
    assert "needs" not in ours and "if" not in ours
    assert nightly[True]["schedule"]
