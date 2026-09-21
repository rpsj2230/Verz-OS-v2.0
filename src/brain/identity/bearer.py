"""Turning an `Authorization` header into somebody the gate can compute a reach for.

`brain.identity.oidc` is a set of pure functions over a token that somebody else has to
hand it. Until this module there was nobody: `validate_token` had never been called by
anything that serves a request, `principal_for` had never been called at all outside a
test, and `brain.openapi.DOCUMENTED_BEFORE_IT_IS_ENFORCED` said so in as many words. A
validator nothing calls is the same shape as the timeout middleware nothing mounted, and
this repository has now found that shape nine times.

**Nothing here re-decides anything `oidc` already decides.** The order of checks, the
algorithm allow-list, the `kid` lookup, the issuer comparison, the audience rule, the
expiry and the not-before all live in `validate_token`, and this module's whole job is to
call it with the right arguments and to turn the two refusals it can produce into one
answer. A second opinion about any of those would be a second place for the wrong one to
win, which is what `CLAUDE.md` says about the intersection and is just as true here.

**An unconfigured authority accepts nothing.** The signature check is an injected callback,
and `brain.identity.keycloak_tokens.verify_rs256` is the one a deployed process holds:
`brain.app.lifespan` builds the authority through `keycloak_authority` when there is a
database and an issuer. A process with neither has no authority, and every request under the
versioned prefix is refused. That is the correct behaviour and it is stated rather than left
to be discovered: fail-closed is what a missing authenticator has to mean, and the
alternative, letting a request through when nothing could check it, is the bug that this
shape makes unrepresentable. See `AN_UNCONFIGURED_AUTHORITY_ACCEPTS_NOTHING`.

**Every refusal says one sentence.** `oidc.SIGN_IN_PROMPT` already argues why: "unknown
key" and "bad signature" and "wrong audience" tell somebody forging a token which part to
fix next, and the difference is invisible in a screenshot. The reason goes to the log as a
closed enumeration and never into the response.

**The assurance level is read from the token rather than assumed.** A password-only sign-in
and one carrying a second factor are not the same evidence, and `gate.admission` already
turns that difference into a ceiling: an `AUTHENTICATED` caller cannot exercise an `admin:`
or `approve:` capability however many grants they hold. Assuming `STRONG` would make that
ceiling decorative, and assuming `AUTHENTICATED` unconditionally would make a step-up flow
unbuildable without editing this file. So `amr` is read, against a deliberately short list
of values this realm can actually mint. See `A_SECOND_FACTOR_IS_A_CLAIM_ABOUT_THIS_SESSION`.

Rejected: reading `acr` and comparing it against a configured level of assurance. It is the
more standard mechanism and it is a number whose meaning is defined in the realm's own
authentication flow, so the comparison would be correct only for as long as nobody edited
that flow, and being wrong in the permissive direction is silent.

**A token from a session an administrator ended is refused, and the check is here rather than
at each route.** Revoking a grant does not close a sign-in, so M27.7.10 puts a control on the
Sessions screen that ends one, and a control is only real if the next request made with that
sign-in is refused. A bearer token is valid because of what is inside it, so nothing about ending
a row changes a token already in somebody's hand; what does is this function asking the ledger of
sessions, on every request that carries a `sid`, whether the session it names has been ended. The
ledger is asked through the directory the authority already holds, because the directory is the
store this object is built with and `brain.app.wirings_for` builds it once; a second store
threaded through every construction of this object would be a wiring somebody forgets. A
directory that keeps no ledger is asked nothing, which is every test double and no deployed
process. See `AN_ENDED_SESSION_IS_REFUSED_ON_ITS_NEXT_REQUEST`.

Rejected: middleware that authenticates every request and attaches a principal to the
request state. It reads better at each route and it fails open in the one case that
matters: a route mounted outside whatever path prefix the middleware matched on is a route
with no authentication, and nothing about it looks different. A dependency is named at each
route, so a route without one is visible in the diff that adds it, and
`tests/unit/test_api_routes.py` asserts over the mounted set rather than over a habit.

**A caller that is not a person is authenticated here too, and holds nothing of its own.** Two
credentials name a service account: a client-credentials token from the identity provider, which
carries no `sid` and whose subject a registered account names, and an API key minted on this
install (`brain.channels.api_keys`). Either way the caller comes back carrying the account and its
owner, and the owner is read live on every request: disabled, retired or past their end date, and
the account is refused with the sentence every refusal gets. What the account may then reach is
`brain.identity.sessions.reach_for`, asked by `brain.api_routes.asking` over the owner's reach as
the resolver answers it now, so a grant taken from the owner is taken from the account on the next
request. See `A_SERVICE_ACCOUNT_STOPS_WHEN_ITS_OWNER_DOES`.

**A key's claims say it was a key.** `Caller.claims` is what every route reads the session and the
verification from, so a key caller carries claims too: issued by `API_KEY_ISSUER`, never a `sid`,
verified by the key's handle with `API_KEY_METHOD`, from the moment it was issued to the moment it
lapses. Nothing in them is read off the presented string except the handle, and the handle is
what the key was looked up and checked by. Rejected: an optional `claims`, which every route that
reads a `sid` would have to learn to treat as absent, and the one that forgot would fail open on
the channel ceiling `channel_for` reads from it.

Scope: no network call is made here. The key set arrives through a `KeySource` the caller
supplies, which is what `oidc.JwksCache` already is.

Task ids: M1.1.2, M1.1.7, M1.8.2
"""

