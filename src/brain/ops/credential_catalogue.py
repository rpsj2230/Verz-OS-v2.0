"""Every credential slot an install declares, by kind, and what the Credentials screen says of it.

Until 2026-09-29 each credential had its own screen and its own writer: a provider key on Models,
the relay password on Notifications, a source's key on Connectors, a channel's secret on its set-up
route, and the object store's key pair on nothing at all, only a vault command typed at the server.
Nobody could answer "which secrets does this install hold, and when was each set" without opening
five screens and a shell. This is the one list: **every slot the install declares, read from the
modules that own each kind rather than listed again**, so a provider added to `PROVIDER_SLOTS`, a
source added to `SLOT_SCOPES` or a channel wire added to `brain.channels` is a row here with nothing
else to edit.

**Five kinds, and what differs between them is written down per slot, not branched on later.**
Which fields the slot holds (the relay's `password`, the store's key pair, `api_key` for the rest),
which process reads it and when a new value is used (`InUse`), what to ask the issuer for and never,
the environment variable that outranks it, and whether its first value goes in here. A route that
writes a slot reads those facts off `DeclaredSlot` and has no `if kind ==` of its own to get wrong.

**A source's key and a channel's secret are replaced here, never first set here.** Their first
value is written where the thing is set up, because a key written without the settings that say
what it reaches is a key nothing can account for
(`brain.ops.credentials.A_CONNECTED_SOURCE_S_KEY_IS_WRITTEN_BY_CONNECTING_IT`). Once the slot holds
one, replacing it changes nothing about what it reaches, so the Credentials screen may. See
`A_FIRST_KEY_GOES_IN_WHERE_ITS_THING_IS_SET_UP`.

**A slot whose name the audit ledger cannot record is listed and not written.** Every credential
write is recorded under `credential:<slot>`, and `brain.audit.record.CREDENTIAL_SLOT` admits
lower-case segments and underscores only, so `providers/cloudflare-r2` would be written into the
vault and lost from the ledger. It is shown with the sentence saying where it is written instead.
See `EVERY_WRITE_FROM_THIS_SCREEN_IS_ON_THE_LEDGER`.

**The vault is read in `brain.ops.vault_status`'s order: the seal first, without the token, then
what the token carries, then each slot's metadata**, which carries versions and times and no field
of a secret. One more question is asked of an open vault: whether the policy it loaded lets this
process mint the one-read token live reads borrow a source's key with (needs-rupash 99). A release
that changed `application.hcl` is not in force until somebody with the unseal pieces loads the
policies again, and until then the screen says so in a sentence. See
`LIVE_READS_WAIT_FOR_THE_POLICY_THE_VAULT_LOADED`.

Rejected: listing every object store backend's slot. Only the one `INSTALL_OBJECT_STORE_BACKEND`
names is read, and a second row for a store the install does not use is a row somebody fills in.
Rejected: listing webhook subscribers' signing secrets here. Each is minted with its subscriber on
the Webhooks screen and rotated there, and a list of subscribers is that screen's list.

Task ids: M27.11.10, M27.15.50
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final, Protocol, runtime_checkable

from brain.audit.record import credential_subject_id
from brain.channels.adapter import channel_wires
from brain.connectors.declaration import shipped
from brain.gate.context import Channel
from brain.ops.channel_store import channel_secret_slot
from brain.ops.connector_lease import RUN_TOKEN_ROLE
from brain.ops.connector_slots import SLOT_SCOPES
from brain.ops.credentials import (
    KEY_FIELD,
    MAX_CREDENTIAL_CHARS,
    Credentials,
    CredentialSlot,
    InUse,
    KeySlot,
    connector_key_slot,
)
from brain.ops.mail import RELAY_CREDENTIAL_FIELD, RELAY_CREDENTIAL_SLOT
from brain.ops.object_store import ACCESS_KEY_FIELD, SECRET_KEY_FIELD
from brain.ops.openbao import VaultRefusedError
from brain.ops.secrets import VaultRole
from brain.ops.storage import Backend, credential_path, static_credential_backends
from brain.ops.vault_status import (
    POLICIES_UNKNOWN,
    SEAL_SAYS,
    SLOTS_REFUSED,
    SLOTS_SILENT,
    Seal,
    SlotState,
    TokenPolicy,
    TokenReport,
    VaultStatusReader,
    token_report,
)

# ------------------------------------------------------------------ written-down reasons

#: Why a source's key and a channel's secret are replaced here and first set elsewhere.
A_FIRST_KEY_GOES_IN_WHERE_ITS_THING_IS_SET_UP: Final = (
    "A source's key and a channel's secret reach whatever the settings chosen with them say, so "
    "their first value is written where those settings are chosen. A slot that already holds one "
    "has those settings, and replacing its value changes nothing about what it reaches, so the "
    "Credentials screen replaces it and does not create it."
)

#: Why a slot the ledger cannot name is listed and not written.
EVERY_WRITE_FROM_THIS_SCREEN_IS_ON_THE_LEDGER: Final = (
    "Every value written from this screen leaves a credential entry in the audit ledger under "
    "the slot's name, and the ledger's grammar admits lower-case words joined by underscores. A "
    "slot named outside it would be written into the vault with no entry saying who wrote it, "
    "so it is listed with where it is written instead."
)

#: Why the screen asks the vault whether live reads may run, rather than reading the policy file.
LIVE_READS_WAIT_FOR_THE_POLICY_THE_VAULT_LOADED: Final = (
    "The application policy in this release lets a question borrow a source's key for one read, "
    "but a vault enforces the policy it loaded, and a release's policies are loaded by its deploy "
    "step, or not at all on an install whose vault is still opened by people. So the vault is "
    "asked what its loaded policy lets this token do on that one mint, and the screen says in "
    "words when live reads are waiting for it."
)

# ---------------------------------------------------------------------- the vocabulary


class SlotKind(enum.StrEnum):
    """What a slot's value is for. Listed in this order."""

    PROVIDER = "provider"
    RELAY = "relay"
    STORE = "store"
    CONNECTOR = "connector"
    CHANNEL = "channel"


