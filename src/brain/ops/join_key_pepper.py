"""The join-key pepper: one value per install, created once in its own vault slot, read by two
processes, never rotated.

`brain.resolution.canonical.identifier_hash` stores every join key entity resolution compares (a
UEN, a tax id, a domain, and later an email or a phone number) as an HMAC keyed with a pepper, so
the digests in `er.identifier` cannot be reversed by hashing guesses: a list of every company
registration number in a country is a few million guesses, and without the pepper not one of them
lands. Nothing provided that pepper until this module. The worker hashes join keys when it
registers source records and the application hashes a value an administrator enters to block it,
so both read it, each with its own vault token.

**One slot, `resolution/pepper`, field `value`, 64 lowercase hexadecimal characters, under an
engine of its own.** 32 bytes from the operating system's random source, made in the application
container and written with kv version 2's check-and-set at version 0, which the vault accepts only
while the slot has never held a version. The application's policy grants create and read on that
one path and no update, delete or metadata; the worker's grants read and nothing else; the ordinary
write (`OpenBaoVault.write_static_kv`) refuses the prefix. So nothing can replace it, whichever of
the three a later edit loosens. See `THE_PEPPER_IS_CREATED_ONCE_AND_NEVER_WRITTEN_OVER`.

**Rotation is not offered, and that is the design rather than a gap.** A digest made under one
pepper matches nothing made under another, so a new pepper does not make the old digests weaker,
it makes them unjoinable: every record already registered stops matching every record registered
afterwards, with no error anywhere, and the merge review fills with duplicates that were one entity
yesterday. Changing it is therefore a re-registration of every source record under the new value,
which is a migration with a plan, not a setting with a button. See
`A_NEW_PEPPER_UNJOINS_EVERY_STORED_DIGEST`.

**The installer creates it, every application start makes sure of it, and nothing else writes.**
The owner decided (b): the pepper is kept in a vault slot the installer creates. The installer's
step `keep this install's join-key pepper` runs `python -m brain.ops.join_key_pepper` in the
application container after readiness, and the application runs the same create-if-absent when it
starts, which is how an install made before this release, or updated by its own script or by the
server's deploy hook, comes to hold one with nobody at the server. See
`THE_RELEASE_SCRIPT_CANNOT_CREATE_IT_SO_THE_APPLICATION_DOES` for why it is not the release's
`ops/openbao/apply-release.sh`, which enables the engine and creates nothing in it.

**The value used is the value the vault holds, read back after every create.** Two processes can
find the slot empty together; the vault keeps one value and refuses the other, and both then read
the slot. No process hashes with a pepper it minted unless the vault kept that value.

**The pepper never leaves the vault except into a process's memory.** It is returned as a
`brain.ops.leases.SealedSecret`, whose every rendering is the seal, and revealed at the one place a
digest is computed. Every refusal is `PepperUnavailableError`, whose message is one of the fixed
sentences in `PEPPER_SAYS` and so cannot carry the value, its length or any part of it, and no log
line here names it. See `THE_PEPPER_NEVER_LEAVES_THE_VAULT_BUT_INTO_MEMORY`.

**A value that is not 64 lowercase hexadecimal characters is refused, not used.** This module is
the only thing that writes the slot and it writes exactly that shape, so anything else was put
there by somebody with a root token, and hashing with it would bind every stored digest to a value
nobody here chose. Lowercase only, because the HMAC keys on the characters: the same bytes in
upper case are a different pepper.

**A slot that held a pepper and holds none now is not refilled.** Only a root token can delete a
version, because no policy grants delete, and a pepper created after that would be a rotation by
another route. The vault refuses the create anyway (the missing update, or the check-and-set,
because the slot has a version history), and the problem is `REMOVED`, said in words.

Rejected: creating it in `ops/openbao/apply-release.sh`. That script runs under the root token only
at install and under the deploy token on every release after, and the deploy token writes no
secret value (ops/openbao/policies/deploy.hcl). Granting it one means changing the deploy token's
own policy, which the deploy token may not load, so every install already running would have every
release held back until somebody made a root token from the recovery key: the ceremony
needs-rupash 114 removed. Creating it only under the root token would give a pepper to fresh
installs and to no install made before this release, which `brain.ops.template_key` rejected for
its own key in the same words.

Rejected: a setting in the environment file. It would be one more value a person copies, it would
sit in every backup of that file, and a person editing it would be rotating the pepper without
knowing it.

Rejected: deriving it from another secret the install holds (the template signing key, the
database password). Rotating that secret would then rotate this one, which is the one thing this
value must never do.

Task ids: M14.7.3
"""

