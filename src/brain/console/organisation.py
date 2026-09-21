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

**The structure itself is two new administration capabilities, and not the grant authority.**
Placing somebody is who governs a department's access and so takes `approve:grant`, argued above.
Creating a department, giving it a team, renaming either and drawing a scope is different in kind:
it changes the vocabulary every grant is written in rather than anybody's place in it, and an
`approve:grant` holder who could also mint the scopes they grant over could grant over a boundary
nobody else drew. So `admin:department` governs departments and their teams and `admin:scope`
governs scopes, both declared in `brain.identity.first_administrator.ADMINISTRATION`, which is how
the first administrator, the registry and reconciliation learn them. See
`THE_STRUCTURE_IS_ADMINISTERED_AND_THE_PLACEMENTS_ARE_GOVERNED`.

**Where each is held is containment, through the one function that asks it.** Every act is asked
as `brain.console.scoped_authority.within_reach` over the rows the act writes: a department and its
teams sit at that department's predicate, and a scope at its own. A department administrator holding
`admin:department` over web renames web and gives it teams and nothing else, and one holding
`admin:scope` over web draws scopes inside web and retires them. Two acts are the whole company's
and ask for both capabilities held over everything: creating a department, because its scope is a
new boundary whose name no narrower authority could have been granted over, and retiring one,
because it retires every scope naming it, some of which may name departments outside a narrower
reach, and asking about those would be the refusal that says they exist. See
`FOUNDING_OR_RETIRING_A_DEPARTMENT_IS_THE_WHOLE_COMPANYS_ACT`.

**A retirement is soft and it is not a revocation.** A retired department is named by no live
scope, so the grant route, which resolves a scope by its live slug, refuses a new grant over it. A
grant already written carries its own copy of the predicate and is never touched: revocation is the
removal of a grant somebody decides to remove, and a department wound up is not that decision. See
`A_RETIRED_DEPARTMENT_IS_NAMED_BY_NO_LIVE_SCOPE` and
`A_RETIRED_DEPARTMENT_LEAVES_EVERY_GRANT_ALREADY_WRITTEN_IN_FORCE`.

Scope: domain logic. Nothing here opens a connection, renders anything or reads a clock.

Task ids: M27.7.4, M27.11.1
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.console.govern import NOWHERE, Placed, _in_reach
from brain.console.govern_surfaces import departments_offered
from brain.console.reads import permitted
from brain.console.scoped_authority import within_reach
from brain.console.screens import screen
from brain.core.department import (
    DEPARTMENT_FIELD,
    DepartmentError,
    ScopeRecord,
    create_department,
    department_scope,
    membership_scope,
)
from brain.core.department import Department as DepartmentRecord
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.scope import Op, Scope
from brain.identity.organisation_store import StructureRefusal
from brain.identity.teams import TeamError, team_path, team_scope
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

#: Why the structure takes administration capabilities of its own.
THE_STRUCTURE_IS_ADMINISTERED_AND_THE_PLACEMENTS_ARE_GOVERNED: Final = (
    "Placing somebody changes where they sit in a structure somebody else drew, and takes the "
    "authority over that department's access. Creating a department, a team or a scope changes the "
    "structure every grant is written against. A person who could grant over a scope and also draw "
    "it could grant over a boundary nobody else agreed, so the two are separate capabilities: "
    "admin:department for departments and their teams, admin:scope for scopes."
)

#: Why creating and retiring a department are asked over everything.
FOUNDING_OR_RETIRING_A_DEPARTMENT_IS_THE_WHOLE_COMPANYS_ACT: Final = (
    "A new department is a new boundary with a name no narrower authority was granted over, and "
    "retiring one retires every scope that names it, including scopes over departments a narrower "
    "authority cannot see. Asked of a department administrator, the second would refuse because of "
    "a scope they were never shown, and the refusal would say it exists. So both acts take "
    "admin:department and admin:scope held over the whole company."
)

#: What retiring a department does to the scopes that name it.
A_RETIRED_DEPARTMENT_IS_NAMED_BY_NO_LIVE_SCOPE: Final = (
    "Retiring a department retires its teams and every live scope with a department clause "
    "admitting it: its own scope and any scope over a named set of departments that includes it. "
    "A grant is written over a live scope by its name, so no new grant can be written over the "
    "retired department."
)

