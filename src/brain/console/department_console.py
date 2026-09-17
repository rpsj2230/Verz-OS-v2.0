"""Which console a reader is given, and the menu of each: the company's and a department's.

`docs/screens.html` SCREEN 2 is "the same shape as the Super Admin view, bounded to one scope -
deliberately, so there is one console to learn and one to build". Every screen it names already
exists and every route behind one already narrows per reader, so a department admin opening
People was already shown their own department's people. What they were not given was the
console: the shell listed the same entries for everybody, including every screen about this
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
install and the configuration plane in one department is not offered People at all.
`held_across_the_install` still asks both halves itself, and asks the narrower question of
whether each is unrestricted, because it is public and asked of a screen directly as well as over
`navigation`.

**Both menus are declared here and served whole, since 2026-09-17.** The company console's menu
was a constant in `Shell.tsx` until then, compared with SCREEN 1 by reading the TypeScript. It
moved here with the nine groups of `docs/admin-console-architecture.md` 2.2, because the groups
are a field of the screen registry now (`brain.console.screens.MenuGroup`) and a menu kept in the
browser could not be held to it. The company's menu is the same for everybody given it, so it is
not narrowed: a section somebody cannot use answers with the route's own refusal, which is the
same answer a section that does not exist gets. See `THE_COMPANY_MENU_IS_ONE_MENU`.

**An entry is a module, and a module is not always one page yet.** Part 2.5 of that document
consolidates today's pages into modules (Roles, Capabilities and Scopes into Roles and
permissions, and so on), and the tabs that will hold them are wave 2's. Until then an entry lists
the pages it is made of, in order, and the shell draws them beneath it; an entry with one page is
one link. Rejected: one entry per page under the old labels, which is the menu Part 2.5 replaces;
and one link to the first page alone, which leaves the others reachable only by typing an address.

**An entry with no page is declared and not drawn as a link.** Eight of the forty modules have no
page yet (Service accounts, Automations, Channels, System health, Stop, Settings, Secrets, and
Approvals and autonomy, whose queue is opened from the reader's own work as My approvals). They
are in the declaration because the design draws them and a menu without them is a design
silently shortened; they carry no address because a link to a page that does not exist lands on
the console's not-found page, which reads exactly like a section the reader may not open.
`brain.ops.console_design.unbuilt_entries` names them on every traceability run, the way
`brain.ops.console_screens` names a read nobody can open. See
`A_MODULE_WITH_NO_PAGE_IS_DECLARED_AND_NEVER_A_LINK`.

**The department menu fails closed.** A reader who holds no screen across the install is not
given the install's screens, and that includes a reader who holds no screen at all: their
department console has no section, and the browser lists only the person's own work beside it.
The direction matters because the other default is the whole company console, which offers every
screen about this server to somebody the API has not said may see one.

**A department's entries are declared and the filter is the registry's.** `DEPARTMENT_NAVIGATION`
is SCREEN 2's menu, and `brain.ops.console_design` compares it with the page on every
traceability run. Which entries a reader is offered is `brain.console.screens.for_department`,
the computation `brain.console.role_surfaces.department_surface` already uses, so this is not a
second answer to what a department admin reaches. A section with nothing left in it is dropped
rather than shown empty, for `brain.console.screens.grouped`'s reason.

**A department is never offered Platform, by two routes that are held to agree.** SCREEN 2 draws
none and `department_section` refuses to build one, and `for_department` drops every Install
screen for every reader, which is every Platform screen because
`brain.console.screens.screen_gaps` holds the two groups to one set. See
`brain.console.screens.A_DEPARTMENT_ADMINISTERS_THE_WORK_IN_THE_INSTALL_AND_NOT_THE_INSTALL`.

**The departments named are the reader's own, read off their own grants.** The value of each
`department` clause on the scopes their offered screens are held in, and never the department
table: a list read from the table would name every department in the company to somebody whose
rows were carefully scoped, which is `brain.console.screens.
A_FILTER_LIST_IS_A_LISTING_OF_EVERYTHING_IT_OFFERS`. `ConsoleNavigation` carries no count of
anything, and a test holds its fields to exactly three.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock; `now` is a
parameter, as in every sibling in this package.

Task ids: M27.7.29, M27.10.1
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.console.reads import Plane, admits, plane_capability
from brain.console.screens import (
    MENU_HEADINGS,
    MenuGroup,
    Screen,
    for_department,
    navigation,
    screen,
)
from brain.core.department import DEPARTMENT_FIELD
from brain.core.entitlement import EntitlementSet
from brain.core.scope import Op, Scope

__all__ = [
    "A_MODULE_WITH_NO_PAGE_IS_DECLARED_AND_NEVER_A_LINK",
    "COMPANY_NAVIGATION",
    "DEPARTMENT_NAVIGATION",
    "THE_COMPANY_MENU_IS_ONE_MENU",
    "WHICH_CONSOLE_IS_DECIDED_BY_THE_SCOPE_A_SCREEN_IS_HELD_IN",
    "ConsoleKind",
    "ConsoleNavigation",
    "Entry",
    "Page",
    "Section",
    "console_for",
    "department_section",
    "departments_held",
    "held_across_the_install",
    "offered_sections",
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

#: Why the company console's menu is served whole rather than narrowed per reader.
THE_COMPANY_MENU_IS_ONE_MENU: Final = (
    "Everybody given the company console is given the same menu. Narrowing it per reader would "
    "make its shape a list of what each person may not open, and a section somebody cannot use "
    "already answers with its route's refusal, which is the answer a section that does not "
    "exist gets. It is served rather than kept in the browser because its groups are the "
    "registry's, and a copy in the browser could not be held to them."
)

#: Why a module the design draws and nobody has built is in the menu without an address.
A_MODULE_WITH_NO_PAGE_IS_DECLARED_AND_NEVER_A_LINK: Final = (
    "A module with no page is declared, so the menu is the design's and the gap is visible, and "
    "it carries no address, so nothing links to it. A link to a page that does not exist lands "
    "on the console's not-found page, which a person cannot tell from a section they may not "
    "open. The shell draws such an entry as not available yet, and the traceability sweep names "
    "every one of them until its page is built."
)


class ConsoleKind(enum.StrEnum):
    """The two consoles `docs/screens.html` draws for somebody who administers something."""

    #: SCREEN 1, the company overview. Its menu is `COMPANY_NAVIGATION`, the same for everybody
    #: given it.
    COMPANY = "company"
    #: SCREEN 2, the same shape bounded to a department. Its menu is `DEPARTMENT_NAVIGATION`,
    #: narrowed by `brain.console.screens.for_department`.
    DEPARTMENT = "department"


@dataclass(frozen=True)
class Page:
    """One address a menu entry opens, with the words it is listed under beneath the entry."""

    label: str
    to: str

    def __post_init__(self) -> None:
        if not self.to.startswith("/"):
            msg = (
                f"{self.label} opens {self.to!r}, which is not a console address, and the shell "
                "would resolve it against whatever page happened to be open"
            )
            raise ValueError(msg)


@dataclass(frozen=True)
class Entry:
    """One module in a menu: its key in Part 2.2, its label, its pages and the screens it opens.

    `key` is the module's code in `docs/admin-console-architecture.md` 2.2 ("C1"), which is stable
    across both menus: a department's Agents entry and the company's are one module. `screens` are
    registry keys and are checked, so an entry cannot name a screen nothing registers; which group
    they belong to is checked by the section holding the entry. `pages` is empty for a module with
    no page yet, see `A_MODULE_WITH_NO_PAGE_IS_DECLARED_AND_NEVER_A_LINK`.
    """

    key: str
    label: str
    pages: tuple[Page, ...] = ()
    screens: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for key in self.screens:
            screen(key)

    @property
    def to(self) -> str | None:
        """Where the entry opens: its first page, or nothing for a module with no page yet."""
        return self.pages[0].to if self.pages else None


@dataclass(frozen=True)
class Section:
    """One group of a menu and the entries under it, in the design's order.

    The group is the registry's `MenuGroup`, and an entry whose screens the registry files under a
    different group is refused, so the menu cannot draw a screen somewhere the registry does not
    say it lives. The heading is the group's, never written per section.
    """

    group: MenuGroup
    entries: tuple[Entry, ...]

    def __post_init__(self) -> None:
        for entry in self.entries:
            for key in entry.screens:
                filed = screen(key).menu
                if filed is not self.group:
                    msg = (
                        f"{entry.label} opens {key}, which the registry files under "
                        f"{MENU_HEADINGS[filed]}, and it is listed under "
                        f"{MENU_HEADINGS[self.group]}, so somebody following the menu looks in "
                        "one group and the registry says another"
                    )
                    raise ValueError(msg)

    @property
    def heading(self) -> str:
        """The group's heading, as the design draws it."""
        return MENU_HEADINGS[self.group]


