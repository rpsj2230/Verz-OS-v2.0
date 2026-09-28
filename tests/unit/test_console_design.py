"""The design of record is measured against the console, and the distance is printed.

Delete this file and `brain.ops.console_design` can be reduced to returning nothing, the note
goes quiet, and the console drifts from `docs/screens.html` exactly as it did between
2026-09-02 and 2026-09-16, when thirteen screens were designed, screens were built from the
read modules alone, and the owner was the thing that noticed.

Since 2026-09-28 both consoles' menus are Python declarations the API serves, and the one group
the browser holds, the reader's own work, is declared page by page in the route files. So the
fixtures here are a design page, a registry and route files, and the menus are handed in.
"""

from __future__ import annotations

from pathlib import Path

from brain.console.department_console import (
    COMPANY_NAVIGATION,
    DEPARTMENT_NAVIGATION,
    Entry,
    Page,
    Section,
)
from brain.console.screens import ModuleGroup
from brain.ops.console_design import (
    COMPANY_CONSOLE,
    DEPARTMENT_CONSOLE,
    Unbuilt,
    company_console_navigation,
    console_labels,
    console_navigation,
    department_console_navigation,
    department_navigation_gaps,
    design_navigation,
    design_navigations,
    navigation_gaps,
    own_work,
    unmeasured_navigations,
)

REPO = Path(__file__).resolve().parents[2]

