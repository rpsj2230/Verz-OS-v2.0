"""Where a channel's record, its deliveries and its secret are kept, and nothing that decides.

`brain.tables.channel` holds the argument for the two tables. This module reads and writes them
and borrows a channel's secret from the vault, and it decides nothing about any of it: whether a
request is refused, whether a reply goes out and what is recorded are
`brain.channels.inbound`'s and `brain.channels.outbound`'s, which take everything here through
the protocols below. That is `brain.ops.limit_store`'s split, for its reason: a rule cannot be
tested for the case that is always wrong through a module that opens a connection.

**A channel's secret is a provider credential, and the application reads it.** The vendor issued
it, it is valid until the vendor revokes it, and nothing can mint one per request, which is what
the `providers` engine holds; the mail relay's password is there for the same reason
(`brain.ops.mail.A_RELAY_CREDENTIAL_IS_A_PROVIDER_CREDENTIAL`). The process that verifies an
arriving request and sends the reply is the application, and `ops/openbao/policies/application.hcl`
already lets it write, read and read the metadata of a slot there, so no policy has to be reloaded
on an install for a channel to work. See `A_CHANNEL_CREDENTIAL_IS_A_PROVIDER_CREDENTIAL`.

**The secrets reader refuses every slot that is not a channel's.** It reads under the same engine
as the model providers' keys, so a reader that took any path would be a second way to read them.
`VaultChannelSecrets` refuses a reference outside `providers/channel_` before the vault is asked,
and the record's own check derives the path from the channel. See
`A_CHANNEL_READS_ONLY_ITS_OWN_SLOT`.

**Every change to a record is attributed, and the database writes it to the ledger.** `save` and
`switch` take who is writing, at what reach and in which request, and execute
`brain.tables.audit.attributed_to` in the transaction before the write, so the trigger `0114` puts
on `ops.channel` records the entry with the writer's reach digest and the request's trace rather
than `0003`'s placeholders. The route has no other way to write a record. See
`A_CHANNEL_CHANGE_IS_ATTRIBUTED_IN_ITS_OWN_TRANSACTION`.

**A delivery entry is checked before it is written.** The pairing of direction and outcome and the
rule that a reason is given exactly when nothing was delivered are the table's checks, and
`DeliveryEntry` makes them again so a wrong entry fails where it was built rather than as a
database error inside a request that had otherwise finished.

**A delivery is stamped by the clock when its row is written, not when its transaction began.** The
column's default is `now()`, which is the instant the transaction started, so every delivery written
in one transaction shared a time and `recent` then ordered them by a random id: the Channels
screen's health, which is decided by the newest delivery, was a coin toss between them. Found by the
install's own health check (`brain.ops.acceptance_checks_channels`), which writes a sent and then a
refused delivery in one rolled-back transaction. `record` names `clock_timestamp()`, which moves
inside a transaction where `now()` does not, and which needs no migration. See
`A_DELIVERY_IS_STAMPED_WHEN_IT_IS_WRITTEN`.

Rejected: the channel's own key under `connector_keys/`, which is where `brain.ops.lark_connect`
keeps the Lark app's credential for the chat use today. The application policy grants no read
there, deliberately, because a connector's key is read by the worker that runs the connector; a
channel is not run by the worker, and the process that must read its secret could not.

Task ids: M10.6.1, M10.6.3, M3.2.2, M10.1.4
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final, Protocol, runtime_checkable

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.context import Channel
from brain.gate.event_store import first_delivery
from brain.gate.ingress import ChannelEvent
from brain.ops.credentials import KEY_FIELD, CredentialVault, KeySlot, VaultState
from brain.ops.openbao import VaultRefusedError, VaultUnreachableError
from brain.ops.provider_keys import StaticKvReader
from brain.ops.secrets import SecretRef, SecretsUnavailableError, VaultRole
from brain.tables.audit import attributed_to
from brain.tables.channel import (
    CHANNEL_SECRET_PREFIX,
    OUTCOMES_BY_DIRECTION,
    ChannelDeliveryRow,
    ChannelRow,
    DeliveryOutcome,
    Direction,
    RefusedBecause,
)

# ------------------------------------------------------------------ written-down reasons

#: Why a channel's secret is kept under `providers/`.
A_CHANNEL_CREDENTIAL_IS_A_PROVIDER_CREDENTIAL: Final = (
    "A channel's secret is issued by its vendor, valid until they revoke it, and cannot be minted "
    "per request, which is what the providers engine holds. It is read by the process that "
    "verifies what arrives and sends the reply, which is the application, and that engine's "
    "policy already lets the application write, read and read the metadata of its slots."
)

#: Why the secrets reader refuses a path outside the channel prefix.
A_CHANNEL_READS_ONLY_ITS_OWN_SLOT: Final = (
    "Channel secrets share an engine with the model providers' keys, so a reader that took any "
    "path would be a second way to read a provider's key. A reference outside the channel prefix "
    "is refused before the vault is asked."
)

#: Why a record's write carries its attribution.
A_CHANNEL_CHANGE_IS_ATTRIBUTED_IN_ITS_OWN_TRANSACTION: Final = (
    "The ledger entry for a channel's set-up or switch is written by a trigger, which cannot know "
    "who is writing. The store sets the writer, their reach digest and the request's trace on the "
    "transaction before the write, so the entry names all three instead of placeholders."
)

#: Why a delivery's time is the clock's at the insert.
A_DELIVERY_IS_STAMPED_WHEN_IT_IS_WRITTEN: Final = (
    "A channel's health is decided by its newest delivery, so two deliveries must never share a "
    "time. The row is stamped with clock_timestamp() when it is written, which moves inside a "
    "transaction, rather than the column's default of now(), which is the transaction's start and "
    "left the order of two deliveries in one transaction to a random id."
)

#: How many delivery rows a listing reads at most. A page, not a history.
RECENT_DELIVERIES: Final = 100

#: The status a vault answers for a slot nothing was ever written to.
_SLOT_HOLDS_NOTHING: Final = 404


def channel_secret_slot(channel: Channel) -> KeySlot:
    """Where this channel's secret is kept. Derived, so no row or request can choose it."""
    return KeySlot(
        path=f"{CHANNEL_SECRET_PREFIX}{channel.value}",
        description=f"The secret {channel.value} signs its requests with or sends with.",
    )


