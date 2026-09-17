"""Keeping the two vault tokens alive, each renewed by the process that holds it.

The installer mints two tokens on an install's own vault, one against the application policy and
one against the worker's, each an orphan with a period, `brain.deployment.vault_setup`'s
`TOKEN_PERIOD`.
A periodic token has no maximum lifetime and one hard rule: **renewed inside its period it lives,
and not renewed it lapses, for good.** A lapsed application token is an install whose console can
no longer keep a provider key and whose next start loads none; a lapsed worker token is a worker
that signs no webhook delivery. Neither fails loudly on the day it happens, because nothing reads
the vault on the path of an ordinary question, so this is a control and not a helper.

**Each process renews the token it holds, and that was forced rather than chosen.** The brief for
this module was one worker control renewing both tokens, and it cannot be built without breaking
the policy split it protects. OpenBao renews a token by its value, at `auth/token/renew-self` or at
`auth/token/renew` with the token in the body, and has no renewal by accessor: whoever renews a
token holds it. A worker holding the application's token holds the application's reach, which is
every provider key, every connector lease under `connectors/creds/+` and the write on every stored
slot, and `ops/openbao/policies/worker.hcl` exists to keep exactly that out of the process nobody
watches. See `RENEWAL_TAKES_THE_CREDENTIAL_SO_EACH_HOLDER_RENEWS_ITS_OWN`. So the worker's
schedule runs `vault_token_renewal` for the worker's token, the application's lifespan runs
`keep_renewing` for its own, and both call `renew_if_owed`, which is the one decision. The
registry names both call sites, so the control reads as running only while both are.

**Renewed at half the period, checked twice a day.** A token renewed only when it is nearly gone is
a token one missed week away from lapsing, and the period is a month. At half, a worker that is
down for a fortnight, or an application that is not restarted for one, still renews in time on its
next check. See `RENEWED_WITH_HALF_ITS_PERIOD_STILL_TO_RUN`. The check is cheap, a lookup of the
token's own standing, so asking every twelve hours costs the vault two requests a day per process.

**A token that renewal cannot carry is a failure, said in words.** A token with no period is capped
by the vault's maximum lifetime however often it is renewed, and a token minted non-renewable
refuses outright. Both are what a token minted by hand with the wrong flags looks like, and both
would otherwise be reported as renewed until the day they stopped working. See
`A_CREDENTIAL_WITH_NO_PERIOD_CANNOT_BE_KEPT_ALIVE`.

**An install with no vault has nothing to renew and says so; half a vault is refused.** Both
settings blank is a lite install that declined the vault, and the run succeeds naming that. One
blank is the worker whose overlay was composed without its token, and it fails naming the missing
half, for `brain.ops.credentials.credentials_at_start`'s reason.

Rejected: renewing on every start and nowhere else. A container that runs for longer than a period
is the ordinary case on a server nobody touches, and it is the one that lapses.

Rejected: minting tokens with no period and a long lifetime. The vault caps a token's lifetime at
its maximum, a month by default, so the choice is a token that lapses on a date or one that is
renewed, and only the second is a property this module can keep.

Task ids: M42.6.2, M31.3.2.2
"""

from __future__ import annotations

import asyncio
import enum
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Final, Protocol

import structlog

from brain.ops.openbao import OpenBaoVault, TokenStanding
from brain.ops.secrets import SecretsUnavailableError, VaultRole

log = structlog.get_logger(__name__)

# ------------------------------------------------------------ written-down reasons

#: Why no process renews a token another process holds.
RENEWAL_TAKES_THE_CREDENTIAL_SO_EACH_HOLDER_RENEWS_ITS_OWN: Final = (
    "OpenBao renews a token by its value and offers no renewal by accessor, so a renewer holds "
    "the token it renews. The application's token carries every provider key, every connector "
    "lease and the write on every stored slot, and the worker's policy is written to keep that "
    "reach out of a process nobody watches. So each process renews its own, through one decision, "
    "and the worker is never handed the application's token to renew it."
)

