"""Which console pages are rebuilt, and what a page has to have before it counts as one.

The owner asked for every console page to be rebuilt on the shared parts, to the key screens
design, one page at a time (M27.16.1), with a designed screen drawn for each primary page before
the page is rebuilt (M27.16.4), and for a page to count as rebuilt only after a browser
walk-through of it passes on his install (M27.16.5). Until this module the first was true page by
page in commit messages, the second was true of eleven pages out of forty-two, and nothing said
which pages the third had been done for, so "rebuilt" was a word each author used for their own
page. `docs/console-pages.json` is the record, one row per primary page, and `/build/pages` is
that record in words.

**A page is rebuilt when three things are true of it, and the register will not call it rebuilt
on two.** It is built on the page kit (its source says so, and `console/tests/console-pages.test.ts`
holds the row's statement against the source), a screen for it is drawn in `docs/screens.html`,
and a walk-through of it has passed. The states are named for what is missing, not for how far
along a page is: `REBUILT`, `AWAITING_WALK_THROUGH`, `BUILT_BEFORE_ITS_SCREEN_WAS_DRAWN` and
`NOT_REBUILT`. A page built before its screen was drawn is shown as that, in those words, because
the order is the rule: a design drawn afterwards from the finished page is a description of the
page, and the design of record exists to be what a page is held to.

**The walk-through is a recorded fact and this module cannot make it.** A walk-through is a person
(or a browser run) opening the page on the install and finding it as drawn. The row holds the day
it was last passed and the release it was passed on, and a row cannot hold one for a page that is
not on the kit or has no screen: a walk-through of a page that was not yet rebuilt is a walk-through
of the old page. Every row starts without one. Rejected: deriving it from the browser harness
(`e2e/`), which walks every page of a furnished install on a pull request. That proves the page
draws
against a real API; it is not the owner's install, and the leaf says whose install.

**The set of pages is the served menu and nothing else.** A primary page is a menu entry of the
company console (`brain.console.department_console.COMPANY_NAVIGATION`) and the page of one agent,
which the roster opens and which the key screens page draws on its own. Held in both directions
by `tests/unit/test_console_pages.py`: a menu entry with no row is a page nobody is tracking, and
a row for an address the menu does not serve is a page that no longer exists. A new menu entry
therefore cannot ship untracked.

**The counts are shown, because nothing here is a count of what a reader may not see.** The
register is the same on every install and says nothing about any company's data.

Scope: domain logic. Reads a file and returns values; nothing here opens a connection.

Task ids: M27.16.1, M27.16.4, M27.16.5
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from brain.console.department_console import COMPANY_NAVIGATION

#: Where the register lives, relative to the `docs` directory.
PAGES_IN_DOCS: Final = Path("console-pages.json")

#: The key screens page, relative to the `docs` directory, and where its screens are found.
SCREENS_IN_DOCS: Final = Path("screens.html")

#: The page of one agent. It is not a menu entry (the roster opens it) and it is a primary page:
#: the owner's brief draws it on its own, and the key screens page does too.
AGENT_PAGE: Final = "/agents/:agentId"

#: Why a walk-through cannot be recorded for a page that is not rebuilt yet.
A_WALK_THROUGH_OF_AN_UNREBUILT_PAGE_IS_A_WALK_THROUGH_OF_THE_OLD_PAGE: Final = (
    "A walk-through is recorded against the page as it was rebuilt: on the shared parts, to a "
    "screen that was drawn first. One recorded before that is a walk-through of the old page, "
    "and it would count the new one rebuilt on the strength of a look at something else."
)

#: Why a page with no screen is not rebuilt, whatever it is built on.
THE_SCREEN_COMES_FIRST: Final = (
    "The design is what a rebuilt page is held to, so it is drawn before the page. A screen drawn "
    "afterwards from the finished page describes the page, and a page then agrees with its design "
    "because the design was copied from it."
)

#: A calendar day, as the register spells one.
_DAY: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: A short release identifier: the commit a walk-through was passed on.
_RELEASE: Final = re.compile(r"^[0-9a-f]{7,40}$")

#: The anchor a screen is found by: the id on its heading in `docs/screens.html`.
_SCREEN_ID: Final = re.compile(r'<div class="scrhead" id="(screen-\d+)"')


class PageState(StrEnum):
    """Where a page stands. Named for what is missing, in the order it is missed."""

    NOT_REBUILT = "not rebuilt on the shared parts"
    BUILT_BEFORE_ITS_SCREEN_WAS_DRAWN = "built, and its screen was drawn after it"
    AWAITING_WALK_THROUGH = "built to its screen, awaiting a walk-through"
    REBUILT = "rebuilt"


class RegisterError(ValueError):
    """Raised when the register cannot be read as the shape this module defines."""


@dataclass(frozen=True)
class WalkThrough:
    """The last walk-through of a page that passed: the day, and the release it passed on."""

    on: str
    release: str


@dataclass(frozen=True)
class PageRow:
    """One primary page of the console and what the register says of it."""

    address: str
    name: str
    module: str
    #: The id of the screen drawn for it in `docs/screens.html`, or None where none is drawn.
    screen: str | None
    #: Whether the page's source is built on the page kit. Held against the source by a console
    #: test.
    on_the_shared_parts: bool
    walked: WalkThrough | None

    @property
    def state(self) -> PageState:
        """What the page is, by the first thing it lacks."""
        if not self.on_the_shared_parts:
            return PageState.NOT_REBUILT
        if self.screen is None:
            return PageState.BUILT_BEFORE_ITS_SCREEN_WAS_DRAWN
        if self.walked is None:
            return PageState.AWAITING_WALK_THROUGH
        return PageState.REBUILT


@dataclass(frozen=True)
class PagesRegister:
    """Every primary page, in the order the menu draws them."""

    pages: tuple[PageRow, ...]

    def counts(self) -> Mapping[PageState, int]:
        """How many pages are in each state, every state present."""
        found = Counter(one.state for one in self.pages)
        return {state: found.get(state, 0) for state in PageState}


def _walk(raw: object, where: str) -> WalkThrough | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"on", "release"}:
        msg = f"{where}: a walk-through is {{on, release}} or null"
        raise RegisterError(msg)
    on, release = raw["on"], raw["release"]
    if not isinstance(on, str) or _DAY.fullmatch(on) is None:
        msg = f"{where}: a walk-through's day is YYYY-MM-DD"
        raise RegisterError(msg)
    try:
        date.fromisoformat(on)
    except ValueError:
        msg = f"{where}: a walk-through's day is a day in the calendar"
        raise RegisterError(msg) from None
    if not isinstance(release, str) or _RELEASE.fullmatch(release) is None:
        msg = f"{where}: a walk-through names the release it passed on by its commit"
        raise RegisterError(msg)
    return WalkThrough(on=on, release=release)


def load_pages(path: Path) -> PagesRegister:
    """The register at `path`, or `RegisterError` naming what is wrong with it."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        msg = f"{path.name} cannot be read as JSON"
        raise RegisterError(msg) from error
    rows = raw.get("pages") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        msg = f"{path.name} has no list of pages"
        raise RegisterError(msg)
    pages: list[PageRow] = []
    for index, one in enumerate(rows):
        where = f"page {index + 1}"
        if not isinstance(one, dict):
            msg = f"{where} is not an object"
            raise RegisterError(msg)
        expected = {"address", "name", "module", "screen", "on_the_shared_parts", "walked"}
        if set(one) != expected:
            msg = f"{where} must hold exactly {sorted(expected)}"
            raise RegisterError(msg)
        screen = one["screen"]
        kit = one["on_the_shared_parts"]
        if not (screen is None or isinstance(screen, str)) or not isinstance(kit, bool):
            msg = f"{where}: screen is an id or null, on_the_shared_parts is true or false"
            raise RegisterError(msg)
        text = [one["address"], one["name"], one["module"]]
        if not all(isinstance(each, str) and each for each in text):
            msg = f"{where}: address, name and module are words"
            raise RegisterError(msg)
        pages.append(
            PageRow(
                address=one["address"],
                name=one["name"],
                module=one["module"],
                screen=screen,
                on_the_shared_parts=kit,
                walked=_walk(one["walked"], where),
            )
        )
    return PagesRegister(pages=tuple(pages))


