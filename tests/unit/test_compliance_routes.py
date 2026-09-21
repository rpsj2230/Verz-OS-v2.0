"""The Compliance screen's routes, the answer route's interception and the records route's deny.

The routes run in the real application with the real token path, over stores in memory that keep
what they were asked. The breach store in memory moves a case through `checked_move` and reads it
back through `case_from`, which are the database store's own checks, so the clock the routes
answer with is the module's arithmetic. What the database adds (the policies, the triggers, the
ledger entries) is `tests/unit/test_compliance_store.py`'s and `test_decision_entries.py`'s.

Task ids: M24.1.3, M24.2.2, M24.2.3, M24.2.4
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import compliance_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.audit.compliance import (
    REFERRAL_TEXT,
    Awareness,
    InterceptionTally,
    SensitiveTopic,
)
from brain.audit.record import DenyReason
from brain.connectors.xero import CONNECTOR_NAME as XERO
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.ops import sensitive_referral_store
from brain.ops.breach_store import (
    CLOSING_NEEDS_A_MADE_ASSESSMENT,
    Actor,
    BreachRecord,
    BreachRefusedError,
    case_from,
    checked_move,
)
from brain.ops.connector_store import Connection
from brain.ops.denial_store import Denial
from brain.ops.processing_register import THE_COUNTS_ARE_WHAT_WAS_READ, ReadCounts
from brain.ops.sensitive_referral_store import NamedPerson, Referral
from brain.tables.compliance import BreachCaseRow
from brain.tools.startup import build_registry
from tests.unit.test_answer_route import HOURS, OneRow, texts
from tests.unit.test_answer_route import question as ask
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    SOURCE,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
    wiring,
)
from tests.unit.test_session_routes import Directory

#: `u_admin` holds the authority over everything, `u_prefix` only in web, `u_none` nothing.
GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_admin": (
        Grant(capability=compliance_routes.COMPLIANCE_AUTHORITY, scope=Scope.unrestricted()),
    ),
    "u_prefix": (
        Grant(capability=compliance_routes.COMPLIANCE_AUTHORITY, scope=Scope.department("web")),
    ),
    "u_none": (),
}

AWARE = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS.get(principal_id, ()))


@dataclass
class Referrals:
    """`SensitiveReferrals` in memory: named people, referrals, and every call."""

    named_people: dict[SensitiveTopic, str] = field(default_factory=dict)
    filed: list[Referral] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)

    async def refer(
        self, *, asked_by: str, topic: SensitiveTopic, ent_hash: str, trace_id: str
    ) -> str | None:
        self.calls.append("refer")
        routed = self.named_people.get(topic)
        self.filed.append(
            Referral(str(uuid.uuid4()), topic, asked_by, datetime.now(UTC), routed, None, None)
        )
        return routed

    async def named(self) -> Mapping[SensitiveTopic, NamedPerson]:
        self.calls.append("named")
        at = datetime(2026, 9, 2, tzinfo=UTC)
        return {t: NamedPerson(t, p, "u_admin", at) for t, p in self.named_people.items()}

    async def name(
        self, topic: SensitiveTopic, principal_id: str, *, by: str, ent_hash: str, trace_id: str
    ) -> NamedPerson:
        self.calls.append("name")
        self.named_people[topic] = principal_id
        return NamedPerson(topic, principal_id, by, datetime.now(UTC))

    async def mine(self, principal_id: str) -> tuple[Referral, ...]:
        self.calls.append("mine")
        return tuple(
            r
            for r in self.filed
            if r.routed_to == principal_id
            or (r.routed_to is None and self.named_people.get(r.topic) == principal_id)
        )

    async def handle(
        self, referral_id: str, *, by: str, ent_hash: str, trace_id: str, at: datetime
    ) -> bool:
        self.calls.append("handle")
        for i, one in enumerate(self.filed):
            if (
                one.referral_id == referral_id
                and one.handled_at is None
                and one in await self.mine(by)
            ):
                self.filed[i] = Referral(
                    one.referral_id, one.topic, one.asked_by, one.asked_at, by, at, by
                )
                return True
        return False

    async def tally(self, period: str) -> InterceptionTally:
        self.calls.append("tally")
        counts: dict[SensitiveTopic, int] = {}
        for one in self.filed:
            counts[one.topic] = counts.get(one.topic, 0) + 1
        return InterceptionTally(period=period, counts=counts)


@dataclass
class Breaches:
    """`BreachCases` in memory, moving a case through the database store's own checks."""

    rows: dict[str, BreachCaseRow] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    async def open(self, awareness: Awareness, *, actor: Actor) -> BreachRecord:
        self.calls.append("open")
        case_id = uuid.uuid4()
        row = BreachCaseRow(
            case_id=case_id,
            became_aware_at=awareness.became_aware_at,
            awareness_basis=awareness.basis.value,
            awareness_source=awareness.source.value,
            earliest_possible_at=awareness.earliest_possible_at,
            recorded_at=awareness.recorded_at,
            recorded_by=awareness.recorded_by,
            evidence_reference=awareness.evidence_reference,
            updated_by=actor.principal_id,
        )
        self.rows[str(case_id)] = row
        return case_from(row)

    async def cases(self) -> tuple[BreachRecord, ...]:
        self.calls.append("cases")
        return tuple(case_from(row) for row in self.rows.values())

    async def move(self, case_id: str, changes: dict[str, Any], *, actor: Actor) -> BreachRecord:
        self.calls.append("move")
        moved = checked_move(self.rows.get(case_id), changes, by=actor.principal_id)
        # The database store writes only once the checks pass, and so does this one.
        for key, value in {**changes, "updated_by": actor.principal_id}.items():
            setattr(self.rows[case_id], key, value)
        return moved