from __future__ import annotations

import asyncio
import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Final, Protocol, runtime_checkable

import structlog

from brain.channels.api_keys import PREFIX as API_KEY_PREFIX
from brain.channels.api_keys import ApiKeyError, ApiKeyRecord, handle_of
from brain.channels.api_keys import verify as verify_key
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.gate.admission import Assurance
from brain.identity.oidc import (
    DEFAULT_LEEWAY,
    KeySet,
    PrincipalDirectory,
    SignatureVerifier,
    SigningKey,
    TokenRefusal,
    TokenRefusedError,
    UnmappedSubject,
    VerifiedClaims,
    parse_unverified,
    principal_for,
    validate_token,
)
from brain.identity.sessions import (
    ServiceAccount,
    assurance_for_service_account,
    authenticate_service_account,
)

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why a missing authority refuses rather than waves a request through.
AN_UNCONFIGURED_AUTHORITY_ACCEPTS_NOTHING: Final = (
    "A request cannot be authenticated by a component that is not there. The tempting "
    "reading of a missing authority is 'authentication is switched off in this "
    "environment', which is the same code path in every environment and is decided by "
    "whether a variable happened to be set. So there is no branch here that produces a "
    "caller without a verified token: an absent authority is a refusal, and it is the "
    "same refusal a bad token gets, because a caller has no business learning which of "
    "the two happened."
)

#: Why the refusal never says which check failed.
EVERY_REFUSAL_SAYS_THE_SAME_SENTENCE: Final = (
    "Unknown key, bad signature, wrong audience and an expired token are one sentence to "
    "the presenter and four values in the log. Distinguishing them tells somebody forging "
    "a token which part to fix next, one attempt at a time, and the difference is "
    "invisible in a screenshot of the screen a real person is looking at."
)

#: Why the assurance level is read from the token rather than fixed.
A_SECOND_FACTOR_IS_A_CLAIM_ABOUT_THIS_SESSION: Final = (
    "Assurance is about now, not about the account. A token whose `amr` names a second "
    "factor is evidence that one was presented in the session this token came from; a "
    "token that names only a password is not. Fixing the level at AUTHENTICATED would "
    "make a step-up flow unreachable, and fixing it at STRONG would hand every "
    "password-only session the approve and admin verbs that gate.admission exists to "
    "withhold from them."
)

#: Why a session ended from the console refuses the tokens it goes on minting.
AN_ENDED_SESSION_IS_REFUSED_ON_ITS_NEXT_REQUEST: Final = (
    "Ending a session from the console writes a row, and a row changes nothing about a bearer "
    "token already in somebody's hand, which stays valid until it expires and is replaced by a "
    "fresh one from the same session at the identity provider. So every request carrying a sid "
    "asks the ledger of sessions about it, and one the ledger says was ended is refused with the "
    "same sentence every refusal gets. The session is the unit, not the person: somebody whose "
    "session was ended may sign in again, which opens another, and stopping that is the grant "
    "decision or the sign-in link rather than this."
)

#: Why an integration is refused the moment its owner could not sign in.
A_SERVICE_ACCOUNT_STOPS_WHEN_ITS_OWNER_DOES: Final = (
    "A service account borrows its owner's reach and holds nothing of its own. Its owner is read "
    "on every request, and an owner who is disabled, retired or past their end date leaves the "
    "account refused with the same sentence a bad token gets, so an integration cannot outlive "
    "the person who answers for it."
)

