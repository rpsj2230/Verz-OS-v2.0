"""A member's own accounts page: what a department provided, and disconnecting their own.

Driven through the real application with the rig `tests/unit/test_connector_consent_routes.py`
stands up: a connected source each person consents to for themselves, answering to one department,
and the vault answering a version only for the slots a test holds. So the listing and the refusals
are the router's own. The revoker is a recording stand-in here; the real one, over a fake vendor and
a fake vault, is `tests/unit/test_person_token_revoker.py`, and the install check drives both.

Task ids: M40.5.1.3, M40.5.1.4
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.connector_routes import DEPARTMENT_PROVIDED, MY_ACCOUNTS_PATH
from brain.connectors.declaration import shipped
from brain.member.connections import TokenRevoker
from brain.member_accounts_routes import (
    DISCONNECTED_AND_REVOKED,
    DISCONNECTED_NOT_REVOKED_AT_THE_VENDOR,
    MY_DISCONNECT_PATH,
    NOT_DISCONNECTED,
)
from brain.ops.credentials import connector_person_oauth_slot
from tests.fixtures.http_client import Response
from tests.unit.test_connector_consent_routes import accounts, own_rig
from tests.unit.test_connector_routes import NoDatabase, _wiring, headers


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


@dataclass
class Revoker:
    """A `TokenRevoker` noting what it was asked and answering as told."""

    answer: bool = True
    asked: list[str] = field(default_factory=list)

    def revoke(self, token_ref: str, *, at: datetime) -> bool:
        self.asked.append(token_ref)
        return self.answer


@dataclass
class Factory:
    """`app.state.account_revoker`: who a revoker was made for, and the one it hands back."""

    revoker: Revoker
    made_for: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, connector: str, principal_id: str) -> TokenRevoker:
        self.made_for.append((connector, principal_id))
        return self.revoker


def disconnect(c: TestClient, pid: str, connector: str = "xero") -> Response:
    path = API_PREFIX + MY_DISCONNECT_PATH.replace("{connector}", connector)
    response: Response = c.post(path, headers=headers(pid))
    return response


def hand(app: FastAPI, *, answer: bool = True) -> Factory:
    factory = Factory(Revoker(answer=answer))
    app.state.account_revoker = factory
    return factory


#: A made-up vendor's revocation address, under a name reserved for examples.
REVOKE_ENDPOINT = "https://identity.oauth-vendor.example/connect/revocation"

MINE = connector_person_oauth_slot("xero", "u_none").path


# --------------------------------------------------------------- M40.5.1.4 inherited
def test_a_connection_the_department_made_is_listed_as_inherited_and_offered_no_disconnect(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**M40.5.1.4.** A connected source naming the person's own department, which each person does
    not consent to for themselves, is listed with provenance `department` and nothing to press.
    Delete this and the page keeps listing only what a person attached, so a list of what the
    system reaches on their behalf leaves the department's out, or offers to detach it."""
    own_rig(app, monkeypatch)
    app.state.connector_declarations = {"xero": shipped()["xero"]}

    listed = accounts(client, "u_none").json()["accounts"]

    assert listed == [
        {
            "connector": "xero",
            "label": shipped()["xero"].label,
            "connected": True,
            "told": DEPARTMENT_PROVIDED,
            "provenance": "department",
            "disconnectable": False,
        }
    ]


