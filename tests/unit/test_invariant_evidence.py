"""The invariant suite's evidence, asserted against the parsed workflow and real pytest reports.

M37.4.1.2. Two halves, and each needs the other. `evidence_gaps` is asked of `ci.yml` as
parsed YAML, so a commented step or a renamed one is judged by what runs; every refusal it can
make is shown firing against a workflow that differs from a sound one in exactly that respect,
which is what stops a function that refuses everything from satisfying the suite. And
`read_report` is asked of reports pytest itself wrote, never of XML typed here: a reader tested
only against hand-built input is a test of whoever wrote the input.

Task ids: M37.4.1.2
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

import brain.ops.invariant_evidence as evidence
from brain.ops.invariant_evidence import (
    ARTEFACT_PREFIX,
    READER_MODULE,
    REPORT_PATH,
    RETENTION_DAYS,
    SUITE,
    WHAT_THE_EVIDENCE_DOES_NOT_PROVE,
    Gap,
    Reading,
    Refusal,
    ReportError,
    artefact_name,
    evidence_gaps,
    main,
    read_report,
)

REPO = Path(__file__).resolve().parents[2]


def _ci() -> dict[Any, Any]:
    parsed: dict[Any, Any] = yaml.safe_load(
        (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    return parsed


def _sound() -> dict[str, Any]:
    """A workflow with nothing wrong with it, written independently of `ci.yml`."""
    return {
        "jobs": {
            "static": {
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {
                        "id": "invariants",
                        "run": f"uv run pytest {SUITE} -q --junitxml={REPORT_PATH}",
                    },
                    {"run": f"uv run python -m {READER_MODULE} {REPORT_PATH}"},
                    {
                        "if": "${{ !cancelled() && steps.invariants.outcome != 'skipped' }}",
                        "uses": "actions/upload-artifact@v4",
                        "with": {
                            "name": "invariants-${{ github.sha }}",
                            "path": REPORT_PATH,
                            "if-no-files-found": "error",
                            "retention-days": RETENTION_DAYS,
                        },
                    },
                ]
            }
        }
    }


def _steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = workflow["jobs"]["static"]["steps"]
    return steps


# ------------------------------------------------------------------ the workflow itself
def test_the_ci_workflow_keeps_a_readable_report_of_the_invariant_suite_for_every_commit() -> None:
    """The leaf, asserted against the file CI runs. Delete this and the upload step can be
    dropped in a tidy-up, CI goes on passing the invariants, and the evidence stops existing
    with nothing red anywhere."""
    assert evidence_gaps(_ci()) == ()


def test_the_artefact_the_workflow_keeps_is_named_for_the_commit_the_run_is_at() -> None:
    """Asserted by resolving the workflow's own expression rather than comparing against the
    prefix constant, which would compare the constant with itself. Delete this and the name
    can become a fixed string that every run overwrites, leaving one report about whichever
    commit ran last."""
    sha = "0123456789abcdef0123456789abcdef01234567"
    upload = next(
        step
        for step in _ci()["jobs"]["static"]["steps"]
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    )

    resolved = upload["with"]["name"].replace("${{ github.sha }}", sha)

    assert resolved == artefact_name(sha)
    assert resolved.endswith(sha)
    assert resolved != artefact_name("fedcba9876543210fedcba9876543210fedcba98")


def test_the_reader_ci_runs_is_this_module() -> None:
    """`READER_MODULE` is the name the workflow invokes. Delete this and the constant can drift
    from the module's real name, the workflow can be edited to match the constant, and the step
    fails with a missing module rather than reading anything."""
    assert evidence.__name__ == READER_MODULE


def test_the_stated_lifetime_is_the_one_the_workflow_sets() -> None:
    """The sentence a reviewer reads says how long the evidence lasts. Delete this and the
    retention can change in one place while the explanation goes on stating the old figure."""
    assert f"{RETENTION_DAYS} days" in WHAT_THE_EVIDENCE_DOES_NOT_PROVE
    assert RETENTION_DAYS <= 90, "GitHub keeps an artefact for at most 90 days by default"


# ------------------------------------------------------------ positive and refusal siblings
def test_a_sound_workflow_has_no_gaps() -> None:
    """The sibling every refusal below needs. Delete this and `evidence_gaps` could report a
    gap for every workflow, and each refusal test would still pass."""
    assert evidence_gaps(_sound()) == ()


def test_a_workflow_that_never_runs_the_suite_is_refused() -> None:
    """Delete this and a workflow with the invariants step removed reports no gaps, because
    there would be no step for any other check to be asked about."""
    workflow = _sound()
    _steps(workflow)[1]["run"] = "uv run pytest tests/unit -q --junitxml=evidence/invariants.xml"

    assert evidence_gaps(workflow) == (Gap.NO_SUITE,)


def test_a_commented_out_suite_runs_nothing_and_is_refused() -> None:
    """A commented line in a `run:` block is a disabled gate that still reads as one. Delete
    this and `# uv run pytest tests/invariants` satisfies the check."""
    workflow = _sound()
    _steps(workflow)[1]["run"] = f"# uv run pytest {SUITE} --junitxml={REPORT_PATH}"

    assert evidence_gaps(workflow) == (Gap.NO_SUITE,)


def test_a_suite_step_that_writes_no_report_is_refused() -> None:
    """Delete this and the report flag can be removed from the step, the upload then fails on
    a missing file only if somebody also kept that setting, and the run keeps a log alone."""
    workflow = _sound()
    _steps(workflow)[1]["run"] = f"uv run pytest {SUITE} -q"

    assert evidence_gaps(workflow) == (Gap.NO_REPORT,)


@pytest.mark.parametrize("owner", ["job", "step"])
def test_a_suite_allowed_to_fail_is_refused(owner: str) -> None:
    """`continue-on-error` on the step or on its job turns a broken rule into a green run, and
    Deploy reads the run's conclusion. Delete this and one line lets a failing invariant ship."""
    workflow = _sound()
    target = workflow["jobs"]["static"] if owner == "job" else _steps(workflow)[1]
    target["continue-on-error"] = True

    assert evidence_gaps(workflow) == (Gap.ALLOWED_TO_FAIL,)