def department_section(group: MenuGroup, *entries: Entry) -> Section:
    """A section of a department's menu, which may be any group but Platform.

    A Platform entry could only open a screen whose subject is the installation, because a
    section refuses an entry whose screens are filed elsewhere and the registry holds Platform
    to the Install group. See `brain.console.screens.
    A_DEPARTMENT_ADMINISTERS_THE_WORK_IN_THE_INSTALL_AND_NOT_THE_INSTALL`.
    """
    if group is MenuGroup.PLATFORM:
        labels = ", ".join(one.label for one in entries)
        msg = (
            f"{labels} would be offered under Platform, whose subject is the installation, and "
            "a department's console offers no screen about the install it runs in"
        )
        raise ValueError(msg)
    for entry in entries:
        if not entry.screens or not entry.pages:
            msg = (
                f"{entry.label} opens no registered screen or no page, so nothing narrows it to "
                "what a department's reader holds and it would be offered to every one of them"
            )
            raise ValueError(msg)
    return Section(group=group, entries=entries)


def _one(key: str, label: str, to: str, *screens: str) -> Entry:
    """A module that is one page, listed under its own label."""
    return Entry(key=key, label=label, pages=(Page(label=label, to=to),), screens=screens)


def _pages(key: str, label: str, pages: Sequence[tuple[str, str]], *screens: str) -> Entry:
    """A module that is several pages today, which the shell lists beneath it in this order."""
    return Entry(
        key=key,
        label=label,
        pages=tuple(Page(label=one, to=to) for one, to in pages),
        screens=screens,
    )


