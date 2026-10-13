"""The address Keycloak posts a returned Lark code to: answered only where Lark is brokered,
translating one exchange and one read, and saying one fixed word where anything is refused.

Lark is a recorded stand-in here: its answers are the documented shapes and no socket is opened.

Task ids: M1.1.8
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from brain.connectors.staff_directories import Answer, DirectorySignInError, Outbound
from brain.lark_sign_in_routes import (
    MAX_EXCHANGES_PER_MINUTE,
    forget_recent_requests,
    router,
)

CLIENT = "cli_a1b2c3d4e5f6"
SECRET = "CANARY-LARK-SECRET-7QX2M"
CODE = "CANARY-LARK-CODE-3KD8W"
RETURN = "https://id.northwind.example/realms/brain/broker/lark/endpoint"
LARK_SAID = "NORTHWIND-PAYROLL-APP refused Ada"
TOKEN_URL = "https://open.larksuite.com/open-apis/authen/v2/oauth/token"
USER_URL = "https://open.larksuite.com/open-apis/authen/v1/user_info"

SETTINGS = {
    "INSTALL_BROKERED_DIRECTORY": "lark",
    "INSTALL_BROKERED_CLIENT_ID": CLIENT,
    "INSTALL_STAFF_SOURCE": "lark",
    "INSTALL_STAFF_SOURCE_LOCATION": "larksuite.com",
    "INSTALL_OIDC_REDIRECT_URIS": "https://brain.northwind.example/auth/callback",
}


class Lark:
    """What Lark answers, recorded, and every request it was handed."""

    def __init__(self, *, exchange: Answer | None = None, person: Answer | None = None) -> None:
        self.asked: list[Outbound] = []
        self.exchange = exchange or Answer(
            status=200, body={"code": 0, "access_token": "u-token-1", "expires_in": 7200}
        )
        self.person = person or Answer(
            status=200,
            body={
                "code": 0,
                "data": {
                    "name": "Ada Example",
                    "union_id": "on_0001",
                    "enterprise_email": "ada@northwind.example",
                },
            },
        )

    async def __call__(self, outbound: Outbound) -> Answer:
        self.asked.append(outbound)
        if outbound.url == TOKEN_URL:
            return self.exchange
        if outbound.url == USER_URL:
            return self.person
        raise AssertionError(f"the bridge asked an address it was never meant to: {outbound.url}")


def posted(client: TestClient, **change: str) -> Any:
    body = {
        "grant_type": "authorization_code",
        "client_id": CLIENT,
        "client_secret": SECRET,
        "code": CODE,
        "redirect_uri": RETURN,
        **change,
    }
    return client.post(
        "/lark-sign-in/token",
        content=urlencode(body),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def app_with(lark: Lark) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.staff_directory_fetch = lark
    return app


@pytest.fixture
def brokering_lark(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in ("BRAIN_DATABASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in SETTINGS.items():
        monkeypatch.setenv(name, value)
    forget_recent_requests()
    yield
    forget_recent_requests()


def payload_of(token: str) -> dict[str, Any]:
    segment = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))  # type: ignore[no-any-return]


@pytest.mark.usefixtures("brokering_lark")
def test_a_returned_code_is_answered_as_a_standard_token_endpoint_would() -> None:
    """The positive case. Delete this and a bridge that refuses everything passes every refusal
    test below, and Keycloak's broker is handed nothing it can read."""
    lark = Lark()
    answer = posted(TestClient(app_with(lark)))

    assert answer.status_code == 200 and answer.headers["cache-control"] == "no-store"
    body = answer.json()
    assert body["token_type"] == "Bearer" and body["access_token"] == "u-token-1"
    claims = payload_of(body["id_token"])
    assert (claims["sub"], claims["email"], claims["aud"]) == (
        "on_0001",
        "ada@northwind.example",
        CLIENT,
    )
    assert claims["iss"] == "https://brain.northwind.example/lark-sign-in"
    # Two calls, to Lark's own host, and the second carries the token the first bought.
    assert [one.url for one in lark.asked] == [TOKEN_URL, USER_URL]
    assert lark.asked[0].json_body is not None and lark.asked[0].json_body["code"] == CODE
    assert lark.asked[1].headers["Authorization"] == "Bearer u-token-1"


@pytest.mark.usefixtures("brokering_lark")
def test_the_secret_and_the_code_are_in_no_response_and_no_log_line() -> None:
    """`THE_APPLICATION_KEY_IS_FORWARDED_AND_NEVER_KEPT`. Delete this and a log line or an error
    body can carry the application's secret or a code Lark issued, which are one request from a
    sign-in as somebody else."""
    with capture_logs() as logged:
        for lark in (
            Lark(),
            Lark(exchange=Answer(status=400, body={"code": 20024, "msg": LARK_SAID})),
            Lark(person=Answer(status=200, body={"code": 0, "data": {"union_id": "on_1"}})),
        ):
            answer = posted(TestClient(app_with(lark)))
            assert SECRET not in answer.text and CODE not in answer.text
            assert LARK_SAID not in answer.text
    assert logged and all(SECRET not in repr(one) and CODE not in repr(one) for one in logged)
    assert all(LARK_SAID not in repr(one) for one in logged)


