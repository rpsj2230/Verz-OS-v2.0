"""This install's template signing key: minted once into a write-once vault slot, read at start.

`brain.agents.template.publish` signs a manifest with an HMAC key and `verify` checks it with the
same key, and until 2026-09-29 no install held one: `app.state.template_key`, which every agent
route reads, was set by nothing, so publishing, installing and duplicating an agent all answered
`brain.agent_lifecycle_routes.NO_SIGNING_KEY_HERE` on every real install. The owner pulled the key
forward from Wave 3 (needs-rupash 82) so new agents can be published from the console. This module
is where it lives and how the application comes to hold it.

**One slot, `template_signing/key`, under an engine of its own, and it is created once.** The key is
the install's own: nobody supplies it and no vendor issues it, so it is minted here, 32 random
bytes, and put into the slot with kv version 2's check-and-set at version 0, which the vault accepts
only while the slot has never held a version. The application's policy grants create and read on
that one path and no update, no delete and no metadata write, so even a writer that left the
check-and-set out cannot replace it, and `OpenBaoVault.write_static_kv` refuses the prefix outright.
A signed template version is verified with this key for as long as it exists, so a key replaced
under it would make every version uninstallable, and a key somebody chose would let them sign
whatever they wrote. See `THE_TEMPLATE_KEY_IS_CREATED_ONCE_AND_NEVER_WRITTEN_OVER`.

**The key used is the key the vault holds, read back after every create.** Every application
process runs this at start, and a server runs several, so two can find the slot empty together.
Both try to create; the vault lets one in and refuses the other (400 on the check-and-set, or 403
once the policy's missing update applies), and both then read the slot and use what it holds. No
process ever signs with the value it minted unless the vault kept that value. See
`THE_KEY_USED_IS_THE_KEY_THE_VAULT_HOLDS`.

**A slot that held a key and holds none now is not refilled.** Only somebody holding a root token
made from the recovery key can delete a version, because no policy here grants delete, and a key
minted again after that would be a replacement by another route. The vault refuses the create, by
the missing update or by the check-and-set, because the slot has a version history, and the state is
`UNUSABLE`, said in words.

**The key never leaves the vault except into this process's memory.** It is carried as a
`brain.ops.leases.SealedSecret`, whose every rendering is the seal, until `hold` puts the characters
on `app.state.template_key`, the one place the agent routes read it. No log event, no response and
no console page names it, its length or any part of it; the Credentials screen says only which of
five states it is in. See `THE_TEMPLATE_KEY_NEVER_LEAVES_THE_VAULT_BUT_INTO_THIS_PROCESS`.

**An install with no vault holds no key anywhere, and says so.** A lite install run with
`--no-vault` has nowhere a write-once key can live, and keeping it in a table or a file would be the
weaker place `brain.ops.credentials.NO_VAULT_IS_NOT_A_REASON_TO_USE_A_TABLE` refuses. So the state
is `NO_VAULT`, the key is None, and every agent route answers `NO_SIGNING_KEY_HERE` (M13.8.18).

**Minted at start, and by the installer as a step of its own.** The application mints it when it
starts and finds the slot empty, which is how an install set up before this module gets its key on
its next start, once its owner has loaded this release's policies. The installer's step `keep this
install's template signing key` runs `python -m brain.ops.template_key` in the application
container after readiness, so a fresh install that could not mint at start fails out loud with a
sentence, and its done test (`--held`) only reads. A process whose vault was sealed or silent at
start asks again every minute until it answers, because a server that rebooted starts the
application before anybody has opened the vault.

Rejected: a path under `providers/`, which the application policy already grants create and update
on with a `+`. An exact-path rule would outrank the wildcard in OpenBao's matching, and the rule
keeping the key write-once would then rest on a precedence detail a later edit could undo; an engine
of its own is a line in the installer and one command for an install made before it.
Rejected: minting in the installer's vault step with the root token. The root token lives for that
one step, and a key minted there would reach an install made before this module only by hand.
Rejected: a retry while the vault refuses (403). Every refusal is a line in the vault's audit log,
which is shipped into the ledger, so a process asking once a minute for ever on an install whose
policies were never reloaded would fill the ledger with denials. A refusal waits for a restart.

Task ids: M13.8.10, M13.8.18
"""

