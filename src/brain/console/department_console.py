"""Which console a reader is given, and the menu each console draws, served by the API.

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

**Both menus are declared here and served, and the shell holds neither.** Until 2026-09-28 the
company console's menu was a constant in `console/src/layout/Shell.tsx`, fifty-six entries in
five groups, and every page added to the console edited that one list, which is how two pull
requests conflicted on the same lines on the same day. `COMPANY_NAVIGATION` is the nine module
groups of `docs/admin-console-architecture.md` Part 2.2, one entry per module, and an entry
whose module is several pages today lists them as tabs (`Page`), so Roles, Capabilities and
Scopes are one entry, Roles and permissions, with three tabs rather than three rows. The
grouping itself is a registry field, `brain.console.screens.ModuleGroup`, and a `Section` refuses
an entry whose screen the registry files under another group, so the registry and the menu
cannot disagree about where a screen lives.

**The company console's menu is the same for everybody given it.** It is not narrowed by the
reader's grants, and that is a decision rather than an omission: see
`THE_COMPANY_MENU_IS_THE_SAME_FOR_EVERYBODY_GIVEN_IT`. The department console's is narrowed, for
the reason it always was: its reader holds some screens in one department and not others, and
the entries are what `brain.console.screens.for_department` offers them.

**The plane grant is asked in its own scope as well as the screen's.** A plane capability is a
grant with a scope like any other, and since 2026-09-17 `brain.console.reads.permitted` counts a
plane only over a scope containing the screen's own, so a reader holding `read:grant` across the
install and the configuration plane in one department is not offered People at all.
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
both declarations with the page on every traceability run. Which entries a department's reader
is offered is `brain.console.screens.for_department`, the computation `brain.console.
role_surfaces.department_surface` already uses, so this is not a second answer to what a
department admin reaches. A section with nothing left in it is dropped rather than shown empty,
for `brain.console.screens.grouped`'s reason.

**No screen whose subject is the installation, by three routes that are held to agree.** SCREEN
2 draws none, `department_section` refuses the Platform group and any page on an Install screen at
construction, and `for_department` drops that group for every reader. See
`brain.console.screens.A_DEPARTMENT_ADMINISTERS_THE_WORK_IN_THE_INSTALL_AND_NOT_THE_INSTALL`.

**The departments named are the reader's own, read off their own grants.** The value of each
`department` clause on the scopes their offered screens are held in, and never the department
table: a list read from the table would name every department in the company to somebody whose
rows were carefully scoped, which is `brain.console.screens.
A_FILTER_LIST_IS_A_LISTING_OF_EVERYTHING_IT_OFFERS`. `ConsoleNavigation` carries no count of
anything, and a test holds its fields to exactly three.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock; `now` is a
parameter, as in every sibling in this package.

**One entry the design did not draw before 2026-09-09: the Audit log, under Governance.** See
`A_HEAD_READS_THEIR_PEOPLES_ACTIVITY_FROM_THEIR_OWN_CONSOLE`.

Task ids: M27.7.29, M1.8.3, M27.10.1
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.console.reads import Plane, admits, plane_capability
from brain.console.screens import (
    Group,
    ModuleGroup,
    Screen,
    for_department,
    navigation,
    screen,
)
from brain.core.department import DEPARTMENT_FIELD
from brain.core.entitlement import EntitlementSet
from brain.core.scope import Op, Scope

__all__ = [
    "A_HEAD_READS_THEIR_PEOPLES_ACTIVITY_FROM_THEIR_OWN_CONSOLE",
    "COMPANY_NAVIGATION",
    "DEPARTMENT_NAVIGATION",
    "THE_COMPANY_MENU_IS_THE_SAME_FOR_EVERYBODY_GIVEN_IT",
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
]

#: Why the department console offers the Audit log, which SCREEN 2 did not draw at first.
A_HEAD_READS_THEIR_PEOPLES_ACTIVITY_FROM_THEIR_OWN_CONSOLE: Final = (
    "Needs Rupash item 48 was decided on 2026-09-09: a department head reads their department's "
    "activity through audit grants over its people, which the staff sync writes. A head is given "
    "the department console, and SCREEN 2 was drawn before that decision with no Audit item, so "
    "the grants opened a screen no menu offered. The entry sits under Governance, as on the "
    "company console, and is offered only to a reader the Activity screen's own read is "
    "permitted for."
)

#: Why the console a reader is given follows the scope of what they hold.
WHICH_CONSOLE_IS_DECIDED_BY_THE_SCOPE_A_SCREEN_IS_HELD_IN: Final = (
    "A department admin and a company administrator hold the same capabilities and differ in "
    "where they hold them. So the company console is given to a reader who holds some screen "
    "across the install, capability and console plane both unrestricted, and the department "
    "console to everybody else. The employing department, a role and anything read in a "
    "browser were each rejected: the first is not where somebody administers, the second is a "
    "second permission model, and the third is that model in the copy an attacker edits."
)

#: Why the company console's menu is not narrowed by the reader's grants.
THE_COMPANY_MENU_IS_THE_SAME_FOR_EVERYBODY_GIVEN_IT: Final = (
    "The company console is given to somebody who administers the install, and several of its "
    "modules exist to say who may hold what they withhold: Learning and memory is read on the "
    "content plane, which the first administrator is not granted, and the page is where that is "
    "explained. Narrowing the menu by grants would hide the explanation from the one person who "
    "needs it and make the menu differ between two administrators for a reason neither can see. "
    "A page opened without its grant answers with the API's refusal, which is the answer a page "
    "that does not exist gets. The department console is narrowed, because its reader "
    "administers part of the company and the rest is not theirs to be told about."
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
    """One page of a module: its tab label, its console address and the registry screen it opens.

    `key` is empty for a page with no registry screen yet, which the company console offers as
    it always has and a department's console never offers, because nothing says what it would
    show at a department's scope. A key that names no screen is refused here, so a page cannot
    claim a screen nothing registers. `to` is an address the console routes; a test reads the
    route files and holds every page to one.
    """

    label: str
    to: str
    key: str = ""

    def __post_init__(self) -> None:
        if not self.to.startswith("/"):
            msg = f"{self.label} opens {self.to!r}, which is not a console address"
            raise ValueError(msg)
        if self.key:
            screen(self.key)


@dataclass(frozen=True)
class Entry:
    """One menu item: a module of Part 2.2, the design's label, and its pages in tab order.

    The item opens its first page. A module of several pages today is one entry with those pages
    as tabs, so the menu is one row per module and the pages stay reachable from inside it.
    """

    label: str
    pages: tuple[Page, ...]

    def __post_init__(self) -> None:
        if not self.pages:
            msg = f"{self.label} has no page, so the menu would link to nothing"
            raise ValueError(msg)

    @property
    def to(self) -> str:
        """The address the item opens, which is its first page's."""
        return self.pages[0].to

    @property
    def key(self) -> str:
        """The registry screen the item opens, or empty when its first page has none."""
        return self.pages[0].key


