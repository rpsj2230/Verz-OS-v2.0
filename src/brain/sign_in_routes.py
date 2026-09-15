"""The two ways a Keycloak subject is bound to a principal over HTTP, and nothing else.

`brain.identity.sign_in_binding` writes a binding and `brain.setup_wizard.finish` decides when
the first one may be written without an administrator. Neither had a route, so a deployed gate
would refuse every valid token as having no principal, for ever: a subject signs in only once
an administrator binds it, and binding needs an administrator signed in. This module adds the
two routes and no rule of its own about what may be bound to what.

**The finishing screen, `POST /setup/sign-in`, is the way out of that circle, and it is used
once.** The installer signs in to Keycloak through the console's own authorisation code flow
with PKCE (`console/src/auth/session.ts`, which already runs against the configured issuer),
and presents the resulting access token here with the setup code and the principal the wizard
appointed. The token is verified by the process's real `TokenAuthority`, the same key source,
signature check, issuer, audience and lifetime every request is held to, and its subject is
bound to that principal with `firstrun.GRANTED_BY` as the binder. The screen is open only
while no sign-in is bound anywhere on the install, which is `setup_wizard.finish`'s rule.

**The token is verified without asking who it is.** `TokenAuthority.authenticate` ends by
looking the subject up in the directory, and an unbound subject is refused as `NO_PRINCIPAL`,
which on this screen is every subject there is. So `verified_claims` calls the same pieces
`authenticate` calls, in the same order, and stops before the directory. It decides nothing
`oidc.validate_token` does not; see `THE_FINISHING_SCREEN_VERIFIES_WITHOUT_ASKING_WHO`.
The cleaner home is a `claims_for` split out of `authenticate` in `brain.identity.bearer`, which
is somebody else's file today, and the commit introducing this says so.

**Every refusal on the finishing screen after the token is one answer.** A finished install, a
wrong or expired code, a principal who is not an administrator, a token from a session-less
client and an install with no setup code at all are one 404 with one body, so somebody holding
an old code learns that there is nothing here and never who is signed in or why. A token that is
not acceptable is the 401 every route gives, because what it discloses is about the token and
nothing about the install. See `EVERY_REFUSAL_ON_THE_FINISHING_SCREEN_IS_ONE_ANSWER`.

**The administrator's route, `POST /api/v1/sign-ins`, requires `SIGN_IN_AUTHORITY` over
everything.** Held in part of the company is not held: a binding is a way into any principal,
and no scope can be checked against a principal who cannot yet sign in to have attributes read.
The capability is an `admin:` verb, so `gate.admission` already withholds it from a token with
no session and from a password-only session, and this route adds nothing to that. See
`A_SIGN_IN_IS_BOUND_BY_AN_ADMINISTRATOR_OVER_EVERYTHING`.

**Which refusals an administrator is told, and which are one answer.** A caller without the
capability and a principal who is not here, disabled or deleted are one 404 with one body, so
the route cannot be used to ask which principals exist. What the binder refuses for a principal
who is here, a subject held elsewhere, a principal already signing in, a subject not exactly as
a token carries it, binding one's own sign-in, is told to the administrator by its code in a
409, because each is something they must act on and none names another person. See
`A_BINDING_YOU_MAY_NOT_MAKE_AND_A_PRINCIPAL_NOT_HERE_ARE_ONE_ANSWER`.

**Who did it is written by the database.** `0047`'s trigger appends the `sign_in` entry to the
ledger in the binding's own transaction, naming the actor `SignInBindings.bind` sets: the
administrator's principal, with their reach's digest and the request's trace id, or `first-run`
on the finishing screen, which is who `firstrun.first_administrator` already records as the
author of the first administrator's grant.

**Where things come from.** `app.state.sign_in_bindings`, a `SignInWriter`, and none is a fault
identical for every caller; `app.state.gate` for the token authority and the entitlement store;
`app.state.settings` for the setup enrolment. Nothing here reads the environment.

Rejected: binding the first administrator from the command line on the server. It needs no
route and no setup code, and it is the shape an operator reaches for, and it moves the first
sign-in off the wizard the client is holding onto a shell they may not have, which M42.5.14
names as the screen that hands them into the console signed in.

Rejected: letting the finishing screen accept a subject in the body, as the administrator's
route does. It would need no Keycloak round trip, and it would let whoever holds the setup code
bind any account at all to the widest role, including one they do not control, which the token
proves they do.

Task ids: M42.5.14, M1.2.2
"""

from __future__ import annotations

