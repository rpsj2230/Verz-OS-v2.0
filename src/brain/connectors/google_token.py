"""A connected Google source's key file, exchanged for a token that reads one thing, briefly.

Google Analytics and Search Console are both read with a service account's key file, the file
Google Cloud downloads when a key is created and the console keeps whole in the vault
(`brain.connectors.declaration.CredentialShape.KEY_FILE`). Neither API takes the file: each takes a
bearer token, which the OAuth 2.0 JWT bearer grant issues for an RS256-signed claim set naming the
account and the scope it asks for. **This module is that exchange, once, for both sources**: what is
signed, what is sent and what is read back. Two connectors each writing it would be two opinions
about which scope a token may carry, and the one that drifted would be the one nobody re-read.

**The account reads as itself and never as a person.** The claim set carries no `sub`, so Google
issues a token for the service account alone, which reaches the one property or site it was added to
and nothing else. A `sub` would make it act as somebody in the company's domain, which only
domain-wide delegation permits and which no scope narrows to one property. The directory's reading
signs with a subject because the Directory API answers only an administrator
(`brain.connectors.google_service_account.DELEGATION_IS_NARROWED_BY_SCOPE`); a connected source is
the case that needs none. See `A_CONNECTED_GOOGLE_SOURCE_READS_AS_ITS_SERVICE_ACCOUNT`.

**Only a read-only scope is ever asked for.** A scope is checked before anything is signed, and one
that is not Google's own `.readonly` form is refused, so a declaration edited to ask for
`analytics.edit` fails where it is built rather than at Google. See
`ONLY_A_READ_ONLY_SCOPE_IS_EVER_ASKED_FOR`.

**The token lives as long as the read that needed it.** It is minted where the key is already held
for one request (the worker's run, a connection's test, a question's live read, all in
`brain.ops.connector_sync_run` and `brain.ops.live_read_run`), sent in one header and dropped with
the call. It is never cached, kept, logged or put in an exception: `AccessToken` leaves its value
out of its representation, and every refusal here is a `CallOutcome` and never the reply's text.
Rejected: keeping a token for its hour to save one round trip per question. A token that outlives
its read is a credential held in memory between requests, readable by anything that can read the
process, and the round trip is a question for the answer lane's budget rather than a reason to hold
one. See `WHAT_A_KEY_FILE_BUYS_LIVES_AS_LONG_AS_THE_READ`.

**A key file is never presented as a token.** `AccessToken` is a type of its own, and
`brain.ops.connector_sync_run.authorization` refuses a Google source's header built from anything
else, so a path that forgot the exchange sends nothing rather than the private key. See
`A_KEY_FILE_IS_NEVER_SENT_IN_A_HEADER`.

**The address is Google's own and a constant.** A key file names a `token_uri`, and it is not read,
for `google_service_account.A_KEY_FILE_DOES_NOT_CHOOSE_WHERE_ITS_SIGNATURE_GOES`' reason.

Rejected: `google-auth`, for the directory module's reason: a dependency, its transitive
dependencies and a release schedule for about forty lines, and a client that opens its own sockets
where every call here goes through the pinned, address-checked caller the other sources use.

Scope: domain logic. Nothing here opens a socket or reads a clock: the instant is handed in, and
the call is made by whoever holds the key.

Task ids: M11.7.1
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import urlencode

from brain.connectors.contract import ConnectorContractError
from brain.connectors.google_service_account import (
    JWT_BEARER,
    ServiceAccountKeyError,
    key_of,
    signed_assertion,
)
from brain.connectors.staff_directories import GOOGLE_EXCHANGE_URL
from brain.connectors.throttle import CallOutcome, classify

# ------------------------------------------------------------------ written-down reasons
#: Why the claim set names no subject.
A_CONNECTED_GOOGLE_SOURCE_READS_AS_ITS_SERVICE_ACCOUNT: Final = (
    "A connected Google source is read by a service account added to one property or one site, "
    "and its token is issued for that account alone: the claim set names no subject. A subject "
    "would have it act as a person in the company's domain, which only domain-wide delegation "
    "permits, and no scope narrows delegation to one property."
)

#: Why a scope that is not read-only is refused before anything is signed.
ONLY_A_READ_ONLY_SCOPE_IS_EVER_ASKED_FOR: Final = (
    "A token carries the scopes its claim set asked for, and Google grants a service account "
    "whatever the property's owner allowed it. Asking only for Google's own read-only scopes "
    "means a token this product holds cannot change a property or a site whatever the account "
    "was granted, so a scope outside that form is refused where the claim set is built."
)

#: Why a token is minted per read and never kept.
WHAT_A_KEY_FILE_BUYS_LIVES_AS_LONG_AS_THE_READ: Final = (
    "A token is minted where the key is already held for one request, sent in one header and "
    "dropped with the call. Kept for its hour it would be a credential in memory between "
    "requests, readable by anything that can read the process, to save one round trip."
)

#: Why a Google source's header is only ever built from an exchanged token.
A_KEY_FILE_IS_NEVER_SENT_IN_A_HEADER: Final = (
    "A Google source's key is a key file with a private key in it, and the header its API reads "
    "carries a token. A path that forgot the exchange would send the file itself, so the header "
    "is built only from an AccessToken, which only this module's exchange produces."
)

# --------------------------------------------------------------------- the figures
#: Where every assertion is sent. Google's own, for every install.
GOOGLE_TOKEN_URL: Final = GOOGLE_EXCHANGE_URL

#: Where Google names every OAuth scope, for every install.
GOOGLE_SCOPES_BASE_URL: Final = "https://www.googleapis.com/auth/"

#: A scope this module will ask for: Google's own address for a read-only scope, and nothing else.
READ_ONLY_SCOPE: Final = re.compile(
    "^" + re.escape(GOOGLE_SCOPES_BASE_URL) + r"[a-z]+(\.[a-z]+)*\.readonly$"
)

#: The largest answer the token endpoint is read to. Google's is a few hundred characters.
MAX_TOKEN_ANSWER_BYTES: Final = 16_384

#: What a token may be spelled with: one unbroken run of printable characters, as RFC 6750 says.
_TOKEN_RE: Final = re.compile(r"^[A-Za-z0-9._~+/=-]{1,4096}$")

#: The type of token Google issues for a JWT bearer grant, compared without case.
BEARER: Final = "bearer"


class TokenNotIssuedError(Exception):
    """Google did not issue a token, and the call's outcome says which kind of failure it was.

    Carries no text from the reply, which can quote the assertion, and no key.
    """

    def __init__(self, call: CallOutcome, *, timed_out: bool = False) -> None:
        super().__init__(f"no token was issued: {call.value}")
        self.call = call
        self.timed_out = timed_out


@dataclass(frozen=True)
class AccessToken:
    """A token Google issued for one read. Its value is left out of every representation."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not _TOKEN_RE.match(self.value):
            msg = "an access token is one unbroken run of printable characters"
            raise ConnectorContractError(msg)

    def __str__(self) -> str:
        return "AccessToken(...)"


