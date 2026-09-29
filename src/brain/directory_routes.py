"""Every person this install knows, one person's page, and a person added by hand, over HTTP.

`brain.govern_routes` lists the People screen from the grant tables, which is right for the
question it answers, who holds what, and wrong for the one a directory answers: somebody who holds
no grant is on no grant row, so they never appear, and a person the People screen never shows can
never be granted anything from it. That is the gap this module closes. **The directory is every
live human principal, disabled or not, and who is listed is decided by
`brain.console.organisation.nameable`**, the People screen's own read over where each person sits,
which is the question the Departments page already asks before it lists a member. There is no
filter of this module's own. See `A_DIRECTORY_OF_THE_GRANTED_CANNOT_GRANT_ANYBODY_NEW`.

**Service principals are not people and are not listed.** They have their own screen, and a
directory mixing the two would offer "disable" beside a nightly job.

**Three fields on a person's row are other screens' facts, and each is told through that screen's
question.** Which packs somebody holds is a list of capability names spelled short, so it is carried
only under `brain.console.govern.may_name_capabilities`, the Capabilities screen's read, and
otherwise the list is empty with nothing saying it was withheld: see
`A_PACK_NAME_ON_A_PERSON_IS_THE_VOCABULARY_SPELLED_SHORT`. When somebody last signed in, and whether
with a second factor, is the Sessions screen's, so it is carried only under
`brain.console.govern.may_show_sign_in` about that person's row, and a person who never signed in
reads exactly the same: see `A_SIGN_IN_IS_TOLD_THROUGH_THE_SESSIONS_SCREENS_QUESTION`. Both are read
from the most recent `auth.session` row, and never as a count of sessions.

**A person's own page answers a hidden person exactly as it answers one who is not there.**
`GET /govern/directory/{id}` is an address anybody with a token can type, so it is the oracle
`brain.govern_routes.A_DEEP_LINK_RESOLVED_AGAINST_THE_PAGE_CANNOT_BE_AN_ORACLE` says the listing
routes avoid by having no such address. This one has the address and closes it the other way, as
`brain.agent_routes` closes `/agents/{id}`: an id that is not a principal, a service principal, a
retired person, a person `nameable` does not admit and a reader who may not open the People screen
at all are one `Absent`, raised from one function, with one message and one status. Nothing about a
hidden person is read past their own row. See
`A_PERSON_PAGE_REFUSES_A_HIDDEN_PERSON_AS_IT_REFUSES_A_MISSING_ONE`.

**What a person holds is their own live, unlapsed direct grants and their live pack assignments to
live packs**, and only under the vocabulary grant, for the reason above. A team's grants are the
team's and are on the team, not here. A scope is named beside a holding only when a live scope
carries exactly that predicate and `brain.console.govern_surfaces.scope_rows` would show it to this
reader, because a scope's name is its predicate in words. A granter is named only when `nameable`
admits them. Placements are the person's live team memberships and leads, in the departments
`departments_offered` gives this reader, which is the Departments page's own decision.

**A person is added by hand only on an install that reads no staff list** (M27.15.19). With a
source configured, people arrive from it, and a person added here would be a second record of
somebody the next sync either duplicates or marks as having left. So a caller holding the organising
authority is told that in a sentence and anybody else gets the one refusal. Without one, the
authority is `approve:grant` over the row the new person will sit in, which is
`brain.console.organisation.may_add_person`. The id is minted by
`brain.setup_routes.new_principal_id`, the same function the first administrator's comes from, and
the person arrives holding nothing. `0141`'s trigger records the insert under the person, attributed
to the caller. See `A_PERSON_IS_ADDED_BY_HAND_ONLY_WHERE_NO_STAFF_LIST_IS_READ`.

**No count, anywhere.** `truncated` says the load came back full, computed against what was loaded
and never against what `nameable` kept, for `brain.listing.THE_LOAD_IS_NEVER_NARROWED_BY_THE_QUERY`.

Task ids: M27.11.2, M27.11.3, M27.15.19
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Final, Literal, Self

import structlog
from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import Insert, Select, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import attribute
from brain.console.global_surfaces import GOVERNANCE_CONTROL
from brain.console.govern import may_name_capabilities, may_show_sign_in
from brain.console.govern_surfaces import departments_offered, scope_rows
from brain.console.organisation import (
    ORGANISING_AUTHORITY,
    Member,
    may_add_person,
    may_organise,
    nameable,
    placed,
)
from brain.console.read_replica import StalenessBanner
from brain.console.reads import permitted
from brain.console.scoped_authority import REACH_AUTHORITY
from brain.console.screens import screen
from brain.core.department import SLUG_PATTERN, ScopeRecord
from brain.core.errors import Absent, Failed
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.core.scope_sql import PredicateRefusedError
from brain.gate.admission import Assurance
from brain.gate.context import Channel
from brain.identity.departments_from import (
    DEPARTMENTS_COME_FROM_THE_STAFF_LIST,
    DepartmentsFrom,
    departments_from,
)
from brain.identity.organisation_store import moving_people, one_department
from brain.identity.principal_state_store import A_DISABLE_IS_REVERSIBLE_AND_A_LEAVER_IS_NOT
from brain.identity.staff_accounts import YOUR_ACCOUNT_IS_READY, allowed_types
from brain.identity.staff_source import (
    SELECTABLE,
    STAFF_SOURCE_SETTING,
    EmploymentStatus,
    EmploymentType,
)
from brain.identity.standing import WHY_KEPT_OUT, kept_out_because
from brain.identity.standing import Standing as ListStanding
from brain.install import InstallError, value_of
from brain.listing import Column, ListAsked, Listing
from brain.ops.replica_store import ConsoleReads
from brain.ops.staff_accounts_run import ACCOUNT_TYPES_SETTING
from brain.routing_routes import sessions_of
from brain.setup_routes import new_principal_id
from brain.tables.gate import (
    SLUG_CHARS,
    CapabilityGrantRow,
    CapabilityPackAssignmentRow,
    CapabilityPackRow,
    DepartmentRow,
    ScopeRow,
    TeamRow,
)
from brain.tables.identity import (
    DISPLAY_NAME_CHARS,
    PRINCIPAL_ID_CHARS,
    PrincipalIdentityRow,
    PrincipalRow,
    SessionRow,
)
from brain.tables.organisation import DepartmentLeadRow, TeamMembershipRow
from brain.tables.staff import StaffMemberRow

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why the directory is every person and not every grant subject.
A_DIRECTORY_OF_THE_GRANTED_CANNOT_GRANT_ANYBODY_NEW: Final = (
    "The People screen built from the grant tables lists the subjects that hold a grant, so a "
    "person who holds none is on no row and cannot be chosen for their first grant. The directory "
    "is every live person instead, and which of them this reader is shown is the People screen's "
    "own read over where each one sits, asked by the function the Departments page asks it with."
)

#: Why a person's page gives one refusal for five causes.
A_PERSON_PAGE_REFUSES_A_HIDDEN_PERSON_AS_IT_REFUSES_A_MISSING_ONE: Final = (
    "A page at an address somebody can type answers, for every id they try, whether that id is a "
    "person unless its refusals are identical. So an id nobody holds, a service principal, a "
    "retired person, a person this reader may not be shown and a reader who may not open the "
    "People screen at all are one refusal from one function, with one message and one status, "
    "and nothing about a hidden person is read beyond the row that decided they are hidden."
)

#: Why a person's packs are named only under the vocabulary's grant.
A_PACK_NAME_ON_A_PERSON_IS_THE_VOCABULARY_SPELLED_SHORT: Final = (
    "A pack's name stands for the capabilities it carries, so a list of somebody's packs is a list "
    "of what they hold, which is the disclosure the Capabilities screen governs. It is carried "
    "only for a reader who may name capabilities, and for anybody else it is empty exactly as it "
    "is for somebody who holds no pack, with nothing saying which."
)

#: Why a person's last sign-in is the Sessions screen's to tell.
A_SIGN_IN_IS_TOLD_THROUGH_THE_SESSIONS_SCREENS_QUESTION: Final = (
    "When somebody last signed in, and whether with a second factor, is what the Sessions screen "
    "shows about that person's row. It is carried here only where that screen's own read admits "
    "the row, and otherwise both fields are null, exactly as for somebody who has never signed "
    "in. It is read from their most recent session and is never a count of sessions."
)

#: Why a person is added by hand only where no staff list is read.
A_PERSON_IS_ADDED_BY_HAND_ONLY_WHERE_NO_STAFF_LIST_IS_READ: Final = (
    "An install that reads its people from a staff list learns who works there from that list, "
    "and a person typed in beside it is somebody the next sync either writes a second time or "
    "marks as having left. So adding by hand is offered only when the install reads no list, and "
    "a caller who holds the authority is told why when one is read."
)

# ---------------------------------------------------------------- served sentences

#: What adding a person does, served beside the control.
ADDING_A_PERSON_GRANTS_NOTHING: Final = (
    "Adding a person writes them into this install's directory holding nothing: they can then be "
    "linked to a sign-in, placed in a team and granted, each by whoever may do that. Nothing is "
    "sent to them and no account is made at the identity provider."
)

#: What the control says instead when a staff list is read, and the refusal a holder is told.
PEOPLE_ARRIVE_FROM_THE_STAFF_SOURCE: Final = (
    "This install reads its people from its staff source, so nobody is added here by hand: "
    "somebody added to that list arrives with the next sync."
)

#: What a capability that came with a pack means for removing it, served on a person's page.
A_CAPABILITY_FROM_A_PACK_GOES_WITH_THE_PACK: Final = (
    "A capability that came with a pack is removed with the whole pack, because a pack's "
    "capabilities are granted together; removing one of them on its own is refused and names the "
    "pack."
)

#: The readable refusal of an addition naming a department no live row carries.
A_DEPARTMENT_NAMED_IS_NOT_LIVE: Final = "that department is not a live department on this install"

# ----------------------------------------------------------------- the bounds

#: The most people one directory answer is loaded from, whatever page, search, filter or order was
#: asked. A resource bound and not a permission one: see
#: `brain.listing.THE_LOAD_IS_NEVER_NARROWED_BY_THE_QUERY`.
MAX_PEOPLE: Final = 1000

#: The most departments a name or an offer is looked up among. A bound on the load.
MAX_DEPARTMENTS: Final = 500

#: The most scopes a holding's predicate is matched against, and the most holdings, team places
#: and granters one person's page is loaded from. Bounds on the load.
MAX_SCOPES: Final = 200
MAX_HELD: Final = 500

#: How much of a pack's description is its label, as `brain.govern_routes.PACK_LABEL_CHARS` says.
PACK_LABEL_CHARS: Final = 120

#: The screen whose read opens the directory and decides who is listed.
PEOPLE_SCREEN: Final = "people"

# ------------------------------------------------------------------- the shapes

Standing = Literal["live", "disabled"]


class DirectoryPersonView(BaseModel):
    """One person, as this reader may be shown them. No figure of any kind."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    display_name: str
    #: The slug their principal row names, or null for somebody in no department.
    department: str | None
    #: The live department carrying that slug, by name, or null when none does.
    department_name: str | None
    employment: str
    standing: Standing
    #: Whether their most recent session had a second factor. Null when not told or never.
    second_factor: bool | None
    #: When their most recent session began. Null when not told or never.
    last_signed_in_at: datetime | None
    #: The live packs assigned to them, by slug. Empty when not told or none.
    packs: list[str]
    #: Where the staff list says they stand: active, suspended, left or not_activated. Null for
    #: somebody the list does not name, or an install that reads no list (M1.6.13).
    staff_status: str | None = None
    #: The employment type the staff list records for them, or null when it records none.
    employment_type: str | None = None


