"""A reserved person signed in to the console through the install's own gate, for the people checks.

The Govern screens decide everything from one object, `brain.api_routes.Asking`, which only the
`asking` dependency makes: it verifies a bearer token, finds the person the token's subject is
bound to, records the session, reads the strength of the sign-in off the token's `amr`, resolves
the person's reach through the one resolver and narrows it by the channel and the sign-in. **A
check that built an `Asking` by hand would prove the screens against a reader the install can never
produce**, and the sign-in strength leaves (M27.9.1, M27.9.2) would be proved against the very value
they are about. So this module signs a token and hands it to `asking`, and everything after the
signature is the install's.

**The one thing stood in for is the realm's signing key.** The check makes an RSA key of its own
and serves its public half as the realm's key set, through `keycloak_authority` itself, so the
issuer, the audience, the leeway and the verifier are the install's and only the key differs. A
token the realm signed cannot be had without a person signing in, and every person a check acts as
is a reserved one who cannot (`brain.ops.acceptance.A_RESERVED_PRINCIPAL_CANNOT_SIGN_IN`). The
token carries what `ops/keycloak/realm-export.json`'s mappers write: the audience, the session id,
and `amr` naming a password and, for a strong sign-in, an authenticator.

**The subject is bound by the product's own writer**, `brain.identity.sign_in_binding.
SignInBindings.bind`, which also writes the member grant a sign-in opens, so a signed-in reserved
person holds exactly what a person linked on Sign-in links would. Nothing is committed: the binding,
the session row `asking` records and every ledger entry live in the check's transaction.

Rejected: overriding the `asking` dependency with a fixed `Asking`. It is shorter, and it is a
check of every route except the part that decides who is asking.

Task ids: M38.5.1
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

import structlog

from brain.ops.acceptance import CheckFailedError, CheckNotRunError
from brain.ops.acceptance_run import SET_UP_REACH, Harness

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
    from fastapi import FastAPI
    from starlette.requests import Request

    from brain.api_routes import Asking
    from brain.core.scope import Scope

#: What the realm's amr mapper writes for a password sign-in, and for one with an authenticator.
#: Keycloak's own reference values: `pwd` for the password step and `otp` for the OTP form.
PASSWORD_ONLY: Final = ("pwd",)
WITH_AN_AUTHENTICATOR: Final = ("pwd", "otp")

#: The client the console signs in through, as `ops/keycloak/realm-export.json` names it.
CONSOLE_CLIENT: Final = "brain-console"

#: How long a check's token lives: the realm's access-token lifespan.
TOKEN_SECONDS: Final = 300


def _b64(blob: bytes) -> str:
    return base64.urlsafe_b64encode(blob).decode("ascii").rstrip("=")


def _integer(value: int) -> str:
    return _b64(value.to_bytes((value.bit_length() + 7) // 8, "big"))


def everywhere(*capabilities: str) -> tuple[tuple[str, Scope], ...]:
    """Each capability held over the whole company, as an install's first administrator holds it."""
    from brain.core.scope import Scope

    return tuple((one, Scope.unrestricted()) for one in capabilities)


def within(department: str, *capabilities: str) -> tuple[tuple[str, Scope], ...]:
    """Each capability held over one department's own scope, as a department administrator's are."""
    from brain.core.scope import Clause, Op, Scope

    scope = Scope(clauses=(Clause(field="department", op=Op.EQ, value=department),))
    return tuple((one, scope) for one in capabilities)


def administrator() -> tuple[str, ...]:
    """What `brain.identity.first_administrator` grants an administrator at appointment."""
    from brain.identity.first_administrator import GRANTED_AT_APPOINTMENT

    return GRANTED_AT_APPOINTMENT