@pytest.mark.usefixtures("brokering_lark")
@pytest.mark.parametrize(
    ("lark", "word"),
    [
        (
            Lark(exchange=Answer(status=400, body={"code": 20024, "msg": LARK_SAID})),
            "invalid_grant",
        ),
        (Lark(exchange=Answer(status=200, body={"code": 0})), "invalid_grant"),
        (
            Lark(person=Answer(status=200, body={"code": 0, "data": {"union_id": "on_1"}})),
            "access_denied",
        ),
        (Lark(person=Answer(status=401, body={"code": 99991663})), "invalid_token"),
    ],
)
def test_a_refused_exchange_or_a_person_with_no_address_is_one_fixed_word(
    lark: Lark, word: str
) -> None:
    """The refusals Keycloak reads. Delete this and a refusal can be a 200 Keycloak reads as a
    sign-in, or can say what Lark said."""
    answer = posted(TestClient(app_with(lark)))

    assert answer.status_code == 400 and answer.json() == {"error": word}


@pytest.mark.usefixtures("brokering_lark")
@pytest.mark.parametrize(
    "change",
    [
        {"client_id": "cli_other"},
        {"grant_type": "client_credentials"},
        {"code": ""},
        {"client_secret": ""},
        {"redirect_uri": "https://id.northwind.example/realms/brain/account"},
    ],
)
def test_a_request_that_is_not_keycloaks_for_this_application_reaches_lark_not_at_all(
    change: dict[str, str],
) -> None:
    """Delete this and the bridge is an open relay: anyone can have it ask Lark in this install's
    name, for another application or another return address."""
    lark = Lark()
    answer = posted(TestClient(app_with(lark)), **change)

    assert answer.status_code == 400 and answer.json() == {"error": "invalid_request"}
    assert lark.asked == []


@pytest.mark.usefixtures("brokering_lark")
def test_a_body_that_is_not_a_form_or_is_too_large_is_refused_unread_by_lark() -> None:
    """Delete this and a megabyte, or bytes that are not a form, are parsed and forwarded."""
    lark = Lark()
    client = TestClient(app_with(lark))

    huge = client.post("/lark-sign-in/token", content=b"a=" + b"x" * 20_000)
    assert huge.status_code == 400 and huge.json() == {"error": "invalid_request"}
    binary = client.post("/lark-sign-in/token", content=b"\xff\xfe\xfd")
    assert binary.status_code == 400
    assert lark.asked == []


@pytest.mark.usefixtures("brokering_lark")
def test_a_lark_that_cannot_be_reached_is_told_to_try_again_and_nothing_else() -> None:
    """Delete this and an unreachable Lark is a stack trace, which names a host and may carry the
    request."""

    async def down(outbound: Outbound) -> Answer:
        raise DirectorySignInError("This server could not reach open.larksuite.com.")

    app = FastAPI()
    app.include_router(router)
    app.state.staff_directory_fetch = down
    answer = posted(TestClient(app))

    assert answer.status_code == 502 and answer.json() == {"error": "temporarily_unavailable"}


@pytest.mark.usefixtures("brokering_lark")
def test_the_bridge_is_capped_by_the_minute_and_the_cap_is_a_503_not_a_wrong_answer() -> None:
    """`MAX_EXCHANGES_PER_MINUTE`. Delete this and a flood posts as many calls at Lark, in this
    install's name, as the network carries."""
    lark = Lark()
    client = TestClient(app_with(lark))

    answers = [posted(client).status_code for _ in range(MAX_EXCHANGES_PER_MINUTE + 3)]

    assert answers[:MAX_EXCHANGES_PER_MINUTE] == [200] * MAX_EXCHANGES_PER_MINUTE
    assert answers[MAX_EXCHANGES_PER_MINUTE:] == [503, 503, 503]


@pytest.mark.parametrize(
    "change",
    [
        {"INSTALL_BROKERED_DIRECTORY": "none"},
        {"INSTALL_BROKERED_DIRECTORY": "google"},
        {"INSTALL_BROKERED_CLIENT_ID": "unset"},
        {"INSTALL_STAFF_SOURCE": "google_workspace"},
        {"INSTALL_STAFF_SOURCE_LOCATION": "northwind.example"},
    ],
)
def test_an_install_that_does_not_broker_lark_has_nothing_at_the_address(
    monkeypatch: pytest.MonkeyPatch, change: dict[str, str]
) -> None:
    """`AN_INSTALL_THAT_DOES_NOT_BROKER_LARK_HAS_NOTHING_AT_THIS_ADDRESS`. Delete this and the
    bridge answers on every install, which makes a feature that ships off an open endpoint."""
    for name in ("BRAIN_DATABASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in {**SETTINGS, **change}.items():
        monkeypatch.setenv(name, value)
    forget_recent_requests()
    lark = Lark()
    answer = posted(TestClient(app_with(lark)))

    assert answer.status_code == 404 and answer.json() == {"error": "not_found"}
    assert lark.asked == []


def test_the_bridge_is_outside_the_api_prefix_and_out_of_the_public_schema() -> None:
    """The API prefix authenticates every caller but two written exceptions, and this is a third
    kind of caller. Delete this and the bridge can move under the prefix, where the rule that
    every route there is signed in refuses Keycloak, or into the public schema."""
    from brain.api import API_PREFIX

    app = app_with(Lark())
    paths = [getattr(route, "path", "") for route in router.routes]

    assert paths == ["/lark-sign-in/token"]
    assert not any(one.startswith(API_PREFIX) for one in paths)
    assert "/lark-sign-in/token" not in app.openapi()["paths"]
