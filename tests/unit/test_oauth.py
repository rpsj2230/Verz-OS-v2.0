"""What a source that authorises by OAuth sends and reads back: consent, exchange and renewal.

Every test here is over `brain.connectors.oauth` as data; nothing opens a socket.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from brain.connectors.contract import ConnectorContractError
from brain.connectors.google_token import TokenNotIssuedError
from brain.connectors.oauth import (
    CONSENT_RETURN_PATH,
    ConsentStart,
    OAuthConsent,
    challenge_of,
    code_exchange,
    consent_address,
    consent_return_address,
    new_consent,
    opened_verifier,
    refresh_exchange,
    sealed_verifier,
    state_digest,
    tokens_from,
)
from brain.connectors.throttle import CallOutcome

VENDOR = OAuthConsent(
    authorize_url="https://accounts.vendor.invalid/authorize",
    token_url="https://accounts.vendor.invalid/token",
    scopes=("records.read", "offline_access"),
    authorize_params=(("access_type", "offline"),),
)
REDIRECT = "https://brain.invalid/connectors/consent/callback"
#: RFC 7636 appendix B's own example, so the transform is held to the standard, not to itself.
RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_the_code_challenge_is_rfc_7636_s256() -> None:
    """Delete this and a challenge the vendor cannot verify would be sent, and every consent would
    fail at the exchange with the vendor's refusal and nothing here saying why."""
    assert challenge_of(RFC_VERIFIER) == RFC_CHALLENGE


def test_a_fresh_consent_is_random_and_its_verifier_is_never_shown() -> None:
    """Delete this and two consents could share a state, so one person's answer could complete
    another's, or the verifier could reach a log through a representation."""
    one, two = new_consent(), new_consent()
    assert one.state != two.state and one.verifier != two.verifier
    assert one.verifier not in repr(one)
    with pytest.raises(ConnectorContractError):
        ConsentStart(state="short", verifier=RFC_VERIFIER)


def test_the_consent_page_is_asked_with_the_state_challenge_and_scopes() -> None:
    """`A_CONSENT_ANSWER_IS_TRUSTED_ONLY_FOR_THE_REQUEST_THAT_ASKED`. Delete this and the vendor
    could be sent no state or no challenge, so its answer could not be tied to this request."""
    start = ConsentStart(state="s" * 43, verifier=RFC_VERIFIER)
    address = consent_address(VENDOR, client_id="client-1", redirect_uri=REDIRECT, start=start)
    parts = urlsplit(address)
    asked = {name: one[0] for name, one in parse_qs(parts.query).items()}
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == VENDOR.authorize_url
    assert asked == {
        "response_type": "code",
        "client_id": "client-1",
        "redirect_uri": REDIRECT,
        "scope": "records.read offline_access",
        "state": "s" * 43,
        "code_challenge": RFC_CHALLENGE,
        "code_challenge_method": "S256",
        "access_type": "offline",
    }
    assert RFC_VERIFIER not in address


def test_a_declaration_cannot_set_what_the_consent_itself_sets() -> None:
    """Delete this and a connector could declare its own state or redirect, which would replace
    the one this install checks the answer against."""
    with pytest.raises(ConnectorContractError):
        OAuthConsent(
            authorize_url=VENDOR.authorize_url,
            token_url=VENDOR.token_url,
            scopes=("records.read",),
            authorize_params=(("state", "fixed"),),
        )
    with pytest.raises(ConnectorContractError):
        OAuthConsent(
            authorize_url="http://plain.invalid/a", token_url=VENDOR.token_url, scopes=("a",)
        )
    with pytest.raises(ConnectorContractError):
        OAuthConsent(authorize_url=VENDOR.authorize_url, token_url=VENDOR.token_url, scopes=())


def test_the_code_is_exchanged_with_the_verifier_it_was_issued_with() -> None:
    """Delete this and the code could be posted without the verifier, which a vendor enforcing
    PKCE refuses, or with somebody else's, which is the attack PKCE exists to stop."""
    start = ConsentStart(state="s" * 43, verifier=RFC_VERIFIER)
    asked = code_exchange(
        VENDOR,
        client_id="client-1",
        client_secret="secret-1",
        code="code-1",
        redirect_uri=REDIRECT,
        start=start,
    )
    form = {name: one[0] for name, one in parse_qs(asked.body.decode()).items()}
    assert asked.url == VENDOR.token_url
    assert form == {
        "grant_type": "authorization_code",
        "code": "code-1",
        "redirect_uri": REDIRECT,
        "client_id": "client-1",
        "client_secret": "secret-1",
        "code_verifier": RFC_VERIFIER,
    }
    assert "secret-1" not in repr(asked)


def test_a_renewal_posts_the_kept_refresh_token_and_nothing_else() -> None:
    """`ACCESS_IS_RENEWED_BY_THE_READ_THAT_NEEDS_IT`. Delete this and a renewal could post a code
    or a scope the consent never gave, which a vendor reads as a new consent request."""
    asked = refresh_exchange(
        VENDOR, client_id="client-1", client_secret="secret-1", refresh_token="refresh-1"
    )
    form = {name: one[0] for name, one in parse_qs(asked.body.decode()).items()}
    assert form == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh-1",
        "client_id": "client-1",
        "client_secret": "secret-1",
    }


