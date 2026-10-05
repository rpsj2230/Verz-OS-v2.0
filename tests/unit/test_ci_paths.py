"""CI's path filters: every pattern names a file that exists, each job reads its own filter, and
anything uncertain runs everything.

A filter decides whether a required job runs, and a skipped job passes a required check, so the
failure these guard against is silent: a lock file moved, the audit's pattern pointing where it
used to be, and the audit never running again with every check green. See
`brain.ops.ci_paths.A_FILTER_NAMES_WHAT_ITS_JOB_READS_AND_EVERY_NAME_EXISTS`.

Task ids: none
"""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.ops.ci_paths import ALWAYS, FILTERS, affected, changed_files, main

REPO = Path(__file__).resolve().parents[2]


def tracked() -> list[str]:
    done = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True)
    return done.stdout.splitlines()


def workflow(name: str) -> dict[Any, Any]:
    loaded = yaml.safe_load((REPO / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.mark.parametrize(
    ("name", "pattern"),
    [(name, one) for name, patterns in FILTERS.items() for one in (*patterns, *ALWAYS)],
)
def test_every_pattern_names_a_file_that_exists(name: str, pattern: str) -> None:
    """**The moved-file guard.** Delete this and a renamed lock, compose file or module leaves its
    job's filter matching nothing, and the job is skipped on every pull request as a pass."""
    files = tracked()
    assert any(fnmatch.fnmatchcase(one, pattern) for one in files), (
        f"the {name} filter's pattern {pattern!r} matches no tracked file"
    )


def test_each_filtered_job_reads_its_own_filter_and_every_filter_has_a_job() -> None:
    """The four gated jobs each name one output of `changes`, the output is declared from the
    step that runs this module, and no filter is computed for a job nobody gates. Delete this and
    a job can read another's filter, or an output nothing sets, which is always empty and so
    always skips."""
    jobs = workflow("ci.yml")["jobs"]
    outputs = jobs["changes"]["outputs"]
    read = {
        name: output
        for name, job in jobs.items()
        for output in FILTERS
        if f"needs.changes.outputs.{output} == 'true'" in str(job.get("if", ""))
    }
    assert read == {
        "console": "console",
        "presidio": "presidio",
        "supply_chain": "dependencies",
        "vulnerabilities": "image",
    }
    for output in FILTERS:
        assert outputs[output] == f"${{{{ steps.paths.outputs.{output} }}}}"
    step = next(one for one in jobs["changes"]["steps"] if one.get("id") == "paths")
    assert "python3 src/brain/ops/ci_paths.py" in str(step["run"])
    assert '"$GITHUB_OUTPUT"' in str(step["run"])


def test_no_deploy_gate_reads_a_filter() -> None:
    """Main keeps every job a deploy depends on. Delete this and a path filter can creep onto a
    job main runs, and a merge deploys with that job skipped."""
    jobs = workflow("ci.yml")["jobs"]
    for name, job in jobs.items():
        gate = str(job.get("if", ""))
        if any(f"outputs.{output}" in gate for output in FILTERS):
            assert "github.event_name == 'pull_request'" in gate, name


def test_a_diff_touching_a_filters_file_runs_its_job_and_one_touching_none_does_not() -> None:
    """The positive and the negative of each filter, from paths the tree holds. Delete this and a
    filter that matched everything, or nothing, would satisfy the tests above."""
    assert affected(["uv.lock"]) == {
        "dependencies": True,
        "image": True,
        "presidio": False,
        "console": True,
    }
    assert affected(["docker-compose.presidio.yml"]) == {
        "dependencies": True,
        "image": False,
        "presidio": True,
        "console": False,
    }
    assert affected(["console/src/App.tsx"]) == {
        "dependencies": False,
        "image": False,
        "presidio": False,
        "console": True,
    }
    assert affected(["ops/hooks/pre-push"]) == dict.fromkeys(FILTERS, False)
    assert affected(["src/brain/app.py"]) == {
        "dependencies": False,
        "image": False,
        "presidio": False,
        "console": True,
    }


def test_anything_uncertain_runs_everything() -> None:
    """A diff nobody could compute, an empty one, and a change to the filters or the workflow run
    every gated job. Delete this and a shallow checkout or an edited filter skips the jobs the
    edit exists to change."""
    everything = dict.fromkeys(FILTERS, True)
    assert affected(None) == everything
    assert affected([]) == everything
    for path in ALWAYS:
        assert affected([path]) == everything
    assert changed_files("", "HEAD") is None
    assert changed_files("0" * 40, "HEAD") is None
    assert changed_files("not-a-commit", "HEAD") is None


def test_the_step_prints_one_line_per_filter(capsys: pytest.CaptureFixture[str]) -> None:
    """What `$GITHUB_OUTPUT` is handed. Delete this and a renamed output prints under a name no
    job reads."""
    assert main(["--base", "", "--head", "HEAD"]) == 0
    assert capsys.readouterr().out.splitlines() == [f"{name}=true" for name in FILTERS]


def test_a_job_the_diff_cannot_affect_is_printed_false(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The negative of the one above. Delete this and a step that printed true for everything
    would pass, and no job would ever be skipped."""
    from brain.ops import ci_paths

    monkeypatch.setattr(ci_paths, "changed_files", lambda base, head: ["ops/hooks/pre-push"])
    assert main(["--base", "abc", "--head", "HEAD"]) == 0
    assert capsys.readouterr().out.splitlines() == [f"{name}=false" for name in FILTERS]


def test_the_nightly_scan_is_the_pull_requests_scan_step_for_step() -> None:
    """A new advisory changes no file, so the scan also runs nightly on main. Delete this and the
    nightly copy drifts from the job it stands for, or starts deploying: Deploy listens for CI,
    and the nightly workflow must never be CI."""
    ci, nightly = workflow("ci.yml"), workflow("nightly.yml")
    assert nightly["name"] != ci["name"] == "CI"
    assert nightly["jobs"]["vulnerabilities"]["steps"] == ci["jobs"]["vulnerabilities"]["steps"]
    assert nightly[True]["schedule"], "the nightly workflow has no schedule"