from __future__ import annotations

import enum
import re
import secrets
import sys
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Final, Protocol

import structlog

from brain.ops.leases import SealedSecret
from brain.ops.openbao import RESOLUTION_PREFIX, OpenBaoVault, VaultRefusedError
from brain.ops.secrets import SecretsUnavailableError, VaultRole

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons

#: Why rotation is not offered.
A_NEW_PEPPER_UNJOINS_EVERY_STORED_DIGEST: Final = (
    "Every join key in er.identifier is an HMAC under this pepper, and a digest made under one "
    "pepper matches nothing made under another. A new pepper therefore does not strengthen the "
    "stored digests, it unjoins them: records registered before stop matching records registered "
    "after, silently. Changing it is a re-registration of every source record, planned as a "
    "migration, and never a setting."
)

#: Why the slot is created once and never written over.
THE_PEPPER_IS_CREATED_ONCE_AND_NEVER_WRITTEN_OVER: Final = (
    "The pepper is created with the vault's check-and-set at version 0, the application's policy "
    "grants create and read and never update or delete, the worker's grants read only, and the "
    "ordinary write refuses its prefix. A slot that once held a pepper is never filled again, "
    "because filling it would be a rotation by another route."
)

#: Why the application, and not the release's vault script, creates it.
THE_RELEASE_SCRIPT_CANNOT_CREATE_IT_SO_THE_APPLICATION_DOES: Final = (
    "apply-release.sh runs under the deploy token on every release, and that token writes no "
    "secret value and may not load a change to its own policy. Granting it this slot would hold "
    "back every release on every install already running until somebody made a root token. So the "
    "release enables the engine, and the application creates the pepper, at the installer's step "
    "and at every start, under a policy the deploy token loads."
)

#: Where the pepper may be, and where it may never be.
THE_PEPPER_NEVER_LEAVES_THE_VAULT_BUT_INTO_MEMORY: Final = (
    "The pepper is read from the vault into the memory of the process that hashes with it, sealed "
    "until the digest is computed. It is never logged, never in an exception, a response or a "
    "console page, whole or in part, and nothing reports its length."
)

# --------------------------------------------------------------------- the figures

#: The one slot, and the field the pepper is kept under.
PEPPER_SLOT: Final = f"{RESOLUTION_PREFIX}pepper"
PEPPER_FIELD: Final = "value"

#: 32 random bytes, written as 64 hexadecimal characters: the size of the HMAC-SHA256 output it
#: keys, which is as long as an HMAC key usefully gets.
PEPPER_BYTES: Final = 32
PEPPER_CHARS: Final = 2 * PEPPER_BYTES

#: The only shape a pepper this module made can have.
_PEPPER_SHAPE: Final = re.compile(f"[0-9a-f]{{{PEPPER_CHARS}}}")

#: The installer's done test: read the slot and write nothing.
HELD_FLAG: Final = "--held"

#: The two processes that hash join keys. The browser runner and a connector run never do.
READING_ROLES: Final = frozenset({VaultRole.APPLICATION, VaultRole.WORKER})


class PepperProblem(enum.StrEnum):
    """Why no pepper was handed back. Each has one fixed sentence in `PEPPER_SAYS`."""

    #: This install names no vault.
    NO_VAULT = "no_vault"
    #: The slot has never held a pepper.
    ABSENT = "absent"
    #: The vault refused: this release's policy or the resolution engine is not in force yet.
    REFUSED = "refused"
    #: The vault was sealed, did not answer, or answered in a shape nothing here can read.
    UNREACHABLE = "unreachable"
    #: The slot holds something that is not 64 lowercase hexadecimal characters.
    MALFORMED = "malformed"
    #: The slot held a pepper that was removed, and nothing here creates another.
    REMOVED = "removed"


