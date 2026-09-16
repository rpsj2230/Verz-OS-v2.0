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

**Two of the four say more about what is missing than about what is there, and that is the design
rather than an apology.** Nothing on an install stores a break-glass session or opens one, so the
Elevation screen is the landing `brain.console.elevation` decides and the rules a session would be
held to, with no list and no control. And switching a webhook subscriber off has no ledger member to
be recorded under and no audit subject a subscriber id fits, so the Subscribers screen lists who is
told what and says how that stops, without a button whose press nobody could later attribute. Both
sentences travel on the response, for `brain.skill_routes`' reason: the day a fact changes, the
sentence changes in the same commit.

**No count of anything, anywhere.** Every listing is filtered per caller, and `truncated` says a
load came back full, computed against what was loaded rather than what survived.

Task ids: M27.7.4, M27.7.8, M27.7.9, M27.7.12
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.elevation import ELEVATION_CONTROL, landing
from brain.console.govern import Decision, GovernError, Placed, certify, recertifiable
from brain.console.organisation import (
    DEPARTMENTS_SCREEN,
    Department,
    Member,
    Organisation,
    Team,
    organisation,
)
from brain.console.read_replica import StalenessBanner
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.subscribers import findings, subscriber_lines
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.core.scope_sql import PredicateRefusedError
from brain.gate.review_store import (
    Decided,
    GrantHolding,
    Holding,
    LastDecision,
    PackHolding,
    StoredReview,
)
from brain.govern_routes import placed_assignment, placed_grant
from brain.identity.packs import SubjectGrant
from brain.identity.roles import BREAK_GLASS_MAX, BreakGlassReason
from brain.ops.outbox import EventKind, Subscriber, may_manage
from brain.ops.outbox_store import last_delivered, subscribers
from brain.ops.replica_store import ConsoleReads, Served
from brain.routing_routes import sessions_of
from brain.tables.gate import DepartmentRow, TeamRow
from brain.tables.identity import PrincipalRow
from brain.tables.review import ReviewDecision

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: What the organisation screen cannot show, served beside it.
WHO_IS_IN_A_TEAM_IS_NOT_RECORDED: Final = (
    "Who is in each team is not recorded on this install. A team exists as a named part of its "
    "department, and nothing yet stores its members, so a team is listed here with nobody under it."
)
NO_DEPARTMENT_LEAD_IS_RECORDED: Final = (
    "Nothing on this install records who leads a department. Whoever may review a department's "
    "access holds that authority as a grant, which the People and grants screen shows."
)
NOTHING_HERE_IS_COUNTED: Final = (
    "No headcount is shown. Every list here is narrowed to what you may see, so a number beside "
    "it would say how much you were not shown."
)

