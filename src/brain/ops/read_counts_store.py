"""What the worker's newest run against each source read, for the processing register (M24.2.3).

`ops.connector_sync` records one row per attempt with the records and documents it read. The
register shows the newest per source, which is one `DISTINCT ON` over that table and nothing
else: no source is read to count it, and no index is scanned, for the owner's minimal-index rule.
`brain.ops.processing_register` decides what the counts mean; this owns the query.

Task ids: M24.2.3
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.processing_register import ReadCounts
from brain.tables.connector_sync import ConnectorSyncRow


@runtime_checkable
class ReadCountSource(Protocol):
    """The newest counts per source."""

    async def counts(self) -> Mapping[str, ReadCounts]: ...


class StoredReadCounts:
    """`ops.connector_sync`, newest attempt per source, as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def counts(self) -> Mapping[str, ReadCounts]:
        async with self._sessions() as session, session.begin():
            found = await session.execute(
                select(
                    ConnectorSyncRow.connector,
                    ConnectorSyncRow.records,
                    ConnectorSyncRow.documents,
                    ConnectorSyncRow.finished_at,
                )
                .distinct(ConnectorSyncRow.connector)
                .order_by(ConnectorSyncRow.connector, ConnectorSyncRow.finished_at.desc())
            )
            return {
                str(connector): ReadCounts(
                    records=int(records), documents=int(documents), finished_at=finished_at
                )
                for connector, records, documents, finished_at in found.all()
            }