@dataclass(frozen=True)
class Section:
    """One group of the menu and the entries under it, in the design's order.

    Refuses an entry whose page the registry files under another group, which is how the registry
    field and the menu are held to one answer about where a screen lives.
    """

    group: ModuleGroup
    entries: tuple[Entry, ...]

    def __post_init__(self) -> None:
        for entry in self.entries:
            for page in entry.pages:
                if page.key and screen(page.key).module_group is not self.group:
                    msg = (
                        f"{page.label} opens {page.key}, which the registry files under "
                        f"{screen(page.key).module_group.heading}, and is drawn under "
                        f"{self.group.heading}"
                    )
                    raise ValueError(msg)

    @property
    def heading(self) -> str:
        """The heading the menu draws for this group."""
        return self.group.heading


def department_section(group: ModuleGroup, *entries: Entry) -> Section:
    """A section of a department's console, refused when it names anything about the install.

    Three refusals: the Platform group, a page with no registry screen, and a page on a screen
    whose subject is the installation. The second is here because a department's menu is narrowed
    by the registry, and a page the registry does not know is one nothing could narrow.
    """
    if group is ModuleGroup.PLATFORM:
        msg = (
            "a department's console offers no Platform group, because the subject of every "
            "screen in it is the installation"
        )
        raise ValueError(msg)
    for entry in entries:
        for page in entry.pages:
            if not page.key:
                msg = f"{page.label} opens no registry screen, so nothing could narrow it"
                raise ValueError(msg)
            if screen(page.key).group is Group.INSTALL:
                msg = (
                    f"{page.label} opens {page.key}, whose subject is the installation, and a "
                    "department's console offers no screen about the install it runs in"
                )
                raise ValueError(msg)
    return Section(group=group, entries=entries)


