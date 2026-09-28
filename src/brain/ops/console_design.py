"""Whether the console a browser serves is the console `docs/screens.html` designs.

**Written because it was not, and nobody noticed for a fortnight.** That file is the design of
record: thirteen screens, each with the role it belongs to, the section it sits in and the
navigation around it. Screens were then built from the read modules alone, and on 2026-09-16
the owner opened his own install, compared it with the page, and asked what the point of the
design was. The honest answer was that nothing held anybody to it, so this does.

**What a design is for.** The read modules decide what a reader may see; they say nothing about
what a person is trying to do, which screen they live in all day, or how those screens are
grouped. `docs/screens.html` answers exactly that and is the only place it is answered. A
console assembled screen by screen from whatever module was next is a drawer of settings pages,
which is the shape the owner's brief in `docs/admin-console.md` refuses.

**Reported, never a gate, and the reason is the same one `sweep_house_style` learned.** It was
red on the day it landed, because the console's sections were one flat list and the design
grouped them, and a check that is red the day it lands is a check somebody switches off. So the
count and the names print on every run beside the reads with no screen, and the pair of them is
the distance between what exists and what was designed. See
`A_DESIGN_NOTHING_MEASURES_IS_A_PICTURE`.

**The design draws four navigations, and two of them are measured.** SCREEN 1 is the company
console, SCREEN 2 is the same shape bounded to one department, SCREEN 11 is a member's own
workspace and SCREEN 12 is the menu inside one agent. Until 2026-09-16 every section heading on
the page was read into one list, so the department console's items and the agent's were reported
as missing from the company console, which is a screen none of them belongs to. Each navigation
is now read under the screen that draws it, and the ones with nothing to compare with are named
as not measured. See `ONE_PAGE_FOUR_NAVIGATIONS`.

**Both consoles are measured against the menus the API serves, since 2026-09-17.** Their groups
are a field of the screen registry, so both menus are declared in
`brain.console.department_console` and served by `GET /api/v1/console/navigation`, and the shell
holds only the reader's own work, which is drawn before that answer arrives. A console's menu is
therefore compared as the shell's own group followed by the declaration, which is the order the
shell draws them in. See `A_SERVED_MENU_IS_MEASURED_WHERE_IT_IS_DECLARED`.

**An item is found only in the group the design puts it in.** An item the design draws under
Governance that the console offers under Operations is reported with the group it was found
under, because a screen filed in the wrong group is one somebody following the design looks for
and does not find. See `A_SCREEN_IN_THE_WRONG_GROUP_IS_NOT_FOUND`.

**A declared module with no page is not a gap, and it is not silent either.** The menu declares
every module the design draws, so the comparison finds each one in its group, and a module with
no page is carried with no address and never drawn as a link. `unbuilt_entries` names those, and
the sweep prints them beside the gaps, because a design item that is declared and unbuilt is the
same distance to cover as one that is missing, and only the second is a mistake in the menu. See
`brain.console.department_console.A_MODULE_WITH_NO_PAGE_IS_DECLARED_AND_NEVER_A_LINK`.

**What it cannot see.** Whether a screen shows the columns the design draws, whether a figure on
it means what the mockup means, and whether the wording matches. Those are read by a person
against the page. This reads the navigation, which is the half a machine can hold: every item
the design names, in the section it names, reachable in the browser.

Task ids: M27.8.2, M27.7.29, M27.10.1
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from brain.console.department_console import COMPANY_NAVIGATION, DEPARTMENT_NAVIGATION, Section

__all__ = [
    "A_DESIGN_NOTHING_MEASURES_IS_A_PICTURE",
    "A_SCREEN_IN_THE_WRONG_GROUP_IS_NOT_FOUND",
    "A_SERVED_MENU_IS_MEASURED_WHERE_IT_IS_DECLARED",
    "COMPANY_CONSOLE",
    "DEPARTMENT_CONSOLE",
    "DESIGN_PAGE",
    "ONE_PAGE_FOUR_NAVIGATIONS",
    "Unbuilt",
    "console_labels",
    "console_navigation",
    "declared_navigation",
    "department_console_navigation",
    "department_navigation_gaps",
    "design_navigation",
    "design_navigations",
    "navigation_gaps",
    "shell_navigation",
    "unbuilt_entries",
    "unmeasured_navigations",
]

#: Why this reports rather than refuses.
A_DESIGN_NOTHING_MEASURES_IS_A_PICTURE: Final = (
    "docs/screens.html designs thirteen screens and their navigation, and until this module "
    "existed nothing compared it with the console anybody could open. A design nothing "
    "measures is a picture: it is read once, built from loosely, and quietly diverged from. "
    "This prints the distance on every run instead, because the console was red against the "
    "design when this landed and a check that lands red is a check that gets switched off."
)

#: The design of record.
DESIGN_PAGE: Final = Path("docs") / "screens.html"

#: Where the console declares the menu group it draws before the API has answered.
CONSOLE_SHELL: Final = Path("console") / "src" / "layout" / "Shell.tsx"

#: Why the navigations are read per screen rather than per page.
ONE_PAGE_FOUR_NAVIGATIONS: Final = (
    "docs/screens.html draws a company console, a department console, a member's workspace "
    "and the menu inside an agent, and each is a different reader's navigation. Reading every "
    "section heading on the page into one list reports another reader's menu items as gaps in "
    "this one, so each is read under the screen title that draws it."
)

#: Why a label offered under another heading still counts as a gap.
A_SCREEN_IN_THE_WRONG_GROUP_IS_NOT_FOUND: Final = (
    "The design says where each screen lives as well as what it is called. A person following "
    "it opens Governance to find the audit log, and a console that offers it under Reports has "
    "a screen that exists and cannot be found, so it is reported with the group it sits under."
)

#: The screen whose navigation the company menu is compared with.
COMPANY_CONSOLE: Final = "Company Overview"

#: The screen whose navigation the department menu is compared with.
DEPARTMENT_CONSOLE: Final = "Department Console"

#: Why a served menu is compared with the Python declaration rather than the shell.
A_SERVED_MENU_IS_MEASURED_WHERE_IT_IS_DECLARED: Final = (
    "Both consoles' menus are served by the API, so the shell holds none of their labels beyond "
    "the reader's own work. Comparing the design with the shell alone would report every module "
    "as missing, so the comparison reads the shell's own group and then the declaration the "
    "route serves, with one rule for both: every item the design draws, under the heading it "
    "draws it."
)

_SCREEN = re.compile(r'<section class="scr">')
_TITLE = re.compile(r"<h2>([^<]+)</h2>")
_SECTION_START = r'<(?:div|summary) class="navsec[^"]*">'
_SECTION = re.compile(_SECTION_START + r"([^<]+)")
_ITEM = re.compile(r'<div class="navitem[^"]*">([^<]*?)(?:<span[^>]*>\d+</span>)?</div>')
_GROUP_HEADING = re.compile(r'heading:\s*"([^"]+)"')
_NAV_ROW = re.compile(r'\{\s*to:\s*"([^"]+)"\s*,\s*label:\s*"([^"]+)"\s*\}')


@dataclass(frozen=True)
class Unbuilt:
    """One navigation item the design names and the console does not open."""

    section: str
    label: str
    #: The console group the label was found under instead, or empty when it is nowhere.
    placed_under: str = ""

    @property
    def line(self) -> str:
        """The reported line, section first because the section is the part that is missing."""
        where = f" (offered under {self.placed_under})" if self.placed_under else ""
        return f"{self.section}: {self.label}{where}"


def _text(raw: str) -> str:
    """One navigation label, with the entities the page is written in read back."""
    cleaned = raw.replace("&amp;", "and").replace("&rarr;", "").replace("&middot;", "")
    return " ".join(cleaned.split()).strip()


def _comparable(label: str) -> str:
    """A label as it compares: case, ampersands and the count badges beside it removed."""
    stripped = re.sub(r"\s+\d+$", "", _text(label))
    return stripped.replace(" and ", " ").replace("-", " ").lower().strip()


def design_navigations(repo: Path) -> dict[str, dict[str, tuple[str, ...]]]:
    """Every navigation the design draws, by the title of the screen that draws it.

    Read out of the page's own markup rather than a list kept here, because a list here is a
    second copy of the design that drifts from it exactly as the console did. A section heading
    is a `navsec` element, a `div` or the `summary` of a group drawn collapsed, and an item inside
    a collapsed group is designed like any other. A screen that draws no navigation is not in the
    answer.
    """
    page = (repo / DESIGN_PAGE).read_text(encoding="utf-8", errors="replace")
    drawn: dict[str, dict[str, tuple[str, ...]]] = {}
    for screen in _SCREEN.split(page)[1:]:
        title = _TITLE.search(screen)
        if title is None:
            continue
        found: dict[str, list[str]] = {}
        for chunk in re.split(f"(?={_SECTION_START})", screen):
            heading = _SECTION.search(chunk)
            if heading is None:
                continue
            items = [_text(one) for one in _ITEM.findall(chunk)]
            seen = found.setdefault(_text(heading.group(1)), [])
            seen.extend(one for one in items if one and one not in seen)
        sections = {section: tuple(items) for section, items in found.items() if items}
        if sections:
            drawn[_text(title.group(1))] = sections
    return drawn


def design_navigation(repo: Path) -> dict[str, tuple[str, ...]]:
    """The company console's navigation, by section: the one SCREEN 1 draws."""
    return design_navigations(repo).get(COMPANY_CONSOLE, {})


