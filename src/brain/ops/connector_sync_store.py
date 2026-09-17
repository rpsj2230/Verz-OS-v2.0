"""The rows behind reading a connected source: the live connections, the attempts, the records.

`brain.ops.connector_sync` decides what may be read and what an attempt costs, and
`brain.ops.connector_sync_run` performs the reading. This holds the SQL between them and the
Connectors screen, and decides nothing, for the split CLAUDE.md names.

**The live connections are `brain.ops.connector_store.every_live`, with the row's id added.** A
second statement for "which sources are connected" would be a second answer to it, and the one the
screen lists and the one the worker reads could then disagree about a source disconnected a minute
ago. The id is added because an attempt names the connection it read with; see
`brain.tables.connector_sync`.

**A record is written by one upsert that never revives a retired row and never moves a reading
backwards.** The conflict clause updates only a row that is still live and whose `last_seen_at` is
not newer than this reading's, so a record an erasure or a person retired stays retired whatever the
source still says, which is `0045`'s rule that a retirement is final, and a slower reading cannot
overwrite a faster one's. See `A_RETIRED_RECORD_STAYS_RETIRED_WHATEVER_THE_SOURCE_SAYS`.

**The worker writes as the login its URL names**, which on an install is the database's owner, as
`brain.ops.erasure_store` and `brain.ops.webhook_delivery` already do. Under the application role
`0045`'s update policy raises on a conflict with a retired row instead of skipping it, so one record
somebody erased would fail every sync of its source for good.

**The screen's read is one statement over live connections**, newest attempt first per connection
and the last read to the end beside it, so a connection disconnected and connected again shows the
new connection's history and none of the old one's.

Task ids: M42.6.5, M31.3.2.3, M31.3.2.4
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final, Protocol, runtime_checkable

from sqlalchemy import Insert, RowMapping, Select, and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.contract import HealthState
from brain.connectors.projection import ProjectedRecord
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.connector_store import Connection, every_live
from brain.ops.connector_sync import Attempt, StoredValue, SyncOutcome, SyncState
from brain.tables.connector_connection import ConnectorConnectionRow
from brain.tables.connector_sync import ConnectorSyncRow
from brain.tables.projection import ProjectedRecordRow

#: Why the upsert's update is conditional.
A_RETIRED_RECORD_STAYS_RETIRED_WHATEVER_THE_SOURCE_SAYS: Final = (
    "A projected record is retired by an erasure or by a person, and 0045 makes a retirement "
    "final. A sync that revived a retired record because the source still lists it would undo an "
    "erasure on the next run, silently, as the worker. So the conflict update applies only to a "
    "live row, and only when this reading is not older than the one stored."
)


@dataclass(frozen=True)
class LiveConnection:
    """One live connection and the id its attempts point at."""

    id: uuid.UUID
    connection: Connection


@runtime_checkable
class ConnectorSyncRecords(Protocol):
    """What the Connectors screen needs about reading. `StoredSyncStates` is one."""

    async def states(self) -> Mapping[str, SyncState]:
        """The last attempt of every live connection that has one, by the source's name."""
        ...


# ------------------------------------------------------------------- the statements


def live_connections() -> Select[Any]:
    """`every_live`, with each connection's id. See the module docstring."""
    return every_live().add_columns(ConnectorConnectionRow.id)


def latest_attempts() -> Select[Any]:
    """The newest attempt of every live connection, and when each was last read to the end."""
    newest = (
        select(ConnectorSyncRow)
        .distinct(ConnectorSyncRow.connection_id)
        .order_by(ConnectorSyncRow.connection_id, ConnectorSyncRow.finished_at.desc())
        .subquery("newest")
    )
    synced = (
        select(
            ConnectorSyncRow.connection_id,
            func.max(ConnectorSyncRow.finished_at).label("last_synced_at"),
        )
        .where(ConnectorSyncRow.outcome == SyncOutcome.SYNCED.value)
        .group_by(ConnectorSyncRow.connection_id)
        .subquery("synced")
    )
    return (
        select(
            newest.c.connection_id,
            newest.c.connector,
            newest.c.finished_at,
            newest.c.outcome,
            newest.c.health,
            newest.c.consecutive_failures,
            newest.c.next_attempt_at,
            newest.c.detail,
            synced.c.last_synced_at,
        )
        .join(
            ConnectorConnectionRow,
            and_(
                ConnectorConnectionRow.id == newest.c.connection_id,
                ConnectorConnectionRow.disconnected_at.is_(None),
            ),
        )
        .outerjoin(synced, synced.c.connection_id == newest.c.connection_id)
        .order_by(newest.c.connector)
    )


def record_upsert(record: ProjectedRecord, fields: Mapping[str, StoredValue]) -> Insert:
    """Write one projected record, or refresh it. See the module docstring for the condition."""
    statement = insert(ProjectedRecordRow).values(
        source=record.source,
        entity=record.entity,
        source_id=record.source_id,
        fields=dict(fields),
        last_seen_at=record.last_seen_at,
    )
    table = ProjectedRecordRow.__table__
    return statement.on_conflict_do_update(
        index_elements=[table.c.source, table.c.entity, table.c.source_id],
        set_={
            "fields": statement.excluded.fields,
            "last_seen_at": statement.excluded.last_seen_at,
            "updated_at": func.now(),
        },
        where=and_(
            table.c.deleted_at.is_(None),
            table.c.last_seen_at <= statement.excluded.last_seen_at,
        ),
    )