def screens_drawn(docs: Path) -> frozenset[str]:
    """The ids of the screens `docs/screens.html` draws."""
    page = (docs / SCREENS_IN_DOCS).read_text(encoding="utf-8")
    return frozenset(_SCREEN_ID.findall(page))


def menu_addresses() -> tuple[str, ...]:
    """The pages the company console's menu serves, in order, and the page of one agent."""
    found: list[str] = []
    for section in COMPANY_NAVIGATION:
        for entry in section.entries:
            found.append(entry.to)
            if entry.to == "/agents":
                found.append(AGENT_PAGE)
    return tuple(found)


def findings(register: PagesRegister, *, drawn: Iterable[str], menu: Sequence[str]) -> list[str]:
    """Everything wrong with the register, one sentence each. Empty means it is sound.

    Held in both directions against the menu, against the screens that are drawn, and against the
    order a page is rebuilt in. Each sentence names the page by its address and nothing a reader
    could not already see.
    """
    problems: list[str] = []
    addresses = [one.address for one in register.pages]
    for address, times in Counter(addresses).items():
        if times > 1:
            problems.append(f"{address} has more than one row")
    known = set(menu)
    problems.extend(
        f"{one} is served by the menu and has no row" for one in menu if one not in addresses
    )
    problems.extend(
        f"{one} has a row and the menu does not serve it" for one in addresses if one not in known
    )
    exists = set(drawn)
    for page in register.pages:
        if page.screen is not None and page.screen not in exists:
            problems.append(f"{page.address} names a screen that docs/screens.html does not draw")
        if page.walked is not None and (not page.on_the_shared_parts or page.screen is None):
            problems.append(
                f"{page.address} has a walk-through recorded and is not rebuilt: "
                f"{A_WALK_THROUGH_OF_AN_UNREBUILT_PAGE_IS_A_WALK_THROUGH_OF_THE_OLD_PAGE}"
            )
    return problems