def channel_secret_ref(channel: Channel) -> SecretRef:
    """The reference a record holds, for `channel_secret_slot`'s path and the application."""
    return SecretRef(path=channel_secret_slot(channel).path, role=VaultRole.APPLICATION)


# ------------------------------------------------------------------------ the shapes


@dataclass(frozen=True)
class ChannelRecord:
    """One channel's record on this install. Holds a reference to its secret, never the secret."""

    channel: Channel
    enabled: bool
    tenant: Mapping[str, str]
    secret: SecretRef
    updated_by: str
    updated_at: datetime


@dataclass(frozen=True)
class DeliveryEntry:
    """One delivery to record. No field could hold the message, its sender or its recipient."""

    channel: Channel
    direction: Direction
    outcome: DeliveryOutcome
    reason: RefusedBecause | None = None
    vendor_status: int | None = None

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES_BY_DIRECTION[self.direction]:
            msg = f"an {self.direction} delivery cannot be {self.outcome}"
            raise ValueError(msg)
        undelivered = self.outcome in (DeliveryOutcome.REFUSED, DeliveryOutcome.UNKNOWN)
        if undelivered != (self.reason is not None):
            msg = "a reason is given exactly when nothing was delivered or it is not known"
            raise ValueError(msg)


@dataclass(frozen=True)
class DeliveryView:
    """A recorded delivery and the instant the database gave it."""

    entry: DeliveryEntry
    recorded_at: datetime


# ------------------------------------------------------------------------ the protocols


@runtime_checkable
class ChannelRecords(Protocol):
    """Where channel records are kept. `StoredChannels` over a database."""

    async def get(self, channel: Channel) -> ChannelRecord | None:
        """This channel's record, or None when the install has none."""
        ...

    async def every(self) -> tuple[ChannelRecord, ...]:
        """Every record, in channel order."""
        ...

    async def save(
        self,
        channel: Channel,
        *,
        enabled: bool,
        tenant: Mapping[str, str],
        actor: str,
        ent_hash: str,
        trace_id: str,
    ) -> ChannelRecord:
        """Create or replace this channel's record, attributed, and answer with it as kept."""
        ...

    async def switch(
        self, channel: Channel, *, enabled: bool, actor: str, ent_hash: str, trace_id: str
    ) -> ChannelRecord | None:
        """Switch this channel's record on or off, attributed, or None when there is none."""
        ...