def test_a_report_nobody_reads_is_refused() -> None:
    """Delete this and the reading step can go, after which a run where every invariant skipped
    exits zero and its report is kept as the evidence of a green suite."""
    workflow = _sound()
    del _steps(workflow)[2]

    assert evidence_gaps(workflow) == (Gap.NOT_READ,)


def test_a_report_that_is_never_uploaded_is_refused() -> None:
    """Delete this and the upload can go, and the report is destroyed with the runner."""
    workflow = _sound()
    del _steps(workflow)[3]

    assert evidence_gaps(workflow) == (Gap.NOT_UPLOADED,)


def test_an_upload_placed_before_the_suite_has_run_is_refused() -> None:
    """An upload before the suite keeps a file that does not exist yet. Delete this and moving
    the step up satisfies a check that only asked whether an upload existed."""
    workflow = _sound()
    steps = _steps(workflow)
    steps.insert(1, steps.pop(3))

    assert evidence_gaps(workflow) == (Gap.NOT_UPLOADED,)


def test_an_upload_of_a_different_file_is_refused() -> None:
    """Delete this and the upload can keep a stale or unrelated file under the evidence's name."""
    workflow = _sound()
    _steps(workflow)[3]["with"]["path"] = "evidence/unit.xml"

    assert evidence_gaps(workflow) == (Gap.WRONG_FILE,)


def test_an_artefact_whose_name_does_not_carry_the_commit_is_refused() -> None:
    """Delete this and every run keeps its report under one name, so what survives is about
    whichever commit ran last rather than the one a client accepted."""
    workflow = _sound()
    _steps(workflow)[3]["with"]["name"] = "invariants"

    assert evidence_gaps(workflow) == (Gap.NAME_WITHOUT_COMMIT,)


def test_an_upload_that_accepts_a_missing_report_is_refused() -> None:
    """The action's default for a missing file is a warning and a green step. Delete this and a
    run that wrote nothing is indistinguishable from one that kept its evidence."""
    workflow = _sound()
    del _steps(workflow)[3]["with"]["if-no-files-found"]

    assert evidence_gaps(workflow) == (Gap.EMPTY_UPLOAD_PASSES,)


def test_an_artefact_lifetime_left_to_a_settings_page_is_refused() -> None:
    """Delete this and the lifetime can be dropped from the step, after which the evidence lasts
    as long as a repository setting somebody can change without a commit."""
    workflow = _sound()
    del _steps(workflow)[3]["with"]["retention-days"]

    assert evidence_gaps(workflow) == (Gap.RETENTION_NOT_STATED,)


def test_a_report_kept_only_when_the_suite_passed_is_refused() -> None:
    """Delete this and the condition can be dropped, and the one report that is ever lost is the
    one naming the invariant that broke."""
    workflow = _sound()
    del _steps(workflow)[3]["if"]

    assert evidence_gaps(workflow) == (Gap.LOST_WHEN_RED,)


def test_a_condition_that_keeps_the_report_only_on_success_is_refused() -> None:
    """**A surviving mutation found this.** The test above deletes the condition, and a check
    that accepted any condition at all passed it, so `if: ${{ success() }}` written out in full
    would have been accepted while doing exactly what an absent condition does. Delete this and
    the check can be reduced to "a condition exists"."""
    workflow = _sound()
    _steps(workflow)[3]["if"] = "${{ success() }}"

    assert evidence_gaps(workflow) == (Gap.LOST_WHEN_RED,)


