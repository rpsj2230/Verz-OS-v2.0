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

Task ids: M27.7.4, M27.7.8, M27.7.9, M27.7.12
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import govern_people_routes as routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.elevation import ALREADY_HOLDS_PROMPT
from brain.console.organisation import Department, Member, Team
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.review_store import (
    Decided,
    GrantHolding,
    Holding,
    LastDecision,
    PackHolding,
    StoredReview,
)
from brain.identity.bearer import TokenAuthority
from brain.identity.roles import BreakGlassReason
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.ops.outbox import EventKind, Subscriber
from brain.ops.replica_store import Served
from brain.ops.secrets import SecretRef, VaultRole
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
ELEVATION = f"{API_PREFIX}/govern/elevation"
REVIEW = f"{API_PREFIX}/govern/access-review"
DECISION = f"{API_PREFIX}/govern/access-review/decision"
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
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = _wiring()
        app.state.organisation_source = organisation
        app.state.review_store = review
        app.state.subscriber_source = subscribers
        yield Wired(client, organisation, review, subscribers)


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
    assert body["departments"][1]["teams"] == [{"slug": "design", "name": "Design"}]
    assert body["departments"][1]["members"] == [
        {"principal_id": "u_2", "display_name": "Wei", "disabled": False}
    ]
    assert body["unplaced"][0]["principal_id"] == "u_4"
    assert body["teams"] == routes.WHO_IS_IN_A_TEAM_IS_NOT_RECORDED
    assert body["leads"] == routes.NO_DEPARTMENT_LEAD_IS_RECORDED
    assert body["counted"] == routes.NOTHING_HERE_IS_COUNTED
    assert not keys_in(body) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT


def test_a_department_reader_is_answered_their_department_and_nobody_elses(wired: Wired) -> None:
    """Delete this and the route hands `organisation` a wider reach, or filters nothing, and a
    web admin reads finance's heading, its teams and its people."""
    body = get(wired, DEPARTMENTS, "u_elsewhere").json()

    assert [one["slug"] for one in body["departments"]] == ["web"]
    assert body["unplaced"] == []


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
    assert body["prompt"] == ALREADY_HOLDS_PROMPT
    assert body["holds_nothing_standing"] is False
    assert body["may_authorise"] is False
    assert admin.json()["may_authorise"] is True
    assert body["reasons"] == [one.value for one in BreakGlassReason]
    assert body["longest_hours"] == 4
    assert body["recorded"] == routes.NOTHING_STORES_AN_ELEVATION_YET
    assert not keys_in(body) & {"capabilities", "grants", "available", "offered", "catalogue"}


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
    assert body["stopping"] == routes.SWITCHING_A_SUBSCRIBER_OFF_IS_NOT_ON_THIS_SCREEN_YET
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
    assert wired.client.post(DECISION, json={}).status_code == 401
