"""The rows behind connecting a source: which are connected, and the two writes that change it.

`brain.ops.connector_admin` decides what a connection must be, and `brain.connector_routes` asks who
may make one before this is reached. This holds the SQL between them and decides nothing, for the
split CLAUDE.md names: nothing that decides policy owns a client.

**A connection is one transaction, and the key is kept inside it, after a lock and before the row.**
The transaction takes a lock on the source's name, refuses a source already connected, keeps the key
through the callable it was handed, sets the request's trace and reach, and inserts the row, whose
trigger appends the ledger entry. See `THE_KEY_IS_KEPT_WHILE_THE_SOURCE_S_NAME_IS_LOCKED`.

**The lock is on the source and never on the ledger.** It is a transaction lock under two keys,
this module's class and the source's name hashed, and PostgreSQL keeps two-key locks apart from the
one-key lock every ledger append takes, so a second administrator connecting the same source waits
here and nobody else waits at all. The key's own record, `ops.credential_write`, is written by
`brain.ops.credentials.Credentials.keep` in a transaction of its own inside that window, and it can
take the ledger's lock because this transaction has not touched the ledger yet: its own append is
the insert, which comes last. Taking the ledger's lock first would deadlock that record against the
transaction waiting for it.

**The price, stated.** A connection holds a database connection for as long as the vault takes to
answer, which `brain.ops.openbao.TIMEOUT_SECONDS` bounds at five seconds, as
`brain.ops.webhook_store` already does. And a row that fails to insert after the vault accepted the
key leaves a key at a path no connection names, with its own record in the ledger saying it was
written; connecting that source again replaces it, because the path is the source's name.

**A connection grants the data steward what the source declares, in the same transaction.** The
steward's lock is taken after the key is kept and before the row is inserted, so it comes before
the ledger's, and `brain.identity.data_steward.grant_declared_in` writes the grants after the row,
attributed to the person connecting. With no steward appointed it writes nothing. A connection
that fails at any point writes no grant, because the grants are in the transaction that failed.
See `brain.identity.data_steward.A_CONNECTION_GRANTS_THE_STEWARD_WHAT_THE_SOURCE_DECLARES`.

**Disconnecting is one update, attributed, and the key is not touched.** The application's vault
policy grants no delete, which is argued in `ops/openbao/policies/application.hcl`, and the
sentence the screen shows says to revoke the key in the source's own settings. It retires no
grant either: `brain.identity.data_steward.DISCONNECTING_A_SOURCE_TAKES_NOTHING_FROM_THE_STEWARD`.

Rejected: checking for a live connection, keeping the key, and inserting, with nothing held between
the check and the insert. Two administrators connecting one source at once would both pass the
check and both write the vault, the last write would win the slot, and the insert that lost the
race to the unique index would leave the live row's settings beside the loser's key.

Task ids: M42.6.5, M27.9.9
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, runtime_checkable

from sqlalchemy import Insert, Select, Update, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.identity.data_steward import grant_declared_in, steward_lock
from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.connector_connection import ConnectorConnectionRow

# ------------------------------------------------------------ written-down reasons

#: Why the vault is written between the lock and the insert.
THE_KEY_IS_KEPT_WHILE_THE_SOURCE_S_NAME_IS_LOCKED: Final = (
    "Kept before the lock, two administrators connecting one source would both write its slot and "
    "the row that survived could stand beside the other's key. Kept after the insert, a vault that "
    "refused would leave a source recorded as connected with no key. Kept inside the transaction, "
    "after the lock and the check for a live connection, a second connection of the same source "
    "waits and is then refused before its key is written, and a refusal from the vault rolls "
    "everything back, so nothing is recorded as connected."
)

#: The first key of the lock a connection takes. Any constant no other two-key lock in this schema
#: uses; none does today. The second key is the source's name, hashed by the database.
CONNECT_LOCK_CLASS: Final = 42650


class ConnectorTakenError(Exception):
    """This source is already connected. Disconnect it before connecting it again."""


class NotConnectedError(Exception):
    """This source is not connected: it never was, or it has been disconnected."""


@dataclass(frozen=True)
class Connection:
    """One live connection: the source, its settings, the digest agreed to, and who and when."""

    connector: str
    settings: Mapping[str, str]
    digest: str
    connected_by: str
    connected_at: datetime


@runtime_checkable
class ConnectorRecords(Protocol):
    """What the Connectors routes need from the database. `StoredConnections` is one."""

    async def connected(self) -> tuple[Connection, ...]:
        """Every live connection, in the order of the sources' names."""
        ...

    async def connect(
        self,
        *,
        connector: str,
        settings: Mapping[str, str],
        digest: str,
        actor: str,
        trace_id: str,
        ent_hash: str,
        keep_key: Callable[[], Awaitable[datetime | None]],
        declared: Sequence[str] = (),
    ) -> Connection:
        """Record a connection with its key kept, or nothing. See the module docstring.

        `declared` is what the source's manifest declares, granted to the data steward in the same
        transaction. Empty grants nothing.
        """
        ...

    async def disconnect(
        self, connector: str, *, actor: str, trace_id: str, ent_hash: str
    ) -> datetime:
        """Mark a live connection disconnected, or raise `NotConnectedError`. Returns when."""
        ...


