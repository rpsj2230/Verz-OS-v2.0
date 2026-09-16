"""Departments, their teams, who belongs to each and who leads each, as one reader sees them.

`docs/screens.html` SCREEN 10 draws the organisation as a tree on the left of People and Grants:
the company, its departments with a lead beside each, and the people in each. `brain.govern_routes`
served the departments as names on the Scopes screen and declined the rest in its own words: "a
membership listing is a directory of people that `govern_surfaces.A_LISTING_OF_DEPARTMENTS_IS_AN_
ORG_CHART_A_REFUSAL_HANDED_OVER` would have to be argued about separately, per member, against a
reader's scope." This module is that argument, and it is three decisions that already exist,
composed, and no fourth.

**Which departments: the Scopes screen's answer, unchanged.** `govern_surfaces.departments_offered`
narrows the registered department names by `admits_department` against the scope the reader holds
the Scopes screen's capability in, and returns no count of what it dropped. A department it does not
offer has no heading here, so neither its teams, its lead nor its people can put its name on the
page.

**Which teams: every team of an offered department, and none of any other.** A team is a sub-scope
of its department, `<department>.<team>`, and `brain.identity.teams` says it lives inside one by
foreign key rather than by convention. So a team's name is a fact about a department the reader was
already offered. Rejected: asking `within_reach` about each team's own predicate. A department
admin's grant is a `department` clause and a team predicate is a `team` clause, so containment fails
for exactly the person who runs the department. See
`A_TEAM_IS_LISTED_UNDER_THE_DEPARTMENT_IT_BELONGS_TO`.

**Which people: the People screen's decision, row by row, wherever a person appears.** A person is
placed at the department their principal row names, `govern.Placed`, and shown when the reader holds
the People screen's own read on the console plane and `govern._in_reach` admits that row, which is
exactly the pair `govern.people` and `brain.govern_routes.people_page` ask. **The same set decides a
team's members and a department's lead**, and nothing else does: a web reader looking at a web team
with somebody from finance in it sees the team without that person, and a lead they may not name is
no lead on their page. A person in no department sits at `govern.NOWHERE` and reaches only a
company-wide reader. See `A_MEMBER_LIST_IS_THE_PEOPLE_SCREEN_GROUPED_AND_NEVER_WIDER`.

**Nothing is counted.** The design draws "126 people, 6 departments" and "34" beside a department.
Every figure would be computed from rows filtered to this reader, so each is the subtraction
`CLAUDE.md` names. `organisation_gaps` refuses a field that would carry one, and a team whose
members this reader may not name reads exactly as a team nobody is in.

**Placing somebody is the authority over the department and over the person, and it confers
nothing.** `gate.team_membership` and `gate.department_lead` are where somebody sits and no resolver
reads either, so a placement widens nobody. The authority is still not free: who sits in a team and
who leads a department is the directory a department's grants are reviewed against, so writing it
takes `approve:grant`, the Access review screen's authority, held over a scope admitting both the
department's row and the person's. Rejected: inventing `admin:organisation`, which would be a second
answer to who governs a department and one the first administrator does not hold. See
`ORGANISING_IS_THE_AUTHORITY_OVER_THE_DEPARTMENT_AND_THE_PERSON`.

**Nobody appoints themselves lead.** A lead is who recertifies a department's access in M27.7.9's
own words, so a self-appointed lead is a person choosing who reviews them. See
`A_LEAD_WHO_APPOINTED_THEMSELVES_CHOSE_THEIR_OWN_REVIEWER`.

**What is still not recorded, and is said rather than drawn.** What role a person holds:
`role_grant` is M1.3.2 and unbuilt, which `brain.govern_routes` records about the Roles screen.

Scope: domain logic. Nothing here opens a connection, renders anything or reads a clock.

Task ids: M27.7.4
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.console.govern import NOWHERE, Placed, _in_reach
from brain.console.govern_surfaces import departments_offered
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
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
    "A list of who is in a department or a team, or who leads one, is a directory of people, and "
    "the People screen already decides who this reader may be shown: its own read on the console "
    "plane, and that read's scope against the row the person sits in. Grouping those same rows "
    "under department and team headings adds no person the People screen would not show. A "
    "person in no department sits nowhere and reaches only a company-wide reader, because a "
    "missing field never satisfies a scope."
)

#: Why placing somebody takes the grant authority, over both rows.
ORGANISING_IS_THE_AUTHORITY_OVER_THE_DEPARTMENT_AND_THE_PERSON: Final = (
    "A team's members and a department's lead confer nothing, and they are still the directory a "
    "department's access is reviewed against, so who may write them is who governs that "
    "department's access: approve:grant, the Access review screen's authority, held in a scope "
    "admitting the department's row and the person's. Both rows, because a web administrator "
    "placing somebody from finance into a web team is writing a fact about a person they do not "
    "govern. An invented capability would be a second answer to who governs a department."
)

#: Why nobody may appoint themselves.
A_LEAD_WHO_APPOINTED_THEMSELVES_CHOSE_THEIR_OWN_REVIEWER: Final = (
    "A department's lead is who recertifies what its people hold, so appointing yourself is "
    "choosing who reviews your own access, which is the self-grant with a title on it. Standing "
    "yourself down is permitted: it takes a title away and gives nobody anything."
)

#: The screen whose read decides whether a person may be named on this page.
PEOPLE_SCREEN: Final = "people"

#: The screen whose read opens this page and offers its department headings.
DEPARTMENTS_SCREEN: Final = "scopes"

#: The authority to place somebody or appoint a lead. The Access review screen's own requirement,
#: written out rather than read off the registry so a test can compare the two, which is how
#: `brain.console.elevation.ELEVATION_CONTROL` and `scoped_authority.REACH_AUTHORITY` are pinned.
ORGANISING_AUTHORITY: Final = Capability(value="approve:grant")


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

    @property
    def path(self) -> str:
        """`<department>.<team>`, as `brain.identity.teams.Team.path` spells it."""
        return f"{self.department}.{self.slug}"


@dataclass(frozen=True)
class Member:
    """One person, as loaded. `department` is their principal row's, or None."""

    principal_id: str
    display_name: str
    department: str | None
    disabled: bool


