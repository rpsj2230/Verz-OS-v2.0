"""Consenting to a source at its vendor from the console: who may start it, and what an answer buys.

Driven through the real application with the token machinery, the in-memory connections and the
vault `tests/unit/test_connector_routes.py` uses, so the authority, the 404 and the vault's states
are the router's own. The consents are `Consents`, in memory and keeping the store's contract (a
state taken once, by its own person, before it expires); the database half is
`tests/unit/test_connector_consent.py`. The vendor is a recorded token endpoint. Every refusal has a
sibling that starts or keeps a consent, and no secret reaches a body or a log line.

Task ids: M11.8.6
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.connector_routes import (
    CONNECTORS_PATH,
    CONSENT_CALLBACK_PATH,
    CONSENT_KEPT,
    CONSENT_PATH,
    CONSENTING_AT_THE_VENDOR,
    ConsentExchange,
)
from brain.connectors.contract import HealthState
from brain.connectors.declaration import shipped
from brain.connectors.oauth import CONSENT_WITHDRAWN, ConsentStart
from brain.ops.acceptance_checks_oauth import AUTHORIZE_URL, consented_xero
from brain.ops.connector_consent import CONSENT_LIFETIME, LatestAttempt, TakenConsent
from brain.ops.connector_sync import Attempt
from brain.ops.credentials import KEY_FIELD, connector_key_slot, connector_oauth_slot
from brain.ops.openbao import StaticVersion
from tests.fixtures.http_client import Response
from tests.unit.test_connector_routes import (
    NoDatabase,
    Records,
    _wiring,
    a_connection,
    attach,
    headers,
)
from tests.unit.test_credentials import AT, Recorded, Vault
from tests.unit.test_oauth_renewal import (
    CLIENT,
    SECRET,
    SETTINGS,
    Endpoint,
    Keys,
    Resolver,
    issued,
)

BACK: Final = "https://console.example/connector-consent"
NEW_REFRESH: Final = "REFRESH-FROM-CONSENT-9e31"


@dataclass
class Consents:
    """`ConsentStates` in memory: a state taken once, by its own person, before it expires."""

    held: dict[str, tuple[str, str, ConsentStart, str, datetime]] = field(default_factory=dict)
    issued: list[tuple[str, str]] = field(default_factory=list)

    async def issue(
        self,
        *,
        connector: str,
        principal_id: str,
        start: ConsentStart,
        return_address: str,
        now: datetime,
    ) -> None:
        self.issued.append((connector, principal_id))
        self.held[start.state] = (
            connector,
            principal_id,
            start,
            return_address,
            now + CONSENT_LIFETIME,
        )

    async def take(self, *, state: str, principal_id: str, now: datetime) -> TakenConsent | None:
        found = self.held.get(state)
        if found is None or found[1] != principal_id or now >= found[4]:
            return None
        del self.held[state]
        return TakenConsent(connector=found[0], return_address=found[3], start=found[2])


@dataclass
class Health:
    """`ConsentHealth` over one live connection with no attempt yet, noting what was appended."""

    connection_id: uuid.UUID = field(default_factory=uuid.uuid4)
    appended: list[Attempt] = field(default_factory=list)

    async def latest(self, connector: str) -> LatestAttempt | None:
        return LatestAttempt(self.connection_id, None) if connector == "xero" else None

    async def record(self, connection_id: uuid.UUID, attempt: Attempt) -> None:
        assert connection_id == self.connection_id
        self.appended.append(attempt)


@dataclass
class Rig:
    consents: Consents
    vault: Vault
    writes: Recorded
    endpoint: Endpoint
    health: Health


@pytest.fixture
def app() -> Iterator[FastAPI]:
    from brain.app import Settings, create_app

    built: FastAPI = create_app(Settings(env="development"))
    yield built


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = NoDatabase()
        yield c


def rig(app: FastAPI, *, answer: Any = None, secret_kept: bool = True) -> Rig:
    """A connected Xero consented to by OAuth, its client secret kept, and a vendor answering."""
    declared, _ = consented_xero()
    app.state.connector_declarations = {"xero": declared}
    consents, writes = Consents(), Recorded()
    vault = Vault(version=StaticVersion(written_at=AT) if secret_kept else None)
    attach(app, Records((a_connection("xero", settings=SETTINGS),)), vault, writes)
    endpoint, health = Endpoint(answer or issued(refresh=NEW_REFRESH)), Health()
    keys = Keys(slots={connector_key_slot("xero").path: SECRET})
    app.state.oauth_consents = consents
    app.state.consent_exchange = ConsentExchange(
        keys=keys, poster=endpoint, resolver=Resolver(), health=health
    )
    return Rig(consents=consents, vault=vault, writes=writes, endpoint=endpoint, health=health)


def start(c: TestClient, pid: str, connector: str = "xero", back: str = BACK) -> Response:
    path = API_PREFIX + CONSENT_PATH.replace("{connector}", connector)
    response: Response = c.post(path, headers=headers(pid), json={"return_address": back})
    return response


def answer(c: TestClient, pid: str, **query: str) -> Response:
    response: Response = c.get(
        API_PREFIX + CONSENT_CALLBACK_PATH, headers=headers(pid), params=query
    )
    return response


def started(c: TestClient, pid: str = "u_narrow") -> tuple[str, dict[str, str]]:
    """Start a consent and read the vendor's page it answers: the state, and what was asked."""
    sent = start(c, pid)
    assert sent.status_code == 200, sent.text
    address = sent.json()["address"]
    asked = {key: values[0] for key, values in parse_qs(urlsplit(address).query).items()}
    return asked["state"], asked


