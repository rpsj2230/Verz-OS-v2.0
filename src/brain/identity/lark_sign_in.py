"""Sign in with Lark: what Keycloak needs said to it, because Lark does not speak OpenID Connect.

Needs-rupash item 115 decided a second way in for a company whose staff list is Lark: a person on
the list signs in with Lark and no password, and is the account the staff sync already made for
them. Keycloak's generic OpenID Connect broker is the right host for that, and **Lark cannot be
pointed at it as it stands**: Lark's token endpoint takes a JSON body where the standard takes a
form and answers no ID token, which Keycloak's broker requires, and its user information is
wrapped (`{"code": 0, "data": {...}}`) where Keycloak reads `sub` and `email` from the top of a
flat document. Pointing the broker straight at Lark is a sign-in that fails at the token
exchange, which is why `brain.identity.brokering` refused Lark until now.

**So this module is the translation, and it is nothing but translation.** Pure functions turn what
Keycloak sends into what Lark takes (`exchange_request`), what Lark answers the exchange with into
a token (`grant_from`), what Lark says about the person into the claims Keycloak links on
(`profile_request`, `claims_from`), and those into the token response Keycloak reads
(`id_token_for`). `brain.lark_sign_in_routes` is the one address Keycloak is pointed at for the
exchange; the page the person is sent to (`authorize_base`) is Lark's own. Nothing here opens a
socket, reads a setting or holds a secret: requests are `Outbound` values handed to a `Fetch`, as
in `brain.connectors.staff_directories`, whose Lark token request shape, hosts and refusal wording
this reuses.

**The ID token the bridge makes is unsigned, and that is the standard's own allowance.** Keycloak
asks for an ID token and, with signature validation switched off for this provider, reads it
without a key. OpenID Connect Core (3.1.3.7) lets a client skip validating the signature of a token
it received straight from the token endpoint over TLS, which is the only way this one arrives: the
person's browser never carries it. See `THE_IDENTITY_PROOF_NEVER_TRAVELS_THROUGH_THE_BROWSER`.
Rejected: signing it with a key of the bridge's own, which is a signing key to hold, rotate and
publish for a token nobody but one Keycloak ever reads.

**The application's secret is Keycloak's, and this only passes it on.** The broker is given the
Lark application's secret the way the Google and Microsoft brokers are
(`brain.identity.brokering.VAULT_REFERENCE`), and Keycloak sends it with the code. The bridge
forwards it to Lark in the one request that needs it and keeps it nowhere: not in a log, not in
an exception, not in a response. See `THE_APPLICATION_KEY_IS_FORWARDED_AND_NEVER_KEPT`.
Rejected: the application reading the secret from the vault itself, which would give the web
process a reader for a credential it has no other use for, and a second copy of the secret to
keep in step.

**The person is told apart by Lark's `union_id`, and matched to an account by their work
address.** `union_id` is the identifier Lark does not reissue and does not change between this
company's applications, so it is the broker's `sub` and the link Keycloak keeps afterwards.
`open_id` is per application and is used only where Lark gave no `union_id`. The address is
`brain.identity.staff_adapters.lark_work_address`, the very function the staff sync joins people
on, so the address Keycloak is told is the address the account was made with and the two cannot
disagree about who somebody is. A person Lark gives no address for is refused rather than signed
in as nobody: see `A_PERSON_WITH_NO_ADDRESS_IS_NOT_SIGNED_IN`.

**Refusals are fixed words that name nothing Lark said.** Lark's own error text is the vendor's,
can name a person or a tenant, and goes to nobody: Keycloak is handed one of the words below and
the person sees Keycloak's own page. See `EVERY_REFUSAL_IS_A_FIXED_WORD`.

Scope: pure. Values in, values out.

Task ids: M1.1.8
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import urlsplit

from brain.connectors.staff_directories import (
    CLIENT_ID,
    LARK_PLATFORMS,
    Answer,
    Outbound,
)
from brain.identity.staff_adapters import lark_work_address

# ------------------------------------------------------------------ written-down reasons
#: Why the application's secret is passed on and never kept.
THE_APPLICATION_KEY_IS_FORWARDED_AND_NEVER_KEPT: Final = (
    "Keycloak holds the Lark application's secret in its own vault and sends it with the code. "
    "The bridge puts it in the one request that needs it, in the body of an `Outbound` whose "
    "representation hides it, and it is in no log line, no exception message and no response. "
    "A bridge that kept it would be a second place for it to leak from."
)

#: Why a Lark person with no address is refused.
A_PERSON_WITH_NO_ADDRESS_IS_NOT_SIGNED_IN: Final = (
    "The account is found by the person's work address, so a person Lark gives no address for "
    "has nothing to be found by. Refusing is the whole of the alternative: signing them in "
    "without an address would be a session with no account behind it."
)

#: Why every refusal is a word from a short list.
EVERY_REFUSAL_IS_A_FIXED_WORD: Final = (
    "Lark's refusal text is the vendor's and may name a person, a tenant or an application. "
    "Keycloak is handed one of a few fixed words and the person is shown Keycloak's own page, so "
    "a stranger probing the bridge learns which step refused and nothing Lark said."
)

#: Why the unsigned ID token is acceptable here and nowhere else.
THE_IDENTITY_PROOF_NEVER_TRAVELS_THROUGH_THE_BROWSER: Final = (
    "The ID token is made in the answer to Keycloak's own request for it and is read by Keycloak "
    "alone. Nothing sends it to the person's browser and nothing accepts one from it, so there is "
    "no party who could present a forged one, which is the only thing a signature would defend "
    "against. A token that did travel through a browser would need the signature."
)

# ------------------------------------------------------------------------ the figures
#: The alias the identity provider is registered under, and so the last word but one of the
#: address Lark's sign-in returns to: `/realms/<realm>/broker/lark/endpoint`.
ALIAS: Final = "lark"

#: The end of the address Keycloak's broker for this alias is returned to.
BROKER_RETURN_SUFFIX: Final = f"/broker/{ALIAS}/endpoint"

#: Where Keycloak is pointed for the exchange, under the install's own address. Not under the API
#: prefix, which authenticates every caller but two written exceptions; this one proves the
#: application's secret and a code Lark issued instead, and says so in `brain.lark_sign_in_routes`.
BRIDGE_PATH: Final = "/lark-sign-in"
TOKEN_PATH: Final = BRIDGE_PATH + "/token"

#: The permissions the person is asked to grant at Lark, which are the two that let Lark say an
#: address at all. The same names the staff sync's own application is given, so an application
#: set up for the staff list is one scope list away from signing people in. Held to the staff
#: sync's by a test.
SIGN_IN_SCOPES: Final = "contact:user.email:readonly contact:user.employee:readonly"

#: The one grant type Keycloak sends and this answers.
CODE_GRANT: Final = "authorization_code"

#: The words a refusal is one of. See `EVERY_REFUSAL_IS_A_FIXED_WORD`.
INVALID_REQUEST: Final = "invalid_request"
INVALID_GRANT: Final = "invalid_grant"
INVALID_BEARER: Final = "invalid_token"
UNAUTHORISED_PERSON: Final = "access_denied"

#: The longest value taken from Lark into a claim. An identifier or an address, never a document.
MAX_CLAIM_CHARS: Final = 320

#: How long the token the bridge hands back may be said to live, whatever Lark said: it is held
#: for one exchange by one Keycloak and read once.
MAX_TOKEN_SECONDS: Final = 600

#: What a grant lives for when Lark said nothing usable.
DEFAULT_TOKEN_SECONDS: Final = 300


class LarkSignInError(Exception):
    """A step of the sign-in is refused. `word` is one of the fixed words above and the message
    is that word, so nothing a vendor said can travel in one."""

    def __init__(self, word: str) -> None:
        super().__init__(word)
        self.word = word


@dataclass(frozen=True)
class Grant:
    """What Lark answered the exchange with, and nothing Lark added."""

    access_token: str = field(repr=False)
    expires_in: int


@dataclass(frozen=True)
class Claims:
    """The claims Keycloak links on. `sub` is stable and `email` is the account's address."""

    sub: str
    email: str
    name: str


