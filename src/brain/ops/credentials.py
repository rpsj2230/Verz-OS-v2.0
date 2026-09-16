"""A credential put into the vault from a browser, and said to be held without being read back.

An administrator could not put a credential into this system from anywhere but a shell on the
server. The setup wizard asked for a model provider's key and then refused to go on unless the
same key was already in the process environment, which on the owner's staging install meant a
hand edit of that server's environment; the connectors screen could show what a connector may
read and not connect one; and M27.8.7 asks for a credential that is written once and never read
back. All three wanted the same missing piece, **a write into a named vault slot that returns
that the secret is held and when, and never the secret.** This module is that piece, and
`brain.credential_routes` and `brain.setup_routes` are its two callers.

**The application holds write on the provider slots, and the argument that it must not was
read first.** `brain.ops.openbao` and `ops/openbao/policies/application.hcl` refuse the
application a stored secret because a process that can read `connectors/xero` holds Xero's key
for as long as it lives. That argument is about connector credentials, which the vault can mint
per request, and it does not reach a provider key, which it cannot:
`brain.ops.provider_keys` already has this process read the key into its own environment at
start, where the SDK uses it on every question. A process that can already use a key gains
nothing by being able to replace it except the thing an administrator needs, and the one new
power, persistence of a key an attacker chose, is answered by the vault's own version history
and audit device and by the console showing when each slot was last written. See
`THE_APPLICATION_MAY_WRITE_A_KEY_IT_ALREADY_HOLDS`. What the policy still refuses is written in
the policy: no connector path, no delete, no metadata write.

**Written once and never read back is a property of the types, not a habit.** Nothing here
returns a value. `Held` and `Kept` carry a slot, a boolean and a time, and have no field that
could carry more; the vault's metadata is where the time comes from, and metadata has no field
of the secret. `put_to_use` takes the value from the caller that already had it and returns an
enum. See `A_CREDENTIAL_IS_WRITTEN_ONCE_AND_NEVER_READ_BACK`, and
`tests/unit/test_credential_routes.py` for the response bodies and the log lines searched for a
sentinel.

**An install with no vault keeps nothing, and says so in words.** Both settings blank is every
install until its owner runs a vault. The answer then is `VaultState.ABSENT` and a sentence
naming the two settings, never a row: `brain.tables.config` refuses secrets in the one table the
application can write configuration to, and a credential the application role can select is a
credential in the ordinary query path. See `NO_VAULT_IS_NOT_A_REASON_TO_USE_A_TABLE`.

**A key written here is in use in one process at once, and the rest is said rather than
hidden.** The process that wrote it hands it to its own SDK, so the person who pressed save is
not answered by a process still using the old key. A sibling worker started by
`brain.serve` loads keys at its own start and nowhere else, which is
`brain.ops.provider_keys`' "rotation is a restart", and a variable the environment file sets
outranks the vault on every start. Both are reported, `InUse.OUTRANKED` for the second, so a
screen can say what the person has to do. See `A_KEY_IN_USE_HERE_IS_NOT_IN_USE_EVERYWHERE`.

**A credential write leaves an entry in the audit ledger, and never the value.** Until
2026-09-16 it left a log line, which is kept for a month and edited by whoever holds the log. Now
the key is followed by a row in `ops.credential_write` naming the slot and the actor, and the
trigger `migrations/versions/0054_credential_and_retention_audit.py` puts on that table appends a
`credential` entry under `credential:providers.anthropic`, the way every other entry in the
ledger is appended: from the database, on a row the application wrote. **The record is made
inside `keep`**, so the console's route and the setup wizard are one mechanism and neither call
site has to remember it. Neither the row nor the entry has anywhere to put the value, its
length, a prefix or a fingerprint. See
`A_CREDENTIAL_WRITE_LEAVES_A_LEDGER_ENTRY_AND_NEVER_THE_VALUE`.

**The vault first and the record second, and the window between them is stated rather than
closed.** The record is its own short transaction after the vault has answered, so the ledger's
advisory lock is never held across a network call to the vault: holding it would queue every
grant, sign-in and review decision in the install behind a vault timeout. A vault that refuses or
is silent records nothing, because nothing was replaced. A record that fails after the key was
kept is logged as an error naming the slot, the actor, the trace and the exception's type, and
the write is still answered as kept, **because it was**: an error would send the person to write
it again, making a second version and, with the database still down, a second unrecorded write.
The vault's audit device, once an install enables it, records every write by path with the value
hashed, and it is the second record of exactly that window. With no database there is no ledger
at all and the write says so in a warning; no deployed route reaches `keep` there, since the
console's gate and the wizard's appointer are both built only over a database. See
`THE_KEY_IS_KEPT_BEFORE_IT_IS_RECORDED_AND_A_LOST_RECORD_IS_LOUD`.

Rejected: recording first, as an intent. A vault that then refused would leave an entry saying a
key was replaced when it was not, and the ledger has no way to take an entry back.

Rejected: a synchronous recorder bridged onto the event loop from the vault's worker thread,
which would keep `keep` synchronous. It waits in one thread on a loop running in another and
deadlocks the day somebody calls it on the loop. `keep` awaits instead: the blocking vault client
runs in a worker thread inside it, and the record is awaited on the loop through the application's
own sessions, with no second pool.

Rejected: a lazy load in a sibling worker the first time it finds no key. It is polling with a
different trigger, it puts a vault call on the path of a person's question, and it still does
nothing for a variable the environment file sets.

Rejected: letting the vault win over the environment at start. It is the order that would make
a rotation from the console survive a restart on an install whose file still carries a key, and
it silently overrides a developer's shell, which `load_into_environment` refuses with an
argument. The file line is reported instead, and removing it is one of the install's steps.

Rejected: validating a key against its provider before storing it. It sends the key to a third
party from a code path whose whole job is to hold it, it fails on an install with no egress, and
a provider's key format is not ours to bound; `brain.setup_wizard.MAX_KEY_CHARS` says the same.

**A connected source's key is a second kind of slot, and it goes through this same `keep`.**
Connecting a source from the console (`brain.ops.connector_admin`) writes the key the source's
vendor issued into `connector_keys/<source>`, and that write is recorded in `ops.credential_write`
and reaches the ledger exactly as a provider key's does, because it is this function. The two
kinds share `KeySlot`, which is a path and a sentence; only `CredentialSlot` names a provider, so
`put_to_use` and `told_in_use` cannot be handed a connector's slot, which nothing reads out of the
environment. The console's credential route writes `SLOTS` and nothing else, so a connector's key
is written by connecting the source, under `admin:connector`, and never under `admin:credential`.
See `A_CONNECTED_SOURCE_S_KEY_IS_WRITTEN_BY_CONNECTING_IT`.

Task ids: M27.8.7, M5.1.2, M42.6.5
"""