@dataclass(frozen=True)
class Membership:
    """One live membership, as loaded: which team, by department and slug, and whose."""

    department: str
    team: str
    principal_id: str


@dataclass(frozen=True)
class Lead:
    """One live lead, as loaded: which department, and who."""

    department: str
    principal_id: str


@dataclass(frozen=True)
class TeamLine:
    """One team of an offered department, and the members of it this reader may be shown."""

    department: str
    slug: str
    name: str
    members: tuple[Member, ...]


@dataclass(frozen=True)
class DepartmentLine:
    """One offered department, its teams, its lead and the people in it this reader may be shown."""

    slug: str
    name: str
    teams: tuple[TeamLine, ...]
    members: tuple[Member, ...]
    #: The lead, when one is recorded and this reader may name them. None reads the same either way.
    lead: Member | None = None


@dataclass(frozen=True)
class Organisation:
    """The page. Lists and no figure."""

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


def nameable(
    members: Sequence[Member], entitlement: EntitlementSet, now: datetime | None = None
) -> tuple[Member, ...]:
    """The people this reader may be named, by display name and then id. One set for the page."""
    if not may_name_people(entitlement, now):
        return ()
    requirement = screen(PEOPLE_SCREEN).read.requires
    shown = (one for one in members if _in_reach(entitlement, requirement, placed(one).where, now))
    return tuple(sorted(shown, key=lambda one: (one.display_name, one.principal_id)))


