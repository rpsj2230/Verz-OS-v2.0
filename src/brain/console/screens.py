"""Every screen the console has, what each one needs, and why the menu is computed not written.

The console had four pages and the work breakdown named eighteen, and both numbers were wrong
for the same reason: they were lists somebody wrote down. A screen is not a page. It is a
capability, a plane and a set of axes it can be narrowed on, and once it is stated that way
the questions that were being answered by hand answer themselves: what a department admin
sees, what appears in the menu, what a filter may offer, and which screens are missing.

**The menu is derived from grants and never from a role.** `navigation` takes an
`EntitlementSet` and nothing else. It has no role parameter, so no future edit can make a
screen appear because somebody is a Super Admin: `brain.identity.roles` opens with "no role
implies a capability, including Super Admin", and a registry keyed by role would be that rule
undone in the one place it is least visible, since the screen would look permitted and the
tool behind it would refuse. `Screen.intended_for` exists and is documentation of who a screen
was designed for. `screen_gaps` fails if `navigation` ever grows a parameter that could
consult it.

**The menu must not count what it hid.** "3 more sections" is a count of things a person may
not see, which is the disclosure by subtraction that `CLAUDE.md` names as the easiest way to
break DENIED-equals-ABSENT. `navigation` returns the screens and there is no second value.

**A filter list is itself a disclosure, and it is the one everybody forgets.** Every screen
here can be narrowed by department and by person, which is what makes the console usable and
also means every screen has a dropdown listing departments. Populated from the department
table, that dropdown tells a department admin the names of every department in the company,
from a screen whose rows were carefully scoped. `offerable` intersects the values against what
the caller can already reach and returns no count of what it dropped.

**A department admin gets every screen the requirements call for, and a screen is taken out of
their menu only by writing down what it would disclose.** This module said something else
until 2026-09-10, and the sentence it said is worth keeping in view because it is the shape of
the mistake: five screens were marked `company_wide` on the argument that at a department's
scope each was "either empty or a leak". Those are two different things and only one of them
is a reason. A screen that renders empty has told the reader that the rows they may see are
none, which is what every scoped surface in this system does and discloses nothing; taking it
out of the menu instead is the subtraction disclosure, because a missing heading says there is
something here you may not have. A screen that renders somebody else's rows unnarrowed is a
leak, and that is the only case that survives.

So the derivation runs the other way now. The requirements are M27's four screen groups, which
name the screens, and M33's department admin, which asks for "everything within their scope,
same shape as the Super Admin view". Every screen is offered at a department's scope unless a
`Disclosure` in `NOT_AT_DEPARTMENT_SCOPE` names what a department-scoped reader would learn,
the row form that cannot carry a department, and what would have to change for the screen to
be offered. A flag can be set in a moment of tidying; three sentences cannot.

**One screen qualifies today, and it is rate limits.** `brain.ops.limits.LimitScope` has six
members and not one of them is a department: a limit's subject is a principal, a channel, an
agent, a connector or a widget origin. `brain.console.installation._limit_row` therefore
offers a grant's scope `{scope, subject}` and nothing else, and `Clause.matches` refuses a
field a row does not have, so a department-scoped `read:rate_limit` grant matches no row at
all while an unrestricted one matches every row in the company. "Who is currently being
throttled" is a list of who is busy with a number beside each name, and there is no third
answer at a department's scope. The other four are offered: what release is running, when the
last backup was and how much memory the profile wants are the same facts for everybody on the
install, and where the staff list is linked from renders empty at a department's scope, which
`brain.console.govern_surfaces.A_ROSTER_IS_THE_WHOLE_COMPANYS_LIST_AND_SITS_IN_NO_DEPARTMENT`
already argues is the correct answer rather than a gap.

**Screens are grouped by the question they answer, not by the module behind them.** Operate is
"what is happening now", Govern is "who may do what", Report is "what did it cost and was it
any good", Install is "what is this deployment". A person arriving with a problem knows which
of those four they are in, which is more than they know about which module owns the answer.

Scope: domain logic. Nothing here renders, opens a connection or reads a clock. The tool names
are declarations; `unregistered_tools` checks them against a registry handed in rather than
importing one, so this module has no dependency on the tool layer and the check still exists.

**This declares the screens and builds none of them**, so it claims no screen leaf. A registry
entry for "People and grants" is not that screen: the tool behind it does not exist,
`unregistered_tools` says so, and claiming M27.3.1 here would have the traceability sweep
counting a screen nobody can open. Those leaves belong to whoever writes the tools. What is
built here is the console security group's five rules about how a menu is computed, which is
what the line below claims and what `tests/unit/test_screens.py` holds it to.

Task ids: M27.5.6, M27.5.7, M27.5.8, M27.5.9, M27.5.10
"""