from __future__ import annotations

import asyncio
import enum
import re
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final, Protocol

import structlog

from brain.ops.openbao import (
    CONNECTOR_KEY_PREFIX,
    OpenBaoVault,
    StaticVersion,
    VaultUnreachableError,
)
from brain.ops.provider_keys import (
    PROVIDER_SLOTS,
    ProviderSlot,
    load_into_environment,
    names_in_environment,
    put_into_environment,
)
from brain.ops.secrets import SecretsUnavailableError, VaultRole

log = structlog.get_logger(__name__)

# ------------------------------------------------------------ written-down reasons

#: Why the application's policy grants create and update on the provider slots.
THE_APPLICATION_MAY_WRITE_A_KEY_IT_ALREADY_HOLDS: Final = (
    "The refusal of stored secrets in application.hcl is about connector credentials, which the "
    "vault can mint and take back, so a process that could read one would hold a key it was "
    "meant to borrow. A provider key cannot be minted, and this process already reads it into "
    "its environment at start and uses it on every question. Replacing a key it already holds "
    "adds one power, persistence of a key somebody else chose, and that is answered where it can "
    "be: kv keeps the versions, the vault's audit device records the write, and the console "
    "shows when each slot was last written. Connector paths, delete and metadata writes stay "
    "refused."
)

