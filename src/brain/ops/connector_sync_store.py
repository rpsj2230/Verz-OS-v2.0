"""The rows behind reading a connected source: the live connections, the attempts, the records.

`brain.ops.connector_sync` decides what may be read and what an attempt costs, and
`brain.ops.connector_sync_run` performs the reading. This holds the SQL between them and the
Connectors screen, and decides nothing, for the split CLAUDE.md names.

**The live connections are `brain.ops.connector_store.every_live`, with the row's id added.** A
second statement for "which sources are connected" would be a second answer to it, and the one the
screen lists and the one the worker reads could then disagree about a source disconnected a minute
ago. The id is added because an attempt names the connection it read with; see
`brain.tables.connector_sync`.

**A record is written by one upsert that revives only what a sync retired, and never moves a reading
backwards.** Its conflict target is `proj.record`'s key, the one the previous release names too. It
updates a live row, or a row a complete read retired (one whose `deleted_at` is a retirement's
`noticed_at` in `proj.record_retired`), clearing `deleted_at` so a record the source returns serves
again; a row an erasure or a person retired stays retired whatever the source says, which is
`0045`'s rule. The update applies only when this reading is not older than the one stored, so a
slower reading cannot overwrite a faster one's. See
`A_RETIRED_RECORD_STAYS_RETIRED_WHATEVER_THE_SOURCE_SAYS` and
`A_RETURNED_RECORD_SERVES_AGAIN_AND_ITS_RETIREMENT_IS_KEPT`.

**A retirement and an epoch are statements here and decisions in `brain.ops.connector_sync`.**
`retire_unseen` stamps `statement_timestamp()`, the one instant `0045`'s policy lets the application
write, and copies each row it retires into `proj.record_retired` in the same statement, and
`advance_epoch` counts a change in `proj.source_epoch`; the worker runs each in the
transaction of the write it describes. `StoredSourceEpochs` is the answer path's read of them,
and `ReadThroughSourceEpochs` keeps that read for `SOURCE_EPOCHS_TTL_SECONDS` in the cache when an
install has one (M6.2.5), so a question costs no database read for its epochs. **A read-through and
not a cache the worker writes**, because the worker holds no cache client and a counter kept only in
the cache could start again at zero under an answer it once invalidated; a reading lost here is
read again from the counter, which is the record.

**The worker writes as the login its URL names**, which on an install is the database's owner, as
`brain.ops.erasure_store` and `brain.ops.webhook_delivery` already do. Under the application role
`0045`'s update policy raises on a conflict with a retired row instead of skipping it, so one record
somebody erased would fail every sync of its source for good.

**The screen's read is one statement over live connections**, newest attempt first per connection
and the last read to the end beside it, so a connection disconnected and connected again shows the
new connection's history and none of the old one's. A test a person asked for is an attempt too
(`0142`), so the newest attempt is the test when one is newer, which is how a test's finding
reaches the source's health; see `brain.ops.connector_probe`.

**A test is asked for by a row in `ops.setting` and answered by a row here.** `StoredProbes` writes
the first in the attribution the ledger's trigger reads, and reads both back for the page; the
worker's statements over the second are `probe_targets` and `probe_starts`.

Task ids: M42.6.5, M31.3.2.3, M31.3.2.4, M27.15.8, M11.4.6, M11.4.8, M11.8.4, M11.8.11
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final, Protocol, cast, runtime_checkable

from sqlalchemy import (
    Insert,
    RowMapping,
    Select,
    Table,
    and_,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.contract import HealthState
from brain.connectors.projection import ProjectedRecord
from brain.gate.caches import (
    SOURCE_EPOCHS_KEY,
    SOURCE_EPOCHS_TTL_SECONDS,
    CachedSourceEpochs,
)
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.connector_probe import (
    REQUEST_NAMESPACE,
    ProbeRecord,
    ProbeStatus,
    ProbeTarget,
    request_probe,
    requests_in,
)
from brain.ops.connector_store import Connection, every_live
from brain.ops.connector_sync import Attempt, ReadState, StoredValue, SyncOutcome, SyncState
from brain.ops.setting_store import read_namespace, values_under
from brain.tables.audit import attributed_to
from brain.tables.connector_connection import ConnectorConnectionRow
from brain.tables.connector_sync import ConnectorSyncRow
from brain.tables.projection import ProjectedRecordRow, RetiredRecordRow, SourceEpochRow

#: Why the upsert's update is conditional.
A_RETIRED_RECORD_STAYS_RETIRED_WHATEVER_THE_SOURCE_SAYS: Final = (
    "A projected record is retired by an erasure or by a person, and 0045 makes a retirement "
    "final. A sync that revived such a record because the source still lists it would undo an "
    "erasure on the next run, silently, as the worker. So the conflict update applies to a live "
    "row or to a row a complete read retired, and only when this reading is not older than the "
    "one stored."
)

#: Why a returned record revives its row and the retirement survives it.
A_RETURNED_RECORD_SERVES_AGAIN_AND_ITS_RETIREMENT_IS_KEPT: Final = (
    "A complete read that no longer returns a record retires its row and copies it, as it stood, "
    "into proj.record_retired with when the absence was noticed. When the source returns the "
    "record, its row serves again, and the copy is never touched, so which records went and when "
    "stays on file however often they come back."
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
    """The newest attempt of every live connection, when each was last read to the end, and where
    reading it stood."""
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
    # The newest read's own sentence, which is where a lost field is said and kept. See
    # `brain.ops.connector_sync.fields_lost_of`.
    read = (
        select(
            ConnectorSyncRow.connection_id,
            ConnectorSyncRow.detail.label("synced_detail"),
        )
        .where(ConnectorSyncRow.outcome == SyncOutcome.SYNCED.value)
        .distinct(ConnectorSyncRow.connection_id)
        .order_by(ConnectorSyncRow.connection_id, ConnectorSyncRow.finished_at.desc())
        .subquery("read")
    )
    # Where reading stood, from the newest attempt that recorded it: a test of the connection
    # records none and must not make the next read start again.
    placed = (
        select(ConnectorSyncRow.connection_id, ConnectorSyncRow.read_state)
        .distinct(ConnectorSyncRow.connection_id)
        .where(ConnectorSyncRow.read_state.is_not(None))
        .order_by(ConnectorSyncRow.connection_id, ConnectorSyncRow.finished_at.desc())
        .subquery("placed")
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
            read.c.synced_detail,
            placed.c.read_state,
        )
        .join(
            ConnectorConnectionRow,
            and_(
                ConnectorConnectionRow.id == newest.c.connection_id,
                ConnectorConnectionRow.disconnected_at.is_(None),
            ),
        )
        .outerjoin(synced, synced.c.connection_id == newest.c.connection_id)
        .outerjoin(read, read.c.connection_id == newest.c.connection_id)
        .outerjoin(placed, placed.c.connection_id == newest.c.connection_id)
        .order_by(newest.c.connector)
    )


def record_upsert(record: ProjectedRecord, fields: Mapping[str, StoredValue]) -> Insert:
    """Write one projected record, refresh its live row, or revive a row a sync retired. See
    `A_RETIRED_RECORD_STAYS_RETIRED_WHATEVER_THE_SOURCE_SAYS`."""
    statement = insert(ProjectedRecordRow).values(
        source=record.source,
        entity=record.entity,
        source_id=record.source_id,
        fields=dict(fields),
        last_seen_at=record.last_seen_at,
    )
    table = ProjectedRecordRow.__table__
    # A retirement a sync made, and no other: its `noticed_at` is the row's `deleted_at`. Written
    # as SQL naming both tables in full, because SQLAlchemy renders a subquery inside a conflict
    # clause with the outer table in its FROM list and no schema, which PostgreSQL cannot resolve;
    # it holds no value from anywhere, so nothing is interpolated into it.
    by_a_read = text(
        "EXISTS (SELECT 1 FROM proj.record_retired AS retired"
        " WHERE retired.source = proj.record.source"
        " AND retired.entity = proj.record.entity"
        " AND retired.source_id = proj.record.source_id"
        " AND retired.noticed_at = proj.record.deleted_at)"
    )
    return statement.on_conflict_do_update(
        index_elements=[table.c.source, table.c.entity, table.c.source_id],
        set_={
            "fields": statement.excluded.fields,
            "last_seen_at": statement.excluded.last_seen_at,
            "updated_at": func.now(),
            "deleted_at": None,
        },
        where=and_(
            or_(table.c.deleted_at.is_(None), by_a_read),
            table.c.last_seen_at <= statement.excluded.last_seen_at,
        ),
    )


def live_fields(source: str, entity: str, source_ids: Sequence[str]) -> Select[Any]:
    """The live index rows of these records, as they stand before a page is written over them."""
    return select(ProjectedRecordRow.source_id, ProjectedRecordRow.fields).where(
        ProjectedRecordRow.source == source,
        ProjectedRecordRow.entity == entity,
        ProjectedRecordRow.source_id.in_(list(source_ids)),
        ProjectedRecordRow.deleted_at.is_(None),
    )


def seen_since(source: str, entity: str, since: datetime) -> Select[Any]:
    """The ids of one entity's live rows a read that began at `since` has seen, in any attempt.

    A row a read wrote carries a `last_seen_at` of that read, never before it began, which is the
    same test `retire_unseen` makes from the other side. How an entity listed under another is
    carried on into the parents an earlier attempt kept: see `brain.ops.connector_sync.
    A_WALK_CUT_SHORT_IS_CARRIED_ON_IN_EVERY_SHAPE`.
    """
    return select(ProjectedRecordRow.source_id).where(
        ProjectedRecordRow.source == source,
        ProjectedRecordRow.entity == entity,
        ProjectedRecordRow.deleted_at.is_(None),
        ProjectedRecordRow.last_seen_at >= since,
    )


def retire_unseen(source: str, entity: str, before: datetime) -> Insert:
    """Retire every live row of one entity the read that began at `before` did not see, and keep
    each as it stood in `proj.record_retired`, in one statement.

    A row the read saw carries a `last_seen_at` of that read, which is never before it began; a
    row it did not see keeps an older one. Stamped with `statement_timestamp()`, which is when the
    absence was noticed and the one instant `0045`'s policy lets the application write, and the
    copy carries the same instant as its `noticed_at`, which is how a returned record's upsert
    knows a sync retired it. See
    `brain.ops.connector_sync.WHAT_A_COMPLETE_READ_OF_EVERYTHING_DID_NOT_RETURN_IS_RETIRED`.
    """
    # A cast at the ORM's boundary: a declarative class's `__table__` is typed as the `FromClause`
    # it is declared as, and these are `Table`s. Tables rather than classes, so the statement is
    # plain SQL with no session bookkeeping to evaluate a server-side instant in Python.
    table = cast(Table, ProjectedRecordRow.__table__)
    retired = cast(Table, RetiredRecordRow.__table__)
    gone = (
        update(table)
        .where(
            table.c.source == source,
            table.c.entity == entity,
            table.c.deleted_at.is_(None),
            table.c.last_seen_at < before,
        )
        .values(deleted_at=func.statement_timestamp())
        .returning(
            table.c.source,
            table.c.entity,
            table.c.source_id,
            table.c.local_id,
            table.c.fields,
            table.c.last_seen_at,
            table.c.deleted_at,
        )
        .cte("gone")
    )
    # Returning each retirement's id, because the driver reports no row count for an INSERT fed by
    # a data-modifying CTE (-1, measured), and the caller counts what was retired.
    return (
        insert(retired)
        .returning(retired.c.id)
        .from_select(
            ["source", "entity", "source_id", "local_id", "fields", "last_seen_at", "noticed_at"],
            select(
                gone.c.source,
                gone.c.entity,
                gone.c.source_id,
                gone.c.local_id,
                gone.c.fields,
                gone.c.last_seen_at,
                gone.c.deleted_at,
            ),
        )
    )


def advance_epoch(source: str) -> Insert:
    """Count one change to a source's rows. See `brain.tables.projection.SourceEpochRow`."""
    statement = insert(SourceEpochRow).values(source=source, epoch=1)
    table = SourceEpochRow.__table__
    return statement.on_conflict_do_update(
        index_elements=[table.c.source],
        set_={"epoch": table.c.epoch + 1, "updated_at": func.now()},
    )