from __future__ import annotations

import enum
import inspect
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from brain.console.reads import ConsoleRead, Plane, permitted
from brain.core.entitlement import Capability, EntitlementSet
from brain.identity.roles import Role

#: Why the navigation cannot be keyed by role.
A_MENU_BUILT_FROM_ROLES_IS_A_SECOND_PERMISSION_MODEL: Final = (
    "brain.identity.roles opens with the rule that no role implies a capability, including "
    "Super Admin. A screen registry keyed by role undoes that in the least visible place: "
    "the menu shows the screen because of the role, the tool behind it refuses because of "
    "the grant, and the person reads a broken console rather than a permission boundary. "
    "navigation takes an EntitlementSet and has no parameter a role could arrive through."
)

#: Why the menu returns no count of what it withheld.
A_MENU_THAT_COUNTS_WHAT_IT_HID_IS_A_DIRECTORY_OF_WHAT_YOU_CANNOT_SEE: Final = (
    "Three more sections is a count of things this person may not see, and a count is the "
    "disclosure by subtraction the whole system is built to refuse. The navigation returns "
    "the screens somebody may open and there is no second value alongside it."
)

#: Why a dropdown is a read like any other.
A_FILTER_LIST_IS_A_LISTING_OF_EVERYTHING_IT_OFFERS: Final = (
    "Every screen here can be narrowed by department and by person, which is what makes the "
    "console usable, and it means every screen carries a dropdown of departments. Populated "
    "from the table it names every department in the company, on a screen whose rows were "
    "carefully scoped, and nobody reviewing the rows would think to look at the filter. The "
    "options are intersected with what the caller already reaches and no count is returned "
    "for what was dropped."
)

#: Why a screen leaves a department's menu only when somebody writes down what it would say.
AN_EMPTY_SCREEN_IS_AN_ANSWER_AND_ONLY_A_LEAK_IS_A_REASON_TO_WITHHOLD_ONE: Final = (
    "Five screens were withheld from a department's menu on the argument that each was "
    "either empty or a leak at that scope. Those are two different things and only the "
    "second is a reason. A screen that renders empty has said that the rows this reader may "
    "see are none, which is what every scoped surface here does; withholding it instead is "
    "the subtraction disclosure, because a missing heading tells the reader something is "
    "there that they may not have. A screen that renders somebody else's rows unnarrowed is "
    "a leak and is the only case that survives. So a department admin is offered every "
    "screen unless a Disclosure names what they would learn, which row form cannot carry a "
    "department, and what would have to change for the screen to be offered."
)

#: Why the withheld list is three sentences per screen rather than a boolean.
A_FLAG_CAN_BE_SET_WHILE_TIDYING_AND_THREE_SENTENCES_CANNOT: Final = (
    "company_wide=True is a keystroke, it reads as a category rather than as a decision, and "
    "the next person adding a screen about the deployment copies it from the entry above "
    "without ever asking what the screen would show at a department's scope. A Disclosure "
    "cannot be written without answering that question, and it cannot be written vaguely "
    "either: it names the row form, so a reviewer can go and read the module that builds it "
    "and disagree."
)


class Group(enum.StrEnum):
    """The four questions a console answers, which is how a lost person navigates it.

    Grouped by the reader's question rather than by the module that answers it. Somebody
    arriving with a problem knows whether they are asking what is happening, who may do what,
    what it cost, or what this deployment is; they do not know which package owns the answer.
    """

    #: What is happening right now, and how do I make it stop.
    OPERATE = "operate"
    #: Who may do what, and who decided that.
    GOVERN = "govern"
    #: What did it cost, what was asked, and was the answer any good.
    REPORT = "report"
    #: What is this deployment: version, backups, ceilings.
    INSTALL = "install"


class Axis(enum.StrEnum):
    """The ways a screen can be narrowed. One vocabulary, shared by every screen.

    One vocabulary rather than per-screen filters, because the request was that everything be
    filterable by department and by person, and that is only true if the filter is the same
    object everywhere. A screen with its own filter shape is a screen where the shared filter
    silently does nothing.
    """

    DEPARTMENT = "department"
    PERSON = "person"
    AGENT = "agent"
    CONNECTOR = "connector"
    PERIOD = "period"