#: What a caller of this module can get back, and what it cannot.
A_CREDENTIAL_IS_WRITTEN_ONCE_AND_NEVER_READ_BACK: Final = (
    "Every answer here is a slot, whether it holds a secret, and when that secret was written, "
    "read from the vault's metadata, which carries no field of the secret. No function returns a "
    "value, no result type has a field that could hold one, and no log event names one. The "
    "process that uses a key reads it once at start into its own environment; that is the key "
    "being used, not being read back to anybody."
)

#: Why an install without a vault gets a sentence and not a fallback.
NO_VAULT_IS_NOT_A_REASON_TO_USE_A_TABLE: Final = (
    "An install whose settings name no vault keeps no credential. brain.tables.config refuses "
    "secrets in ops.setting, and it is right to: a credential the application role can select "
    "is a credential in the ordinary query path, one injection or one careless export away from "
    "a file. The answer is the two settings to set, in words, and the key stays wherever it was."
)

#: Which processes a key written here reaches, and when.
A_KEY_IN_USE_HERE_IS_NOT_IN_USE_EVERYWHERE: Final = (
    "The process that wrote a key hands it to its own provider SDK, so the answer to the person "
    "who saved it is not given by a process still using the old one. Every other server process "
    "reads keys at its own start and not again, so it uses the new key from its next start, and "
    "an environment file that sets the same variable wins over the vault on every start. The "
    "first is a restart; the second is a line to remove, then a restart, and it is reported as "
    "outranked so a screen can say which."
)

#: What a credential write leaves in the ledger, and what it never leaves.
A_CREDENTIAL_WRITE_LEAVES_A_LEDGER_ENTRY_AND_NEVER_THE_VALUE: Final = (
    "Every key kept here is followed by a row in ops.credential_write naming the slot and who "
    "wrote it, and the database's trigger on that row appends a credential entry to the "
    "hash-chained ledger under the slot, so who replaced a key and when is answered by the "
    "ledger and not only by a log. The record is made inside keep, so the console and the setup "
    "wizard cannot differ about it. Neither the row nor the entry carries the value, its length, "
    "a prefix or a fingerprint."
)

#: The order of the two writes, the window between them, and what answers for that window.
THE_KEY_IS_KEPT_BEFORE_IT_IS_RECORDED_AND_A_LOST_RECORD_IS_LOUD: Final = (
    "The vault write comes first and the record second, in a transaction of its own, so the "
    "ledger's lock is never held across a network call to the vault and a vault that refused or "
    "was silent records nothing. A record that fails after the key was kept is logged as an error "
    "naming the slot, the actor and the trace, never the value, and the write is still answered "
    "as kept, because it was. The vault's audit device, once an install enables it, is the second "
    "record of that write."
)

#: Why a connected source's key has a slot kind of its own and a writer of its own.
A_CONNECTED_SOURCE_S_KEY_IS_WRITTEN_BY_CONNECTING_IT: Final = (
    "A source's key is kept by the same write as a provider key, so it is recorded in the ledger "
    "the same way, and it is never read back by either. It is a different kind of slot because "
    "nothing reads it into this process's environment, and it is written only by connecting the "
    "source under admin:connector, because a key written without the settings that say what it "
    "reaches is a key nothing on the connectors screen can account for."
)

# --------------------------------------------------------------------- the figures

#: The one field a provider slot's secret is written under. `api_key`, because it is the first
#: name `brain.ops.provider_keys.read_static` looks for, so what this writes is what start-up
#: reads, and a second name here would be a slot that reads as empty.
KEY_FIELD: Final = "api_key"

#: The longest credential this accepts, which is `brain.setup_wizard.MAX_KEY_CHARS` held equal
#: by a test rather than imported, so this module stays underneath the wizard. A ceiling on a
#: paste, not a statement about any provider's format.
MAX_CREDENTIAL_CHARS: Final = 1000


