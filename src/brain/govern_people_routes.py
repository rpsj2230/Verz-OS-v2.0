"""Four Govern screens over HTTP: departments and teams, elevation, access review and subscribers.

Each of the four had its decision written and nothing a browser could reach. `brain.ops.
console_screens` listed `brain.console.elevation` and `brain.console.subscribers` among the reads
with no screen; `brain.console.govern.recertifiable` and `certify` had one route, a removal, and no
way to record that a grant was kept; and the membership half of the organisation was declined in
`brain.govern_routes` pending the argument `brain.console.organisation` now makes. This module
serves all four beside People in the Govern group.

**Nothing here decides who may see or change anything.** Whether a screen opens is
`brain.console.reads.permitted` over its registered read, or for subscribers
`brain.ops.outbox.may_manage` through `brain.console.subscribers`; which rows each shows is
`brain.console.organisation.organisation`, `govern.recertifiable` and
`subscribers.subscriber_lines`;
whether a review decision may be recorded is `govern.certify`, asked under the row's lock by
`brain.gate.review_store.StoredReview.decide`; and what the break-glass landing says is
`brain.console.elevation.landing`. A route that filtered a row itself would be a second answer to a
question one of those answers, and the second answer is the one nobody keeps in step.

**Each screen's question is asked before any store is reached for.** Straight from
`brain.govern_routes`: a caller holding no authority is refused identically on a process with a
database and on one without, so nobody reads this deployment's state off the difference.

**Recording a review decision is proved to reach the system, in three places.** The row: a
`gate.review_decision` row naming the decider, and for a removal the grant row or the pack
assignment retired, in one transaction. The ledger: `0052`'s trigger appends `certification`, and a
removal also gets the `revoke` entry `0003`'s trigger has always written, both carrying the
reviewer's reach digest and the request. The behaviour: a removed grant is no longer in what the
resolver returns for its holder, and a kept one is listed as decided, by whom and when. The database
half is `tests/unit/test_review_store.py`, which skips without a server and runs in CI.

**Placing somebody in a team and appointing a lead are confirmed writes, proved to reach the system
in three places.** The row: `gate.team_membership` or `gate.department_lead`, naming who did it,
with an appointment ending the current lead in the same transaction. The ledger: `0062`'s triggers
append `organisation` entries on the insert and on the ending, under the person's own subject. The
behaviour: the Departments and teams page lists the person under the team, or as the lead, for a
reader who may name them and for nobody else. `brain.identity.organisation_store` holds the SQL and
`brain.console.organisation` the two questions, `may_place` and `may_appoint`, asked under the
transaction about the rows as they stand. `tests/unit/test_organisation_store.py` is the database
half.

**An elevation request is filed, approved or denied, and an approval is a grant with a lapse.** The
request is a `gate.elevation_request` row by the caller for themselves; a decision is somebody
else's, asked through `brain.console.elevation.may_approve` or `may_decide` inside
`brain.gate.elevation_store`'s transaction with the requester's reach as the resolver answers it
then. An approval writes a `gate.capability_grant` row whose `not_after` ends the window, so the
requester resolves to more at once and to no more after the lapse, with nothing on this module's
side ending it. The listing is `requests_shown`: a requester's own and those the reader may decide.
`tests/unit/test_elevation_store.py` is the database half, and it asks the resolver on both sides of
the lapse.

**One of the four still says more about what is missing than about what is there, and that is the
design rather than an apology.** The Subscribers screen lists who is told what and says
how that stops, pointing at the two screens that stop it rather than offering a second button for
the same write: a subscriber is switched off on the Webhooks screen, which the audit ledger records
under its `webhook` action, and a notice to people on the Notifications and email screen. Its
sentences travel on the response, for `brain.skill_routes`' reason: the day a fact changes, the
sentence changes in the same commit, which is what happened to the Elevation screen's.

**No count of anything, anywhere.** Every listing is filtered per caller, and `truncated` says a
load came back full, computed against what was loaded rather than what survived.

**The three long lists page, search, filter and order through `brain.listing`.** Departments, the
elevation requests and the access review each load `MAX_ROWS` whatever was asked, decide, project,
and hand the projected rows to their listing. The people nobody has placed are answered with the
first page of departments and narrowed by the same search, because they are the organisation's
remainder rather than a list of their own: see `THE_UNPLACED_ARRIVE_WITH_THE_FIRST_PAGE`.

**Several review decisions are several decisions.** `POST /govern/access-review/decisions` records
one decision over up to `brain.listing.MAX_SEVERAL` holdings, and each holding goes through the
single decision's store call, its lock, its `may` and its trigger, with its own outcome answered in
the order asked. Elevations are not decided in bulk. See
`AN_ELEVATION_IS_DECIDED_ON_ITS_OWN_REASON`.

Task ids: M27.7.4, M27.7.8, M27.7.9, M27.7.12, M27.8.6, M1.2.3
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any, Final, Literal, Self

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.console.elevation import (
    ELEVATION_CONTROL,
    ElevationRequest,
    ElevationState,
    landing,
    may_approve,
    may_decide,
    requester_prompt,
    requests_shown,
    state_of,
    would_widen,
)
from brain.console.global_surfaces import GOVERNANCE_CONTROL
from brain.console.govern import Decision, GovernError, Placed, certify, recertifiable
from brain.console.organisation import (
    A_DEPARTMENTS_OWN_SCOPE_GOES_WITH_ITS_DEPARTMENT,
    A_RETIRED_DEPARTMENT_IS_NAMED_BY_NO_LIVE_SCOPE,
    A_RETIRED_DEPARTMENT_LEAVES_EVERY_GRANT_ALREADY_WRITTEN_IN_FORCE,
    A_RETIRED_SCOPE_TAKES_NO_GRANT_AWAY,
    A_RETIRED_TEAM_CHANGES_NOBODYS_ACCESS,
    COMPANY_ID,
    DEPARTMENTS_SCREEN,
    ORGANISING_AUTHORITY,
    SCOPE_AUTHORITY,
    THE_COMPANY_WIDE_SCOPE_IS_NEVER_RETIRED,
    Department,
    Lead,
    Member,
    Membership,
    Organisation,
    Team,
    drawn,
    founded,
    may_appoint,
    may_draw_scope,
    may_found_or_retire_departments,
    may_know_taken_scope,
    may_organise,
    may_place,
    may_shape_department,
    organisation,
    retired_with,
    scope_retirement,
)
from brain.console.read_replica import StalenessBanner
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.subscribers import findings, subscriber_lines
from brain.core.department import SLUG_PATTERN, ScopeRecord
from brain.core.entitlement import CAPABILITY_RE, Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.core.scope import Scope
from brain.core.scope_sql import PredicateRefusedError
from brain.gate.elevation_store import (
    ElevationRecords,
    PendingRequest,
    StoredElevations,
    StoredRequest,
)
from brain.gate.review_store import (
    Decided,
    GrantHolding,
    Holding,
    LastDecision,
    PackHolding,
    StoredReview,
    held_by,
)
from brain.govern_routes import placed_assignment, placed_grant
from brain.identity.organisation_store import (
    Attribution,
    OrganisationRecords,
    Person,
    StoredOrganisation,
    Structured,
    StructureRecords,
    StructureRefusal,
    live_leads,
    live_memberships,
)
from brain.identity.packs import SubjectGrant
from brain.identity.principal_state_store import A_DISABLE_IS_REVERSIBLE_AND_A_LEAVER_IS_NOT
from brain.identity.roles import BREAK_GLASS_MAX, BreakGlassReason, IdentityError
from brain.identity.teams import PrincipalSubject
from brain.identity.teams import Team as TeamRecord
from brain.listing import MAX_SEVERAL, Column, ListAsked, Listing, each_of
from brain.ops.outbox import EventKind, Subscriber, may_manage
from brain.ops.outbox_store import last_delivered, subscribers
from brain.ops.replica_store import ConsoleReads, Served
from brain.routing_routes import sessions_of
from brain.tables.elevation import (
    EXPLANATION_CHARS,
    LONGEST_HOURS,
    ElevationDecision,
)
from brain.tables.gate import LABEL_CHARS, SLUG_CHARS, DepartmentRow, TeamRow
from brain.tables.identity import PrincipalRow
from brain.tables.review import ReviewDecision

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: What the organisation screen says about its teams and leads, served beside it.
A_TEAM_LISTS_WHO_YOU_MAY_SEE_IN_IT: Final = (
    "A team lists the people in it you may see. Placing somebody in a team, or taking them out, "
    "changes nobody's access: a team is where somebody sits, and what they may see is still only "
    "what their grants say."
)
A_LEAD_CONFERS_NOTHING: Final = (
    "A department's lead is who leads it, recorded with who appointed them. Appointing a lead "
    "gives them no access; whoever may review a department's access holds that authority as a "
    "grant, which the People and grants screen shows. Nobody may appoint themselves."
)
NOTHING_HERE_IS_COUNTED: Final = (
    "No headcount is shown. Every list here is narrowed to what you may see, so a number beside "
    "it would say how much you were not shown."
)
ORGANISING_IS_THE_GRANT_AUTHORITY: Final = (
    "Placing somebody or appointing a lead takes the authority the Access review screen asks for, "
    "held over the department and over the department the person sits in."
)

#: What the structure's controls take, served beside the page.
SHAPING_IS_ITS_OWN_AUTHORITY: Final = (
    "Creating or retiring a department takes the authority over departments and over scopes, held "
    "over the whole company. Renaming a department, and creating, renaming or retiring its teams, "
    "takes the authority over departments held over that department. Creating or retiring a scope "
    "takes the authority over scopes held over everything the scope reaches."
)

#: The readable refusals of a change to the structure, said only to a caller holding the authority.
A_DEPARTMENT_NAME_IS_TAKEN: Final = (
    "that short name is already used by a live department or a live scope, so choose another; a "
    "retired department's short name can be used again"
)
A_TEAM_NAME_IS_TAKEN: Final = "that short name is already used by a live team in this department"
A_SCOPE_NAME_IS_TAKEN: Final = "that short name is already used by a live scope, so choose another"
IT_CHANGED_SINCE_YOU_OPENED_IT: Final = (
    "somebody changed it after this page was opened, so nothing was written; reload the page to "
    "see it as it is now"
)
A_SCOPE_NAMES_NO_LIVE_DEPARTMENT: Final = (
    "a department the scope names is not a live department on this install"
)

#: What an elevation is, served on the Elevation screen.
AN_ELEVATION_IS_A_GRANT_WITH_A_CLOCK_ON_IT: Final = (
    "An elevation is one capability, at a named scope, for one person, for a reason from a fixed "
    "list and a few hours at most, approved by somebody other than that person. It is added to "
    "what they already hold, and it lapses on its own at the end of the hours asked, with nobody "
    "needing to end it."
)
WHAT_IS_RECORDED_ABOUT_AN_ELEVATION: Final = (
    "Every request is kept with who asked, for what and why, who approved or denied it and when, "
    "and when an approved one lapses. Asking, approving and denying are each recorded in the audit "
    "ledger, and an approval is recorded again as the grant it wrote."
)
NOBODY_IS_TOLD_YET: Final = (
    "Nobody is sent a notice when somebody asks or is approved. The people who should be told are "
    "the standing Super Admins, and this install does not record who holds a role, so the audit "
    "ledger is the record."
)
AUTHORISING_IS_THE_ACCESS_REVIEW_AUTHORITY: Final = (
    "Approving or denying an elevation takes the same authority the Access review screen asks for, "
    "held over the department the person sits in, and approving it also takes the capability "
    "itself, held over the scope named."
)

#: What a review decision does, served on the Access review screen.
KEEPING_A_GRANT_RECORDS_THE_DECISION: Final = (
    "Keeping a grant records that you reviewed it and it stands. Nothing about what the person "
    "may do changes, and the decision is kept with your name and the time."
)
REMOVING_A_GRANT_TAKES_IT_AWAY: Final = (
    "Removing a grant takes it away from the next request the person makes, and records that you "
    "decided it. A grant from a pack is removed with the whole pack, because a pack's "
    "capabilities are granted together."
)
WHAT_A_REVIEW_SHOWS: Final = (
    "Only grants you could have written are listed: your review authority and the capability "
    "itself, both over the department the person sits in and the scope the grant carries. "
    "Nobody may decide a grant of their own."
)

#: Why the people nobody has placed are not a paged list of their own.
THE_UNPLACED_ARRIVE_WITH_THE_FIRST_PAGE: Final = (
    "The people whose row names no registered department are the organisation's remainder, not a "
    "list an administrator walks. They are answered once, beside the first page of departments, "
    "narrowed by the same search and in name order, and never again on a later page, so walking "
    "the departments does not repeat them."
)

#: Why elevation requests are listed, searched and ordered and never decided several at once.
AN_ELEVATION_IS_DECIDED_ON_ITS_OWN_REASON: Final = (
    "Approving an elevation widens one person's reach for hours on the strength of the reason "
    "and explanation they wrote, and the authority to approve it is asked against that request. "
    "Approving several at once is approving explanations nobody read, so each is decided from its "
    "own row."
)

#: What the subscribers screen cannot do, served beside it.
HOW_TO_STOP_BEING_TOLD: Final = (
    "A subscriber is switched off on the Webhooks screen, which records who switched it off in "
    "the audit ledger and sends nothing more to it, including deliveries already waiting. A "
    "subscriber switched off is never switched back on: it is registered again under a new id. "
    "A notice to people is switched off on the Notifications and email screen, except a notice "
    "that exists to report misuse or a mechanism that stopped running, which has no switch."
)
ONLY_WEBHOOK_SUBSCRIBERS_ARE_LISTED: Final = (
    "Only webhook subscribers are listed here. Every notice this install composes for people, "
    "who each is told to, how, and whether anything sends it yet, is on the Notifications and "
    "email screen."
)
A_SUBSCRIBER_IS_TOLD_IDENTIFIERS: Final = (
    "A subscriber is told that something happened and the identifiers of what it happened to, "
    "never the content."
)

# ----------------------------------------------------------------- the screens

#: The registered screen whose read opens the review and decides whether a decision may be
#: offered at all. A key rather than a capability, so it cannot drift from the registry.
ACCESS_REVIEW_SCREEN: Final = "access_review"

#: The most rows one listing loads, whatever page, search, filter or order was asked for. A
#: resource bound and not a permission one. See
#: `brain.listing.THE_LOAD_IS_NEVER_NARROWED_BY_THE_QUERY`.
MAX_ROWS: Final = 1000


# ------------------------------------------------------------------- the shapes


class MemberView(BaseModel):
    """One person on the organisation screen. No role, no grant count, no figure of any kind."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    display_name: str
    disabled: bool