import asyncio
import enum
from datetime import UTC, datetime
from typing import Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, wiring_of
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, BrainError, Failed
from brain.firstrun import GRANTED_BY, Enrolment
from brain.gate.resolve import EntitlementStore
from brain.identity.bearer import TokenAuthority, token_from_header

# Re-exported, because the route tests read the capability from this module.
from brain.identity.first_administrator import SIGN_IN_AUTHORITY as SIGN_IN_AUTHORITY
from brain.identity.first_administrator import holds_everywhere
from brain.identity.oidc import (
    KeySet,
    TokenRefusal,
    TokenRefusedError,
    VerifiedClaims,
    parse_unverified,
    validate_token,
)
from brain.identity.sign_in_binding import Binding, BindingRefusal, SignInBindingRefusedError
from brain.settings import Settings
from brain.setup_wizard import MAX_ANSWER_CHARS, WizardError, finish

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why the finishing screen checks a token without the directory.
THE_FINISHING_SCREEN_VERIFIES_WITHOUT_ASKING_WHO: Final = (
    "authenticate ends by asking the directory who the subject is, and on the finishing screen "
    "the subject is bound to nobody, because binding it is what the screen is for. So the "
    "token is held to everything authenticate holds it to, the key source warmed for its kid, "
    "the signature, issuer, audience and lifetime through validate_token, and the directory is "
    "not asked. Nothing is decided here that validate_token does not decide."
)

#: Why the finishing screen gives one answer after the token.
EVERY_REFUSAL_ON_THE_FINISHING_SCREEN_IS_ONE_ANSWER: Final = (
    "The finishing screen is reachable by anybody who finds the address. A finished install, a "
    "wrong code, a principal who is not an administrator, a session-less token and an install "
    "with no code are one 404, so nobody learns whether the install is finished, whether their "
    "code was ever right, or which principal is the administrator. The reason goes to the log."
)

#: Why the administrator's route wants the capability over everything.
A_SIGN_IN_IS_BOUND_BY_AN_ADMINISTRATOR_OVER_EVERYTHING: Final = (
    "A binding is a way into a principal, and a principal who does not sign in yet has nothing "
    "a scope can be checked against from here. So SIGN_IN_AUTHORITY held in part of the company "
    "is not held: a department administrator binding an account to a principal outside their "
    "department would otherwise be one request, and nothing would say it was out of scope."
)

#: Why some binder refusals are told and one is not.
A_BINDING_YOU_MAY_NOT_MAKE_AND_A_PRINCIPAL_NOT_HERE_ARE_ONE_ANSWER: Final = (
    "A caller without the capability and a principal who is absent, disabled or deleted are "
    "one 404, so the route is not a way to ask which principals exist. The other refusals "
    "concern a principal the administrator may bind, name nobody else, and are each something "
    "the administrator has to act on, so they are told by code in a 409."
)

#: Why a token with no session cannot become the first administrator's sign-in.
A_CALLER_WITH_NO_SESSION_IS_NOT_A_SIGN_IN: Final = (
    "A token carrying no sid came from no interactive session: it is a client credential, a "
    "secret in a configuration file. Bound as the first administrator's sign-in it would make "
    "the widest role in the system a file, which gate.admission refuses the admin verb for."
)

# --------------------------------------------------------------------- the figures

#: `SIGN_IN_AUTHORITY`, the capability that binds a sign-in, is imported from
#: `brain.identity.first_administrator` beside `holds_everywhere`, because the wizard's count of
#: administrators and this module's check are one test. It is an `admin:` verb, so admission
#: withholds it from a session-less token and a password-only session before this module is asked.

#: Where the administrator's route and the finishing screen are served.
SIGN_INS_PATH: Final = f"{API_PREFIX}/sign-ins"
FINISH_PATH: Final = "/setup/sign-in"

#: The longest subject or principal id accepted. A ceiling on a paste: a Keycloak subject is a
#: 36-character uuid and a principal id is bounded well below this by its column.
MAX_IDENTIFIER_CHARS: Final = 255

#: Binder refusals that are the same answer as a caller without the capability.
ONE_ANSWER: Final[frozenset[BindingRefusal]] = frozenset({BindingRefusal.NO_LIVE_PRINCIPAL})


# ------------------------------------------------------------------------ the writer


@runtime_checkable
class SignInWriter(Protocol):
    """What these routes need from the bindings store. `SignInBindings` implements it."""

    @property
    def issuer(self) -> str:
        """The issuer every binding is written at."""
        ...

    async def sign_ins(self) -> int:
        """How many live sign-in bindings the install holds."""
        ...

    async def bind(
        self,
        subject: str,
        *,
        principal_id: str,
        bound_by: str,
        now: datetime,
        ent_hash: str = "",
        trace_id: str = "",
    ) -> Binding:
        """Bind, or raise `SignInBindingRefusedError`."""
        ...