class VaultState(enum.StrEnum):
    """Whether this install's vault can be asked, and if not, which of three things is wrong."""

    #: The install names no vault, or names half of one.
    ABSENT = "absent"
    #: It named one and it did not answer.
    UNREACHABLE = "unreachable"
    #: It answered, and refused.
    REFUSED = "refused"
    #: It answered.
    READY = "ready"


#: What a person is told for each state, in words that say what to do. Served by both callers.
TOLD: Final[Mapping[VaultState, str]] = MappingProxyType(
    {
        VaultState.ABSENT: (
            "This install runs no secrets vault, so no credential can be kept. Set "
            "BRAIN_VAULT_ADDRESS and BRAIN_VAULT_TOKEN in the server's environment file, restart "
            "the system, and try again. Nothing was stored anywhere else."
        ),
        VaultState.UNREACHABLE: (
            "The secrets vault did not answer, so nothing was stored. Check that it is running "
            "and unsealed and that the application can reach it, then try again."
        ),
        VaultState.REFUSED: (
            "The secrets vault answered and refused to store this, so nothing was stored. Its "
            "token may have expired, or the application policy or the providers engine may not "
            "be loaded: ops/openbao/credential-slots.md has the steps. Then try again."
        ),
        VaultState.READY: "The secrets vault answered.",
    }
)


class InUse(enum.StrEnum):
    """Whether the process that wrote a key now uses it. See the named constant."""

    #: This process uses it now; every other server process from its next start.
    HERE = "here"
    #: The environment sets this variable, which wins over the vault on every start.
    OUTRANKED = "outranked"


# ------------------------------------------------------------------------ the shapes


@dataclass(frozen=True)
class KeySlot:
    """Where a credential is kept and what it is for. Everything `keep` and `held` need.

    Two kinds below, and a function taking this takes either: the write, the metadata read and
    the record are one mechanism for both. See
    `A_CONNECTED_SOURCE_S_KEY_IS_WRITTEN_BY_CONNECTING_IT`.
    """

    path: str
    description: str


@dataclass(frozen=True)
class CredentialSlot(KeySlot):
    """A model provider's key: its vault path, what it is for, and the provider that reads it.

    `provider` is required, and it is the field `ConnectorKeySlot` does not have, because nothing
    reads a connector's key out of the environment. `put_to_use` takes this type and not
    `KeySlot`, so a connector's slot cannot be handed to a provider's SDK by a caller that mixed
    the two up.
    """

    provider: ProviderSlot


@dataclass(frozen=True)
class ConnectorKeySlot(KeySlot):
    """The key a connected source's vendor issued, at `connector_keys/<source>`.

    Built only by `connector_key_slot`, which holds the source's name to one path segment, so the
    slot is one the application policy's `+` names and one `brain.audit.record.CREDENTIAL_SLOT`
    admits as a ledger subject.
    """

    connector: str


#: A source's name as a slot takes it: one lower-case path segment, a letter first. The same
#: grammar as `brain.ops.webhook_admin.SUBSCRIBER_ID_PATTERN`, for that constant's reason.
CONNECTOR_NAME_PATTERN: Final = r"^[a-z][a-z0-9_]{0,62}$"
_CONNECTOR_NAME_RE: Final = re.compile(CONNECTOR_NAME_PATTERN)


def connector_key_slot(connector: str) -> ConnectorKeySlot:
    """Where a connected source's key is kept. Refuses a name that is not one path segment.

    Refused rather than escaped, because the name is the path: `xero/../providers/anthropic` would
    be a write over the key every question is sent with, and a name the grammar refuses is one
    no connectable source in `brain.ops.connectable` has.
    """
    if not _CONNECTOR_NAME_RE.fullmatch(connector):
        msg = f"{connector!r} is not a source name a key slot can be built from"
        raise ValueError(msg)
    return ConnectorKeySlot(
        path=f"{CONNECTOR_KEY_PREFIX}{connector}",
        description=f"The key {connector} issued for this company's connection.",
        connector=connector,
    )