class DirectoryPage(BaseModel):
    """One page of the directory, and what this reader may do from it. Presentation flags only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[DirectoryPersonView]
    #: Present exactly when a further person this reader may see matches. See `brain.listing`.
    next_cursor: str | None = None
    #: The load came back full. Never how much more there is.
    truncated: bool
    #: The grant authority is held somewhere, so a grant may be offered.
    editable: bool
    #: The disable authority is held somewhere.
    may_disable: bool
    #: A person may be added by hand: no staff list is read and the authority is held somewhere.
    may_add: bool
    #: What adding does, or that people arrive from the staff source.
    adding: str
    #: With a staff list read: the sentence to pass on to somebody whose account the sync made.
    account_ready: str | None = None
    #: Several people may be moved to a department: departments are managed on People and the
    #: organising authority is held somewhere (M1.6.20). Presentation only; the route asks again.
    may_move: bool = False
    disabling: str = A_DISABLE_IS_REVERSIBLE_AND_A_LEAVER_IS_NOT
    staleness: StalenessBanner | None = None


class NamedDepartment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    name: str


class TeamPlace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    slug: str
    name: str


class PlacementView(BaseModel):
    """Where a person sits, in the departments this reader is offered."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: NamedDepartment | None = None
    teams: list[TeamPlace] = Field(default_factory=list)
    leads: list[NamedDepartment] = Field(default_factory=list)


