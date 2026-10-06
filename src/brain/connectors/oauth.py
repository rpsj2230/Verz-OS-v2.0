"""A source that authorises by OAuth: the consent a person gives, and the token it is renewed by.

Most sources this product reads are given a key: an administrator creates it in the vendor's own
screens and pastes it into the Connectors screen. A source that authorises by OAuth has no key to
paste. A person signs in at the vendor, reads what the connection asks for and consents, and the
vendor hands back a code that is exchanged once for a refresh token. **This module is that exchange
and the renewal after it, as data**: what is sent to the vendor's consent page, what is posted to
its token endpoint, and what is read back. It opens no socket and reads no clock, for the reason
`brain.connectors.google_token` gives: the call is made by whoever holds the secret, through the
address-checked poster every other source's token goes through.

**Consent is given by a person, on the vendor's page, never on ours.** The console only sends the
administrator there and receives the answer. This product never sees the vendor password, and what
was consented to is what the vendor's page showed. See
`CONSENT_IS_GIVEN_BY_A_PERSON_ON_THE_VENDORS_OWN_PAGE`.

**The answer is trusted only for the request that asked for it.** Every consent carries a state
that is random, used once, bound to the person who started it and short-lived, and a PKCE verifier
(RFC 7636, S256) that never leaves this install until the code is exchanged. A code arriving with
a state nobody issued, one already used, or one issued to somebody else, is refused before anything
is posted. See `A_CONSENT_ANSWER_IS_TRUSTED_ONLY_FOR_THE_REQUEST_THAT_ASKED`.

**The refresh token lives in the vault; an access token lives as long as the read.** The refresh
token is kept whole in the source's own vault slot, by reference, exactly as a pasted key is. Each
read exchanges it for an access token and drops that token with the call, which is the Google key
file's rule (`google_token.WHAT_A_KEY_FILE_BUYS_LIVES_AS_LONG_AS_THE_READ`): access is therefore
always renewed before it expires, by the read that needs it, with no person and no timer. See
`ACCESS_IS_RENEWED_BY_THE_READ_THAT_NEEDS_IT`.

**A refused renewal is the source down, in words.** A vendor answering the refresh with
`invalid_grant`, or a 400 or 401, has withdrawn the consent: somebody revoked the app, the person
who consented left, or the token expired unused. Nothing this install does without a person mends
that, so the read fails as a declined key and the Connectors screen says to connect again
(`CONSENT_WITHDRAWN`), rather than retrying a refusal into the vendor's rate limit.

Rejected: an OAuth library (authlib, requests-oauthlib). The exchange is three form posts and a
hash, and a library would open its own sockets where every call here goes through the pinned,
address-checked poster; the reason is `google_token`'s, about the same size of saving.

Rejected: keeping the access token for its lifetime to save a round trip. It is
`WHAT_A_KEY_FILE_BUYS_LIVES_AS_LONG_AS_THE_READ` again: a token held between requests is a
credential in memory readable by anything that can read the process.

**The verifier is kept sealed under the state, and the state is never kept.** Between the console
sending the person and the vendor answering, the install has to hold the verifier somewhere, and
`ops.oauth_consent` (`0202`) is that place. Its row holds a digest of the state, to find the row
by, and the verifier sealed with AES-GCM under a key derived from the state. The state itself
travels only through the person's browser and the vendor, so a copy of the table, or a reader of
it, holds verifiers nobody can open, and PKCE's protection survives a leaked row. See
`A_KEPT_VERIFIER_IS_SEALED_UNDER_THE_STATE_THE_TABLE_NEVER_HOLDS`. Rejected: a key of the install's
own for the purpose, which would be a vault slot and a vault round trip per consent to protect a
value that lives ten minutes, when the state is already a 256-bit secret only the right answer
carries. Rejected: the verifier in the row as it is, which would let anybody holding the table and
an intercepted code finish somebody else's consent.

**The vendor sends the person back to one page of the console, and only to that one.** The
address is built in the person's browser from the console's own origin and `CONSENT_RETURN_PATH`,
checked here, kept with the consent, and sent again with the code, because a vendor refuses an
exchange whose address differs from the one the consent was asked with. See
`consent_return_address`.

**A source's consent is given once for the source, or by each person for themselves.** A source
whose vendor holds one company account (Xero's organisation) is consented to once, by somebody
holding the authority to connect it, and every read uses that one refresh token. A source whose
vendor holds each person's own account (their mailbox, their calendar) cannot be: the company has
no account there to consent with, and one person's consent reading for everybody would be that
person's mailbox told to whoever asks. So `OAuthConsent.kind` says which, and a `ConsentKind.PERSON`
consent is started by the person themselves, kept in a slot of their own
(`brain.ops.credentials.connector_person_oauth_slot`), and read only for that person's own
questions. See `A_PERSONS_CONSENT_READS_ONLY_FOR_THAT_PERSON`. The client id and secret stay the
source's: they are the application the company registered at the vendor, which every person
consents to. Rejected: a second declaration field beside `oauth` for the personal case, which would
let a source declare both and leave which one a read used to whichever path came first.

Task ids: M11.8.6
"""