def source_epochs() -> Select[Any]:
    """Every source's epoch."""
    return select(SourceEpochRow.source, SourceEpochRow.epoch)


@runtime_checkable
class SourceEpochs(Protocol):
    """What the answer path reads to key a cached answer on its sources' changes."""

    async def epochs(self) -> Mapping[str, int]:
        """Every source's epoch, by name. A source with none has never changed a row."""
        ...


class StoredSourceEpochs:
    """`SourceEpochs` over this install's database, as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def epochs(self) -> Mapping[str, int]:
        async with self._sessions() as session, session.begin():
            rows = (await session.execute(source_epochs())).all()
        return MappingProxyType({str(name): int(epoch) for name, epoch in rows})


class EpochsCache(Protocol):
    """Where a reading of every source's epoch is kept: `brain.cache.source_epochs_cache`.

    Never raises: a store that is down is a miss on `get` and a dropped write on `set`, which is
    `brain.cache.ValkeyRecordCache`'s promise, so an unreachable cache slows a question down and
    never fails it.
    """

    def get(self, key: str) -> CachedSourceEpochs | None: ...

    def set(self, key: str, value: CachedSourceEpochs, ttl_seconds: int) -> None: ...


class ReadThroughSourceEpochs:
    """`SourceEpochs` from the cache when it holds a reading, else from `inner`, which it keeps.

    See `brain.gate.caches.ONE_EPOCH_SOURCE_KEYS_AN_ANSWER`: this is the counter, read less often,
    and never a second epoch source. The reading is the whole mapping under one key, because the
    database read it saves is the whole table in one statement.
    """

    def __init__(self, inner: SourceEpochs, cache: EpochsCache) -> None:
        self._inner = inner
        self._cache = cache

    async def epochs(self) -> Mapping[str, int]:
        kept = self._cache.get(SOURCE_EPOCHS_KEY)
        if kept is not None:
            return MappingProxyType(dict(kept.epochs))
        read = await self._inner.epochs()
        self._cache.set(
            SOURCE_EPOCHS_KEY,
            CachedSourceEpochs(key=SOURCE_EPOCHS_KEY, epochs=dict(read)),
            SOURCE_EPOCHS_TTL_SECONDS,
        )
        return read


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
        # A sync hands nothing to the corpus since 2026-09-28 (connector_sync.A_SYNC_KEEPS_NO_BODY);
        # the column keeps the rows written before, and a migration may drop it.
        documents=0,
        consecutive_failures=attempt.consecutive_failures,
        next_attempt_at=attempt.next_attempt_at,
        detail=attempt.detail,
        lease=attempt.lease.value,
        read_state=None if attempt.read_state is None else attempt.read_state.stored(),
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
        synced_detail=str(row["synced_detail"] or ""),
        read_state=ReadState.from_stored(str(row["connector"]), row["read_state"]),
    )


async def held_by_record(
    session: AsyncSession, source: str, entity: str, source_ids: Sequence[str]
) -> Mapping[str, frozenset[str]]:
    """The fields the index holds on each of these live records, by the record's id.

    Read for a page before the page is written, because a run that has lost a field writes its
    records without it. See `brain.ops.connector_sync.A_FIELD_IS_LOST_WHEN_THE_RECORDS_THAT_
    CARRIED_IT_NO_LONGER_DO`.
    """
    if not source_ids:
        return MappingProxyType({})
    rows = await session.execute(
        select(ProjectedRecordRow.source_id, ProjectedRecordRow.fields).where(
            ProjectedRecordRow.source == source,
            ProjectedRecordRow.entity == entity,
            ProjectedRecordRow.source_id.in_(list(source_ids)),
            ProjectedRecordRow.deleted_at.is_(None),
        )
    )
    return MappingProxyType({str(one): frozenset(dict(fields)) for one, fields in rows.all()})


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


# ---------------------------------------------------------------------- the tests


def probe_targets() -> Select[Any]:
    """Every live connection, with when a test of it last started, or null when none has."""
    tested = (
        select(
            ConnectorSyncRow.connection_id,
            func.max(ConnectorSyncRow.started_at).label("last_probe_started"),
        )
        .where(ConnectorSyncRow.outcome == SyncOutcome.PROBED.value)
        .group_by(ConnectorSyncRow.connection_id)
        .subquery("tested")
    )
    return (
        select(ConnectorConnectionRow.connector, tested.c.last_probe_started)
        .outerjoin(tested, tested.c.connection_id == ConnectorConnectionRow.id)
        .where(ConnectorConnectionRow.disconnected_at.is_(None))
        .order_by(ConnectorConnectionRow.connector)
    )


def probe_starts(connection_id: uuid.UUID, since: datetime) -> Select[Any]:
    """When each test of this connection since `since` started, oldest first."""
    return (
        select(ConnectorSyncRow.started_at)
        .where(
            ConnectorSyncRow.connection_id == connection_id,
            ConnectorSyncRow.outcome == SyncOutcome.PROBED.value,
            ConnectorSyncRow.started_at >= since,
        )
        .order_by(ConnectorSyncRow.started_at)
    )


def latest_probe(connector: str) -> Select[Any]:
    """The newest test of this source's live connection, if it has been tested."""
    return (
        select(
            ConnectorSyncRow.started_at,
            ConnectorSyncRow.finished_at,
            ConnectorSyncRow.health,
            ConnectorSyncRow.detail,
        )
        .join(
            ConnectorConnectionRow,
            and_(
                ConnectorConnectionRow.id == ConnectorSyncRow.connection_id,
                ConnectorConnectionRow.disconnected_at.is_(None),
            ),
        )
        .where(
            ConnectorConnectionRow.connector == connector,
            ConnectorSyncRow.outcome == SyncOutcome.PROBED.value,
        )
        .order_by(ConnectorSyncRow.started_at.desc())
        .limit(1)
    )


