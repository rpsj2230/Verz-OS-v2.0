"""Where the evidence that the invariant suite passed is kept, and what it proves.

`M37.4.1.2` asks for the invariant suite green, evidenced. **Green was already true and
evidenced was not.** `ci.yml` has run `tests/invariants` on every push, and a red run stops the
deploy, so on any commit that reached a server the suite had passed. But the only record of that
was a tick in GitHub's interface and a line of scrollback saying how many passed. A tick is a
claim about a run rather than a record of what the run contained, and a log is prose: a reviewer
asking which rules were checked, at which commit, and whether any of them did not run, is
answered by somebody reading it and nobody checking it.

So the invariants step writes a JUnit report and the job keeps it as a workflow artefact named
for the commit. **Where the evidence is:** the CI run for a commit, artefact
`invariants-<full commit sha>`, holding `invariants.xml`. **What it proves:** at that commit, on
the runner, every test under `tests/invariants` was collected and run, each one by name with how
long it took, and the counts of failures, errors and skips are fields in a file rather than a
sentence about one.

**The report is kept when the suite fails too.** The default condition on a step is that every
step before it passed, which uploads a report only on the runs where it says nothing interesting
and loses the one naming the rule that broke. See `Gap.LOST_WHEN_RED`.

**A report that ran nothing is not green, and neither is one with a skip in it.** pytest exits
zero when every test it collected skipped, and a marker that skips without a database is exactly
how that would happen here, because the job that runs the invariants has none. Measured on
2026-09-15 with `DATABASE_URL` unset: 1332 invariants, none skipped, so the refusal is green on
arrival and fires on the first day an invariant starts skipping in the job whose report is the
evidence. The job runs this module over the report it has just written, so the reading is a
step rather than a promise. See `Refusal.SKIPPED`.

**The workflow is checked as data.** `evidence_gaps` takes the parsed `ci.yml` and names every
way it could run the suite and still keep nothing a reviewer could use: no report written, a
report nobody reads, a report never uploaded, an upload of a different file, an artefact whose
name does not carry the commit, a missing file uploaded as a success, a lifetime inherited from a
repository setting, and a suite allowed to fail without failing the run that Deploy waits on.
Each is a member of `Gap`, so a test asserts on which gap was found rather than on a sentence.

What it does not prove is `WHAT_THE_EVIDENCE_DOES_NOT_PROVE`, and the two halves that matter are
that an artefact expires and that a report is about a commit rather than about a server.

Rejected: committing the report into the repository, which is the most durable place and the
wrong one. A report committed by the run it describes changes the commit it names, so it is
always about the commit before it; and a push from CI would deploy. Rejected as well: a status
badge, which is a live claim about the latest run and says nothing about the commit a client
accepted.

Task ids: M37.4.1.2
"""

from __future__ import annotations

import enum
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from xml.etree import ElementTree

#: The directory the evidence is about. `tests/unit/test_ci_workflow.py` holds the step that
#: runs it to the same four tokens, so the two cannot name different suites.
SUITE: Final = "tests/invariants"

#: Where the suite step writes its report, relative to the checkout.
REPORT_PATH: Final = "evidence/invariants.xml"

#: The artefact's name before the commit. See `artefact_name`.
ARTEFACT_PREFIX: Final = "invariants-"

#: How the workflow spells the commit a run is at.
COMMIT_EXPRESSION: Final = "${{ github.sha }}"

#: The action that keeps a file after the runner is destroyed.
UPLOAD_ACTION: Final = "actions/upload-artifact"

#: The module CI runs over the report. Held equal to this module's own name by test.
READER_MODULE: Final = "brain.ops.invariant_evidence"

#: How long the artefact is kept, stated in the workflow rather than inherited.
#:
#: Ninety days is the longest GitHub keeps an artefact without a change to the repository's
#: own settings. Stated on the step because an inherited lifetime is one somebody can shorten in
#: a settings page, with nothing in the repository changing and every run still green.
RETENTION_DAYS: Final = 90

#: What a kept report is not evidence of. Kept beside the constants rather than only in the
#: docstring, because the figure in it has to agree with `RETENTION_DAYS` and a test says so.
WHAT_THE_EVIDENCE_DOES_NOT_PROVE: Final = (
    "The report is about a commit, not about a server. It says the invariants passed at that "
    "commit on the runner; which commit a server is running is answered by the image tag the "
    "deploy publishes, and the two are joined by the commit rather than by this file. And it "
    "expires: an artefact is deleted 90 days after the run that made it, so evidence a client "
    "accepts has to be downloaded and kept by whoever accepts it, which is an act on the day "
    "and not something a commit can do."
)