#: Every slot this system writes, by path. Closed, and built from `PROVIDER_SLOTS` rather than
#: listed again, so a provider added there is a slot here with nothing else to edit.
SLOTS: Final[Mapping[str, CredentialSlot]] = MappingProxyType(
    {
        one.path: CredentialSlot(path=one.path, description=one.description, provider=one)
        for one in PROVIDER_SLOTS
    }
)


@dataclass(frozen=True)
class Problem:
    """One thing wrong with a credential before it is written: a code and what to do about it."""

    code: str
    message: str


@dataclass(frozen=True)
class Held:
    """Whether a slot holds a secret, and when it was written. `set_at` is None when it holds
    none, or when the vault kept no time this could read."""

    slot: str
    held: bool
    set_at: datetime | None


@dataclass(frozen=True)
class Kept:
    """A secret was written to a slot. Nothing here could hold the secret."""

    slot: str
    set_at: datetime | None


class CredentialsUnavailableError(Exception):
    """The vault could not be asked or refused. `state` says which; the message is `TOLD`'s."""

    def __init__(self, state: VaultState) -> None:
        super().__init__(TOLD[state])
        self.state = state


class CredentialProblemError(Exception):
    """What was given is not a credential this will write. Nothing was sent anywhere."""

    def __init__(self, problems: tuple[Problem, ...]) -> None:
        super().__init__("; ".join(one.message for one in problems))
        self.problems = problems


class CredentialVault(Protocol):
    """What this module needs from a vault. `brain.ops.openbao.OpenBaoVault` is one."""

    def write_static_kv(self, path: str, fields: Mapping[str, str]) -> datetime | None:
        """Write one slot and return the version's time."""
        ...

    def static_kv_version(self, path: str) -> StaticVersion | None:
        """The slot's current version, or None when it holds nothing."""
        ...


class CredentialWrites(Protocol):
    """Where a kept credential is recorded. `brain.ops.credential_write_store` is the one.

    Named for what it records and taking no value, so there is no argument through which one
    could reach the table: a slot, who wrote it, the request's trace and the writer's reach as a
    digest, which is empty for the setup wizard because first run has no reach to digest.
    """

    async def record(self, *, slot: str, written_by: str, trace_id: str, ent_hash: str) -> None:
        """Record that `written_by` wrote a credential into `slot`, in a transaction of its own."""
        ...


# ------------------------------------------------------------------------ the decisions


def problems_with(value: str) -> tuple[Problem, ...]:
    """Everything wrong with a credential as given, judged before anything is sent.

    Judged on the value with its outer whitespace removed, because a paste usually carries a
    line break at the end and refusing it would be refusing the commonest correct answer. What
    is left must be non-empty, no longer than `MAX_CREDENTIAL_CHARS`, and one unbroken run of
    printable characters: a space or a line break inside a key is a bad copy, and a character a
    header cannot carry would fail at the provider as an authentication error nobody can read.
    """
    given = value.strip()
    if not given:
        return (
            Problem(
                code="blank",
                message="Nothing was given. Paste the key from your provider account.",
            ),
        )
    found: list[Problem] = []
    if len(given) > MAX_CREDENTIAL_CHARS:
        found.append(
            Problem(
                code="too_long",
                message=(
                    f"That is longer than {MAX_CREDENTIAL_CHARS} characters, which is longer "
                    "than a key. Check that only the key was copied, and paste it again."
                ),
            )
        )
    if any(one.isspace() or not one.isprintable() for one in given):
        found.append(
            Problem(
                code="not_one_piece",
                message=(
                    "The key has a space, a line break or a character a key cannot hold inside "
                    "it. Copy it again from your provider account and paste it without them."
                ),
            )
        )
    return tuple(found)


