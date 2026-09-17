"""A critical finding fails unless it is excepted with a reason and an end, over fixed scans.

Task ids: M38.5.2
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from brain.ops import vulnerabilities as vulns
from brain.ops.dependency_policy import NPM_LOCKS, PYTHON_LOCKS
from brain.ops.vulnerabilities import (
    EXCEPTIONS,
    LONGEST_EXCEPTION,
    Finding,
    RecordedException,
    findings_in,
    judge,
    read_exceptions,
    unread_locks,
)

REPO = Path(__file__).resolve().parents[2]
TODAY = date(2999, 6, 1)


def critical(vulnerability: str = "CVE-1", package: str = "zlib1g") -> Finding:
    return Finding(vulnerability, package, "1.0", "CRITICAL", "image (debian)", "")


def excepted(
    ends: date, vulnerability: str = "CVE-1", package: str = "zlib1g"
) -> RecordedException:
    return RecordedException(vulnerability, package, "unused code path", date(2999, 5, 1), ends)


def a_report(targets: list[str], severity: str = "CRITICAL") -> dict[str, Any]:
    return {
        "Results": [
            {
                "Target": target,
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-9",
                        "PkgName": "left",
                        "InstalledVersion": "1.0.0",
                        "Severity": severity,
                        "FixedVersion": "1.0.1",
                    }
                ],
            }
            for target in targets
        ]
    }


def test_a_critical_finding_with_no_exception_fails() -> None:
    """The rule. Delete this and the scan runs, reports, and ships whatever it found."""
    verdict = judge([critical()], [], today=TODAY)
    assert verdict.failing == (critical(),) and not verdict.passes


def test_a_critical_finding_with_a_live_exception_passes() -> None:
    """The positive case. Delete this and an exception that is never honoured passes the test
    above just as well, and the only way through is to remove the scan."""
    verdict = judge([critical()], [excepted(date(2999, 7, 1))], today=TODAY)
    assert verdict.passes and verdict.excepted == (critical(),)


def test_an_exception_past_its_end_excepts_nothing() -> None:
    """See `AN_EXCEPTION_SAYS_WHY_AND_ENDS`. Delete this and the exception recorded in March is
    still silencing the finding in December."""
    verdict = judge([critical()], [excepted(date(2999, 5, 31))], today=TODAY)
    assert not verdict.passes and len(verdict.lapsed) == 1


def test_an_exception_for_the_same_id_in_another_package_does_not_apply() -> None:
    """Delete this and one reviewed finding excepts the same id wherever else it turns up, in a
    package nobody looked at."""
    verdict = judge([critical(package="openssl")], [excepted(date(2999, 7, 1))], today=TODAY)
    assert not verdict.passes


def test_high_and_below_are_counted_and_do_not_fail() -> None:
    """M38.5.2 names critical. Delete this and the first high finding in a transitive package
    makes every build red, and the gate is switched off within the week."""
    high = Finding("CVE-2", "nanoid", "3.3.6", "HIGH", "piece lock", "3.3.8")
    verdict = judge([high], [], today=TODAY)
    assert verdict.passes and verdict.below == 1


@pytest.mark.parametrize(
    ("entry", "why"),
    [
        (
            {
                "vulnerability": "CVE-1",
                "package": "p",
                "recorded": "2999-01-01",
                "ends": "2999-02-01",
            },
            "no reason",
        ),
        (
            {
                "vulnerability": "CVE-1",
                "package": "p",
                "reason": " ",
                "recorded": "2999-01-01",
                "ends": "2999-02-01",
            },
            "blank reason",
        ),
        (
            {
                "vulnerability": "CVE-1",
                "package": "p",
                "reason": "r",
                "recorded": "2999-01-01",
                "ends": "2999-06-01",
            },
            "too long",
        ),
        (
            {
                "vulnerability": "CVE-1",
                "package": "p",
                "reason": "r",
                "recorded": "2999-01-01",
                "ends": "2999-01-01",
            },
            "ends as it starts",
        ),
        (
            {
                "vulnerability": "CVE-1",
                "package": "p",
                "reason": "r",
                "recorded": "soon",
                "ends": "2999-01-01",
            },
            "no date",
        ),
    ],
)
def test_an_exception_that_is_not_a_full_record_is_refused_and_fails_the_run(
    entry: dict[str, str], why: str
) -> None:
    """Delete this and an exception with no reason or no end is honoured like one with both."""
    valid, refused = read_exceptions({"exceptions": [entry]})
    assert valid == () and len(refused) == 1, why
    assert not judge([], valid, today=TODAY, record_refusals=refused).passes


def test_an_exception_of_exactly_the_longest_span_is_accepted() -> None:
    """The boundary, asserted against the span rather than restating it. Delete this and `>`
    becoming `>=` refuses a ninety-day exception the constant says is allowed."""
    recorded = date(2999, 1, 1)
    entry = {
        "vulnerability": "CVE-1",
        "package": "p",
        "reason": "r",
        "recorded": recorded.isoformat(),
        "ends": (recorded + LONGEST_EXCEPTION).isoformat(),
    }
    valid, refused = read_exceptions({"exceptions": [entry]})
    assert len(valid) == 1 and refused == ()


def test_a_lock_the_scan_did_not_read_fails_the_run() -> None:
    """See `A_LOCK_THE_SCAN_DID_NOT_READ_IS_A_FAILURE`. Delete this and a scanner that does not
    recognise `uv.lock` reports a clean Python dependency set."""
    report = a_report(["console/package-lock.json"], severity="LOW")
    missing = unread_locks(report, ["uv.lock", "console/package-lock.json"])
    assert missing == ("uv.lock",)
    assert not judge(findings_in(report), [], today=TODAY, unread=missing).passes


def test_every_lock_the_dependency_policy_reads_is_one_the_scan_must_read() -> None:
    """One list of locks for both checks. Delete this and a lock added to the policy is never
    required of the scan."""
    report = a_report([*PYTHON_LOCKS, *NPM_LOCKS], severity="LOW")
    assert unread_locks(report, [*PYTHON_LOCKS, *NPM_LOCKS]) == ()


def test_a_trivy_report_is_read_into_findings() -> None:
    """Delete this and a renamed field makes every report read as no findings at all."""
    (one,) = findings_in(a_report(["uv.lock"]))
    assert one == Finding("CVE-9", "left", "1.0.0", "CRITICAL", "uv.lock", "1.0.1")


def test_the_recorded_exceptions_file_is_a_valid_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """The committed file. Delete this and a malformed exception makes every build red for a
    reason nobody reads as a vulnerability."""
    document = json.loads((REPO / EXCEPTIONS).read_text(encoding="utf-8"))
    valid, refused = read_exceptions(document)
    assert refused == ()
    assert all(one.reason and one.ends > one.recorded for one in valid)


def test_the_command_fails_on_a_critical_finding_and_passes_without_one(tmp_path: Path) -> None:
    """End to end through `main`. Delete this and the command can print CRITICAL and exit 0."""
    targets = [*PYTHON_LOCKS, *NPM_LOCKS]
    locks = tmp_path / "locks.json"
    image = tmp_path / "image.json"
    locks.write_text(json.dumps(a_report(targets, severity="LOW")), encoding="utf-8")
    image.write_text(json.dumps(a_report(["brain:scan (debian 12)"])), encoding="utf-8")
    argv = ["--locks", str(locks), "--image", str(image), "--today", TODAY.isoformat()]
    assert vulns.main(argv) == 1
    image.write_text(json.dumps(a_report(["brain:scan (debian 12)"], "HIGH")), encoding="utf-8")
    assert vulns.main(argv) == 0


def test_ci_scans_every_lock_and_the_image_and_judges_both() -> None:
    """Delete this and the job can lose its image scan or its verdict step and still go green."""
    workflow = yaml.safe_load(
        (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["vulnerabilities"]
    runs = [" ".join(str(step.get("run", "")).split()) for step in job["steps"]]
    assert any(run.startswith("mkdir -p evidence trivy fs --scanners vuln") for run in runs)
    assert any("trivy image --scanners vuln" in run and "brain:scan" in run for run in runs)
    assert any(run.startswith("docker build") and "-t brain:scan" in run for run in runs)
    verdict = next(run for run in runs if "brain.ops.vulnerabilities" in run)
    assert "--locks evidence/trivy-locks.json" in verdict
    assert "--image evidence/trivy-image.json" in verdict