def attempt_row(connection_id: uuid.UUID, attempt: Attempt) -> Insert:
    """The row one finished attempt leaves."""
    return insert(ConnectorSyncRow).values(
        connection_id=connection_id,
        connector=attempt.connector,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        outcome=attempt.outcome.value,
        health=attempt.health.value,
        records=attempt.records,
        documents=attempt.documents,
        consecutive_failures=attempt.consecutive_failures,
        next_attempt_at=attempt.next_attempt_at,
        detail=attempt.detail,
        lease=attempt.lease.value,
    )


# ----------------------------------------------------------------------- the reads


def _state(row: RowMapping) -> SyncState:
    return SyncState(
        connector=str(row["connector"]),
        finished_at=row["finished_at"],
        outcome=SyncOutcome(row["outcome"]),
        health=HealthState(row["health"]),
        consecutive_failures=int(row["consecutive_failures"]),
        next_attempt_at=row["next_attempt_at"],
        detail=str(row["detail"]),
        last_synced_at=row["last_synced_at"],
    )


async def read_live(session: AsyncSession) -> tuple[LiveConnection, ...]:
    """Every live connection with its id, in the order of the sources' names."""
    rows = (await session.execute(live_connections())).mappings().all()
    return tuple(
        LiveConnection(
            id=one["id"],
            connection=Connection(
                connector=one["connector"],
                settings={str(key): str(value) for key, value in dict(one["settings"]).items()},
                digest=one["digest"],
                connected_by=one["connected_by"],
                connected_at=one["connected_at"],
            ),
        )
        for one in rows
    )


async def read_states(session: AsyncSession) -> Mapping[uuid.UUID, SyncState]:
    """The newest attempt of every live connection that has one, by connection id."""
    rows = (await session.execute(latest_attempts())).mappings().all()
    return MappingProxyType({one["connection_id"]: _state(one) for one in rows})


class StoredSyncStates:
    """`ConnectorSyncRecords` over this install's database."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def states(self) -> Mapping[str, SyncState]:
        async with self._sessions() as session, session.begin():
            rows = (await session.execute(latest_attempts())).mappings().all()
        return MappingProxyType({str(one["connector"]): _state(one) for one in rows})


# ---------------------------------------------------------------------- the leases


@dataclass(frozen=True)
class LeaseTally:
    """How one source's attempts' leases ended over a window. Counts of this install's own runs.

    Every figure is a count of attempts the worker made, never of anything a reader may not see:
    which sources a reader is told of is decided before a tally is looked up, as the Connectors
    screen decides it.
    """

    revoked: int = 0
    expired: int = 0
    not_revoked: int = 0

    @property
    def issued(self) -> int:
        return self.revoked + self.expired + self.not_revoked


@runtime_checkable
class LeaseCounts(Protocol):
    """What the Secrets vault screen needs about leases. `StoredLeaseCounts` is one."""

    async def tallies(self, since: datetime) -> Mapping[str, LeaseTally]:
        """Each live connection's lease endings since `since`, by the source's name."""
        ...


def lease_tallies(since: datetime) -> Select[Any]:
    """Attempts that held a lease since `since`, by source and ending, live connections only."""
    return (
        select(ConnectorSyncRow.connector, ConnectorSyncRow.lease, func.count().label("attempts"))
        .join(
            ConnectorConnectionRow,
            and_(
                ConnectorConnectionRow.id == ConnectorSyncRow.connection_id,
                ConnectorConnectionRow.disconnected_at.is_(None),
            ),
        )
        .where(
            ConnectorSyncRow.finished_at >= since,
            ConnectorSyncRow.lease != LeaseOutcome.NONE.value,
        )
        .group_by(ConnectorSyncRow.connector, ConnectorSyncRow.lease)
    )


def fold_tallies(rows: Sequence[tuple[str, str, int]]) -> Mapping[str, LeaseTally]:
    """The grouped counts as one tally per source. An ending this build does not know is refused."""
    found: dict[str, LeaseTally] = {}
    for connector, ending, attempts in rows:
        one = found.get(connector, LeaseTally())
        match LeaseOutcome(ending):
            case LeaseOutcome.REVOKED:
                one = LeaseTally(one.revoked + attempts, one.expired, one.not_revoked)
            case LeaseOutcome.EXPIRED:
                one = LeaseTally(one.revoked, one.expired + attempts, one.not_revoked)
            case LeaseOutcome.NOT_REVOKED:
                one = LeaseTally(one.revoked, one.expired, one.not_revoked + attempts)
            case LeaseOutcome.NONE:
                continue
        found[connector] = one
    return MappingProxyType(found)


class StoredLeaseCounts:
    """`LeaseCounts` over this install's database."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def tallies(self, since: datetime) -> Mapping[str, LeaseTally]:
        async with self._sessions() as session, session.begin():
            rows = (await session.execute(lease_tallies(since))).all()
        return fold_tallies([(str(a), str(b), int(c)) for a, b, c in rows])
