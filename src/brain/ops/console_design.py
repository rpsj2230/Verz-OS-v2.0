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

**Reported, never a gate, and the reason is the same one `sweep_house_style` learned.** This is
red today by construction: the console's sections are one flat list and the design groups them
under Operate, Govern and Report. A check that is red the day it lands is a check somebody
switches off, so the count and the names print on every run beside the reads with no screen,
and the pair of them is the distance between what exists and what was designed. See
`A_DESIGN_NOTHING_MEASURES_IS_A_PICTURE`.

**The design draws four navigations, and only one of them is this console's.** SCREEN 1 is
the company console a Super Admin runs, SCREEN 2 is the same shape bounded to one department,
SCREEN 11 is a member's own workspace and SCREEN 12 is the menu inside one agent. Until
2026-09-16 every section heading on the page was read into one list, so the department
console's "Department", "Gaps" and "Usage" and the agent's "Leash history" and "Settings" were
reported as missing from the company console, which is a screen none of them belongs to. Seven
of nineteen reported gaps were that. Each navigation is now read under the screen that draws
it, the company console is compared with the shell, and the other three are named as not
measured, because none of them has a shell of its own yet to compare with. See
`ONE_PAGE_FOUR_NAVIGATIONS`.

**What it cannot see.** Whether a screen shows the columns the design draws, whether a figure on
it means what the mockup means, and whether the wording matches. Those are read by a person
against the page. This reads the navigation, which is the half a machine can hold: every item
the design names, in the section it names, reachable in the browser.

Task ids: M27.8.2
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = [
    "A_DESIGN_NOTHING_MEASURES_IS_A_PICTURE",
    "COMPANY_CONSOLE",
    "DESIGN_PAGE",
    "ONE_PAGE_FOUR_NAVIGATIONS",
    "Unbuilt",
    "console_labels",
    "design_navigation",
    "design_navigations",
    "navigation_gaps",
    "unmeasured_navigations",
]

#: Why this reports rather than refuses.
A_DESIGN_NOTHING_MEASURES_IS_A_PICTURE: Final = (
    "docs/screens.html designs thirteen screens and their navigation, and until this module "
    "existed nothing compared it with the console anybody could open. A design nothing "
    "measures is a picture: it is read once, built from loosely, and quietly diverged from. "
    "This prints the distance on every run instead, because the console is red against the "
    "design today and a check that lands red is a check that gets switched off."
)

#: The design of record.
DESIGN_PAGE: Final = Path("docs") / "screens.html"

#: Where the console declares what its navigation holds.
CONSOLE_SHELL: Final = Path("console") / "src" / "layout" / "Shell.tsx"

#: Why the navigations are read per screen rather than per page.
ONE_PAGE_FOUR_NAVIGATIONS: Final = (
    "docs/screens.html draws a company console, a department console, a member's workspace "
    "and the menu inside an agent, and each is a different reader's navigation. Reading every "
    "section heading on the page into one list reports another reader's menu items as gaps in "
    "this one, so each is read under the screen title that draws it."
)

#: The screen whose navigation the administrative shell is compared with.
COMPANY_CONSOLE: Final = "Company Overview"

_SCREEN = re.compile(r'<section class="scr">')
_TITLE = re.compile(r"<h2>([^<]+)</h2>")
_SECTION = re.compile(r'<div class="navsec">([^<]+)')
_ITEM = re.compile(r'<div class="navitem[^"]*">([^<]*?)(?:<span[^>]*>\d+</span>)?</div>')
_NAV_ROW = re.compile(r'\{\s*to:\s*"([^"]+)"\s*,\s*label:\s*"([^"]+)"\s*\}')


@dataclass(frozen=True)
class Unbuilt:
    """One navigation item the design names and the console does not serve."""

    section: str
    label: str

    @property
    def line(self) -> str:
        """The reported line, section first because the section is the part that is missing."""
        return f"{self.section}: {self.label}"


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
    second copy of the design that drifts from it exactly as the console did. A screen that
    draws no navigation is not in the answer.
    """
    page = (repo / DESIGN_PAGE).read_text(encoding="utf-8", errors="replace")
    drawn: dict[str, dict[str, tuple[str, ...]]] = {}
    for screen in _SCREEN.split(page)[1:]:
        title = _TITLE.search(screen)
        if title is None:
            continue
        found: dict[str, list[str]] = {}
        for chunk in re.split(r'(?=<div class="navsec">)', screen):
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
    """The company console's navigation, by section: the one the administrative shell is for."""
    return design_navigations(repo).get(COMPANY_CONSOLE, {})


def unmeasured_navigations(repo: Path) -> tuple[str, ...]:
    """The titles of the other navigations the design draws, which nothing here compares yet."""
    return tuple(title for title in design_navigations(repo) if title != COMPANY_CONSOLE)


def console_labels(repo: Path) -> tuple[str, ...]:
    """Every label the console's shell offers, in the order it offers them."""
    shell = (repo / CONSOLE_SHELL).read_text(encoding="utf-8", errors="replace")
    return tuple(label for _, label in _NAV_ROW.findall(shell))


def navigation_gaps(repo: Path) -> tuple[Unbuilt, ...]:
    """Every item the design names that the console's navigation does not offer.

    Compared on the label rather than the address, because the design draws a navigation and
    never an address, and a screen that is reachable under another name is still a screen
    somebody following the design cannot find.
    """
    offered = {_comparable(one) for one in console_labels(repo)}
    missing: list[Unbuilt] = []
    for section, items in design_navigation(repo).items():
        for label in items:
            if _comparable(label) not in offered:
                missing.append(Unbuilt(section=section, label=label))
    return tuple(missing)