def _one(label: str, to: str, key: str = "") -> Entry:
    """An entry that is one page, whose tab label is the entry's own."""
    return Entry(label=label, pages=(Page(label=label, to=to, key=key),))


#: The company console's menu: the nine groups of Part 2.2, one entry per module that has a page.
#:
#: The labels are the design's, and `brain.ops.console_design` compares them with SCREEN 1 of
#: `docs/screens.html` on every traceability run, so a label spelled any other way is reported as
#: a gap. A module the map names and nothing builds yet (approvals and autonomy, system health,
#: stop) has no entry, because an entry that opens a page saying "not built" is clutter the owner
#: asked to be rid of.
#:
#: Left out on purpose, and reachable by address: Requirement checks (`/requirement-checks`),
#: which records what a person saw on this install against the product's own requirements
#: register. It is how the product's build is proved, not something a company administers.
COMPANY_NAVIGATION: Final[tuple[Section, ...]] = (
    Section(
        group=ModuleGroup.HOME,
        entries=(
            _one("Dashboard", "/", "overview"),
            # The Super Admin's view across the install (M33.1.1.1 to M33.1.1.3), served by
            # `brain.company_routes`. No registry screen of its own: each tab opens on the reads
            # its rows already sit behind, which is `brain.console.global_surfaces`' argument.
            Entry(
                label="Whole company",
                pages=(
                    Page(label="Everything", to="/company/estate"),
                    Page(label="Activity", to="/company/activity"),
                    Page(label="Consumption", to="/company/consumption"),
                ),
            ),
        ),
    ),
    Section(
        group=ModuleGroup.PEOPLE,
        entries=(
            _one("People", "/people", "people"),
            _one("Departments and teams", "/departments"),
            Entry(
                label="Roles and permissions",
                pages=(
                    Page(label="Roles", to="/roles", key="roles"),
                    Page(label="Capabilities", to="/capabilities", key="capabilities"),
                    Page(label="Scopes", to="/scopes", key="scopes"),
                    # A pack's contents are capability names, so it opens on the vocabulary's read.
                    Page(label="Packs", to="/packs", key="capabilities"),
                ),
            ),
            Entry(
                label="Access reviews and elevation",
                pages=(
                    Page(label="Access review", to="/access_review", key="access_review"),
                    Page(label="Elevation requests", to="/elevation"),
                ),
            ),
            Entry(
                label="Sign-in, directory and sessions",
                pages=(
                    Page(label="Sessions", to="/sessions", key="sessions"),
                    Page(label="Sign-in links", to="/sign-in-links"),
                    Page(label="Staff sources", to="/staff_sources", key="staff_sources"),
                ),
            ),
            _one("Service accounts and API keys", "/service-accounts"),
        ),
    ),
    Section(
        group=ModuleGroup.AGENTS,
        entries=(
            Entry(
                label="Agents",
                pages=(
                    Page(label="Agents", to="/agents", key="agents"),
                    Page(label="Prompts", to="/prompts"),
                ),
            ),
            _one("Agent templates", "/agent-templates"),
            Entry(
                label="Skills and tools",
                pages=(
                    Page(label="Skills", to="/skills", key="skills"),
                    Page(label="Tools", to="/tools"),
                ),
            ),
            _one("Automations", "/automations"),
            Entry(
                label="Models and routing",
                pages=(
                    Page(label="Models and health", to="/models", key="models"),
                    Page(label="Routing", to="/routing"),
                ),
            ),
        ),
    ),
    Section(
        group=ModuleGroup.KNOWLEDGE,
        entries=(
            _one("Connectors", "/connectors", "connectors"),
            # Documents and the solutions captured into them. Both open under the library screen,
            # because a solution becomes one of its documents once somebody approves it.
            Entry(
                label="Knowledge",
                pages=(
                    Page(label="Documents", to="/library", key="library"),
                    Page(label="Solutions", to="/solutions", key="library"),
                ),
            ),
            Entry(
                label="Learning and memory",
                pages=(
                    Page(label="Learning", to="/learning", key="learning"),
                    Page(label="Memory", to="/memory", key="memory"),
                ),
            ),
            # Part 2.2's D4 module holds `er.*` and "review merges", so the pairs waiting for a
            # person to say whether two records are one are a tab of it rather than an entry.
            Entry(
                label="Fields and records",
                pages=(
                    Page(label="Fields", to="/classification"),
                    Page(label="Possible duplicates", to="/duplicates"),
                    # The fast-lane rules over a department's tables are written under the grants
                    # its fields are changed under (`brain.rule_routes`), so they sit beside them.
                    Page(label="Quick answers", to="/rules"),
                ),
            ),
            _one("Artifacts", "/artifacts", "artifacts"),
        ),
    ),
    Section(
        group=ModuleGroup.CHANNELS,
        entries=(
            # E1 of the map: each chat surface's set-up, switch, health and bound people.
            _one("Channels", "/channels"),
            _one("Webhooks", "/webhooks"),
            Entry(
                label="Notifications and email",
                pages=(
                    Page(label="Notifications and email", to="/notifications"),
                    Page(label="Subscribers", to="/subscribers"),
                ),
            ),
        ),
    ),
    Section(
        group=ModuleGroup.OPERATIONS,
        entries=(
            _one("Runs and queue", "/runs", "runs"),
            _one("Background jobs", "/jobs"),
            _one("Stop", "/stop", "halt"),
            Entry(
                label="Logs and errors",
                pages=(Page(label="Logs", to="/logs"), Page(label="Errors", to="/errors")),
            ),
            _one("Incidents", "/incidents", "incidents"),
        ),
    ),
    Section(
        group=ModuleGroup.GOVERNANCE,
        entries=(
            _one("Audit log", "/audit", "audit"),
            _one("Retention, legal holds and erasure", "/retention", "retention"),
            _one("Import and export", "/import-export"),
            _one("Compliance", "/compliance"),
        ),
    ),
    Section(
        group=ModuleGroup.REPORTS,
        entries=(
            Entry(
                label="Usage and cost",
                pages=(
                    Page(label="Usage", to="/usage", key="usage"),
                    Page(label="Spend", to="/spend"),
                    Page(label="Adoption", to="/adoption"),
                ),
            ),
            _one("Questions and gaps", "/questions", "questions"),
            _one("Quality and canaries", "/quality", "quality"),
            _one("Service levels", "/service-levels", "service_levels"),
        ),
    ),
    Section(
        group=ModuleGroup.PLATFORM,
        entries=(
            _one("Settings", "/settings"),
            _one("Features and plugins", "/features"),
            Entry(
                label="Limits, budgets and capacity",
                pages=(
                    Page(label="Rate limits", to="/limits", key="limits"),
                    Page(label="Capacity", to="/connections", key="connections"),
                ),
            ),
            Entry(
                label="Secrets and credentials",
                pages=(
                    Page(label="Credentials", to="/credentials"),
                    Page(label="Vault activity", to="/vault"),
                ),
            ),
            _one("Storage", "/storage"),
            _one("Backup and recovery", "/recovery", "recovery"),
            Entry(
                label="Version and updates",
                pages=(
                    Page(label="Version and updates", to="/updates", key="updates"),
                    Page(label="This install", to="/install", key="install"),
                ),
            ),
        ),
    ),
)