async def read_probe_targets(session: AsyncSession) -> tuple[ProbeTarget, ...]:
    """`probe_targets`, as the worker's rule takes it."""
    rows = (await session.execute(probe_targets())).all()
    return tuple(ProbeTarget(connector=str(name), last_probe_started=last) for name, last in rows)


async def read_probe_starts(
    session: AsyncSession, connection_id: uuid.UUID, since: datetime
) -> tuple[datetime, ...]:
    """`probe_starts`, as instants."""
    return tuple((await session.execute(probe_starts(connection_id, since))).scalars().all())


@runtime_checkable
class ConnectorProbes(Protocol):
    """What the Connectors page needs to ask for a test and to see how it went."""

    async def ask(
        self, connector: str, *, at: datetime, by: str, trace_id: str, ent_hash: str
    ) -> None:
        """Ask for one test of this source, recorded on the ledger as `by`'s."""
        ...

    async def status(self, connector: str) -> ProbeStatus:
        """Whether a test of this source waits for the worker, and what the newest one found."""
        ...


class StoredProbes:
    """`ConnectorProbes` over this install's database, as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def ask(
        self, connector: str, *, at: datetime, by: str, trace_id: str, ent_hash: str
    ) -> None:
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(actor_id=by, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            await request_probe(session, connector, at=at, by=by)

    async def status(self, connector: str) -> ProbeStatus:
        async with self._sessions() as session, session.begin():
            states = values_under(
                await read_namespace(session, REQUEST_NAMESPACE), REQUEST_NAMESPACE
            )
            asked = requests_in({connector: states[connector]} if connector in states else {})
            row = (await session.execute(latest_probe(connector))).first()
        last = (
            None
            if row is None
            else ProbeRecord(
                started_at=row[0], finished_at=row[1], health=str(row[2]), detail=str(row[3])
            )
        )
        return ProbeStatus(requested_at=asked.get(connector), last=last)