class UnplacedView(MemberView):
    """One person not under a registered department, and the department value their row names."""

    department: str | None


class TeamView(BaseModel):
    """One team, and the people in it this reader may be shown. No figure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    name: str
    members: list[MemberView] = Field(default_factory=list)


class DepartmentView(BaseModel):
    """One offered department, its teams, its lead and the people in it this reader may be shown."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    name: str
    teams: list[TeamView]
    members: list[MemberView]
    #: Null when none is recorded and when this reader may not name the one who is.
    lead: MemberView | None = None
    #: Whether this reader holds the authority to rename it and change its teams. Presentation
    #: only: the writes ask `may_shape_department` whatever this said.
    shapeable: bool = False


class OrganisationPage(BaseModel):
    """The organisation, and the sentences about what it shows and who may change it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[DepartmentView]
    #: Present exactly when a further department this reader may see matches.
    next_cursor: str | None = None
    #: Empty on every page but the first. See `THE_UNPLACED_ARRIVE_WITH_THE_FIRST_PAGE`.
    unplaced: list[UnplacedView]
    #: A load came back full. Never how much more there is.
    truncated: bool
    #: Whether this reader holds the authority to place anybody anywhere. Presentation only: the
    #: writes ask `may_place` and `may_appoint` about the rows, whatever this said.
    may_organise: bool = False
    #: Whether this reader may create and retire departments. Presentation only.
    may_found: bool = False
    #: Whether this reader holds the authority over scopes anywhere. Presentation only.
    may_draw_scopes: bool = False
    #: Whether this reader holds the grant decision anywhere, so may disable or enable somebody.
    #: Presentation only: `brain.principal_state_routes` asks `may_disable` about the row.
    may_disable: bool = False
    #: What disabling somebody does and does not do, for its confirmation.
    disabling: str = A_DISABLE_IS_REVERSIBLE_AND_A_LEAVER_IS_NOT
    staleness: StalenessBanner | None = None
    teams: str = A_TEAM_LISTS_WHO_YOU_MAY_SEE_IN_IT
    leads: str = A_LEAD_CONFERS_NOTHING
    counted: str = NOTHING_HERE_IS_COUNTED
    organising: str = ORGANISING_IS_THE_GRANT_AUTHORITY
    shaping: str = SHAPING_IS_ITS_OWN_AUTHORITY
    #: What retiring a department does to scopes and to grants, for its confirmation.
    retiring_department: str = (
        f"{A_RETIRED_DEPARTMENT_IS_NAMED_BY_NO_LIVE_SCOPE} "
        f"{A_RETIRED_DEPARTMENT_LEAVES_EVERY_GRANT_ALREADY_WRITTEN_IN_FORCE}"
    )
    retiring_team: str = A_RETIRED_TEAM_CHANGES_NOBODYS_ACCESS
    retiring_scope: str = A_RETIRED_SCOPE_TAKES_NO_GRANT_AWAY


class MembershipChange(BaseModel):
    """Which team, whose, and in or out. Nothing that could say who did it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str = Field(min_length=2, max_length=60)
    team: str = Field(min_length=2, max_length=60)
    principal_id: str = Field(min_length=1, max_length=128)
    change: Literal["join", "leave"]


