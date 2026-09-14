"""The restore drill page, held to what following it writes and what the product makes of that.

**M34.3.3.4** asks for a restore drill procedure. The procedure is shell on a client's server and
nobody has run it, so what is held is its output: the checks a drill record must answer, the
fields it must carry, the figures the schedule depends on, and the verdict
`brain.ops.recovery.verification_of` reaches from the page's own worked examples. The page also
states which pieces of a drill exist, and those rows are observed from the repository here.

Every refusal is produced by breaking the real page, one table cell or one example at a time, so
the check that passes the page and the checks that refuse it are about the same document.

Task ids: M34.3.3.4
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from brain.console.screens import screen
from brain.demo import DEMO_SOURCE
from brain.ops import backup_manifest, install_docs
from brain.ops.backup_manifest import DRILL_SUFFIX
from brain.ops.install_docs import (
    DRILL_CHECKS_MARKER,
    DRILL_COPY_EXAMPLE_MARKER,
    DRILL_FAILING_EXAMPLE_MARKER,
    DRILL_FIELDS_MARKER,
    DRILL_FIGURES_MARKER,
    DRILL_PASSING_EXAMPLE_MARKER,
    DRILL_PIECES_MARKER,
    InstallDocsError,
    drill_figures,
    drill_procedure_gaps,
    json_after,
)
from brain.ops.recovery import DRILL_INTERVAL_DAYS, verification_of
from brain.tools.startup import build_registry

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "docs" / "install" / "restore-drill.md"


def page() -> str:
    return PAGE.read_text(encoding="utf-8")


def runnable() -> frozenset[str]:
    """Every module under `src` that runs as a command, read off its `__main__` guard."""
    src = REPO / "src"
    return frozenset(
        ".".join(path.relative_to(src).with_suffix("").parts)
        for path in src.rglob("*.py")
        if 'if __name__ == "__main__":' in path.read_text(encoding="utf-8")
    )


def pieces_today() -> dict[str, bool]:
    """Whether each piece of a drill exists, observed from the repository rather than declared.

    A script performing a drill writes a drill record, so it names the suffix. A timer scheduling
    one names a drill. A console control is a registered tool, and the recovery screen can be
    opened when its tool is registered.
    """
    files = [one for one in (REPO / "ops").rglob("*") if one.is_file() and one.suffix != ".md"]
    tools = frozenset(build_registry(source=DEMO_SOURCE).names())
    return {
        "A script that performs a drill": any(
            DRILL_SUFFIX in one.read_text(encoding="utf-8", errors="ignore") for one in files
        ),
        "A timer that schedules a drill": any(
            one.suffix == ".timer"
            and "drill" in f"{one.name}{one.read_text(encoding='utf-8', errors='ignore')}".lower()
            for one in files
        ),
        "A console control that starts a drill": any("drill" in name for name in tools),
        "The recovery screen can be opened": screen("recovery").read.tool in tools,
        "A reader that turns a drill record into a verdict": callable(
            getattr(backup_manifest, "read_drills", None)
        ),
    }


def gaps(text: str, **overrides: Any) -> tuple[str, ...]:
    arguments: dict[str, Any] = {"pieces": pieces_today(), "runnable": runnable()}
    arguments.update(overrides)
    return drill_procedure_gaps(text, **arguments)


def with_example(text: str, marker: str, document: Any) -> str:
    """The page with the JSON block after `marker` replaced by `document`."""
    block = re.compile(re.escape(marker) + r"\n```json\n.*?\n```", re.S)
    replaced, count = block.subn(
        lambda _: f"{marker}\n```json\n{json.dumps(document, indent=2)}\n```", text
    )
    assert count == 1
    return replaced


def once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


# ------------------------------------------------------------------------------ the real page
def test_the_restore_drill_page_agrees_with_what_a_drill_record_must_be_and_what_exists() -> None:
    """**M34.3.3.4.** The procedure is prose and says so. What a person following it produces is
    held: three questions in the order the verdict requires, the fields the reader requires, the
    figures, the examples as the product reads them, and which pieces of a drill have a machine.

    Delete this and the page goes on teaching a record format the product has since stopped
    reading, and the recovery panel says never verified about an install that rehearses weekly."""
    assert gaps(page()) == ()


def test_the_example_that_does_not_verify_fails_on_the_permission_canary_alone() -> None:
    """The page's lesson is that a load without the roles brings back every row and none of the
    policies. Delete this and the failing example can fail for any reason at all, including one
    that teaches nothing, with the agreement test above still green."""
    verdict = verification_of(
        backup_manifest.drill_from(
            json_after(page(), DRILL_FAILING_EXAMPLE_MARKER), where="the failing example"
        )
    )

    assert verdict.verified is False
    assert len(verdict.shortfalls) == 1
    assert verdict.shortfalls[0].startswith("permission_canary ran and did not pass")


def test_the_figures_are_read_off_the_modules_that_decide_them() -> None:
    """Delete this and `drill_figures` can state its own numbers, which the page would then agree
    with and the schedule would not. The interval is compared against the rehearsal module's
    value and the suffix against the file a drill record must end in, both imported here."""
    figures = dict(drill_figures())

    assert figures["Days between rehearsals"] == str(DRILL_INTERVAL_DAYS)
    assert figures["A drill record's name ends"] == DRILL_SUFFIX
    assert int(figures["Days between rehearsals"]) < int(figures["Days a copy is kept"])


def test_every_figure_moves_when_the_value_it_is_read_from_moves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Written after a mutation survived.** `drill_figures` stating the interval as the literal
    `"7"` passed every test, because the test above compares the figure against the constant it
    was read from and both said 7. A figure typed in agrees with the schedule on the day it is
    typed and with nothing afterwards, so each source is moved here and the figure has to follow.

    Delete this and any figure on the page can become a number somebody typed, with the page, the
    check and the test all agreeing about a schedule that has since changed."""
    monkeypatch.setattr(install_docs, "DRILL_INTERVAL_DAYS", 3)
    monkeypatch.setattr(install_docs, "BACKUP_RETENTION_DAYS", 90)
    monkeypatch.setattr(install_docs, "MANIFEST_SUFFIX", ".copy.json")
    monkeypatch.setattr(install_docs, "DRILL_SUFFIX", ".rehearsal.json")

    assert dict(drill_figures()) == {
        "Days between rehearsals": "3",
        "Days a copy is kept": "90",
        "A copy's manifest name ends": ".copy.json",
        "A drill record's name ends": ".rehearsal.json",
    }