#: What each problem says. Fixed sentences, so an exception built from one cannot carry the value.
PEPPER_SAYS: Final[Mapping[PepperProblem, str]] = MappingProxyType(
    {
        PepperProblem.NO_VAULT: (
            "Join-key pepper: none. This install runs no secrets vault and the pepper is kept "
            "nowhere else, so no join key is hashed and records are not matched on identifiers."
        ),
        PepperProblem.ABSENT: (
            "Join-key pepper: not created yet. The application creates it when it starts; "
            "python -m brain.ops.join_key_pepper in the application container creates it now."
        ),
        PepperProblem.REFUSED: (
            "Join-key pepper: the vault refused it. This release's vault policies or its "
            "resolution engine are not in force yet: ops/openbao/UNSEAL.md, under When a "
            "release's vault changes do not take."
        ),
        PepperProblem.UNREACHABLE: (
            "Join-key pepper: not read. The vault was sealed, did not answer, or answered in a "
            "shape that could not be read; nothing was hashed."
        ),
        PepperProblem.MALFORMED: (
            "Join-key pepper: not used. Its vault slot holds something that is not a pepper this "
            "product made, and nothing is hashed with it: see ops/openbao/credential-slots.md, "
            "The join-key pepper."
        ),
        PepperProblem.REMOVED: (
            "Join-key pepper: removed. Its vault slot held a pepper that has since been deleted, "
            "and nothing here creates another, because a new pepper unjoins every stored digest: "
            "see ops/openbao/credential-slots.md, The join-key pepper."
        ),
    }
)


class PepperUnavailableError(Exception):
    """No pepper could be handed back. `problem` says why; the message is `PEPPER_SAYS[problem]`.

    Built only from a problem, never from a value, so no rendering of it can carry the pepper.
    """

    def __init__(self, problem: PepperProblem) -> None:
        super().__init__(PEPPER_SAYS[problem])
        self.problem = problem


class PepperReader(Protocol):
    """The one vault call reading needs. `brain.ops.openbao.OpenBaoVault` is one."""

    def read_static_kv(self, path: str) -> dict[str, object]:
        """The slot's fields. Raises `VaultRefusedError` with 404 for a slot never written."""
        ...


class PepperKeeper(PepperReader, Protocol):
    """Reading, and the one create-only write. `brain.ops.openbao.OpenBaoVault` is one."""

    def create_static_kv_once(self, path: str, fields: Mapping[str, str]) -> bool:
        """Create the slot if it never held a version; False when it did."""
        ...


def mint_pepper() -> str:
    """A fresh pepper from the operating system's random source, in the one shape accepted."""
    return secrets.token_hex(PEPPER_BYTES)


def read_pepper(vault: PepperReader | None) -> SealedSecret:
    """The install's pepper, sealed. The one reader both processes use, each with its own token.

    Raises `PepperUnavailableError` when there is no vault, the slot is empty, the vault refuses
    or does not answer, or the slot holds anything but 64 lowercase hexadecimal characters. Writes
    nothing and logs nothing. Rotation is not offered: see
    `A_NEW_PEPPER_UNJOINS_EVERY_STORED_DIGEST`.
    """
    if vault is None:
        raise PepperUnavailableError(PepperProblem.NO_VAULT)
    return _read(vault)


def _read(vault: PepperReader) -> SealedSecret:
    """`read_pepper` once a vault is known to be named."""
    try:
        fields = vault.read_static_kv(PEPPER_SLOT)
    except VaultRefusedError as refused:
        problem = PepperProblem.ABSENT if refused.status == 404 else PepperProblem.REFUSED
        raise PepperUnavailableError(problem) from refused
    except SecretsUnavailableError as silent:
        # A vault that did not answer, or answered in a shape that could not be read. A refusal
        # is a subclass too, and is caught above, because it says something a silence does not.
        raise PepperUnavailableError(PepperProblem.UNREACHABLE) from silent
    if not fields:
        raise PepperUnavailableError(PepperProblem.ABSENT)
    value = fields.get(PEPPER_FIELD)
    if not isinstance(value, str) or _PEPPER_SHAPE.fullmatch(value) is None:
        # Raised with no cause and no detail: the value is what is wrong, so nothing about it may
        # travel with the refusal.
        raise PepperUnavailableError(PepperProblem.MALFORMED)
    return SealedSecret(value)