def _later(key: str, label: str, *screens: str) -> Entry:
    """A module the design draws with no page yet: declared, and never a link."""
    return Entry(key=key, label=label, screens=screens)


#: SCREEN 1's navigation: the nine groups of Part 2.2, forty modules, in the design's order.
#:
#: The labels are the design's and are compared with it on every traceability run. The reader's
#: own work (Ask, My workspace, My approvals, Records) is not here: it is on every console and is
#: drawn before this answer arrives, so it is the shell's (`console/src/layout/Shell.tsx`, `USE`).
COMPANY_NAVIGATION: Final[tuple[Section, ...]] = (
    Section(
        group=MenuGroup.HOME,
        entries=(_one("A1", "Dashboard", "/", "overview"),),
    ),
    Section(
        group=MenuGroup.PEOPLE,
        entries=(
            _one("B1", "People", "/people", "people"),
            _one("B2", "Departments and teams", "/departments"),
            _pages(
                "B3",
                "Roles and permissions",
                (("Roles", "/roles"), ("Capabilities", "/capabilities"), ("Scopes", "/scopes")),
                "roles",
                "capabilities",
                "scopes",
            ),
            _pages(
                "B4",
                "Access reviews and elevation",
                (("Access review", "/access_review"), ("Elevation requests", "/elevation")),
                "access_review",
                "access_friction",
            ),
            _pages(
                "B5",
                "Sign-in, directory and sessions",
                (
                    ("Sessions", "/sessions"),
                    ("Sign-in links", "/sign-in-links"),
                    ("Staff sources", "/staff_sources"),
                ),
                "sessions",
                "staff_sources",
            ),
            _later("B6", "Service accounts and API keys"),
        ),
    ),
    Section(
        group=MenuGroup.AGENTS,
        entries=(
            _pages("C1", "Agents", (("Agents", "/agents"), ("Prompts", "/prompts")), "agents"),
            _one("C2", "Agent templates", "/agent-templates"),
            _one("C3", "Skills and tools", "/skills", "skills"),
            _later("C4", "Approvals and autonomy", "approvals"),
            _later("C5", "Automations"),
            _pages(
                "C6",
                "Models and routing",
                (("Models and health", "/models"), ("Routing", "/routing")),
                "models",
            ),
        ),
    ),
    Section(
        group=MenuGroup.KNOWLEDGE,
        entries=(
            _one("D1", "Connectors", "/connectors", "connectors"),
            _one("D2", "Knowledge", "/library", "library", "knowledge_coverage"),
            _pages(
                "D3",
                "Learning and memory",
                (("Learning", "/learning"), ("Memory", "/memory")),
                "learning",
                "memory",
            ),
            _one("D4", "Fields and records", "/classification"),
            _one("D5", "Artifacts", "/artifacts", "artifacts"),
        ),
    ),
    Section(
        group=MenuGroup.CHANNELS,
        entries=(
            _later("E1", "Channels"),
            _one("E2", "Webhooks", "/webhooks"),
            _pages(
                "E3",
                "Notifications and email",
                (("Notifications and email", "/notifications"), ("Subscribers", "/subscribers")),
            ),
        ),
    ),
    Section(
        group=MenuGroup.OPERATIONS,
        entries=(
            _later("F1", "System health", "incidents"),
            _one("F2", "Runs and queue", "/runs", "runs", "queue"),
            _one("F3", "Background jobs", "/jobs"),
            _pages("F4", "Logs and errors", (("Errors", "/errors"), ("Logs", "/logs"))),
            _later("F5", "Stop", "halt"),
        ),
    ),
    Section(
        group=MenuGroup.GOVERNANCE,
        entries=(
            _one("G1", "Audit log", "/audit", "audit"),
            _one("G2", "Retention, legal holds and erasure", "/retention", "retention"),
            _one("G3", "Import and export", "/import-export", "exports"),
        ),
    ),
    Section(
        group=MenuGroup.REPORTS,
        entries=(
            _pages(
                "H1",
                "Usage and cost",
                (("Usage", "/usage"), ("Spend", "/spend"), ("Adoption", "/adoption")),
                "usage",
                "budget",
            ),
            _one("H2", "Questions and gaps", "/questions", "questions"),
            _one("H3", "Quality and canaries", "/quality", "quality"),
            _one("H4", "Service levels", "/service-levels", "service_levels"),
        ),
    ),
    Section(
        group=MenuGroup.PLATFORM,
        entries=(
            _later("I1", "Settings"),
            _one("I2", "Features and plugins", "/features"),
            _pages(
                "I3",
                "Limits, budgets and capacity",
                (("Rate limits", "/limits"), ("Capacity", "/connections")),
                "limits",
                "connections",
            ),
            _later("I4", "Secrets and credentials"),
            _one("I5", "Storage", "/storage"),
            _one("I6", "Backup and recovery", "/recovery", "recovery"),
            _pages(
                "I7",
                "Version and updates",
                (("Version and updates", "/updates"), ("This install", "/install")),
                "updates",
                "install",
            ),
        ),
    ),
)