def organisation(
    departments: Sequence[Department],
    teams: Sequence[Team],
    members: Sequence[Member],
    entitlement: EntitlementSet,
    now: datetime | None = None,
    *,
    memberships: Sequence[Membership] = (),
    leads: Sequence[Lead] = (),
) -> Organisation:
    """What this reader is shown of the organisation (M27.7.4).

    Departments in the order `departments_offered` returns them, which is the order they were
    loaded in; teams by slug; people by display name and then id, wherever they appear, so two
    readings of an unchanged directory are the same page. A membership or a lead naming somebody
    outside `nameable` is dropped with nothing left in its place.
    """
    offered = departments_offered([one.slug for one in departments], entitlement, now)
    names = {one.slug: one.name for one in departments}
    ordered = nameable(members, entitlement, now)
    by_id: Mapping[str, Member] = {one.principal_id: one for one in ordered}
    in_team = {(one.department, one.team, one.principal_id) for one in memberships}
    leading = {one.department: one.principal_id for one in leads}
    lines = tuple(
        DepartmentLine(
            slug=slug,
            name=names[slug],
            teams=tuple(
                TeamLine(
                    department=slug,
                    slug=team.slug,
                    name=team.name,
                    members=tuple(
                        one for one in ordered if (slug, team.slug, one.principal_id) in in_team
                    ),
                )
                for team in sorted(
                    (one for one in teams if one.department == slug), key=lambda one: one.slug
                )
            ),
            members=tuple(one for one in ordered if one.department == slug),
            lead=by_id.get(leading.get(slug, "")),
        )
        for slug in offered
    )
    registered = set(names)
    return Organisation(
        departments=lines,
        unplaced=tuple(one for one in ordered if one.department not in registered),
    )


# ------------------------------------------------------------------------------ the writes
def may_organise(
    entitlement: EntitlementSet,
    *,
    department: str,
    person: Member,
    now: datetime | None = None,
) -> bool:
    """Whether this reader may place `person` in a team of `department`, or take them out of one.

    The authority over both rows. See
    `ORGANISING_IS_THE_AUTHORITY_OVER_THE_DEPARTMENT_AND_THE_PERSON`.
    Also what standing a lead down asks, about the lead being stood down.
    """
    return _in_reach(
        entitlement, ORGANISING_AUTHORITY, {"department": department}, now
    ) and _in_reach(entitlement, ORGANISING_AUTHORITY, placed(person).where, now)


def may_place(
    entitlement: EntitlementSet,
    *,
    department: str,
    person: Member,
    now: datetime | None = None,
) -> bool:
    """Whether this reader may put `person` somewhere new: a team, or a department's lead.

    `may_organise`, and a disabled person is refused: a placement of somebody who cannot sign in
    is a directory entry for nobody, and the next reader would take it as somebody at work.
    """
    if person.disabled:
        return False
    return may_organise(entitlement, department=department, person=person, now=now)


def may_appoint(
    entitlement: EntitlementSet,
    *,
    department: str,
    person: Member,
    now: datetime | None = None,
) -> bool:
    """Whether this reader may appoint `person` to lead `department`.

    `may_place`, and never yourself. See `A_LEAD_WHO_APPOINTED_THEMSELVES_CHOSE_THEIR_OWN_REVIEWER`.
    """
    if person.principal_id == entitlement.principal_id:
        return False
    return may_place(entitlement, department=department, person=person, now=now)


#: The row types a reader of this page is handed. Listed rather than discovered, following
#: `brain.console.govern.GOVERN_ROWS`.
ORGANISATION_ROWS: Final[tuple[type, ...]] = (
    Organisation,
    DepartmentLine,
    TeamLine,
    Team,
    Member,
    Membership,
    Lead,
)


def organisation_gaps(*, rows: Sequence[type] = ORGANISATION_ROWS) -> tuple[str, ...]:
    """Every row type here that would tell a reader how much they were not shown.

    Takes its input for `govern.govern_gaps`' reason: a diagnostic that only reads the healthy
    tree has nothing to report and survives every mutation.
    """
    return tuple(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(rows)
    )