# ------------------------------------------------------------------------ the shapes


class SignInAsked(BaseModel):
    """What an administrator binds: a subject as Keycloak issues it, and a principal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str = Field(max_length=MAX_IDENTIFIER_CHARS)
    principal_id: str = Field(max_length=MAX_IDENTIFIER_CHARS)


class FinishAsked(BaseModel):
    """What the finishing screen sends beside the token: the setup code and the administrator."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    setup_code: str = Field(max_length=MAX_ANSWER_CHARS)
    principal_id: str = Field(max_length=MAX_IDENTIFIER_CHARS)


class SignInOutcome(enum.StrEnum):
    """What came of asking for a binding, as the caller is told it."""

    BOUND = "bound"
    ALREADY_BOUND = "already_bound"
    SUBJECT_NOT_EXACT = "subject_not_exact"
    OWN_SIGN_IN = "own_sign_in"
    SUBJECT_BOUND_ELSEWHERE = "subject_bound_elsewhere"
    PRINCIPAL_ALREADY_SIGNS_IN = "principal_already_signs_in"


class SignInView(BaseModel):
    """The principal asked about and what came of it. Never another principal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    outcome: SignInOutcome


# ------------------------------------------------------------------------ the decisions


def _nothing_to_finish() -> Absent:
    """The one refusal the finishing screen makes after the token. See the module note."""
    return Absent("no finishing screen is answerable here")


def _no_sign_in_here() -> Absent:
    """The one refusal for a caller who may not bind and for a principal who is not here."""
    return Absent("no sign-in is bindable here for this caller")


def _current_keys(authority: TokenAuthority, kid: object, now: datetime) -> KeySet:
    """The key set after warming it for the token's kid, as `TokenAuthority` does. Blocking."""
    if isinstance(kid, str) and kid:
        authority.keys.key_for(authority.issuer, kid, now)
    return authority.keys.keys_for(authority.issuer, now)


async def verified_claims(
    authority: TokenAuthority, header: str | None, *, now: datetime
) -> VerifiedClaims:
    """The claims of a token this authority accepts, without asking who its subject is.

    Raises `TokenRefusedError` for every token `authenticate` would refuse before its directory
    lookup. See `THE_FINISHING_SCREEN_VERIFIES_WITHOUT_ASKING_WHO`.
    """
    raw = parse_unverified(token_from_header(header))
    # On a worker thread, for bearer.A_KEY_FETCH_NEVER_HOLDS_THE_EVENT_LOOP.
    keys = await asyncio.to_thread(_current_keys, authority, raw.header.get("kid"), now)
    return validate_token(
        raw,
        keys=keys,
        verify=authority.verify,
        expected_issuer=authority.issuer,
        expected_audience=authority.audience,
        now=now,
        leeway=authority.leeway,
    )


async def finish_sign_in(
    writer: SignInWriter,
    entitlements: EntitlementStore,
    *,
    enrolment: Enrolment | None,
    presented: str,
    claims: VerifiedClaims,
    principal_id: str,
    trace_id: str,
    now: datetime,
) -> Binding:
    """Bind a verified token's subject to the first administrator, once, or refuse one way.

    Every refusal is `_nothing_to_finish`. See
    `EVERY_REFUSAL_ON_THE_FINISHING_SCREEN_IS_ONE_ANSWER`.
    """
    if enrolment is None:
        log.info("finish refused", reason="no_setup_code")
        raise _nothing_to_finish()
    reach = await entitlements.load(principal_id, now)
    try:
        finish(
            enrolment,
            presented,
            administrators=1 if holds_everywhere(reach, now) else 0,
            signing_in=await writer.sign_ins(),
            now=now,
        )
    except WizardError as refused:
        log.info("finish refused", reason=type(refused).__name__)
        raise _nothing_to_finish() from refused
    if claims.session_id is None:
        # See A_CALLER_WITH_NO_SESSION_IS_NOT_A_SIGN_IN.
        log.info("finish refused", reason="no_session")
        raise _nothing_to_finish()
    if claims.issuer != writer.issuer:
        # A token the authority accepts at an issuer the binding would not be written at, which
        # is a wiring fault: a binding no token here would ever be found by.
        log.warning("finish refused", reason="issuer_mismatch")
        raise _nothing_to_finish()
    try:
        return await writer.bind(
            claims.subject,
            principal_id=principal_id,
            bound_by=GRANTED_BY,
            now=now,
            trace_id=trace_id,
        )
    except SignInBindingRefusedError as refused:
        log.info("finish refused", reason=refused.reason.value)
        raise _nothing_to_finish() from refused