from __future__ import annotations

import base64
import enum
import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import urlencode, urlsplit

from pydantic import ValidationError

from brain.connectors.contract import ConnectorContractError
from brain.connectors.google_token import (
    MAX_TOKEN_ANSWER_BYTES,
    AccessToken,
    TokenExchange,
    TokenNotIssuedError,
)
from brain.connectors.throttle import CallOutcome, classify
from brain.core.entitlement import Capability

# ------------------------------------------------------------------ written-down reasons
#: Why the console never asks for a vendor password or decides what was consented to.
CONSENT_IS_GIVEN_BY_A_PERSON_ON_THE_VENDORS_OWN_PAGE: Final = (
    "A source that authorises by OAuth is consented to by a person signing in on the vendor's own "
    "page, which shows what the connection asks for. The console only sends the administrator "
    "there and receives the vendor's answer, so this product never sees the vendor password and "
    "what was consented to is what the vendor showed."
)

#: Why a consent answer is checked against the request that asked for it.
A_CONSENT_ANSWER_IS_TRUSTED_ONLY_FOR_THE_REQUEST_THAT_ASKED: Final = (
    "The vendor's answer arrives at an address anybody can call, so a code is exchanged only when "
    "it comes back with a state this install issued, unused, unexpired, and to the same person "
    "who started the consent, and only with the PKCE verifier that state was issued with. A code "
    "with any other state is refused before anything is posted, which is what stops somebody "
    "else's consent being attached to this install's connection."
)

#: Why access is renewed by each read and never by a timer.
ACCESS_IS_RENEWED_BY_THE_READ_THAT_NEEDS_IT: Final = (
    "The refresh token is kept in the source's vault slot, and each read exchanges it for an "
    "access token it drops with the call. So access is never used past its expiry and is renewed "
    "without a person, by the read that needs it, and no access token outlives the request it was "
    "issued for."
)

#: What the Connectors screen says when the vendor refused a renewal or a consent. Constant, and
#: never the vendor's own text, which can quote the token it refused.
CONSENT_WITHDRAWN: Final = (
    "The vendor refused this connection's consent: it was revoked, it expired, or it was given by "
    "somebody who can no longer give it. Connect it with the vendor again from this source's page."
)

#: Why a consented source's header is only ever built from an access token.
A_CONSENTED_SOURCE_IS_SENT_ONLY_ITS_ACCESS: Final = (
    "A consented source's credential is a client secret and a refresh token, and the header its "
    "API reads carries an access token. A path that forgot the renewal would send the client "
    "secret itself, so the header is built only from an AccessToken, which only the renewal "
    "produces, and the refresh token and the secret go to the vendor's token endpoint alone."
)