#: Why renewal happens at half the period rather than near its end.
RENEWED_WITH_HALF_ITS_PERIOD_STILL_TO_RUN: Final = (
    "A token renewed only when it is nearly out is one missed stretch of downtime from lapsing, "
    "and a lapsed token cannot be renewed at all. Renewed once less than half its period is "
    "left, a process that misses a fortnight of checks on a month's period still renews in time."
)

#: Why a token with no period, or one the vault will not renew, is a failed run.
A_CREDENTIAL_WITH_NO_PERIOD_CANNOT_BE_KEPT_ALIVE: Final = (
    "Renewing a token with no period extends it only up to the vault's maximum lifetime, and a "
    "token minted non-renewable is refused outright. Either is a token minted by hand with other "
    "flags than the installer's, and reporting it as renewed would be true until the day it "
    "stopped working. Mint it again with a period, as ops/openbao/credential-slots.md says."
)

# --------------------------------------------------------------------- the figures

#: Renew once less than this share of the period is left. See the named constant.
RENEW_BELOW_SHARE_OF_PERIOD: Final = 0.5

#: How often a process asks whether its token is owed a renewal. Twice a day; the control's cadence.
CHECK_EVERY: Final = timedelta(hours=12)

#: The two settings a process names its vault with, in the words a person sets them in.
_ADDRESS: Final = "BRAIN_VAULT_ADDRESS"
_TOKEN: Final = "BRAIN_VAULT_TOKEN"  # noqa: S105  the name of a setting, never a value

# ------------------------------------------------------------------------ the shapes


class TokenCannotBeKeptError(SecretsUnavailableError):
    """This token is not one renewal can keep alive.

    See `A_CREDENTIAL_WITH_NO_PERIOD_CANNOT_BE_KEPT_ALIVE`.
    """


class Renewal(enum.StrEnum):
    """What one check did."""

    #: Less than half the period was left, and the vault renewed it.
    RENEWED = "renewed"
    #: More than half was left, so nothing was asked of the vault beyond the lookup.
    NOT_OWED = "not_owed"


@dataclass(frozen=True)
class Renewed:
    """One check's outcome, in figures a run report can print. No field could hold a token."""

    outcome: Renewal
    left_seconds: int
    period_seconds: int

    def summary(self) -> str:
        """The run report line, in hours, which is the unit the period is minted in."""
        left, period = self.left_seconds // 3600, self.period_seconds // 3600
        if self.outcome is Renewal.RENEWED:
            return f"vault token renewed: {left}h left of a {period}h period"
        return (
            f"vault token not owed a renewal: {left}h left of a {period}h period, renewed once "
            f"fewer than {int(period * RENEW_BELOW_SHARE_OF_PERIOD)}h are left"
        )


class SelfRenewing(Protocol):
    """What renewal needs of a vault client. `OpenBaoVault` is one."""

    def token_standing(self) -> TokenStanding:
        """The standing of the token this client holds."""
        ...

    def renew_self(self) -> int:
        """Renew the token this client holds; the seconds the vault granted."""
        ...


# ------------------------------------------------------------------------ the decisions


def renewal_owed(standing: TokenStanding) -> bool:
    """Whether this token should be renewed now, or raise when renewal cannot keep it.

    See `RENEWED_WITH_HALF_ITS_PERIOD_STILL_TO_RUN` for the share and
    `A_CREDENTIAL_WITH_NO_PERIOD_CANNOT_BE_KEPT_ALIVE` for the two refusals.
    """
    if not standing.renewable:
        msg = (
            f"this vault token is not renewable. {A_CREDENTIAL_WITH_NO_PERIOD_CANNOT_BE_KEPT_ALIVE}"
        )
        raise TokenCannotBeKeptError(msg)
    if standing.period_seconds <= 0:
        msg = f"this vault token has no period. {A_CREDENTIAL_WITH_NO_PERIOD_CANNOT_BE_KEPT_ALIVE}"
        raise TokenCannotBeKeptError(msg)
    return standing.ttl_seconds < standing.period_seconds * RENEW_BELOW_SHARE_OF_PERIOD