class LeadChange(BaseModel):
    """Which department, and whom to appoint, or that its lead stands down.

    An appointment names somebody and a standing down names nobody, because it is the current
    lead who stands down; a body naming a person to stand down could name the wrong one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str = Field(min_length=2, max_length=60)
    change: Literal["appoint", "stand_down"]
    principal_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def _names_somebody_exactly_when_appointing(self) -> Self:
        if (self.change == "appoint") != (self.principal_id is not None):
            msg = "an appointment names the person appointed and a standing down names nobody"
            raise ValueError(msg)
        return self


class OrganisationChanged(BaseModel):
    """What a placement or a lead change recorded, and the database's instant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: str
    team: str | None
    principal_id: str | None
    change: str
    at: datetime


#: A short name, as `brain.core.department` and `gate.scope`, `gate.department` and `gate.team`
#: hold one. Checked here so a malformed one is a 422 naming the field.
Slug = Annotated[str, Field(min_length=2, max_length=SLUG_CHARS, pattern=SLUG_PATTERN)]

#: A name a person reads, trimmed, as the tables' `name_present` checks require.
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=LABEL_CHARS)
]

#: The name a page showed, compared exactly, so it is not trimmed.
Shown = Annotated[str, Field(min_length=1, max_length=LABEL_CHARS)]

#: The most departments one scope may name. A bound on a form, not a permission.
MOST_DEPARTMENTS_IN_A_SCOPE: Final = 50


class DepartmentFounding(BaseModel):
    """A new department: its short name and its name. Its scope is drawn from the short name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: Slug
    name: Name

    @model_validator(mode="after")
    def _the_types_accept_it(self) -> Self:
        founded(self.slug, self.name)
        return self


class DepartmentRenaming(BaseModel):
    """Which department, the name the page showed, and its new name. Never its short name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: Slug
    expected_name: Shown
    name: Name

    @model_validator(mode="after")
    def _names_something_new(self) -> Self:
        if self.name == self.expected_name:
            msg = "the new name is the name it already has"
            raise ValueError(msg)
        return self


class DepartmentRetirement(BaseModel):
    """Which department, and the name the confirmation showed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: Slug
    expected_name: Shown


class TeamAdding(BaseModel):
    """A new team in a department: its short name and its name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: Slug
    slug: Slug
    name: Name

    @model_validator(mode="after")
    def _the_type_accepts_it(self) -> Self:
        team_record(self.department, self.slug, self.name)
        return self


class TeamRenaming(BaseModel):
    """Which team of which department, the name the page showed, and its new name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: Slug
    slug: Slug
    expected_name: Shown
    name: Name

    @model_validator(mode="after")
    def _names_something_new(self) -> Self:
        if self.name == self.expected_name:
            msg = "the new name is the name it already has"
            raise ValueError(msg)
        return self


class TeamRetirement(BaseModel):
    """Which team of which department, and the name the confirmation showed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    department: Slug
    slug: Slug
    expected_name: Shown


class ScopeDrawing(BaseModel):
    """A new scope over one department or a named set of them. Never a clause typed in a form."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: Slug
    label: Name
    departments: list[Slug] = Field(min_length=1, max_length=MOST_DEPARTMENTS_IN_A_SCOPE)
    #: A team of the one department named, so the scope references that team (M1.5.2).
    team: Slug | None = None

    @model_validator(mode="after")
    def _the_types_accept_it(self) -> Self:
        if len(set(self.departments)) != len(self.departments):
            msg = "a department is named twice"
            raise ValueError(msg)
        drawn(self.slug, self.label, self.departments, self.team)
        return self


class ScopeRetirement(BaseModel):
    """Which scope, and the predicate the page showed, as `ScopeView.scope` carries it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: Slug
    expected_scope: dict[str, Any]

    @model_validator(mode="after")
    def _is_a_scope(self) -> Self:
        Scope.model_validate(self.expected_scope)
        return self


class StructureChanged(BaseModel):
    """What a change to a department, a team or a scope recorded, and the database's instant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["department", "team", "scope"]
    #: The department a team belongs to, and null for a department or a scope.
    department: str | None
    slug: str
    change: Literal["created", "renamed", "retired"]
    at: datetime


def team_record(department: str, slug: str, name: str) -> TeamRecord:
    """A team as `brain.identity.teams.Team` reads one, or `ValueError` naming what it refused."""
    try:
        return TeamRecord(company_id=COMPANY_ID, department_slug=department, slug=slug, name=name)
    except IdentityError as refused:
        raise ValueError(str(refused)) from None


class ElevationRequestView(BaseModel):
    """One request this reader is shown: who asked, for what and why, and where it stands."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    principal_id: str
    display_name: str | None
    department: str | None
    capability: str
    scope_slug: str
    reason: str
    explanation: str
    hours: int
    requested_at: datetime
    state: ElevationState
    decided_by: str | None
    decided_at: datetime | None
    lapses_at: datetime | None
    #: Whether this reader may decide it now. Presentation only: the decision asks again.
    decidable: bool


class ElevationPage(BaseModel):
    """The request screen for this reader: their standing, the requests they are shown, the rules.

    Nothing here lists what an elevation could confer:
    `A_LANDING_THAT_LISTS_WHAT_YOU_COULD_ELEVATE_TO_IS_THE_CATALOGUE`. A requester types the
    capability they need.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str
    holds_nothing_standing: bool
    #: Whether this reader holds the authority to decide one anywhere. Presentation only.
    may_authorise: bool
    #: The closed list of reasons an elevation may be asked for. The product's, not the company's.
    reasons: list[str]
    #: The longest an elevation may run, in hours.
    longest_hours: int
    items: list[ElevationRequestView] = Field(default_factory=list)
    #: Present exactly when a further request this reader may see matches.
    next_cursor: str | None = None
    #: A load came back full. Never how much more there is.
    truncated: bool = False
    what: str = AN_ELEVATION_IS_A_GRANT_WITH_A_CLOCK_ON_IT
    recorded: str = WHAT_IS_RECORDED_ABOUT_AN_ELEVATION
    notified: str = NOBODY_IS_TOLD_YET
    authorising: str = AUTHORISING_IS_THE_ACCESS_REVIEW_AUTHORITY


class ElevationAsked(BaseModel):
    """What somebody asks for, for themselves. Nothing that could say who, or decide it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: str = Field(pattern=CAPABILITY_RE.pattern, max_length=200)
    scope_slug: str = Field(min_length=2, max_length=60)
    reason: BreakGlassReason
    explanation: str = Field(min_length=1, max_length=EXPLANATION_CHARS)
    hours: int = Field(ge=1, le=LONGEST_HOURS)