#: The order kinds are listed in: what every question uses first, what one source uses last.
KIND_ORDER: Final[Mapping[SlotKind, int]] = MappingProxyType(
    {kind: position for position, kind in enumerate(SlotKind)}
)


class ReadBy(enum.StrEnum):
    """Which server process reads a slot's value to use it."""

    APPLICATION = "application"
    WORKER = "worker"


class LiveReads(enum.StrEnum):
    """Whether the policy the vault loaded lets a question borrow a source's key."""

    READY = "ready"
    WAITING = "waiting"
    #: The vault is not open, or did not say.
    UNKNOWN = "unknown"


#: The one mint a live read needs, as `brain.ops.live_read_run` makes it.
LIVE_READ_MINT_PATH: Final = f"auth/token/create/{RUN_TOKEN_ROLE}"

LIVE_READS_SAY: Final[Mapping[LiveReads, str]] = MappingProxyType(
    {
        LiveReads.READY: (
            "Answers can read a connected source live: the vault's loaded policy lets this "
            "process borrow a source's key for one read."
        ),
        LiveReads.WAITING: (
            "Answers cannot read connected sources live yet: the vault is still enforcing the "
            "application policy from before live reads. Each deploy applies its release's "
            "policies itself; a vault still opened by people moves first with "
            "ops/openbao/switch-to-auto-unseal.sh (ops/openbao/UNSEAL.md, Moving an older "
            "install)."
        ),
        LiveReads.UNKNOWN: "",
    }
)

#: The fields a slot's form asks for, and what a person is told each one accepts before sending.
FORMAT_TOLD: Final = (
    f"One unbroken line of at most {MAX_CREDENTIAL_CHARS:,} characters, pasted as the issuer shows "
    "it. A line break at the end is removed; a space or a line break inside it is refused. It is "
    "never shown again."
)

#: The label a slot of one field asks for its value under, by kind.
VALUE_LABELS: Final[Mapping[SlotKind, str]] = MappingProxyType(
    {
        SlotKind.PROVIDER: "API key",
        SlotKind.RELAY: "Password",
        SlotKind.CONNECTOR: "Key",
        SlotKind.CHANNEL: "Secret",
    }
)

#: The label each field of a slot of several is asked under.
FIELD_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {ACCESS_KEY_FIELD: "Access key ID", SECRET_KEY_FIELD: "Secret access key"}
)

#: The built-in providers by the names a person knows them by. Held against `PROVIDER_SLOTS`.
PROVIDER_HOLDERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "anthropic": "Anthropic (Claude)",
        "openai": "OpenAI",
        "moonshot": "Moonshot (Kimi)",
        "deepseek": "DeepSeek",
    }
)

#: What to ask a model provider for, and never.
PROVIDER_ASK: Final = ("an API key from the provider's own console, for this company's account",)
PROVIDER_NEVER: Final = ("an organisation owner's key, which can change billing and members",)