def unmeasured_navigations(repo: Path) -> tuple[str, ...]:
    """The titles of the other navigations the design draws, which nothing here compares yet."""
    measured = {COMPANY_CONSOLE, DEPARTMENT_CONSOLE}
    return tuple(title for title in design_navigations(repo) if title not in measured)


def console_labels(repo: Path) -> tuple[str, ...]:
    """Every label the console's shell declares itself, in the order it declares them."""
    shell = (repo / CONSOLE_SHELL).read_text(encoding="utf-8", errors="replace")
    return tuple(label for _, label in _NAV_ROW.findall(shell))


def shell_navigation(repo: Path) -> dict[str, tuple[str, ...]]:
    """The shell's own labels, by the heading of the group each sits under.

    A group runs from its `heading:` to the next one. Since the menus are served this is the
    reader's own work alone, the group every console draws before the API has answered.
    """
    shell = (repo / CONSOLE_SHELL).read_text(encoding="utf-8", errors="replace")
    headings = list(_GROUP_HEADING.finditer(shell))
    grouped: dict[str, tuple[str, ...]] = {}
    for at, heading in enumerate(headings):
        end = headings[at + 1].start() if at + 1 < len(headings) else len(shell)
        rows = tuple(label for _, label in _NAV_ROW.findall(shell[heading.end() : end]))
        grouped[heading.group(1)] = grouped.get(heading.group(1), ()) + rows
    return grouped


