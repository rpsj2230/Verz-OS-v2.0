"""A department's console: the navigation SCREEN 2 draws, and whether a reader is given it.

`docs/screens.html` SCREEN 2 is "the same shape as the Super Admin view, bounded to one scope -
deliberately, so there is one console to learn and one to build". Every screen it names already
exists and every route behind one already narrows per reader, so a department admin opening
People and grants was already shown their own department's people. What they were not given was
the console: the shell listed the same entries for everybody, including every screen about this
server, and nothing anywhere could say which console a reader was in.

**Which console is the API's answer, computed from grants, and never a role or a token.** A
reader is given the company console when they hold at least one registered screen across the
installation: the screen's own capability in an unrestricted scope, and a console plane that
admits the screen, also unrestricted. Everybody else is given the department console. Rejected:
`Principal.primary_department`. That is where somebody is employed, and a person employed in one
department can administer another, or none; the department on a grant's scope is where they
administer, and it is the one the rows are narrowed by. Rejected: a role, for
`brain.console.screens.A_MENU_BUILT_FROM_ROLES_IS_A_SECOND_PERMISSION_MODEL`. Rejected: deciding
in the browser from `/me`, which is the note at the top of `console/src/layout/Shell.tsx`: a
browser that chose the menu would be a permission model in the copy an attacker edits. See
`WHICH_CONSOLE_IS_DECIDED_BY_THE_SCOPE_A_SCREEN_IS_HELD_IN`.

**The plane grant is asked in its own scope as well as the screen's.** A plane capability is a
grant with a scope like any other, and since 2026-09-17 `brain.console.reads.permitted` counts a
plane only over a scope containing the screen's own, so a reader holding `read:grant` across the
install and the configuration plane in one department is not offered People and grants at all.
`held_across_the_install` still asks both halves itself, and asks the narrower question of
whether each is unrestricted, because it is public and asked of a screen directly as well as over
`navigation`.

**The menu fails closed.** A reader who holds no screen across the install is not given the
install's screens, and that includes a reader who holds no screen at all: their department
console has no section, and the browser lists only the person's own work beneath it. The
direction matters because the other default is the whole company console, which offers every
screen about this server to somebody the API has not said may see one.

**The entries are the design's and the filter is the registry's.** `DEPARTMENT_NAVIGATION` is
SCREEN 2's menu, section by section and label by label, and `brain.ops.console_design` compares
it with the page on every traceability run. Which entries a reader is offered is
`brain.console.screens.for_department`, the computation `brain.console.role_surfaces.
department_surface` already uses, so this is not a second answer to what a department admin
reaches. A section with nothing left in it is dropped rather than shown empty, for
`brain.console.screens.grouped`'s reason.

**No screen whose subject is the installation, by two routes that are held to agree.** SCREEN 2
draws none, `Entry` refuses a key in `Group.INSTALL` at construction, and `for_department` drops
that group for every reader. See `brain.console.screens.
A_DEPARTMENT_ADMINISTERS_THE_WORK_IN_THE_INSTALL_AND_NOT_THE_INSTALL`.

**The departments named are the reader's own, read off their own grants.** The value of each
`department` clause on the scopes their offered screens are held in, and never the department
table: a list read from the table would name every department in the company to somebody whose
rows were carefully scoped, which is `brain.console.screens.
A_FILTER_LIST_IS_A_LISTING_OF_EVERYTHING_IT_OFFERS`. `ConsoleNavigation` carries no count of
anything, and a test holds its fields to exactly three.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock; `now` is a
parameter, as in every sibling in this package.

Task ids: M27.7.29
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.console.reads import Plane, admits, plane_capability
from brain.console.screens import Group, Screen, for_department, navigation, screen
from brain.core.department import DEPARTMENT_FIELD
from brain.core.entitlement import EntitlementSet
from brain.core.scope import Op, Scope

__all__ = [
    "DEPARTMENT_NAVIGATION",
    "WHICH_CONSOLE_IS_DECIDED_BY_THE_SCOPE_A_SCREEN_IS_HELD_IN",
    "ConsoleKind",
    "ConsoleNavigation",
    "Entry",
    "Section",
    "console_for",
    "departments_held",
    "held_across_the_install",
]

#: Why the console a reader is given follows the scope of what they hold.
WHICH_CONSOLE_IS_DECIDED_BY_THE_SCOPE_A_SCREEN_IS_HELD_IN: Final = (
    "A department admin and a company administrator hold the same capabilities and differ in "
    "where they hold them. So the company console is given to a reader who holds some screen "
    "across the install, capability and console plane both unrestricted, and the department "
    "console to everybody else. The employing department, a role and anything read in a "
    "browser were each rejected: the first is not where somebody administers, the second is a "
    "second permission model, and the third is that model in the copy an attacker edits."
)


class ConsoleKind(enum.StrEnum):
    """The two consoles `docs/screens.html` draws for somebody who administers something."""

    #: SCREEN 1, the company overview. Its menu is the shell's own and is the same for everybody
    #: given it.
    COMPANY = "company"
    #: SCREEN 2, the same shape bounded to a department. Its menu is `DEPARTMENT_NAVIGATION`,
    #: narrowed by `brain.console.screens.for_department`.
    DEPARTMENT = "department"


@dataclass(frozen=True)
class Entry:
    """One item in the department console's menu: the design's label, a screen and its address.

    `key` is a registry screen and is checked, so an entry cannot name a screen nothing
    registers, and cannot name one whose subject is the installation. `to` is the console address
    the shell links to, which `console/src/App.tsx` routes; a test reads the route table and
    holds every entry to it.
    """

    label: str
    key: str
    to: str

    def __post_init__(self) -> None:
        if screen(self.key).group is Group.INSTALL:
            msg = (
                f"{self.label} opens {self.key}, whose subject is the installation, and a "
                "department's console offers no screen about the install it runs in"
            )
            raise ValueError(msg)


@dataclass(frozen=True)
class Section:
    """One heading of the menu and the entries under it, in the design's order."""

    heading: str
    entries: tuple[Entry, ...]