from __future__ import annotations

import asyncio
import enum
import secrets
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from types import MappingProxyType
from typing import Final, Protocol

import structlog
from starlette.datastructures import State

from brain.ops.leases import SealedSecret
from brain.ops.openbao import TEMPLATE_KEY_PREFIX, OpenBaoVault, VaultRefusedError
from brain.ops.secrets import SecretsUnavailableError, VaultRole

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons

#: Why the key is created once and never replaced.
THE_TEMPLATE_KEY_IS_CREATED_ONCE_AND_NEVER_WRITTEN_OVER: Final = (
    "Every template version this install publishes is signed with this key and every install "
    "verifies with it. A replaced key makes every signed version uninstallable, and a key somebody "
    "chose signs whatever they write. So it is created with the vault's check-and-set at version "
    "0, the policy grants create and never update or delete, the ordinary write refuses its "
    "prefix, and a slot that once held a key is never filled again."
)

#: Why a process uses what it read back, never what it minted.
THE_KEY_USED_IS_THE_KEY_THE_VAULT_HOLDS: Final = (
    "Several application processes start together and can find the slot empty together. Each "
    "tries to create it, the vault keeps one value and refuses the rest, and every process then "
    "reads the slot and uses what it holds, so no process signs with a key the vault does not have."
)

#: Where the key may be, and where it may never be.
THE_TEMPLATE_KEY_NEVER_LEAVES_THE_VAULT_BUT_INTO_THIS_PROCESS: Final = (
    "The key is read from the vault into this process's memory and put where the agent routes read "
    "it. It is never logged, never in a response and never on a console page, whole or in part; "
    "the console is told which state it is in and nothing else."
)

# --------------------------------------------------------------------- the figures

#: The one slot, and the field the key is kept under.
TEMPLATE_KEY_SLOT: Final = f"{TEMPLATE_KEY_PREFIX}key"
TEMPLATE_KEY_FIELD: Final = "key"

#: The key's size: 32 random bytes, written as 64 hexadecimal characters, the size of the
#: HMAC-SHA256 output it keys.
KEY_BYTES: Final = 32

#: The shortest value in the slot accepted as a key. A shorter one is not a key this module made,
#: and signing with it would be signing with a weaker key than the product promises.
MIN_KEY_CHARS: Final = 2 * KEY_BYTES

#: How often a process whose vault did not answer at start asks again.
RETRY_EVERY: Final = timedelta(minutes=1)

#: The installer's done test: read the slot and write nothing.
HELD_FLAG: Final = "--held"


class TemplateKeyState(enum.StrEnum):
    """Where this process stands with the key. Only `HELD` carries one."""

    HELD = "held"
    #: The vault refused: this release's policy is not loaded yet, or its engine is not enabled.
    WAITING = "waiting"
    #: This install names no vault.
    NO_VAULT = "no_vault"
    #: The vault was sealed or did not answer. Asked again every minute.
    UNREAD = "unread"
    #: The slot holds something that is not a key, or held one that was removed.
    UNUSABLE = "unusable"


#: What the console says of each state, and the command line prints.
TEMPLATE_KEY_SAYS: Final[Mapping[TemplateKeyState, str]] = MappingProxyType(
    {
        TemplateKeyState.HELD: (
            "Template signing key: held. Agents can be published and installed from the console, "
            "each version signed with this install's own key."
        ),
        TemplateKeyState.WAITING: (
            "Template signing key: not yet created, waiting for the vault policy reload. Each "
            "deploy applies its release's policies itself; a vault still opened by people moves "
            "first with ops/openbao/switch-to-auto-unseal.sh (ops/openbao/UNSEAL.md, Moving an "
            "older install). Until the policy is in force and the application restarts, "
            "publishing and installing agents are unavailable."
        ),
        TemplateKeyState.NO_VAULT: (
            "Template signing key: none. This install runs no secrets vault and the key is kept "
            "nowhere else, so publishing and installing agents are unavailable."
        ),
        TemplateKeyState.UNREAD: (
            "Template signing key: not read yet. The vault was sealed or did not answer when this "
            "process started; it is asked again every minute, and publishing and installing agents "
            "wait until it answers."
        ),
        TemplateKeyState.UNUSABLE: (
            "Template signing key: not used. Its vault slot holds no key this product made, and "
            "nothing here writes it again. Publishing and installing agents are unavailable: see "
            "ops/openbao/credential-slots.md, The template signing key."
        ),
    }
)