RELAY_HOLDER: Final = "Mail relay"
RELAY_DESCRIPTION: Final = (
    "The password for the relay's user name, which every email this install sends signs in with."
)
RELAY_ASK: Final = ("the password of a relay user that may only send mail",)
RELAY_NEVER: Final = ("a mailbox administrator's password",)

#: Each static backend's name, and what to ask for and never: `ops/openbao/credential-slots.md`.
STORE_HOLDERS: Final[Mapping[Backend, str]] = MappingProxyType(
    {
        Backend.SEAWEEDFS: "File store (SeaweedFS)",
        Backend.CLOUDFLARE_R2: "File store (Cloudflare R2)",
    }
)
STORE_ASK: Final[Mapping[Backend, tuple[str, ...]]] = MappingProxyType(
    {
        Backend.SEAWEEDFS: (
            "the key pair of the brain-application identity, which may read, write and list",
        ),
        Backend.CLOUDFLARE_R2: (
            "an R2 API token's key pair scoped to this install's buckets, object read and write",
        ),
    }
)
STORE_NEVER: Final[Mapping[Backend, tuple[str, ...]]] = MappingProxyType(
    {
        Backend.SEAWEEDFS: ("an identity with Admin, which can delete a bucket",),
        Backend.CLOUDFLARE_R2: ("an account-wide token",),
    }
)
STORE_DESCRIPTION: Final = (
    "The key pair the application signs every request to the object store with: artifacts, the "
    "backup bucket's descriptions and storage figures."
)

#: A source the connector declarations do not name, by the name a person knows it by.
CONNECTOR_HOLDERS: Final[Mapping[str, str]] = MappingProxyType({"staff_source": "Staff list"})

CHANNEL_HOLDERS: Final[Mapping[Channel, str]] = MappingProxyType(
    {Channel.LARK: "Lark chat", Channel.WEBHOOK: "Inbound webhook"}
)
CHANNEL_ASK: Final[Mapping[Channel, tuple[str, ...]]] = MappingProxyType(
    {
        Channel.LARK: ("the App Secret of the app this company created for its assistant",),
        Channel.WEBHOOK: ("the signing secret the sending system was given for this install",),
    }
)
CHANNEL_ASK_OTHERWISE: Final = ("the secret the channel's vendor issued for this install",)
CHANNEL_NEVER: Final = ("a secret another app or receiver already uses",)

#: Said on a slot whose first value goes in elsewhere and which holds none yet.
FIRST_SET_ELSEWHERE: Final[Mapping[SlotKind, str]] = MappingProxyType(
    {
        SlotKind.CONNECTOR: (
            "Its first key goes in when the source is connected, where its settings are chosen. "
            "Once it holds one, it can be replaced here."
        ),
        SlotKind.CHANNEL: (
            "Its first secret goes in when the channel is set up. Once it holds one, it can be "
            "replaced here."
        ),
    }
)

#: Said on a slot whose name the ledger cannot record.
WRITTEN_AT_THE_SERVER: Final = (
    "This slot's name cannot be recorded in the audit log, so its key pair is written at the "
    "server with the vault's command line: ops/openbao/credential-slots.md, The object store's key."
)


def takes_effect_told(kind: SlotKind, in_use: InUse, *, backend: Backend | None = None) -> str:
    """When a value written into a slot of this kind is used, in words to act on."""
    if in_use is InUse.AT_START:
        told = (
            "The key pair is held in the vault. The system reads it when it starts, so restart "
            "the system to use it."
        )
        if backend is Backend.SEAWEEDFS:
            told += (
                " The file store must hold the same pair in its identities file, or it refuses "
                "every request signed with it."
            )
        return told
    if kind is SlotKind.RELAY:
        return "The password is held in the vault and is used for the next message sent."
    if kind is SlotKind.CONNECTOR:
        return "The key is held in the vault and is used from the next read of this source."
    if kind is SlotKind.CHANNEL:
        return "The secret is held in the vault and is used from the next message on this channel."
    return (
        "The key is held in the vault and in use by the server process that answered. Every other "
        "server process picks it up from the vault within a minute, with no restart."
    )


# ------------------------------------------------------------------------ the shapes