@runtime_checkable
class DeliveryRecords(Protocol):
    """Where deliveries are recorded. `StoredDeliveries` over a database."""

    async def record(self, entry: DeliveryEntry) -> None:
        """Append one delivery, in a transaction of its own."""
        ...

    async def recent(self, channel: Channel) -> tuple[DeliveryView, ...]:
        """This channel's newest deliveries, newest first, at most `RECENT_DELIVERIES`."""
        ...


@runtime_checkable
class EventClaims(Protocol):
    """Where an arrived message is claimed. `StoredClaims` over `gate.channel_event`."""

    async def first(self, event: ChannelEvent) -> bool:
        """True when this is the first delivery of this message, committed before returning."""
        ...


class ChannelSecretsUnavailableError(Exception):
    """The vault could not be asked, or refused. `state` says which."""

    def __init__(self, state: VaultState) -> None:
        super().__init__(state.value)
        self.state = state


@runtime_checkable
class ChannelSecrets(Protocol):
    """Where a channel's secret is borrowed from. `VaultChannelSecrets` over the vault."""

    def read(self, ref: SecretRef) -> str | None:
        """The secret, for the one check or send that uses it, or None when none is held."""
        ...

    def held(self, ref: SecretRef) -> bool:
        """Whether a secret is held, from the slot's metadata, which holds no field of it."""
        ...


# ------------------------------------------------------------------------ the database