class ElevationFiled(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    requested_at: datetime


class ElevationDecisionAsked(BaseModel):
    """Approved or denied. Nothing that could say who, and no third word."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ElevationDecision


class ElevationDecided(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    principal_id: str
    decision: ElevationDecision
    decided_at: datetime
    lapses_at: datetime | None


class HoldingKind(enum.StrEnum):
    """Which table a reviewed holding is a row of."""

    GRANT = "grant"
    PACK = "pack"


class ReviewRowView(BaseModel):
    """One holding this reviewer may decide, and the last decision about it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: HoldingKind
    row_id: str
    principal_id: str
    display_name: str | None
    department: str | None
    #: The one capability of a direct grant, or every capability the pack carries.
    capabilities: list[str]
    pack: str | None
    scope: dict[str, Any]
    granted_by: str
    reason: str
    granted_at: datetime
    lapses_at: datetime | None
    last_decision: ReviewDecision | None
    last_decided_by: str | None
    last_decided_at: datetime | None


class ReviewPage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[ReviewRowView]
    #: Present exactly when a further holding this reviewer may decide matches.
    next_cursor: str | None = None
    truncated: bool
    shows: str = WHAT_A_REVIEW_SHOWS
    keeping: str = KEEPING_A_GRANT_RECORDS_THE_DECISION
    removing: str = REMOVING_A_GRANT_TAKES_IT_AWAY


class ReviewDecisionAsked(BaseModel):
    """Which holding, which table, and what was decided. Nothing that could say who."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: HoldingKind
    row_id: uuid.UUID
    decision: Decision


class ReviewDecided(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: HoldingKind
    row_id: str
    principal_id: str
    decision: ReviewDecision
    decided_at: datetime


class HoldingNamed(BaseModel):
    """One holding in a bulk decision: which table, and which row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: HoldingKind
    row_id: uuid.UUID


class ReviewDecisionsAsked(BaseModel):
    """One decision over several holdings. Nothing that could say who."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Decision
    holdings: list[HoldingNamed] = Field(min_length=1, max_length=MAX_SEVERAL)


class ReviewOutcome(BaseModel):
    """What came of one holding named in a bulk decision.

    `decided` false carries nothing else, identically for a holding out of reach, the reviewer's
    own, the wrong kind and one that does not exist: the single decision's one refusal, per row.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: HoldingKind
    row_id: str
    decided: bool
    principal_id: str | None = None
    decided_at: datetime | None = None


class ReviewDecisionsDecided(BaseModel):
    """Each holding named, in the order asked, with its own outcome."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ReviewDecision
    outcomes: list[ReviewOutcome]


class SubscriberView(BaseModel):
    """One subscriber, as `brain.console.subscribers.SubscriberLine` carries it. No vault path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subscriber_id: str
    endpoint: str
    kinds: list[str]
    active: bool
    created_by: str
    last_delivered_at: datetime | None


class SubscribersPage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[SubscriberView]
    findings: list[str]
    #: Every kind of event there is to be told about. The product's closed vocabulary.
    kinds: list[str]
    staleness: StalenessBanner | None = None
    stopping: str = HOW_TO_STOP_BEING_TOLD
    scope: str = ONLY_WEBHOOK_SUBSCRIBERS_ARE_LISTED
    told: str = A_SUBSCRIBER_IS_TOLD_IDENTIFIERS


# ---------------------------------------------------------------- the statements


def live_departments(limit: int) -> Select[tuple[str, str]]:
    """Every live department's slug and name, in slug order."""
    return (
        select(DepartmentRow.slug, DepartmentRow.name)
        .where(DepartmentRow.deleted_at.is_(None))
        .order_by(DepartmentRow.slug)
        .limit(limit)
    )


def live_teams(limit: int) -> Select[tuple[str, str, str]]:
    """Every live team of a live department: the department's slug, the team's slug and name."""
    return (
        select(DepartmentRow.slug, TeamRow.slug, TeamRow.name)
        .join(
            DepartmentRow,
            (DepartmentRow.id == TeamRow.department_id) & (DepartmentRow.deleted_at.is_(None)),
        )
        .where(TeamRow.deleted_at.is_(None))
        .order_by(DepartmentRow.slug, TeamRow.slug)
        .limit(limit)
    )


def live_people(limit: int) -> Select[tuple[str, str, str | None, datetime | None]]:
    """Every principal not retired, disabled or not, with the department their row names."""
    return (
        select(
            PrincipalRow.id,
            PrincipalRow.display_name,
            PrincipalRow.primary_department,
            PrincipalRow.disabled_at,
        )
        .where(PrincipalRow.deleted_at.is_(None))
        .order_by(PrincipalRow.display_name, PrincipalRow.id)
        .limit(limit)
    )


# ------------------------------------------------------------------- the sources


@dataclass(frozen=True)
class LoadedOrganisation:
    departments: tuple[Department, ...]
    teams: tuple[Team, ...]
    members: tuple[Member, ...]
    full: bool
    memberships: tuple[Membership, ...] = ()
    leads: tuple[Lead, ...] = ()


@dataclass(frozen=True)
class OrganisationSource:
    """The departments, teams, people, memberships and leads, read for display. Decides nothing."""

    reads: ConsoleReads

    async def load(self, *, limit: int, now: datetime) -> Served[LoadedOrganisation]:
        async def work(session: AsyncSession) -> LoadedOrganisation:
            departments = (await session.execute(live_departments(limit))).all()
            teams = (await session.execute(live_teams(limit))).all()
            people = (await session.execute(live_people(limit))).all()
            memberships = (await session.execute(live_memberships(limit))).all()
            leads = (await session.execute(live_leads(limit))).all()
            return LoadedOrganisation(
                departments=tuple(Department(slug=slug, name=name) for slug, name in departments),
                teams=tuple(
                    Team(department=department, slug=slug, name=name)
                    for department, slug, name in teams
                ),
                members=tuple(
                    Member(
                        principal_id=pid,
                        display_name=name,
                        department=department,
                        disabled=disabled_at is not None,
                    )
                    for pid, name, department, disabled_at in people
                ),
                memberships=tuple(
                    Membership(department=department, team=team, principal_id=pid)
                    for department, team, pid in memberships
                ),
                leads=tuple(
                    Lead(department=department, principal_id=pid) for department, pid in leads
                ),
                full=max(len(departments), len(teams), len(people), len(memberships), len(leads))
                >= limit,
            )

        return await self.reads.read(work, now=now)


@dataclass(frozen=True)
class SubscriberSource:
    """`ops.webhook_subscriber` and its deliveries, read for display. Decides nothing."""

    reads: ConsoleReads

    async def load(
        self, *, now: datetime
    ) -> Served[tuple[tuple[Subscriber, ...], dict[str, datetime]]]:
        async def work(
            session: AsyncSession,
        ) -> tuple[tuple[Subscriber, ...], dict[str, datetime]]:
            return await subscribers(session), await last_delivered(session)

        return await self.reads.read(work, now=now)


def _console_reads(request: Request) -> ConsoleReads:
    """`app.state.console_reads`, or the primary, or one process fault for every caller."""
    found = getattr(request.app.state, "console_reads", None)
    if isinstance(found, ConsoleReads):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return ConsoleReads(factory)


def organisation_source_of(request: Request) -> OrganisationSource:
    found = getattr(request.app.state, "organisation_source", None)
    if isinstance(found, OrganisationSource):
        return found
    return OrganisationSource(_console_reads(request))


def subscriber_source_of(request: Request) -> SubscriberSource:
    found = getattr(request.app.state, "subscriber_source", None)
    if isinstance(found, SubscriberSource):
        return found
    return SubscriberSource(_console_reads(request))


def organisation_records_of(request: Request) -> OrganisationRecords:
    """`app.state.organisation_records` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "organisation_records", None)
    if isinstance(found, OrganisationRecords):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredOrganisation(factory)


def structure_records_of(request: Request) -> StructureRecords:
    """`app.state.structure_records` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "structure_records", None)
    if isinstance(found, StructureRecords):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredOrganisation(factory)