#: SCREEN 2's navigation, as the design draws it: the company console's shape, bounded.
#:
#: The Department entry opens the overview screen at an address of its own, because the
#: company's overview is the index route and a department's is a different page over the same
#: narrowed reads.
DEPARTMENT_NAVIGATION: Final[tuple[Section, ...]] = (
    department_section(ModuleGroup.HOME, _one("Department", "/department", "overview")),
    department_section(ModuleGroup.PEOPLE, _one("People", "/people", "people")),
    department_section(
        ModuleGroup.AGENTS,
        _one("Agents", "/agents", "agents"),
        _one("Skills and tools", "/skills", "skills"),
    ),
    department_section(
        ModuleGroup.KNOWLEDGE,
        _one("Connectors", "/connectors", "connectors"),
        # A department's own administrators decide its solutions, so they are offered the tab too.
        Entry(
            label="Knowledge",
            pages=(
                Page(label="Documents", to="/library", key="library"),
                Page(label="Solutions", to="/solutions", key="library"),
            ),
        ),
        _one("Learning and memory", "/learning", "learning"),
    ),
    department_section(
        ModuleGroup.OPERATIONS,
        _one("Runs and queue", "/runs", "runs"),
        _one("Stop", "/stop", "halt"),
    ),
    # Not drawn in SCREEN 2 until item 48 was decided. See
    # `A_HEAD_READS_THEIR_PEOPLES_ACTIVITY_FROM_THEIR_OWN_CONSOLE`.
    department_section(ModuleGroup.GOVERNANCE, _one("Audit log", "/audit", "audit")),
    department_section(
        ModuleGroup.REPORTS,
        _one("Questions and gaps", "/questions", "questions"),
        _one("Usage and cost", "/usage", "usage"),
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


def _offered_sections(offered: Sequence[Screen]) -> tuple[Section, ...]:
    """`DEPARTMENT_NAVIGATION` narrowed to the screens offered, page by page.

    A page is kept when its screen is offered; an entry with no page left, and a section with no
    entry left, are dropped rather than shown empty.
    """
    keys = {one.key for one in offered}
    kept: list[Section] = []
    for section in DEPARTMENT_NAVIGATION:
        entries: list[Entry] = []
        for entry in section.entries:
            pages = tuple(one for one in entry.pages if one.key in keys)
            if pages:
                entries.append(Entry(label=entry.label, pages=pages))
        if entries:
            kept.append(Section(group=section.group, entries=tuple(entries)))
    return tuple(kept)


def console_for(entitlement: EntitlementSet, now: datetime | None = None) -> ConsoleNavigation:
    """The console this reader is given. Grants only, and no count of anything withheld.

    Asked over `navigation` rather than every registered screen. Under today's `permitted` that
    changes no answer, because `held_across_the_install` already asks both halves unrestricted,
    and a mutation replacing it is equivalent; it is kept so the console is decided over the same
    screens the menu is made of, whatever `permitted` comes to ask beyond the two scopes. See
    `WHICH_CONSOLE_IS_DECIDED_BY_THE_SCOPE_A_SCREEN_IS_HELD_IN`, and for why the company's menu
    is whole, `THE_COMPANY_MENU_IS_THE_SAME_FOR_EVERYBODY_GIVEN_IT`.
    """
    permitted_screens = navigation(entitlement, now)
    if any(held_across_the_install(one, entitlement, now) for one in permitted_screens):
        return ConsoleNavigation(kind=ConsoleKind.COMPANY, sections=COMPANY_NAVIGATION)
    offered = for_department(entitlement, now)
    return ConsoleNavigation(
        kind=ConsoleKind.DEPARTMENT,
        departments=departments_held(offered, entitlement, now),
        sections=_offered_sections(offered),
    )