def keep_pepper(vault: PepperKeeper | None, *, mint: Callable[[], str] = mint_pepper) -> bool:
    """Make sure the slot holds a pepper: True when this call created it, False when one was held.

    Creates only into a slot that has never held a version, then reads back and checks what the
    vault kept, so a process that lost a race to another creator reports False and is right. Raises
    `PepperUnavailableError` for everything `read_pepper` does except an empty slot, and `REMOVED`
    for a slot whose pepper was deleted. See `THE_PEPPER_IS_CREATED_ONCE_AND_NEVER_WRITTEN_OVER`.
    """
    if vault is None:
        raise PepperUnavailableError(PepperProblem.NO_VAULT)
    try:
        _read(vault)
    except PepperUnavailableError as first:
        if first.problem is not PepperProblem.ABSENT:
            raise
    else:
        return False
    created = False
    refused: int | None = None
    try:
        created = vault.create_static_kv_once(PEPPER_SLOT, {PEPPER_FIELD: mint()})
    except VaultRefusedError as refusal:
        # The read was allowed, so the policy is loaded: a 403 is a slot with a version history
        # (another process's create, or a pepper since removed) and a 404 the engine not enabled.
        refused = refusal.status
    except SecretsUnavailableError as silent:
        raise PepperUnavailableError(PepperProblem.UNREACHABLE) from silent
    try:
        _read(vault)
    except PepperUnavailableError as again:
        if again.problem is not PepperProblem.ABSENT:
            raise
        raise PepperUnavailableError(_why_still_absent(created, refused)) from None
    return created


def _why_still_absent(created: bool, refused: int | None) -> PepperProblem:
    """What a slot still empty after a create attempt means."""
    if refused == 404:
        return PepperProblem.REFUSED
    if created or (refused is not None and refused != 403):
        # Accepted and then not readable, or a refusal that was not about the slot: the vault
        # answered one call and not the next.
        return PepperProblem.UNREACHABLE
    # The check-and-set (False) or the missing update (403) refused because the slot has a version
    # history and holds no pepper: one was removed, and creating another would rotate it.
    return PepperProblem.REMOVED


def pepper_vault(address: str, token: str, role: VaultRole) -> OpenBaoVault | None:
    """This process's vault client for the pepper, or None when the install names no vault.

    Only the application and the worker hash join keys, so only their roles are accepted; a
    browser runner or a run token asking is a caller that has no business holding the pepper.
    """
    if role not in READING_ROLES:
        msg = f"the {role.value} role does not hash join keys and is not given the pepper"
        raise ValueError(msg)
    if not address or not token:
        return None
    return OpenBaoVault(address, token, role=role)


def pepper_at_start(address: str, token: str) -> PepperProblem | None:
    """The application's start: create the pepper if the slot has never held one. Never raises.

    Returns None when a pepper is held afterwards, and the problem otherwise; logs which, never the
    value. An address that is not a URL is readiness's to report, and is `UNREACHABLE` here.
    """
    try:
        vault = pepper_vault(address, token, VaultRole.APPLICATION)
    except ValueError:
        log.warning("join-key pepper not held", problem=PepperProblem.UNREACHABLE.value)
        return PepperProblem.UNREACHABLE
    try:
        created = keep_pepper(vault)
    except PepperUnavailableError as unavailable:
        if unavailable.problem is PepperProblem.NO_VAULT:
            log.info("join-key pepper not held", problem=unavailable.problem.value)
        else:
            log.warning("join-key pepper not held", problem=unavailable.problem.value)
        return unavailable.problem
    log.info("join-key pepper held", created_here=created)
    return None


# ----------------------------------------------------------------------------- the command


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m brain.ops.join_key_pepper [--held]`, in the application container.

    With no argument: create the pepper if the slot has never held one, print a sentence and exit 0
    when one is held. With `--held`: read only, print nothing, and exit 0 when one is held, which
    is the installer's done test. Neither ever prints the pepper.
    """
    from brain.settings import Settings

    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], [HELD_FLAG]):
        print(f"usage: python -m brain.ops.join_key_pepper [{HELD_FLAG}]", file=sys.stderr)
        return 2
    settings = Settings()
    try:
        vault = pepper_vault(settings.vault_address, settings.vault_token, VaultRole.APPLICATION)
    except ValueError:
        vault = None
    if args:
        try:
            read_pepper(vault)
        except PepperUnavailableError:
            return 1
        return 0
    try:
        created = keep_pepper(vault)
    except PepperUnavailableError as unavailable:
        print(str(unavailable))
        return 1
    print(
        "Join-key pepper: created in its vault slot, once, and never written over."
        if created
        else "Join-key pepper: held. Nothing was written."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
