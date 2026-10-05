"""A connected Google source's key file, exchanged for a token as itself, with a read-only scope.

`brain.connectors.google_token` is the exchange Google Analytics and Search Console share, and
`brain.ops.connector_sync_run` is where it is sent: `presented` decides whether a reading's key is
exchanged, `mint_token` posts the assertion to Google's own address, and `authorization` refuses to
build a Google source's header from anything but the token. The keys are generated here, the key
file is written in the shape Google documents, and nothing is sent anywhere: the poster records.

Task ids: M11.7.1
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final
from urllib.parse import parse_qs

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from brain.connectors.contract import ConnectorContractError
from brain.connectors.declaration import KeyScheme
from brain.connectors.google_analytics import SCOPE, AnalyticsReading
from brain.connectors.google_service_account import JWT_BEARER
from brain.connectors.google_token import (
    A_CONNECTED_GOOGLE_SOURCE_READS_AS_ITS_SERVICE_ACCOUNT,
    A_KEY_FILE_IS_NEVER_SENT_IN_A_HEADER,
    GOOGLE_TOKEN_URL,
    ONLY_A_READ_ONLY_SCOPE_IS_EVER_ASKED_FOR,
    AccessToken,
    TokenNotIssuedError,
    checked_scopes,
    exchange,
    token_from,
)
from brain.connectors.throttle import CallOutcome
from brain.ops.connector_sync_run import SourceAnswer, authorization, mint_token, presented
from brain.tools.fetch import UnsafeAddressError
from tests.unit.test_google_service_account import ACCOUNT, key_file, unpadded

#: Far outside any plausible wall clock, so the assertion's times are a value and not a clock.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)

#: A global unicast address in a block nobody was handed, which the address rule admits.
PUBLIC: Final = "2000::1"

#: What Google answers a good assertion with, in its documented shape.
ISSUED: Final = SourceAnswer(
    status=200,
    headers={},
    body=json.dumps(
        {"access_token": "ya29.a-token", "expires_in": 3599, "token_type": "Bearer"}
    ).encode("utf-8"),
)


@pytest.fixture(scope="module")
def key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class Resolver:
    def __init__(self, address: str = PUBLIC) -> None:
        self.address = address

    def resolve(self, host: str) -> list[str]:
        del host
        return [self.address]


@dataclass
class Poster:
    """`SourcePoster` answering every post with one answer and noting what it was sent."""

    answer: SourceAnswer = ISSUED
    posts: list[tuple[str, str, dict[str, str], bytes]] = field(default_factory=list)

    def post(
        self,
        url: str,
        *,
        address: str,
        headers: Mapping[str, str],
        body: bytes,
        max_bytes: int,
    ) -> SourceAnswer:
        del max_bytes
        self.posts.append((url, address, dict(headers), body))
        return self.answer


def claims_of(form: bytes) -> tuple[dict[str, list[str]], dict[str, Any], str, str]:
    """The form's fields, the assertion's claims, and the signed input and signature."""
    fields = parse_qs(form.decode("ascii"))
    header, claims, signature = fields["assertion"][0].split(".")
    return fields, json.loads(unpadded(claims)), f"{header}.{claims}", signature


# --------------------------------------------------------------------- the exchange
def test_a_key_file_is_exchanged_as_the_account_itself_with_its_read_only_scope(
    key: rsa.RSAPrivateKey,
) -> None:
    """The positive case, checked by the key: the form is the JWT bearer grant, the claim set is
    issued by the key file's account for the one read-only scope and names **no subject**, it is
    addressed to Google's own token endpoint, and the signature verifies under the file's key.

    Delete this and the exchange could act as a person in the domain, which only delegation
    permits, or sign for a scope nobody asked for, with nothing failing until Google refuses."""
    asked = exchange(key_file(key), (SCOPE,), now=int(NOW.timestamp()))

    fields, claims, signed, signature = claims_of(asked.body)
    assert asked.url == GOOGLE_TOKEN_URL == "https://oauth2.googleapis.com/token"
    assert fields["grant_type"] == [JWT_BEARER]
    assert claims["iss"] == ACCOUNT
    assert claims["scope"] == SCOPE
    assert claims["aud"] == GOOGLE_TOKEN_URL
    assert "sub" not in claims
    assert "alone" in A_CONNECTED_GOOGLE_SOURCE_READS_AS_ITS_SERVICE_ACCOUNT
    key.public_key().verify(
        unpadded(signature), signed.encode("ascii"), padding.PKCS1v15(), hashes.SHA256()
    )


def test_a_file_s_own_token_address_is_never_where_the_assertion_goes(
    key: rsa.RSAPrivateKey,
) -> None:
    """The key file used here names `tokens.example.invalid` as its `token_uri`; the exchange is
    addressed to Google's constant whatever the file says.

    Delete this and a pasted file could choose where a signature made with the company's key is
    sent."""
    assert "tokens.example.invalid" in key_file(key)
    assert exchange(key_file(key), (SCOPE,), now=0).url == GOOGLE_TOKEN_URL


@pytest.mark.parametrize(
    "scope",
    [
        "https://www.googleapis.com/auth/analytics.edit",
        "https://www.googleapis.com/auth/analytics",
        "https://www.googleapis.com/auth/webmasters",
        "https://tokens.example.invalid/auth/analytics.readonly",
        "analytics.readonly",
    ],
)
def test_a_scope_that_is_not_google_s_read_only_form_is_refused_before_anything_is_signed(
    key: rsa.RSAPrivateKey, scope: str
) -> None:
    """`ONLY_A_READ_ONLY_SCOPE_IS_EVER_ASKED_FOR`, with its sibling: the two read-only scopes the
    Google sources ask for pass.

    Delete this and a declaration edited to ask for `analytics.edit` mints a token that can change
    the property, with the account's grant the only thing in the way."""
    with pytest.raises(ConnectorContractError, match="read-only"):
        exchange(key_file(key), (SCOPE, scope), now=0)
    with pytest.raises(ConnectorContractError):
        checked_scopes(())
    assert checked_scopes((SCOPE, "https://www.googleapis.com/auth/webmasters.readonly")) == (
        SCOPE,
        "https://www.googleapis.com/auth/webmasters.readonly",
    )
    assert "read-only" in ONLY_A_READ_ONLY_SCOPE_IS_EVER_ASKED_FOR