class TemplateKeyVault(Protocol):
    """The two vault calls this needs. `brain.ops.openbao.OpenBaoVault` is one."""

    def read_static_kv(self, path: str) -> dict[str, object]:
        """The slot's fields. Raises `VaultRefusedError` with 404 for a slot never written."""
        ...

    def create_static_kv_once(self, path: str, fields: Mapping[str, str]) -> bool:
        """Create the slot if it never held a version; False when it did."""
        ...


@dataclass(frozen=True)
class TemplateKeyReading:
    """A state, and the key only when the state is `HELD`. Its rendering never shows the key."""

    state: TemplateKeyState
    key: SealedSecret | None = None

    def __post_init__(self) -> None:
        if (self.key is not None) is not (self.state is TemplateKeyState.HELD):
            msg = "a reading carries a key exactly when the key is held"
            raise ValueError(msg)

    @property
    def told(self) -> str:
        return TEMPLATE_KEY_SAYS[self.state]


def mint_key() -> str:
    """A fresh key from the operating system's random source."""
    return secrets.token_hex(KEY_BYTES)


def _read(vault: TemplateKeyVault) -> TemplateKeyReading | None:
    """What the slot holds, or None when it holds nothing. Never raises for the vault."""
    try:
        fields = vault.read_static_kv(TEMPLATE_KEY_SLOT)
    except VaultRefusedError as refused:
        if refused.status == 404:
            return None
        if refused.status == 403:
            return TemplateKeyReading(TemplateKeyState.WAITING)
        return TemplateKeyReading(TemplateKeyState.UNREAD)
    except SecretsUnavailableError:
        return TemplateKeyReading(TemplateKeyState.UNREAD)
    if not fields:
        return None
    value = fields.get(TEMPLATE_KEY_FIELD)
    if not isinstance(value, str) or len(value) < MIN_KEY_CHARS:
        return TemplateKeyReading(TemplateKeyState.UNUSABLE)
    return TemplateKeyReading(TemplateKeyState.HELD, SealedSecret(value))


def look(vault: TemplateKeyVault | None) -> TemplateKeyReading:
    """The slot as it is, writing nothing: the installer's done test."""
    if vault is None:
        return TemplateKeyReading(TemplateKeyState.NO_VAULT)
    found = _read(vault)
    return TemplateKeyReading(TemplateKeyState.WAITING) if found is None else found


def obtain(
    vault: TemplateKeyVault | None, *, mint: Callable[[], str] = mint_key
) -> TemplateKeyReading:
    """The key, minted into the slot first if the slot has never held one. Never raises for the
    vault. See `THE_TEMPLATE_KEY_IS_CREATED_ONCE_AND_NEVER_WRITTEN_OVER` and
    `THE_KEY_USED_IS_THE_KEY_THE_VAULT_HOLDS`."""
    if vault is None:
        return _said(TemplateKeyReading(TemplateKeyState.NO_VAULT))
    found = _read(vault)
    if found is not None:
        return _said(found)
    created = False
    refused: int | None = None
    try:
        created = vault.create_static_kv_once(TEMPLATE_KEY_SLOT, {TEMPLATE_KEY_FIELD: mint()})
    except VaultRefusedError as refusal:
        # The read was allowed, so the policy is loaded: a 403 here is a slot that already has a
        # version, another process's create or a key since removed, and a 404 is the engine not
        # enabled. Reading again tells the race from the rest.
        refused = refusal.status
    except SecretsUnavailableError:
        return _said(TemplateKeyReading(TemplateKeyState.UNREAD))
    again = _read(vault)
    if again is not None:
        return _said(again, created=created)
    return _said(TemplateKeyReading(_why_still_empty(created=created, refused=refused)))