@dataclass(frozen=True)
class DeclaredSlot:
    """One slot the install declares, and every fact about it a route needs to list or write it."""

    kind: SlotKind
    #: The write target. A `CredentialSlot` for a provider, so its key can be put to use here.
    slot: KeySlot
    #: What the value belongs to, as a person names it.
    holder: str
    #: The fields its value is written under, in the order the form asks for them.
    fields: tuple[str, ...]
    ask_for: tuple[str, ...]
    never: tuple[str, ...]
    read_by: ReadBy
    #: When a new value is used, before any environment variable is considered.
    takes_effect: InUse
    #: What a figure of when it was last used is looked up by: a provider's slug, a source's name,
    #: a channel's name. Empty where nothing records a use.
    used_by: str = ""
    #: The provider variable that outranks the slot when this process's environment sets it.
    env_var: str = ""
    #: Its first value is written where its thing is set up. See the named constant.
    replace_only: bool = False
    #: The object store's backend, for the sentence about its identities file.
    backend: Backend | None = None

    @property
    def path(self) -> str:
        return self.slot.path

    @property
    def family(self) -> str:
        return self.path.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.path.split("/", 1)[1]

    @property
    def recordable(self) -> bool:
        """Whether the ledger can record a write to this slot. See the named constant."""
        try:
            credential_subject_id(self.path)
        except ValueError:
            return False
        return True

    @property
    def provider(self) -> CredentialSlot | None:
        return self.slot if isinstance(self.slot, CredentialSlot) else None


def _connector_holder(name: str) -> str:
    declared = shipped().get(name)
    if declared is not None:
        return declared.label
    return CONNECTOR_HOLDERS.get(name, name.replace("_", " ").capitalize())


def declared_slots(store: Credentials, *, backend: str) -> tuple[DeclaredSlot, ...]:
    """Every slot this install declares, in `KIND_ORDER` and then by path.

    `backend` is `INSTALL_OBJECT_STORE_BACKEND` as `brain.install.value_of` read it; a backend
    nothing stores a key for (AWS S3, whose key is a lease) or a value nobody recognises lists no
    store slot, because there is no slot to fill.
    """
    found: list[DeclaredSlot] = [
        DeclaredSlot(
            kind=SlotKind.PROVIDER,
            slot=one,
            holder=PROVIDER_HOLDERS.get(one.provider.slug, one.provider.slug),
            fields=(KEY_FIELD,),
            ask_for=PROVIDER_ASK,
            never=PROVIDER_NEVER,
            read_by=ReadBy.APPLICATION,
            takes_effect=InUse.HERE,
            used_by=one.provider.slug,
            env_var=one.provider.env_var,
        )
        for one in store.slots()
    ]
    found.append(
        DeclaredSlot(
            kind=SlotKind.RELAY,
            slot=KeySlot(path=RELAY_CREDENTIAL_SLOT, description=RELAY_DESCRIPTION),
            holder=RELAY_HOLDER,
            fields=(RELAY_CREDENTIAL_FIELD,),
            ask_for=RELAY_ASK,
            never=RELAY_NEVER,
            read_by=ReadBy.APPLICATION,
            takes_effect=InUse.NEXT_USE,
        )
    )
    try:
        chosen: Backend | None = Backend(backend)
    except ValueError:
        chosen = None
    if chosen is not None and chosen in static_credential_backends():
        found.append(
            DeclaredSlot(
                kind=SlotKind.STORE,
                slot=KeySlot(path=credential_path(chosen), description=STORE_DESCRIPTION),
                holder=STORE_HOLDERS.get(chosen, chosen.value),
                fields=(ACCESS_KEY_FIELD, SECRET_KEY_FIELD),
                ask_for=STORE_ASK.get(chosen, ()),
                never=STORE_NEVER.get(chosen, ()),
                read_by=ReadBy.APPLICATION,
                takes_effect=InUse.AT_START,
                backend=chosen,
            )
        )
    for name in sorted(SLOT_SCOPES):
        scopes = SLOT_SCOPES[name]
        found.append(
            DeclaredSlot(
                kind=SlotKind.CONNECTOR,
                slot=connector_key_slot(name),
                holder=_connector_holder(name),
                fields=(KEY_FIELD,),
                ask_for=scopes.request,
                never=scopes.refuse,
                read_by=ReadBy.WORKER,
                takes_effect=InUse.NEXT_USE,
                used_by=name,
                replace_only=True,
            )
        )
    for channel in sorted(channel_wires()):
        found.append(
            DeclaredSlot(
                kind=SlotKind.CHANNEL,
                slot=channel_secret_slot(channel),
                holder=CHANNEL_HOLDERS.get(channel, channel.value.capitalize()),
                fields=(KEY_FIELD,),
                ask_for=CHANNEL_ASK.get(channel, CHANNEL_ASK_OTHERWISE),
                never=CHANNEL_NEVER,
                read_by=ReadBy.APPLICATION,
                takes_effect=InUse.NEXT_USE,
                used_by=channel.value,
                replace_only=True,
            )
        )
    return tuple(sorted(found, key=lambda one: (KIND_ORDER[one.kind], one.path)))