# ------------------------------------------------------------------------------ the checks table
def test_a_check_left_out_or_out_of_order_is_a_finding() -> None:
    """Delete this and a page listing two of the three questions is agreed with, and everybody
    following it writes a record that can never verify."""
    real = page()
    canary = next(line for line in real.splitlines() if line.startswith("| `permission_canary` |"))
    smoke = next(line for line in real.splitlines() if line.startswith("| `smoke_query` |"))

    missing = once(real, canary + "\n", "")
    swapped = once(once(real, canary, "CANARY"), smoke, canary).replace("CANARY", smoke)

    assert gaps(missing) == (
        "the page lists the checks ['schema_complete', 'smoke_query'] and a drill verifies only "
        "on ['schema_complete', 'smoke_query', 'permission_canary'], in that order, so a runner "
        "following the page writes a record that cannot verify",
    )
    assert len(gaps(swapped)) == 1


def test_a_command_that_is_not_a_runnable_module_is_a_finding() -> None:
    """Delete this and a renamed module leaves the page telling somebody mid-drill to run a
    command that prints `No module named`."""
    broken = once(
        page(),
        "| `python -m brain.ops.schema_check <scratch database url>` |",
        "| `python -m brain.ops.schema_checker <scratch database url>` |",
    )

    assert gaps(broken) == (
        "schema_complete: the page says to run python -m brain.ops.schema_checker, and no module "
        "of that name runs as a command",
    )
    assert "brain.ops.schema_check" in runnable()