def _why_still_empty(*, created: bool, refused: int | None) -> TemplateKeyState:
    """What a slot still empty after a create attempt means."""
    if refused == 404:
        return TemplateKeyState.WAITING
    if created or (refused is not None and refused != 403):
        # Accepted and then not readable, or a refusal that was not about the slot: the vault
        # answered one call and not the next.
        return TemplateKeyState.UNREAD
    # The check-and-set (400) or the missing update (403) refused because the slot has a version
    # history and holds no readable key: one was removed, and minting again would replace it.
    return TemplateKeyState.UNUSABLE


def _said(found: TemplateKeyReading, *, created: bool = False) -> TemplateKeyReading:
    """Log the state, never the key, and hand the reading back."""
    if found.state is TemplateKeyState.HELD:
        log.info("template signing key held", minted_here=created)
    elif found.state is TemplateKeyState.NO_VAULT:
        log.info("template signing key not held", state=found.state.value)
    else:
        log.warning("template signing key not held", state=found.state.value)
    return found


def vault_for(address: str, token: str) -> OpenBaoVault | None:
    """The application's vault client, or None when the install names none."""
    if not address or not token:
        return None
    return OpenBaoVault(address, token, role=VaultRole.APPLICATION)


def template_key_at_start(address: str, token: str) -> TemplateKeyReading:
    """What the lifespan holds: the key read, minted first if the slot is empty. Never raises."""
    try:
        vault = vault_for(address, token)
    except ValueError:
        # An address that is not a URL; readiness's vault part says so.
        return _said(TemplateKeyReading(TemplateKeyState.UNREAD))
    return obtain(vault)


def hold(state: State, found: TemplateKeyReading) -> None:
    """Put a reading where it is read: the key on `template_key`, which
    `brain.agent_lifecycle_routes.template_key_of` reads, and the state on `template_key_state`,
    which the Credentials screen reads."""
    state.template_key = None if found.key is None else found.key.reveal()
    state.template_key_state = found.state


def state_of(state: State) -> TemplateKeyState:
    """The state a process holds, or `NO_VAULT` for one that never read the key."""
    found = getattr(state, "template_key_state", None)
    return found if isinstance(found, TemplateKeyState) else TemplateKeyState.NO_VAULT


async def keep_trying(
    attempt: Callable[[], Awaitable[TemplateKeyReading]],
    held: Callable[[TemplateKeyReading], None],
    *,
    every: float = RETRY_EVERY.total_seconds(),
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> TemplateKeyReading:
    """Ask again every `every` seconds while the vault has not answered, and stop once it has.

    Only `UNREAD` is asked again: a sealed or silent vault writes nothing to its audit log, and a
    refusal does. See the module's last rejection.
    """
    while True:
        await sleep(every)
        found = await attempt()
        held(found)
        if found.state is not TemplateKeyState.UNREAD:
            return found


# ----------------------------------------------------------------------------- the command


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m brain.ops.template_key [--held]`, in the application container.

    With no argument: read the key, minting it first if the slot has never held one, print the
    state's sentence and exit 0 when it is held. With `--held`: read only, print nothing, and exit
    0 when it is held, which is the installer's done test. Neither prints the key.
    """
    from brain.settings import Settings

    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], [HELD_FLAG]):
        print(f"usage: python -m brain.ops.template_key [{HELD_FLAG}]", file=sys.stderr)
        return 2
    settings = Settings()
    try:
        vault = vault_for(settings.vault_address, settings.vault_token)
    except ValueError:
        vault = None
    if args:
        return 0 if look(vault).state is TemplateKeyState.HELD else 1
    found = obtain(vault)
    print(found.told)
    return 0 if found.state is TemplateKeyState.HELD else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