def declared_at(slots: Sequence[DeclaredSlot], path: str) -> DeclaredSlot | None:
    """The declared slot at `path`, or None."""
    for one in slots:
        if one.path == path:
            return one
    return None


# ------------------------------------------------------------------- reading the vault


@runtime_checkable
class CapabilityLookup(Protocol):
    """A reader that can ask what its own token may do on a path. `OpenBaoVault` is one."""

    def capabilities_self(self, path: str) -> tuple[str, ...]:
        """What the loaded policies let this token do on `path`."""
        ...


@dataclass(frozen=True)
class SlotReading:
    """What one slot's metadata said: its state, and when its value was written."""

    state: SlotState
    set_at: datetime | None = None


UNKNOWN: Final = SlotReading(SlotState.UNKNOWN)


@dataclass(frozen=True)
class CatalogueReport:
    """The vault as the Credentials screen may describe it, and what each slot holds."""

    seal: Seal
    told: str
    #: Why the slots are unknown when the vault is open and they are, or empty.
    slots_unread: str
    token: TokenReport
    live_reads: LiveReads
    readings: Mapping[str, SlotReading]

    def reading(self, path: str) -> SlotReading:
        return self.readings.get(path, UNKNOWN)


def live_reads_of(reader: object) -> LiveReads:
    """Whether the loaded policy lets this process mint a live read's token. Never raises."""
    if not isinstance(reader, CapabilityLookup):
        return LiveReads.UNKNOWN
    try:
        allowed = set(reader.capabilities_self(LIVE_READ_MINT_PATH))
    except Exception:
        # Broad for `brain.ops.vault_status.report`'s reason: whatever stopped the answer, the
        # vault did not say, and not saying is not a policy that refuses.
        return LiveReads.UNKNOWN
    if allowed & {"create", "update", "root"}:
        return LiveReads.READY
    return LiveReads.WAITING


def _reading(reader: VaultStatusReader, one: DeclaredSlot) -> SlotReading:
    version = reader.static_kv_version(one.path)
    if version is not None:
        return SlotReading(SlotState.HELD, version.written_at)
    if one.kind is SlotKind.CONNECTOR and reader.static_kv_defined(one.path):
        return SlotReading(SlotState.DEFINED)
    return SlotReading(SlotState.EMPTY)


def read_catalogue(
    reader: VaultStatusReader | None,
    slots: Sequence[DeclaredSlot],
    role: VaultRole = VaultRole.APPLICATION,
) -> CatalogueReport:
    """The seal, the token, live reads and every slot, in that order. Never raises for the vault."""
    none: TokenReport = TokenReport(TokenPolicy.UNKNOWN, (), POLICIES_UNKNOWN)
    if reader is None:
        seal = Seal.ABSENT
    else:
        try:
            status = reader.seal_status()
        except Exception:
            # Broad, for `brain.ops.vault_status.report`'s reason.
            seal = Seal.UNREACHABLE
        else:
            if not status.initialized:
                seal = Seal.UNINITIALISED
            elif status.sealed:
                seal = Seal.SEALED
            else:
                seal = Seal.OPEN
    if reader is None or seal is not Seal.OPEN:
        return CatalogueReport(seal, SEAL_SAYS[seal], "", none, LiveReads.UNKNOWN, {})
    token = token_report(reader, role)
    live = live_reads_of(reader)
    try:
        readings = {one.path: _reading(reader, one) for one in slots}
    except VaultRefusedError:
        return CatalogueReport(seal, SEAL_SAYS[seal], SLOTS_REFUSED, token, live, {})
    except Exception:
        return CatalogueReport(seal, SEAL_SAYS[seal], SLOTS_SILENT, token, live, {})
    return CatalogueReport(seal, SEAL_SAYS[seal], "", token, live, MappingProxyType(readings))


def offered(one: DeclaredSlot, report: CatalogueReport) -> str:
    """Why this slot's form is not offered now, or empty when it is.

    A slot the ledger cannot name, a vault that cannot be asked, a slot nobody could read, and a
    slot whose first value goes in elsewhere and holds none, in that order.
    """
    if not one.recordable:
        return WRITTEN_AT_THE_SERVER
    if report.seal is not Seal.OPEN:
        return report.told
    reading = report.reading(one.path)
    if reading.state is SlotState.UNKNOWN:
        return report.slots_unread or report.told
    if one.replace_only and reading.state is not SlotState.HELD:
        return FIRST_SET_ELSEWHERE[one.kind]
    return ""