#: The only return annotation `navigation` may carry. See `screen_gaps`.
ONLY_THE_SCREENS: Final = "tuple[Screen, ...]"

#: The two axes the owner asked for on everything, so a test can hold every screen to them.
EVERYWHERE: Final[frozenset[Axis]] = frozenset({Axis.DEPARTMENT, Axis.PERSON})


@dataclass(frozen=True)
class Lens:
    """How a screen was narrowed. The same type on every screen, or the promise is not kept.

    Empty strings rather than `None` for the unset axes, because a lens is built from query
    parameters and a missing parameter and an empty one arrive identically; making them the
    same value here removes a distinction nothing downstream could act on.
    """

    department: str = ""
    person: str = ""
    agent: str = ""
    connector: str = ""
    #: An opaque period key ("7d", "2026-08"), interpreted by whatever renders the screen.
    period: str = ""

    def axes_used(self) -> frozenset[Axis]:
        """Which axes this lens actually narrows on."""
        named = {
            Axis.DEPARTMENT: self.department,
            Axis.PERSON: self.person,
            Axis.AGENT: self.agent,
            Axis.CONNECTOR: self.connector,
            Axis.PERIOD: self.period,
        }
        return frozenset(axis for axis, value in named.items() if value.strip())


@dataclass(frozen=True)
class Screen:
    """One screen: what it needs, what it shows, and how it can be narrowed.

    `read` carries the capability and the plane, because a screen is a console read and this
    module refuses to be a second way of saying what one of those is. `intended_for` is
    documentation and is never consulted by anything that decides access; see
    `A_MENU_BUILT_FROM_ROLES_IS_A_SECOND_PERMISSION_MODEL`.
    """

    key: str
    title: str
    group: Group
    read: ConsoleRead
    #: What this screen can be narrowed by. Never empty: a screen nobody can filter is a
    #: screen that shows everything it has to whoever opens it.
    axes: frozenset[Axis]
    #: Who this was designed for. Documentation. Not an authorisation and not consulted.
    intended_for: frozenset[Role]
    #: One sentence, for the menu and for whoever has to explain the console to somebody.
    purpose: str = ""

    def __post_init__(self) -> None:
        if not self.axes:
            msg = (
                f"{self.key} declares no axes, so it shows everything it has to whoever "
                "opens it and no filter on it can do anything"
            )
            raise ValueError(msg)
        if self.read.screen != self.key:
            msg = (
                f"{self.key} is wired to a read that audits itself as {self.read.screen!r}, "
                "so the audit row names a screen nobody can navigate to"
            )
            raise ValueError(msg)
        if not self.purpose.strip():
            msg = f"{self.key} has no purpose sentence, so the menu entry explains nothing"
            raise ValueError(msg)

    def accepts(self, lens: Lens) -> bool:
        """Whether this screen can honour every axis the lens narrows on.

        Checked rather than ignored, because a filter that is silently dropped is worse than
        one that is refused: the reader believes they are looking at one department and are
        looking at all of them.
        """
        return lens.axes_used() <= self.axes


def _read(screen: str, tool: str, capability: str, plane: Plane) -> ConsoleRead:
    return ConsoleRead(screen=screen, tool=tool, requires=Capability(value=capability), plane=plane)


def _screen(
    key: str,
    title: str,
    group: Group,
    tool: str,
    capability: str,
    plane: Plane,
    purpose: str,
    *,
    axes: Iterable[Axis] = (),
    intended_for: Iterable[Role] = (),
) -> Screen:
    """One registry entry, with the two axes every screen has folded in.

    Department and person are added to whatever a screen declares rather than repeated on
    every entry, because the requirement is that they are on everything and a list repeated
    thirty-four times is a list with an omission in it.

    There is deliberately no parameter here for withholding a screen from a department's
    menu. See `A_FLAG_CAN_BE_SET_WHILE_TIDYING_AND_THREE_SENTENCES_CANNOT`: that decision is
    a `Disclosure` in one list, where a reviewer reads all of them at once.
    """
    return Screen(
        key=key,
        title=title,
        group=group,
        read=_read(key, tool, capability, plane),
        axes=EVERYWHERE | frozenset(axes),
        intended_for=frozenset(intended_for) or frozenset({Role.SUPER_ADMIN}),
        purpose=purpose,
    )


_ADMINS: Final = (Role.SUPER_ADMIN, Role.DEPARTMENT_ADMIN)
_WITH_AUDITOR: Final = (Role.SUPER_ADMIN, Role.DEPARTMENT_ADMIN, Role.AUDITOR)