#: Why the verifier is sealed in the consent's row, and under what.
A_KEPT_VERIFIER_IS_SEALED_UNDER_THE_STATE_THE_TABLE_NEVER_HOLDS: Final = (
    "A consent's verifier waits in the database until the vendor answers, sealed with a key "
    "derived from the consent's state, and the row keeps only a digest of the state. The state "
    "travels through the person's browser and the vendor and nowhere else, so the table alone "
    "opens no verifier, and a code intercepted on its way back cannot be exchanged by somebody "
    "who also read the table."
)

#: Why a person's own consent is read for nobody but them.
A_PERSONS_CONSENT_READS_ONLY_FOR_THAT_PERSON: Final = (
    "A consent a person gives for their own account at a vendor reaches what that account holds, "
    "their mail and their calendar, which is theirs and nobody else's. So it is started by that "
    "person, kept in a slot of their own, and leased only for a read made for their own question: "
    "a read for anybody else never names their slot, and no process reading with nobody present "
    "can lease it at all."
)

#: What a person is told when the vendor refused the consent they gave for their own account.
#: Constant, for `CONSENT_WITHDRAWN`'s reason, and about their reads alone.
YOUR_CONSENT_WITHDRAWN: Final = (
    "The vendor refused the consent you gave for your own account: it was revoked or it expired. "
    "Nothing was read from it for you. Connect your account again from My workspace; nobody "
    "else's reads are affected."
)

#: What a person is told when they have not consented for their own account yet.
NOT_CONNECTED_FOR_YOU: Final = (
    "You have not connected your own account with this source, so nothing was read from it for "
    "you. Connect it from My workspace."
)

#: Where the vendor sends the person back: one page of the console, the same on every install.
CONSENT_RETURN_PATH: Final = "/connector-consent"

#: What the sealing key is derived for, so a key derived from a state for anything else differs.
_SEAL_INFO: Final = b"brain.connectors.oauth.verifier.v1"

#: AES-GCM's nonce, in bytes.
_NONCE_BYTES: Final = 12

#: The longest return address a consent keeps.
MAX_RETURN_ADDRESS_CHARS: Final = 512

# --------------------------------------------------------------------- the figures
#: How long a consent may take between the console sending the person and the vendor answering.
CONSENT_LIFETIME_SECONDS: Final = 600

#: The PKCE verifier's length in characters: RFC 7636 allows 43 to 128.
VERIFIER_CHARS: Final = 64

#: What a state and a verifier are spelled with: RFC 7636's unreserved characters.
_UNRESERVED_RE: Final = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")

#: What a scope may be spelled with: one token of printable characters (RFC 6749 section 3.3).
_SCOPE_RE: Final = re.compile(r"^[\x21\x23-\x5b\x5d-\x7e]{1,256}$")

#: What a code and a refresh token may be spelled with. Generous, because vendors differ, and
#: bounded, because an answer is read into memory.
_GRANT_RE: Final = re.compile(r"^[\x21-\x7e]{1,4096}$")

#: A console setting's name, as `brain.core.envelope.OBJECT_NAME_PATTERN` spells a field.
_SETTING_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

FORM: Final = (
    ("Content-Type", "application/x-www-form-urlencoded"),
    ("Accept", "application/json"),
)