class Credentials:
    """This process's way into the vault for credentials, or its lack of one.

    Built once, by `credentials_at_start`, and held on `app.state.credentials`. `vault` is None
    on an install with no vault; every method then refuses with `VaultState.ABSENT`. `writes` is
    where each kept credential is recorded, attached by the lifespan through `recording_to` once
    there is a database, and None where there is none.
    """

    def __init__(
        self,
        vault: CredentialVault | None,
        *,
        outranking: frozenset[str] = frozenset(),
        environ: MutableMapping[str, str] | None = None,
        writes: CredentialWrites | None = None,
    ) -> None:
        self._vault = vault
        self._outranking = outranking
        self._environ = environ
        self._writes = writes

    def __repr__(self) -> str:
        return f"Credentials(configured={self.configured}, outranking={sorted(self._outranking)})"

    __str__ = __repr__

    @property
    def configured(self) -> bool:
        """Whether this install names a vault at all. Not whether it answers."""
        return self._vault is not None

    def recording_to(self, writes: CredentialWrites | None) -> Credentials:
        """This store, with every credential it keeps recorded to `writes`.

        A new store rather than a setter, so a store is never half built. The lifespan builds
        this one before the database, because loading keys needs none, and attaches the record
        after, because the record is a row in it. With nowhere to record, this same store,
        since nothing about it changes.
        """
        if writes is None:
            return self
        return Credentials(
            self._vault, outranking=self._outranking, environ=self._environ, writes=writes
        )

    def _vault_or_refuse(self) -> CredentialVault:
        if self._vault is None:
            raise CredentialsUnavailableError(VaultState.ABSENT)
        return self._vault

    def held(self, slot: KeySlot) -> Held:
        """Whether `slot` holds a secret, and when it was written. Reads metadata only."""
        vault = self._vault_or_refuse()
        try:
            version = vault.static_kv_version(slot.path)
        except VaultUnreachableError as silent:
            raise CredentialsUnavailableError(VaultState.UNREACHABLE) from silent
        except SecretsUnavailableError as refused:
            raise CredentialsUnavailableError(VaultState.REFUSED) from refused
        if version is None:
            return Held(slot=slot.path, held=False, set_at=None)
        return Held(slot=slot.path, held=True, set_at=version.written_at)

    async def keep(
        self,
        slot: KeySlot,
        value: str,
        *,
        actor: str,
        trace_id: str,
        ent_hash: str = "",
    ) -> Kept:
        """Write `value` into `slot` and record that it was written, in that order, or raise.

        No vault first, because a person told to fix a paste on an install that cannot keep one
        has been given the wrong thing to do. Then what was given, judged before anything is
        sent. Then the write, in a worker thread because the vault's client blocks, whose failure
        is a silence or a refusal and never both. Then the record, which only a kept key reaches;
        see `THE_KEY_IS_KEPT_BEFORE_IT_IS_RECORDED_AND_A_LOST_RECORD_IS_LOUD` for why it comes
        second and why losing it does not unsay the write. Every event this logs names the slot,
        the actor and the trace id and nothing else. `ent_hash` is the writer's reach as a digest,
        and empty from the setup wizard, which has none.
        """
        vault = self._vault
        if vault is None:
            log.info("credential not kept", slot=slot.path, actor=actor, vault=VaultState.ABSENT)
            raise CredentialsUnavailableError(VaultState.ABSENT)
        problems = problems_with(value)
        if problems:
            log.info(
                "credential refused",
                slot=slot.path,
                actor=actor,
                problems=[one.code for one in problems],
            )
            raise CredentialProblemError(problems)
        try:
            set_at = await asyncio.to_thread(
                vault.write_static_kv, slot.path, {KEY_FIELD: value.strip()}
            )
        except VaultUnreachableError as silent:
            state = VaultState.UNREACHABLE
            log.info("credential not kept", slot=slot.path, actor=actor, vault=state)
            raise CredentialsUnavailableError(state) from silent
        except SecretsUnavailableError as refused:
            state = VaultState.REFUSED
            log.info("credential not kept", slot=slot.path, actor=actor, vault=state)
            raise CredentialsUnavailableError(state) from refused
        log.info("credential kept", slot=slot.path, actor=actor, trace_id=trace_id)
        await self._record(slot, actor=actor, trace_id=trace_id, ent_hash=ent_hash)
        return Kept(slot=slot.path, set_at=set_at)

    async def _record(self, slot: KeySlot, *, actor: str, trace_id: str, ent_hash: str) -> None:
        """Record a key already kept, and never raise: the key is in the vault either way.

        Broad, because any failure here is the same fact, a kept key with no record, and the one
        thing that must not follow is a person told their key was not saved. The type name alone
        is logged, for the reason `brain.credential_routes` gives about an exception's message.
        """
        if self._writes is None:
            log.warning(
                "credential write has no ledger to be recorded in",
                slot=slot.path,
                actor=actor,
                trace_id=trace_id,
            )
            return
        try:
            await self._writes.record(
                slot=slot.path, written_by=actor, trace_id=trace_id, ent_hash=ent_hash
            )
        except Exception as exc:
            log.error(
                "credential write not recorded",
                slot=slot.path,
                actor=actor,
                trace_id=trace_id,
                error=type(exc).__name__,
            )

    def put_to_use(self, slot: CredentialSlot, value: str) -> InUse:
        """Hand a key this process has just kept to its own provider SDK, unless it is outranked.

        Outranked means the environment set this variable before the vault was asked at start,
        and it will again on every start, so handing the new key over here would make this
        process disagree with every sibling and with itself after a restart. See
        `A_KEY_IN_USE_HERE_IS_NOT_IN_USE_EVERYWHERE`.
        """
        if slot.provider.env_var in self._outranking:
            return InUse.OUTRANKED
        put_into_environment(slot.provider, value.strip(), environ=self._environ)
        return InUse.HERE