#: The issuer a key caller's claims name. Not a URL, so it can never equal a realm's issuer.
API_KEY_ISSUER: Final = "brain:api-key"

#: What verified a key caller, in the claims' `algorithm` field. `brain.channels.api_keys`.
API_KEY_METHOD: Final = "brn-sha256"

#: Why the key source is asked on a worker thread.
A_KEY_FETCH_NEVER_HOLDS_THE_EVENT_LOOP: Final = (
    "The route that authenticates is a coroutine on the event loop every request in the "
    "process shares, and a key-set fetch is a blocking HTTP call of up to five seconds. "
    "Made on the loop, one cold cache or one rotated key stops every request, the health "
    "check included, for as long as the identity provider takes to answer. So the key "
    "source is asked on a worker thread, cached answers included, which costs a thread hop "
    "per request and leaves KeySource synchronous for every source that satisfies it. "
    "Rejected: an awaitable KeySource over an async HTTP client, which would put "
    "JwksCache's refetch floor and stale grace behind an await, a rewrite of the cache "
    "oidc already has, to gain nothing a thread does not."
)


# --------------------------------------------------------------------- the pieces

#: `amr` values that count as a second factor actually presented.
#:
#: Deliberately short. RFC 8176 registers around twenty methods and most of them are ways of
#: describing a first factor: `pwd`, `pin` and `user` are all somebody typing a secret they
#: know. Widening this list would raise the assurance of a session on the strength of a value
#: this realm has never been observed to mint, and the failure is silent and permissive.
#:
#: **Keycloak mints none of these by itself.** This comment said until 2026-09-17 that it emits
#: `mfa` after a multi-factor sign-in and `otp` from its OTP form, and Keycloak 26.0.0 does
#: neither: `oidc-amr-mapper` writes only the reference value an administrator configured on
#: each completed step, and no built-in scope carries that mapper. The realm minted nothing,
#: every token was AUTHENTICATED, and every admin screen refused everybody on the owner's
#: staging install. `otp` is minted now because `ops/keycloak/realm-export.json` configures it
#: on the OTP form, and `test_keycloak_realm.py` holds that value to this set. `mfa` is RFC
#: 8176's value for a sign-in that used more than one factor, and `hwk` is a hardware key, the
#: factor a company would move to next; both are second factors by definition.
SECOND_FACTOR_METHODS: Final[frozenset[str]] = frozenset({"mfa", "otp", "hwk"})

#: The scheme the `Authorization` header must name, compared case-insensitively because the
#: header's scheme token is case-insensitive by RFC 7235 and a client that sends `bearer` is
#: correct.
BEARER_PREFIX: Final = "bearer"


class SessionStanding(enum.StrEnum):
    """What the ledger of sign-in sessions says about the one a token came from."""

    #: Recorded, belonging to this principal, and not ended. Recorded now if it was not.
    OPEN = "open"
    #: Ended before it lapsed: from the console, by a disable or by a retirement.
    ENDED = "ended"
    #: Recorded against a different principal. The catastrophic case, refused on one comparison,
    #: which is `brain.identity.sessions.SessionRegistry.admit`'s own check.
    SOMEBODY_ELSES = "somebody_elses"


@runtime_checkable
class SessionLedger(Protocol):
    """The sign-in sessions this installation has seen. `brain.identity.session_store` holds it.

    Asked of the directory rather than held beside it; see the module docstring. `started_at` is
    `started_at_of` the token, and the ledger records it only when it has not seen the session.
    """

    async def standing(
        self,
        *,
        session_id: str,
        principal_id: str,
        assurance: Assurance,
        started_at: datetime,
        now: datetime,
    ) -> SessionStanding:
        """Record the session if it is new, and say whether it may still be used."""
        ...


def started_at_of(claims: VerifiedClaims) -> datetime:
    """When the session a token came from began, as well as the token can say.

    `auth_time` when the token carries one that is a whole number of seconds no later than its
    own issue time, and the issue time otherwise. A later `auth_time` than `iat` is a clock or a
    realm misconfigured, and trusting it would record a session as starting after the token it
    was read from; a boolean is refused because it is an `int` to Python and a session starting
    one second after the epoch is not a fact.
    """
    raw = claims.claim("auth_time")
    if isinstance(raw, int) and not isinstance(raw, bool):
        began = datetime.fromtimestamp(raw, tz=UTC)
        if began <= claims.issued_at:
            return began
    return claims.issued_at