#: What retiring a department does not do, which is the half somebody would otherwise assume.
A_RETIRED_DEPARTMENT_LEAVES_EVERY_GRANT_ALREADY_WRITTEN_IN_FORCE: Final = (
    "Grants already written over a retired department are not retired with it. Each grant carries "
    "its own copy of the scope it was written over, and taking access away is removing a grant, "
    "which somebody decides grant by grant on the People and grants or Access review screens."
)

#: Why the company-wide scope cannot be retired from the console.
THE_COMPANY_WIDE_SCOPE_IS_NEVER_RETIRED: Final = (
    "The company-wide scope cannot be retired. It is the one scope every install is furnished "
    "with and the only one a grant over the whole company can be written at, and furnishing never "
    "writes it again once an install has been furnished."
)

#: Why a department's own scope is not retired on its own.
A_DEPARTMENTS_OWN_SCOPE_GOES_WITH_ITS_DEPARTMENT: Final = (
    "This is the scope a live department is defined by. It is retired with its department and "
    "never alone, because a live department with no scope is a name no grant can be written over."
)

#: The authority over departments and their teams. Declared in
#: `brain.identity.first_administrator.ADMINISTRATION`.
DEPARTMENT_AUTHORITY: Final = Capability(value="admin:department")

#: The authority over scopes. Declared in `brain.identity.first_administrator.ADMINISTRATION`.
SCOPE_AUTHORITY: Final = Capability(value="admin:scope")

#: What retiring a team does, said on its confirmation.
A_RETIRED_TEAM_CHANGES_NOBODYS_ACCESS: Final = (
    "Retiring a team takes it off this page, with the placements in it. Nobody's access changes, "
    "because a team confers nothing, and the placements stay on record."
)

#: What retiring a scope does, said on its confirmation.
A_RETIRED_SCOPE_TAKES_NO_GRANT_AWAY: Final = (
    "Retiring a scope stops any new grant being written over it. Grants already written over it "
    "stay in force until somebody removes them, because each grant carries its own copy of the "
    "scope."
)

#: Why every department an install writes names the same company.
ONE_INSTALL_IS_ONE_COMPANY: Final = (
    "gate.department carries a company id because the type does, and an install is one company "
    "and holds nothing of anybody else's. So every department written from the console names the "
    "install's company by one product constant rather than by a company's own name, which could "
    "only have come from configuration and would put a client's name into every row."
)

#: The company id every department written from the console carries. See
#: `ONE_INSTALL_IS_ONE_COMPANY`.
COMPANY_ID: Final = "company"

#: Why a new department is written with one scope and not the wizard's three.
A_NEW_DEPARTMENT_IS_WRITTEN_WITH_THE_SCOPE_THAT_DEFINES_IT: Final = (
    "brain.core.department.create_department drafts a department with three scopes: its own, its "
    "teams' by scope_path, and what it marks visible elsewhere by cross_department_visible. No row "
    "source under src carries either of the last two fields, so each would be a named scope that "
    "reaches no row, and a grant over one would read as access and be none. The defining scope is "
    "written with the department in one transaction, so there is never a department with no "
    "scope, and the other two are drawn when something carries the fields they test."
)


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


# ------------------------------------------------------------------------ the structure (M27.11.1)
def may_found_or_retire_departments(
    entitlement: EntitlementSet, now: datetime | None = None
) -> bool:
    """Whether this reader may create a department or retire one: both authorities, everywhere.

    See `FOUNDING_OR_RETIRING_A_DEPARTMENT_IS_THE_WHOLE_COMPANYS_ACT`.
    """
    everything = Scope.unrestricted()
    return within_reach(entitlement, DEPARTMENT_AUTHORITY, everything, now) and within_reach(
        entitlement, SCOPE_AUTHORITY, everything, now
    )


def may_shape_department(
    entitlement: EntitlementSet, *, department: str, now: datetime | None = None
) -> bool:
    """Whether this reader may rename `department`, or give it, rename or retire a team.

    `admin:department` held over the department's own predicate, which contains every row of it
    and of its teams.
    """
    return within_reach(entitlement, DEPARTMENT_AUTHORITY, department_scope(department), now)


def may_draw_scope(entitlement: EntitlementSet, scope: Scope, now: datetime | None = None) -> bool:
    """Whether this reader may create or retire a scope with this predicate.

    `admin:scope` held over a scope containing it, so nobody draws a boundary wider than their own.
    """
    return within_reach(entitlement, SCOPE_AUTHORITY, scope, now)