#: Every screen the console has. The order inside a group is the order of the menu.
#:
#: A tuple rather than a mapping, because the order is information: it is the order somebody
#: reads the menu in, and a mapping would leave that to whatever the renderer sorted by.
SCREENS: Final[tuple[Screen, ...]] = (
    # --- Operate: what is happening now ----------------------------------------------------
    _screen(
        "overview",
        "Company overview",
        Group.OPERATE,
        "console.overview",
        "read:overview",
        Plane.EXISTENCE,
        "What the system did today, counted honestly: nothing here is a figure derived from "
        "rows the reader may not see.",
        axes=[Axis.PERIOD],
        intended_for=_ADMINS,
    ),
    _screen(
        "runs",
        "Live runs",
        Group.OPERATE,
        "console.runs",
        "read:run",
        Plane.CONFIGURATION,
        "What is executing right now, with its lane, its agent and how long it has been "
        "going. Configuration and not content: the question, not the answer.",
        axes=[Axis.AGENT, Axis.CONNECTOR],
        intended_for=_ADMINS,
    ),
    _screen(
        "queue",
        "Queue and automations",
        Group.OPERATE,
        "console.queue",
        "read:queue",
        Plane.CONFIGURATION,
        "What is waiting, what is scheduled, what failed and what is being retried.",
        axes=[Axis.AGENT],
        intended_for=_ADMINS,
    ),
    _screen(
        "connectors",
        "Connector health",
        Group.OPERATE,
        "console.connectors",
        "read:connector",
        Plane.CONFIGURATION,
        "Every source this install reads, whether it is answering, and when it last did.",
        axes=[Axis.CONNECTOR],
        intended_for=(Role.SUPER_ADMIN, Role.DEPARTMENT_ADMIN, Role.CONNECTOR_ADMIN),
    ),
    _screen(
        "models",
        "Models and providers",
        Group.OPERATE,
        "console.models",
        "read:model_route",
        Plane.CONFIGURATION,
        "Which model answers which lane, which provider is degraded, and what fell back.",
        axes=[Axis.PERIOD],
    ),
    _screen(
        "knowledge_coverage",
        "Knowledge coverage",
        Group.OPERATE,
        "console.knowledge_coverage",
        "read:knowledge_coverage",
        Plane.EXISTENCE,
        "Where the answers come from and where they cannot: which areas are covered, which "
        "are stale, and which have nothing behind them at all.",
        axes=[Axis.CONNECTOR, Axis.PERIOD],
        intended_for=_ADMINS,
    ),
    _screen(
        "incidents",
        "Incidents",
        Group.OPERATE,
        "console.incidents",
        "read:incident",
        Plane.CONFIGURATION,
        "What is currently degraded, what it blocks, and what has been done about it. "
        "Distinct from connector health, which is one component at a time.",
        axes=[Axis.CONNECTOR, Axis.PERIOD],
        intended_for=_ADMINS,
    ),
    _screen(
        "halt",
        "Stop",
        Group.OPERATE,
        "console.halt",
        "admin:halt",
        Plane.CONFIGURATION,
        "The stop button, and everything currently stopped. Stopping needs no approval; "
        "resuming needs a stated reason. See brain.ops.halt.",
        axes=[Axis.AGENT, Axis.CONNECTOR],
        intended_for=_ADMINS,
    ),
    # --- Govern: who may do what -----------------------------------------------------------
    _screen(
        "people",
        "People and grants",
        Group.GOVERN,
        "console.people",
        "read:grant",
        Plane.CONFIGURATION,
        "Everybody the system knows, what each of them may reach, and where that came from. "
        "The page the owner asked for so nobody has to open Keycloak.",
        intended_for=_WITH_AUDITOR,
    ),
    _screen(
        "staff_sources",
        "Staff sources",
        Group.GOVERN,
        "console.staff_sources",
        "read:staff_source",
        Plane.CONFIGURATION,
        "Where the staff list is linked from: a spreadsheet, Google Workspace, Microsoft, "
        "Lark or a directory. What each source is trusted to assert, and when it last ran.",
    ),
    _screen(
        "roles",
        "Roles",
        Group.GOVERN,
        "console.roles",
        "read:role",
        Plane.CONFIGURATION,
        "The six roles, what each one is for, and who holds it. A role governs the platform "
        "and never implies a capability, which this screen has to make visible.",
        intended_for=_WITH_AUDITOR,
    ),
    _screen(
        "capabilities",
        "Capabilities",
        Group.GOVERN,
        "console.capabilities",
        "read:capability",
        Plane.CONFIGURATION,
        "The vocabulary itself: everything that can be granted at all, and what each one "
        "unlocks. Read before writing a grant, not after wondering why one did nothing.",
        intended_for=_WITH_AUDITOR,
    ),
    _screen(
        "scopes",
        "Scopes and departments",
        Group.GOVERN,
        "console.scopes",
        "read:scope",
        Plane.CONFIGURATION,
        "The row filters a grant can carry, and the departments they are usually written against.",
        intended_for=_WITH_AUDITOR,
    ),
    _screen(
        "access_review",
        "Access review",
        Group.GOVERN,
        "console.access_review",
        "approve:grant",
        Plane.CONFIGURATION,
        "The recertification round: each department's admin confirms or removes what their "
        "people hold. The screen an auditor asks for and the one nobody builds until then.",
        axes=[Axis.PERIOD],
        intended_for=_ADMINS,
    ),
    _screen(
        "approvals",
        "Approvals",
        Group.GOVERN,
        "console.approvals",
        "approve:action",
        Plane.CONFIGURATION,
        "What is waiting on a human: an action above its rung, a grant, a promotion.",
        axes=[Axis.AGENT],
        intended_for=(Role.SUPER_ADMIN, Role.DEPARTMENT_ADMIN, Role.APPROVER),
    ),
    _screen(
        "sessions",
        "Sessions",
        Group.GOVERN,
        "console.sessions",
        "read:session",
        Plane.CONFIGURATION,
        "Who is signed in, from when, and the control to end one. A revoked grant does not "
        "end a session that is already open, which is why this is separate from people.",
        intended_for=_ADMINS,
    ),
    _screen(
        "agents",
        "Agents",
        Group.GOVERN,
        "console.agents",
        "read:agent",
        Plane.CONFIGURATION,
        "Every agent, its ceiling, its leash state, and the history of every promotion and "
        "demotion. An agent is a lens and its ceiling is the only thing that narrows it.",
        axes=[Axis.AGENT],
        intended_for=_ADMINS,
    ),
    _screen(
        "skills",
        "Skills and templates",
        Group.GOVERN,
        "console.skills",
        "read:skill",
        Plane.CONFIGURATION,
        "What agents can be taught to do, with the review queue for anything proposed.",
        axes=[Axis.AGENT],
        intended_for=_ADMINS,
    ),
    _screen(
        "library",
        "Knowledge library",
        Group.GOVERN,
        "console.library",
        "read:document",
        Plane.EXISTENCE,
        "Every document the system can draw on, with the visibility scope on each. Existence "
        "plane: this screen says a document is there, never what is in it.",
        axes=[Axis.CONNECTOR],
        intended_for=_ADMINS,
    ),
    _screen(
        "learning",
        "Learning review",
        Group.GOVERN,
        "console.learning",
        "read:learning",
        Plane.CONTENT,
        "What the system has inferred and would like to keep. Tiers separated, and tier one "
        "undoable, because a wrong inference kept quietly becomes a fact.",
        axes=[Axis.PERIOD],
        intended_for=_ADMINS,
    ),
    _screen(
        "memory",
        "Memory",
        Group.GOVERN,
        "console.memory",
        "read:memory",
        Plane.CONTENT,
        "What the system remembers about a person or a department, and every change to it.",
        axes=[Axis.AGENT],
        intended_for=_ADMINS,
    ),
    _screen(
        "artifacts",
        "Artifacts",
        Group.GOVERN,
        "console.artifacts",
        "read:artifact",
        Plane.EXISTENCE,
        "What the system produced: documents, exports, reports, with what each was built "
        "from and when it will be deleted.",
        axes=[Axis.AGENT, Axis.PERIOD],
        intended_for=_ADMINS,
    ),
    _screen(
        "exports",
        "Exports",
        Group.GOVERN,
        "console.exports",
        "read:export",
        Plane.CONFIGURATION,
        "What left the building, who took it and under whose reach. The largest "
        "exfiltration channel any permission system has, and the one least often watched.",
        axes=[Axis.PERIOD],
        intended_for=_WITH_AUDITOR,
    ),
    _screen(
        "retention",
        "Retention and erasure",
        Group.GOVERN,
        "console.retention",
        "read:retention_policy",
        Plane.CONFIGURATION,
        "How long each kind of thing is kept, what is due for deletion, and the queue of "
        "erasure requests.",
        axes=[Axis.PERIOD],
    ),
    _screen(
        "access_friction",
        "Access friction",
        Group.GOVERN,
        "console.access_friction",
        "read:denial_pattern",
        Plane.EXISTENCE,
        "Where people are repeatedly hitting a boundary, by shape and never by name. Either "
        "somebody is under-granted or somebody is probing, and both look like this.",
        axes=[Axis.PERIOD],
        intended_for=_WITH_AUDITOR,
    ),
    _screen(
        "audit",
        "Activity",
        Group.GOVERN,
        "console.audit",
        "read:audit",
        Plane.CONFIGURATION,
        "Everything that happened: every question, every grant, every export, every halt. "
        "Filterable by department and by person like everything else.",
        axes=[Axis.AGENT, Axis.CONNECTOR, Axis.PERIOD],
        intended_for=_WITH_AUDITOR,
    ),
    # --- Report: what it cost and whether it was any good -----------------------------------
    _screen(
        "usage",
        "Usage and tokens",
        Group.REPORT,
        "console.usage",
        "read:usage",
        Plane.CONFIGURATION,
        "Questions asked, tokens in and out, by person, by department, by model and by "
        "agent. What was consumed, as against what it is allowed to consume.",
        axes=[Axis.AGENT, Axis.PERIOD],
        intended_for=_ADMINS,
    ),
    _screen(
        "budget",
        "Budget and spend",
        Group.REPORT,
        "console.budget",
        "read:budget",
        Plane.CONFIGURATION,
        "What each department and person may spend, what they have spent, and what happens "
        "when they reach it. A limit rather than a report, which is why it is not usage.",
        axes=[Axis.AGENT, Axis.PERIOD],
        intended_for=_ADMINS,
    ),
    _screen(
        "questions",
        "Questions and gaps",
        Group.REPORT,
        "console.questions",
        "read:question",
        Plane.EXISTENCE,
        "What people asked and what the system could not answer. The gaps are the roadmap.",
        axes=[Axis.PERIOD],
        intended_for=_ADMINS,
    ),
    _screen(
        "quality",
        "Quality and canaries",
        Group.REPORT,
        "console.quality",
        "read:evaluation",
        Plane.CONFIGURATION,
        "How the golden corpus scored, what the permission canaries found, and what "
        "regressed since the last release.",
        axes=[Axis.PERIOD],
    ),
    # --- Install: what this deployment is ---------------------------------------------------
    _screen(
        "install",
        "This install",
        Group.INSTALL,
        "console.install",
        "read:release",
        Plane.CONFIGURATION,
        "What is actually running: the release, the migration level, the profile and the "
        "features it turns on. The first question of every support conversation.",
    ),
    _screen(
        "recovery",
        "Backup and recovery",
        Group.INSTALL,
        "console.recovery",
        "read:backup",
        Plane.CONFIGURATION,
        "The last backup, the last verified restore, the measured recovery time, and the "
        "control to run a drill.",
        axes=[Axis.PERIOD],
    ),
    _screen(
        "limits",
        "Rate limits",
        Group.INSTALL,
        "console.limits",
        "read:rate_limit",
        Plane.CONFIGURATION,
        "The ceilings on requests and what is currently being throttled by them.",
        axes=[Axis.AGENT, Axis.PERIOD],
    ),
    _screen(
        "connections",
        "Capacity",
        Group.INSTALL,
        "console.connections",
        "read:connection_budget",
        Plane.CONFIGURATION,
        "Database connections, memory ceilings and pool sizes against what is deployed. "
        "brain.ops.connections holds the arithmetic; this shows it.",
    ),
)


