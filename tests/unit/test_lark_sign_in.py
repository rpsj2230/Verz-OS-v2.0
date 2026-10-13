"""Lark's sign-in said in the words Keycloak's broker reads, and every refusal one fixed word.

Task ids: M1.1.8
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from brain.connectors.staff_directories import Answer
from brain.identity.lark_sign_in import (
    CODE_GRANT,
    INVALID_BEARER,
    INVALID_GRANT,
    INVALID_REQUEST,
    UNAUTHORISED_PERSON,
    Claims,
    Grant,
    LarkSignInError,
    authorize_base,
    claims_from,
    exchange_request,
    grant_from,
    id_token_for,
    platform_of,
    profile_request,
)

#: Made-up values on a reserved documentation domain. The secret is improbable on purpose: if it
#: appears in a repr, a message or a body, it leaked.
CLIENT = "cli_a1b2c3d4e5f6"
SECRET = "CANARY-LARK-SECRET-7QX2M"
RETURN = "https://id.northwind.example/realms/brain/broker/lark/endpoint"


def form(**change: str) -> dict[str, str]:
    base = {
        "grant_type": CODE_GRANT,
        "client_id": CLIENT,
        "client_secret": SECRET,
        "code": "code-123",
        "redirect_uri": RETURN,
    }
    return {**base, **change}


def refused(call: Any) -> str:
    with pytest.raises(LarkSignInError) as caught:
        call()
    assert str(caught.value) == caught.value.word
    return str(caught.value.word)


def person(**change: object) -> Answer:
    data = {
        "name": "Ada Example",
        "union_id": "on_0001",
        "open_id": "ou_0001",
        "enterprise_email": "Ada@Northwind.example",
        "email": "ada.personal@northwind.example",
        "tenant_key": "tenant-1",
    }
    return Answer(status=200, body={"code": 0, "msg": "success", "data": {**data, **change}})


def test_the_exchange_is_lark_s_own_json_to_the_platforms_host_with_the_keys_forwarded() -> None:
    """The positive case. Delete this and an `exchange_request` that refuses everything passes
    every refusal test below, and nobody ever signs in."""
    sent = exchange_request("larksuite.com", form=form(), client_id=CLIENT)

    assert (sent.method, sent.url) == (
        "POST",
        "https://open.larksuite.com/open-apis/authen/v2/oauth/token",
    )
    assert sent.form is None and sent.json_body == {
        "grant_type": CODE_GRANT,
        "client_id": CLIENT,
        "client_secret": SECRET,
        "code": "code-123",
        "redirect_uri": RETURN,
    }
    assert exchange_request("feishu.cn", form=form(), client_id=CLIENT).url.startswith(
        "https://open.feishu.cn/"
    )


def test_the_application_s_secret_is_in_the_body_and_in_no_representation_of_the_request() -> None:
    """`THE_APPLICATION_KEY_IS_FORWARDED_AND_NEVER_KEPT`. Delete this and a traceback holding the
    request writes the secret to a log."""
    sent = exchange_request("larksuite.com", form=form(), client_id=CLIENT)

    assert SECRET not in repr(sent) and SECRET not in str(sent)
    assert SECRET not in repr(Grant(access_token=SECRET, expires_in=60))


@pytest.mark.parametrize(
    "change",
    [
        {"grant_type": "password"},
        {"client_id": "cli_other"},
        {"client_id": ""},
        {"code": ""},
        {"code": "x" * 2001},
        {"client_secret": ""},
        {"client_secret": "x" * 501},
        {"redirect_uri": "https://id.northwind.example/realms/brain/broker/google/endpoint"},
        {"redirect_uri": "https://id.northwind.example/elsewhere"},
        {"redirect_uri": RETURN + "?next=https://evil.example"},
        {"redirect_uri": "ftp://id.northwind.example/realms/brain/broker/lark/endpoint"},
        {"redirect_uri": "/realms/brain/broker/lark/endpoint"},
    ],
)
def test_an_exchange_that_is_not_keycloak_s_for_this_application_is_refused_unsent(
    change: dict[str, str],
) -> None:
    """Delete this and the bridge can be used to redeem a code for another application, for
    another return address, or with a shape Lark was never meant to be handed."""
    assert refused(
        lambda: exchange_request("larksuite.com", form=form(**change), client_id=CLIENT)
    ) == (INVALID_REQUEST)


@pytest.mark.parametrize(
    "location", ["", "unset", "northwind.example", "larksuite.com.evil.example"]
)
def test_a_location_that_is_not_one_of_larks_two_platforms_is_refused(location: str) -> None:
    """The location decides which host the secret is sent to. Delete this and a typo in a setting
    sends the application's secret to whoever owns the typo."""
    assert refused(lambda: platform_of(location)) == INVALID_REQUEST
    assert refused(lambda: exchange_request(location, form=form(), client_id=CLIENT)) == (
        INVALID_REQUEST
    )
    assert refused(lambda: profile_request(location, "u-token")) == INVALID_REQUEST
    assert refused(lambda: authorize_base(location)) == INVALID_REQUEST
    assert authorize_base("feishu.cn") == "https://accounts.feishu.cn/open-apis/authen/v1/authorize"