def test_a_row_too_short_to_read_is_a_finding_in_every_table() -> None:
    """Delete this and a row that lost its cells is skipped, so the table reads as shorter
    rather than broken."""
    real = page()
    for marker, header in (
        (DRILL_CHECKS_MARKER, "| Check | What it asks | How |\n| --- | --- | --- |\n"),
        (DRILL_FIELDS_MARKER, "| Field | Where | What to write |\n| --- | --- | --- |\n"),
        (DRILL_FIGURES_MARKER, "| Figure | Value |\n| --- | --- |\n"),
        (DRILL_PIECES_MARKER, "| Piece | Exists today |\n| --- | --- |\n"),
    ):
        broken = once(real, f"{marker}\n\n{header}", f"{marker}\n\n{header}| lonely |\n")
        assert any("1 cell(s)" in one for one in gaps(broken)), marker


# ------------------------------------------------------------------------------ the fields table
def test_a_field_the_reader_requires_left_out_and_a_verified_field_asked_for_are_findings() -> None:
    """The field the obvious format carries and this one refuses is `verified`, because a runner
    that never asked the canary writes true. Delete this and the page can ask for it."""
    real = page()
    scratch = next(line for line in real.splitlines() if line.startswith("| `into_scratch` |"))
    broken = once(real, scratch, "| `verified` | the record | whether it verified |")

    assert gaps(broken) == (
        "into_scratch on the record: a drill record is refused without it and the page does not "
        "ask for it",
        "verified on the record: the page asks for a field no reader reads, so a runner writes it "
        "and nothing believes it",
    )


def test_a_field_placed_on_the_wrong_level_is_a_finding() -> None:
    """Delete this and the page can put `passed` on the record, where a runner writes one flag for
    the whole drill and the reader refuses every record."""
    broken = once(page(), "| `passed` | each check |", "| `passed` | the record |")

    assert len(gaps(broken)) == 2


# ------------------------------------------------------------------------------ figures and pieces
def test_a_figure_that_disagrees_and_one_nothing_declares_are_findings() -> None:
    """Delete this and the rehearsal interval on the page can drift from the one that decides
    when a drill is owed."""
    figures = (*drill_figures()[1:], ("Days between rehearsals", "14"), ("Something else", "1"))

    assert gaps(page(), figures=figures) == (
        "Something else: the page does not state this figure",
        "Days between rehearsals: the page says '7' and the repository says '14'",
    )
    assert gaps(page(), figures=drill_figures()[1:]) == (
        "Days between rehearsals: a figure nothing here declares, which reads as one it does",
    )


def test_a_piece_built_since_the_page_was_written_is_a_finding() -> None:
    """`A_PROCEDURE_THAT_DOES_NOT_SAY_WHAT_IS_MISSING_READS_AS_AUTOMATION`, and the day it fires
    is the day a drill script lands. Delete this and the page goes on telling somebody to do by
    hand what a timer already does."""
    built = {**pieces_today(), "A script that performs a drill": True}

    assert gaps(page(), pieces=built) == (
        "A script that performs a drill: the page says 'no' and the repository says 'yes'",
    )


# ------------------------------------------------------------------------------ the examples
def test_the_two_drill_examples_labelled_the_wrong_way_round_are_both_findings() -> None:
    """Delete this and the example a reader copies as the good one can be the one that fails the
    canary, with the page describing it as verified."""
    real = page()
    swapped = (
        real.replace(DRILL_PASSING_EXAMPLE_MARKER, "PLACEHOLDER")
        .replace(DRILL_FAILING_EXAMPLE_MARKER, DRILL_PASSING_EXAMPLE_MARKER)
        .replace("PLACEHOLDER", DRILL_FAILING_EXAMPLE_MARKER)
    )

    found = gaps(swapped)

    assert found[0].startswith(
        "the drill record that verifies: the product reads it as not verified; "
        "permission_canary ran and did not pass"
    )
    assert found[1] == "the drill record that does not verify: the product reads it as verified"
    assert len(found) == 2