def platform_of(location: str) -> tuple[str, str]:
    """The accounts host and the open host of the platform a company signs in to.

    The location is the staff source's, which is already one of Lark's two platforms. Anything
    else is refused, because the location decides which address the application's secret is sent
    to (`brain.connectors.staff_directories.LARK_PLATFORMS`).
    """
    found = LARK_PLATFORMS.get(location.strip().lower())
    if found is None:
        raise LarkSignInError(INVALID_REQUEST)
    return found


def authorize_base(location: str) -> str:
    """Lark's own sign-in page, with no query: Keycloak adds the client, the return address, the
    state and the scope. The one address of the three that is not this bridge's."""
    accounts, _ = platform_of(location)
    return f"https://{accounts}/open-apis/authen/v1/authorize"


def _is_the_brokers_return(address: str) -> bool:
    """Whether this is the address Keycloak's broker for this alias returns to.

    The exchange is made only for a code that was sent back to `/broker/lark/endpoint`, so the
    bridge cannot be used to redeem a code issued for some other address of the same application.
    """
    parts = urlsplit(address)
    return (
        parts.scheme in ("http", "https")
        and bool(parts.netloc)
        and not parts.query
        and not parts.fragment
        and parts.path.endswith(BROKER_RETURN_SUFFIX)
    )