class Gap(enum.StrEnum):
    """Every way the workflow can run the suite and still keep nothing a reviewer could use."""

    NO_SUITE = (
        "no live step runs the invariant suite, so there is no run for a report to be evidence "
        "about"
    )
    NO_REPORT = (
        "the step running the invariant suite writes no JUnit report at the report path, so the "
        "run leaves a log and nothing a reviewer can check"
    )
    ALLOWED_TO_FAIL = (
        "the invariant suite may fail without failing the run, and Deploy waits on the run's "
        "conclusion, so a broken rule would deploy with a report saying so"
    )
    NOT_READ = (
        "nothing reads the report after the suite writes it, and pytest exits zero when every "
        "test skipped, so a report of nothing having run would be kept as green"
    )
    NOT_UPLOADED = "no step after the suite uploads the report, so it is deleted with the runner"
    WRONG_FILE = "the upload keeps a different file from the one the suite writes"
    NAME_WITHOUT_COMMIT = (
        "the artefact's name does not carry the commit, so a kept report cannot be matched to "
        "the commit it is evidence about"
    )
    EMPTY_UPLOAD_PASSES = (
        "a missing report is uploaded as a warning and a success, so a run that wrote nothing "
        "looks exactly like a run that kept its evidence"
    )
    LOST_WHEN_RED = (
        "the report is kept only when every step before it passed, which loses the one report "
        "that names the rule that broke"
    )
    RETENTION_NOT_STATED = (
        "the artefact's lifetime is not the one stated here, so it is whatever a settings page "
        "says on the day"
    )


class Refusal(enum.StrEnum):
    """Every reason a report the suite wrote is not evidence that the invariants hold."""

    NOTHING_RAN = "the report records no tests at all, and a suite that ran nothing proves nothing"
    FAILED = "the report records a failing invariant"
    ERRORED = "the report records an error, which is an invariant that could not be asked"
    SKIPPED = "the report records a skipped invariant, and a skipped rule is not a rule that held"


class ReportError(ValueError):
    """Raised when a file is not a pytest JUnit report at all."""


@dataclass(frozen=True)
class Reading:
    """The four counts a pytest JUnit report carries, summed over its test suites."""

    tests: int
    failures: int
    errors: int
    skipped: int

    def refusals(self) -> tuple[Refusal, ...]:
        """Every reason this report is not evidence, in a fixed order. Empty when it is."""
        found: list[Refusal] = []
        if self.tests < 1:
            found.append(Refusal.NOTHING_RAN)
        if self.failures:
            found.append(Refusal.FAILED)
        if self.errors:
            found.append(Refusal.ERRORED)
        if self.skipped:
            found.append(Refusal.SKIPPED)
        return tuple(found)


def artefact_name(commit: str) -> str:
    """The name the report is kept under for one commit.

    A blank commit is refused rather than producing `invariants-`, which is a name every run
    would share and each would overwrite the last under.
    """
    if not commit.strip():
        msg = "an artefact named for no commit is evidence about every commit and so about none"
        raise ValueError(msg)
    return f"{ARTEFACT_PREFIX}{commit}"


def evidence_gaps(workflow: Mapping[Any, Any]) -> tuple[Gap, ...]:
    """Every way this parsed workflow runs the invariant suite and keeps nothing usable.

    The suite step is found by what it runs, never by its name: a step renamed in a tidy-up is
    the same step, and a step named "Invariants" that runs something else is not. A commented
    line runs nothing and does not count. Only the first step running the suite is judged,
    because the report path is one file and a second writer would overwrite the first.
    """
    for job in (workflow.get("jobs") or {}).values():
        steps: list[Mapping[str, Any]] = list(job.get("steps") or [])
        for index, step in enumerate(steps):
            lines = [line for line in _live_lines(step.get("run")) if _runs_the_suite(line)]
            if lines:
                return _gaps_after(job, steps, index, lines)
    return (Gap.NO_SUITE,)