#: SCREEN 2's navigation, as the design draws it.
#:
#: The labels are the design's and not the registry's titles: "Gaps" rather than "Questions and
#: gaps", "Knowledge" rather than "Knowledge library". `brain.ops.console_design` compares on
#: the label, so a label spelled any other way is reported as a gap in the department console.
#: The Department entry opens the overview screen at an address of its own, because the
#: company's overview is the index route and a department's is a different page over the same
#: narrowed reads.
DEPARTMENT_NAVIGATION: Final[tuple[Section, ...]] = (
    Section(
        heading="Operate",
        entries=(
            Entry(label="Department", key="overview", to="/department"),
            Entry(label="Live runs", key="runs", to="/runs"),
            Entry(label="Connectors", key="connectors", to="/connectors"),
        ),
    ),
    Section(
        heading="Govern",
        entries=(
            Entry(label="People and grants", key="people", to="/people"),
            Entry(label="Agents and leashes", key="agents", to="/agents"),
            Entry(label="Knowledge", key="library", to="/library"),
            Entry(label="Skills", key="skills", to="/skills"),
            Entry(label="Learning", key="learning", to="/learning"),
        ),
    ),
    Section(
        heading="Report",
        entries=(
            Entry(label="Gaps", key="questions", to="/questions"),
            Entry(label="Usage", key="usage", to="/usage"),
        ),
    ),
)


@dataclass(frozen=True)
class ConsoleNavigation:
    """Which console one reader is given, the departments it is bounded to, and its menu.

    Three fields and no fourth. There is nothing here that could carry how many screens were
    left out, which is `brain.console.screens.
    A_MENU_THAT_COUNTS_WHAT_IT_HID_IS_A_DIRECTORY_OF_WHAT_YOU_CANNOT_SEE` as a shape.

    `sections` is empty for the company console, whose menu is the shell's own constant and the
    same for everybody given it, and may be empty for a department console, which is a reader
    who holds no screen of the department's.
    """

    kind: ConsoleKind
    departments: tuple[str, ...] = ()
    sections: tuple[Section, ...] = ()