def declared_navigation(offered: Sequence[Section]) -> dict[str, tuple[str, ...]]:
    """A served menu's labels, by the heading of the section each sits under."""
    grouped: dict[str, tuple[str, ...]] = {}
    for section in offered:
        labels = tuple(one.label for one in section.entries)
        grouped[section.heading] = grouped.get(section.heading, ()) + labels
    return grouped


def _drawn(repo: Path, offered: Sequence[Section]) -> dict[str, tuple[str, ...]]:
    """What a console draws: the shell's own group, then the menu the API serves."""
    grouped = dict(shell_navigation(repo))
    for heading, labels in declared_navigation(offered).items():
        grouped[heading] = grouped.get(heading, ()) + labels
    return grouped


def console_navigation(
    repo: Path, offered: Sequence[Section] = COMPANY_NAVIGATION
) -> dict[str, tuple[str, ...]]:
    """The company console's labels by heading, as the shell draws them once the API answers."""
    return _drawn(repo, offered)


def department_console_navigation(
    repo: Path, offered: Sequence[Section] = DEPARTMENT_NAVIGATION
) -> dict[str, tuple[str, ...]]:
    """A department console's labels by heading, as the shell draws them once the API answers."""
    return _drawn(repo, offered)


def navigation_gaps(
    repo: Path, offered: Sequence[Section] = COMPANY_NAVIGATION
) -> tuple[Unbuilt, ...]:
    """Every item SCREEN 1 names that the company console does not offer in the same group.

    Compared on the label rather than the address, because the design draws a navigation and
    never an address, and a screen that is reachable under another name is still a screen
    somebody following the design cannot find. An item offered under another group is reported
    with that group named.
    """
    return _gaps(design_navigation(repo), console_navigation(repo, offered))


def department_navigation_gaps(
    repo: Path, offered: Sequence[Section] = DEPARTMENT_NAVIGATION
) -> tuple[Unbuilt, ...]:
    """Every item SCREEN 2 names that the department console does not offer in the same group.

    The same comparison as `navigation_gaps`, against the department's declaration. See
    `A_SERVED_MENU_IS_MEASURED_WHERE_IT_IS_DECLARED`.
    """
    designed = design_navigations(repo).get(DEPARTMENT_CONSOLE, {})
    return _gaps(designed, department_console_navigation(repo, offered))


def unbuilt_entries(offered: Sequence[Section] = COMPANY_NAVIGATION) -> tuple[Unbuilt, ...]:
    """Every entry a menu declares with no page yet, which the shell draws and never links.

    Not a gap in the menu, which is `navigation_gaps`, and not silence either: see the module
    docstring.
    """
    return tuple(
        Unbuilt(section=section.heading, label=entry.label)
        for section in offered
        for entry in section.entries
        if entry.to is None
    )


def _gaps(
    designed: Mapping[str, tuple[str, ...]], grouped: Mapping[str, tuple[str, ...]]
) -> tuple[Unbuilt, ...]:
    """Every designed item not offered under its own heading, with where it was offered instead."""
    found_under: dict[str, str] = {}
    for heading, labels in grouped.items():
        for label in labels:
            found_under.setdefault(_comparable(label), heading)
    missing: list[Unbuilt] = []
    for section, items in designed.items():
        offered = {_comparable(one) for one in grouped.get(section, ())}
        for label in items:
            if _comparable(label) in offered:
                continue
            missing.append(
                Unbuilt(
                    section=section,
                    label=label,
                    placed_under=found_under.get(_comparable(label), ""),
                )
            )
    return tuple(missing)