def pages_page(register: PagesRegister) -> str:
    """The register as the markdown `/build/pages` renders: the counts, then one row a page."""
    counts = register.counts()
    total = len(register.pages)
    lines = [
        "# Console pages",
        "",
        "Which primary pages of the console are rebuilt. A page counts as rebuilt only when it is "
        "built on the shared parts, a screen for it is drawn on the key screens page first, and a "
        "walk-through of it has passed on the owner's install.",
        "",
        f"**{counts[PageState.REBUILT]} of {total} pages are rebuilt.** "
        f"{counts[PageState.AWAITING_WALK_THROUGH]} are built to a drawn screen and await a "
        f"walk-through, {counts[PageState.BUILT_BEFORE_ITS_SCREEN_WAS_DRAWN]} were built before "
        f"their screen was drawn and {counts[PageState.NOT_REBUILT]} are not on the shared parts.",
        "",
        "| Page | Module | Where it stands | Screen | Walk-through |",
        "| --- | --- | --- | --- | --- |",
    ]
    for page in register.pages:
        screen = (
            "not drawn" if page.screen is None else f"[{page.screen}](/build/screens#{page.screen})"
        )
        walked = (
            "none yet"
            if page.walked is None
            else f"passed {page.walked.on} on {page.walked.release}"
        )
        lines.append(f"| {page.name} | {page.module} | {page.state.value} | {screen} | {walked} |")
    lines.extend(
        [
            "",
            "The order is the rule: " + THE_SCREEN_COMES_FIRST,
        ]
    )
    return "\n".join(lines) + "\n"