def test_a_grant_is_larks_token_and_a_refusal_is_one_word_naming_nothing_lark_said() -> None:
    """Delete this and a refused exchange passes Lark's own text on, which may name a person or
    an application, or a refusal inside a 200 is read as a token."""
    grant = grant_from(
        Answer(status=200, body={"code": 0, "access_token": " u-abc ", "expires_in": 7200})
    )
    assert grant.access_token == "u-abc" and 0 < grant.expires_in <= 600
    short = grant_from(
        Answer(status=200, body={"code": 0, "access_token": "u-abc", "expires_in": 120})
    )
    assert short.expires_in == 120

    said = "app NORTHWIND-PAYROLL is not allowed to sign Ada in"
    for answer in (
        Answer(status=400, body={"code": 20024, "msg": said}),
        Answer(status=200, body={"code": 20024, "msg": said}),
        Answer(status=200, body={"code": 0}),
        Answer(status=200, body={"code": 0, "access_token": ""}),
        Answer(status=200, body={"code": 0, "access_token": 5}),
    ):
        word = refused(lambda answer=answer: grant_from(answer))
        assert word == INVALID_GRANT and "NORTHWIND" not in word


def test_the_person_is_read_with_the_token_in_a_header_and_never_in_the_address() -> None:
    """Delete this and the token can be put in a query string, which every proxy in front of
    Lark writes to its log."""
    asked = profile_request("larksuite.com", " u-abc ")

    assert (asked.method, asked.url) == (
        "GET",
        "https://open.larksuite.com/open-apis/authen/v1/user_info",
    )
    assert asked.headers["Authorization"] == "Bearer u-abc" and "u-abc" not in asked.url
    assert refused(lambda: profile_request("larksuite.com", " ")) == INVALID_BEARER
    assert refused(lambda: profile_request("larksuite.com", "x" * 2001)) == INVALID_BEARER


def test_a_person_is_their_union_id_and_the_address_the_staff_sync_joins_on() -> None:
    """The positive case, and the join. Delete this and the address Keycloak is told can differ
    from the one the account was made with, so the link finds nobody."""
    claims = claims_from(person())
    assert claims == Claims(sub="on_0001", email="ada@northwind.example", name="Ada Example")

    # Lark Mail's address wins where there is one, and the account's own address otherwise: the
    # staff sync's rule, which is `brain.identity.staff_adapters.lark_work_address`.
    plain = claims_from(person(enterprise_email=""))
    assert plain.email == "ada.personal@northwind.example"
    # `open_id` is per application and is used only where Lark gave no `union_id`.
    assert claims_from(person(union_id="")).sub == "ou_0001"
    assert claims_from(person(name="")).name == "ada@northwind.example"


@pytest.mark.parametrize(
    ("answer", "word"),
    [
        (person(enterprise_email="", email=""), UNAUTHORISED_PERSON),
        (person(enterprise_email="", email="not-an-address"), UNAUTHORISED_PERSON),
        (person(enterprise_email="@northwind.example"), UNAUTHORISED_PERSON),
        (person(union_id="", open_id=""), INVALID_BEARER),
        (
            Answer(status=401, body={"code": 99991663, "msg": "invalid access token"}),
            INVALID_BEARER,
        ),
        (Answer(status=200, body={"code": 99991663}), INVALID_BEARER),
        (Answer(status=200, body={"code": 0}), INVALID_BEARER),
        (Answer(status=200, body={"code": 0, "data": "ada"}), INVALID_BEARER),
    ],
)
def test_a_person_with_no_address_or_no_identifier_or_no_answer_is_refused_by_one_word(
    answer: Answer, word: str
) -> None:
    """`A_PERSON_WITH_NO_ADDRESS_IS_NOT_SIGNED_IN`. Delete this and a person Lark gives no address
    for is signed in as an account with nothing to find it by."""
    assert refused(lambda: claims_from(answer)) == word


def test_the_token_response_carries_an_unsigned_identity_proof_for_this_client_alone() -> None:
    """What Keycloak's broker reads. Delete this and the response can lack the ID token the
    broker requires, name another audience, or outlive the grant it was made from."""
    claims = Claims(sub="on_0001", email="ada@northwind.example", name="Ada Example")
    answered = id_token_for(
        claims,
        Grant(access_token="u-abc", expires_in=300),
        client_id=CLIENT,
        issuer="https://brain.northwind.example/lark-sign-in",
        now_seconds=4_000_000_000,
    )

    assert answered["access_token"] == "u-abc" and answered["token_type"] == "Bearer"
    header, payload, signature = str(answered["id_token"]).split(".")
    assert signature == ""

    def read(segment: str) -> dict[str, Any]:
        padded = segment + "=" * (-len(segment) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))  # type: ignore[no-any-return]

    assert read(header) == {"alg": "none", "typ": "JWT"}
    assert read(payload) == {
        "iss": "https://brain.northwind.example/lark-sign-in",
        "sub": "on_0001",
        "aud": CLIENT,
        "iat": 4_000_000_000,
        "exp": 4_000_000_300,
        "email": "ada@northwind.example",
        "email_verified": True,
        "preferred_username": "ada@northwind.example",
        "name": "Ada Example",
    }