class HeldView(BaseModel):
    """One thing a person holds: a direct grant, or a pack assignment and everything in it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["grant", "pack"]
    #: The grant's id or the assignment's id. For the console's acts, never shown as a figure.
    row_id: str
    capabilities: list[str]
    pack: str | None = None
    pack_label: str | None = None
    pack_version: int | None = None
    scope: dict[str, Any]
    #: The live scope with exactly this predicate, when one does and this reader may be shown it.
    scope_slug: str | None = None
    scope_label: str | None = None
    granted_by: str
    #: The granter's name, when this reader may be shown the granter.
    granted_by_name: str | None = None
    reason: str
    granted_at: datetime
    not_after: datetime | None = None


class PersonDetail(BaseModel):
    """One person's page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    person: DirectoryPersonView
    placements: PlacementView
    held: list[HeldView]
    editable: bool
    may_disable: bool
    may_organise: bool
    disabling: str = A_DISABLE_IS_REVERSIBLE_AND_A_LEAVER_IS_NOT
    from_a_pack: str = A_CAPABILITY_FROM_A_PACK_GOES_WITH_THE_PACK
    staleness: StalenessBanner | None = None
    #: Why the staff list keeps them from signing in or asking, or null when it does not
    #: (`brain.identity.standing.WHY_KEPT_OUT`, M1.6.14).
    kept_out: str | None = None
    #: Departments are managed on People on this install, so their department is set there and
    #: not at the staff source (M1.6.19). Presentation only.
    department_set_on_people: bool = False


#: A person's name as a person reads it, trimmed, as `auth.principal.display_name_present` requires.
PersonName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=DISPLAY_NAME_CHARS)
]

#: A department's short name, as `gate.department.slug` holds one.
DepartmentSlug = Annotated[str, Field(min_length=2, max_length=SLUG_CHARS, pattern=SLUG_PATTERN)]


class PersonAdding(BaseModel):
    """A person to add by hand: a name, where they sit, how they are engaged, and until when.

    `extra="forbid"`, so a body naming an id, a kind or a granter is refused rather than ignored:
    the id is minted, the kind is a person, and the actor is the token. A bounded engagement
    without an end is refused by `brain.core.principal.Principal` itself, constructed here so the
    rule is that type's and a 422 names it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: PersonName
    department: DepartmentSlug | None = None
    employment: Employment = Employment.STAFF
    not_after: datetime | None = None

    @model_validator(mode="after")
    def _is_a_person(self) -> Self:
        if self.employment is Employment.SERVICE:
            msg = "a person added by hand is not a service account; those have their own screen"
            raise ValueError(msg)
        Principal(
            id="u_draft",
            kind=PrincipalKind.HUMAN,
            employment=self.employment,
            display_name=self.display_name,
            primary_department=self.department,
            not_after=self.not_after,
        )
        return self


class PersonAdded(BaseModel):
    """The person as the database now holds them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    display_name: str
    department: str | None
    created_at: datetime


#: Where several people are moved to one department.
MOVING_PATH: Final = "/govern/directory/department"

#: The most people one move carries. A bound on the request, as `/govern/grants/several` has one.
MAX_MOVED: Final = 200


#: A person's id as a move names one.
PersonId = Annotated[str, StringConstraints(min_length=1, max_length=PRINCIPAL_ID_CHARS)]


class DepartmentMoving(BaseModel):
    """Several people to put in one department, on an install that manages departments on People.

    `extra="forbid"`, so a body naming anything else is refused rather than ignored.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_ids: list[PersonId] = Field(min_length=1, max_length=MAX_MOVED)
    department: DepartmentSlug


class DepartmentMoved(BaseModel):
    """Who was moved. Somebody already in the department is not a move, and is not listed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    moved: list[str]
    told: str


#: Why a move is all of the people named or none of them.
A_MOVE_IS_EVERYBODY_OR_NOBODY: Final = (
    "Several people are moved in one statement or not at all. A move that went through for some of "
    "them would leave the page showing a selection the database no longer matches, and the one "
    "refusal for any of them says nothing about which person this reader may not move."
)


# ---------------------------------------------------------------- the statements