@dataclass(frozen=True)
class Disclosure:
    """Why one screen is not offered at a department's scope. Never a flag, always an argument.

    Three fields and none of them optional, which is
    `A_FLAG_CAN_BE_SET_WHILE_TIDYING_AND_THREE_SENTENCES_CANNOT` written as a shape.

    `row_form` is the load-bearing one and it is the reason this is not simply a sentence. It
    names the module and the keys a grant's scope is matched against, so a reviewer can open
    that module, read the row, and disagree. A withholding argued only in prose is one nobody
    can check, and the prose survives the change to the rows that made it untrue.

    `offered_when` is what has to change for the screen to come back. Without it a withheld
    screen is a permanent state rather than a piece of work, and the next person to read the
    list has no way to tell which it was.
    """

    screen: str
    #: The specific thing a department-scoped reader would learn that is not theirs.
    discloses: str
    #: The row form a grant's scope is matched against, named by the module that builds it.
    row_form: str
    #: What would have to change for this screen to be offered at a department's scope.
    offered_when: str

    def __post_init__(self) -> None:
        for name, value in (
            ("discloses", self.discloses),
            ("row_form", self.row_form),
            ("offered_when", self.offered_when),
        ):
            if len(value.split()) < 8:
                msg = (
                    f"{self.screen} is withheld from a department's menu with a {name} of "
                    f"{value!r}, which is a flag with a longer name. "
                    f"{A_FLAG_CAN_BE_SET_WHILE_TIDYING_AND_THREE_SENTENCES_CANNOT}"
                )
                raise ValueError(msg)