_DESIGN = """
<section class="scr">
<h2>Company Overview</h2>
<div class="navsec">Use</div>
<div class="navitem">Ask</div>
<div class="navitem">My workspace</div>
<div class="navsec">Home</div>
<div class="navitem on">Dashboard</div>
<div class="navitem">Runs &amp; queue</div>
<div class="navitem">Models &amp; routing<span class="badge">1</span></div>
<div class="navsec">People and access</div>
<div class="navitem">People &amp; grants</div>
<div class="navitem">Quality &amp; canaries</div>
</section>
<section class="scr">
<h2>Department Console</h2>
<div class="navsec">Home</div>
<div class="navitem on">Department</div>
<div class="navsec">Reports</div>
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

_REGISTRY = 'export const OWN_WORK_HEADING = "Use";\n'

#: Two route files declaring the reader's own work, written in the opposite order to their numbers.
_ROUTE_FILES = {
    "MyWorkspace.route.tsx": (
        'export const routes: PageRoutes = [{ path: "me", element: <MyWorkspace /> }];\n'
        'export const ownWork: OwnWorkEntry = { to: "/me", label: "My workspace", order: 20 };\n'
    ),
    "Ask.route.tsx": (
        'export const routes: PageRoutes = [{ path: "ask", element: <Ask /> }];\n'
        'export const ownWork: OwnWorkEntry = { to: "/ask", label: "Ask", order: 10 };\n'
    ),
    "People.route.tsx": (
        'export const routes: PageRoutes = [{ path: "people", element: <People /> }];\n'
    ),
}


def _entry(label: str, to: str = "/x") -> Entry:
    """An entry of one page with no registry screen, so a fixture can file it in any group."""
    return Entry(label=label, pages=(Page(label=label, to=to),))


_OFFERED = (
    Section(group=ModuleGroup.HOME, entries=(_entry("Dashboard", "/"),)),
    Section(
        group=ModuleGroup.PEOPLE,
        entries=(_entry("people and grants"), _entry("Quality-canaries")),
    ),
)

_MISFILED = (
    Section(
        group=ModuleGroup.HOME,
        entries=(_entry("Dashboard", "/"), _entry("People and grants")),
    ),
    Section(group=ModuleGroup.PEOPLE, entries=(_entry("Quality and canaries"),)),
)


def _tree(root: Path, design: str = _DESIGN, *, routes: bool = True) -> Path:
    """A repository holding only what this module reads: the design, the registry and routes."""
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "screens.html").write_text(design, encoding="utf-8")
    if routes:
        (root / "console" / "src" / "routes").mkdir(parents=True, exist_ok=True)
        (root / "console" / "src" / "pages").mkdir(parents=True, exist_ok=True)
        (root / "console" / "src" / "routes" / "registry.ts").write_text(
            _REGISTRY, encoding="utf-8"
        )
        for name, text in _ROUTE_FILES.items():
            (root / "console" / "src" / "pages" / name).write_text(text, encoding="utf-8")
    return root


def test_an_item_the_design_names_and_the_console_does_not_offer_is_reported(
    tmp_path: Path,
) -> None:
    """The whole point. `Runs and queue` and `Models and routing` are drawn in the design's Home
    section and the console offers neither, which is the state the owner found on his own
    install: screens built from whatever module came next, and a design nobody was held to.

    Delete this and `navigation_gaps` can return an empty tuple for any input, the note reads
    as a console that matches its design, and the only thing left that notices is a person."""
    repo = _tree(tmp_path)

    assert navigation_gaps(repo, _OFFERED) == (
        Unbuilt(section="Home", label="Runs and queue"),
        Unbuilt(section="Home", label="Models and routing"),
    )


def test_an_item_the_console_offers_under_the_designs_own_wording_is_not_a_gap(
    tmp_path: Path,
) -> None:
    """The positive sibling, and it carries the two spellings that would otherwise be false
    findings: the design writes `People &amp; grants` with an ampersand entity and the console
    writes `people and grants`, and a count badge beside a label is a number rather than part
    of the name. The reader's own work, read from the route files, is offered too.

    Delete this and the comparison can be tightened to an exact string match, which reports
    every item in the design as missing and makes the note useless on the day it is right."""
    repo = _tree(tmp_path)

    reported = {one.label for one in navigation_gaps(repo, _OFFERED)}

    assert "People &amp; grants" not in reported
    assert "People and grants" not in reported
    assert "Quality and canaries" not in reported
    assert "Dashboard" not in reported
    assert "Ask" not in reported
    assert "My workspace" not in reported


def test_the_readers_own_work_is_read_from_the_route_files_in_the_order_they_number(
    tmp_path: Path,
) -> None:
    """The one group the browser holds is declared page by page, each route file saying where its
    page sits. Read in their numbers' order, not the files' names, and absent without a registry.

    Delete this and the Use group can be dropped from the comparison, so every item SCREEN 1 draws
    under it is reported missing, or read in file-name order and compared in an order nobody chose.
    """
    repo = _tree(tmp_path)

    assert own_work(repo) == ("Use", ("Ask", "My workspace"))
    assert console_navigation(repo, _OFFERED)["Use"] == ("Ask", "My workspace")
    assert next(iter(console_navigation(repo, _OFFERED))) == "Use"

    bare = _tree(tmp_path / "bare", routes=False)
    assert own_work(bare) == ("", ())
    assert "Use" not in console_navigation(bare, _OFFERED)
    assert {one.label for one in navigation_gaps(bare, _OFFERED)} >= {"Ask", "My workspace"}


def test_an_item_offered_under_another_group_is_reported_with_the_group_it_sits_under(
    tmp_path: Path,
) -> None:
    """The half of M27.8.2 a label comparison cannot see. `People and grants` is offered, but under
    Home where the design draws it under People and access, so somebody following the design opens
    People and access and does not find it. It is reported, and the line names where it was put.

    Delete this and the comparison can go back to labels alone, and a menu with every screen in
    the wrong group reads as a menu that matches its design."""
    repo = _tree(tmp_path)

    misfiled = [one for one in navigation_gaps(repo, _MISFILED) if one.label == "People and grants"]

    assert misfiled == [
        Unbuilt(section="People and access", label="People and grants", placed_under="Home")
    ]
    assert misfiled[0].line == "People and access: People and grants (offered under Home)"
    assert console_navigation(repo, _MISFILED)["Home"] == ("Dashboard", "People and grants")


def test_another_screens_navigation_is_not_the_company_consoles_gap(
    tmp_path: Path,
) -> None:
    """The design draws four navigations: the company console, the department console, a
    member's workspace and the menu inside an agent. Only the first is the company console's.
    Until 2026-09-16 every section heading on the page was read into one list, and seven of the
    nineteen gaps printed were other screens' items reported against a screen none of them
    belongs to.

    Delete this and the reading can go back to one list, the count grows by items nobody
    should build into this menu, and the first person to act on it does exactly that."""
    repo = _tree(tmp_path)

    reported = {one.label for one in navigation_gaps(repo, _OFFERED)}

    assert "Department" not in reported
    assert "Gaps" not in reported
    assert "My agents" not in reported
    assert set(design_navigation(repo)) == {"Use", "Home", "People and access"}


def test_the_other_navigations_are_named_as_not_measured_rather_than_dropped(
    tmp_path: Path,
) -> None:
    """The sibling of the test above, and the reason reading one screen is not a silence. A
    member's workspace is designed and nothing compares it with anything yet. Naming it is what
    keeps that a known gap. A screen that draws no navigation is not a navigation to measure, and
    a frame with no title has no screen to be read under, so it is left out rather than named as
    an empty string or allowed to stop the sweep.

    Delete this and those navigations can simply stop being read, and the note that says the
    console matches its design says so about one of the four menus it was given."""
    repo = _tree(tmp_path)

    assert unmeasured_navigations(repo) == ("My Workspace",)
    assert COMPANY_CONSOLE not in unmeasured_navigations(repo)
    assert DEPARTMENT_CONSOLE in design_navigations(repo)


def test_an_item_the_department_design_names_and_its_menu_does_not_offer_is_reported(
    tmp_path: Path,
) -> None:
    """M27.7.29's half of this module. The fixture design draws `Department` under Home and `Gaps`
    under Reports; a department menu offering only `Department` reports `Gaps` missing, and one
    offering `Gaps` under Home reports it with the heading it was put under. The real declaration
    offers everything SCREEN 2 draws, where it draws it.

    Delete this and `department_navigation_gaps` can return nothing for any menu, and the
    department console drifts from SCREEN 2 exactly as the company console did from SCREEN 1."""
    repo = _tree(tmp_path)
    department = _entry("Department", "/department")
    gaps = _entry("Gaps", "/questions")

    only_the_overview = (Section(group=ModuleGroup.HOME, entries=(department,)),)
    misfiled = (Section(group=ModuleGroup.HOME, entries=(department, gaps)),)

    assert department_navigation_gaps(repo, only_the_overview) == (
        Unbuilt(section="Reports", label="Gaps"),
    )
    assert department_navigation_gaps(repo, misfiled) == (
        Unbuilt(section="Reports", label="Gaps", placed_under="Home"),
    )
    assert department_navigation_gaps(REPO) == ()
    assert department_console_navigation(misfiled) == {"Home": ("Department", "Gaps")}


def test_the_design_and_the_console_are_read_out_of_the_real_files() -> None:
    """Against this repository rather than a fixture, because a parser that reads a synthetic
    page and not the real one is a parser that reports nothing on every real run. The design's
    `navsec` and `navitem` markup, the route files' `ownWork` lines and both declarations are the
    shapes this depends on, and the real ones have no gap between them.

    Delete this and any of them can be rewritten in a way this module cannot read, leaving a
    note that says nothing is missing because nothing was found."""
    sections = design_navigation(REPO)
    labels = console_labels(REPO)
    grouped = console_navigation(REPO)

    assert list(sections) == ["Use", *(one.heading for one in ModuleGroup)], list(sections)
    assert "Department" not in sections["Home"]
    assert "Department Console" not in unmeasured_navigations(REPO)
    assert "Platform" not in design_navigations(REPO)[DEPARTMENT_CONSOLE]
    assert navigation_gaps(REPO) == ()
    assert department_navigation_gaps(REPO) == ()
    assert department_console_navigation() == department_console_navigation(DEPARTMENT_NAVIGATION)
    assert company_console_navigation() == department_console_navigation(COMPANY_NAVIGATION)
    assert "Dashboard" in labels
    assert list(grouped) == list(sections)
    assert all(items for items in sections.values())
