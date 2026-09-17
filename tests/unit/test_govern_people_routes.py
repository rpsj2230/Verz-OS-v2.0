"""Departments and teams, Elevation, Access review and Subscribers over HTTP.

Driven through the real application with the token machinery borrowed from
`tests/unit/test_api_routes.py`, with the sources and the review store in memory where the
database is. None of the doubles decides anything: the review store asks the route's `may` under
what would be the row's lock, exactly as `brain.gate.review_store.StoredReview.decide` does, and
the sources hand back rows. What reaches the database, the ledger entries the triggers write and
the grant no longer resolved are proved in `tests/unit/test_review_store.py`, against PostgreSQL.

**Every refusal has a sibling proving the permitted case is answered**, which is CLAUDE.md's rule
about a guard tested only by its refusals. Capabilities are spelled out rather than read off the
registry, for `tests/unit/test_govern_routes.py`' reason.

Task ids: M27.7.4, M27.7.8, M27.7.9, M27.7.12, M27.8.6
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import govern_people_routes as routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.elevation import REQUEST_ADDS_PROMPT, ElevationState
from brain.console.organisation import Department, Lead, Member, Membership, Team
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.elevation_store import (
    Decided as ElevationDecided,
)
from brain.gate.elevation_store import (
    ElevationRecords,
    NamedScope,
    PendingRequest,
    StoredRequest,
)
from brain.gate.review_store import (
    Decided,
    GrantHolding,
    Holding,
    LastDecision,
    PackHolding,
    StoredReview,
)
from brain.identity.bearer import TokenAuthority
from brain.identity.organisation_store import OrganisationRecords, Person
from brain.identity.packs import SubjectGrant
from brain.identity.roles import BreakGlassReason
from brain.identity.teams import PrincipalSubject
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.ops.outbox import EventKind, Subscriber
from brain.ops.replica_store import Served
from brain.ops.secrets import SecretRef, VaultRole
from brain.tables.elevation import ElevationDecision
from brain.tables.gate import CapabilityGrantRow, CapabilityPackAssignmentRow, CapabilityPackRow
from brain.tables.review import ReviewDecision
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

DEPARTMENTS = f"{API_PREFIX}/govern/departments"
MEMBERSHIP = f"{API_PREFIX}/govern/departments/membership"
LEAD = f"{API_PREFIX}/govern/departments/lead"
ELEVATION = f"{API_PREFIX}/govern/elevation"
ELEVATION_REQUESTS = f"{API_PREFIX}/govern/elevation/requests"
REVIEW = f"{API_PREFIX}/govern/access-review"
DECISION = f"{API_PREFIX}/govern/access-review/decision"
DECISIONS = f"{API_PREFIX}/govern/access-review/decisions"
SUBSCRIBERS = f"{API_PREFIX}/govern/subscribers"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

SECOND_FACTOR: dict[str, object] = {"amr": ["otp"]}

WHOLE = Scope.unrestricted()
WEB = Scope.department("web")
CONFIGURATION = plane_capability(Plane.CONFIGURATION).value
EXISTENCE = plane_capability(Plane.EXISTENCE).value


def grant(value: str, scope: Scope = WHOLE) -> Grant:
    return Grant(capability=Capability(value=value), scope=scope)


#: `u_admin` holds every read here company-wide, the review authority, the two capabilities the
#: rows grant, and subscriber management. `u_elsewhere` holds the same in web only. `u_wide` holds
#: the reads and no authority. `u_prefix` holds the reads on the existence plane only, which a bare
#: capability check would let through. `u_narrow` holds the review authority and one of the two
#: capabilities in a pack. `u_none` holds nothing.
GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_admin": (
        grant("read:scope"),
        grant("read:grant"),
        grant("approve:grant"),
        grant("read:client.name"),
        grant("read:invoice.total"),
        grant("admin:webhook_subscriber"),
        grant(CONFIGURATION),
    ),
    "u_elsewhere": (
        grant("read:scope", WEB),
        grant("read:grant", WEB),
        grant("approve:grant", WEB),
        grant("read:client.name", WEB),
        grant("read:invoice.total", WEB),
        grant(CONFIGURATION),
    ),
    "u_wide": (grant("read:scope"), grant("read:grant"), grant(CONFIGURATION)),
    "u_prefix": (
        grant("read:scope"),
        grant("read:grant"),
        grant("approve:grant"),
        grant(EXISTENCE),
    ),
    "u_narrow": (
        grant("approve:grant"),
        grant("read:client.name"),
        grant(CONFIGURATION),
    ),
    "u_none": (),
}


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


# ------------------------------------------------------------------- the doubles


class Organisation(routes.OrganisationSource):
    """An `OrganisationSource` handing back rows, and counting how often it was asked."""

    def __init__(self) -> None:
        object.__setattr__(self, "calls", [])
        object.__setattr__(
            self,
            "loaded",
            routes.LoadedOrganisation(
                departments=(
                    Department(slug="finance", name="Finance"),
                    Department(slug="web", name="Web"),
                ),
                teams=(
                    Team(department="web", slug="design", name="Design"),
                    Team(department="finance", slug="payroll", name="Payroll"),
                ),
                members=(
                    Member(
                        principal_id="u_2", display_name="Wei", department="web", disabled=False
                    ),
                    Member(
                        principal_id="u_3",
                        display_name="Grace",
                        department="finance",
                        disabled=True,
                    ),
                    Member(
                        principal_id="u_4", display_name="Nobody", department=None, disabled=False
                    ),
                ),
                full=False,
                memberships=(
                    Membership(department="web", team="design", principal_id="u_2"),
                    Membership(department="web", team="design", principal_id="u_3"),
                ),
                leads=(
                    Lead(department="web", principal_id="u_2"),
                    Lead(department="finance", principal_id="u_3"),
                ),
            ),
        )

    async def load(self, *, limit: int, now: datetime) -> Served[routes.LoadedOrganisation]:
        self.calls.append(limit)  # type: ignore[attr-defined]
        return Served(value=self.loaded, banner=None)  # type: ignore[attr-defined]


class Subscribers(routes.SubscriberSource):
    def __init__(self, registered: tuple[Subscriber, ...]) -> None:
        object.__setattr__(self, "calls", [])
        object.__setattr__(self, "registered", registered)

    async def load(
        self, *, now: datetime
    ) -> Served[tuple[tuple[Subscriber, ...], dict[str, datetime]]]:
        self.calls.append(now)  # type: ignore[attr-defined]
        return Served(value=(self.registered, {"hook_a": LONG_AGO}), banner=None)  # type: ignore[attr-defined]


class Placements(OrganisationRecords):
    """`OrganisationRecords` in memory. Each write asks `may` about the person as the store would.

    People sit where `PEOPLE` says; `u_admin` is in web so a self-appointment can be posted.
    """

    PEOPLE: ClassVar[dict[str, Person]] = {
        "u_2": Person(principal_id="u_2", display_name="Wei", department="web", disabled=False),
        "u_3": Person(
            principal_id="u_3", display_name="Grace", department="finance", disabled=False
        ),
        "u_gone": Person(
            principal_id="u_gone", display_name="Gone", department="web", disabled=True
        ),
        "u_admin": Person(
            principal_id="u_admin", display_name="Admin", department="web", disabled=False
        ),
    }

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.written: list[tuple[str, str, str | None, str]] = []
        self.members: set[tuple[str, str, str]] = set()
        self.leads: dict[str, str] = {}

    async def place(
        self,
        *,
        department: str,
        team: str,
        principal_id: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[Person], bool],
    ) -> datetime | None:
        self.calls.append("place")
        person = self.PEOPLE.get(principal_id)
        key = (department, team, principal_id)
        if person is None or key in self.members or not may(person):
            return None
        self.members.add(key)
        self.written.append(("joined", department, principal_id, actor))
        return LONG_AGO

    async def unplace(
        self,
        *,
        department: str,
        team: str,
        principal_id: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[Person], bool],
    ) -> datetime | None:
        self.calls.append("unplace")
        key = (department, team, principal_id)
        if key not in self.members or not may(self.PEOPLE[principal_id]):
            return None
        self.members.discard(key)
        self.written.append(("left", department, principal_id, actor))
        return LONG_AGO

    async def appoint(
        self,
        *,
        department: str,
        principal_id: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[Person, Person | None], bool],
    ) -> datetime | None:
        self.calls.append("appoint")
        person = self.PEOPLE.get(principal_id)
        current = self.leads.get(department)
        incumbent = None if current is None else self.PEOPLE[current]
        if person is None or current == principal_id or not may(person, incumbent):
            return None
        self.leads[department] = principal_id
        self.written.append(("appointed", department, principal_id, actor))
        return LONG_AGO

    async def stand_down(
        self,
        *,
        department: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[Person], bool],
    ) -> datetime | None:
        self.calls.append("stand_down")
        current = self.leads.get(department)
        if current is None or not may(self.PEOPLE[current]):
            return None
        del self.leads[department]
        self.written.append(("stood_down", department, current, actor))
        return LONG_AGO


def a_request(
    principal_id: str,
    department: str | None,
    *,
    capability: str = "read:client.name",
    decision: ElevationDecision | None = None,
    lapses_at: datetime | None = None,
    grant_live: bool = False,
) -> StoredRequest:
    return StoredRequest(
        request_id=uuid.uuid5(uuid.NAMESPACE_URL, f"{principal_id}/{capability}/{decision}"),
        principal_id=principal_id,
        display_name=f"Person {principal_id}",
        department=department,
        capability=capability,
        scope_slug="web_all",
        reason="incident_response",
        explanation="the portal is down",
        hours=2,
        requested_at=LONG_AGO,
        decision=decision,
        decided_by=None if decision is None else "u_other",
        decided_at=None if decision is None else LONG_AGO,
        lapses_at=lapses_at,
        grant_live=grant_live,
    )


class Elevations(ElevationRecords):
    """`ElevationRecords` in memory. A decision asks the route's callable about the pending row,
    with the requester holding what `REACHES` says, as the store asks with the resolver's answer."""

    REACHES: ClassVar[dict[str, tuple[Grant, ...]]] = {
        "u_2": (),
        "u_3": (),
        "u_admin": GRANTS["u_admin"],
    }

    def __init__(self) -> None:
        self.stored: list[StoredRequest] = []
        self.calls: list[str] = []
        self.granted: list[SubjectGrant] = []
        self.denied: list[tuple[uuid.UUID, str]] = []
        self.scope: NamedScope | None = NamedScope(
            slug="web_all", predicate={"department": "web"}, is_department=False, label=""
        )

    async def requests(self, *, limit: int) -> tuple[tuple[StoredRequest, ...], bool]:
        self.calls.append("requests")
        return tuple(self.stored), False

    async def file(
        self,
        *,
        principal_id: str,
        capability: str,
        scope_slug: str,
        reason: str,
        explanation: str,
        hours: int,
        ent_hash: str,
        trace_id: str,
    ) -> StoredRequest | None:
        self.calls.append("file")
        filed = a_request(principal_id, None, capability=capability)
        self.stored.append(filed)
        return filed

    def _pending(self, request_id: uuid.UUID) -> StoredRequest | None:
        for one in self.stored:
            if one.request_id == request_id and one.decision is None:
                return one
        return None

    async def approve(
        self,
        request_id: uuid.UUID,
        *,
        approver_id: str,
        ent_hash: str,
        trace_id: str,
        grant_for: Callable[[PendingRequest, EntitlementSet, datetime], SubjectGrant | None],
    ) -> ElevationDecided | None:
        self.calls.append("approve")
        one = self._pending(request_id)
        if one is None:
            return None
        requester = EntitlementSet(
            principal_id=one.principal_id, grants=self.REACHES.get(one.principal_id, ())
        )
        at = datetime.now(UTC)
        grant = grant_for(PendingRequest(request=one, scope=self.scope), requester, at)
        if grant is None:
            return None
        self.granted.append(grant)
        return ElevationDecided(
            request_id=request_id,
            principal_id=one.principal_id,
            decision=ElevationDecision.APPROVED,
            decided_at=at,
            lapses_at=grant.not_after,
        )

    async def deny(
        self,
        request_id: uuid.UUID,
        *,
        decider_id: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[PendingRequest], bool],
    ) -> ElevationDecided | None:
        self.calls.append("deny")
        one = self._pending(request_id)
        if one is None or not may(PendingRequest(request=one, scope=self.scope)):
            return None
        self.denied.append((request_id, decider_id))
        return ElevationDecided(
            request_id=request_id,
            principal_id=one.principal_id,
            decision=ElevationDecision.DENIED,
            decided_at=LONG_AGO,
            lapses_at=None,
        )