def elevation_records_of(request: Request) -> ElevationRecords:
    """`app.state.elevation_records` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "elevation_records", None)
    if isinstance(found, ElevationRecords):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredElevations(factory)


def review_store_of(request: Request) -> StoredReview:
    """`app.state.review_store` when something put one there, and the database otherwise.

    Nothing in `brain.app` sets it, which is `brain.session_routes.session_store_of`'s arrangement.
    """
    found = getattr(request.app.state, "review_store", None)
    if isinstance(found, StoredReview):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredReview(factory)


# ---------------------------------------------------------------- the projections


def member_view(one: Member) -> MemberView:
    return MemberView(
        principal_id=one.principal_id, display_name=one.display_name, disabled=one.disabled
    )


def _shapes_nothing(_department: str) -> bool:
    return False


def organisation_page(
    shown: Organisation,
    *,
    full: bool,
    banner: StalenessBanner | None,
    may_organise: bool = False,
    shapeable: Callable[[str], bool] = _shapes_nothing,
) -> OrganisationPage:
    return OrganisationPage(
        items=[
            DepartmentView(
                slug=line.slug,
                name=line.name,
                shapeable=shapeable(line.slug),
                teams=[
                    TeamView(
                        slug=one.slug,
                        name=one.name,
                        members=[member_view(member) for member in one.members],
                    )
                    for one in line.teams
                ],
                members=[member_view(one) for one in line.members],
                lead=None if line.lead is None else member_view(line.lead),
            )
            for line in shown.departments
        ],
        may_organise=may_organise,
        unplaced=[
            UnplacedView(
                principal_id=one.principal_id,
                display_name=one.display_name,
                disabled=one.disabled,
                department=one.department,
            )
            for one in shown.unplaced
        ],
        truncated=full,
        staleness=banner,
    )


def grants_of(holding: Holding) -> tuple[Placed[SubjectGrant], ...]:
    """The grants a holding confers, each placed at its holder's row, or none if it does not build.

    `brain.govern_routes.placed_grant` and `placed_assignment`, called rather than repeated; the
    second goes through `packs.expand`, the only route from a pack to its grants. A row the types
    refuse confers nothing this screen can reason about, so it is neither listed nor decidable.
    """
    try:
        if isinstance(holding, GrantHolding):
            return (placed_grant(holding.row, holding.department),)
        return placed_assignment(holding.row, holding.pack, holding.department)
    except (ValueError, PredicateRefusedError):
        log.warning("reviewed holding does not construct", principal=holding.row.principal_id)
        return ()


def reviewable(
    holding: Holding, reach: EntitlementSet, now: datetime
) -> tuple[Placed[SubjectGrant], ...] | None:
    """The holding's grants when this reviewer may decide every one of them now, or None.

    Every one, because a pack is decided whole: `govern.recertifiable` over the expanded grants,
    and a pack with one capability the reviewer could not have written is absent, for
    `govern.A_REVIEW_THAT_SHOWS_A_GRANT_OUTSIDE_A_SCOPE_WIDENS_BY_SHOWING`'s reason. A grant that
    has lapsed confers nothing and is absent too, which is `govern.people`' reading of one.
    """
    grants = grants_of(holding)
    if not grants or not all(one.record.is_active(now) for one in grants):
        return None
    if len(recertifiable(grants, reach, now)) != len(grants):
        return None
    return grants


def review_row(
    holding: Holding, grants: Sequence[Placed[SubjectGrant]], last: LastDecision | None
) -> ReviewRowView:
    first = grants[0].record
    return ReviewRowView(
        kind=HoldingKind.GRANT if isinstance(holding, GrantHolding) else HoldingKind.PACK,
        row_id=str(holding.row.id),
        principal_id=held_by(holding),
        display_name=holding.display_name,
        department=holding.department,
        capabilities=[one.record.capability.value for one in grants],
        pack=holding.pack.name if isinstance(holding, PackHolding) else None,
        scope=first.scope.model_dump(),
        granted_by=first.granted_by,
        reason=first.reason,
        granted_at=first.granted_at,
        lapses_at=first.not_after,
        last_decision=None if last is None else last.decision,
        last_decided_by=None if last is None else last.decided_by,
        last_decided_at=None if last is None else last.decided_at,
    )


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.approval_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _not_answerable(what: str) -> Absent:
    """The refusal a screen makes. Names the screen and never a row or the caller."""
    return Absent(f"the {what} screen is not answerable for this caller")


def _not_decidable_here() -> Absent:
    """The one refusal a review decision makes. See `StoredReview.decide`."""
    return Absent("that grant is not decidable by this caller")


router = APIRouter(prefix=API_PREFIX, tags=["govern"])


# ------------------------------------------------------------------ the listings

#: What the Departments and teams screen may search, filter and order by: a department's name, its
#: teams, the people it shows and its lead, and whether it has one.
DEPARTMENTS: Final[Listing[DepartmentView]] = Listing(
    name="departments",
    columns=(
        Column("name", lambda row: row.name, search=True, sort=True),
        Column("slug", lambda row: row.slug, search=True, sort=True),
        Column("teams", lambda row: tuple(one.name for one in row.teams), search=True, filter=True),
        Column(
            "members",
            lambda row: tuple(
                name
                for one in (
                    *row.members,
                    *(member for team in row.teams for member in team.members),
                )
                for name in (one.display_name, one.principal_id)
            ),
            search=True,
        ),
        Column(
            "lead", lambda row: None if row.lead is None else row.lead.display_name, search=True
        ),
        Column("led", lambda row: row.lead is not None, filter=True),
    ),
    key=lambda row: row.slug,
    order="name",
)
DepartmentsQuery = Annotated[ListAsked, Depends(DEPARTMENTS.query())]

#: The people nobody has placed, searched with the departments' words. Never paged.
UNPLACED: Final[Listing[UnplacedView]] = Listing(
    name="unplaced",
    columns=(
        Column("display_name", lambda row: row.display_name, search=True, sort=True),
        Column("principal_id", lambda row: row.principal_id, search=True),
        Column("department", lambda row: row.department, search=True),
    ),
    key=lambda row: row.principal_id,
    order="display_name",
)

#: What the Elevation screen may search, filter and order the requests it shows by.
ELEVATIONS: Final[Listing[ElevationRequestView]] = Listing(
    name="elevation-requests",
    columns=(
        Column("display_name", lambda row: row.display_name, search=True, sort=True),
        Column("principal_id", lambda row: row.principal_id, search=True, filter=True),
        Column("department", lambda row: row.department, search=True, filter=True, sort=True),
        Column("capability", lambda row: row.capability, search=True, filter=True, sort=True),
        Column("scope_slug", lambda row: row.scope_slug, search=True, filter=True),
        Column("reason", lambda row: row.reason, filter=True),
        Column("explanation", lambda row: row.explanation, search=True),
        Column("state", lambda row: row.state.value, filter=True, sort=True),
        Column("decidable", lambda row: row.decidable, filter=True),
        Column("requested_at", lambda row: row.requested_at, sort=True),
        Column("lapses_at", lambda row: row.lapses_at, sort=True),
    ),
    key=lambda row: row.request_id,
    order="-requested_at",
)
ElevationsQuery = Annotated[ListAsked, Depends(ELEVATIONS.query())]

#: What the Access review screen may search, filter and order by.
REVIEW: Final[Listing[ReviewRowView]] = Listing(
    name="access-review",
    columns=(
        Column("display_name", lambda row: row.display_name, search=True, sort=True),
        Column("principal_id", lambda row: row.principal_id, search=True, filter=True, sort=True),
        Column("department", lambda row: row.department, search=True, filter=True, sort=True),
        Column("capabilities", lambda row: tuple(row.capabilities), search=True, filter=True),
        Column("pack", lambda row: row.pack, search=True, filter=True),
        Column("kind", lambda row: row.kind.value, filter=True),
        Column("granted_by", lambda row: row.granted_by, search=True, filter=True),
        Column("reason", lambda row: row.reason, search=True),
        Column(
            "last_decision",
            lambda row: "undecided" if row.last_decision is None else row.last_decision.value,
            filter=True,
            sort=True,
        ),
        Column("granted_at", lambda row: row.granted_at, sort=True),
        Column("lapses_at", lambda row: row.lapses_at, sort=True),
        Column("last_decided_at", lambda row: row.last_decided_at, sort=True),
    ),
    key=lambda row: f"{row.kind.value}:{row.row_id}",
    order="principal_id",
)
ReviewQuery = Annotated[ListAsked, Depends(REVIEW.query())]


# ------------------------------------------------------------------ departments


@router.get("/govern/departments", response_model=OrganisationPage, responses=COMMON_RESPONSES)
async def departments_page(
    request: Request, asked: Asked, listed: DepartmentsQuery
) -> OrganisationPage:
    """One page of the departments, their teams and their people, as this reader may be shown them.

    Opens on the Scopes and departments screen's read, because the headings are that screen's
    decision; who is listed under them is the People screen's, asked inside `organisation`. The
    search, filter and order are applied to the projected departments, so a search for a person
    finds the department they are shown under and never one they are withheld from.
    """
    if not permitted(screen(DEPARTMENTS_SCREEN).read, asked.reach, asked.now):
        log.info("departments screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable("departments")
    plan = DEPARTMENTS.plan(listed, reader=asked.caller.principal.id)
    remainder = UNPLACED.plan(ListAsked(search=listed.search), reader=asked.caller.principal.id)
    served = await organisation_source_of(request).load(limit=MAX_ROWS, now=asked.now)
    loaded = served.value
    shown = organisation(
        loaded.departments,
        loaded.teams,
        loaded.members,
        asked.reach,
        asked.now,
        memberships=loaded.memberships,
        leads=loaded.leads,
    )
    reach, now = asked.reach, asked.now

    def shapeable(department: str) -> bool:
        return may_shape_department(reach, department=department, now=now)

    whole = organisation_page(
        shown,
        full=loaded.full,
        banner=served.banner,
        may_organise=reach.scope_for(ORGANISING_AUTHORITY, now) is not None,
        shapeable=shapeable,
    )
    page = plan.page(whole.items)
    unplaced = [] if listed.cursor is not None else remainder.matching(whole.unplaced)
    return whole.model_copy(
        update={
            "items": list(page.items),
            "next_cursor": page.next_cursor,
            "unplaced": unplaced,
            "may_found": may_found_or_retire_departments(reach, now),
            "may_draw_scopes": reach.scope_for(SCOPE_AUTHORITY, now) is not None,
            "may_disable": reach.scope_for(GOVERNANCE_CONTROL, now) is not None,
        }
    )


def member_of(person: Person) -> Member:
    """A person a write read, as `brain.console.organisation` asks about one."""
    return Member(
        principal_id=person.principal_id,
        display_name=person.display_name,
        department=person.department,
        disabled=person.disabled,
    )


def _not_organisable_here() -> Absent:
    """The one refusal a placement or a lead change makes, whatever refused it."""
    return Absent("that change to the organisation is not writable by this caller")


@router.post(
    "/govern/departments/membership",
    response_model=OrganisationChanged,
    responses=COMMON_RESPONSES,
)
async def change_membership(
    request: Request, body: MembershipChange, asked: Asked
) -> OrganisationChanged:
    """Place a person in a team or take them out. A row, a ledger entry, and the team's listing.

    The authority is asked cheaply before a store is reached for, on the ordering argument every
    route here shares; then the store asks `may_place` or `may_organise` about the team and the
    person as the database holds them. A team that is not there, a person who is not there, a
    person already in the team, one not in it, and a caller out of reach are one refusal.
    """
    reach, now = asked.reach, asked.now
    if reach.scope_for(ORGANISING_AUTHORITY, now) is None:
        log.info("membership change refused", principal=asked.caller.principal.id)
        raise _not_organisable_here()
    store = organisation_records_of(request)
    decide = may_place if body.change == "join" else may_organise

    def may(person: Person) -> bool:
        return decide(reach, department=body.department, person=member_of(person), now=now)

    write = store.place if body.change == "join" else store.unplace
    at = await write(
        department=body.department,
        team=body.team,
        principal_id=body.principal_id,
        actor=asked.caller.principal.id,
        ent_hash=reach.ent_hash(),
        trace_id=_trace_id(),
        may=may,
    )
    if at is None:
        log.info("membership change not recorded", principal=asked.caller.principal.id)
        raise _not_organisable_here()
    return OrganisationChanged(
        department=body.department,
        team=body.team,
        principal_id=body.principal_id,
        change=body.change,
        at=at,
    )


@router.post(
    "/govern/departments/lead",
    response_model=OrganisationChanged,
    responses=COMMON_RESPONSES,
)
async def change_lead(request: Request, body: LeadChange, asked: Asked) -> OrganisationChanged:
    """Appoint a department's lead, ending the current one, or stand the current one down.

    An appointment asks `may_appoint` about the person and `may_organise` about the lead it ends;
    a standing down asks `may_organise` about the lead. Every refusal is one refusal.
    """
    reach, now = asked.reach, asked.now
    if reach.scope_for(ORGANISING_AUTHORITY, now) is None:
        log.info("lead change refused", principal=asked.caller.principal.id)
        raise _not_organisable_here()
    store = organisation_records_of(request)
    department = body.department
    actor = asked.caller.principal.id

    if body.principal_id is None:

        def may_end(lead: Person) -> bool:
            return may_organise(reach, department=department, person=member_of(lead), now=now)

        at = await store.stand_down(
            department=department,
            actor=actor,
            ent_hash=reach.ent_hash(),
            trace_id=_trace_id(),
            may=may_end,
        )
    else:

        def may_replace(person: Person, incumbent: Person | None) -> bool:
            if not may_appoint(reach, department=department, person=member_of(person), now=now):
                return False
            return incumbent is None or may_organise(
                reach, department=department, person=member_of(incumbent), now=now
            )

        at = await store.appoint(
            department=department,
            principal_id=body.principal_id,
            actor=actor,
            ent_hash=reach.ent_hash(),
            trace_id=_trace_id(),
            may=may_replace,
        )
    if at is None:
        log.info("lead change not recorded", principal=actor)
        raise _not_organisable_here()
    return OrganisationChanged(
        department=department,
        team=None,
        principal_id=body.principal_id,
        change=body.change,
        at=at,
    )


# ------------------------------------------------------------ the structure (M27.11.1)


def _by(asked: Asking) -> Attribution:
    """Who the triggers record: the caller from the token, their reach's digest, the request."""
    return Attribution(
        actor=asked.caller.principal.id, ent_hash=asked.reach.ent_hash(), trace_id=_trace_id()
    )