def _admitting_plane_scopes(
    found: Screen, entitlement: EntitlementSet, now: datetime | None
) -> tuple[Scope, ...]:
    """The scopes this reader holds each console plane in that admits the screen's plane."""
    held: list[Scope] = []
    for plane in Plane:
        if not admits(plane, found.read.plane):
            continue
        scope = entitlement.scope_for(plane_capability(plane), now)
        if scope is not None:
            held.append(scope)
    return tuple(held)


def held_across_the_install(
    found: Screen, entitlement: EntitlementSet, now: datetime | None = None
) -> bool:
    """Whether this reader holds one screen across the whole installation.

    Both halves, and each unrestricted: the screen's own capability, and at least one console
    plane that admits what the screen shows. See the module docstring for why the plane's scope
    is asked as well as the capability's.
    """
    scope = entitlement.scope_for(found.read.requires, now)
    if scope is None or not scope.is_unrestricted():
        return False
    return any(one.is_unrestricted() for one in _admitting_plane_scopes(found, entitlement, now))


def _named_departments(scope: Scope) -> tuple[str, ...]:
    """The departments one scope names, in the order its clauses hold them."""
    named: list[str] = []
    for clause in scope.clauses:
        if clause.field != DEPARTMENT_FIELD:
            continue
        if clause.op is Op.EQ and isinstance(clause.value, str):
            named.append(clause.value)
        elif clause.op is Op.IN and isinstance(clause.value, tuple):
            named.extend(clause.value)
    return tuple(named)


def departments_held(
    screens: Iterable[Screen], entitlement: EntitlementSet, now: datetime | None = None
) -> tuple[str, ...]:
    """The departments named on the scopes this reader holds these screens in, sorted, once each.

    Read off the reader's own grants and nowhere else. A scope narrowed on some other field names
    no department, and contributes nothing rather than a placeholder.
    """
    named: set[str] = set()
    for found in screens:
        scope = entitlement.scope_for(found.read.requires, now)
        if scope is not None:
            named.update(_named_departments(scope))
        for plane_scope in _admitting_plane_scopes(found, entitlement, now):
            named.update(_named_departments(plane_scope))
    return tuple(sorted(named))


def _offered_sections(offered: Sequence[Screen]) -> tuple[Section, ...]:
    """`DEPARTMENT_NAVIGATION` narrowed to the screens offered, empty sections dropped."""
    keys = {one.key for one in offered}
    kept: list[Section] = []
    for section in DEPARTMENT_NAVIGATION:
        entries = tuple(one for one in section.entries if one.key in keys)
        if entries:
            kept.append(Section(heading=section.heading, entries=entries))
    return tuple(kept)


def console_for(entitlement: EntitlementSet, now: datetime | None = None) -> ConsoleNavigation:
    """The console this reader is given. Grants only, and no count of anything withheld.

    Asked over `navigation` rather than every registered screen. Under today's `permitted` that
    changes no answer, because `held_across_the_install` already asks both halves unrestricted,
    and a mutation replacing it is equivalent; it is kept so the console is decided over the same
    screens the menu is made of, whatever `permitted` comes to ask beyond the two scopes. See
    `WHICH_CONSOLE_IS_DECIDED_BY_THE_SCOPE_A_SCREEN_IS_HELD_IN`.
    """
    permitted_screens = navigation(entitlement, now)
    if any(held_across_the_install(one, entitlement, now) for one in permitted_screens):
        return ConsoleNavigation(kind=ConsoleKind.COMPANY)
    offered = for_department(entitlement, now)
    return ConsoleNavigation(
        kind=ConsoleKind.DEPARTMENT,
        departments=departments_held(offered, entitlement, now),
        sections=_offered_sections(offered),
    )