def a_grant_row(principal_id: str, capability: str, *, lapsed: bool = False) -> CapabilityGrantRow:
    row = CapabilityGrantRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"{principal_id}/{capability}"),
        principal_id=principal_id,
        capability=capability,
        scope=WHOLE.model_dump(),
        granted_by="u_seed",
        reason="the job needs it",
        not_after=(datetime.now(UTC) - timedelta(days=1)) if lapsed else None,
    )
    row.created_at = LONG_AGO
    return row


def a_pack_holding(principal_id: str, department: str) -> PackHolding:
    pack = CapabilityPackRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, "pricing"),
        name="pricing",
        description="what pricing needs",
        capabilities=["read:client.name", "read:invoice.total"],
    )
    row = CapabilityPackAssignmentRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"{principal_id}/pricing"),
        principal_id=principal_id,
        pack_id=pack.id,
        scope=WEB.model_dump(),
        granted_by="u_seed",
        reason="joined pricing",
        not_after=None,
    )
    row.created_at = LONG_AGO
    return PackHolding(row=row, pack=pack, display_name="Packed", department=department)


class Review(StoredReview):
    """A `StoredReview` in memory. `decide` asks `may` about the row, as the real store does."""

    held: list[Holding]
    decided: dict[uuid.UUID, LastDecision]
    calls: list[str]
    recorded: list[tuple[uuid.UUID, ReviewDecision, str]]

    def __init__(self) -> None:
        # The store is a frozen dataclass; a double holding state sets it the way one would.
        for name, value in (("held", []), ("decided", {}), ("calls", []), ("recorded", [])):
            object.__setattr__(self, name, value)

    async def holdings(
        self, *, limit: int
    ) -> tuple[tuple[Holding, ...], dict[uuid.UUID, LastDecision], bool]:
        self.calls.append("holdings")
        return tuple(self.held), self.decided, False

    async def decide(
        self,
        row_id: uuid.UUID,
        *,
        pack: bool,
        decision: ReviewDecision,
        may: Callable[[Holding], bool],
        decided_by: str,
        ent_hash: str,
        trace_id: str,
    ) -> Decided | None:
        self.calls.append("decide")
        for one in self.held:
            if one.row.id == row_id and may(one):
                self.recorded.append((row_id, decision, decided_by))
                return Decided(
                    row_id=row_id,
                    principal_id=one.row.principal_id,
                    decision=decision,
                    decided_at=LONG_AGO,
                )
        return None