def _https(url: str, what: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment:
        msg = f"an OAuth {what} is an https address with no query, and {url!r} is not"
        raise ConnectorContractError(msg)
    return url


class ConsentKind(enum.StrEnum):
    """Whose consent a source's access is renewed from. `ops.oauth_consent.kind` holds one."""

    #: Once for the source, by somebody who may connect it; every read uses it.
    SOURCE = "source"
    #: By each person for their own account; a read uses only the asker's. See
    #: `A_PERSONS_CONSENT_READS_ONLY_FOR_THAT_PERSON`.
    PERSON = "person"


@dataclass(frozen=True)
class OAuthConsent:
    """How one source is consented to and renewed: the vendor's two addresses and what is asked.

    Declared by the connector, as everything about a source is. `authorize_params` are the
    vendor's own extra words for asking a refresh token at all (Google's `access_type=offline`),
    never anything this install chooses per connection.
    """

    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    authorize_params: tuple[tuple[str, str], ...] = ()
    #: The console setting the application's client id is typed into. The client secret is the
    #: connection's credential, kept in its vault slot like any pasted key.
    client_id_setting: str = "client_id"
    #: Whether the source is consented to once, or by each person for themselves.
    kind: ConsentKind = ConsentKind.SOURCE
    #: For a personal consent, the capability a person holds in the connection's department to be
    #: read anything from the source, and so to consent for themselves at all; empty otherwise.
    reader: str = ""

    def __post_init__(self) -> None:
        _https(self.authorize_url, "consent page")
        _https(self.token_url, "token endpoint")
        if not _SETTING_RE.match(self.client_id_setting):
            msg = f"{self.client_id_setting!r} is not a setting a client id can be typed into"
            raise ConnectorContractError(msg)
        self._reader_matches_kind()
        if not self.scopes:
            msg = "an OAuth consent asks for at least one scope, or it can read nothing"
            raise ConnectorContractError(msg)
        for one in self.scopes:
            if not _SCOPE_RE.match(one):
                msg = f"{one!r} is not a scope as RFC 6749 spells one"
                raise ConnectorContractError(msg)
        reserved = {"client_id", "redirect_uri", "response_type", "scope", "state"}
        reserved |= {"code_challenge", "code_challenge_method"}
        for name, _ in self.authorize_params:
            if name in reserved:
                msg = f"{name!r} is set by the consent itself and is not the vendor's to declare"
                raise ConnectorContractError(msg)

    def _reader_matches_kind(self) -> None:
        """A personal consent names the read capability a person must hold; a source's names none.

        Without one, anybody who can sign in could keep a refresh token for an account no read
        would ever use for them; with one on a source's consent, the capability would read as a
        rule the source-wide renewal never asks.
        """
        if self.kind is ConsentKind.SOURCE:
            if self.reader:
                msg = "a source's own consent is given by its connector, so it names no reader"
                raise ConnectorContractError(msg)
            return
        try:
            verb = Capability(value=self.reader).verb
        except ValidationError:
            verb = ""
        if verb != "read":
            msg = (
                f"a personal consent names the read capability a person needs, and "
                f"{self.reader!r} is not one"
            )
            raise ConnectorContractError(msg)


# ----------------------------------------------------------------------- starting consent
@dataclass(frozen=True)
class ConsentStart:
    """A consent this install issued: the state it is answered with and the verifier it keeps."""

    state: str
    verifier: str = field(repr=False)

    def __post_init__(self) -> None:
        for name, value in (("state", self.state), ("verifier", self.verifier)):
            if not _UNRESERVED_RE.match(value):
                msg = f"a consent's {name} is 43 to 128 unreserved characters (RFC 7636)"
                raise ConnectorContractError(msg)

    @property
    def challenge(self) -> str:
        """The S256 code challenge: BASE64URL(SHA256(verifier)) without padding (RFC 7636)."""
        return challenge_of(self.verifier)


def challenge_of(verifier: str) -> str:
    """RFC 7636's S256 transform of a verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def new_consent() -> ConsentStart:
    """A fresh state and verifier, each from the operating system's random source."""
    return ConsentStart(
        state=secrets.token_urlsafe(32),
        verifier=secrets.token_urlsafe(VERIFIER_CHARS)[:VERIFIER_CHARS],
    )


def consent_return_address(address: str) -> str:
    """The address the vendor sends the person back to, or a refusal naming what is wrong.

    An https address on whatever host the console is served from, at `CONSENT_RETURN_PATH` and
    nothing after it. The host is the browser's, because the console knows where it is served and
    this install's configuration does not have to; the vendor refuses an address its application
    was not registered with, so a host typed by somebody else reaches nothing.
    """
    parts = urlsplit(address)
    if (
        len(address) > MAX_RETURN_ADDRESS_CHARS
        or parts.scheme != "https"
        or not parts.hostname
        or parts.path != CONSENT_RETURN_PATH
        or parts.query
        or parts.fragment
    ):
        msg = (
            f"a consent returns to an https address ending in {CONSENT_RETURN_PATH} and "
            "nothing after it"
        )
        raise ConnectorContractError(msg)
    return address


def state_digest(state: str) -> str:
    """What a consent's row is found by: the SHA-256 of its state, in hex. Never the state."""
    return hashlib.sha256(state.encode("ascii")).hexdigest()


def _sealing_key(state: str) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    derive = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_SEAL_INFO)
    return derive.derive(state.encode("ascii"))