def test_a_report_kept_whenever_the_run_was_not_cancelled_is_accepted() -> None:
    """Both spellings of "keep it when red" are accepted, not only the one the workflow uses.
    Delete this and the check could require one exact expression, which refuses `always()`,
    the form most people write."""
    workflow = _sound()
    _steps(workflow)[3]["if"] = "always()"

    assert evidence_gaps(workflow) == ()


def test_an_artefact_named_for_no_commit_is_refused() -> None:
    """Delete this and a blank commit produces the bare prefix, a name every run shares."""
    with pytest.raises(ValueError, match="no commit"):
        artefact_name("  ")
    assert artefact_name("abc") == f"{ARTEFACT_PREFIX}abc"


# ------------------------------------------------------ reports pytest actually wrote
def _report_of(tmp_path: Path, source: str) -> str:
    """Run pytest over one probe file and return the JUnit report it wrote.

    Configured by a file of its own so this repository's settings do not apply, which keeps
    the report about the probe rather than about whatever `addopts` says today.
    """
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_probe.py").write_text(source, encoding="utf-8")
    report = tmp_path / "report.xml"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(tmp_path / "pytest.ini"),
            "--rootdir",
            str(tmp_path),
            "-p",
            "no:cacheprovider",
            f"--junitxml={report}",
            str(tmp_path / "test_probe.py"),
        ],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=120,
    )
    return report.read_text(encoding="utf-8")


def test_a_report_of_a_suite_that_passed_is_evidence(tmp_path: Path) -> None:
    """The positive half of the reader, from a report pytest wrote. Delete this and
    `refusals` could refuse every report, which the refusal tests below would not notice."""
    reading = read_report(_report_of(tmp_path, "def test_holds():\n    assert True\n"))

    assert reading == Reading(tests=1, failures=0, errors=0, skipped=0)
    assert reading.refusals() == ()


def test_a_report_with_a_failing_invariant_is_refused(tmp_path: Path) -> None:
    """Delete this and the reader can ignore the failure count, and a red run's report reads as
    evidence that the rules held."""
    reading = read_report(_report_of(tmp_path, "def test_breaks():\n    assert False\n"))

    assert reading.refusals() == (Refusal.FAILED,)


def test_a_report_with_a_skipped_invariant_is_refused(tmp_path: Path) -> None:
    """pytest exits zero here, which is why the reader exists. Delete this and a suite whose
    rules all skipped without a database is kept as green."""
    source = "import pytest\n\ndef test_needs_a_database():\n    pytest.skip('no database')\n"
    reading = read_report(_report_of(tmp_path, source))

    assert reading.refusals() == (Refusal.SKIPPED,)


def test_a_report_of_a_suite_that_collected_nothing_is_refused(tmp_path: Path) -> None:
    """Delete this and an empty directory, or a suite narrowed to a file with no tests, reads as
    a clean report because every count in it is zero."""
    reading = read_report(_report_of(tmp_path, "VALUE = 1\n"))

    assert reading.refusals() == (Refusal.NOTHING_RAN,)


def test_a_report_with_an_invariant_that_could_not_be_collected_is_refused(tmp_path: Path) -> None:
    """A collection error is counted as an error, not a failure, and it means the rules in that
    file were never asked. Delete this and the reader can ignore errors."""
    reading = read_report(_report_of(tmp_path, "import module_that_is_not_there\n"))

    assert Refusal.ERRORED in reading.refusals()
    assert reading.failures == 0


@pytest.mark.parametrize(
    "text",
    [
        "not xml at all",
        "<testsuite tests='1' failures='0' errors='0' skipped='0'/>",
        "<report><testsuite tests='1' failures='0' errors='0' skipped='0'/></report>",
        "<testsuites></testsuites>",
        "<testsuites><testsuite failures='0' errors='0' skipped='0'/></testsuites>",
    ],
)
def test_a_file_pytest_did_not_write_is_not_read_as_a_report(text: str) -> None:
    """Delete this and a malformed or foreign file is read as zeroes, which is a report of
    nothing having failed."""
    with pytest.raises(ReportError):
        read_report(text)


def test_the_command_ci_runs_exits_zero_only_on_evidence(tmp_path: Path) -> None:
    """The step's exit status is what stops the job, so both directions are asked of `main`.
    Delete this and the entry point could print the refusals and exit zero, which is a reading
    step that reads and gates nothing."""
    passed = tmp_path / "passed"
    skipped = tmp_path / "skipped"
    passed.mkdir()
    skipped.mkdir()
    good = passed / "good.xml"
    bad = skipped / "bad.xml"
    good.write_text(_report_of(passed, "def test_holds():\n    assert True\n"), encoding="utf-8")
    bad.write_text(
        _report_of(skipped, "import pytest\n\ndef test_s():\n    pytest.skip('x')\n"),
        encoding="utf-8",
    )

    assert main([str(good)]) == 0
    assert main([str(bad)]) == 1
    assert main([str(tmp_path / "absent.xml")]) == 1
    assert main([]) == 2