class KeySource(Protocol):
    """Where the issuer's current signing keys come from.

    A protocol rather than a `KeySet` so that key rotation is somebody's job rather than a
    restart. `oidc.JwksCache` satisfies it, including the rate-limited refetch when an
    unrecognised `kid` appears mid-window.
    """

    def keys_for(self, issuer: str, now: datetime) -> KeySet: ...

    def key_for(self, issuer: str, kid: str, now: datetime) -> SigningKey: ...


@runtime_checkable
class ServiceAccountDirectory(Protocol):
    """The registered service accounts, their keys and their owners.

    `brain.identity.principal_directory.StoredDirectory` implements it over the database. Asked of
    the directory rather than held beside it, for the reason `SessionLedger` is.
    """

    async def service_account_for_subject(self, subject: str) -> ServiceAccount | None: ...

    async def service_account_for_key(
        self, handle: str
    ) -> tuple[ApiKeyRecord, ServiceAccount] | None: ...

    async def live_owner(self, principal_id: str) -> Principal | None: ...


def principal_of(account: ServiceAccount) -> Principal:
    """The account as the principal a route and the ledger name: its own id, never its owner's."""
    return Principal(
        id=account.client_id,
        kind=PrincipalKind.SERVICE,
        employment=Employment.SERVICE,
        display_name=account.client_id,
        not_after=account.not_after,
    )


def key_claims(record: ApiKeyRecord, *, audience: str, now: datetime) -> VerifiedClaims:
    """What a checked key is worth as claims. See the module docstring on why a key has them."""
    return VerifiedClaims(
        issuer=API_KEY_ISSUER,
        subject=record.client_id,
        audience=(audience,),
        issued_at=record.issued_at,
        expires_at=record.not_after,
        session_id=None,
        key_id=record.handle,
        algorithm=API_KEY_METHOD,
        verified_at=now,
        claims=MappingProxyType({"azp": record.client_id}),
    )


@dataclass(frozen=True)
class Caller:
    """A verified person, and how strongly we know it is them, right now.

    Three fields and no entitlement. Reach is resolved per request from grants this company
    writes, and carrying a set on the caller would be an invitation to compute it once at
    sign-in and reuse it, which is how a revocation stops taking effect until somebody logs
    out.

    `claims` is kept because an audit entry that says "verified by kid abc123 at 09:14" can
    be argued with and "trusted" cannot, and because the session id is what a logout has to
    match against.
    """

    principal: Principal
    claims: VerifiedClaims
    assurance: Assurance
    #: The integration this caller is, and the live person whose reach it borrows. Both or
    #: neither: `brain.api_routes.asking` computes the reach from the pair.
    service_account: ServiceAccount | None = None
    owner: Principal | None = None

    @property
    def principal_id(self) -> str:
        return self.principal.id


def assurance_from(claims: VerifiedClaims) -> Assurance:
    """How strongly this token's own session authenticated the person (M3.3.4 input).

    `AUTHENTICATED` is the floor rather than the default, and the distinction matters: this
    function is only ever reached with claims that `validate_token` has already accepted, so
    there is a live, signed, in-date credential from the right issuer for the right audience.
    That is an authenticated session by definition. What is being decided here is only
    whether to go one rung higher.

    An `amr` that is absent, empty, or not a list of strings leaves the floor, and does not
    raise: Keycloak emits `amr` only when the flow was configured to, so its absence is the
    ordinary case at a client who has not turned on a second factor, and refusing the token
    over it would stop everybody signing in to gain nothing.
    """
    raw = claims.claim("amr")
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        # A string `amr` is refused rather than split. A single-valued claim spelled as a
        # string is a real shape, and splitting it would mean choosing a separator, which is
        # a guess that decides whether somebody holds the approve verb.
        return Assurance.AUTHENTICATED
    methods = {value for value in raw if isinstance(value, str)}
    if methods & SECOND_FACTOR_METHODS:
        return Assurance.STRONG
    return Assurance.AUTHENTICATED