def told_in_use(slot: CredentialSlot, in_use: InUse) -> str:
    """What a person is told about which processes use a key just kept, in words to act on."""
    if in_use is InUse.OUTRANKED:
        variable = slot.provider.env_var
        return (
            "The key is held in the vault and is not in use yet: the server's environment sets "
            f"{variable}, which wins over the vault every time the system starts. Remove "
            f"{variable} from the environment file and restart the system."
        )
    return (
        "The key is held in the vault and in use by the server process that answered. Any "
        "other server process uses it from its next start, so restart the system to be sure "
        "every question reaches the provider."
    )


# ------------------------------------------------------------------------ the wiring


def credentials_at_start(
    address: str,
    token: str,
    *,
    environ: MutableMapping[str, str] | None = None,
    make_vault: Callable[[str, str], OpenBaoVault] | None = None,
) -> Credentials:
    """This process's `Credentials`, with every held provider key loaded into its environment.

    Called by the lifespan with the two settings. Both blank is no vault and says so once;
    one blank is no vault as well and names which, because a half-configured vault that was
    tried anyway fails on its first request as a refusal, which sends somebody to read a policy.
    The names the environment already sets are taken before anything is loaded, which is what
    `InUse.OUTRANKED` is judged against afterwards. Never raises: a vault that cannot be asked
    at start is an install that answers without its keys, and says why in the log.
    """
    if not address and not token:
        log.info("no secrets vault configured")
        return Credentials(None)
    if not address or not token:
        missing = "BRAIN_VAULT_ADDRESS" if not address else "BRAIN_VAULT_TOKEN"
        log.warning("secrets vault half configured, so none is used", missing=missing)
        return Credentials(None)
    build = make_vault if make_vault is not None else _application_vault
    try:
        vault = build(address, token)
    except ValueError:
        log.warning("secrets vault address is not a URL, so none is used")
        return Credentials(None)
    outranking = names_in_environment(environ=environ)
    try:
        loaded = load_into_environment(vault, environ=environ)
    except SecretsUnavailableError:
        # Only raised for a slot named as required, and none is named here. Caught anyway,
        # because the one thing start-up must not do over a key is refuse to start.
        loaded = ()
    log.info(
        "provider keys loaded",
        from_vault=sorted(set(loaded) - outranking),
        from_environment=sorted(outranking),
    )
    return Credentials(vault, outranking=outranking, environ=environ)


def _application_vault(address: str, token: str) -> OpenBaoVault:
    return OpenBaoVault(address, token, role=VaultRole.APPLICATION)