def test_a_drill_of_another_copy_or_of_one_not_yet_taken_is_a_finding() -> None:
    """Delete this and the examples can describe a drill of a copy the page never shows, or one
    that began before the copy it read had finished."""
    real = page()
    drill = json_after(real, DRILL_PASSING_EXAMPLE_MARKER)
    other = with_example(real, DRILL_PASSING_EXAMPLE_MARKER, {**drill, "backup_id": "database-x"})
    early = with_example(
        real, DRILL_PASSING_EXAMPLE_MARKER, {**drill, "started_at": "2019-03-03T02:04:09Z"}
    )

    assert gaps(other) == (
        "the drill record that verifies: reads 'database-x' and the example manifest describes "
        "'database-20190303T020000Z'",
    )
    assert gaps(early) == (
        "the drill record that verifies: starts before the copy it reads was consistent, which is "
        "a drill of a copy that did not exist yet",
    )
    at_the_instant = with_example(
        real, DRILL_PASSING_EXAMPLE_MARKER, {**drill, "started_at": "2019-03-03T02:04:10Z"}
    )
    assert gaps(at_the_instant) == ()


def test_an_example_the_product_refuses_is_a_finding_and_the_rest_are_still_checked() -> None:
    """`"passed": "false"` in quotes is the mistake the page warns about. Delete this and a page
    whose example the reader refuses is agreed with, because the refusal would stop the check."""
    real = page()
    drill = json_after(real, DRILL_FAILING_EXAMPLE_MARKER)
    quoted = {
        **drill,
        "checks": [{**one, "passed": str(one["passed"]).lower()} for one in drill["checks"]],
    }
    manifest = json_after(real, DRILL_COPY_EXAMPLE_MARKER)

    refused_drill = gaps(with_example(real, DRILL_FAILING_EXAMPLE_MARKER, quoted))
    refused_copy = gaps(
        with_example(real, DRILL_COPY_EXAMPLE_MARKER, {**manifest, "size_bytes": 0})
    )

    assert len(refused_drill) == 1
    assert refused_drill[0].startswith(
        "the drill record that does not verify: example.drill.json: check 0 passed is"
    )
    assert len(refused_copy) == 1
    assert refused_copy[0].startswith("the example manifest: ")


def test_an_example_that_is_missing_or_not_directly_under_its_marker_is_refused() -> None:
    """Delete this and a deleted example makes the check read the next example down, which agrees
    with the page for the wrong reason."""
    real = page()

    with pytest.raises(InstallDocsError, match="carries no"):
        json_after("no marker here", DRILL_COPY_EXAMPLE_MARKER)
    with pytest.raises(InstallDocsError, match="directly beneath"):
        json_after(
            f"{DRILL_COPY_EXAMPLE_MARKER}\nprose\n```json\n{{}}\n```", DRILL_COPY_EXAMPLE_MARKER
        )
    with pytest.raises(InstallDocsError, match="directly beneath"):
        json_after(DRILL_COPY_EXAMPLE_MARKER, DRILL_COPY_EXAMPLE_MARKER)
    with pytest.raises(InstallDocsError, match="never closes"):
        json_after(f"{DRILL_COPY_EXAMPLE_MARKER}\n```json\n{{}}", DRILL_COPY_EXAMPLE_MARKER)
    with pytest.raises(InstallDocsError, match="not JSON"):
        json_after(f"{DRILL_COPY_EXAMPLE_MARKER}\n```json\n{{\n```", DRILL_COPY_EXAMPLE_MARKER)
    with pytest.raises(InstallDocsError, match="is a list"):
        json_after(f"{DRILL_COPY_EXAMPLE_MARKER}\n```json\n[]\n```", DRILL_COPY_EXAMPLE_MARKER)
    assert (
        json_after(f"{DRILL_COPY_EXAMPLE_MARKER}\n\n```json\n{{}}\n```", DRILL_COPY_EXAMPLE_MARKER)
        == {}
    )

    gone = once(real, DRILL_COPY_EXAMPLE_MARKER, "")
    assert gaps(gone) == (
        f"the page carries no {DRILL_COPY_EXAMPLE_MARKER!r}, so there is no example to read",
    )