def _said(message: str) -> Absent:
    """A refusal a caller holding the authority over the row may read, as `prompt_routes` says."""
    return Absent(message, public_message=f"Nothing was changed: {message}.")


def _structured(
    outcome: Structured,
    asked: Asking,
    *,
    kind: Literal["department", "team", "scope"],
    slug: str,
    change: Literal["created", "renamed", "retired"],
    department: str | None = None,
    taken: str = A_DEPARTMENT_NAME_IS_TAKEN,
) -> StructureChanged:
    """The answer to a change to the structure, or the refusal its outcome is.

    `NOT_WRITABLE` is `_not_organisable_here`, the one refusal every placement makes, so a row out
    of reach and a row that is not there answer alike. The others are sentences, and each can only
    arrive for a caller the route and the store have already found holds the authority over the row.
    """
    if not isinstance(outcome, StructureRefusal):
        return StructureChanged(
            kind=kind, department=department, slug=slug, change=change, at=outcome
        )
    log.info("structure not changed", principal=asked.caller.principal.id, why=outcome.value)
    match outcome:
        case StructureRefusal.NAME_TAKEN:
            raise _said(taken)
        case StructureRefusal.CHANGED_SINCE:
            raise _said(IT_CHANGED_SINCE_YOU_OPENED_IT)
        case StructureRefusal.UNKNOWN_DEPARTMENT:
            raise _said(A_SCOPE_NAMES_NO_LIVE_DEPARTMENT)
        case StructureRefusal.COMPANY_WIDE_SCOPE:
            raise _said(THE_COMPANY_WIDE_SCOPE_IS_NEVER_RETIRED.rstrip("."))
        case StructureRefusal.DEPARTMENTS_OWN_SCOPE:
            raise _said(A_DEPARTMENTS_OWN_SCOPE_GOES_WITH_ITS_DEPARTMENT.rstrip("."))
        case StructureRefusal.NOT_WRITABLE:
            raise _not_organisable_here()


def _shaping_refused(asked: Asking, department: str) -> None:
    """The authority over one department's name and teams, asked before any store is reached for."""
    if not may_shape_department(asked.reach, department=department, now=asked.now):
        log.info("department not shapeable", principal=asked.caller.principal.id)
        raise _not_organisable_here()


def _founding_refused(asked: Asking) -> None:
    """The whole company's authority over departments and scopes, asked before any store."""
    if not may_found_or_retire_departments(asked.reach, asked.now):
        log.info("department not foundable", principal=asked.caller.principal.id)
        raise _not_organisable_here()


@router.post(
    "/govern/departments",
    response_model=StructureChanged,
    responses=COMMON_RESPONSES,
    status_code=201,
)
async def found_department(
    request: Request, body: DepartmentFounding, asked: Asked
) -> StructureChanged:
    """Create a department and the scope it is defined by. Two rows and two ledger entries.

    The whole company's authority, asked before the store: see
    `brain.console.organisation.FOUNDING_OR_RETIRING_A_DEPARTMENT_IS_THE_WHOLE_COMPANYS_ACT`. A
    short name a live department or scope already has is said, because a caller holding that
    authority governs every department and scope there is.
    """
    _founding_refused(asked)
    department, scope = founded(body.slug, body.name)
    outcome = await structure_records_of(request).found_department(
        department=department, scope=scope, by=_by(asked)
    )
    return _structured(outcome, asked, kind="department", slug=body.slug, change="created")


@router.post(
    "/govern/departments/rename", response_model=StructureChanged, responses=COMMON_RESPONSES
)
async def rename_department(
    request: Request, body: DepartmentRenaming, asked: Asked
) -> StructureChanged:
    """Change a department's name, never its short name, if it still has the name the page showed.

    The short name is the value every grant's scope carries, so it is not in the body at all.
    """
    _shaping_refused(asked, body.slug)
    outcome = await structure_records_of(request).rename_department(
        slug=body.slug, expected_name=body.expected_name, name=body.name, by=_by(asked)
    )
    return _structured(outcome, asked, kind="department", slug=body.slug, change="renamed")


@router.post(
    "/govern/departments/retirement",
    response_model=StructureChanged,
    responses=COMMON_RESPONSES,
)
async def retire_department(
    request: Request, body: DepartmentRetirement, asked: Asked
) -> StructureChanged:
    """Retire a department, its teams and every live scope that names it. Grants stay.

    See `brain.console.organisation.A_RETIRED_DEPARTMENT_IS_NAMED_BY_NO_LIVE_SCOPE` and
    `A_RETIRED_DEPARTMENT_LEAVES_EVERY_GRANT_ALREADY_WRITTEN_IN_FORCE`. Which scopes go with it is
    `retired_with`, asked by the store about each live scope under its lock.
    """
    _founding_refused(asked)
    slug = body.slug

    def takes(scope_slug: str, record: ScopeRecord | None, defining: str) -> bool:
        return retired_with(scope_slug, record, department=slug, defining=defining)

    outcome = await structure_records_of(request).retire_department(
        slug=slug, expected_name=body.expected_name, takes=takes, by=_by(asked)
    )
    return _structured(outcome, asked, kind="department", slug=slug, change="retired")


# Singular `team`: a path segment named `teams` reads as the Microsoft Teams channel to the
# inbound webhook sweep, which refuses any POST address a platform could be pointed at.
@router.post(
    "/govern/departments/team",
    response_model=StructureChanged,
    responses=COMMON_RESPONSES,
    status_code=201,
)
async def add_team(request: Request, body: TeamAdding, asked: Asked) -> StructureChanged:
    """Create a team in a department. One row and one ledger entry under the department."""
    _shaping_refused(asked, body.department)
    outcome = await structure_records_of(request).add_team(
        team=team_record(body.department, body.slug, body.name), by=_by(asked)
    )
    return _structured(
        outcome,
        asked,
        kind="team",
        department=body.department,
        slug=body.slug,
        change="created",
        taken=A_TEAM_NAME_IS_TAKEN,
    )


@router.post(
    "/govern/departments/team/rename",
    response_model=StructureChanged,
    responses=COMMON_RESPONSES,
)
async def rename_team(request: Request, body: TeamRenaming, asked: Asked) -> StructureChanged:
    """Change a team's name, if it still has the name the page showed."""
    _shaping_refused(asked, body.department)
    outcome = await structure_records_of(request).rename_team(
        department=body.department,
        slug=body.slug,
        expected_name=body.expected_name,
        name=body.name,
        by=_by(asked),
    )
    return _structured(
        outcome, asked, kind="team", department=body.department, slug=body.slug, change="renamed"
    )