# ------------------------------------------------------------------- the statements


def _set_config(name: str, value: str) -> Any:
    # Transaction-local, as `brain.ops.credential_write_store` sets the same two for its trigger.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


def lock_on(connector: str) -> Any:
    """The transaction lock a connection of this source takes. Two keys, never the ledger's one."""
    return text("SELECT pg_advisory_xact_lock(:lock_class, hashtext(:connector))").bindparams(
        lock_class=CONNECT_LOCK_CLASS, connector=connector
    )


def live(connector: str) -> Select[Any]:
    """The live connection of one source, if there is one."""
    return select(ConnectorConnectionRow.id).where(
        ConnectorConnectionRow.connector == connector,
        ConnectorConnectionRow.disconnected_at.is_(None),
    )


def every_live() -> Select[Any]:
    """Every live connection, in name order. No disconnected row: the screen lists what reads."""
    return (
        select(
            ConnectorConnectionRow.connector,
            ConnectorConnectionRow.settings,
            ConnectorConnectionRow.digest,
            ConnectorConnectionRow.connected_by,
            ConnectorConnectionRow.connected_at,
        )
        .where(ConnectorConnectionRow.disconnected_at.is_(None))
        .order_by(ConnectorConnectionRow.connector)
    )


def connected_row(connector: str, settings: Mapping[str, str], digest: str, actor: str) -> Insert:
    """The row a connection leaves. The time is the database's, as the ledger entry's is."""
    return (
        insert(ConnectorConnectionRow)
        .values(connector=connector, settings=dict(settings), digest=digest, connected_by=actor)
        .returning(ConnectorConnectionRow.connected_at)
    )


def disconnection(connector: str, actor: str) -> Update:
    """Mark the live connection of one source disconnected, by `actor`, now."""
    return (
        update(ConnectorConnectionRow)
        .where(
            ConnectorConnectionRow.connector == connector,
            ConnectorConnectionRow.disconnected_at.is_(None),
        )
        .values(disconnected_by=actor, disconnected_at=func.now())
        .returning(ConnectorConnectionRow.disconnected_at)
    )


# ------------------------------------------------------------------------ the store


class StoredConnections:
    """`ConnectorRecords` over this install's database."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def connected(self) -> tuple[Connection, ...]:
        async with self._sessions() as session, session.begin():
            rows = (await session.execute(every_live())).mappings().all()
        return tuple(
            Connection(
                connector=one["connector"],
                settings={str(key): str(value) for key, value in dict(one["settings"]).items()},
                digest=one["digest"],
                connected_by=one["connected_by"],
                connected_at=one["connected_at"],
            )
            for one in rows
        )

    async def connect(
        self,
        *,
        connector: str,
        settings: Mapping[str, str],
        digest: str,
        actor: str,
        trace_id: str,
        ent_hash: str,
        keep_key: Callable[[], Awaitable[datetime | None]],
        declared: Sequence[str] = (),
    ) -> Connection:
        async with self._sessions() as session, session.begin():
            await session.execute(lock_on(connector))
            if (await session.execute(live(connector))).scalar_one_or_none() is not None:
                raise ConnectorTakenError(connector)
            await keep_key()
            # Before the row's ledger entry, for
            # `data_steward.THE_STEWARD_S_LOCK_COMES_BEFORE_THE_LEDGER_S`.
            await session.execute(steward_lock())
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            # Read by the grant trigger for the steward's grants; the connection's own trigger
            # names the column it reads.
            await session.execute(_set_config(ACTOR_SETTING, actor))
            try:
                at = (
                    await session.execute(connected_row(connector, settings, digest, actor))
                ).scalar_one()
            except IntegrityError as raced:
                raise ConnectorTakenError(connector) from raced
            await grant_declared_in(session, declared)
        return Connection(
            connector=connector,
            settings=dict(settings),
            digest=digest,
            connected_by=actor,
            connected_at=at,
        )

    async def disconnect(
        self, connector: str, *, actor: str, trace_id: str, ent_hash: str
    ) -> datetime:
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            at: datetime | None = (
                await session.execute(disconnection(connector, actor))
            ).scalar_one_or_none()
            if at is None:
                raise NotConnectedError(connector)
        return at