def names_department(scope: Scope, department: str) -> bool:
    """Whether a clause of `scope` on the department field admits `department`.

    Naming rather than admitting: the company-wide scope admits every department and names none, so
    it is never retired with one, and a clause of `Op.ANY` is that scope's clause written on one
    field. Asked of the clause itself, so an equality, a named set and a prefix are all read by the
    rule that decides which rows they reach.
    """
    row = {DEPARTMENT_FIELD: department}
    return any(
        one.field == DEPARTMENT_FIELD and one.op is not Op.ANY and one.matches(row)
        for one in scope.clauses
    )


def retired_with(slug: str, record: ScopeRecord | None, *, department: str, defining: str) -> bool:
    """Whether retiring `department`, defined by the scope `defining`, retires the scope `slug` too.

    Its own scope always, by name, even when the type refuses its row: a department's name left on
    a live scope is a name nobody can retire from the console, because a row that does not construct
    cannot be asked about. Any other scope when a clause of it names the department. `record` is
    None for a row the type refuses. See `A_RETIRED_DEPARTMENT_IS_NAMED_BY_NO_LIVE_SCOPE`.
    """
    if slug == defining:
        return True
    return record is not None and names_department(record.scope, department)


def founded(slug: str, name: str) -> tuple[DepartmentRecord, ScopeRecord]:
    """The department a creation writes and the one scope it is defined by.

    `brain.core.department.create_department`, called rather than repeated, so the department and
    its scope are the wizard's. See `A_NEW_DEPARTMENT_IS_WRITTEN_WITH_THE_SCOPE_THAT_DEFINES_IT`.
    Raises `ValueError` for a slug or a name the types refuse.
    """
    try:
        draft = create_department(COMPANY_ID, slug, name)
    except DepartmentError as refused:
        raise ValueError(str(refused)) from None
    return draft.department, draft.defining_scope


def drawn(
    slug: str, label: str, departments: Sequence[str], team: str | None = None
) -> ScopeRecord:
    """The scope a creation writes: over one department, a named set of them, or one team.

    `brain.core.department.membership_scope`, which renders one department as an equality and
    several as a membership test, and `ScopeRecord`, whose construction refuses a predicate that is
    not conjunctive or can match nothing. Never flagged as a department's own: that one is written
    with its department. Raises `ValueError` for anything the types refuse.

    A team scope (M1.5.2) is `brain.identity.teams.team_scope`, the department's clause and the
    team's, so it is inside its department by construction and names exactly one of them.
    """
    try:
        if team is not None:
            if len(departments) != 1:
                msg = "a team scope names the one department its team belongs to"
                raise ValueError(msg)
            scope = team_scope(team_path(departments[0], team))
        else:
            scope = membership_scope(departments)
    except (DepartmentError, TeamError) as refused:
        raise ValueError(str(refused)) from None
    return ScopeRecord(slug=slug, scope=scope, is_department=False, label=label)


def scope_retirement(
    entitlement: EntitlementSet,
    record: ScopeRecord,
    *,
    defines_a_live_department: bool,
    now: datetime | None = None,
) -> StructureRefusal | None:
    """Why this reader may not retire this scope, or None when nothing stands against it.

    The authority first, and the ordinary refusal for a scope outside it, so the two sentences after
    it are said only to somebody who could otherwise have retired the row. Then the company-wide
    scope, which restricts nothing and is never retired, and a department's own scope, which goes
    with its department. See `THE_COMPANY_WIDE_SCOPE_IS_NEVER_RETIRED` and
    `A_DEPARTMENTS_OWN_SCOPE_GOES_WITH_ITS_DEPARTMENT`.
    """
    if not may_draw_scope(entitlement, record.scope, now):
        return StructureRefusal.NOT_WRITABLE
    if record.scope.is_unrestricted():
        return StructureRefusal.COMPANY_WIDE_SCOPE
    if record.is_department or defines_a_live_department:
        return StructureRefusal.DEPARTMENTS_OWN_SCOPE
    return None


def may_know_taken_scope(
    entitlement: EntitlementSet, held: ScopeRecord | None, now: datetime | None = None
) -> bool:
    """Whether a creation refused because a live scope holds its name may say so.

    Only to a reader whose authority contains that scope, who could have retired it and so already
    governs it. Anybody else is given the ordinary refusal, because the slug is one namespace across
    the company and "that name is taken" about a scope outside a reader's reach would say the scope
    exists. A row the type refuses is nobody's to be told about.
    """
    return held is not None and may_draw_scope(entitlement, held.scope, now)


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