def live_people(limit: int) -> Select[tuple[str, str, str | None, str, datetime | None]]:
    """Every live person, disabled or not: id, name, department, engagement, disablement."""
    return (
        select(
            PrincipalRow.id,
            PrincipalRow.display_name,
            PrincipalRow.primary_department,
            PrincipalRow.employment,
            PrincipalRow.disabled_at,
        )
        .where(
            PrincipalRow.deleted_at.is_(None),
            PrincipalRow.kind == PrincipalKind.HUMAN.value,
        )
        .order_by(PrincipalRow.display_name, PrincipalRow.id)
        .limit(limit)
    )


def one_person(principal_id: str) -> Select[tuple[str, str, str | None, str, datetime | None]]:
    """One live person by id, or nothing. A service principal and a retired row are nothing."""
    return select(
        PrincipalRow.id,
        PrincipalRow.display_name,
        PrincipalRow.primary_department,
        PrincipalRow.employment,
        PrincipalRow.disabled_at,
    ).where(
        PrincipalRow.id == principal_id,
        PrincipalRow.deleted_at.is_(None),
        PrincipalRow.kind == PrincipalKind.HUMAN.value,
    )


def people_by_id(
    principal_ids: Sequence[str],
) -> Select[tuple[str, str, str | None, str, datetime | None]]:
    """These live people, as `one_person` reads one, in id order."""
    return (
        select(
            PrincipalRow.id,
            PrincipalRow.display_name,
            PrincipalRow.primary_department,
            PrincipalRow.employment,
            PrincipalRow.disabled_at,
        )
        .where(
            PrincipalRow.id.in_(list(principal_ids)),
            PrincipalRow.deleted_at.is_(None),
            PrincipalRow.kind == PrincipalKind.HUMAN.value,
        )
        .order_by(PrincipalRow.id)
    )


def people_named(principal_ids: Sequence[str]) -> Select[tuple[str, str, str | None]]:
    """These live people's names and departments, for naming a granter."""
    return select(
        PrincipalRow.id, PrincipalRow.display_name, PrincipalRow.primary_department
    ).where(
        PrincipalRow.id.in_(list(principal_ids)),
        PrincipalRow.deleted_at.is_(None),
        PrincipalRow.kind == PrincipalKind.HUMAN.value,
    )


def live_department_names(limit: int) -> Select[tuple[str, str]]:
    """Every live department's slug and name, in slug order."""
    return (
        select(DepartmentRow.slug, DepartmentRow.name)
        .where(DepartmentRow.deleted_at.is_(None))
        .order_by(DepartmentRow.slug)
        .limit(limit)
    )


def packs_of(principal_ids: Sequence[str]) -> Select[tuple[str, str, datetime | None]]:
    """The live assignments of live packs to these people: whose, which pack, until when."""
    return (
        select(
            CapabilityPackAssignmentRow.principal_id,
            CapabilityPackRow.name,
            CapabilityPackAssignmentRow.not_after,
        )
        .join(
            CapabilityPackRow,
            (CapabilityPackRow.id == CapabilityPackAssignmentRow.pack_id)
            & (CapabilityPackRow.deleted_at.is_(None)),
        )
        .where(
            CapabilityPackAssignmentRow.principal_id.in_(list(principal_ids)),
            CapabilityPackAssignmentRow.deleted_at.is_(None),
        )
        .order_by(CapabilityPackAssignmentRow.principal_id, CapabilityPackRow.name)
    )


def last_sessions(principal_ids: Sequence[str]) -> Select[tuple[str, datetime, int]]:
    """Each of these people's most recent session: whose, when it began, and how strongly.

    `DISTINCT ON` the person, newest first, so one row per person and never a count of them.
    """
    return (
        select(SessionRow.principal_id, SessionRow.started_at, SessionRow.assurance)
        .where(SessionRow.principal_id.in_(list(principal_ids)))
        .distinct(SessionRow.principal_id)
        .order_by(SessionRow.principal_id, SessionRow.started_at.desc())
    )


def grants_held(principal_id: str, limit: int) -> Select[tuple[CapabilityGrantRow]]:
    """One person's own live direct grants, by capability. A team's grants are the team's."""
    return (
        select(CapabilityGrantRow)
        .where(
            CapabilityGrantRow.principal_id == principal_id,
            CapabilityGrantRow.team_path.is_(None),
            CapabilityGrantRow.deleted_at.is_(None),
        )
        .order_by(CapabilityGrantRow.capability)
        .limit(limit)
    )


def assignments_held(
    principal_id: str, limit: int
) -> Select[tuple[CapabilityPackAssignmentRow, CapabilityPackRow]]:
    """One person's live assignments of live packs, by the pack's slug."""
    return (
        select(CapabilityPackAssignmentRow, CapabilityPackRow)
        .join(
            CapabilityPackRow,
            (CapabilityPackRow.id == CapabilityPackAssignmentRow.pack_id)
            & (CapabilityPackRow.deleted_at.is_(None)),
        )
        .where(
            CapabilityPackAssignmentRow.principal_id == principal_id,
            CapabilityPackAssignmentRow.deleted_at.is_(None),
        )
        .order_by(CapabilityPackRow.name)
        .limit(limit)
    )


def live_scopes(limit: int) -> Select[tuple[ScopeRow]]:
    """Every live scope, in slug order, for naming a holding's predicate."""
    return (
        select(ScopeRow).where(ScopeRow.deleted_at.is_(None)).order_by(ScopeRow.slug).limit(limit)
    )


def teams_of(principal_id: str, limit: int) -> Select[tuple[str, str, str]]:
    """One person's live places in live teams of live departments: department, team, its name."""
    return (
        select(DepartmentRow.slug, TeamRow.slug, TeamRow.name)
        .select_from(TeamMembershipRow)
        .join(TeamRow, TeamRow.id == TeamMembershipRow.team_id)
        .join(DepartmentRow, DepartmentRow.id == TeamRow.department_id)
        .where(
            TeamMembershipRow.principal_id == principal_id,
            TeamMembershipRow.ended_at.is_(None),
            TeamRow.deleted_at.is_(None),
            DepartmentRow.deleted_at.is_(None),
        )
        .order_by(DepartmentRow.slug, TeamRow.slug)
        .limit(limit)
    )