def sealed_verifier(start: ConsentStart) -> str:
    """The start's verifier, sealed under a key derived from its state. See
    `A_KEPT_VERIFIER_IS_SEALED_UNDER_THE_STATE_THE_TABLE_NEVER_HOLDS`."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(_NONCE_BYTES)
    sealed = AESGCM(_sealing_key(start.state)).encrypt(nonce, start.verifier.encode("ascii"), None)
    return base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def opened_verifier(state: str, sealed: str) -> ConsentStart:
    """The consent a sealed verifier was issued with, opened by its state, or a refusal.

    A state that is not the one the verifier was sealed under cannot open it, and that is refused
    in the same words as a seal that was altered, because both are a consent this install did not
    issue to whoever is answering.
    """
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        raw = base64.urlsafe_b64decode(sealed.encode("ascii"))
        opened = AESGCM(_sealing_key(state)).decrypt(raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], None)
        return ConsentStart(state=state, verifier=opened.decode("ascii"))
    except (InvalidTag, ValueError, UnicodeError, ConnectorContractError):
        msg = A_CONSENT_ANSWER_IS_TRUSTED_ONLY_FOR_THE_REQUEST_THAT_ASKED
        raise ConnectorContractError(msg) from None


def consent_address(
    consent: OAuthConsent, *, client_id: str, redirect_uri: str, start: ConsentStart
) -> str:
    """Where the administrator is sent to consent: the vendor's page, asking with this start."""
    if not client_id.strip():
        msg = "a consent is asked for by a client id, and this one is empty"
        raise ConnectorContractError(msg)
    _https(redirect_uri, "redirect address")
    asked = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(consent.scopes),
        "state": start.state,
        "code_challenge": start.challenge,
        "code_challenge_method": "S256",
        **dict(consent.authorize_params),
    }
    return f"{consent.authorize_url}?{urlencode(asked)}"


# ------------------------------------------------------------------ the two token requests
def _secret(value: str, what: str) -> str:
    if not _GRANT_RE.match(value):
        msg = f"an OAuth {what} is one unbroken run of printable characters"
        raise ConnectorContractError(msg)
    return value


def code_exchange(
    consent: OAuthConsent,
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    start: ConsentStart,
) -> TokenExchange:
    """The one post that turns a consent's code into tokens, with the verifier it was issued."""
    body = {
        "grant_type": "authorization_code",
        "code": _secret(code, "code"),
        "redirect_uri": _https(redirect_uri, "redirect address"),
        "client_id": client_id,
        "client_secret": _secret(client_secret, "client secret"),
        "code_verifier": start.verifier,
    }
    return TokenExchange(url=consent.token_url, headers=FORM, body=urlencode(body).encode())