#: Every screen a department admin is not offered, and the argument for each.
#:
#: One entry, and the four screens that used to sit beside it are offered now. See the module
#: docstring for what changed and why: the previous rule conflated a screen that renders empty
#: with a screen that renders somebody else's rows, and only the second is a reason.
NOT_AT_DEPARTMENT_SCOPE: Final[tuple[Disclosure, ...]] = (
    Disclosure(
        screen="limits",
        discloses=(
            "which principals in the company are currently being throttled, with the ceiling "
            "they are stuck behind and how long they must wait. That is a list of who is busy "
            "enough to hit a limit, across every department, and it is a directory of people "
            "assembled from a screen whose subject looks like configuration."
        ),
        row_form=(
            "brain.console.installation._limit_row offers a grant's scope the two fields a "
            "rate limit has, which are its scope and its subject. brain.ops.limits.LimitScope "
            "has six members and none of them is a department: a subject is a principal, a "
            "channel, an agent, a connector or a widget origin. brain.core.scope.Clause."
            "matches refuses a field the row does not have, so a department-scoped grant "
            "matches no row at all and an unrestricted one matches every row in the company."
        ),
        offered_when=(
            "a rate limit carries the department its subject belongs to, so a department-"
            "scoped grant can narrow the throttling list to that department's own people. "
            "That is a change to brain.ops.limits.Limit rather than to this registry, and "
            "until it is made there is no third answer between empty and everybody."
        ),
    ),
)

