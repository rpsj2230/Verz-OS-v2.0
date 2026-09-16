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
    "DESIGN_PAGE",
    "Unbuilt",
    "console_labels",
    "design_navigation",
    "navigation_gaps",
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

#: Sections in the design that belong to a member rather than an administrator. The console
#: this module reads is the administrative one, so a member's own navigation is not its gap.
MEMBER_SECTIONS: Final[frozenset[str]] = frozenset({"Use", "Mine", "Me", "Agent"})

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


def design_navigation(repo: Path) -> dict[str, tuple[str, ...]]:
    """Every administrative navigation item the design names, by the section it sits in.

    Read out of the page's own markup rather than a list kept here, because a list here is a
    second copy of the design that drifts from it exactly as the console did.
    """
    page = (repo / DESIGN_PAGE).read_text(encoding="utf-8", errors="replace")
    found: dict[str, list[str]] = {}
    for chunk in re.split(r'(?=<div class="navsec">)', page):
        heading = _SECTION.search(chunk)
        if heading is None:
            continue
        section = _text(heading.group(1))
        if section in MEMBER_SECTIONS:
            continue
        items = [_text(one) for one in _ITEM.findall(chunk)]
        seen = found.setdefault(section, [])
        seen.extend(one for one in items if one and one not in seen)
    return {section: tuple(items) for section, items in found.items() if items}


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