def token_from_header(header: str | None) -> str:
    """The compact token out of an `Authorization` header, or a refusal.

    Refuses rather than returning None, for the reason `oidc.JwksCache.key_for` refuses: a
    caller holding an optional token is one `if token is None: token = ""` away from handing
    an empty string to the parser, and an empty string is a malformed token rather than an
    absent credential. Here the two are the same refusal anyway, which is the point.
    """
    if not header:
        raise TokenRefusedError(TokenRefusal.MALFORMED, "no authorization header")
    scheme, _, rest = header.partition(" ")
    if scheme.strip().lower() != BEARER_PREFIX:
        # The scheme is named in the log and not in the response. A caller sending Basic
        # authentication has made a mistake worth telling an operator about, and telling the
        # sender that Bearer is the accepted scheme is already in the published document.
        raise TokenRefusedError(TokenRefusal.MALFORMED, f"scheme {scheme.strip()!r} is not bearer")
    value = rest.strip()
    if not value:
        raise TokenRefusedError(TokenRefusal.MALFORMED, "bearer scheme with no token")
    return value


@dataclass(frozen=True)
class TokenAuthority:
    """Everything needed to turn a header into a caller, held once per process.

    One object rather than four arguments threaded through the routes, because the four have
    to agree: a key source for one issuer and an `expected_issuer` naming another is a
    configuration that accepts nothing and explains itself as a bad signature. Holding them
    together means the mismatch is visible where the thing is built.

    `verify` is injected and there is no default. `oidc.SignatureVerifier` explains why: the
    standard library cannot verify RS256, and a verifier written here would be the worst thing
    in the repository. `keycloak_tokens.verify_rs256`, over the `cryptography` library, is the
    one `keycloak_authority` puts here, and `brain.app.lifespan` is what builds it. A route asks
    for one of these and there is nowhere else to get a caller from.
    """

    issuer: str
    audience: str
    keys: KeySource
    verify: SignatureVerifier
    directory: PrincipalDirectory
    leeway: timedelta = DEFAULT_LEEWAY

    async def authenticate(self, header: str | None, *, now: datetime) -> Caller:
        """A verified caller, or `TokenRefusedError`. Never anything in between.

        The `kid` is read off the unverified header before validation, and only to give the
        key source a chance to refetch after a rotation. Nothing is decided by that read:
        `validate_token` reads the same field again, checks it against the allow-list, looks
        it up in the key set it is handed, and refuses if the two disagree. Warming a cache
        with an attacker-controlled string is safe precisely because the value is re-derived
        and re-checked on the path that matters, and skipping the warm would mean a rotated
        key refusing every sign-in in the company until a TTL expired.
        """
        presented = token_from_header(header)
        if presented.startswith(f"{API_KEY_PREFIX}."):
            return await self._key_caller(presented, now=now)
        raw = parse_unverified(presented)

        # On a worker thread. See A_KEY_FETCH_NEVER_HOLDS_THE_EVENT_LOOP.
        keys = await asyncio.to_thread(self._current_keys, raw.header.get("kid"), now)

        claims = validate_token(
            raw,
            keys=keys,
            verify=self.verify,
            expected_issuer=self.issuer,
            expected_audience=self.audience,
            now=now,
            leeway=self.leeway,
        )

        if claims.session_id is None and isinstance(self.directory, ServiceAccountDirectory):
            account = await self.directory.service_account_for_subject(claims.subject)
            if account is not None:
                checked = authenticate_service_account(claims, {claims.subject: account}, now)
                return await self._account_caller(checked, claims, now=now)

        found = await principal_for(claims, self.directory, now=now)
        if isinstance(found, UnmappedSubject):
            # A valid token from somebody with no live principal here. `oidc` argues why this
            # is not an empty `Principal`: an empty one type-checks everywhere a real one
            # does, flows into the gate, resolves to an empty reach, and produces a confident
            # "I could not find that" for a person who should have been told to ask an
            # administrator. The subject and issuer are recorded because an operator asked
            # "why can Priya not sign in" cannot answer without them, and because a Keycloak
            # `sub` is an opaque uuid rather than a phone number.
            raise TokenRefusedError(
                TokenRefusal.NO_PRINCIPAL, f"{claims.subject} at {claims.issuer}"
            )

        assurance = assurance_from(claims)
        if claims.session_id is not None and isinstance(self.directory, SessionLedger):
            # See AN_ENDED_SESSION_IS_REFUSED_ON_ITS_NEXT_REQUEST.
            standing = await self.directory.standing(
                session_id=claims.session_id,
                principal_id=found.id,
                assurance=assurance,
                started_at=started_at_of(claims),
                now=now,
            )
            if standing is SessionStanding.ENDED:
                raise TokenRefusedError(TokenRefusal.LOGGED_OUT, claims.session_id)
            if standing is SessionStanding.SOMEBODY_ELSES:
                raise TokenRefusedError(TokenRefusal.SESSION_MISMATCH, claims.session_id)
        return Caller(principal=found, claims=claims, assurance=assurance)

    async def _key_caller(self, presented: str, *, now: datetime) -> Caller:
        """The caller behind an API key, or the one refusal. See the module docstring."""
        if not isinstance(self.directory, ServiceAccountDirectory):
            raise TokenRefusedError(TokenRefusal.UNKNOWN_SERVICE_ACCOUNT, "no accounts here")
        try:
            handle = handle_of(presented)
        except ApiKeyError as exc:
            raise TokenRefusedError(TokenRefusal.MALFORMED, "not an api key") from exc
        found = await self.directory.service_account_for_key(handle)
        if found is None:
            raise TokenRefusedError(TokenRefusal.UNKNOWN_SERVICE_ACCOUNT, handle)
        record, account = found
        try:
            checked = verify_key(presented, record, account, now=now)
        except ApiKeyError as exc:
            raise TokenRefusedError(TokenRefusal.SERVICE_ACCOUNT_EXPIRED, record.handle) from exc
        return await self._account_caller(
            checked, key_claims(record, audience=self.audience, now=now), now=now
        )

    async def _account_caller(
        self, account: ServiceAccount, claims: VerifiedClaims, *, now: datetime
    ) -> Caller:
        """The account as a caller, with its owner read now.

        See `A_SERVICE_ACCOUNT_STOPS_WHEN_ITS_OWNER_DOES`.
        """
        if not isinstance(self.directory, ServiceAccountDirectory):
            raise TokenRefusedError(TokenRefusal.UNKNOWN_SERVICE_ACCOUNT, account.client_id)
        owner = await self.directory.live_owner(account.owner_principal_id)
        if owner is None or not owner.is_active(now):
            raise TokenRefusedError(TokenRefusal.OWNER_INACTIVE, account.client_id)
        return Caller(
            principal=principal_of(account),
            claims=claims,
            assurance=assurance_for_service_account(account, now),
            service_account=account,
            owner=owner,
        )

    def _current_keys(self, kid: object, now: datetime) -> KeySet:
        """The key set to validate against, after warming it for the token's `kid`.

        Blocking, because a fetch is, and so called only through `asyncio.to_thread`.
        """
        if isinstance(kid, str) and kid:
            self.keys.key_for(self.issuer, kid, now)
        return self.keys.keys_for(self.issuer, now)