def refresh_exchange(
    consent: OAuthConsent, *, client_id: str, client_secret: str, refresh_token: str
) -> TokenExchange:
    """The post that renews access from the kept refresh token. See
    `ACCESS_IS_RENEWED_BY_THE_READ_THAT_NEEDS_IT`."""
    body = {
        "grant_type": "refresh_token",
        "refresh_token": _secret(refresh_token, "refresh token"),
        "client_id": client_id,
        "client_secret": _secret(client_secret, "client secret"),
    }
    return TokenExchange(url=consent.token_url, headers=FORM, body=urlencode(body).encode())


# ------------------------------------------------------------------------ the failures
class ConsentWithdrawnError(TokenNotIssuedError):
    """The vendor refused a renewal or a code: the consent is withdrawn. See `CONSENT_WITHDRAWN`."""

    def __init__(self) -> None:
        super().__init__(CallOutcome.REJECTED)


class ConsentNotHeldError(TokenNotIssuedError):
    """There is no refresh token to renew with: nobody has consented, or its slot is empty."""

    def __init__(self) -> None:
        super().__init__(CallOutcome.REJECTED)


class RotatedTokenNotKeptError(TokenNotIssuedError):
    """The vendor rotated the refresh token and the vault would not keep the new one."""

    def __init__(self) -> None:
        super().__init__(CallOutcome.UNAVAILABLE)


# ------------------------------------------------------------------------ the answer
@dataclass(frozen=True)
class OAuthTokens:
    """What a token endpoint issued: access for one read, and the refresh token when it sent one.

    A vendor that rotates its refresh tokens sends a new one with every renewal and voids the old;
    one that does not sends none after the first. Neither value is in any representation.
    """

    access: AccessToken
    refresh: str | None = field(default=None, repr=False)
    expires_in: int | None = None


def tokens_from(
    *,
    status: int | None,
    body: bytes,
    timed_out: bool = False,
    connection_failed: bool = False,
) -> OAuthTokens:
    """The tokens in a token endpoint's answer, or `TokenNotIssuedError` saying which failure.

    RFC 6749 section 5.2 answers a revoked, expired or unknown grant with 400 `invalid_grant`, and a
    client it no longer knows with 401, which `throttle.classify` reads as refusals: the consent is
    withdrawn (`CONSENT_WITHDRAWN`). A 429 and a 5xx are the endpoint's ill health. An answer longer
    than `MAX_TOKEN_ANSWER_BYTES`, or not the documented shape, is not an answer this reads.
    """
    call = classify(
        status=status, timed_out=timed_out, connection_failed=connection_failed or status is None
    )
    if call is not CallOutcome.OK:
        raise TokenNotIssuedError(call, timed_out=timed_out)
    if len(body) > MAX_TOKEN_ANSWER_BYTES:
        raise TokenNotIssuedError(CallOutcome.UNAVAILABLE)
    try:
        parsed: Any = json.loads(body)
    except ValueError:
        raise TokenNotIssuedError(CallOutcome.UNAVAILABLE) from None
    if not isinstance(parsed, dict):
        raise TokenNotIssuedError(CallOutcome.UNAVAILABLE)
    token, kind = parsed.get("access_token"), parsed.get("token_type")
    if not isinstance(token, str) or not isinstance(kind, str) or kind.casefold() != "bearer":
        raise TokenNotIssuedError(CallOutcome.UNAVAILABLE)
    refresh = parsed.get("refresh_token")
    if refresh is not None and (not isinstance(refresh, str) or not _GRANT_RE.match(refresh)):
        raise TokenNotIssuedError(CallOutcome.UNAVAILABLE)
    expires = parsed.get("expires_in")
    if expires is not None and (not isinstance(expires, int) or isinstance(expires, bool)):
        raise TokenNotIssuedError(CallOutcome.UNAVAILABLE)
    try:
        return OAuthTokens(access=AccessToken(token), refresh=refresh, expires_in=expires)
    except ConnectorContractError:
        raise TokenNotIssuedError(CallOutcome.UNAVAILABLE) from None
