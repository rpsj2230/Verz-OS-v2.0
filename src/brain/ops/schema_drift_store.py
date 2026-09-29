"""The rows behind the nightly schema check: the last night's finding, tonight's, and what is gone.

`brain.ops.schema_drift` decides which fields a source no longer answers and
`brain.ops.schema_drift_run` reads the sources. This holds the SQL between them, the answer route
and the Connectors screen, and decides nothing, for the split CLAUDE.md names.

**Every read is over live connections only.** A finding names the connection it was made on, and a
source disconnected and connected again is a new connection, so the findings read are the newest
per live connection and kind of record, joined to the live rows by the same `every_live` the
Connectors screen lists. A field gone under an old connection's mapping is never held against a
new one. See `brain.tables.connector_schema`.

**The newest finding is the finding.** Rows are appended nightly and never edited, so what a source
no longer answers today is the newest row per connection and kind of record, read with one
`DISTINCT ON`, the shape `brain.ops.connector_sync_store.latest_attempts` reads attempts with.

Task ids: M11.8.7
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from sqlalchemy import Insert, Select, and_, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.connector_store import every_live
from brain.ops.schema_drift import SchemaFinding
from brain.tables.connector_connection import ConnectorConnectionRow
from brain.tables.connector_schema import ConnectorSchemaCheckRow


def latest_findings() -> Select[Any]:
    """The newest finding of every live connection's every kind of record."""
    newest = (
        select(ConnectorSchemaCheckRow)
        .distinct(ConnectorSchemaCheckRow.connection_id, ConnectorSchemaCheckRow.entity)
        .order_by(
            ConnectorSchemaCheckRow.connection_id,
            ConnectorSchemaCheckRow.entity,
            ConnectorSchemaCheckRow.checked_at.desc(),
        )
        .subquery("newest")
    )
    live = every_live().add_columns(ConnectorConnectionRow.id.label("live_id")).subquery("live")
    return (
        select(
            newest.c.connection_id,
            newest.c.connector,
            newest.c.entity,
            newest.c.checked_at,
            newest.c.sampled,
            newest.c.answered,
            newest.c.missing,
        )
        .join(
            live,
            and_(live.c.live_id == newest.c.connection_id, live.c.connector == newest.c.connector),
        )
        .order_by(newest.c.connector, newest.c.entity)
    )


def finding_row(connection_id: uuid.UUID, connector: str, finding: SchemaFinding) -> Insert:
    """Append one night's finding for one kind of record of one connection."""
    return insert(ConnectorSchemaCheckRow).values(
        connection_id=connection_id,
        connector=connector,
        entity=finding.entity,
        checked_at=finding.checked_at,
        sampled=finding.sampled,
        answered=list(finding.answered),
        missing=list(finding.missing),
    )


async def read_findings(
    session: AsyncSession,
) -> Mapping[tuple[uuid.UUID, str], SchemaFinding]:
    """The newest finding per live connection and kind of record, for tonight's judgement."""
    rows = (await session.execute(latest_findings())).mappings().all()
    return MappingProxyType(
        {
            (one["connection_id"], one["entity"]): SchemaFinding(
                entity=one["entity"],
                checked_at=one["checked_at"],
                sampled=int(one["sampled"]),
                answered=tuple(one["answered"]),
                missing=tuple(one["missing"]),
            )
            for one in rows
        }
    )


async def fields_gone(
    sessions: async_sessionmaker[AsyncSession],
) -> Mapping[tuple[str, str], tuple[str, ...]]:
    """What each connected source no longer answers, by source and kind of record.

    Only the pairs with something missing, so an empty mapping is a night with nothing gone, or no
    night yet. The answer route hands it to the lane and the Connectors screen reads it too.
    """
    async with sessions() as session:
        rows = (await session.execute(latest_findings())).mappings().all()
    return MappingProxyType(
        {
            (str(one["connector"]), str(one["entity"])): tuple(one["missing"])
            for one in rows
            if one["missing"]
        }
    )