async def authenticate(
    authority: TokenAuthority | None, header: str | None, *, now: datetime
) -> Caller:
    """The only way a request becomes a caller, including when nothing is configured.

    The `None` case is handled here rather than at each route, so that "this deployment has
    no authority" and "this token is not acceptable" are one refusal produced by one line.
    Handled at the route it would be a branch per route, and the route that forgot it would
    be a route serving unauthenticated traffic while every other one refused.

    See `AN_UNCONFIGURED_AUTHORITY_ACCEPTS_NOTHING`.
    """
    if authority is None:
        raise TokenRefusedError(
            TokenRefusal.NO_KEYS_AVAILABLE, "no token authority is configured on this process"
        )
    return await authority.authenticate(header, now=now)


def log_refusal(error: TokenRefusedError, *, path: str) -> None:
    """One log line per refused credential, with the reason and never the token.

    The token is deliberately absent, including a prefix of it. A bearer token is a
    credential for as long as it is valid, and a log store is read by more people and kept
    for longer than the ten minutes an access token lives. The `kid` and the subject are
    equally absent, because both come from a token nothing has verified and recording an
    unverified claim as though it were a fact is how a log becomes evidence of something
    that did not happen.
    """
    log.warning("credential refused", reason=str(error.reason), path=path)


def refusal_headers() -> Mapping[str, str]:
    """What a 401 carries so a client knows what to present.

    `Bearer` and the realm are omitted deliberately: the realm parameter is a free-text
    label that installations fill in with the identity provider's URL, and a refusal is not
    the place to publish where the identity provider lives to somebody who has not
    authenticated. The scheme alone is what a client actually needs.
    """
    return {"www-authenticate": "Bearer"}