@dataclass
class Connections:
    found: tuple[Connection, ...] = ()

    async def connected(self) -> tuple[Connection, ...]:
        return self.found

    async def connect(self, **_: Any) -> Any:  # pragma: no cover - not reached here
        raise AssertionError

    async def disconnect(self, **_: Any) -> Any:  # pragma: no cover - not reached here
        raise AssertionError


@dataclass
class Counts:
    found: dict[str, ReadCounts] = field(default_factory=dict)

    async def counts(self) -> Mapping[str, ReadCounts]:
        return self.found


@dataclass
class Denials:
    written: list[Denial] = field(default_factory=list)

    async def denied(self, denial: Denial) -> None:
        self.written.append(denial)


@pytest.fixture
def referrals() -> Referrals:
    return Referrals()


@pytest.fixture
def breaches() -> Breaches:
    return Breaches()


@pytest.fixture
def client(referrals: Referrals, breaches: Breaches) -> Iterator[TestClient]:
    app = create_app(Settings(env="development", database_url=""))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        app.state.sensitive_referrals = referrals
        app.state.breach_cases = breaches
        app.state.connector_records = Connections(
            (
                Connection(
                    connector=XERO,
                    settings={"tenant_id": "9f1c2e7a-0b4d-4c3e-8a21-6d5f3b2c1a0e"},
                    digest="a" * 64,
                    connected_by="u_admin",
                    connected_at=AWARE,
                ),
            )
        )
        app.state.read_counts = Counts(
            {XERO: ReadCounts(records=412, documents=0, finished_at=AWARE)}
        )
        yield c


def auth(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims={'amr': ['otp']})}"}


BREACHES = f"{API_PREFIX}{compliance_routes.BREACHES_PATH}"
TOPICS = f"{API_PREFIX}{compliance_routes.TOPICS_PATH}"
REGISTER = f"{API_PREFIX}{compliance_routes.REGISTER_PATH}"
MINE = f"{API_PREFIX}{compliance_routes.MY_REFERRALS_PATH}"


def opened(client: TestClient) -> dict[str, Any]:
    answer = client.post(
        BREACHES,
        json={
            "became_aware_at": AWARE.isoformat(),
            "basis": "observed",
            "source": "internal_detection",
            "evidence_reference": "alert-4471",
        },
        headers=auth("u_admin"),
    )
    assert answer.status_code == 200, answer.text
    body: dict[str, Any] = answer.json()
    return body


# ------------------------------------------------------------------------ breach cases