def leads_of(principal_id: str, limit: int) -> Select[tuple[str, str]]:
    """The live departments one person leads: slug and name."""
    return (
        select(DepartmentRow.slug, DepartmentRow.name)
        .select_from(DepartmentLeadRow)
        .join(DepartmentRow, DepartmentRow.id == DepartmentLeadRow.department_id)
        .where(
            DepartmentLeadRow.principal_id == principal_id,
            DepartmentLeadRow.ended_at.is_(None),
            DepartmentRow.deleted_at.is_(None),
        )
        .order_by(DepartmentRow.slug)
        .limit(limit)
    )


def adding_person(principal_id: str, body: PersonAdding) -> Insert:
    """The INSERT for one person added by hand. The instant is the database's `created_at`."""
    return (
        insert(PrincipalRow)
        .values(
            id=principal_id,
            kind=PrincipalKind.HUMAN.value,
            employment=body.employment.value,
            display_name=body.display_name,
            primary_department=body.department,
            not_after=body.not_after,
        )
        .returning(PrincipalRow.created_at)
    )


# ------------------------------------------------------------------ the loading


@dataclass(frozen=True)
class Loaded:
    """One person as the directory reads them, beside the facts it may carry about them."""

    member: Member
    employment: str
    department_name: str | None
    packs: tuple[str, ...]
    #: When the most recent session began and how strongly, or None.
    sign_in: tuple[datetime, int] | None
    #: Where the staff list says they stand and their employment type, or None when not named.
    standing: tuple[str, str | None] | None = None


def department_names(rows: Sequence[Any]) -> dict[str, str]:
    """Live departments' names by slug, from `live_department_names`' rows."""
    return {row[0]: row[1] for row in rows}


def is_live(not_after: datetime | None, now: datetime) -> bool:
    """Whether an assignment or a grant with this lapse still confers anything at `now`."""
    return not_after is None or not_after > now


def member_of(row: Any) -> Member:
    """A person row as `brain.console.organisation` asks about one."""
    pid, name, department, _employment, disabled_at = row
    return Member(
        principal_id=pid,
        display_name=name,
        department=department,
        disabled=disabled_at is not None,
    )


def person_view(one: Loaded) -> DirectoryPersonView:
    """One loaded person, copied field by field. The facts were decided before this."""
    member = one.member
    return DirectoryPersonView(
        principal_id=member.principal_id,
        display_name=member.display_name,
        department=member.department,
        department_name=one.department_name,
        employment=one.employment,
        standing="disabled" if member.disabled else "live",
        second_factor=None if one.sign_in is None else one.sign_in[1] >= Assurance.STRONG,
        last_signed_in_at=None if one.sign_in is None else one.sign_in[0],
        packs=list(one.packs),
        staff_status=None if one.standing is None else one.standing[0],
        employment_type=None if one.standing is None else one.standing[1],
    )


def the_list_read() -> str | None:
    """The staff source this install reads its people from, or None when it reads none."""
    try:
        named = value_of(STAFF_SOURCE_SETTING)
    except InstallError:
        return None
    chosen = {one.name: one for one in SELECTABLE}.get(named)
    return named if chosen is not None and chosen.reads_a_list else None


def standing_of(
    principal_ids: Sequence[str], source: str
) -> Select[tuple[str, str, str | None, datetime | None]]:
    """Where the list names these people: whose, their status, type and when they left.

    Joined through the roster's email binding, the one join between a person and their row.
    """
    return (
        select(
            PrincipalIdentityRow.principal_id,
            StaffMemberRow.status,
            StaffMemberRow.employment_type,
            StaffMemberRow.left_at,
        )
        .join(StaffMemberRow, StaffMemberRow.address_hash == PrincipalIdentityRow.identity_hash)
        .where(
            PrincipalIdentityRow.channel == Channel.EMAIL.value,
            PrincipalIdentityRow.deleted_at.is_(None),
            PrincipalIdentityRow.principal_id.in_(list(principal_ids)),
            StaffMemberRow.source == source,
        )
    )


def standings_by_person(rows: Sequence[Any]) -> dict[str, tuple[str, str | None]]:
    """Each person's status and type. A row the list marked left with no status of its own, which
    a row written before `0156` is, reads as left."""
    found: dict[str, tuple[str, str | None]] = {}
    for pid, status, kind, left_at in rows:
        shown = (
            EmploymentStatus.LEFT.value if left_at is not None and status == "active" else status
        )
        found[str(pid)] = (str(shown), None if kind is None else str(kind))
    return found


def kept_out_sentence(standing: tuple[str, str | None] | None) -> str | None:
    """What a person's page says about why the list keeps them out, or None."""
    if standing is None:
        return None
    try:
        why = kept_out_because(
            ListStanding(
                EmploymentStatus(standing[0]),
                None if standing[1] is None else EmploymentType(standing[1]),
            ),
            allowed_types(value_of(ACCOUNT_TYPES_SETTING)),
        )
    except (ValueError, InstallError):
        return None
    return None if why is None else WHY_KEPT_OUT[why]