async def bind_for_administrator(
    writer: SignInWriter,
    reach: EntitlementSet,
    asked: SignInAsked,
    *,
    trace_id: str,
    now: datetime,
) -> SignInOutcome:
    """Bind on an administrator's word, naming them as the binder, or refuse.

    Raises `_no_sign_in_here` for a caller without the capability over everything and for every
    refusal in `ONE_ANSWER`, and returns the refusal's code for the rest. See
    `A_BINDING_YOU_MAY_NOT_MAKE_AND_A_PRINCIPAL_NOT_HERE_ARE_ONE_ANSWER`.
    """
    if not holds_everywhere(reach, now):
        log.info("sign-in bind refused", reason="not_an_administrator")
        raise _no_sign_in_here()
    try:
        bound = await writer.bind(
            asked.subject,
            principal_id=asked.principal_id,
            bound_by=reach.principal_id,
            now=now,
            ent_hash=reach.ent_hash(),
            trace_id=trace_id,
        )
    except SignInBindingRefusedError as refused:
        if refused.reason in ONE_ANSWER:
            log.info("sign-in bind refused", reason=refused.reason.value)
            raise _no_sign_in_here() from refused
        return SignInOutcome(refused.reason.value)
    return SignInOutcome(bound.value)


# ------------------------------------------------------------------------- the wiring


def writer_of(request: Request) -> SignInWriter | None:
    """The bindings store this process was built with, or None, in `wiring_of`'s shape."""
    found = getattr(request.app.state, "sign_in_bindings", None)
    return found if isinstance(found, SignInWriter) else None


def _require_writer(request: Request) -> SignInWriter:
    """The store, or one fault identical for every caller."""
    found = writer_of(request)
    if found is None:
        raise Failed("no sign-in bindings store on this process")
    return found


def enrolment_of(request: Request) -> Enrolment | None:
    """This installation's setup enrolment, read through `Settings` and nowhere else."""
    settings = getattr(request.app.state, "settings", None)
    return settings.setup_enrolment() if isinstance(settings, Settings) else None


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.approval_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


router = APIRouter(tags=["sign-ins"])

#: A refusal an administrator is told is a 409 carrying the view, not `ErrorBody`.
_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": SignInView, "description": "Not bound, and why, naming nobody else."},
}


@router.post(SIGN_INS_PATH, response_model=SignInView, responses=_TOLD)
async def bind_sign_in(request: Request, asked: Asked, body: SignInAsked) -> JSONResponse:
    """Bind a Keycloak subject to a principal, as an administrator over everything."""
    writer = _require_writer(request)
    try:
        outcome = await bind_for_administrator(
            writer, asked.reach, body, trace_id=_trace_id(), now=asked.now
        )
    except BrainError:
        raise
    except Exception as exc:
        # Broad for the reason `brain.api_routes.answer` gives.
        raise Failed(f"binding: {type(exc).__name__}") from exc
    view = SignInView(principal_id=body.principal_id, outcome=outcome)
    told = outcome not in {SignInOutcome.BOUND, SignInOutcome.ALREADY_BOUND}
    return JSONResponse(status_code=409 if told else 200, content=view.model_dump(mode="json"))


@router.post(FINISH_PATH, response_model=SignInView, responses=COMMON_RESPONSES)
async def finish_setup_sign_in(request: Request, body: FinishAsked) -> SignInView:
    """Bind the installer's own sign-in to the first administrator, once."""
    now = datetime.now(UTC)
    wiring = wiring_of(request)
    if wiring is None:
        # bearer.AN_UNCONFIGURED_AUTHORITY_ACCEPTS_NOTHING, in the words it uses.
        raise TokenRefusedError(
            TokenRefusal.NO_KEYS_AVAILABLE, "no token authority is configured on this process"
        )
    writer = _require_writer(request)
    claims = await verified_claims(wiring.authority, request.headers.get("authorization"), now=now)
    try:
        bound = await finish_sign_in(
            writer,
            wiring.store,
            enrolment=enrolment_of(request),
            presented=body.setup_code,
            claims=claims,
            principal_id=body.principal_id,
            trace_id=_trace_id(),
            now=now,
        )
    except BrainError:
        raise
    except Exception as exc:
        raise Failed(f"finishing: {type(exc).__name__}") from exc
    return SignInView(principal_id=body.principal_id, outcome=SignInOutcome(bound.value))
