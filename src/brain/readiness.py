"""What `/health/ready` says about each part this process depends on, asked now rather than at boot.

**Four parts are always named: the database, the cache, the vault and sign-in.** Each is ready,
not ready, or not configured, and each says whether it decides the status. A part that is not
configured is named rather than left out, because an owner reading the console cannot tell a
part nobody set up from a part the check forgot, and those two need different people.

**A configured dependency decides readiness, and one nobody configured is named and never
counted.** The database, the cache and the vault, once an install names them, are what every
answer stands on, so a wrong address fails the deploy gate rather than serving wrong answers. An
install that names no vault (every install until its owner runs one) is named `not_configured`
and stays ready, for the reason `brain.app.SIGN_IN_IS_REPORTED_AND_DOES_NOT_GATE_READINESS` gives
about sign-in: failing the gate would take down the setup wizard that is how a vault gets set.
See `A_PART_NOBODY_CONFIGURED_IS_NAMED_AND_NEVER_COUNTED`.

**The blocking checks are asked again, not remembered.** Until 2026-09-17 `database`, `cache` and
`row_security` were answered once in the lifespan and then served for the life of the process,
so a database that went away an hour after boot was reported reachable by the endpoint whose
only job is to notice. Each is now a probe asked when a reading is older than
`PROBE_INTERVAL_SECONDS`, all at once, each bounded by `PROBE_TIMEOUT_SECONDS`. Rejected: asking
on every request. The endpoint is unauthenticated, so that turns every anonymous GET into a
database query, a cache ping and a vault call, which is an amplifier nobody needs to sign in
to use. See `A_READING_IS_SHARED_SO_AN_ANONYMOUS_CALLER_CANNOT_AMPLIFY_IT`.

**Sign-in is true only while the configured issuer answers as that issuer.** A key set fetched
once said nothing about the issuer an hour later, and a URL that answers with some other
issuer's discovery document is a wrong issuer however well its keys load. See
`SIGN_IN_IS_TRUE_ONLY_WHILE_THE_ISSUER_ANSWERS_AS_ITSELF`.

Task ids: M31.1.1.2, M31.1.1.5, M31.4.1, M31.4.2
"""

from __future__ import annotations

import asyncio
import enum
import json
import time
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import Final, Protocol

import structlog
from pydantic import BaseModel, ConfigDict

from brain.ops.openbao import OpenBaoVault, TokenStanding
from brain.ops.secrets import SecretsUnavailableError, VaultRole

log = structlog.get_logger()

#: The four parts `/health/ready` always names, in the order a person reads them.
DATABASE_PART: Final = "database"
CACHE_PART: Final = "cache"
VAULT_PART: Final = "vault"
SIGN_IN_PART: Final = "sign_in"
#: Whether the login itself, not only each transaction, is kept inside row-level security.
DATABASE_LOGIN_PART: Final = "database_login"
HEADLINE_PARTS: Final = (DATABASE_PART, CACHE_PART, VAULT_PART, SIGN_IN_PART)

#: How old a reading may be before the next request asks again, and how long one probe may take.
PROBE_INTERVAL_SECONDS: Final = 10.0
PROBE_TIMEOUT_SECONDS: Final = 4.0

#: Where an issuer describes itself. Relative to the issuer, as OpenID Connect Discovery puts it.
DISCOVERY_PATH: Final = "/.well-known/openid-configuration"

A_PART_NOBODY_CONFIGURED_IS_NAMED_AND_NEVER_COUNTED: Final = (
    "A database, cache or vault an install names is a readiness check: a wrong address fails the "
    "deploy gate rather than serving answers without it. One the install does not name is shown "
    "as not_configured and decides nothing, because failing readiness for it would take down the "
    "setup wizard and the status page, which are how an owner configures it. Named rather than "
    "omitted, so the console can say the vault is not ready instead of saying nothing about it."
)

A_READING_IS_SHARED_SO_AN_ANONYMOUS_CALLER_CANNOT_AMPLIFY_IT: Final = (
    "/health/ready needs no sign-in. A probe per request would let anybody turn one GET into a "
    "database statement, a cache ping and a vault call. So one reading is taken at a time, under a "
    "lock, and served to every request until it is PROBE_INTERVAL_SECONDS old; a probe that has "
    "not answered inside PROBE_TIMEOUT_SECONDS is not ready."
)

SIGN_IN_IS_TRUE_ONLY_WHILE_THE_ISSUER_ANSWERS_AS_ITSELF: Final = (
    "sign_in is ready when the realm's key set has been read and the configured issuer's discovery "
    "document answers, now, naming exactly that issuer. It is asked again on a timer for as long "
    "as the process runs, so an identity provider that stops answering turns sign_in not ready "
    "without a restart, and an address that answers for some other issuer never turns it ready. "
    "Neither decides readiness, so a wrong issuer leaves every page that needs no sign-in up."
)


