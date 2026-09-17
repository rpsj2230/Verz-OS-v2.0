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

**Both menus are in the answer, since 2026-09-17.** The company console's menu was the shell's
own constant until then; its groups are a field of the screen registry now, so it is declared in
Python beside the department's and served whole to everybody given that console. See
`brain.console.department_console.THE_COMPANY_MENU_IS_ONE_MENU`. An entry with no page yet is
sent with no address, so the browser has nothing to link it to: see
`A_MODULE_WITH_NO_PAGE_IS_DECLARED_AND_NEVER_A_LINK` in the same module.

**What has never run.** No database is read, so there is nothing here that a stub stands in
for: the route is exercised through the real application with the token machinery the other
route tests use.

Task ids: M27.7.29, M27.10.1
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.department_console import ConsoleNavigation, Entry, Section, console_for


class PageView(BaseModel):
    """One address an entry opens, and the words it is listed under beneath the entry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    to: str


class EntryView(BaseModel):
    """One module of a menu: its code, the design's label, where it opens and its pages.

    `to` is null exactly when `pages` is empty, which is a module with no page yet: the shell draws
    it as not available and links it to nothing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    label: str
    to: str | None
    pages: list[PageView]


class SectionView(BaseModel):
    """One group of a menu, by the registry's name and the design's heading, and its entries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    group: str
    heading: str
    entries: list[EntryView]


class NavigationView(BaseModel):
    """Which console this reader is given, the departments it is bounded to, and its menu.

    `console` is `company` or `department`. `sections` is the company's whole menu for the company
    console and the department's menu narrowed to this reader otherwise. `departments` is read off
    the reader's own grants. No field counts anything, which is
    `brain.console.department_console.ConsoleNavigation`'s shape carried to the wire.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    console: str
    departments: list[str]
    sections: list[SectionView]


def entry_view(entry: Entry) -> EntryView:
    """One entry, copied field by field."""
    return EntryView(
        key=entry.key,
        label=entry.label,
        to=entry.to,
        pages=[PageView(label=one.label, to=one.to) for one in entry.pages],
    )


def section_view(section: Section) -> SectionView:
    """One section, copied field by field."""
    return SectionView(
        group=section.group.value,
        heading=section.heading,
        entries=[entry_view(one) for one in section.entries],
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