def test_a_file_that_is_not_a_service_account_s_key_is_a_refusal_and_repeats_nothing() -> None:
    """A key file that does not parse is the key being declined, which is what Google would do,
    and the refusal carries no part of what was given.

    Delete this and a bad key file would surface as a crash in the worker, with its text in the
    trace."""
    given = '{"type": "authorized_user", "private_key": "PRIVATE-SENTINEL"}'
    with pytest.raises(TokenNotIssuedError) as refused:
        exchange(given, (SCOPE,), now=0)
    assert refused.value.call is CallOutcome.REJECTED
    assert "SENTINEL" not in str(refused.value)


# ------------------------------------------------------------------ what Google answers
def test_google_s_answer_is_read_into_a_token_whose_value_no_representation_shows() -> None:
    """The positive case of the answer, and the value kept out of `repr` and `str`, because a
    token in a traceback is a credential in a log.

    Delete this and the token could be printed by whatever logs the object holding it."""
    token = token_from(status=ISSUED.status, body=ISSUED.body)

    assert token.value == "ya29.a-token"
    assert "ya29" not in repr(token) and "ya29" not in str(token)


@pytest.mark.parametrize(
    ("status", "body", "call"),
    [
        (400, {"error": "invalid_grant"}, CallOutcome.REJECTED),
        (401, {"error": "invalid_client"}, CallOutcome.REJECTED),
        (429, {"error": "rate_limit_exceeded"}, CallOutcome.QUOTA),
        (503, {}, CallOutcome.UNAVAILABLE),
        (200, {"access_token": "ya29.x", "token_type": "mac"}, CallOutcome.UNAVAILABLE),
        (200, {"token_type": "Bearer"}, CallOutcome.UNAVAILABLE),
        (200, {"access_token": "two words", "token_type": "Bearer"}, CallOutcome.UNAVAILABLE),
        (200, ["not", "an", "object"], CallOutcome.UNAVAILABLE),
    ],
)
def test_an_answer_that_is_not_a_bearer_token_is_the_kind_of_failure_it_was(
    status: int, body: Any, call: CallOutcome
) -> None:
    """A declined key is a refusal, a spent allowance is a quota, and an answer in any other shape
    is a source that did not answer in a shape this reads, never a token.

    Delete this and an answer carrying no token could be sent on as `Bearer None`."""
    with pytest.raises(TokenNotIssuedError) as refused:
        token_from(status=status, body=json.dumps(body).encode("utf-8"))
    assert refused.value.call is call