@router.post(
    "/govern/departments/team/retirement",
    response_model=StructureChanged,
    responses=COMMON_RESPONSES,
)
async def retire_team(request: Request, body: TeamRetirement, asked: Asked) -> StructureChanged:
    """Retire a team. Its placements stay on record and nobody's access changes."""
    _shaping_refused(asked, body.department)
    outcome = await structure_records_of(request).retire_team(
        department=body.department,
        slug=body.slug,
        expected_name=body.expected_name,
        by=_by(asked),
    )
    return _structured(
        outcome, asked, kind="team", department=body.department, slug=body.slug, change="retired"
    )


@router.post(
    "/govern/departments/scopes",
    response_model=StructureChanged,
    responses=COMMON_RESPONSES,
    status_code=201,
)
async def draw_scope(request: Request, body: ScopeDrawing, asked: Asked) -> StructureChanged:
    """Create a scope over one department or a named set of them. One row and one ledger entry.

    Containment first, before the store: `may_draw_scope` over the scope drawn, so nobody draws a
    boundary wider than their own and a caller outside it learns nothing about the departments it
    names. A taken short name is said only when `may_know_taken_scope` finds the live scope holding
    it inside the caller's authority, and a department named that no live row carries is said,
    because the caller's authority already reaches it.
    """
    reach, now = asked.reach, asked.now
    record = drawn(body.slug, body.label, body.departments, body.team)
    if not may_draw_scope(reach, record.scope, now):
        log.info("scope not drawable", principal=asked.caller.principal.id)
        raise _not_organisable_here()

    def may_know(held: ScopeRecord | None) -> bool:
        return may_know_taken_scope(reach, held, now)

    outcome = await structure_records_of(request).draw_scope(
        scope=record,
        departments=tuple(body.departments),
        team=body.team,
        may_know=may_know,
        by=_by(asked),
    )
    return _structured(
        outcome, asked, kind="scope", slug=body.slug, change="created", taken=A_SCOPE_NAME_IS_TAKEN
    )


@router.post(
    "/govern/departments/scopes/retirement",
    response_model=StructureChanged,
    responses=COMMON_RESPONSES,
)
async def retire_scope(request: Request, body: ScopeRetirement, asked: Asked) -> StructureChanged:
    """Retire a scope, if it still bounds what the page showed. Grants over it stay.

    The authority is asked cheaply before the store; `scope_retirement` then asks it properly about
    the row under its lock, and refuses the company-wide scope and a department's own with a
    sentence. See `brain.console.organisation.A_RETIRED_SCOPE_TAKES_NO_GRANT_AWAY`.
    """
    reach, now = asked.reach, asked.now
    if reach.scope_for(SCOPE_AUTHORITY, now) is None:
        log.info("scope not retirable", principal=asked.caller.principal.id)
        raise _not_organisable_here()

    def judge(record: ScopeRecord, defines: bool) -> StructureRefusal | None:
        return scope_retirement(reach, record, defines_a_live_department=defines, now=now)

    outcome = await structure_records_of(request).retire_scope(
        slug=body.slug,
        expected=Scope.model_validate(body.expected_scope),
        judge=judge,
        by=_by(asked),
    )
    return _structured(outcome, asked, kind="scope", slug=body.slug, change="retired")


# ------------------------------------------------------------------ elevation


def elevation_request(stored: StoredRequest) -> ElevationRequest:
    """A stored request as `brain.console.elevation` asks about one."""
    return ElevationRequest(
        request_id=str(stored.request_id),
        principal_id=stored.principal_id,
        department=stored.department,
        capability=Capability(value=stored.capability),
    )


def request_view(
    stored: StoredRequest, reach: EntitlementSet, now: datetime
) -> ElevationRequestView:
    state = state_of(
        decision=stored.decision, lapses_at=stored.lapses_at, grant_live=stored.grant_live, now=now
    )
    return ElevationRequestView(
        request_id=str(stored.request_id),
        principal_id=stored.principal_id,
        display_name=stored.display_name,
        department=stored.department,
        capability=stored.capability,
        scope_slug=stored.scope_slug,
        reason=stored.reason,
        explanation=stored.explanation,
        hours=stored.hours,
        requested_at=stored.requested_at,
        state=state,
        decided_by=stored.decided_by,
        decided_at=stored.decided_at,
        lapses_at=stored.lapses_at,
        decidable=state is ElevationState.PENDING
        and may_decide(reach, elevation_request(stored), now),
    )


def approval_grant(
    pending: PendingRequest, *, approver: EntitlementSet, requester: EntitlementSet, at: datetime
) -> SubjectGrant | None:
    """The grant approving this request writes, if `may_approve` says so, or None.

    Built at the database's instant, lapsing the hours the request asked for later, at the scope
    the request names as that scope's row stands now. A slug no live scope carries, a predicate
    `ScopeRecord` refuses and a grant `SubjectGrant` refuses are all None, the same as a refusal.
    """
    stored = pending.request
    if pending.scope is None:
        return None
    try:
        record = ScopeRecord.from_predicate(
            pending.scope.slug,
            pending.scope.predicate,
            is_department=pending.scope.is_department,
            label=pending.scope.label,
        )
        grant = SubjectGrant(
            subject=PrincipalSubject(principal_id=stored.principal_id),
            capability=Capability(value=stored.capability),
            scope=record.scope,
            granted_by=approver.principal_id,
            reason=f"elevation {stored.request_id}: {stored.reason}",
            granted_at=at,
            not_after=at + timedelta(hours=stored.hours),
        )
    except (ValueError, PredicateRefusedError):
        return None
    if not may_approve(
        approver, elevation_request(stored), grant=grant, requester=requester, now=at
    ):
        return None
    return grant


def _not_elevatable_here() -> Absent:
    """The one refusal a request or a decision makes, whatever refused it."""
    return Absent("that elevation is not writable by this caller")