def test_an_issued_answer_is_read_and_its_tokens_kept_out_of_every_representation() -> None:
    """The positive case. Delete this and a working vendor's answer could be misread as a refusal,
    or a token could reach a log through its representation."""
    answer = {
        "access_token": "access-1",
        "token_type": "Bearer",
        "refresh_token": "refresh-2",
        "expires_in": 1800,
    }
    tokens = tokens_from(status=200, body=json.dumps(answer).encode())
    assert (tokens.access.value, tokens.refresh, tokens.expires_in) == (
        "access-1",
        "refresh-2",
        1800,
    )
    assert "access-1" not in repr(tokens) and "refresh-2" not in repr(tokens)
    plain = tokens_from(status=200, body=b'{"access_token": "a2", "token_type": "bearer"}')
    assert plain.refresh is None


@pytest.mark.parametrize(
    ("status", "call"),
    [(400, CallOutcome.REJECTED), (401, CallOutcome.REJECTED), (429, CallOutcome.QUOTA)],
)
def test_a_refused_grant_is_a_refusal_and_never_a_token(status: int, call: CallOutcome) -> None:
    """RFC 6749's `invalid_grant` is a 400, and a forgotten client a 401: the consent is withdrawn.
    Delete this and a revoked consent could be retried as ill health into the vendor's limit."""
    with pytest.raises(TokenNotIssuedError) as refused:
        tokens_from(status=status, body=b'{"error": "invalid_grant"}')
    assert refused.value.call is call


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"access_token": "a", "token_type": "mac"}',
        b'{"access_token": "a", "token_type": "bearer", "expires_in": "soon"}',
        b'{"access_token": "a", "token_type": "bearer", "refresh_token": 7}',
    ],
)
def test_an_answer_not_in_the_documented_shape_is_not_a_token(body: bytes) -> None:
    """Delete this and a half-read answer could be kept as a refresh token or sent as access."""
    with pytest.raises(TokenNotIssuedError) as refused:
        tokens_from(status=200, body=body)
    assert refused.value.call is CallOutcome.UNAVAILABLE


# ------------------------------------------------------------------ where the person comes back
def test_the_vendor_sends_the_person_back_only_to_the_console_s_consent_page() -> None:
    """An https address ending in `CONSENT_RETURN_PATH` and nothing after it is accepted, on
    whatever host the console is served from; an address on plain http, at any other path, or
    carrying a query or a fragment is refused. Delete this and a consent could be asked with a
    return address that hands the code to another page, or to a script that reads the query."""
    good = f"https://console.example{CONSENT_RETURN_PATH}"
    assert consent_return_address(good) == good
    for refused in (
        f"http://console.example{CONSENT_RETURN_PATH}",
        "https://console.example/somewhere-else",
        f"https://console.example{CONSENT_RETURN_PATH}?next=/",
        f"https://console.example{CONSENT_RETURN_PATH}#x",
        f"https://{'a' * 600}.example{CONSENT_RETURN_PATH}",
        f"https://{CONSENT_RETURN_PATH}",
    ):
        with pytest.raises(ConnectorContractError):
            consent_return_address(refused)


def test_the_console_page_is_where_the_console_says_it_is() -> None:
    """The path the API holds a return address to is the path the console serves its consent page
    at, read from the console's own route file. Delete this and the two can drift apart, and every
    consent's return address is refused by the start route or lands on the console's not-found
    page."""
    from pathlib import Path

    route = Path(__file__).resolve().parents[2] / "console/src/pages/ConnectorConsent.route.tsx"
    assert f'path: "{CONSENT_RETURN_PATH.lstrip("/")}"' in route.read_text(encoding="utf-8")


def test_a_client_id_is_typed_into_a_setting_the_declaration_names() -> None:
    """The setting a client id is read from is a setting name; a declaration naming anything else
    is refused where it is built. Delete this and a client id could be read from a setting no form
    asks for, and every consent would ask the vendor for an empty client."""
    assert VENDOR.client_id_setting == "client_id"
    with pytest.raises(ConnectorContractError):
        OAuthConsent(
            authorize_url=VENDOR.authorize_url,
            token_url=VENDOR.token_url,
            scopes=VENDOR.scopes,
            client_id_setting="Client Id",
        )


# ------------------------------------------------------------------ the verifier, kept sealed
def test_a_kept_verifier_opens_only_with_the_state_it_was_sealed_under() -> None:
    """`A_KEPT_VERIFIER_IS_SEALED_UNDER_THE_STATE_THE_TABLE_NEVER_HOLDS`: a sealed verifier holds
    neither the verifier nor the state, opens with its own state to the very consent that was
    started, and is refused under any other state or with one character changed. Delete this and
    the table could keep the verifier as it is, or a seal anybody can open."""
    start, other = new_consent(), new_consent()
    sealed = sealed_verifier(start)
    assert start.verifier not in sealed and start.state not in sealed
    assert opened_verifier(start.state, sealed) == start
    assert sealed_verifier(start) != sealed
    with pytest.raises(ConnectorContractError):
        opened_verifier(other.state, sealed)
    flipped = sealed[:-2] + ("A" if sealed[-2] != "A" else "B") + sealed[-1]
    with pytest.raises(ConnectorContractError):
        opened_verifier(start.state, flipped)
    with pytest.raises(ConnectorContractError):
        opened_verifier(start.state, "not base64 at all")


def test_a_consent_is_found_by_a_digest_of_its_state_and_never_by_the_state() -> None:
    """The digest is SHA-256 in hex, the shape the table's constraint holds, and is not the
    state. Delete this and the row could come to be keyed by the state itself."""
    import hashlib

    start = new_consent()
    found = state_digest(start.state)
    assert found == hashlib.sha256(start.state.encode("ascii")).hexdigest()
    assert len(found) == 64 and found != start.state