# ------------------------------------------------------------------ starting a consent
def test_a_consent_is_started_for_a_connected_source_and_answers_the_vendor_s_own_page(
    app: FastAPI, client: TestClient
) -> None:
    """A person who may connect the source is answered the vendor's consent page, asking with the
    connection's client id, an S256 challenge, the scopes the source declares and the console's
    page to come back to, and the consent is held for them. Delete this and the start route can
    answer an address the vendor refuses, or hold the consent for nobody."""
    held = rig(app)
    state, asked = started(client)
    assert asked["client_id"] == CLIENT and asked["redirect_uri"] == BACK
    assert asked["code_challenge_method"] == "S256" and asked["response_type"] == "code"
    assert start(client, "u_narrow").json()["address"].startswith(f"{AUTHORIZE_URL}?")
    assert held.consents.issued[0] == ("xero", "u_narrow") and state in held.consents.held


def test_a_caller_who_may_not_connect_the_source_starts_nothing_and_is_told_nothing(
    app: FastAPI, client: TestClient
) -> None:
    """A reader of the screen without the authority to connect the source, and somebody holding
    nothing, are refused in the router's one way and no consent is held. The sibling above starts
    one. Delete this and anybody who can sign in can send the vendor a consent for this install."""
    held = rig(app)
    for pid in ("u_wide", "u_none"):
        refused = start(client, pid)
        assert refused.status_code == 404
    assert not held.consents.issued


def test_a_source_that_cannot_be_consented_to_now_is_told_why_and_nothing_is_held(
    app: FastAPI, client: TestClient
) -> None:
    """A source not consented to by OAuth, one whose client secret is not kept, and a return
    address that is not the console's consent page each answer 422 with a problem naming its
    field, and no consent is held. The sibling above starts one. Delete this and a consent can be
    started whose code nothing could exchange."""
    rig(app, secret_kept=False)
    assert start(client, "u_admin").json()["problems"][0]["code"] == "no_secret"
    held = rig(app)
    assert (
        start(client, "u_admin", back="https://elsewhere.example/x").json()["problems"][0]["field"]
        == "return_address"
    )
    app.state.connector_declarations = shipped()
    assert start(client, "u_admin").json()["problems"][0]["code"] == "not_oauth"
    assert not held.consents.issued


# ------------------------------------------------------------------ the vendor's answer
def test_the_vendor_s_code_is_exchanged_and_its_refresh_token_kept_in_its_slot_once(
    app: FastAPI, client: TestClient
) -> None:
    """The callback takes the person's own consent, exchanges the code with the verifier its state
    sealed and the client secret, keeps the refresh token in its own slot through the credential
    store, which records the write, and sends the person on to the source's page. The same state a
    second time is refused. Delete this and a consent never reaches the vault, or reaches it
    twice."""
    held = rig(app)
    state, asked = started(client)
    done = answer(client, "u_narrow", state=state, code="CODE-1")
    assert done.status_code == 200, done.text
    assert done.json() == {
        "connector": "xero",
        "kept": True,
        "told": CONSENT_KEPT,
        "back_to": "/connectors/xero",
    }
    (form,) = held.endpoint.forms
    assert form["grant_type"] == "authorization_code" and form["code"] == "CODE-1"
    assert form["client_secret"] == SECRET and form["redirect_uri"] == BACK
    assert form["code_verifier"] and asked["code_challenge"] != form["code_verifier"]
    slot = connector_oauth_slot("xero").path
    assert held.vault.written == [(slot, {KEY_FIELD: NEW_REFRESH})]
    assert [one["slot"] for one in held.writes.records] == [slot]
    assert answer(client, "u_narrow", state=state, code="CODE-1").status_code == 404
    assert len(held.endpoint.forms) == 1