def a_review() -> Review:
    return Review()


def _wiring() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=Store(),
        cache=NoCache(),
    )


@dataclass
class Wired:
    client: TestClient
    organisation: Organisation
    review: Review
    subscribers: Subscribers
    placements: Placements
    elevations: Elevations


def a_subscriber(subscriber_id: str, endpoint: str, *, active: bool = True) -> Subscriber:
    return Subscriber(
        subscriber_id=subscriber_id,
        endpoint=endpoint,
        secret_ref=SecretRef(path="webhooks/signing", role=VaultRole.APPLICATION),
        kinds=(EventKind.APPROVAL_REQUESTED,),
        created_by="u_admin",
        active=active,
    )


@pytest.fixture
def wired() -> Iterator[Wired]:
    """The real application with this router mounted, as `brain.app` mounts it.

    Included here as well, which is `tests/unit/test_session_routes.py`' arrangement, so this file
    tests the router whether or not the line in `brain.app` is in the tree it runs in.
    """
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(routes.router)
    organisation = Organisation()
    review = a_review()
    subscribers = Subscribers(
        (
            a_subscriber("hook_a", "https://hooks.example.test/a"),
            a_subscriber("hook_b", "https://hooks.example.test/a", active=False),
        )
    )
    placements = Placements()
    elevations = Elevations()
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = _wiring()
        app.state.organisation_source = organisation
        app.state.review_store = review
        app.state.subscriber_source = subscribers
        app.state.organisation_records = placements
        app.state.elevation_records = elevations
        yield Wired(client, organisation, review, subscribers, placements, elevations)