#: What an elevation is, served on the Elevation screen.
AN_ELEVATION_IS_A_GRANT_WITH_A_CLOCK_ON_IT: Final = (
    "An elevation is a break-glass session: grants named one by one, for one person, for a reason "
    "from a fixed list, for a few hours at most, authorised by somebody other than that person, "
    "told to the standing Super Admins other than those two, and recorded in an audit chain of "
    "its own. While it is open it replaces what the person holds rather than adding to it."
)
NOTHING_STORES_AN_ELEVATION_YET: Final = (
    "Nothing on this install stores an elevation or opens one. The rules above are enforced "
    "where a session is built, and no request consults a session yet, so there is no request "
    "here to approve or deny, no list of who was given what, and no control to end one early. "
    "When sessions are stored, they are listed here with who asked, who authorised, what was "
    "given and when it lapses."
)
AUTHORISING_IS_THE_ACCESS_REVIEW_AUTHORITY: Final = (
    "Authorising an elevation takes the same authority the Access review screen asks for, held "
    "over the department the person sits in."
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

#: What the subscribers screen cannot do, served beside it.
SWITCHING_A_SUBSCRIBER_OFF_IS_NOT_ON_THIS_SCREEN_YET: Final = (
    "Switching a subscriber off is not on this screen yet. The change itself is one statement, "
    "and the audit ledger has nothing it could be recorded under, so a control here would stop "
    "deliveries with nobody able to read afterwards who stopped them. Until it is, an operator "
    "switches one off at the database. A subscriber switched off is never switched back on: it "
    "is registered again under a new id."
)
ONLY_WEBHOOK_SUBSCRIBERS_ARE_LISTED: Final = (
    "Only webhook subscribers are listed. The evening digest goes to one room named in this "
    "install's configuration, and alerts go to whoever a grant makes responsible at the moment "
    "they fire, so neither has a stored list of recipients to show."
)
A_SUBSCRIBER_IS_TOLD_IDENTIFIERS: Final = (
    "A subscriber is told that something happened and the identifiers of what it happened to, "
    "never the content."
)

# ----------------------------------------------------------------- the screens

#: The registered screen whose read opens the review and decides whether a decision may be
#: offered at all. A key rather than a capability, so it cannot drift from the registry.
ACCESS_REVIEW_SCREEN: Final = "access_review"

#: The most rows one listing loads. A resource bound and not a permission one.
MAX_ROWS: Final = 1000
DEFAULT_ROWS: Final = 500


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
    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    name: str


class DepartmentView(BaseModel):
    """One offered department, its teams and the people in it this reader may be shown."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    name: str
    teams: list[TeamView]
    members: list[MemberView]


class OrganisationPage(BaseModel):
    """The organisation, and the three sentences about what it cannot show."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    departments: list[DepartmentView]
    unplaced: list[UnplacedView]
    #: A load came back full. Never how much more there is.
    truncated: bool
    staleness: StalenessBanner | None = None
    teams: str = WHO_IS_IN_A_TEAM_IS_NOT_RECORDED
    leads: str = NO_DEPARTMENT_LEAD_IS_RECORDED
    counted: str = NOTHING_HERE_IS_COUNTED


class ElevationPage(BaseModel):
    """The break-glass landing for this reader, and the rules a session would be held to.

    Three fields are `brain.console.elevation.ElevationLanding`'s, and nothing here lists what a
    session could confer: `A_LANDING_THAT_LISTS_WHAT_YOU_COULD_ELEVATE_TO_IS_THE_CATALOGUE`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str
    holds_nothing_standing: bool
    #: Whether this reader holds the authority to authorise one anywhere. Presentation only.
    may_authorise: bool
    #: The closed list of reasons a session may be opened for. The product's, not the company's.
    reasons: list[str]
    #: The longest a session may run, in hours.
    longest_hours: int
    what: str = AN_ELEVATION_IS_A_GRANT_WITH_A_CLOCK_ON_IT
    recorded: str = NOTHING_STORES_AN_ELEVATION_YET
    authorising: str = AUTHORISING_IS_THE_ACCESS_REVIEW_AUTHORITY


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
    stopping: str = SWITCHING_A_SUBSCRIBER_OFF_IS_NOT_ON_THIS_SCREEN_YET
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


@dataclass(frozen=True)
class OrganisationSource:
    """`gate.department`, `gate.team` and `auth.principal`, read for display. Decides nothing."""

    reads: ConsoleReads

    async def load(self, *, limit: int, now: datetime) -> Served[LoadedOrganisation]:
        async def work(session: AsyncSession) -> LoadedOrganisation:
            departments = (await session.execute(live_departments(limit))).all()
            teams = (await session.execute(live_teams(limit))).all()
            people = (await session.execute(live_people(limit))).all()
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
                full=max(len(departments), len(teams), len(people)) >= limit,
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


def organisation_page(
    shown: Organisation, *, full: bool, banner: StalenessBanner | None
) -> OrganisationPage:
    return OrganisationPage(
        departments=[
            DepartmentView(
                slug=line.slug,
                name=line.name,
                teams=[TeamView(slug=one.slug, name=one.name) for one in line.teams],
                members=[
                    MemberView(
                        principal_id=one.principal_id,
                        display_name=one.display_name,
                        disabled=one.disabled,
                    )
                    for one in line.members
                ],
            )
            for line in shown.departments
        ],
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
        principal_id=holding.row.principal_id,
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


# ------------------------------------------------------------------ departments


@router.get("/govern/departments", response_model=OrganisationPage, responses=COMMON_RESPONSES)
async def departments_page(
    request: Request,
    asked: Asked,
    limit: Annotated[int, Query(ge=1, le=MAX_ROWS)] = DEFAULT_ROWS,
) -> OrganisationPage:
    """The departments, their teams and their people, as this reader may be shown them.

    Opens on the Scopes and departments screen's read, because the headings are that screen's
    decision; who is listed under them is the People screen's, asked inside `organisation`.
    """
    if not permitted(screen(DEPARTMENTS_SCREEN).read, asked.reach, asked.now):
        log.info("departments screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable("departments")
    served = await organisation_source_of(request).load(limit=limit, now=asked.now)
    loaded = served.value
    shown = organisation(loaded.departments, loaded.teams, loaded.members, asked.reach, asked.now)
    return organisation_page(shown, full=loaded.full, banner=served.banner)


# ------------------------------------------------------------------ elevation


@router.get("/govern/elevation", response_model=ElevationPage, responses=COMMON_RESPONSES)
async def elevation_page(asked: Asked) -> ElevationPage:
    """The break-glass landing for this reader. No database: nothing stores a session to read.

    Open to every signed-in caller, because the one reader the landing is designed for is
    somebody holding nothing, and a landing that required a grant would be unreachable for them.
    """
    shown = landing(asked.caller.principal, grants=asked.reach.grants)
    return ElevationPage(
        prompt=shown.prompt,
        holds_nothing_standing=shown.holds_nothing_standing,
        may_authorise=asked.reach.scope_for(ELEVATION_CONTROL, asked.now) is not None,
        reasons=[one.value for one in BreakGlassReason],
        longest_hours=int(BREAK_GLASS_MAX.total_seconds() // 3600),
    )


# ------------------------------------------------------------------ access review


@router.get("/govern/access-review", response_model=ReviewPage, responses=COMMON_RESPONSES)
async def access_review_page(
    request: Request,
    asked: Asked,
    limit: Annotated[int, Query(ge=1, le=MAX_ROWS)] = DEFAULT_ROWS,
) -> ReviewPage:
    """Every grant this reviewer could have written, and the last decision about each."""
    if not permitted(screen(ACCESS_REVIEW_SCREEN).read, asked.reach, asked.now):
        log.info("access review not answerable", principal=asked.caller.principal.id)
        raise _not_answerable("access review")
    holdings, decided, full = await review_store_of(request).holdings(limit=limit)
    items: list[ReviewRowView] = []
    for holding in holdings:
        grants = reviewable(holding, asked.reach, asked.now)
        if grants is None:
            continue
        items.append(review_row(holding, grants, decided.get(holding.row.id)))
    return ReviewPage(items=items, truncated=full)


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

    def may(holding: Holding) -> bool:
        if isinstance(holding, PackHolding) is not wanted_pack:
            return False
        grants = reviewable(holding, reach, now)
        if grants is None:
            return False
        try:
            for one in grants:
                certify(one, reach, body.decision, by=decider, at=now, now=now)
        except (GovernError, ValueError):
            return False
        return True

    decided: Decided | None = await store.decide(
        body.row_id,
        pack=wanted_pack,
        decision=ReviewDecision(body.decision.value),
        may=may,
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