def test_a_case_shows_its_clock_from_the_awareness_and_its_findings(
    client: TestClient, breaches: Breaches
) -> None:
    """M24.2.4 end to end over the routes: opened, assessed notifiable, Commission told, closed.
    The clock runs from the awareness, not from when the case was opened, so an assessment due
    thirty days after 1 September is already overdue on the day it is opened in late September.
    Delete this and the screen can key the clock on the filing date, which reports headroom the
    organisation does not have."""
    case = opened(client)
    assess = client.post(
        f"{BREACHES}/{case['case_id']}/assessment",
        json={"significant_harm": True, "rationale_reference": "dpo-note-7", "affected_count": 12},
        headers=auth("u_admin"),
    )
    told = client.post(f"{BREACHES}/{case['case_id']}/commission", json={}, headers=auth("u_admin"))
    closed = client.post(f"{BREACHES}/{case['case_id']}/close", headers=auth("u_admin"))
    listed = client.get(BREACHES, headers=auth("u_admin")).json()["cases"]

    assert case["clock_starts_at"] == AWARE.isoformat().replace("+00:00", "Z")
    due = {o["kind"]: o for o in case["obligations"]}
    assert datetime.fromisoformat(due["assess"]["due_before"]) > AWARE + timedelta(days=30)
    assert assess.status_code == 200 and assess.json()["outcome"] == "notifiable"
    assert told.status_code == 200 and told.json()["commission_notified_at"] is not None
    assert closed.status_code == 200 and closed.json()["closed_by"] == "u_admin"
    assert listed[0]["case_id"] == case["case_id"] and listed[0]["closed_at"] is not None
    assert breaches.calls == ["open", "move", "move", "move", "cases"]


def test_closing_a_case_whose_assessment_is_not_made_is_refused(client: TestClient) -> None:
    """The one refusal the module makes: an assessment nobody made cannot be closed, and an
    undetermined one (no harm, count unknown) has not been made. Delete this and a case can be
    closed with its clock unanswerable. The positive case is the test above."""
    case = opened(client)
    early = client.post(f"{BREACHES}/{case['case_id']}/close", headers=auth("u_admin"))
    client.post(
        f"{BREACHES}/{case['case_id']}/assessment",
        json={"significant_harm": False, "rationale_reference": "dpo-note-8"},
        headers=auth("u_admin"),
    )
    undetermined = client.post(f"{BREACHES}/{case['case_id']}/close", headers=auth("u_admin"))

    for answer in (early, undetermined):
        assert answer.status_code == 404
        assert CLOSING_NEEDS_A_MADE_ASSESSMENT in answer.json()["message"]