#: The keys `for_department` drops, derived so the two cannot disagree.
_WITHHELD_KEYS: Final[frozenset[str]] = frozenset(one.screen for one in NOT_AT_DEPARTMENT_SCOPE)


def screen(key: str) -> Screen:
    """One screen by key, or a failure naming it.

    A lookup rather than a mapping exported directly, because the registry's order is
    information and a mapping invites somebody to iterate it for the menu.
    """
    for one in SCREENS:
        if one.key == key:
            return one
    msg = f"no screen named {key!r}"
    raise KeyError(msg)


def navigation(entitlement: EntitlementSet, now: Any = None) -> tuple[Screen, ...]:
    """The menu this caller sees. Grants only, in registry order, with no count of the rest.

    **No role parameter, and that absence is enforced.** See
    `A_MENU_BUILT_FROM_ROLES_IS_A_SECOND_PERMISSION_MODEL`, and `screen_gaps`, which reads
    this function's own signature.

    Returns one value. A second one carrying what was withheld would be a count of things
    this person may not see, which is the subtraction disclosure `CLAUDE.md` names.
    """
    return tuple(one for one in SCREENS if permitted(one.read, entitlement, now))


def for_department(entitlement: EntitlementSet, now: Any = None) -> tuple[Screen, ...]:
    """The menu for somebody administering one department rather than the install.

    The grant check is the same one, and everything it admits is offered except the screens
    `NOT_AT_DEPARTMENT_SCOPE` names. See
    `AN_EMPTY_SCREEN_IS_AN_ANSWER_AND_ONLY_A_LEAK_IS_A_REASON_TO_WITHHOLD_ONE` for why the
    subtraction is that small, and `A_FLAG_CAN_BE_SET_WHILE_TIDYING_AND_THREE_SENTENCES_CANNOT`
    for why it is a list of arguments rather than a field on the screen.

    Note what this is not: it is not an authorisation. A caller holding `read:rate_limit`
    reaches that screen by its address whatever this returns, because the tool decides that,
    and `brain.console.installation.throttled_now` narrows the rows it returns by the reader's
    own grant. This decides what is worth putting in a menu.
    """
    return tuple(one for one in navigation(entitlement, now) if one.key not in _WITHHELD_KEYS)