@dataclass
class Console:
    """The console's routes over the check's transaction, and a realm key the check holds."""

    h: Harness
    app: FastAPI
    issuer: str
    private: RSAPrivateKey = field(repr=False)
    kid: str
    _subjects: dict[str, str] = field(default_factory=dict)
    _sessions: int = 0
    #: The request the last `asked` authenticated, where `asking` left what a refusal is told.
    last: Request | None = None

    def request(self, bearer: str = "") -> Request:
        """A request on the console's application, carrying `bearer` when given one."""
        from starlette.requests import Request

        headers = [(b"authorization", f"Bearer {bearer}".encode())] if bearer else []
        return Request({"type": "http", "app": self.app, "headers": headers, "method": "GET"})

    async def link(self, principal_id: str) -> str:
        """Bind a subject of the check's own to `principal_id`, as Sign-in links would."""
        from brain.identity.sign_in_binding import Binding, SignInBindings

        subject = f"acceptance-{self.h.run}-{len(self._subjects)}"
        bound = await SignInBindings(self.h.sessions, self.issuer).bind(
            subject,
            principal_id=principal_id,
            bound_by=self.h.actor,
            now=self.h.now,
            ent_hash=SET_UP_REACH,
            trace_id=self.h.trace_id,
        )
        if bound is not Binding.BOUND:
            raise CheckFailedError("a reserved person could not be linked to a sign-in")
        self._subjects[principal_id] = subject
        return subject

    def token(
        self, subject: str, *, session: str, amr: tuple[str, ...] = WITH_AN_AUTHENTICATOR
    ) -> str:
        """A console token for `subject`, shaped as the realm mints one, signed by its key."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        from brain.identity.keycloak_tokens import API_AUDIENCE

        now = int(time.time())
        head = {"alg": "RS256", "kid": self.kid, "typ": "JWT"}
        claims = {
            "iss": self.issuer,
            "aud": API_AUDIENCE,
            "azp": CONSOLE_CLIENT,
            "typ": "Bearer",
            "sub": subject,
            "sid": session,
            "iat": now,
            "auth_time": now,
            "exp": now + TOKEN_SECONDS,
            "amr": list(amr),
        }
        signing = f"{_b64(json.dumps(head).encode())}.{_b64(json.dumps(claims).encode())}"
        signature = self.private.sign(signing.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
        return f"{signing}.{_b64(signature)}"

    def session(self) -> str:
        """A session id of the run's own, as Keycloak's `sid` names one."""
        self._sessions += 1
        return f"acceptance-{self.h.run}-{self._sessions}"

    async def asked(
        self,
        principal_id: str,
        *,
        strong: bool = True,
        session: str | None = None,
        bearer: str | None = None,
    ) -> Asking:
        """`brain.api_routes.asking` over a token for `principal_id`, linking them on first use.

        Strong means the token names an authenticator. `session` reuses a session id, so a second
        request in one sign-in is the same session; `bearer` presents a token as it is.
        """
        from brain.api_routes import asking

        if bearer is None:
            subject = self._subjects.get(principal_id) or await self.link(principal_id)
            bearer = self.token(
                subject,
                session=session or self.session(),
                amr=WITH_AN_AUTHENTICATOR if strong else PASSWORD_ONLY,
            )
        request = self.request(bearer)
        self.last = request
        with structlog.contextvars.bound_contextvars(trace_id=self.h.trace_id):
            return await asking(request)

    def as_route(self) -> Any:
        """Bind the run's trace id for a route call, as the trace middleware does for a request."""
        return structlog.contextvars.bound_contextvars(trace_id=self.h.trace_id)


class _OneKey:
    """The realm's key set, as `KeycloakJwks` fetches it: the check's own public key, and only
    for the address the install's issuer gives its key set."""

    def __init__(self, document: bytes, url: str) -> None:
        self._document = document
        self._url = url

    def __call__(self, url: str) -> bytes:
        if url != self._url:
            raise CheckFailedError("the gate asked for a key set at an address not its realm's")
        return self._document


async def console(h: Harness) -> Console:
    """The console's routes over the check's transaction, behind the install's own gate.

    The objects `brain.app.lifespan` sets on the application's state that the Govern routes read,
    each over `harness.sessions`: the gate `brain.app.wirings_for` builds, with no entitlement
    cache, which would outlive the transaction, and the database. Every other store a route needs
    it chooses itself from those.
    """
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import FastAPI

    from brain.api_routes import GateWiring
    from brain.cache import NoEntitlementCache, PostgresVersionSource
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.identity.keycloak_tokens import jwks_url_for, keycloak_authority
    from brain.identity.principal_directory import StoredDirectory
    from brain.identity.roles import IdentityError
    from brain.identity.sign_in_binding import sign_in_bindings
    from brain.install import InstallError, value_of

    try:
        issuer = value_of("INSTALL_OIDC_ISSUER")
    except InstallError as unset:
        raise CheckNotRunError(
            "this install cannot check a sign-in, so it has no console to open"
        ) from unset
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    kid = f"acceptance-{h.run}"
    numbers = private.public_key().public_numbers()
    document = json.dumps(
        {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": kid,
                    "n": _integer(numbers.n),
                    "e": _integer(numbers.e),
                }
            ]
        }
    ).encode()
    try:
        authority = keycloak_authority(
            directory=StoredDirectory(h.sessions),
            get=_OneKey(document, jwks_url_for(issuer)),
            clock=lambda: datetime.now(UTC),
        )
    except (InstallError, IdentityError) as exc:
        raise CheckNotRunError(
            "this install cannot check a sign-in, so it has no console to open"
        ) from exc
    app = FastAPI()
    app.state.settings = h.settings
    app.state.db_sessions = h.sessions
    app.state.sign_in_bindings = sign_in_bindings(h.sessions)
    app.state.gate = GateWiring(
        authority=authority,
        versions=PostgresVersionSource(h.sessions),
        store=StoredEntitlements(h.sessions),
        cache=NoEntitlementCache(),
    )
    return Console(h=h, app=app, issuer=issuer, private=private, kid=kid)


def told(exc: Exception) -> str:
    """What a person is told for a refusal: `brain.core.errors.to_public`."""
    from brain.core.errors import BrainError, to_public

    return to_public(exc) if isinstance(exc, BrainError) else type(exc).__name__
