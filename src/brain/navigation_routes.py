"""Which console a reader is given, over HTTP: the navigation the shell renders.

`brain.console.screens.navigation` took an `EntitlementSet` and was reachable from no route, so
the menu a browser could compute from grants was none, and `console/src/layout/Shell.tsx` listed
the same entries for everybody because the alternative was a permission check written in the
browser. This is the route that note asked for. `brain.console.department_console.console_for`
decides and this projects what it decided.

**One route, one answer, computed at the reach the request was admitted at.** `asked.reach` is
`E(caller)` narrowed by the channel and by the sign-in, which is the reach every screen behind
the menu will answer at, so the menu and the screens cannot disagree about who is asking. A
reader who holds a screen across the install only through a second factor they did not use is
given the department console for this session, which is the direction to be wrong in.

**Nobody is refused.** Every signed-in reader is given a console, and a reader who holds no
screen is given a department console with nothing in it. Refusing them instead would make this
the one route whose status says whether somebody administers anything, and the menu would then
be the least visible way to ask it.

**The company console's menu is not in the answer.** It is the shell's own constant, identical
for everybody given it, and `brain.ops.console_design` measures it there against SCREEN 1. What
is here is the department console's menu, because that one is narrowed per reader by
`brain.console.screens.for_department` and a browser cannot narrow it without a copy of the
rules.

**What has never run.** No database is read, so there is nothing here that a stub stands in
for: the route is exercised through the real application with the token machinery the other
route tests use.

Task ids: M27.7.29
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.department_console import ConsoleNavigation, Section, console_for


class EntryView(BaseModel):
    """One menu item: the design's label, the registry screen it opens and the console address."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    label: str
    to: str


class SectionView(BaseModel):
    """One heading of the department console's menu and its items, in the design's order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    heading: str
    entries: list[EntryView]


class NavigationView(BaseModel):
    """Which console this reader is given, the departments it is bounded to, and its menu.

    `console` is `company` or `department`. `sections` is empty for the company console, whose
    menu the shell holds. `departments` is read off the reader's own grants. No field counts
    anything, which is `brain.console.department_console.ConsoleNavigation`'s shape carried to
    the wire.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    console: str
    departments: list[str]
    sections: list[SectionView]


def section_view(section: Section) -> SectionView:
    """One section, copied field by field."""
    return SectionView(
        heading=section.heading,
        entries=[EntryView(key=one.key, label=one.label, to=one.to) for one in section.entries],
    )


def navigation_view(decided: ConsoleNavigation) -> NavigationView:
    """The response, copied field by field off the decision, so nothing is added on the way."""
    return NavigationView(
        console=decided.kind.value,
        departments=list(decided.departments),
        sections=[section_view(one) for one in decided.sections],
    )


router = APIRouter(prefix=API_PREFIX, tags=["console"])


@router.get("/console/navigation", response_model=NavigationView, responses=COMMON_RESPONSES)
async def console_navigation(asked: Asked) -> NavigationView:
    """The console this reader is given, at the reach this request was admitted at."""
    return navigation_view(console_for(asked.reach, asked.now))