def reads_a_staff_list(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> bool:
    """Whether this install reads its people from a staff list, which forbids adding by hand.

    The chosen source's own `reads_a_list`, so `none` is the one answer that reads nothing. A value
    no source carries, and a setting that cannot be read, count as reading one: adding by hand
    beside a list somebody named is the failure `A_PERSON_IS_ADDED_BY_HAND_ONLY_WHERE_NO_STAFF_LIST_
    IS_READ` exists to stop, and a name nobody recognises is still a name.
    """
    try:
        named = value_of(STAFF_SOURCE_SETTING, env, saved)
    except InstallError:
        return True
    chosen = {one.name: one for one in SELECTABLE}.get(named)
    return chosen is None or chosen.reads_a_list


def _console_reads(request: Request) -> ConsoleReads:
    """`app.state.console_reads`, or the primary, or one process fault for every caller."""
    found = getattr(request.app.state, "console_reads", None)
    if isinstance(found, ConsoleReads):
        return found
    return ConsoleReads(_sessions(request))


def _sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _no_person_here() -> Absent:
    """The one refusal a person's page makes. See
    `A_PERSON_PAGE_REFUSES_A_HIDDEN_PERSON_AS_IT_REFUSES_A_MISSING_ONE`."""
    return Absent("that person is not answerable for this caller")


def _not_answerable() -> Absent:
    """The refusal the directory makes. Names the screen and never a row or the caller."""
    return Absent(f"the {PEOPLE_SCREEN} screen is not answerable for this caller")


def _no_person_to_add() -> Absent:
    """The one refusal an addition makes to a caller who is told nothing more."""
    return Absent("no person is addable here by this caller")


def _said(message: str) -> Absent:
    """A refusal a caller holding the authority over the row may read, as `prompt_routes` says."""
    return Absent(message, public_message=f"Nothing was changed: {message}.")


# ------------------------------------------------------------------- the listing

#: What the directory may search, filter and order by: the fields a row shows.
DIRECTORY: Final[Listing[DirectoryPersonView]] = Listing(
    name="directory",
    columns=(
        Column("display_name", lambda row: row.display_name, search=True, sort=True),
        Column("principal_id", lambda row: row.principal_id, search=True),
        Column("department", lambda row: row.department, search=True, filter=True, sort=True),
        Column("department_name", lambda row: row.department_name, search=True),
        Column("standing", lambda row: row.standing, filter=True, sort=True),
        Column("second_factor", lambda row: row.second_factor, filter=True),
        Column("last_signed_in_at", lambda row: row.last_signed_in_at, sort=True),
        Column("packs", lambda row: tuple(row.packs), search=True, filter=True),
        Column("staff_status", lambda row: row.staff_status, filter=True, sort=True),
        Column("employment_type", lambda row: row.employment_type, filter=True, sort=True),
    ),
    key=lambda row: row.principal_id,
    order="display_name",
)
DirectoryQuery = Annotated[ListAsked, Depends(DIRECTORY.query())]


router = APIRouter(prefix=API_PREFIX, tags=["people"])


@router.get("/govern/directory", response_model=DirectoryPage, responses=COMMON_RESPONSES)
async def directory(request: Request, asked: Asked, listed: DirectoryQuery) -> DirectoryPage:
    """One page of every person this reader may be shown, disabled or not.

    The screen's question first and the database second, which is `brain.govern_routes`' order.
    Who is listed is `nameable`; what each row may carry about packs and sign-ins is asked of the
    Capabilities and Sessions screens, and only the people `nameable` kept are read about at all.
    """
    reach, now = asked.reach, asked.now
    if not permitted(screen(PEOPLE_SCREEN).read, reach, now):
        log.info("directory not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    plan = DIRECTORY.plan(listed, reader=asked.caller.principal.id)
    named = may_name_capabilities(reach, now)
    source = the_list_read()

    async def load(session: AsyncSession) -> tuple[list[Loaded], bool]:
        rows = (await session.execute(live_people(MAX_PEOPLE))).all()
        engaged = {row[0]: row[3] for row in rows}
        shown = nameable([member_of(row) for row in rows], reach, now)
        if not shown:
            return [], len(rows) >= MAX_PEOPLE
        names = department_names(
            (await session.execute(live_department_names(MAX_DEPARTMENTS))).all()
        )
        ids = [one.principal_id for one in shown]
        packs: dict[str, list[str]] = {}
        if named:
            for pid, pack, lapses in (await session.execute(packs_of(ids))).all():
                if is_live(lapses, now) and pack not in packs.setdefault(pid, []):
                    packs[pid].append(pack)
        told = [
            one.principal_id for one in shown if may_show_sign_in(placed(one).where, reach, now)
        ]
        signed: dict[str, tuple[datetime, int]] = {}
        if told:
            signed = {
                pid: (started, assurance)
                for pid, started, assurance in (await session.execute(last_sessions(told))).all()
            }
        standing: dict[str, tuple[str, str | None]] = {}
        if source is not None:
            standing = standings_by_person((await session.execute(standing_of(ids, source))).all())
        return [
            Loaded(
                member=one,
                employment=engaged[one.principal_id],
                department_name=None if one.department is None else names.get(one.department),
                packs=tuple(packs.get(one.principal_id, ())),
                sign_in=signed.get(one.principal_id),
                standing=standing.get(one.principal_id),
            )
            for one in shown
        ], len(rows) >= MAX_PEOPLE

    served = await _console_reads(request).read(load, now=now)
    loaded, full = served.value
    page = plan.page([person_view(one) for one in loaded])
    from_a_list = reads_a_staff_list()
    return DirectoryPage(
        items=list(page.items),
        next_cursor=page.next_cursor,
        truncated=full,
        editable=reach.scope_for(REACH_AUTHORITY, now) is not None,
        may_disable=reach.scope_for(GOVERNANCE_CONTROL, now) is not None,
        may_add=not from_a_list and reach.scope_for(ORGANISING_AUTHORITY, now) is not None,
        adding=PEOPLE_ARRIVE_FROM_THE_STAFF_SOURCE
        if from_a_list
        else ADDING_A_PERSON_GRANTS_NOTHING,
        account_ready=YOUR_ACCOUNT_IS_READY if from_a_list else None,
        may_move=departments_from() is DepartmentsFrom.CONSOLE
        and reach.scope_for(ORGANISING_AUTHORITY, now) is not None,
        staleness=served.banner,
    )


# ------------------------------------------------------------------ one person


@dataclass(frozen=True)
class LoadedPerson:
    """One person's page as read, before it is projected."""

    person: Loaded
    placements: PlacementView
    held: tuple[HeldView, ...]


def scope_named(
    stored: dict[str, Any], records: Sequence[ScopeRecord]
) -> tuple[str | None, str | None]:
    """The first shown scope whose predicate is exactly this holding's, as slug and label."""
    try:
        wanted = Scope.model_validate(stored)
    except ValueError:
        return None, None
    for one in records:
        if one.scope == wanted:
            return one.slug, one.label
    return None, None


def grant_held(
    row: CapabilityGrantRow, records: Sequence[ScopeRecord], names: Mapping[str, str]
) -> HeldView:
    slug, label = scope_named(row.scope, records)
    return HeldView(
        kind="grant",
        row_id=str(row.id),
        capabilities=[row.capability],
        scope=row.scope,
        scope_slug=slug,
        scope_label=label,
        granted_by=row.granted_by,
        granted_by_name=names.get(row.granted_by),
        reason=row.reason,
        granted_at=row.created_at,
        not_after=row.not_after,
    )


def pack_held(
    row: CapabilityPackAssignmentRow,
    pack: CapabilityPackRow,
    records: Sequence[ScopeRecord],
    names: Mapping[str, str],
) -> HeldView:
    slug, label = scope_named(row.scope, records)
    return HeldView(
        kind="pack",
        row_id=str(row.id),
        capabilities=list(pack.capabilities),
        pack=pack.name,
        pack_label=pack.description[:PACK_LABEL_CHARS],
        pack_version=pack.version,
        scope=row.scope,
        scope_slug=slug,
        scope_label=label,
        granted_by=row.granted_by,
        granted_by_name=names.get(row.granted_by),
        reason=row.reason,
        granted_at=row.created_at,
        not_after=row.not_after,
    )


def shown_scopes(rows: Sequence[ScopeRow], asked: Asked) -> tuple[ScopeRecord, ...]:
    """The live scopes this reader may be shown, by `scope_rows`. A row the type refuses is none."""
    records: list[ScopeRecord] = []
    for row in rows:
        try:
            records.append(
                ScopeRecord.from_predicate(
                    row.slug, row.predicate, is_department=row.is_department, label=row.label
                )
            )
        except (ValueError, PredicateRefusedError):
            log.warning("scope row does not construct", slug=row.slug)
    return scope_rows(records, asked.reach, asked.now)


PrincipalIdPath = Annotated[str, Path(min_length=1, max_length=PRINCIPAL_ID_CHARS)]


@router.get(
    "/govern/directory/{principal_id}", response_model=PersonDetail, responses=COMMON_RESPONSES
)
async def person_page(
    request: Request, principal_id: PrincipalIdPath, asked: Asked
) -> PersonDetail:
    """One person's page: who they are, where they sit, and what they hold.

    Refused in one way for every reason it can be refused; see
    `A_PERSON_PAGE_REFUSES_A_HIDDEN_PERSON_AS_IT_REFUSES_A_MISSING_ONE`. The People screen's read is
    asked before the database, and everything past the person's own row is read only once
    `nameable` has admitted them.
    """
    reach, now = asked.reach, asked.now
    if not permitted(screen(PEOPLE_SCREEN).read, reach, now):
        log.info("person not answerable", principal=asked.caller.principal.id)
        raise _no_person_here()
    named = may_name_capabilities(reach, now)
    source = the_list_read()

    async def load(session: AsyncSession) -> LoadedPerson | None:
        row = (await session.execute(one_person(principal_id))).one_or_none()
        if row is None:
            return None
        member = member_of(row)
        if not nameable([member], reach, now):
            return None
        departments = department_names(
            (await session.execute(live_department_names(MAX_DEPARTMENTS))).all()
        )
        offered = set(departments_offered(list(departments), reach, now))
        teams = [
            TeamPlace(department=department, slug=slug, name=name)
            for department, slug, name in (
                await session.execute(teams_of(member.principal_id, MAX_HELD))
            ).all()
            if department in offered
        ]
        leads = [
            NamedDepartment(slug=slug, name=name)
            for slug, name in (await session.execute(leads_of(member.principal_id, MAX_HELD))).all()
            if slug in offered
        ]
        home = member.department
        placements = PlacementView(
            department=NamedDepartment(slug=home, name=departments[home])
            if home is not None and home in departments and home in offered
            else None,
            teams=teams,
            leads=leads,
        )
        grants: list[CapabilityGrantRow] = []
        assignments: list[tuple[CapabilityPackAssignmentRow, CapabilityPackRow]] = []
        if named:
            grants = [
                one
                for one in (await session.execute(grants_held(member.principal_id, MAX_HELD)))
                .scalars()
                .all()
                if is_live(one.not_after, now)
            ]
            assignments = [
                (one, pack)
                for one, pack in (
                    await session.execute(assignments_held(member.principal_id, MAX_HELD))
                ).all()
                if is_live(one.not_after, now)
            ]
        held: tuple[HeldView, ...] = ()
        if grants or assignments:
            records = shown_scopes(
                (await session.execute(live_scopes(MAX_SCOPES))).scalars().all(), asked
            )
            granters = sorted(
                {one.granted_by for one in grants} | {one.granted_by for one, _ in assignments}
            )
            found = (await session.execute(people_named(granters))).all()
            names = {
                one.principal_id: one.display_name
                for one in nameable(
                    [
                        Member(principal_id=pid, display_name=name, department=dept, disabled=False)
                        for pid, name, dept in found
                    ],
                    reach,
                    now,
                )
            }
            held = (
                *(grant_held(one, records, names) for one in grants),
                *(pack_held(one, pack, records, names) for one, pack in assignments),
            )
        sign_in: tuple[datetime, int] | None = None
        if may_show_sign_in(placed(member).where, reach, now):
            last = (await session.execute(last_sessions([member.principal_id]))).all()
            sign_in = (last[0][1], last[0][2]) if last else None
        standing = (
            standings_by_person(
                (await session.execute(standing_of([member.principal_id], source))).all()
            ).get(member.principal_id)
            if source is not None
            else None
        )
        return LoadedPerson(
            person=Loaded(
                member=member,
                employment=row[3],
                department_name=None if home is None else departments.get(home),
                packs=tuple(dict.fromkeys(pack.name for _, pack in assignments)),
                sign_in=sign_in,
                standing=standing,
            ),
            placements=placements,
            held=held,
        )

    served = await _console_reads(request).read(load, now=now)
    found = served.value
    if found is None:
        log.info("person not answerable", principal=asked.caller.principal.id)
        raise _no_person_here()
    return PersonDetail(
        person=person_view(found.person),
        placements=found.placements,
        held=list(found.held),
        editable=reach.scope_for(REACH_AUTHORITY, now) is not None,
        may_disable=reach.scope_for(GOVERNANCE_CONTROL, now) is not None,
        may_organise=reach.scope_for(ORGANISING_AUTHORITY, now) is not None,
        staleness=served.banner,
        kept_out=kept_out_sentence(found.person.standing),
        department_set_on_people=departments_from() is DepartmentsFrom.CONSOLE,
    )


# -------------------------------------------------------------------- adding


@router.post(
    "/govern/directory", response_model=PersonAdded, responses=COMMON_RESPONSES, status_code=201
)
async def add_person(request: Request, body: PersonAdding, asked: Asked) -> PersonAdded:
    """Add a person by hand, on an install reading no staff list, where the caller governs.

    The authority is asked cheaply before anything, so a caller holding it nowhere learns nothing,
    not even whether a staff list is read. A holder is then told when one is, in a sentence. Then
    `may_add_person` about the row the person will sit in, before the database; then the
    department, which must be live, said only to a caller whose authority covers it, which is the
    caller who reached it. The insert is attributed so `0141`'s trigger records the caller.
    """
    reach, now = asked.reach, asked.now
    if reach.scope_for(ORGANISING_AUTHORITY, now) is None:
        log.info("person not addable", principal=asked.caller.principal.id)
        raise _no_person_to_add()
    if reads_a_staff_list():
        log.info("person not added beside a staff list", principal=asked.caller.principal.id)
        raise _said(PEOPLE_ARRIVE_FROM_THE_STAFF_SOURCE.rstrip("."))
    if not may_add_person(reach, department=body.department, now=now):
        log.info("person not addable there", principal=asked.caller.principal.id)
        raise _no_person_to_add()

    principal_id = new_principal_id()
    async with _sessions(request)() as session:
        if body.department is not None:
            live = (await session.execute(one_department(body.department))).first()
            if live is None:
                await session.rollback()
                raise _said(A_DEPARTMENT_NAMED_IS_NOT_LIVE)
        await attribute(session, asked)
        try:
            created = (await session.execute(adding_person(principal_id, body))).scalar_one()
        except IntegrityError:
            await session.rollback()
            log.info("person refused by a constraint", principal=asked.caller.principal.id)
            raise _no_person_to_add() from None
        await session.commit()
    return PersonAdded(
        principal_id=principal_id,
        display_name=body.display_name,
        department=body.department,
        created_at=created,
    )


# -------------------------------------------------------------------- moving (M1.6.20)


def _no_person_to_move() -> Absent:
    """The one refusal a move makes to a caller who is told nothing more."""
    return Absent("those people are not movable here by this caller")


@router.post(MOVING_PATH, response_model=DepartmentMoved, responses=COMMON_RESPONSES)
async def move_people(request: Request, body: DepartmentMoving, asked: Asked) -> DepartmentMoved:
    """Put several people in one department, on an install that manages departments on People.

    The authority anywhere first, so a caller holding it nowhere learns nothing, not even where
    departments come from; then the setting, said to a holder in a sentence; then the authority over
    the department they go to, before the database; then the department, which must be live, and
    every person, each of whom this reader must be able to name and to organise where they sit now
    and where they are going (`may_organise`). One refusal for any of them, and nobody moves; see
    `A_MOVE_IS_EVERYBODY_OR_NOBODY`. The update is attributed so `0170`'s trigger records each move
    under the caller.
    """
    reach, now = asked.reach, asked.now
    if reach.scope_for(ORGANISING_AUTHORITY, now) is None:
        log.info("people not movable", principal=asked.caller.principal.id)
        raise _no_person_to_move()
    if departments_from() is not DepartmentsFrom.CONSOLE:
        raise _said(DEPARTMENTS_COME_FROM_THE_STAFF_LIST)
    if not may_add_person(reach, department=body.department, now=now):
        log.info("people not movable there", principal=asked.caller.principal.id)
        raise _no_person_to_move()
    wanted = sorted(set(body.principal_ids))
    async with _sessions(request)() as session:
        if (await session.execute(one_department(body.department))).first() is None:
            await session.rollback()
            raise _said(A_DEPARTMENT_NAMED_IS_NOT_LIVE)
        members = [member_of(row) for row in (await session.execute(people_by_id(wanted))).all()]
        shown = {one.principal_id for one in nameable(members, reach, now)}
        if [one.principal_id for one in members] != wanted or not all(
            one.principal_id in shown
            and may_organise(reach, department=body.department, person=one, now=now)
            for one in members
        ):
            await session.rollback()
            log.info("people not movable", principal=asked.caller.principal.id)
            raise _no_person_to_move()
        moving = [one.principal_id for one in members if one.department != body.department]
        if moving:
            await attribute(session, asked)
            await session.execute(moving_people(moving, body.department))
        await session.commit()
    log.info(
        "people moved", principal=asked.caller.principal.id, moved=len(moving), to=body.department
    )
    return DepartmentMoved(
        department=body.department,
        moved=moving,
        told=(
            f"Moved {len(moving)} {'person' if len(moving) == 1 else 'people'}. Their access has "
            "not changed: what they may see is still only what their grants say."
        ),
    )
