"""Departments, the teams inside them, and who belongs to each, as one reader may be shown them.

`docs/screens.html` SCREEN 10 draws the organisation as a tree on the left of People and Grants:
the company, its departments, and the people in each. `brain.govern_routes` served the departments
as names on the Scopes screen and declined the rest in its own words: "a membership listing is a
directory of people that `govern_surfaces.A_LISTING_OF_DEPARTMENTS_IS_AN_ORG_CHART_A_REFUSAL_HANDED_
OVER` would have to be argued about separately, per member, against a reader's scope. The membership
half is not built and is named here rather than implied." This module is that argument, and it is
three decisions that already exist, composed, and no fourth.

**Which departments: the Scopes screen's answer, unchanged.** `govern_surfaces.departments_offered`
narrows the registered department names by `admits_department` against the scope the reader holds
the Scopes screen's capability in, and returns no count of what it dropped. A department it does not
offer has no heading here, so neither its teams nor its people can put its name on the page.

**Which teams: every team of an offered department, and none of any other.** A team is a sub-scope
of its department, `<department>.<team>`, and `brain.identity.teams` says it lives inside one by
foreign key rather than by convention. So a team's name is a fact about a department the reader was
already offered. Rejected: asking `within_reach` about each team's own predicate. A department
admin's grant is a `department` clause and a team predicate is a `team` clause, so containment fails
for exactly the person who runs the department. See
`A_TEAM_IS_LISTED_UNDER_THE_DEPARTMENT_IT_BELONGS_TO`.

**Which people: the People screen's decision, row by row.** A person is placed at the department
their principal row names, `govern.Placed`, and shown when the reader holds the People screen's own
read on the console plane and `govern._in_reach` admits that row, which is exactly the pair
`govern.people` and `brain.govern_routes.people_page` ask. A person in no department sits at
`govern.NOWHERE` and reaches only a company-wide reader. See
`A_MEMBER_LIST_IS_THE_PEOPLE_SCREEN_GROUPED_AND_NEVER_WIDER`.

**Nothing is counted.** The design draws "126 people, 6 departments" and "34" beside a department.
Every figure would be computed from rows filtered to this reader, so each is the subtraction
`CLAUDE.md` names. `organisation_gaps` refuses a field that would carry one.

**What is not recorded anywhere, and is said rather than drawn.** Who is in a team: `TeamMembership`
is a type and no table holds one. Who leads a department: `DepartmentAdmin` is a type and no table
holds one, and the Access review's authority is whoever holds it over the department, which is a
grant rather than a title. What role a person holds: `role_grant` is M1.3.2 and unbuilt, which
`brain.govern_routes` records about the Roles screen.

Scope: domain logic. Nothing here opens a connection, renders anything or reads a clock.

The leaf is not complete while team membership has no table, and that half is named above the line
rather than implied by it.

Task ids: M27.7.4
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.console.govern import NOWHERE, Placed, _in_reach
from brain.console.govern_surfaces import departments_offered
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import EntitlementSet
from brain.ops.jobs import hidden_count_fields

#: Why a team needs no decision of its own.
A_TEAM_IS_LISTED_UNDER_THE_DEPARTMENT_IT_BELONGS_TO: Final = (
    "A team is a named part of one department, held to it by a foreign key. Its name tells a "
    "reader nothing about a place they were not already shown, because the department heading "
    "above it was offered by the Scopes screen's own decision. Asking containment of the team's "
    "predicate instead would refuse the department admin, whose grant names the department and "
    "not the team, so the one person who runs the teams would see none of them."
)

#: Why the member list is the People screen's decision and nothing wider.
A_MEMBER_LIST_IS_THE_PEOPLE_SCREEN_GROUPED_AND_NEVER_WIDER: Final = (
    "A list of who is in a department is a directory of people, and the People screen already "
    "decides who this reader may be shown: its own read on the console plane, and that read's "
    "scope against the row the person sits in. Grouping those same rows under department "
    "headings adds no person the People screen would not show. A person in no department sits "
    "nowhere and reaches only a company-wide reader, because a missing field never satisfies "
    "a scope."
)

#: The screen whose read decides whether a person may be named on this page.
PEOPLE_SCREEN: Final = "people"

#: The screen whose read opens this page and offers its department headings.
DEPARTMENTS_SCREEN: Final = "scopes"


@dataclass(frozen=True)
class Department:
    """One registered department, as loaded. A slug and a display name."""

    slug: str
    name: str


@dataclass(frozen=True)
class Team:
    """One registered team, and the slug of the department it belongs to."""

    department: str
    slug: str
    name: str


@dataclass(frozen=True)
class Member:
    """One person, as loaded. `department` is their principal row's, or None."""

    principal_id: str
    display_name: str
    department: str | None
    disabled: bool


@dataclass(frozen=True)
class DepartmentLine:
    """One offered department, its teams, and the people in it this reader may be shown."""

    slug: str
    name: str
    teams: tuple[Team, ...]
    members: tuple[Member, ...]


@dataclass(frozen=True)
class Organisation:
    """The page. Two lists and no figure."""

    departments: tuple[DepartmentLine, ...]
    #: People this reader may be shown whose department is none, or one no registered department
    #: carries. Each keeps the department value its row names.
    unplaced: tuple[Member, ...]


def placed(member: Member) -> Placed[Member]:
    """A person at the row their department names, or nowhere."""
    return Placed(
        record=member,
        where=NOWHERE if member.department is None else {"department": member.department},
    )


def may_name_people(entitlement: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether this reader may be shown anybody here: the People screen's own read, whole."""
    return permitted(screen(PEOPLE_SCREEN).read, entitlement, now)


def organisation(
    departments: Sequence[Department],
    teams: Sequence[Team],
    members: Sequence[Member],
    entitlement: EntitlementSet,
    now: datetime | None = None,
) -> Organisation:
    """What this reader is shown of the organisation (M27.7.4).

    Departments in the order `departments_offered` returns them, which is the order they were
    loaded in; teams by slug; people by display name and then id, so two readings of an unchanged
    directory are the same page.
    """
    offered = departments_offered([one.slug for one in departments], entitlement, now)
    names = {one.slug: one.name for one in departments}
    naming = may_name_people(entitlement, now)
    requirement = screen(PEOPLE_SCREEN).read.requires
    shown = (
        [one for one in members if _in_reach(entitlement, requirement, placed(one).where, now)]
        if naming
        else []
    )
    ordered = sorted(shown, key=lambda one: (one.display_name, one.principal_id))
    lines = tuple(
        DepartmentLine(
            slug=slug,
            name=names[slug],
            teams=tuple(
                sorted((one for one in teams if one.department == slug), key=lambda one: one.slug)
            ),
            members=tuple(one for one in ordered if one.department == slug),
        )
        for slug in offered
    )
    registered = set(names)
    return Organisation(
        departments=lines,
        unplaced=tuple(one for one in ordered if one.department not in registered),
    )


#: The row types a reader of this page is handed. Listed rather than discovered, following
#: `brain.console.govern.GOVERN_ROWS`.
ORGANISATION_ROWS: Final[tuple[type, ...]] = (Organisation, DepartmentLine, Team, Member)


def organisation_gaps(*, rows: Sequence[type] = ORGANISATION_ROWS) -> tuple[str, ...]:
    """Every row type here that would tell a reader how much they were not shown.

    Takes its input for `govern.govern_gaps`' reason: a diagnostic that only reads the healthy
    tree has nothing to report and survives every mutation.
    """
    return tuple(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(rows)
    )
