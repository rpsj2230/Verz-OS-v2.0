"""The design of record is measured against the console, and the distance is printed.

Delete this file and `brain.ops.console_design` can be reduced to returning nothing, the note
goes quiet, and the console drifts from `docs/screens.html` exactly as it did between
2026-09-02 and 2026-09-16, when thirteen screens were designed, screens were built from the
read modules alone, and the owner was the thing that noticed.
"""

from __future__ import annotations

from pathlib import Path

from brain.ops.console_design import (
    COMPANY_CONSOLE,
    Unbuilt,
    console_labels,
    design_navigation,
    navigation_gaps,
    unmeasured_navigations,
)

REPO = Path(__file__).resolve().parents[2]

_DESIGN = """
<section class="scr">
<h2>Company Overview</h2>
<div class="navsec">Operate</div>
<div class="navitem on">Overview</div>
<div class="navitem">Live runs</div>
<div class="navitem">Models &amp; health<span class="badge">1</span></div>
<div class="navsec">Govern</div>
<div class="navitem">People &amp; grants</div>
<div class="navitem">Quality &amp; canaries</div>
</section>
<section class="scr">
<h2>Department Console</h2>
<div class="navsec">Operate</div>
<div class="navitem on">Department</div>
<div class="navsec">Report</div>
<div class="navitem">Gaps</div>
</section>
<section class="scr">
<h2>My Workspace</h2>
<div class="navsec">Mine</div>
<div class="navitem">My agents</div>
</section>
<section class="scr">
<h2>Ask</h2>
<p>A screen that draws no navigation.</p>
</section>
<section class="scr">
<p>A frame with a navigation and no title, as a half-finished edit to the page leaves.</p>
<div class="navsec">Report</div>
<div class="navitem">Untitled</div>
</section>
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


def test_another_screens_navigation_is_not_the_company_consoles_gap(
    tmp_path: Path,
) -> None:
    """The design draws four navigations: the company console, the department console, a
    member's workspace and the menu inside an agent. Only the first is what the administrative
    shell is for. Until 2026-09-16 every section heading on the page was read into one list,
    and seven of the nineteen gaps printed were the department console's `Department`, `Gaps`
    and `Usage` and the agent's `Leash history`, `Runs and cost` and `Settings`, reported
    against a screen none of them belongs to.

    Delete this and the reading can go back to one list, the count grows by items nobody
    should build into this shell, and the first person to act on it does exactly that."""
    repo = _tree(tmp_path, _DESIGN, _SHELL)

    reported = {one.label for one in navigation_gaps(repo)}

    assert "Department" not in reported
    assert "Gaps" not in reported
    assert "My agents" not in reported
    assert set(design_navigation(repo)) == {"Operate", "Govern"}


def test_the_other_navigations_are_named_as_not_measured_rather_than_dropped(
    tmp_path: Path,
) -> None:
    """The sibling of the test above, and the reason reading one screen is not a silence. The
    department console and a member's workspace are designed and nothing compares them with
    anything yet, because neither has a shell of its own. Naming them is what keeps that a
    known gap. A screen that draws no navigation is not a navigation to measure, and a frame
    with no title has no screen to be read under, so it is left out rather than named as an
    empty string or allowed to stop the sweep.

    Delete this and those navigations can simply stop being read, and the note that says the
    console matches its design says so about one of the four menus it was given."""
    repo = _tree(tmp_path, _DESIGN, _SHELL)

    assert unmeasured_navigations(repo) == ("Department Console", "My Workspace")
    assert COMPANY_CONSOLE not in unmeasured_navigations(repo)


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
    assert "Department" not in sections["Operate"]
    assert "Department Console" in unmeasured_navigations(REPO)
    assert "Overview" in labels
    assert all(items for items in sections.values())