def test_a_department_connection_is_absent_for_a_person_in_another_department(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal sibling: somebody holding a grant in another department, and somebody holding
    none, are listed nothing, exactly as if no such source were connected. Delete this and a
    department's connection is shown to people outside it, which says what the company reaches."""
    own_rig(app, monkeypatch)
    app.state.connector_declarations = {"xero": shipped()["xero"]}

    for pid in ("u_prefix", "u_wide", "u_admin"):
        assert accounts(client, pid).json()["accounts"] == []


def test_an_account_a_person_attached_is_personal_and_disconnectable_only_when_held(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive sibling: a source each person consents to is `personal`, and offers a disconnect
    exactly when their own token is kept. Delete this and the control appears on an account that
    was never connected, or never on one that was."""
    own_rig(app, monkeypatch, held={MINE})
    [held] = accounts(client, "u_none").json()["accounts"]
    own_rig(app, monkeypatch)
    [not_held] = accounts(client, "u_none").json()["accounts"]

    assert (held["provenance"], held["disconnectable"]) == ("personal", True)
    assert (not_held["provenance"], not_held["disconnectable"]) == ("personal", False)


# ---------------------------------------------------------------- M40.5.1.3 disconnect
def test_a_person_disconnects_their_own_account_and_the_revoker_is_asked_for_their_slot(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**M40.5.1.3.** The route builds the revoker for this person and this source, hands it the
    slot the connection was made with, and says in words that the vendor was asked. Delete this and
    a disconnect can answer success without the revoker being reached."""
    own_rig(app, monkeypatch, held={MINE})
    with_endpoint = app.state.connector_declarations["xero"]
    app.state.connector_declarations = {
        "xero": replace(
            with_endpoint, oauth=replace(with_endpoint.oauth, revoke_url=REVOKE_ENDPOINT)
        )
    }
    made = hand(app)

    response = disconnect(client, "u_none")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "connector": "xero",
        "vendor_revoked": True,
        "told": DISCONNECTED_AND_REVOKED,
    }
    assert made.made_for == [("xero", "u_none")]
    assert made.revoker.asked == [MINE]


def test_a_vendor_with_no_way_to_revoke_is_not_claimed_to_have_revoked(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sibling: a source whose consent declares no revocation endpoint is disconnected here and
    the answer says the vendor was not asked, and tells the person where to finish it. Delete this
    and the page claims a revocation no vendor performed."""
    own_rig(app, monkeypatch, held={MINE})
    hand(app)

    response = disconnect(client, "u_none")

    assert response.json() == {
        "connector": "xero",
        "vendor_revoked": False,
        "told": DISCONNECTED_NOT_REVOKED_AT_THE_VENDOR,
    }


def test_a_revocation_that_fails_is_told_in_one_sentence_and_nothing_else_is_said(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A revoker answering False is a 503 with the fixed sentence, which names no vendor and no
    error. Delete this and a failed revocation reads as a disconnection, the page promising a
    protection nobody provided."""
    own_rig(app, monkeypatch, held={MINE})
    made = hand(app, answer=False)

    response = disconnect(client, "u_none")

    assert response.status_code == 503
    assert response.json()["message"] == NOT_DISCONNECTED
    assert made.revoker.asked == [MINE]


def test_a_person_with_no_account_connected_and_a_colleague_are_refused_alike(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nobody can disconnect an account they never connected, and one person's connection is not
    reachable from another's sign-in: a colleague holding nothing, a person whose own slot is not
    kept, and a source that does not exist get the one refusal, and no revoker is built. Delete this
    and the route can be used to ask which sources exist or who connected one."""
    own_rig(app, monkeypatch, held={MINE})
    made = hand(app)

    for pid in ("u_prefix", "u_wide", "u_admin"):
        assert disconnect(client, pid).status_code == 404
    assert disconnect(client, "u_none", connector="no_such_source").status_code == 404
    assert made.made_for == []


def test_a_source_each_person_does_not_consent_to_cannot_be_disconnected_from_here(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A department's connection is not the person's to detach: even for somebody who reads it, the
    route is absent and no revoker is built. Delete this and one person's page can revoke a
    credential everyone in the department relies on."""
    own_rig(app, monkeypatch, held={MINE})
    app.state.connector_declarations = {"xero": shipped()["xero"]}
    made = hand(app)

    assert disconnect(client, "u_none").status_code == 404
    assert made.made_for == []


def test_a_source_consented_to_once_for_everybody_cannot_be_disconnected_by_one_person(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source with an OAuth consent that is not a person's own is refused even when the asker's
    slot for that name is held: the kind decides, not the declaration being present. Delete this and
    one person's page can revoke the credential every read of the source uses."""
    from brain.ops.acceptance_checks_oauth import consented_xero

    own_rig(app, monkeypatch, held={MINE})
    app.state.connector_declarations = {"xero": consented_xero()[0]}
    made = hand(app)

    assert disconnect(client, "u_none").status_code == 404
    assert made.made_for == []


def test_a_person_who_has_left_the_department_can_still_take_their_own_token_back(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The undo is not behind the reader capability that attaching needs: `u_prefix` holds it in
    another department now, lists nothing, and can still disconnect the account whose token is
    kept. Delete this and a move strands a token nobody can revoke from the page."""
    away = connector_person_oauth_slot("xero", "u_prefix").path
    own_rig(app, monkeypatch, held={away})
    made = hand(app)

    assert accounts(client, "u_prefix").json()["accounts"] == []
    assert disconnect(client, "u_prefix").status_code == 200
    assert made.revoker.asked == [away]


def test_the_disconnect_is_a_post_the_console_can_label_and_not_a_delete() -> None:
    """The route is registered as a POST to `.../disconnect`. Delete this and a DELETE sneaks in
    that `console/tests/destructive-labels.test.ts` forbids a page from sending."""
    from fastapi.routing import APIRoute

    from brain.member_accounts_routes import router

    methods = {
        (route.path, tuple(sorted(route.methods or ())))
        for route in router.routes
        if isinstance(route, APIRoute) and route.path.endswith("/disconnect")
    }
    assert methods == {(API_PREFIX + MY_ACCOUNTS_PATH + "/{connector}/disconnect", ("POST",))}


def test_a_process_with_nothing_to_revoke_with_says_it_could_not_and_removes_nothing(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no revoker made for this process (no vault able to remove a slot) the answer is the
    fixed sentence and a 503, not an absence and not a success. Delete this and an install whose
    vault cannot remove a slot reports a disconnection, or looks as though the account was never
    there."""
    rig = own_rig(app, monkeypatch, held={MINE})

    response = disconnect(client, "u_none")

    assert response.status_code == 503
    assert response.json()["message"] == NOT_DISCONNECTED
    assert MINE not in getattr(rig.vault, "removed", [])


def test_a_listing_with_no_connections_to_read_lists_no_department_connection(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no connections store on the process the department's list is empty rather than an
    error. Delete this and a process without a database fails the whole accounts page for a
    guard that is one line."""
    own_rig(app, monkeypatch)
    app.state.connector_declarations = {"xero": shipped()["xero"]}
    app.state.connector_records = None
    app.state.db_sessions = None

    assert accounts(client, "u_none").json()["accounts"] == []
