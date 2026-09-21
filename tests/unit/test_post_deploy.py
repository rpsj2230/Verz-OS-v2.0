"""The post-deploy checks' verdict, the page that serves it, and the two workflows that act on it.

Task ids: M38.5.1, M38.2.1.2
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from brain.ops import post_deploy
from brain.ops.post_deploy import (
    CHECKS,
    DATABASE_INVARIANTS,
    FAILED,
    NOT_RUN,
    PASSED,
    database_invariants,
    invariant_checks,
    read_recorded,
    run_checks,
    served,
)
from brain.ops.sweeps import SweepFailure

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2999, 1, 1, tzinfo=UTC)
CHECKS_JOB = "Staging permission canaries and RLS sweep"


def fine() -> None:
    return None


def rls_off() -> None:
    raise SweepFailure(["row-level security disabled on secret_table"])


def checks(**overrides: Any) -> dict[str, Any]:
    return {"rls": fine, "canaries": fine, "schema": fine, "invariants": fine, **overrides}


def test_every_check_passing_is_a_pass() -> None:
    """The positive case. Delete this and a verdict that is always failed passes every refusal."""
    verdict = run_checks("abc1234", **checks(), now=NOW)
    assert verdict.passed and all(getattr(verdict, name) == PASSED for name in CHECKS)


@pytest.mark.parametrize("name", ["schema", "invariants"])
def test_a_failed_schema_or_invariant_check_fails_the_verdict(name: str) -> None:
    """M38.2.1.2. Delete this and `passed` can go on reading only the first two checks."""
    verdict = run_checks("abc1234", **checks(**{name: rls_off}), now=NOW)
    assert getattr(verdict, name) == FAILED and not verdict.passed


def test_every_database_invariant_runs_and_one_failure_fails_them_all(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Delete this and the first failing invariant hides the rest, or a failure passes."""
    ran: list[str] = []
    with pytest.raises(SweepFailure) as raised:
        database_invariants({"first": rls_off, "second": lambda: ran.append("second")})
    assert ran == ["second"] and raised.value.findings == ["first failed"]
    assert "secret_table" in capsys.readouterr().err
    database_invariants({"only": fine})


def test_the_invariants_bound_to_a_database_are_the_ones_documented() -> None:
    """Delete this and `DATABASE_INVARIANTS` can describe checks `main` no longer runs."""

    class Settings:
        database_url = "postgresql+psycopg://x@localhost/x"
        migration_database_url = ""

    assert list(invariant_checks(Settings())) == [name for name, _ in DATABASE_INVARIANTS]


def test_a_failed_sweep_fails_and_the_canaries_still_run() -> None:
    """Both halves are reported whatever the other found. Delete this and the first failure hides
    whether the second check would have failed too."""
    ran: list[str] = []
    verdict = run_checks(
        "abc1234", **checks(rls=rls_off, canaries=lambda: ran.append("canaries")), now=NOW
    )
    assert (verdict.rls, verdict.canaries, ran) == (FAILED, PASSED, ["canaries"])
    assert not verdict.passed


def test_a_canary_that_raises_fails(capsys: pytest.CaptureFixture[str]) -> None:
    """Delete this and a red canary run, which raises, is recorded as whatever the default is."""

    def leak() -> None:
        raise RuntimeError("the canaries found something")

    verdict = run_checks("abc1234", **checks(canaries=leak), now=NOW)
    assert verdict.canaries == FAILED and not verdict.passed
    assert "the canaries found something" in capsys.readouterr().err


def test_the_served_document_names_no_finding(tmp_path: Path) -> None:
    """The public page says passed or failed and never which table. Delete this and a finding's
    words reach a page anybody on the internet can read."""
    verdict = run_checks("abc1234", **checks(rls=rls_off), now=NOW)
    recorded = json.loads(json.dumps(verdict.__dict__))
    recorded["rls"] = "row-level security disabled on secret_table"
    recorded["invariants"] = "2 migration(s) not applied: 0087_secret"
    page = served("abc1234", recorded)
    assert page["rls"] == FAILED and page["invariants"] == FAILED
    assert "secret" not in json.dumps(page)
    assert set(page) == {"commit", "rls", "canaries", "schema", "invariants", "checked_at"}


def test_a_verdict_an_older_image_wrote_reports_the_new_checks_as_not_run() -> None:
    """A verdict with no schema or invariants field never ran them. Delete this and it reads as
    failed, or worse, somebody makes a missing field read as passed."""
    old = {"commit": "abc1234", "rls": PASSED, "canaries": PASSED, "checked_at": "t"}
    page = served("abc1234", old)
    assert (page["schema"], page["invariants"]) == (NOT_RUN, NOT_RUN)


def test_a_verdict_for_another_commit_is_not_run() -> None:
    """See `A_VERDICT_BELONGS_TO_THE_CONTAINER_THAT_EARNED_IT`. Delete this and a new container
    serving an unchecked commit shows the previous commit's pass."""
    old = {"commit": "old1234", "rls": PASSED, "canaries": PASSED, "checked_at": "x"}
    assert served("new5678", old)["rls"] == NOT_RUN
    assert all(served("new5678", None)[name] == NOT_RUN for name in CHECKS)
    assert served("old1234", old)["rls"] == PASSED


def test_an_unreadable_record_reads_as_none(tmp_path: Path) -> None:
    """Delete this and a half-written file raises in a public route rather than saying not run."""
    broken = tmp_path / "result.json"
    broken.write_text("{not json", encoding="utf-8")
    assert read_recorded(broken) is None
    assert read_recorded(tmp_path / "absent.json") is None