def test_a_notification_is_recorded_once_and_never_in_the_future(client: TestClient) -> None:
    """Delete this and a second Commission notification rewrites the first, or a date in the
    future reports an obligation met that has not been."""
    case = opened(client)
    future = client.post(
        f"{BREACHES}/{case['case_id']}/commission",
        json={"at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        headers=auth("u_admin"),
    )
    first = client.post(
        f"{BREACHES}/{case['case_id']}/commission", json={}, headers=auth("u_admin")
    )
    again = client.post(
        f"{BREACHES}/{case['case_id']}/commission", json={}, headers=auth("u_admin")
    )

    assert future.status_code == 404
    assert first.status_code == 200
    assert again.status_code == 404 and "already records" in again.json()["message"]


def test_checked_move_refuses_a_column_the_case_does_not_move_by() -> None:
    """The awareness is fixed at opening. Delete this and a move could rewrite when the
    organisation became aware, which is the one fact every deadline is computed from."""
    row = BreachCaseRow(
        case_id=uuid.uuid4(),
        became_aware_at=AWARE,
        awareness_basis="observed",
        awareness_source="staff_report",
        recorded_at=AWARE,
        recorded_by="u_admin",
        evidence_reference="ticket-1",
        updated_by="u_admin",
    )
    with pytest.raises(BreachRefusedError, match="does not move by"):
        checked_move(row, {"became_aware_at": AWARE + timedelta(days=9)}, by="u_admin")
    with pytest.raises(BreachRefusedError, match="not open"):
        checked_move(None, {"closed_at": AWARE}, by="u_admin")


# -------------------------------------------------------------------- the authority


@pytest.mark.parametrize("pid", ["u_none", "u_prefix"])
def test_every_compliance_route_refuses_a_caller_without_the_authority_before_any_store(
    client: TestClient, referrals: Referrals, breaches: Breaches, pid: str
) -> None:
    """`admin:compliance` over everything, asked first. A department's grant of it is not enough,
    because a breach case and the register are the whole company's. Delete this and a caller
    holding nothing reads every case, names who receives whistleblowing referrals, or reaches a
    store before being refused."""
    case_id = uuid.uuid4()
    answers = [
        client.get(TOPICS, headers=auth(pid)),
        client.put(f"{TOPICS}/legal", json={"principal_id": "u_x"}, headers=auth(pid)),
        client.get(REGISTER, headers=auth(pid)),
        client.get(BREACHES, headers=auth(pid)),
        client.post(BREACHES, json={}, headers=auth(pid)),
        client.post(f"{BREACHES}/{case_id}/close", headers=auth(pid)),
    ]

    assert [a.status_code for a in answers[:4]] == [404] * 4
    assert answers[5].status_code == 404
    assert referrals.calls == [] and breaches.calls == []


# ------------------------------------------------------------------ sensitive topics


def test_a_sensitive_question_is_routed_to_the_person_named_for_its_topic(
    referrals: Referrals,
) -> None:
    """M24.2.2 over the real answer route: a legal question is referred before the lane reads
    anything, routed to the person named for legal matters, and the asker reads the one referral
    sentence. Delete this and the interception can be correct and uncalled again, which is how it
    stood until 2026-09-21."""
    rows = OneRow()
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring()
        app.state.tools = build_registry(source=SOURCE, records=rows)
        app.state.fast_path_rules = (HOURS,)
        referrals.named_people[SensitiveTopic.LEGAL] = "u_counsel"
        app.state.sensitive_referrals = referrals
        answered = ask(c, "can I sue the company over my contract")
        ordinary = ask(c, "what is the price of WEB-1001")

    assert answered.status_code == 200
    assert texts(answered) == [REFERRAL_TEXT]
    [filed] = referrals.filed
    assert (filed.topic, filed.asked_by, filed.routed_to) == (
        SensitiveTopic.LEGAL,
        "u_wide",
        "u_counsel",
    )
    assert texts(ordinary) and texts(ordinary) != [REFERRAL_TEXT]
    assert referrals.calls == ["refer"]


def test_the_referral_is_the_same_sentence_for_every_topic(referrals: Referrals) -> None:
    """The person differs by topic and the sentence must not, or the transcript names the topic.
    Delete this and a per-topic reply can come back one helpful edit at a time."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring()
        app.state.tools = build_registry(source=SOURCE, records=OneRow())
        app.state.sensitive_referrals = referrals
        replies = {
            tuple(texts(ask(c, q)))
            for q in ("is this harassment", "can I sue them", "what is my salary this month")
        }

    assert replies == {(REFERRAL_TEXT,)}
    assert {one.topic for one in referrals.filed} == {
        SensitiveTopic.HARASSMENT,
        SensitiveTopic.LEGAL,
        SensitiveTopic.SALARY,
    }


def test_naming_a_person_and_reading_the_topics(client: TestClient, referrals: Referrals) -> None:
    """The positive case for the refusals above: the authority names the person for a topic and
    sees every topic with who it goes to. Delete this and a route that refuses everybody passes."""
    named = client.put(
        f"{TOPICS}/whistleblowing", json={"principal_id": "u_ethics"}, headers=auth("u_admin")
    )
    shown = client.get(TOPICS, headers=auth("u_admin")).json()

    assert named.status_code == 200 and named.json()["principal_id"] == "u_ethics"
    by_topic = {one["topic"]: one["named"] for one in shown["topics"]}
    assert set(by_topic) == {t.value for t in SensitiveTopic}
    assert by_topic["whistleblowing"]["principal_id"] == "u_ethics"
    assert by_topic["legal"] is None
    assert shown["referral"] == REFERRAL_TEXT
    assert shown["tally"]["suppressed"] is True and shown["tally"]["total"] is None


def test_an_unknown_topic_is_refused_like_a_missing_authority(client: TestClient) -> None:
    """Delete this and a key outside the topics could be written into `ops.setting`."""
    answer = client.put(f"{TOPICS}/gossip", json={"principal_id": "u_x"}, headers=auth("u_admin"))

    assert answer.status_code == 404


def test_a_referral_marked_handled_is_shown_handled(
    client: TestClient, referrals: Referrals
) -> None:
    """The named person's list over `/me/referrals`, with no capability: they see what was routed
    to them and mark it handled; somebody else sees nothing and cannot handle it. Delete this and
    the person the owner named has no way to see what was sent to them."""
    asyncio.run(
        referrals.refer(asked_by="u_asker", topic=SensitiveTopic.MEDICAL, ent_hash="", trace_id="t")
    )
    referrals.named_people[SensitiveTopic.MEDICAL] = "u_none"
    [one] = client.get(MINE, headers=auth("u_none")).json()["referrals"]
    stranger = client.post(f"{MINE}/{one['referral_id']}/handled", headers=auth("u_prefix"))
    done = client.post(f"{MINE}/{one['referral_id']}/handled", headers=auth("u_none"))

    assert one["topic"] == "medical" and one["asked_by"] == "u_asker" and one["handled_at"] is None
    assert set(one) == {
        "referral_id",
        "topic",
        "label",
        "asked_by",
        "asked_at",
        "handled_at",
        "handled_by",
    }
    assert stranger.status_code == 404
    assert done.status_code == 200
    assert done.json()["referrals"][0]["handled_by"] == "u_none"


def test_the_referral_store_has_no_parameter_a_question_could_arrive_through() -> None:
    """`THE_QUESTION_HAS_NO_WAY_IN`, read off the signatures. Delete this and a `question` or
    `text` parameter added for the follow-up puts the content in the one table built to omit it."""
    for owner in (
        sensitive_referral_store.SensitiveReferrals,
        sensitive_referral_store.StoredSensitiveReferrals,
    ):
        for name, method in inspect.getmembers(owner, inspect.isfunction):
            params = set(inspect.signature(method).parameters)
            assert not params & {"question", "text", "content", "message", "body"}, name


# --------------------------------------------------------------- processing register


def test_the_register_lists_what_each_connector_reads_with_its_categories_and_counts(
    client: TestClient,
) -> None:
    """M24.2.3: a connected source's row says which entities it reads and in which tier, the
    sensitivity classes of their fields, and what the last run read. Delete this and the register
    can list a connector with nothing about what it touches, which is the question a regulator
    asks first."""
    answer = client.get(REGISTER, headers=auth("u_admin"))

    assert answer.status_code == 200, answer.text
    [row] = answer.json()["connectors"]
    assert row["connector"] == XERO and row["problem"] == ""
    assert row["entities"], "a connected source reads something"
    assert {e["tier"] for e in row["entities"]} <= {"federated", "projected"}
    assert set(row["categories"]) >= {e["tier"] for e in row["entities"]}
    assert (row["records_read"], row["documents_read"]) == (412, 0)
    assert answer.json()["counts"] == THE_COUNTS_ARE_WHAT_WAS_READ


def test_a_connection_that_no_longer_builds_is_listed_with_its_reason(client: TestClient) -> None:
    """A register is judged by its gaps. Delete this and a connection whose settings no longer
    build is dropped from the list, which is the gap nobody sees."""
    client.app.state.connector_records = Connections(  # type: ignore[attr-defined]
        (Connection("retired_source", {}, "a" * 64, "u_admin", AWARE),)
    )
    [row] = client.get(REGISTER, headers=auth("u_admin")).json()["connectors"]

    assert row["connector"] == "retired_source" and row["entities"] == []
    assert row["problem"] and row["records_read"] is None


# ----------------------------------------------------------------- the records deny


def test_a_records_refusal_for_a_served_entity_is_a_deny_and_an_unknown_one_is_not() -> None:
    """M24.1.3's deny at its real decision point: a caller holding no grant over an entity this
    install serves is refused with the one 404, and the refusal is written as a `no_grant` deny
    naming the entity and the capability. An entity nobody serves is an absence and writes none.
    Both answers are identical. Delete this and a deny is never recorded on a running install,
    which is what the tracker audit found."""
    denials = Denials()
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = wiring()
        app.state.tools = build_registry(source=SOURCE, records=OneRow())
        app.state.denials = denials
        headers = {"authorization": f"Bearer {token_for('u_none')}"}
        refused = c.get(f"{API_PREFIX}/records/price_list", headers=headers)
        unknown = c.get(f"{API_PREFIX}/records/no_such_entity", headers=headers)
        reached = c.get(
            f"{API_PREFIX}/records/price_list",
            headers={"authorization": f"Bearer {token_for('u_wide')}"},
        )

    assert refused.status_code == unknown.status_code == 404
    assert reached.status_code == 200
    assert refused.json()["message"] == unknown.json()["message"]
    assert set(refused.json()) == set(unknown.json())
    [written] = denials.written
    assert (written.actor_id, written.subject, written.reason) == (
        "u_none",
        "entity:price_list",
        DenyReason.NO_GRANT,
    )
    assert written.capability == Capability(value="read:price_list")