def renew_if_owed(vault: SelfRenewing) -> Renewed:
    """Look the token up, renew it when it is owed, and say what was done.

    The figure reported after a renewal is the vault's grant rather than the period, because the
    grant is what the token now has; the two are equal for a token the installer minted.
    """
    standing = vault.token_standing()
    if not renewal_owed(standing):
        return Renewed(Renewal.NOT_OWED, standing.ttl_seconds, standing.period_seconds)
    granted = vault.renew_self()
    return Renewed(Renewal.RENEWED, granted, standing.period_seconds)


def vault_named(address: str, token: str) -> bool:
    """Whether these two settings name a vault, refusing half of one.

    Both blank is no vault. One blank raises naming the missing setting, because a process whose
    overlay handed it an address and no token has a token that nothing is renewing.
    """
    if not address and not token:
        return False
    if not address or not token:
        missing = _ADDRESS if not address else _TOKEN
        msg = (
            f"this process names half a secrets vault: {missing} is not set, so no token is renewed"
        )
        raise SecretsUnavailableError(msg)
    return True


def run_renewal_now(
    address: str,
    token: str,
    *,
    make_vault: Callable[[str, str], SelfRenewing] | None = None,
) -> str:
    """The worker's scheduled run: renew the worker's own token when owed, as a report line.

    Raises for half a vault, an address that is not a URL, a vault that is silent or refuses, and
    a token renewal cannot keep, so the schedule records the run as failed with the sentence. An
    install with no vault succeeds saying there was nothing to renew.
    """
    if not vault_named(address, token):
        return "no secrets vault is named on this worker, so there is no token to renew"
    build = make_vault if make_vault is not None else _worker_vault
    try:
        vault = build(address, token)
    except ValueError as exc:
        msg = f"{_ADDRESS} is not a URL, so no token is renewed"
        raise SecretsUnavailableError(msg) from exc
    return renew_if_owed(vault).summary()


def renewer_at_start(
    address: str,
    token: str,
    *,
    make_vault: Callable[[str, str], SelfRenewing] | None = None,
) -> SelfRenewing | None:
    """The application's vault client for renewing its own token, or None where there is none.

    Never raises, for `brain.ops.credentials.credentials_at_start`'s reason: a process must not
    refuse to start over a token, and half a vault or an address that is not a URL is logged and
    answered with None, which renews nothing.
    """
    try:
        if not vault_named(address, token):
            return None
        build = make_vault if make_vault is not None else _application_vault
        return build(address, token)
    except (SecretsUnavailableError, ValueError) as exc:
        log.warning("vault token renewal not started", reason=type(exc).__name__)
        return None


async def keep_renewing(
    vault: SelfRenewing,
    *,
    every: timedelta = CHECK_EVERY,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    rounds: int | None = None,
) -> None:
    """The application's own renewal: check now, then every `every`, until cancelled.

    The vault client is blocking, so each check runs in a worker thread. A failed check is logged
    and asked again on the next round rather than ending the loop, because a vault sealed for an
    hour is not a reason to stop renewing for the life of the process. `rounds` bounds the loop
    for a test; the lifespan passes none.
    """
    done = 0
    while rounds is None or done < rounds:
        try:
            renewed = await asyncio.to_thread(renew_if_owed, vault)
        except SecretsUnavailableError as exc:
            log.warning("vault token renewal failed", reason=str(exc))
        else:
            log.info(
                "vault token checked", outcome=renewed.outcome.value, left=renewed.left_seconds
            )
        done += 1
        await sleep(every.total_seconds())


def _worker_vault(address: str, token: str) -> OpenBaoVault:
    return OpenBaoVault(address, token, role=VaultRole.WORKER)


def _application_vault(address: str, token: str) -> OpenBaoVault:
    return OpenBaoVault(address, token, role=VaultRole.APPLICATION)