@router.get("/govern/elevation", response_model=ElevationPage, responses=COMMON_RESPONSES)
async def elevation_page(request: Request, asked: Asked, listed: ElevationsQuery) -> ElevationPage:
    """The request screen for this reader: their standing, the requests they are shown, the rules.

    Open to every signed-in caller, because everybody may ask for more and see their own
    requests, and the one reader the landing is designed for is somebody holding nothing. So the
    store is read for every caller alike, and a process with no database answers every caller
    alike. `requests_shown` decides the rows, and the listing pages what it decided.
    """
    plan = ELEVATIONS.plan(listed, reader=asked.caller.principal.id)
    shown = landing(asked.caller.principal, grants=asked.reach.grants)
    stored, full = await elevation_records_of(request).requests(limit=MAX_ROWS)
    by_id = {str(one.request_id): one for one in stored}
    visible = requests_shown([elevation_request(one) for one in stored], asked.reach, asked.now)
    page = plan.page(
        [request_view(by_id[one.request_id], asked.reach, asked.now) for one in visible]
    )
    return ElevationPage(
        prompt=requester_prompt(shown),
        holds_nothing_standing=shown.holds_nothing_standing,
        may_authorise=asked.reach.scope_for(ELEVATION_CONTROL, asked.now) is not None,
        reasons=[one.value for one in BreakGlassReason],
        longest_hours=int(BREAK_GLASS_MAX.total_seconds() // 3600),
        items=list(page.items),
        next_cursor=page.next_cursor,
        truncated=full,
    )


@router.post(
    "/govern/elevation/requests",
    response_model=ElevationFiled,
    responses=COMMON_RESPONSES,
    status_code=201,
)
async def file_elevation(request: Request, body: ElevationAsked, asked: Asked) -> ElevationFiled:
    """Ask for one capability, for yourself. A pending row and a ledger entry.

    Refused when the caller already holds anything covering the capability, before a store is
    reached for: `would_widen`, and `AN_ELEVATION_OF_WHAT_IS_ALREADY_HELD_WOULD_NARROW_IT`. The
    scope slug is not looked up, so filing says nothing about which scopes exist; whoever decides
    it resolves the slug.
    """
    capability = Capability(value=body.capability)
    if not would_widen(asked.reach, capability, asked.now):
        log.info("elevation not filed", principal=asked.caller.principal.id)
        raise _not_elevatable_here()
    filed = await elevation_records_of(request).file(
        principal_id=asked.caller.principal.id,
        capability=capability.value,
        scope_slug=body.scope_slug,
        reason=body.reason.value,
        explanation=body.explanation,
        hours=body.hours,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    )
    if filed is None:
        log.info("elevation not recorded", principal=asked.caller.principal.id)
        raise _not_elevatable_here()
    return ElevationFiled(request_id=str(filed.request_id), requested_at=filed.requested_at)


@router.post(
    "/govern/elevation/requests/{request_id}/decision",
    response_model=ElevationDecided,
    responses=COMMON_RESPONSES,
)
async def decide_elevation(
    request: Request, request_id: uuid.UUID, body: ElevationDecisionAsked, asked: Asked
) -> ElevationDecided:
    """Approve a request into a grant with a lapse, or deny it. Never your own.

    The authority is asked cheaply before a store is reached for; then the store asks
    `approval_grant` or `may_decide` about the request as it stands under its lock, with the
    requester's reach as the resolver answers it at the database's instant. A request that is not
    there, one already decided, the caller's own, one out of reach and one that would narrow its
    requester are one refusal.
    """
    reach = asked.reach
    if reach.scope_for(ELEVATION_CONTROL, asked.now) is None:
        log.info("elevation decision refused", principal=asked.caller.principal.id)
        raise _not_elevatable_here()
    store = elevation_records_of(request)
    decider = asked.caller.principal.id
    if body.decision is ElevationDecision.APPROVED:

        def grant_for(
            pending: PendingRequest, requester: EntitlementSet, at: datetime
        ) -> SubjectGrant | None:
            return approval_grant(pending, approver=reach, requester=requester, at=at)

        decided = await store.approve(
            request_id,
            approver_id=decider,
            ent_hash=reach.ent_hash(),
            trace_id=_trace_id(),
            grant_for=grant_for,
        )
    else:

        def may(pending: PendingRequest) -> bool:
            return may_decide(reach, elevation_request(pending.request), asked.now)

        decided = await store.deny(
            request_id,
            decider_id=decider,
            ent_hash=reach.ent_hash(),
            trace_id=_trace_id(),
            may=may,
        )
    if decided is None:
        log.info("elevation decision not recorded", principal=decider)
        raise _not_elevatable_here()
    return ElevationDecided(
        request_id=str(decided.request_id),
        principal_id=decided.principal_id,
        decision=decided.decision,
        decided_at=decided.decided_at,
        lapses_at=decided.lapses_at,
    )


# ------------------------------------------------------------------ access review


@router.get("/govern/access-review", response_model=ReviewPage, responses=COMMON_RESPONSES)
async def access_review_page(request: Request, asked: Asked, listed: ReviewQuery) -> ReviewPage:
    """One page of the grants this reviewer could have written, and the last decision about each."""
    if not permitted(screen(ACCESS_REVIEW_SCREEN).read, asked.reach, asked.now):
        log.info("access review not answerable", principal=asked.caller.principal.id)
        raise _not_answerable("access review")
    plan = REVIEW.plan(listed, reader=asked.caller.principal.id)
    holdings, decided, full = await review_store_of(request).holdings(limit=MAX_ROWS)
    items: list[ReviewRowView] = []
    for holding in holdings:
        grants = reviewable(holding, asked.reach, asked.now)
        if grants is None:
            continue
        items.append(review_row(holding, grants, decided.get(holding.row.id)))
    page = plan.page(items)
    return ReviewPage(items=list(page.items), next_cursor=page.next_cursor, truncated=full)


def _may_decide_holding(
    asked: Asking, decision: Decision, *, pack: bool
) -> Callable[[Holding], bool]:
    """The question the review store asks about one holding under its lock, for one caller.

    `govern.certify` over every grant the holding confers, and the holding must be of the table the
    body named. One function for the single decision and the bulk one, so the two cannot differ.
    """
    reach, now, decider = asked.reach, asked.now, asked.caller.principal.id

    def may(holding: Holding) -> bool:
        if isinstance(holding, PackHolding) is not pack:
            return False
        grants = reviewable(holding, reach, now)
        if grants is None:
            return False
        try:
            for one in grants:
                certify(one, reach, decision, by=decider, at=now, now=now)
        except (GovernError, ValueError):
            return False
        return True

    return may


@router.post(
    "/govern/access-review/decision", response_model=ReviewDecided, responses=COMMON_RESPONSES
)
async def decide_review(request: Request, body: ReviewDecisionAsked, asked: Asked) -> ReviewDecided:
    """Keep or remove one holding. A decision row, a ledger entry, and for a removal the grant gone.

    The review authority is asked before a store is reached for; then the store locks the row and
    asks `may`, which is `govern.certify` over every grant the holding confers, because a decision
    is pressed by whatever was posted rather than by what the page offered.
    """
    reach, now = asked.reach, asked.now
    if reach.scope_for(screen(ACCESS_REVIEW_SCREEN).read.requires, now) is None:
        log.info("review decision refused", principal=asked.caller.principal.id)
        raise _not_decidable_here()

    store = review_store_of(request)
    decider = asked.caller.principal.id
    wanted_pack = body.kind is HoldingKind.PACK
    decided: Decided | None = await store.decide(
        body.row_id,
        pack=wanted_pack,
        decision=ReviewDecision(body.decision.value),
        may=_may_decide_holding(asked, body.decision, pack=wanted_pack),
        decided_by=decider,
        ent_hash=reach.ent_hash(),
        trace_id=_trace_id(),
    )
    if decided is None:
        log.info("review decision not recorded", principal=decider)
        raise _not_decidable_here()
    return ReviewDecided(
        kind=body.kind,
        row_id=str(decided.row_id),
        principal_id=decided.principal_id,
        decision=decided.decision,
        decided_at=decided.decided_at,
    )


@router.post(
    "/govern/access-review/decisions",
    response_model=ReviewDecisionsDecided,
    responses=COMMON_RESPONSES,
)
async def decide_reviews(
    request: Request, body: ReviewDecisionsAsked, asked: Asked
) -> ReviewDecisionsDecided:
    """Keep or remove each named holding, one decision at a time.

    The review authority is asked once, before a store is reached for, exactly as the single
    decision asks it, and a caller without it is the single decision's 404. Then every holding is
    the single decision: its own lock, its own `may`, its own row and ledger entries. See
    `brain.listing.SEVERAL_ACTS_ARE_EACH_DECIDED_ALONE`.
    """
    reach, now = asked.reach, asked.now
    if reach.scope_for(screen(ACCESS_REVIEW_SCREEN).read.requires, now) is None:
        log.info("review decisions refused", principal=asked.caller.principal.id)
        raise _not_decidable_here()

    store = review_store_of(request)
    decision = ReviewDecision(body.decision.value)

    async def decide_one(named: tuple[HoldingKind, uuid.UUID]) -> Decided | None:
        kind, row_id = named
        pack = kind is HoldingKind.PACK
        return await store.decide(
            row_id,
            pack=pack,
            decision=decision,
            may=_may_decide_holding(asked, body.decision, pack=pack),
            decided_by=asked.caller.principal.id,
            ent_hash=reach.ent_hash(),
            trace_id=_trace_id(),
        )

    outcomes = await each_of([(one.kind, one.row_id) for one in body.holdings], decide_one)
    return ReviewDecisionsDecided(
        decision=decision,
        outcomes=[
            ReviewOutcome(kind=kind, row_id=str(row_id), decided=False)
            if decided is None
            else ReviewOutcome(
                kind=kind,
                row_id=str(row_id),
                decided=True,
                principal_id=decided.principal_id,
                decided_at=decided.decided_at,
            )
            for (kind, row_id), decided in outcomes
        ],
    )


# ------------------------------------------------------------------ subscribers


def _empty_subscribers() -> SubscribersPage:
    """What an install with no subscribers answers, and what a reader who may not manage is told.

    One function for both, so the two cannot come apart:
    `brain.console.subscribers.A_READER_WHO_MAY_NOT_MANAGE_IS_SHOWN_WHAT_AN_EMPTY_INSTALL_SHOWS`.
    """
    return SubscribersPage(items=[], findings=[], kinds=[one.value for one in EventKind])


@router.get("/govern/subscribers", response_model=SubscribersPage, responses=COMMON_RESPONSES)
async def subscribers_page(request: Request, asked: Asked) -> SubscribersPage:
    """Who is told what, and when each was last told.

    `may_manage` is asked before the database, and the answer for a reader without it is the empty
    install's, which is `subscriber_lines`' own answer asked early enough to be free: loading first
    would make the refusal differ between a process with a database and one without.
    """
    if not may_manage(asked.reach, asked.now):
        log.info("subscribers not shown", principal=asked.caller.principal.id)
        return _empty_subscribers()
    served = await subscriber_source_of(request).load(now=asked.now)
    registered, delivered = served.value
    lines = subscriber_lines(asked.reach, registered, delivered, now=asked.now)
    return SubscribersPage(
        items=[
            SubscriberView(
                subscriber_id=one.subscriber_id,
                endpoint=one.endpoint,
                kinds=list(one.kinds),
                active=one.active,
                created_by=one.created_by,
                last_delivered_at=one.last_delivered_at,
            )
            for one in lines
        ],
        findings=list(findings(asked.reach, registered, now=asked.now)),
        kinds=[one.value for one in EventKind],
        staleness=served.banner,
    )
