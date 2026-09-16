"""The design of record is measured against the console, and the distance is printed.

Delete this file and `brain.ops.console_design` can be reduced to returning nothing, the note
goes quiet, and the console drifts from `docs/screens.html` exactly as it did between
2026-09-02 and 2026-09-16, when thirteen screens were designed, screens were built from the
read modules alone, and the owner was the thing that noticed.
"""

from __future__ import annotations

from pathlib import Path

from brain.ops.console_design import (
    Unbuilt,
    console_labels,
    design_navigation,
    navigation_gaps,
)

REPO = Path(__file__).resolve().parents[2]

_DESIGN = """
<div class="navsec">Operate</div>
<div class="navitem on">Overview</div>
<div class="navitem">Live runs</div>
<div class="navitem">Models &amp; health<span class="badge">1</span></div>
<div class="navsec">Govern</div>
<div class="navitem">People &amp; grants</div>
<div class="navitem">Quality &amp; canaries</div>
<div class="navsec">Mine</div>
<div class="navitem">My agents</div>
"""

_SHELL = """
const SECTIONS: readonly { to: string; label: string }[] = [
  { to: "/", label: "Overview" },
  { to: "/people", label: "people and grants" },
  { to: "/quality", label: "Quality-canaries" },
];
"""


def _tree(root: Path, design: str, shell: str) -> Path:
    """A repository holding only the two files this module reads."""
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "console" / "src" / "layout").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "screens.html").write_text(design, encoding="utf-8")
    (root / "console" / "src" / "layout" / "Shell.tsx").write_text(shell, encoding="utf-8")
    return root


def test_an_item_the_design_names_and_the_console_does_not_offer_is_reported(
    tmp_path: Path,
) -> None:
    """The whole point. `Live runs` and `Models and health` are drawn in the design's Operate
    section and the console offers neither, which is the state the owner found on his own
    install: screens built from whatever module came next, and a design nobody was held to.

    Delete this and `navigation_gaps` can return an empty tuple for any input, the note reads
    as a console that matches its design, and the only thing left that notices is a person."""
    repo = _tree(tmp_path, _DESIGN, _SHELL)

    assert navigation_gaps(repo) == (
        Unbuilt(section="Operate", label="Live runs"),
        Unbuilt(section="Operate", label="Models and health"),
    )


def test_an_item_the_console_offers_under_the_designs_own_wording_is_not_a_gap(
    tmp_path: Path,
) -> None:
    """The positive sibling, and it carries the two spellings that would otherwise be false
    findings: the design writes `People &amp; grants` with an ampersand entity and the console
    writes `People and grants`, and a count badge beside a label is a number rather than part
    of the name.

    Delete this and the comparison can be tightened to an exact string match, which reports
    every item in the design as missing and makes the note useless on the day it is right."""
    repo = _tree(tmp_path, _DESIGN, _SHELL)

    reported = {one.label for one in navigation_gaps(repo)}

    assert "People &amp; grants" not in reported
    assert "People and grants" not in reported
    assert "Quality &amp; canaries" not in reported
    assert "Overview" not in reported


def test_a_members_own_navigation_is_not_the_administrative_consoles_gap(
    tmp_path: Path,
) -> None:
    """The design draws a member's screens too, under Mine, Me, Use and Agent. This module
    reads the administrative console, so `My agents` is not a missing administrative screen: it
    is a screen for somebody else, and reporting it would make the note the thing people learn
    to ignore.

    Delete this and every member item joins the count, the number stops meaning what it says,
    and the first person to act on it builds a member page into the administrative shell."""
    repo = _tree(tmp_path, _DESIGN, _SHELL)

    assert all(one.section != "Mine" for one in navigation_gaps(repo))
    assert "Mine" not in design_navigation(repo)


def test_the_design_and_the_console_are_read_out_of_the_real_files() -> None:
    """Against this repository rather than a fixture, because a parser that reads a synthetic
    page and not the real one is a parser that reports nothing on every real run. Both files
    have a shape this depends on: the design's `navsec` and `navitem` markup, and the shell's
    `{ to, label }` rows.

    The assertion is deliberately about shape and not about a count: the count is what the note
    prints and it moves every time a screen is built, which is what it is for.

    Delete this and either file can be rewritten in a way this module cannot read, leaving a
    note that says nothing is missing because nothing was found."""
    sections = design_navigation(REPO)
    labels = console_labels(REPO)

    assert set(sections) == {"Operate", "Govern", "Report"}, sorted(sections)
    assert "Overview" in labels
    assert all(items for items in sections.values())