def read_report(text: str) -> Reading:
    """The counts in a pytest JUnit report, refusing a file that is not one."""
    try:
        # The report is one this job's own pytest wrote a step earlier, and the expat bundled
        # with CPython 3.13 refuses the entity expansion the lint rule is about.
        root = ElementTree.fromstring(text)  # noqa: S314
    except ElementTree.ParseError as error:
        msg = f"the report is not well-formed XML: {error}"
        raise ReportError(msg) from error
    suites = root.findall("testsuite")
    if root.tag != "testsuites" or not suites:
        msg = "the report has no <testsuites> holding a <testsuite>, so pytest did not write it"
        raise ReportError(msg)
    return Reading(
        tests=_total(suites, "tests"),
        failures=_total(suites, "failures"),
        errors=_total(suites, "errors"),
        skipped=_total(suites, "skipped"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Read one report and exit non-zero unless it is evidence that the invariants hold."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(f"usage: python -m {READER_MODULE} <report>", file=sys.stderr)
        return 2
    try:
        reading = read_report(Path(args[0]).read_text(encoding="utf-8"))
    except (OSError, ReportError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    print(
        f"{reading.tests} invariant(s): {reading.failures} failed, {reading.errors} errored, "
        f"{reading.skipped} skipped"
    )
    refusals = reading.refusals()
    for refusal in refusals:
        print(f"refused: {refusal}", file=sys.stderr)
    return 1 if refusals else 0


def _gaps_after(
    job: Mapping[str, Any],
    steps: Sequence[Mapping[str, Any]],
    index: int,
    lines: Sequence[str],
) -> tuple[Gap, ...]:
    gaps: list[Gap] = []
    if not any(f"--junitxml={REPORT_PATH}" in line.split() for line in lines):
        gaps.append(Gap.NO_REPORT)
    # Absent or false is the only safe value. An expression is refused too: a condition that
    # is false today is a condition, and the rule it would switch off is every invariant.
    if any(owner.get("continue-on-error") not in (None, False) for owner in (job, steps[index])):
        gaps.append(Gap.ALLOWED_TO_FAIL)
    later = steps[index + 1 :]
    reader = f"-m {READER_MODULE} {REPORT_PATH}"
    if not any(
        reader in " ".join(line.split()) for step in later for line in _live_lines(step.get("run"))
    ):
        gaps.append(Gap.NOT_READ)
    uploads = [step for step in later if str(step.get("uses", "")).startswith(f"{UPLOAD_ACTION}@")]
    if not uploads:
        gaps.append(Gap.NOT_UPLOADED)
        return tuple(gaps)
    upload = uploads[0]
    given: Mapping[str, Any] = upload.get("with") or {}
    if given.get("path") != REPORT_PATH:
        gaps.append(Gap.WRONG_FILE)
    if given.get("name") != artefact_name(COMMIT_EXPRESSION):
        gaps.append(Gap.NAME_WITHOUT_COMMIT)
    if given.get("if-no-files-found") != "error":
        gaps.append(Gap.EMPTY_UPLOAD_PASSES)
    if given.get("retention-days") != RETENTION_DAYS:
        gaps.append(Gap.RETENTION_NOT_STATED)
    condition = str(upload.get("if", ""))
    if "always()" not in condition and "!cancelled()" not in condition:
        gaps.append(Gap.LOST_WHEN_RED)
    return tuple(gaps)


def _live_lines(run: object) -> tuple[str, ...]:
    """The lines of a `run:` that execute. A commented line is a gate somebody switched off.

    A step with no `run:` arrives as None and reads as the one line "None", which runs no
    suite and names no reader, so it needs no branch of its own.
    """
    stripped = (line.strip() for line in str(run).splitlines())
    return tuple(line for line in stripped if line and not line.startswith("#"))


def _runs_the_suite(line: str) -> bool:
    tokens = line.split()
    return "pytest" in tokens and SUITE in tokens[tokens.index("pytest") + 1 :]


def _total(suites: Sequence[ElementTree.Element], attribute: str) -> int:
    try:
        return sum(int(suite.attrib[attribute]) for suite in suites)
    except (KeyError, ValueError) as error:
        msg = f"a <testsuite> has no readable {attribute!r} count, so pytest did not write it"
        raise ReportError(msg) from error


if __name__ == "__main__":  # pragma: no cover - the entry point CI runs
    raise SystemExit(main())