class PartState(enum.StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    NOT_CONFIGURED = "not_configured"


class ReadinessPart(BaseModel):
    """One dependency as `/health/ready` reports it. `gates` says whether it decides the status."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    state: PartState
    gates: bool


def parts_of(checks: Mapping[str, bool], reported: Mapping[str, bool]) -> list[ReadinessPart]:
    """Every part, headline parts first and always present, then the rest as they were named.

    A name in `checks` decides the status; one in `reported` does not; a headline part in neither
    was not configured. See `A_PART_NOBODY_CONFIGURED_IS_NAMED_AND_NEVER_COUNTED`.
    """
    names = list(HEADLINE_PARTS)
    names += [one for one in (*checks, *reported) if one not in names]
    parts: list[ReadinessPart] = []
    for name in names:
        if name in checks:
            state = PartState.READY if checks[name] else PartState.NOT_READY
            parts.append(ReadinessPart(name=name, state=state, gates=True))
        elif name in reported:
            state = PartState.READY if reported[name] else PartState.NOT_READY
            parts.append(ReadinessPart(name=name, state=state, gates=False))
        else:
            parts.append(ReadinessPart(name=name, state=PartState.NOT_CONFIGURED, gates=False))
    return parts


Probe = Callable[[], Awaitable[bool]]


class Readings:
    """The blocking probes, asked together at most once per interval. See the module docstring."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.probes: dict[str, Probe] = {}
        self._clock = clock
        self._taken_at: float | None = None
        self._lock = asyncio.Lock()

    async def refresh(self, into: MutableMapping[str, bool]) -> None:
        """Ask every probe if the last reading is stale, writing each answer into `into`."""
        if not self.probes:
            return
        async with self._lock:
            now = self._clock()
            if self._taken_at is not None and now - self._taken_at < PROBE_INTERVAL_SECONDS:
                return
            names = list(self.probes)
            answers = await asyncio.gather(*(_bounded(self.probes[one]) for one in names))
            for name, answer in zip(names, answers, strict=True):
                into[name] = answer
            self._taken_at = self._clock()


async def _bounded(probe: Probe) -> bool:
    """A probe's answer, or False when it raised or did not answer in time."""
    try:
        return await asyncio.wait_for(probe(), timeout=PROBE_TIMEOUT_SECONDS)
    except Exception as exc:
        log.warning("readiness probe failed", error=type(exc).__name__)
        return False


def vault_configured(address: str, token: str) -> bool:
    """Whether this install names a vault at all. Half a pair is configured, and wrongly."""
    return bool(address or token)


class TokenLookup(Protocol):
    """What the vault probe asks of a vault client. `OpenBaoVault` is one."""

    def token_standing(self) -> TokenStanding: ...


def _application_vault(address: str, token: str) -> TokenLookup:
    return OpenBaoVault(address, token, role=VaultRole.APPLICATION)


def vault_answers(
    address: str,
    token: str,
    *,
    make_vault: Callable[[str, str], TokenLookup] = _application_vault,
) -> bool:
    """Whether the vault answers this process's own token. Blocking; call it off the loop.

    `auth/token/lookup-self`, which the application policy grants, so a sealed vault, a revoked or
    expired token and an address nothing listens on are all not ready, and nothing is read from a
    slot. The log names the exception class only: the vault's messages carry its address.
    """
    try:
        make_vault(address, token).token_standing()
    except (ValueError, SecretsUnavailableError) as exc:
        log.warning("secrets vault not ready", error=type(exc).__name__)
        return False
    return True


def issuer_answers(get: Callable[[str], bytes], issuer: str) -> bool:
    """Whether `issuer`'s discovery document answers and names exactly `issuer`. Blocking.

    `get` is `brain.identity.keycloak_tokens.http_get`, which refuses a redirect and caps the body,
    so a discovery document served from somewhere else is not an answer. See
    `SIGN_IN_IS_TRUE_ONLY_WHILE_THE_ISSUER_ANSWERS_AS_ITSELF`.
    """
    try:
        document = json.loads(get(f"{issuer}{DISCOVERY_PATH}"))
    except Exception as exc:
        log.warning("identity provider not answering", issuer=issuer, error=type(exc).__name__)
        return False
    named = document.get("issuer") if isinstance(document, dict) else None
    if named != issuer:
        log.error("identity provider answers as a different issuer", issuer=issuer)
        return False
    return True