def test_an_answer_that_never_came_is_unavailable_and_says_it_timed_out() -> None:
    """A timeout is the endpoint's ill health, and the flag is carried so the run's sentence says
    it did not answer in time.

    Delete this and a slow token endpoint reads as a declined key."""
    with pytest.raises(TokenNotIssuedError) as refused:
        token_from(status=None, body=b"", timed_out=True)
    assert (refused.value.call, refused.value.timed_out) == (CallOutcome.UNAVAILABLE, True)


# ------------------------------------------------------------------ where it is sent
def test_a_google_reading_s_key_is_posted_to_google_and_presented_as_the_token_it_bought(
    key: rsa.RSAPrivateKey,
) -> None:
    """`presented` over a Google reading: one post, to Google's constant at the address the rule
    checked, and the token it bought is what `authorization` sends.

    Delete this and the worker could send the key file itself, or post the assertion somewhere
    the address rule never saw."""
    poster = Poster()

    shown = presented(
        AnalyticsReading(), key_file(key), poster=poster, resolver=Resolver(), now=NOW
    )

    assert isinstance(shown, AccessToken)
    assert authorization(KeyScheme.GOOGLE_SERVICE_ACCOUNT, shown) == "Bearer ya29.a-token"
    ((url, address, headers, _),) = poster.posts
    assert (url, address) == (GOOGLE_TOKEN_URL, PUBLIC)
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"


def test_a_key_sent_as_it_is_is_never_exchanged() -> None:
    """The sibling: a bearer or Basic source's key is presented untouched and nothing is posted.

    Delete this and every Xero read could start posting a key to Google."""

    class Bearer:
        def key_scheme(self) -> KeyScheme:
            return KeyScheme.BEARER

    poster = Poster()
    assert presented(Bearer(), "k", poster=poster, resolver=Resolver(), now=NOW) == "k"  # type: ignore[arg-type]
    assert poster.posts == []


def test_a_google_source_s_header_is_never_built_from_the_key_file(
    key: rsa.RSAPrivateKey,
) -> None:
    """`A_KEY_FILE_IS_NEVER_SENT_IN_A_HEADER`: the Google scheme refuses a plain string, which is
    what a path that skipped the exchange would hand it, while a bearer source takes one.

    Delete this and a caller that forgot `presented` sends the private key to Google as a bearer
    token."""
    with pytest.raises(ConnectorContractError):
        authorization(KeyScheme.GOOGLE_SERVICE_ACCOUNT, key_file(key))
    assert authorization(KeyScheme.BEARER, "k") == "Bearer k"
    assert "private key" in A_KEY_FILE_IS_NEVER_SENT_IN_A_HEADER


def test_a_google_reading_with_no_scope_or_no_poster_is_refused_before_anything_is_sent(
    key: rsa.RSAPrivateKey,
) -> None:
    """A reading naming the Google scheme must say its scope, and a process given no way to post
    cannot mint a token; both refuse without a call.

    Delete this and a reading with no scope would ask Google for a token carrying none, or a
    process wired without a poster would fall back to sending the key."""

    class Unscoped:
        def key_scheme(self) -> KeyScheme:
            return KeyScheme.GOOGLE_SERVICE_ACCOUNT

    poster = Poster()
    with pytest.raises(TokenNotIssuedError) as unscoped:
        presented(Unscoped(), key_file(key), poster=poster, resolver=Resolver(), now=NOW)  # type: ignore[arg-type]
    with pytest.raises(TokenNotIssuedError) as unwired:
        presented(AnalyticsReading(), key_file(key), poster=None, resolver=Resolver(), now=NOW)
    assert (unscoped.value.call, unwired.value.call) == (
        CallOutcome.REJECTED,
        CallOutcome.UNAVAILABLE,
    )
    assert poster.posts == []


def test_google_s_address_resolving_inside_the_network_is_refused_before_the_post(
    key: rsa.RSAPrivateKey,
) -> None:
    """The token endpoint is a constant, and still goes through the address rule: a resolver that
    answers inside this network is refused before a signed assertion leaves.

    Delete this and a poisoned resolver could collect assertions signed with the company's key."""
    poster = Poster()
    with pytest.raises(UnsafeAddressError):
        mint_token(key_file(key), (SCOPE,), poster=poster, resolver=Resolver("fd00::1"), now=NOW)
    assert poster.posts == []