def auth(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"}


def get(wired: Wired, path: str, pid: str) -> Response:
    answer: Response = wired.client.get(path, headers=auth(pid))
    return answer


def keys_in(value: Any) -> set[str]:
    """Every key anywhere in a JSON body."""
    if isinstance(value, dict):
        return set(value) | {k for one in value.values() for k in keys_in(one)}
    if isinstance(value, list):
        return {k for one in value for k in keys_in(one)}
    return set()


# ------------------------------------------------------------------ departments


def test_an_administrator_sees_departments_teams_and_people_and_the_three_sentences(
    wired: Wired,
) -> None:
    """M27.7.4, the positive case. Delete this and every refusal below is satisfied by a route
    that answers nothing, and the sentences saying what the install does not record can drop off
    the response while the page draws an empty team as a team nobody is in."""
    answer = get(wired, DEPARTMENTS, "u_admin")

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert [one["slug"] for one in body["departments"]] == ["finance", "web"]
    wei = {"principal_id": "u_2", "display_name": "Wei", "disabled": False}
    grace = {"principal_id": "u_3", "display_name": "Grace", "disabled": True}
    assert body["departments"][1]["teams"] == [
        {"slug": "design", "name": "Design", "members": [grace, wei]}
    ]
    assert body["departments"][1]["members"] == [wei]
    assert body["departments"][1]["lead"] == wei
    assert body["departments"][0]["lead"] == grace
    assert body["unplaced"][0]["principal_id"] == "u_4"
    assert body["may_organise"] is True
    assert body["teams"] == routes.A_TEAM_LISTS_WHO_YOU_MAY_SEE_IN_IT
    assert body["leads"] == routes.A_LEAD_CONFERS_NOTHING
    assert body["counted"] == routes.NOTHING_HERE_IS_COUNTED
    assert not keys_in(body) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT


def test_a_department_reader_is_answered_their_department_and_nobody_elses(wired: Wired) -> None:
    """Delete this and the route hands `organisation` a wider reach, or filters nothing, and a
    web admin reads finance's heading, its teams and its people."""
    body = get(wired, DEPARTMENTS, "u_elsewhere").json()

    assert [one["slug"] for one in body["departments"]] == ["web"]
    assert body["unplaced"] == []
    # Grace is in web's design team and sits in finance: the team lists nobody this reader may not
    # name, and says nothing about the difference.
    assert [one["principal_id"] for one in body["departments"][0]["teams"][0]["members"]] == ["u_2"]


@pytest.mark.parametrize("pid", ["u_none", "u_prefix", "u_narrow"])
def test_the_departments_screen_needs_its_read_on_the_console_plane_before_any_load(
    wired: Wired, pid: str
) -> None:
    """`permitted`, asked before the source. Delete this and a caller with no grant learns this
    process has a database from the difference between a refusal and a fault, or an existence
    plane reader is answered the organisation."""
    answer = get(wired, DEPARTMENTS, pid)

    assert answer.status_code == 404
    assert wired.organisation.calls == []  # type: ignore[attr-defined]


def post(wired: Wired, path: str, pid: str, body: dict[str, Any]) -> Response:
    answer: Response = wired.client.post(path, headers=auth(pid), json=body)
    return answer


def test_an_organiser_places_and_removes_a_member_and_appoints_and_stands_down_a_lead(
    wired: Wired,
) -> None:
    """M27.7.4, the writes. Delete this and every refusal below is satisfied by routes that record
    nothing, or a join can be recorded as a departure, or an appointment written under the wrong
    person, or the actor taken from somewhere other than the token."""
    join = {"department": "web", "team": "design", "principal_id": "u_2", "change": "join"}

    joined = post(wired, MEMBERSHIP, "u_admin", join)
    left = post(wired, MEMBERSHIP, "u_admin", join | {"change": "leave"})
    appointed = post(
        wired,
        LEAD,
        "u_elsewhere",
        {"department": "web", "principal_id": "u_2", "change": "appoint"},
    )
    stood_down = post(wired, LEAD, "u_admin", {"department": "web", "change": "stand_down"})

    assert [one.status_code for one in (joined, left, appointed, stood_down)] == [200] * 4
    assert joined.json()["change"] == "join"
    assert stood_down.json()["principal_id"] is None
    assert wired.placements.written == [
        ("joined", "web", "u_2", "u_admin"),
        ("left", "web", "u_2", "u_admin"),
        ("appointed", "web", "u_2", "u_elsewhere"),
        ("stood_down", "web", "u_2", "u_admin"),
    ]


def test_every_refused_change_to_the_organisation_is_one_refusal(wired: Wired) -> None:
    """`may_place`, `may_appoint` and `may_organise` asked about the rows the store read. Delete
    this and a web organiser places somebody from finance, a disabled person is placed, somebody
    appoints themselves, or a lead from finance is replaced by a web organiser; and any two of
    those answered differently tell a caller who sits where."""
    wired.placements.leads["finance"] = "u_3"
    answers = [
        post(
            wired,
            MEMBERSHIP,
            "u_elsewhere",
            {"department": "web", "team": "design", "principal_id": "u_3", "change": "join"},
        ),
        post(
            wired,
            MEMBERSHIP,
            "u_admin",
            {"department": "web", "team": "design", "principal_id": "u_gone", "change": "join"},
        ),
        post(
            wired,
            LEAD,
            "u_admin",
            {"department": "web", "principal_id": "u_admin", "change": "appoint"},
        ),
        post(
            wired,
            LEAD,
            "u_elsewhere",
            {"department": "finance", "principal_id": "u_2", "change": "appoint"},
        ),
        post(wired, LEAD, "u_elsewhere", {"department": "finance", "change": "stand_down"}),
    ]

    assert [one.status_code for one in answers] == [404] * 5
    assert len({one.json()["message"] for one in answers}) == 1
    assert wired.placements.written == []


def test_a_caller_without_the_authority_never_reaches_the_organisation_store(wired: Wired) -> None:
    """Delete this and a caller holding nothing is refused only after the store is asked, which
    answers a fault on a process with no database and a refusal on one with."""
    join = {"department": "web", "team": "design", "principal_id": "u_2", "change": "join"}

    answers = [
        post(wired, MEMBERSHIP, "u_wide", join),
        post(wired, LEAD, "u_wide", {"department": "web", "change": "stand_down"}),
    ]

    assert [one.status_code for one in answers] == [404, 404]
    assert wired.placements.calls == []


def test_a_change_body_carrying_an_actor_or_the_wrong_shape_is_refused(wired: Wired) -> None:
    """Delete this and a body naming `actor` is accepted and ignored, an appointment of nobody
    reaches the store, or a standing down names a person who may not be the lead."""
    join = {"department": "web", "team": "design", "principal_id": "u_2", "change": "join"}

    answers = [
        post(wired, MEMBERSHIP, "u_admin", join | {"actor": "u_2"}),
        post(wired, MEMBERSHIP, "u_admin", join | {"change": "move"}),
        post(wired, LEAD, "u_admin", {"department": "web", "change": "appoint"}),
        post(
            wired,
            LEAD,
            "u_admin",
            {"department": "web", "principal_id": "u_2", "change": "stand_down"},
        ),
    ]

    assert [one.status_code for one in answers] == [422] * 4
    assert wired.placements.calls == []


# ------------------------------------------------------------------ elevation


def test_every_signed_in_caller_reaches_the_landing_and_nothing_on_it_lists_what_could_be_given(
    wired: Wired,
) -> None:
    """M27.7.8, the landing `brain.console.elevation` decides. Delete this and the landing can be
    closed to the reader holding nothing, who is the one it exists for, or a list of capabilities
    can arrive on it, which is the catalogue handed to somebody with no reach to relabel."""
    nobody = get(wired, ELEVATION, "u_none")
    admin = get(wired, ELEVATION, "u_admin")

    assert nobody.status_code == 200, nobody.text
    body = nobody.json()
    assert body["prompt"] == REQUEST_ADDS_PROMPT
    assert body["holds_nothing_standing"] is False
    assert body["may_authorise"] is False
    assert admin.json()["may_authorise"] is True
    assert body["reasons"] == [one.value for one in BreakGlassReason]
    assert body["longest_hours"] == 4
    assert body["recorded"] == routes.WHAT_IS_RECORDED_ABOUT_AN_ELEVATION
    assert body["requests"] == []
    assert not keys_in(body) & {"capabilities", "grants", "available", "offered", "catalogue"}


def test_a_requester_sees_their_own_requests_and_an_authoriser_those_they_may_decide(
    wired: Wired,
) -> None:
    """`requests_shown` and `state_of`, through the route. Delete this and a web authoriser reads
    who in finance asked for what, a requester reads everybody's, a lapsed elevation reads as live,
    or a request is offered for a decision to somebody who may not make it."""
    soon = datetime.now(UTC) + timedelta(hours=1)
    wired.elevations.stored = [
        a_request("u_2", "web"),
        a_request(
            "u_3", "finance", decision=ElevationDecision.APPROVED, lapses_at=soon, grant_live=True
        ),
        a_request("u_elsewhere", "web", decision=ElevationDecision.APPROVED, lapses_at=LONG_AGO),
    ]

    admin = get(wired, ELEVATION, "u_admin").json()["requests"]
    web = get(wired, ELEVATION, "u_elsewhere").json()["requests"]
    nobody = get(wired, ELEVATION, "u_none").json()["requests"]

    assert [(one["principal_id"], one["state"], one["decidable"]) for one in admin] == [
        ("u_2", ElevationState.PENDING.value, True),
        ("u_3", ElevationState.LIVE.value, False),
        ("u_elsewhere", ElevationState.LAPSED.value, False),
    ]
    assert [(one["principal_id"], one["decidable"]) for one in web] == [
        ("u_2", True),
        ("u_elsewhere", False),
    ]
    assert nobody == []
    assert not keys_in(admin) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT


def test_anybody_may_ask_for_what_they_do_not_hold_and_nobody_for_what_they_do(
    wired: Wired,
) -> None:
    """`would_widen`, before the store. Delete this and somebody holding `read:client.name` asks for
    it again, and an approval narrows them to where both grants reach; or somebody holding nothing
    cannot ask for anything."""
    body = {
        "capability": "read:client.name",
        "scope_slug": "web_all",
        "reason": "incident_response",
        "explanation": "the portal is down",
        "hours": 2,
    }

    filed = post(wired, ELEVATION_REQUESTS, "u_none", body)
    held = post(wired, ELEVATION_REQUESTS, "u_admin", body)
    too_long = post(wired, ELEVATION_REQUESTS, "u_none", body | {"hours": 5})
    forged = post(wired, ELEVATION_REQUESTS, "u_none", body | {"principal_id": "u_admin"})

    assert filed.status_code == 201, filed.text
    assert [one.principal_id for one in wired.elevations.stored] == ["u_none"]
    assert held.status_code == 404
    assert (too_long.status_code, forged.status_code) == (422, 422)
    assert wired.elevations.calls == ["file"]


def decide_request(wired: Wired, pid: str, request: StoredRequest, decision: str) -> Response:
    return post(
        wired,
        f"{ELEVATION_REQUESTS}/{request.request_id}/decision",
        pid,
        {"decision": decision},
    )


def test_an_approval_writes_the_grant_the_request_asked_for_and_a_denial_is_recorded(
    wired: Wired,
) -> None:
    """M27.7.8, the decisions. Delete this and an approval writes a grant for another capability,
    at another scope, with no lapse or a longer one, or in the approver's name; or a denial is not
    recorded against the request it was about."""
    asked = a_request("u_2", "web")
    other = a_request("u_2", "web", capability="read:invoice.total")
    wired.elevations.stored = [asked, other]

    approved = decide_request(wired, "u_admin", asked, "approved")
    denied = decide_request(wired, "u_elsewhere", other, "denied")

    assert approved.status_code == 200, approved.text
    [grant] = wired.elevations.granted
    assert grant.subject == PrincipalSubject(principal_id="u_2")
    assert grant.capability == Capability(value="read:client.name")
    assert grant.scope == Scope.department("web")
    assert grant.granted_by == "u_admin"
    assert grant.not_after == grant.granted_at + timedelta(hours=2)
    assert approved.json()["lapses_at"] is not None
    assert denied.status_code == 200, denied.text
    assert wired.elevations.denied == [(other.request_id, "u_elsewhere")]


def test_every_refused_decision_is_one_refusal(wired: Wired) -> None:
    """`may_approve` and `may_decide` under the store's lock. Delete this and somebody approves
    their own request, a web authoriser decides a finance request, an approver without the
    capability grants it, or a scope nobody registered is granted as unrestricted; and any two of
    those answered differently tell a caller which requests exist."""
    own = a_request("u_admin", "web", capability="read:ticket.status")
    finance = a_request("u_3", "finance")
    uncapable = a_request("u_2", "web", capability="read:ticket.status")
    wired.elevations.stored = [own, finance, uncapable]

    answers = [
        decide_request(wired, "u_admin", own, "approved"),
        decide_request(wired, "u_admin", own, "denied"),
        decide_request(wired, "u_elsewhere", finance, "approved"),
        decide_request(wired, "u_elsewhere", finance, "denied"),
        decide_request(wired, "u_admin", uncapable, "approved"),
    ]
    wired.elevations.scope = None
    answers.append(decide_request(wired, "u_admin", finance, "approved"))

    assert [one.status_code for one in answers] == [404] * 6
    assert len({one.json()["message"] for one in answers}) == 1
    assert wired.elevations.granted == [] and wired.elevations.denied == []


def test_a_caller_without_the_authority_never_reaches_the_elevation_store(wired: Wired) -> None:
    """Delete this and a caller holding nothing is refused only after the store is asked; and a
    decision body with a third word or a decider is accepted."""
    asked = a_request("u_2", "web")
    wired.elevations.stored = [asked]

    refused = decide_request(wired, "u_wide", asked, "approved")
    wired.elevations.calls.clear()
    maybe = decide_request(wired, "u_admin", asked, "maybe")
    forged = post(
        wired,
        f"{ELEVATION_REQUESTS}/{asked.request_id}/decision",
        "u_admin",
        {"decision": "denied", "decided_by": "u_2"},
    )

    assert refused.status_code == 404
    assert (maybe.status_code, forged.status_code) == (422, 422)
    assert wired.elevations.calls == []


# ------------------------------------------------------------------ access review


def test_a_reviewer_is_shown_what_they_could_have_written_with_its_last_decision(
    wired: Wired,
) -> None:
    """M27.7.9, the listing. Delete this and the route lists what it loaded, which shows a reviewer
    a grant they could not have written and widens them by showing; or a lapsed grant is offered
    for a decision that changes nothing; or the last decision drops off the row."""
    kept = a_grant_row("u_2", "read:client.name")
    wired.review.held = [
        GrantHolding(row=kept, display_name="Wei", department="web"),
        GrantHolding(
            row=a_grant_row("u_3", "read:client.name", lapsed=True),
            display_name="Old",
            department="web",
        ),
        a_pack_holding("u_5", "web"),
    ]
    wired.review.decided = {
        kept.id: LastDecision(ReviewDecision.KEEP, decided_by="u_lead", decided_at=LONG_AGO)
    }

    admin = get(wired, REVIEW, "u_admin").json()
    narrow = get(wired, REVIEW, "u_narrow").json()

    assert [(one["kind"], one["principal_id"]) for one in admin["items"]] == [
        ("grant", "u_2"),
        ("pack", "u_5"),
    ]
    assert admin["items"][0]["last_decision"] == "keep"
    assert admin["items"][0]["last_decided_by"] == "u_lead"
    assert admin["items"][1]["capabilities"] == ["read:client.name", "read:invoice.total"]
    assert admin["removing"] == routes.REMOVING_A_GRANT_TAKES_IT_AWAY
    # Holds one of the pack's two capabilities, so the pack is absent rather than half shown.
    assert [one["kind"] for one in narrow["items"]] == ["grant"]
    assert not keys_in(admin) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT


@pytest.mark.parametrize("pid", ["u_none", "u_prefix", "u_wide"])
def test_the_review_needs_its_authority_on_the_console_plane_before_the_store(
    wired: Wired, pid: str
) -> None:
    """Delete this and an existence plane reader holding the authority, or a reader of every other
    Govern screen, is answered the review; and a stranger learns the process has a database."""
    assert get(wired, REVIEW, pid).status_code == 404
    assert wired.review.calls == []


def decide(wired: Wired, pid: str, holding: Holding, decision: str, kind: str = "") -> Response:
    answer: Response = wired.client.post(
        DECISION,
        headers=auth(pid),
        json={
            "kind": kind or ("pack" if isinstance(holding, PackHolding) else "grant"),
            "row_id": str(holding.row.id),
            "decision": decision,
        },
    )
    return answer


def test_a_reviewer_keeps_and_removes_what_they_could_have_written(wired: Wired) -> None:
    """M27.7.9, the write. Delete this and every refusal below is satisfied by a route that
    records nothing, and the decision recorded can be a different word from the one pressed."""
    direct = GrantHolding(
        row=a_grant_row("u_2", "read:client.name"), display_name="W", department="web"
    )
    packed = a_pack_holding("u_5", "web")
    wired.review.held = [direct, packed]

    kept = decide(wired, "u_admin", direct, "keep")
    removed = decide(wired, "u_elsewhere", packed, "remove")

    assert kept.status_code == 200, kept.text
    assert kept.json()["decision"] == "keep"
    assert removed.status_code == 200, removed.text
    assert wired.review.recorded == [
        (direct.row.id, ReviewDecision.KEEP, "u_admin"),
        (packed.row.id, ReviewDecision.REMOVE, "u_elsewhere"),
    ]


def test_a_decision_is_refused_alike_out_of_reach_not_held_own_or_the_wrong_kind(
    wired: Wired,
) -> None:
    """`govern.certify` under the lock, for every grant a holding confers. Delete this and a web
    reviewer decides a finance grant, a reviewer holding one of a pack's capabilities removes the
    whole pack, somebody renews their own grant, or a grant id posted as a pack is decided; and any
    two of those answered differently tell a caller which grants exist."""
    finance = GrantHolding(
        row=a_grant_row("u_3", "read:client.name"), display_name="G", department="finance"
    )
    packed = a_pack_holding("u_5", "web")
    own = GrantHolding(
        row=a_grant_row("u_admin", "read:client.name"), display_name="A", department="web"
    )
    wired.review.held = [finance, packed, own]

    answers = [
        decide(wired, "u_elsewhere", finance, "keep"),
        decide(wired, "u_narrow", packed, "remove"),
        decide(wired, "u_admin", own, "keep"),
        decide(wired, "u_admin", finance, "keep", kind="pack"),
    ]

    assert [one.status_code for one in answers] == [404, 404, 404, 404]
    assert len({one.json()["message"] for one in answers}) == 1
    assert wired.review.recorded == []


def test_a_caller_without_the_review_authority_never_reaches_the_store(wired: Wired) -> None:
    """Delete this and a caller holding nothing is refused only after the store is asked, which
    answers a fault on a process with no database and a refusal on one with."""
    wired.review.held = [
        GrantHolding(row=a_grant_row("u_2", "read:client.name"), display_name="W", department="web")
    ]

    answer = decide(wired, "u_wide", wired.review.held[0], "keep")

    assert answer.status_code == 404
    assert wired.review.calls == []


def test_a_decision_body_carrying_a_decider_or_a_third_word_is_refused(wired: Wired) -> None:
    """Delete this and a body naming `decided_by` is accepted and ignored, or `defer` becomes a
    decision every row acquires in the last week of a round."""
    holding = GrantHolding(
        row=a_grant_row("u_2", "read:client.name"), display_name="W", department="web"
    )
    wired.review.held = [holding]
    body = {"kind": "grant", "row_id": str(holding.row.id), "decision": "keep"}

    forged = wired.client.post(DECISION, headers=auth("u_admin"), json=body | {"decided_by": "x"})
    deferred = wired.client.post(
        DECISION, headers=auth("u_admin"), json=body | {"decision": "defer"}
    )

    assert forged.status_code == 422
    assert deferred.status_code == 422
    assert wired.review.recorded == []


# ------------------------------------------------------------------ subscribers


def test_a_manager_sees_who_is_told_what_with_no_vault_path_and_the_findings(wired: Wired) -> None:
    """M27.7.12, the listing. Delete this and the route drops `subscriber_lines`, putting the vault
    path on the page, or loses the finding that two subscribers share one endpoint."""
    body = get(wired, SUBSCRIBERS, "u_admin").json()

    assert [one["subscriber_id"] for one in body["items"]] == ["hook_a", "hook_b"]
    assert body["items"][0]["last_delivered_at"] is not None
    assert body["items"][1]["active"] is False
    assert body["findings"] != []
    assert body["kinds"] == [one.value for one in EventKind]
    assert body["stopping"] == routes.HOW_TO_STOP_BEING_TOLD
    assert "Webhooks screen" in body["stopping"] and "Notifications" in body["stopping"]
    assert "webhooks/signing" not in str(body)
    assert not keys_in(body) & {"secret_ref", "secret_path", "path"}


def test_a_reader_who_may_not_manage_is_answered_what_an_empty_install_is_and_nothing_is_loaded(
    wired: Wired,
) -> None:
    """`A_READER_WHO_MAY_NOT_MANAGE_IS_SHOWN_WHAT_AN_EMPTY_INSTALL_SHOWS`. Delete this and a
    non-manager reads the map of where the company's identifiers go, or is refused, which says
    there are subscribers to refuse; and the answer differs with whether a database is there."""
    body = get(wired, SUBSCRIBERS, "u_wide").json()

    assert body == routes._empty_subscribers().model_dump(mode="json")
    assert wired.subscribers.calls == []  # type: ignore[attr-defined]


def test_every_route_here_refuses_a_request_with_no_credential(wired: Wired) -> None:
    """Delete this and a route can be mounted without `Asked`, answering anybody."""
    for path in (DEPARTMENTS, ELEVATION, REVIEW, SUBSCRIBERS):
        assert wired.client.get(path).status_code == 401, path
    for path in (
        DECISION,
        MEMBERSHIP,
        LEAD,
        ELEVATION_REQUESTS,
        f"{ELEVATION_REQUESTS}/x/decision",
    ):
        assert wired.client.post(path, json={}).status_code == 401, path


# ------------------------------------------------------------------ paging, search and filter


def listed(wired: Wired, path: str, pid: str, **params: str) -> dict[str, Any]:
    answer: Response = wired.client.get(path, headers=auth(pid), params=params)
    assert answer.status_code == 200, answer.text
    body: dict[str, Any] = answer.json()
    return body


def test_a_search_for_a_person_finds_the_department_they_are_shown_under_and_no_other(
    wired: Wired,
) -> None:
    """Delete this and the departments search can read the loaded organisation, so a web reader who
    types a finance person's name is answered the web department because that person sits in its
    team, which is the membership `organisation` withheld. The positive half is the administrator,
    who may name Grace, finding both departments she appears under."""
    web_reader = listed(wired, DEPARTMENTS, "u_elsewhere", q="grace")
    admin = listed(wired, DEPARTMENTS, "u_admin", q="grace")
    by_team = listed(wired, DEPARTMENTS, "u_admin", filter="teams:Design")

    assert web_reader["departments"] == []
    assert [one["slug"] for one in admin["departments"]] == ["finance", "web"]
    assert [one["slug"] for one in by_team["departments"]] == ["web"]


def test_the_departments_page_one_at_a_time_and_the_unplaced_arrive_only_with_the_first(
    wired: Wired,
) -> None:
    """Delete this and walking the departments repeats the people nobody has placed on every page,
    or drops them, or the unplaced ignore the search and a search for one department still lists
    everybody unplaced. See `THE_UNPLACED_ARRIVE_WITH_THE_FIRST_PAGE`."""
    first = listed(wired, DEPARTMENTS, "u_admin", limit="1")
    second = listed(wired, DEPARTMENTS, "u_admin", limit="1", cursor=first["next_cursor"])
    searched = listed(wired, DEPARTMENTS, "u_admin", q="finance")

    assert [one["slug"] for one in first["departments"]] == ["finance"]
    assert [one["principal_id"] for one in first["unplaced"]] == ["u_4"]
    assert [one["slug"] for one in second["departments"]] == ["web"]
    assert second["unplaced"] == []
    assert second["next_cursor"] is None
    assert searched["unplaced"] == []
    assert wired.organisation.calls == [routes.MAX_ROWS] * 3  # type: ignore[attr-defined]


def test_elevation_requests_filter_by_state_and_page_inside_what_the_reader_is_shown(
    wired: Wired,
) -> None:
    """Delete this and a filter on the requests can reach one `requests_shown` withheld, so a web
    authoriser filtering by a finance person's id is told whether that person asked, or a walk
    repeats a request at a page boundary. The positive half is the administrator's walk."""
    soon = datetime.now(UTC) + timedelta(hours=1)
    wired.elevations.stored = [
        a_request("u_2", "web"),
        a_request(
            "u_3", "finance", decision=ElevationDecision.APPROVED, lapses_at=soon, grant_live=True
        ),
        a_request("u_elsewhere", "web", decision=ElevationDecision.APPROVED, lapses_at=LONG_AGO),
    ]

    withheld = listed(wired, ELEVATION, "u_elsewhere", filter="principal_id:u_3")
    shown = listed(wired, ELEVATION, "u_admin", filter="principal_id:u_3")
    pending = listed(wired, ELEVATION, "u_admin", filter="state:pending")
    first = listed(wired, ELEVATION, "u_admin", limit="2", sort="display_name")
    rest = listed(
        wired, ELEVATION, "u_admin", limit="2", sort="display_name", cursor=first["next_cursor"]
    )

    assert withheld["requests"] == [] and withheld["next_cursor"] is None
    assert [one["principal_id"] for one in shown["requests"]] == ["u_3"]
    assert [one["principal_id"] for one in pending["requests"]] == ["u_2"]
    walked = [one["principal_id"] for one in (*first["requests"], *rest["requests"])]
    assert walked == ["u_2", "u_3", "u_elsewhere"]
    assert rest["next_cursor"] is None


def test_the_access_review_searches_the_capabilities_a_row_shows_and_refuses_an_undeclared_filter(
    wired: Wired,
) -> None:
    """Delete this and the review search can match a pack's capability on a row the reviewer is not
    shown, or a filter on a column no row carries is accepted and ignored, which draws every
    holding as a match."""
    wired.review.held = [
        GrantHolding(
            row=a_grant_row("u_2", "read:client.name"), display_name="W", department="web"
        ),
        a_pack_holding("u_5", "web"),
    ]

    admin = listed(wired, REVIEW, "u_admin", q="invoice")
    narrow = listed(wired, REVIEW, "u_narrow", q="invoice")
    undeclared = wired.client.get(REVIEW, headers=auth("u_admin"), params={"filter": "scope:web"})

    assert [one["principal_id"] for one in admin["items"]] == ["u_5"]
    assert narrow["items"] == []
    assert undeclared.status_code == 422


# ------------------------------------------------------------------ several review decisions


def test_several_holdings_are_decided_one_at_a_time_each_by_the_single_decisions_question(
    wired: Wired,
) -> None:
    """Delete this and a bulk decision can be decided for the set, so a web reviewer keeps a finance
    grant by listing it beside a web one; or a holding out of reach is answered differently from one
    that does not exist, which makes the bulk control a way of asking which grants exist. The
    positive half is the web holding decided, recorded under the reviewer's name."""
    web = a_pack_holding("u_5", "web")
    finance = GrantHolding(
        row=a_grant_row("u_3", "read:client.name"), display_name="G", department="finance"
    )
    wired.review.held = [web, finance]
    missing = uuid.uuid5(uuid.NAMESPACE_URL, "nobody")

    answer = post(
        wired,
        DECISIONS,
        "u_elsewhere",
        {
            "decision": "keep",
            "holdings": [
                {"kind": "pack", "row_id": str(web.row.id)},
                {"kind": "grant", "row_id": str(finance.row.id)},
                {"kind": "grant", "row_id": str(missing)},
            ],
        },
    )

    assert answer.status_code == 200, answer.text
    outcomes = answer.json()["outcomes"]
    assert [one["decided"] for one in outcomes] == [True, False, False]
    assert outcomes[0]["principal_id"] == "u_5"
    assert {k: v for k, v in outcomes[1].items() if k != "row_id"} == {
        k: v for k, v in outcomes[2].items() if k != "row_id"
    }
    assert wired.review.recorded == [(web.row.id, ReviewDecision.KEEP, "u_elsewhere")]
    assert wired.review.calls == ["decide", "decide", "decide"]


def test_a_caller_without_the_review_authority_is_refused_the_bulk_decision_before_the_store(
    wired: Wired,
) -> None:
    """Delete this and the bulk route reaches the store for a reader holding no authority, or
    refuses them in words the single decision does not use, which says the two are guarded apart.
    An empty list and a third word are refused by the declaration."""
    holding = GrantHolding(
        row=a_grant_row("u_2", "read:client.name"), display_name="W", department="web"
    )
    wired.review.held = [holding]
    named = [{"kind": "grant", "row_id": str(holding.row.id)}]

    several = post(wired, DECISIONS, "u_wide", {"decision": "keep", "holdings": named})
    single = decide(wired, "u_wide", holding, "keep")
    empty = post(wired, DECISIONS, "u_admin", {"decision": "keep", "holdings": []})
    deferred = post(wired, DECISIONS, "u_admin", {"decision": "defer", "holdings": named})

    assert several.status_code == single.status_code == 404
    assert several.json()["message"] == single.json()["message"]
    assert empty.status_code == deferred.status_code == 422
    assert wired.review.calls == []
    assert not keys_in(several.json()) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