def test_the_route_serves_the_recorded_verdict_for_the_commit_it_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Through the application. Delete this and the page the Deploy workflow reads can be removed
    or can stop reading the file the checks write, and staging_checks waits ten minutes and fails
    on every deploy for a reason that is not a check."""
    from brain.app import create_app

    result = tmp_path / "brain-post-deploy.json"
    everything = {"commit": "abc1234", **dict.fromkeys(CHECKS, PASSED), "checked_at": "t"}
    result.write_text(json.dumps(everything), encoding="utf-8")
    monkeypatch.setattr(post_deploy, "RESULT", result)
    monkeypatch.setattr(post_deploy.read_recorded, "__defaults__", (result,))
    monkeypatch.setenv("BRAIN_COMMIT_SHA", "abc1234")
    body = TestClient(create_app()).get("/api/deploy-checks.json").json()
    assert body == everything


# ------------------------------------------------------------------------------ the workflows
def _workflow(name: str) -> dict[Any, Any]:
    loaded: dict[Any, Any] = yaml.safe_load(
        (REPO / ".github" / "workflows" / name).read_text(encoding="utf-8")
    )
    return loaded


def _decide(body: str, sha: str) -> str:
    step = _workflow("deploy.yml")["jobs"]["staging_checks"]["steps"][0]
    done = subprocess.run(
        [sys.executable, "-c", step["env"]["DECIDE"]],
        input=body,
        capture_output=True,
        text=True,
        env={**os.environ, "SHA": sha},
        check=False,
    )
    return done.stdout.strip()


ALL_PASSED = {"rls": PASSED, "canaries": PASSED, "schema": PASSED, "invariants": PASSED}


@pytest.mark.parametrize(
    ("page", "decision"),
    [
        ({"commit": "abc1234", **ALL_PASSED}, "passed"),
        ({"commit": "abc1234", **ALL_PASSED, "rls": FAILED}, "failed"),
        ({"commit": "abc1234", **ALL_PASSED, "canaries": FAILED}, "failed"),
        ({"commit": "abc1234", **ALL_PASSED, "schema": FAILED}, "failed"),
        ({"commit": "abc1234", **ALL_PASSED, "invariants": FAILED}, "failed"),
        ({"commit": "abc1234", **ALL_PASSED, "invariants": NOT_RUN}, "wait"),
        ({"commit": "abc1234", "rls": PASSED, "canaries": PASSED}, "wait"),
        ({"commit": "abc1234", "rls": NOT_RUN, "canaries": NOT_RUN}, "wait"),
        ({"commit": "0ld1234", "rls": FAILED, "canaries": FAILED}, "wait"),
        ({"commit": "", **ALL_PASSED}, "wait"),
    ],
)
def test_the_deploy_workflow_passes_only_every_check_for_this_commit(
    page: dict[str, str], decision: str
) -> None:
    """The decision the Deploy workflow makes, run as it runs. Delete this and the job can pass on
    the previous commit's verdict, on an empty commit, which `"".startswith` would allow, or on a
    page from before the schema and invariant checks existed."""
    assert _decide(json.dumps(page), "abc1234def") == decision


def test_the_deploy_workflow_waits_for_the_live_deploy_and_reads_the_verdict_page() -> None:
    """Delete this and the job can run before the server has pulled, or read another page."""
    job = _workflow("deploy.yml")["jobs"]["staging_checks"]
    assert job["name"] == CHECKS_JOB
    assert set(job["needs"]) == {"build", "deploy"}
    assert "/api/deploy-checks.json" in job["steps"][0]["run"]


def test_the_checks_wait_for_the_owner_to_switch_them_on_and_release_still_needs_a_pass() -> None:
    """Delete this and the job either runs before the server writes a verdict, failing every
    deploy, or a skipped job could be read as a pass. Release asks for `success`, not skipped."""
    job = _workflow("deploy.yml")["jobs"]["staging_checks"]
    assert job["if"] == "${{ vars.POST_DEPLOY_CHECKS == 'on' }}"
    gate = next(
        step
        for step in _workflow("release.yml")["jobs"]["image"]["steps"]
        if "CHECKS_JOB" in step.get("env", {})
    )
    assert '.conclusion == \\"success\\"' in gate["run"]


def test_a_release_is_refused_for_a_commit_whose_deploy_did_not_pass_the_checks() -> None:
    """The promotion M38.5.1 stops. Delete this and the gate step can be removed from Release, or
    moved after the tag is created, and a refused commit is released anyway."""
    job = _workflow("release.yml")["jobs"]["image"]
    names = [step.get("name", step.get("id", "")) for step in job["steps"]]
    gate = next(
        index for index, step in enumerate(job["steps"]) if "CHECKS_JOB" in step.get("env", {})
    )
    promote = next(index for index, step in enumerate(job["steps"]) if step.get("id") == "promote")
    assert gate < promote, names
    step = job["steps"][gate]
    assert step["env"]["CHECKS_JOB"] == CHECKS_JOB
    assert "actions/workflows/deploy.yml/runs?head_sha=$commit" in step["run"]
    assert '.conclusion == \\"success\\"' in step["run"]
    assert job["permissions"]["actions"] == "read"


def test_the_server_runs_the_checks_in_the_container_it_deployed_and_stops_on_failure() -> None:
    """The server half, which is the only place the checks can run. Delete this and the timer's
    script can lose the step, and every Deploy run waits for a verdict nobody writes."""
    script = (REPO / "ops" / "deploy" / "brain-autodeploy").read_text(encoding="utf-8")
    live = [line.strip() for line in script.splitlines() if not line.strip().startswith("#")]
    deploy_at = live.index("/usr/local/bin/brain-deploy")
    check_at = next(
        i
        for i, line in enumerate(live)
        if 'docker exec "$CONTAINER" python -m brain.ops.post_deploy' in line
    )
    assert deploy_at < check_at
    assert 'note "checks-failed" "$tag_id"' in live[check_at:]
