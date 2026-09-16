"""The rows behind an export: the window read from the ledger, and the record the export leaves.

`brain.ops.data_transfer` decides who may take an audit trail export, renders it and verifies it;
this holds the transaction it happens in and re-decides nothing. It reads the window, hands the
entries to the caller's `produce`, writes `ops.data_export` from what came back, and commits, and
`0053`'s trigger appends the ledger entry inside the same commit.

**The row and the document commit together.** The document exists only in memory until the
transaction that recorded it has committed, and the route hands it over only after that. A failure
anywhere before the commit, in rendering, in the insert or in the trigger's append, rolls the
record back and returns no document, so there is no path that hands over an export and leaves no
record of it. See `THE_ROW_AND_THE_DOCUMENT_COMMIT_TOGETHER`.

**The actor, the reach's digest and the trace are set in the transaction**, as
`brain.gate.review_store` sets them, so the ledger entry the trigger writes carries the reach the
export was taken under rather than the zero digest a statement at the server would get.

**Entries are read in sequence order inside a time window, one more than the ceiling.** The extra
row is how `produce` knows a window is too large without anything counting the whole window, and
reading the ledger inside the export's own transaction means the entries exported and the append
recording the export are one consistent view of the chain.

**The log is read back whole and narrowed by the route.** `StoredExports.recent` returns every
person's newest exports, and `brain.erasure_routes` hands each to
`brain.console.govern_surfaces.export_log`, which decides who may be told that it happened.

Task ids: M27.8.16, M27.7.24
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, runtime_checkable

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.ledger import AuditEntry
from brain.audit_routes import entry_from
from brain.ops.data_transfer import AuditExportRefusedError, Produced
from brain.ops.export import ExportReason
from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING, AuditEntryRow
from brain.tables.data_export import DataExportRow, ExportDataSet

#: Why the document is not handed over before the commit.
THE_ROW_AND_THE_DOCUMENT_COMMIT_TOGETHER: Final = (
    "An export handed over before its record committed can leave the building with no record, "
    "if the insert or the ledger append then fails. So the document is built inside the "
    "transaction and returned only once it has committed, and a failure at any step returns "
    "nothing and records nothing."
)

#: What a person is told when an entry in the window cannot be read as a ledger entry.
AN_ENTRY_THAT_DOES_NOT_READ: Final = (
    "An entry in this window cannot be read as an audit entry, so the window cannot be exported "
    "as it was written. The audit trail's own check reports which one; choose a window that does "
    "not include it."
)


@dataclass(frozen=True)
class TakenExport:
    """One export's record, as `ops.data_export` holds it. Never the document."""

    export_id: str
    data_set: ExportDataSet
    requested_by: str
    reason: ExportReason
    reason_reference: str
    produced_at: datetime
    first_seq: int | None
    last_seq: int | None
    entries: int
    verified: bool
    document_digest: str


@runtime_checkable
class ExportRecords(Protocol):
    """What the Import and export routes need from the database. `StoredExports` is one."""

    async def take_audit_export(
        self,
        *,
        since: datetime,
        until: datetime,
        limit: int,
        actor: str,
        ent_hash: str,
        trace_id: str,
        reason: ExportReason,
        reason_reference: str,
        at: datetime,
        produce: Callable[[Sequence[AuditEntry]], Produced],
    ) -> tuple[TakenExport, Produced]:
        """Read the window, produce the export, record it and commit, or do none of it."""
        ...

    async def taken_by(self, principal_id: str, *, limit: int) -> tuple[TakenExport, ...]:
        """The newest exports this person took, newest first."""
        ...


@runtime_checkable
class ExportLog(Protocol):
    """What the Retention screen's export log needs from the database. `StoredExports` is one.

    A protocol of its own rather than a third method on `ExportRecords`, because the log is read
    by a screen whose reader may take no export at all, and a fake standing in for the export
    routes should not have to answer for a list it never serves.
    """

    async def recent(self, *, limit: int) -> tuple[TakenExport, ...]:
        """The newest exports anybody took, newest first."""
        ...


def _set_config(name: str, value: str) -> Any:
    # `set_config(..., true)` is transaction-scoped, which is what a pooled connection needs.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


def taken_from(row: DataExportRow) -> TakenExport:
    """The record a row holds."""
    return TakenExport(
        export_id=str(row.export_id),
        data_set=ExportDataSet(row.data_set),
        requested_by=row.requested_by,
        reason=ExportReason(row.reason),
        reason_reference=row.reason_reference,
        produced_at=row.produced_at,
        first_seq=row.first_seq,
        last_seq=row.last_seq,
        entries=row.entries,
        verified=row.verified,
        document_digest=row.document_digest,
    )


class StoredExports:
    """`obs.audit_entry` read, and `ops.data_export` written, in one transaction per export."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def take_audit_export(
        self,
        *,
        since: datetime,
        until: datetime,
        limit: int,
        actor: str,
        ent_hash: str,
        trace_id: str,
        reason: ExportReason,
        reason_reference: str,
        at: datetime,
        produce: Callable[[Sequence[AuditEntry]], Produced],
    ) -> tuple[TakenExport, Produced]:
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(ACTOR_SETTING, actor))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            rows = (
                (
                    await session.execute(
                        select(AuditEntryRow)
                        .where(AuditEntryRow.at >= since, AuditEntryRow.at < until)
                        .order_by(AuditEntryRow.seq)
                        .limit(limit + 1)
                    )
                )
                .scalars()
                .all()
            )
            entries: list[AuditEntry] = []
            for row in rows:
                entry = entry_from(row)
                if entry is None:
                    raise AuditExportRefusedError(AN_ENTRY_THAT_DOES_NOT_READ)
                entries.append(entry)
            produced = produce(entries)
            record = DataExportRow(
                export_id=uuid.uuid4(),
                data_set=ExportDataSet.AUDIT_TRAIL.value,
                requested_by=actor,
                reason=reason.value,
                reason_reference=reason_reference,
                produced_at=at,
                first_seq=produced.first_seq,
                last_seq=produced.last_seq,
                entries=produced.entries,
                verified=produced.verified,
                document_digest=produced.digest,
            )
            session.add(record)
            await session.flush()
            taken = taken_from(record)
        return taken, produced

    async def taken_by(self, principal_id: str, *, limit: int) -> tuple[TakenExport, ...]:
        async with self._sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        select(DataExportRow)
                        .where(DataExportRow.requested_by == principal_id)
                        .order_by(DataExportRow.produced_at.desc(), DataExportRow.export_id)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return tuple(taken_from(row) for row in rows)

    async def recent(self, *, limit: int) -> tuple[TakenExport, ...]:
        """Every person's exports, newest first. Who may be shown one is the route's to decide."""
        async with self._sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        select(DataExportRow)
                        .order_by(DataExportRow.produced_at.desc(), DataExportRow.export_id)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return tuple(taken_from(row) for row in rows)