@dataclass(frozen=True)
class TokenExchange:
    """The one request that exchanges a signed assertion: its address, headers and form body."""

    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes = field(repr=False)


def checked_scopes(scopes: Sequence[str]) -> tuple[str, ...]:
    """The scopes, or a refusal when there are none or one is not read-only.

    See `ONLY_A_READ_ONLY_SCOPE_IS_EVER_ASKED_FOR`.
    """
    given = tuple(scopes)
    if not given:
        msg = "a token is asked for with at least one scope, or it reads nothing"
        raise ConnectorContractError(msg)
    for one in given:
        if not READ_ONLY_SCOPE.match(one):
            msg = (
                f"{one!r} is not a read-only Google scope. "
                f"{ONLY_A_READ_ONLY_SCOPE_IS_EVER_ASKED_FOR}"
            )
            raise ConnectorContractError(msg)
    return given


def exchange(key_file: str, scopes: Sequence[str], *, now: int) -> TokenExchange:
    """The request that exchanges this key file for a token carrying these scopes, as itself.

    Raises `TokenNotIssuedError` as a refusal when the file is not a service account's key, since
    Google would decline it too; the words of `ServiceAccountKeyError` stay here, because they
    were written for the person pasting a file and nobody pasted anything on this path.
    """
    asked = checked_scopes(scopes)
    try:
        issuer, key = key_of(key_file)
    except ServiceAccountKeyError:
        raise TokenNotIssuedError(CallOutcome.REJECTED) from None
    signed = signed_assertion(issuer=issuer, key=key, scopes=asked, now=now, subject=None)
    return TokenExchange(
        url=GOOGLE_TOKEN_URL,
        headers=(
            ("Content-Type", "application/x-www-form-urlencoded"),
            ("Accept", "application/json"),
        ),
        body=urlencode({"grant_type": JWT_BEARER, "assertion": signed}).encode("ascii"),
    )


def token_from(
    *,
    status: int | None,
    body: bytes,
    timed_out: bool = False,
    connection_failed: bool = False,
) -> AccessToken:
    """The token in Google's answer, or `TokenNotIssuedError` saying what kind of failure it was.

    Google answers a revoked or unknown key with 400 `invalid_grant` and a disabled account with
    401, which `throttle.classify` reads as refusals; a 429 and a 5xx are the endpoint's ill health.
    An answer that is not the documented shape is read as a source that did not answer in a shape
    this reads, the same as a page that disagrees with its declaration.
    """
    call = classify(
        status=status, timed_out=timed_out, connection_failed=connection_failed or status is None
    )
    if call is not CallOutcome.OK:
        raise TokenNotIssuedError(call, timed_out=timed_out)
    try:
        parsed: Any = json.loads(body)
    except ValueError:
        raise TokenNotIssuedError(CallOutcome.UNAVAILABLE) from None
    if not isinstance(parsed, dict):
        raise TokenNotIssuedError(CallOutcome.UNAVAILABLE)
    token, kind = parsed.get("access_token"), parsed.get("token_type")
    if not isinstance(token, str) or not isinstance(kind, str) or kind.casefold() != BEARER:
        raise TokenNotIssuedError(CallOutcome.UNAVAILABLE)
    try:
        return AccessToken(token)
    except ConnectorContractError:
        raise TokenNotIssuedError(CallOutcome.UNAVAILABLE) from None