def exchange_request(location: str, *, form: Mapping[str, str], client_id: str) -> Outbound:
    """Keycloak's form as Lark's exchange: the same values, in a JSON body.

    The client id must be the one this install brokers with, so the bridge cannot be used to
    exchange a code for some other application; the code is passed on exactly and only bounded.
    The secret is whatever Keycloak sent and is forwarded as it came (see
    `THE_APPLICATION_KEY_IS_FORWARDED_AND_NEVER_KEPT`); Lark is the one to refuse a wrong one.
    """
    _, open_host = platform_of(location)
    code = form.get("code", "")
    secret = form.get("client_secret", "")
    redirect_uri = form.get("redirect_uri", "")
    if (
        form.get("grant_type") != CODE_GRANT
        or not CLIENT_ID.match(client_id)
        or form.get("client_id") != client_id
        or not code.strip()
        or len(code) > 2000
        or not secret.strip()
        or len(secret) > 500
        or not _is_the_brokers_return(redirect_uri)
    ):
        raise LarkSignInError(INVALID_REQUEST)
    body = {
        "grant_type": CODE_GRANT,
        "client_id": client_id,
        "client_secret": secret.strip(),
        "code": code,
        "redirect_uri": redirect_uri,
    }
    return Outbound("POST", f"https://{open_host}/open-apis/authen/v2/oauth/token", json_body=body)


def grant_from(answer: Answer) -> Grant:
    """The token Lark answered an exchange with, or a refusal as one fixed word."""
    token = answer.body.get("access_token")
    refused = answer.status != 200 or answer.body.get("code", 0) not in (0, None)
    if refused or not isinstance(token, str) or not token.strip():
        raise LarkSignInError(INVALID_GRANT)
    seconds = answer.body.get("expires_in")
    lives = (
        seconds
        if isinstance(seconds, int) and 0 < seconds <= MAX_TOKEN_SECONDS
        else DEFAULT_TOKEN_SECONDS
    )
    return Grant(access_token=token.strip(), expires_in=lives)


def profile_request(location: str, token: str) -> Outbound:
    """Lark's read of the person a token belongs to, as a request not yet sent."""
    _, open_host = platform_of(location)
    if not token.strip() or len(token) > 2000:
        raise LarkSignInError(INVALID_BEARER)
    return Outbound(
        "GET",
        f"https://{open_host}/open-apis/authen/v1/user_info",
        headers={"Authorization": f"Bearer {token.strip()}", "Accept": "application/json"},
    )


def _text(value: object) -> str:
    return " ".join(str(value or "").split())[:MAX_CLAIM_CHARS]


def claims_from(answer: Answer) -> Claims:
    """The claims for the person Lark described, or a refusal as one fixed word.

    Lark wraps the person under `data`. The stable identifier is `union_id`, else `open_id`; the
    address is the one the staff sync joins on. A person with either missing is refused (see
    `A_PERSON_WITH_NO_ADDRESS_IS_NOT_SIGNED_IN`), and so is an answer that is not a person.
    """
    refused = answer.status != 200 or answer.body.get("code", 0) not in (0, None)
    data: Any = answer.body.get("data")
    if refused or not isinstance(data, Mapping):
        raise LarkSignInError(INVALID_BEARER)
    sub = _text(data.get("union_id")) or _text(data.get("open_id"))
    address = _text(lark_work_address(data)).lower()
    if not sub:
        raise LarkSignInError(INVALID_BEARER)
    if "@" not in address or address.startswith("@") or address.endswith("@"):
        raise LarkSignInError(UNAUTHORISED_PERSON)
    return Claims(sub=sub, email=address, name=_text(data.get("name")) or address)


def _segment(value: Mapping[str, object]) -> str:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def id_token_for(
    claims: Claims, grant: Grant, *, client_id: str, issuer: str, now_seconds: int
) -> dict[str, object]:
    """The token response Keycloak's broker reads: an access token and an unsigned ID token.

    The ID token names the person (`sub`, `email`, `name`), the client it was made for (`aud`)
    and the bridge as its issuer, and lives as long as the grant. The address is marked verified
    because it is the one Lark's own contact book holds and the staff sync read from there; the
    broker's link-only flow, not this flag, is what decides whom it may sign in as. See
    `THE_IDENTITY_PROOF_NEVER_TRAVELS_THROUGH_THE_BROWSER`.
    """
    payload: dict[str, object] = {
        "iss": issuer,
        "sub": claims.sub,
        "aud": client_id,
        "iat": now_seconds,
        "exp": now_seconds + grant.expires_in,
        "email": claims.email,
        "email_verified": True,
        "preferred_username": claims.email,
        "name": claims.name,
    }
    header = {"alg": "none", "typ": "JWT"}
    return {
        "access_token": grant.access_token,
        "token_type": "Bearer",
        "expires_in": grant.expires_in,
        "id_token": f"{_segment(header)}.{_segment(payload)}.",
    }