#: SCREEN 2's navigation, as the design draws it: the company's shape, bounded to a department.
#:
#: The labels are the company menu's, so there is one console to learn, except the overview:
#: a department's is "Department", at an address of its own, because the company's is the index
#: route and a department's is a different page over the same narrowed reads. Each entry opens
#: one screen, the one `tests/unit/test_department_console.py` proves a department-scoped reader
#: sees less on.
DEPARTMENT_NAVIGATION: Final[tuple[Section, ...]] = (
    department_section(MenuGroup.HOME, _one("A1", "Department", "/department", "overview")),
    department_section(MenuGroup.PEOPLE, _one("B1", "People", "/people", "people")),
    department_section(
        MenuGroup.AGENTS,
        _one("C1", "Agents", "/agents", "agents"),
        _one("C3", "Skills and tools", "/skills", "skills"),
    ),
    department_section(
        MenuGroup.KNOWLEDGE,
        _one("D1", "Connectors", "/connectors", "connectors"),
        _one("D2", "Knowledge", "/library", "library"),
        _one("D3", "Learning and memory", "/learning", "learning"),
    ),
    department_section(MenuGroup.OPERATIONS, _one("F2", "Runs and queue", "/runs", "runs")),
    department_section(
        MenuGroup.REPORTS,
        _one("H1", "Usage and cost", "/usage", "usage"),
        _one("H2", "Questions and gaps", "/questions", "questions"),
    ),
)


@dataclass(frozen=True)
class ConsoleNavigation:
    """Which console one reader is given, the departments it is bounded to, and its menu.

    Three fields and no fourth. There is nothing here that could carry how many screens were
    left out, which is `brain.console.screens.
    A_MENU_THAT_COUNTS_WHAT_IT_HID_IS_A_DIRECTORY_OF_WHAT_YOU_CANNOT_SEE` as a shape.

    `sections` is `COMPANY_NAVIGATION` whole for the company console, and may be empty for a
    department console, which is a reader who holds no screen of the department's.
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


def offered_sections(
    offered: Sequence[Screen], declared: Sequence[Section] = DEPARTMENT_NAVIGATION
) -> tuple[Section, ...]:
    """A department's declared menu narrowed to the screens offered, empty sections dropped.

    An entry stays when every screen it opens is offered. Every screen rather than any, because
    an entry is a promise that each page under it answers this reader, and an entry kept for one
    of two screens would open a page the reader was not offered.
    """
    keys = {one.key for one in offered}
    kept: list[Section] = []
    for section in declared:
        entries = tuple(one for one in section.entries if set(one.screens) <= keys)
        if entries:
            kept.append(Section(group=section.group, entries=entries))
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
        return ConsoleNavigation(kind=ConsoleKind.COMPANY, sections=COMPANY_NAVIGATION)
    offered = for_department(entitlement, now)
    return ConsoleNavigation(
        kind=ConsoleKind.DEPARTMENT,
        departments=departments_held(offered, entitlement, now),
        sections=offered_sections(offered),
    )