def _record_of(row: ChannelRow) -> ChannelRecord:
    return ChannelRecord(
        channel=Channel(row.channel),
        enabled=row.enabled,
        tenant=MappingProxyType({str(k): str(v) for k, v in row.tenant.items()}),
        secret=SecretRef(path=row.secret_path, role=VaultRole(row.secret_role)),
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


async def _attribute(session: AsyncSession, *, actor: str, ent_hash: str, trace_id: str) -> None:
    """See `A_CHANNEL_CHANGE_IS_ATTRIBUTED_IN_ITS_OWN_TRANSACTION`. Before the write, always."""
    for statement in attributed_to(actor_id=actor, ent_hash=ent_hash, trace_id=trace_id):
        await session.execute(statement)


class StoredChannels:
    """`ops.channel`, read and written as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, channel: Channel) -> ChannelRecord | None:
        async with self._sessions() as session, session.begin():
            row = await session.get(ChannelRow, channel.value)
            return None if row is None else _record_of(row)

    async def every(self) -> tuple[ChannelRecord, ...]:
        async with self._sessions() as session, session.begin():
            rows = (
                await session.execute(select(ChannelRow).order_by(ChannelRow.channel))
            ).scalars()
            return tuple(_record_of(row) for row in rows)

    async def save(
        self,
        channel: Channel,
        *,
        enabled: bool,
        tenant: Mapping[str, str],
        actor: str,
        ent_hash: str,
        trace_id: str,
    ) -> ChannelRecord:
        ref = channel_secret_ref(channel)
        values: dict[str, Any] = {
            "enabled": enabled,
            "tenant": dict(tenant),
            "secret_path": ref.path,
            "secret_role": ref.role.value,
            "updated_by": actor,
        }
        statement = (
            insert(ChannelRow)
            .values(channel=channel.value, **values)
            .on_conflict_do_update(
                index_elements=["channel"], set_={**values, "updated_at": func.now()}
            )
            .returning(ChannelRow)
        )
        async with self._sessions() as session, session.begin():
            await _attribute(session, actor=actor, ent_hash=ent_hash, trace_id=trace_id)
            return _record_of((await session.execute(statement)).scalar_one())

    async def switch(
        self, channel: Channel, *, enabled: bool, actor: str, ent_hash: str, trace_id: str
    ) -> ChannelRecord | None:
        statement = (
            update(ChannelRow)
            .where(ChannelRow.channel == channel.value)
            .values(enabled=enabled, updated_by=actor, updated_at=func.now())
            .returning(ChannelRow)
        )
        async with self._sessions() as session, session.begin():
            await _attribute(session, actor=actor, ent_hash=ent_hash, trace_id=trace_id)
            row = (await session.execute(statement)).scalar_one_or_none()
            return None if row is None else _record_of(row)


class StoredDeliveries:
    """`ops.channel_delivery`, appended and read as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(self, entry: DeliveryEntry) -> None:
        statement = insert(ChannelDeliveryRow).values(
            channel=entry.channel.value,
            direction=entry.direction.value,
            outcome=entry.outcome.value,
            reason=None if entry.reason is None else entry.reason.value,
            vendor_status=entry.vendor_status,
            # See A_DELIVERY_IS_STAMPED_WHEN_IT_IS_WRITTEN.
            recorded_at=func.clock_timestamp(),
        )
        async with self._sessions() as session, session.begin():
            await session.execute(statement)

    async def recent(self, channel: Channel) -> tuple[DeliveryView, ...]:
        statement = (
            select(ChannelDeliveryRow)
            .where(ChannelDeliveryRow.channel == channel.value)
            .order_by(ChannelDeliveryRow.recorded_at.desc(), ChannelDeliveryRow.id)
            .limit(RECENT_DELIVERIES)
        )
        async with self._sessions() as session, session.begin():
            rows = (await session.execute(statement)).scalars().all()
        return tuple(
            DeliveryView(
                entry=DeliveryEntry(
                    channel=Channel(row.channel),
                    direction=Direction(row.direction),
                    outcome=DeliveryOutcome(row.outcome),
                    reason=None if row.reason is None else RefusedBecause(row.reason),
                    vendor_status=row.vendor_status,
                ),
                recorded_at=row.recorded_at,
            )
            for row in rows
        )


class StoredClaims:
    """`gate.channel_event`, through `brain.gate.event_store.first_delivery`, committed at once.

    Its own transaction, committed before the answer is made: a claim rolled back with a failed
    answer would let the vendor's retry be answered again, and a failed answer after a committed
    claim leaves one message unanswered, which is the direction a redelivered side effect cannot
    be allowed to fail in.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def first(self, event: ChannelEvent) -> bool:
        async with self._sessions() as session, session.begin():
            return await first_delivery(session, event)


# ------------------------------------------------------------------------ the vault


class ChannelVault(CredentialVault, StaticKvReader, Protocol):
    """What the channel secrets need from a vault: read a slot, and read its metadata."""


@dataclass(frozen=True)
class VaultChannelSecrets:
    """`ChannelSecrets` over this process's vault, as the application. Holds no value."""

    vault: ChannelVault | None = field(repr=False)

    def _vault_or_refuse(self, ref: SecretRef) -> ChannelVault:
        if not ref.path.startswith(CHANNEL_SECRET_PREFIX) or ref.role is not VaultRole.APPLICATION:
            msg = f"{ref.path!r} is not a channel's slot. {A_CHANNEL_READS_ONLY_ITS_OWN_SLOT}"
            raise ValueError(msg)
        if self.vault is None:
            raise ChannelSecretsUnavailableError(VaultState.ABSENT)
        return self.vault

    def read(self, ref: SecretRef) -> str | None:
        vault = self._vault_or_refuse(ref)
        try:
            fields = vault.read_static_kv(ref.path)
        except VaultRefusedError as refused:
            if refused.status == _SLOT_HOLDS_NOTHING:
                return None
            raise ChannelSecretsUnavailableError(VaultState.REFUSED) from refused
        except VaultUnreachableError as silent:
            raise ChannelSecretsUnavailableError(VaultState.UNREACHABLE) from silent
        except SecretsUnavailableError as refused:
            raise ChannelSecretsUnavailableError(VaultState.REFUSED) from refused
        value = fields.get(KEY_FIELD)
        return value if isinstance(value, str) and value else None

    def held(self, ref: SecretRef) -> bool:
        vault = self._vault_or_refuse(ref)
        try:
            return vault.static_kv_version(ref.path) is not None
        except VaultUnreachableError as silent:
            raise ChannelSecretsUnavailableError(VaultState.UNREACHABLE) from silent
        except SecretsUnavailableError as refused:
            raise ChannelSecretsUnavailableError(VaultState.REFUSED) from refused
