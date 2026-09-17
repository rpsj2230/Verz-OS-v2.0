"""A critical vulnerability fails the build unless somebody has recorded why it may ship.

The scanner is Trivy, run by the `vulnerabilities` job in `ci.yml` over the repository's locks and
over the image that job builds the way production builds it. This module reads what Trivy wrote
and decides; the scanner decides nothing. Rejected: Trivy's own `--exit-code 1 --severity
CRITICAL` with a `.trivyignore`. That file takes an id and nothing else, so an exception there
carries no reason, no author's date and no end, and the one that was right in March is still
silencing the finding in December. See `AN_EXCEPTION_SAYS_WHY_AND_ENDS`.

**A scan that did not read a lock has proved nothing about it.** Trivy reports the files it
recognised, and a lockfile it skipped (a format it does not know, a path it was not given) is
simply absent from its report, which reads exactly like a lockfile with no findings. So every lock
`brain.ops.dependency_policy` reads must appear as a target of the scan, or the run fails. See
`A_LOCK_THE_SCAN_DID_NOT_READ_IS_A_FAILURE`.

**Only critical findings fail.** High and below are counted and printed, which is the sentence
M38.5.2 asks for, and on 2026-09-17 the locks carried four high findings in npm packages, printed
on every run so they are worked down rather than discovered.

Task ids: M38.5.2
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Final

from brain.ops.dependency_policy import NPM_LOCKS, PYTHON_LOCKS

REPO = Path(__file__).resolve().parents[3]

#: Where exceptions are recorded. Owned by CODEOWNERS, because adding a line here ships a flaw.
EXCEPTIONS: Final = "ops/security/vulnerability-exceptions.json"

#: The longest an exception may run before somebody has to look again.
LONGEST_EXCEPTION: Final = timedelta(days=90)

FAILING_SEVERITY: Final = "CRITICAL"

AN_EXCEPTION_SAYS_WHY_AND_ENDS: Final = (
    "An exception is a vulnerability id, the package it was found in, the reason it may ship, the "
    "day it was recorded and the day it ends, at most ninety days later. One missing any of those "
    "is refused as a record, and one past its end no longer excepts anything, so the build goes "
    "red on the day somebody promised to look again rather than never."
)

A_LOCK_THE_SCAN_DID_NOT_READ_IS_A_FAILURE: Final = (
    "Trivy lists the files it recognised and is silent about the rest, so a lockfile it could not "
    "read looks exactly like a lockfile with no vulnerabilities. Every lock the dependency policy "
    "reads has to be a target of the lock scan, or the scan has proved nothing about it."
)


@dataclass(frozen=True)
class Finding:
    vulnerability: str
    package: str
    version: str
    severity: str
    target: str
    fixed_in: str


@dataclass(frozen=True)
class RecordedException:
    """One recorded exception to the critical rule."""

    vulnerability: str
    package: str
    reason: str
    recorded: date
    ends: date


def findings_in(report: Mapping[str, Any]) -> tuple[Finding, ...]:
    """Every vulnerability in one Trivy JSON report."""
    found: list[Finding] = []
    for result in report.get("Results") or ():
        for one in result.get("Vulnerabilities") or ():
            found.append(
                Finding(
                    vulnerability=str(one.get("VulnerabilityID", "")),
                    package=str(one.get("PkgName", "")),
                    version=str(one.get("InstalledVersion", "")),
                    severity=str(one.get("Severity", "UNKNOWN")).upper(),
                    target=str(result.get("Target", "")),
                    fixed_in=str(one.get("FixedVersion") or ""),
                )
            )
    return tuple(found)


def targets_in(report: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(str(result.get("Target", "")) for result in report.get("Results") or ())


def unread_locks(report: Mapping[str, Any], locks: Iterable[str]) -> tuple[str, ...]:
    """Locks the scan names no result for. See `A_LOCK_THE_SCAN_DID_NOT_READ_IS_A_FAILURE`."""
    targets = {target.replace("\\", "/").removeprefix("./") for target in targets_in(report)}
    return tuple(sorted(lock for lock in locks if lock not in targets))


def read_exceptions(
    document: Mapping[str, Any],
) -> tuple[tuple[RecordedException, ...], tuple[str, ...]]:
    """The valid exceptions, and a sentence for each entry refused as a record."""
    valid: list[RecordedException] = []
    refused: list[str] = []
    for index, entry in enumerate(document.get("exceptions") or ()):
        try:
            record = RecordedException(
                vulnerability=str(entry["vulnerability"]).strip(),
                package=str(entry["package"]).strip(),
                reason=str(entry["reason"]).strip(),
                recorded=date.fromisoformat(str(entry["recorded"])),
                ends=date.fromisoformat(str(entry["ends"])),
            )
        except (KeyError, TypeError, ValueError) as missing:
            refused.append(f"exception {index} is not a record: {missing!r}")
            continue
        if not (record.vulnerability and record.package and record.reason):
            refused.append(f"exception {index} names no vulnerability, package or reason")
        elif record.ends <= record.recorded or record.ends - record.recorded > LONGEST_EXCEPTION:
            refused.append(
                f"exception {index} ({record.vulnerability}) runs from {record.recorded} to "
                f"{record.ends}; an exception ends after it starts and within 90 days"
            )
        else:
            valid.append(record)
    return tuple(valid), tuple(refused)


@dataclass(frozen=True)
class Verdict:
    failing: tuple[Finding, ...]
    excepted: tuple[Finding, ...]
    lapsed: tuple[RecordedException, ...]
    below: int
    record_refusals: tuple[str, ...]
    unread: tuple[str, ...]

    @property
    def passes(self) -> bool:
        return not (self.failing or self.record_refusals or self.unread)


def judge(
    findings: Iterable[Finding],
    exceptions: Iterable[RecordedException],
    *,
    today: date,
    record_refusals: Sequence[str] = (),
    unread: Sequence[str] = (),
) -> Verdict:
    recorded = tuple(exceptions)
    live = [one for one in recorded if today <= one.ends]
    lapsed = tuple(one for one in recorded if today > one.ends)
    failing: list[Finding] = []
    excepted: list[Finding] = []
    below = 0
    for finding in findings:
        if finding.severity != FAILING_SEVERITY:
            below += 1
        elif any(
            one.vulnerability == finding.vulnerability and one.package == finding.package
            for one in live
        ):
            excepted.append(finding)
        else:
            failing.append(finding)
    return Verdict(
        tuple(failing), tuple(excepted), lapsed, below, tuple(record_refusals), tuple(unread)
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m brain.ops.vulnerabilities")
    parser.add_argument("--locks", type=Path, required=True, help="Trivy JSON over the repository")
    parser.add_argument("--image", type=Path, required=True, help="Trivy JSON over the image")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    arguments = parser.parse_args(argv)

    locks = json.loads(arguments.locks.read_text(encoding="utf-8"))
    image = json.loads(arguments.image.read_text(encoding="utf-8"))
    recorded = json.loads((REPO / EXCEPTIONS).read_text(encoding="utf-8"))
    exceptions, refusals = read_exceptions(recorded)
    verdict = judge(
        [*findings_in(locks), *findings_in(image)],
        exceptions,
        today=arguments.today,
        record_refusals=refusals,
        unread=unread_locks(locks, [*PYTHON_LOCKS, *NPM_LOCKS]),
    )
    for lock in verdict.unread:
        print(f"refused: the scan read no result for {lock}")
    for line in verdict.record_refusals:
        print(f"refused: {line}")
    for gone in verdict.lapsed:
        print(f"note: the exception for {gone.vulnerability} in {gone.package} ended {gone.ends}")
    for one in verdict.excepted:
        print(f"excepted: {one.vulnerability} {one.package} {one.version} in {one.target}")
    for one in verdict.failing:
        print(
            f"CRITICAL: {one.vulnerability} {one.package} {one.version} in {one.target}"
            f" (fixed in {one.fixed_in or 'no release yet'})"
        )
    print(f"note: {verdict.below} finding(s) below critical")
    print(f"{'ok' if verdict.passes else 'FAIL'}: vulnerability scan")
    return 0 if verdict.passes else 1


if __name__ == "__main__":
    sys.exit(main())