def test_a_state_nobody_issued_and_somebody_else_s_answer_are_refused_alike(
    app: FastAPI, client: TestClient
) -> None:
    """An unknown state and the right state answered by somebody else are the same 404, nothing
    is posted to the vendor, and the person who started the consent can still answer it. Delete
    this and a code can be attached to a consent somebody else started, or the refusal tells which
    states exist."""
    held = rig(app)
    state, _ = started(client)
    unknown = answer(client, "u_narrow", state="X" * 43, code="CODE-1")
    stolen = answer(client, "u_admin", state=state, code="CODE-1")
    assert unknown.status_code == stolen.status_code == 404
    assert unknown.json()["message"] == stolen.json()["message"]
    assert not held.endpoint.forms
    assert answer(client, "u_narrow", state=state, code="CODE-1").json()["kept"] is True


@pytest.mark.parametrize("refusal", ["at_the_page", "at_the_code"])
def test_a_consent_the_vendor_refused_marks_the_source_down_and_keeps_nothing(
    app: FastAPI, client: TestClient, refusal: str
) -> None:
    """A person who declined on the vendor's page, and a code the vendor refused to exchange, are
    the consent withdrawn: said in `CONSENT_WITHDRAWN`'s words, marked on the source's health, and
    nothing kept. The sibling above keeps a consent. Delete this and a refused consent leaves the
    source looking connected."""
    refused = issued() if refusal == "at_the_page" else None
    held = rig(app, answer=refused)
    if refused is None:
        from brain.ops.connector_sync_run import SourceAnswer

        held.endpoint.answer = SourceAnswer(
            status=400, headers={}, body=b'{"error":"invalid_grant"}'
        )
    state, _ = started(client)
    query = {"state": state, "code": "CODE-1"}
    if refusal == "at_the_page":
        query = {"state": state, "error": "access_denied"}
    done = answer(client, "u_narrow", **query)
    assert done.status_code == 200
    assert done.json()["kept"] is False and done.json()["told"] == CONSENT_WITHDRAWN
    assert [(one.health, one.detail) for one in held.health.appended] == [
        (HealthState.DOWN, CONSENT_WITHDRAWN)
    ]
    assert not held.vault.written


def test_no_secret_reaches_a_body_or_a_log_line(app: FastAPI, client: TestClient) -> None:
    """The client secret, the code, the refresh token and the verifier reach no response and no
    log line on either route. Delete this and a debugging log of the exchange ships with them."""
    rig(app)
    with structlog.testing.capture_logs() as logs:
        state, _ = started(client)
        done = answer(client, "u_narrow", state=state, code="CODE-SECRET-77")
    said = json.dumps(logs) + done.text + start(client, "u_narrow").text
    for secret in (SECRET, NEW_REFRESH, "CODE-SECRET-77"):
        assert secret not in said


def test_a_source_that_declares_a_consent_is_offered_connect_with_its_vendor(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Connectors screen serves `consent_with` for a source consented to by OAuth, with what
    consenting agrees to, and empty for every other; no source this release ships declares one.
    Delete this and the console's "Connect with" step has nothing to draw from."""
    import dataclasses

    import brain.connector_routes as connector_routes
    from brain.ops.connectable import CONNECTABLE

    rig(app)
    listing = client.get(API_PREFIX + CONNECTORS_PATH, headers=headers("u_admin")).json()
    assert {one["consent_with"] for one in listing["connectable"]} == {""}
    declared, _ = consented_xero()
    patched = {
        **CONNECTABLE,
        "xero": dataclasses.replace(CONNECTABLE["xero"], oauth=declared.oauth),
    }
    monkeypatch.setattr(connector_routes, "CONNECTABLE", patched)
    listing = client.get(API_PREFIX + CONNECTORS_PATH, headers=headers("u_admin")).json()
    offered = {one["name"]: one for one in listing["connectable"]}
    assert offered["xero"]["consent_with"] == "Xero"
    assert offered["xero"]["consent_told"] == CONSENTING_AT_THE_VENDOR