def grouped(screens: Sequence[Screen]) -> tuple[tuple[Group, tuple[Screen, ...]], ...]:
    """The menu in its four sections, dropping any section with nothing in it.

    Dropped rather than shown empty, because an empty section headed Govern tells the reader
    there are governance screens they may not open, which is the same subtraction in a
    different shape.
    """
    found: list[tuple[Group, tuple[Screen, ...]]] = []
    for group in Group:
        inside = tuple(one for one in screens if one.group is group)
        if inside:
            found.append((group, inside))
    return tuple(found)


def offerable(values: Iterable[str], reachable: Iterable[str]) -> tuple[str, ...]:
    """What a filter dropdown may list: the values this caller can already reach.

    See `A_FILTER_LIST_IS_A_LISTING_OF_EVERYTHING_IT_OFFERS`. Returns the values and no count
    of what was dropped, for the same reason `navigation` returns one value.

    Order follows `values` rather than being sorted here, because the caller's order is
    usually meaningful (most recent, most used) and re-sorting would discard it.
    """
    allowed = set(reachable)
    return tuple(one for one in values if one in allowed)


def screen_gaps(registered_tools: Iterable[str] = ()) -> tuple[str, ...]:
    """Everything about this registry that would let a screen show more than it should.

    Six checks. The first two hold this module to its own shape and would otherwise be
    review comments that survive exactly as long as the reviewer remembers them.
    """
    gaps: list[str] = []

    taken = set(inspect.signature(navigation).parameters)
    for forbidden in ("role", "roles", "is_admin", "super_admin", "override"):
        if forbidden in taken:
            gaps.append(
                f"navigation takes {forbidden}, so a screen can appear because of who "
                "somebody is rather than what they hold, and the tool behind it will refuse"
            )

    # Compared against the one annotation that is correct rather than searched for words that
    # would be wrong, because the list of ways to spell "and also the hidden count" is open
    # and the list of acceptable return types has one entry.
    returns = str(inspect.signature(navigation).return_annotation)
    if returns != ONLY_THE_SCREENS:
        gaps.append(
            f"navigation returns {returns} rather than {ONLY_THE_SCREENS}, and the only "
            "other thing it could usefully return is a description of what it withheld"
        )

    seen: set[str] = set()
    for one in SCREENS:
        if one.key in seen:
            gaps.append(f"{one.key} is registered twice, so one of the two is unreachable")
        seen.add(one.key)
        if not one.axes >= EVERYWHERE:
            missing = sorted(axis.value for axis in EVERYWHERE - one.axes)
            gaps.append(
                f"{one.key} cannot be filtered by {missing}, and the requirement is that "
                "every screen can be narrowed to a department and to a person"
            )

    for withheld in NOT_AT_DEPARTMENT_SCOPE:
        if withheld.screen not in seen:
            gaps.append(
                f"{withheld.screen} is withheld from a department's menu and is not a screen, "
                "so the argument for withholding it is about something nobody can open and "
                "the screen it was meant for is quietly being offered"
            )

    known = set(registered_tools)
    if known:
        for one in SCREENS:
            if one.read.tool not in known:
                gaps.append(
                    f"{one.key} is wired to {one.read.tool}, which no registry holds, so the "
                    "screen has a capability check in front of a call that cannot be made"
                )

    return tuple(gaps)


def unregistered_tools(registered_tools: Iterable[str]) -> tuple[str, ...]:
    """The tools these screens name that a registry does not hold, for a build check.

    Separate from `screen_gaps` because this one is expected to be non-empty for a while:
    the screens are declared before the tools behind them exist, deliberately, so the shape
    of the console can be argued about before thirty-four tools are written. A diagnostic
    that is red for a month is one somebody switches off, so the honest thing is to keep it
    apart from the ones that must always be green.
    """
    known = set(registered_tools)
    return tuple(one.read.tool for one in SCREENS if one.read.tool not in known)


#: How many screens exist, so a test can pin it and a person can quote it.
#:
#: Pinned rather than computed at the call site, because the interesting failure is a screen
#: disappearing in a refactor, and a test asserting `len(SCREENS) == len(SCREENS)` would not
#: notice.
SCREEN_COUNT: Final = 34

#: The screens a department admin is not offered, in registry order.
#:
#: Derived from `NOT_AT_DEPARTMENT_SCOPE` rather than written out again, so a screen can be
#: withheld in one place only and the argument travels with the key. Registry order rather
#: than declaration order, so a reader comparing this against a menu is comparing two lists in
#: the same order.
WITHHELD_AT_DEPARTMENT_SCOPE: Final[tuple[str, ...]] = tuple(
    one.key for one in SCREENS if one.key in _WITHHELD_KEYS
)
