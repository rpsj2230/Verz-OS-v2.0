"""Where a migration's documents are kept: save a version, read the newest of a kind.

`ops.migration_record` (`0241`) holds one row per save, appended and never edited, and the
newest row of a kind is the current document. This module is the whole of the translation and
decides nothing: what a document may say is `brain.migration`'s, asked of it by
`brain.migration_routes` before a body reaches here.

**Written in the session's own name.** `0241`'s insert policy admits a row whose `recorded_by` is
`app.principal_id`, so the principal is set here, in the caller's transaction, before the insert.
Rejected: a store that took the principal from nowhere and left the policy to refuse a row with no
name, which is a refusal nobody can act on.

**The newest, and nothing older.** A screen shows the current document, and an auditor asked "what
did the criteria say when the period started" reads the earlier rows, which is a query this module
does not offer because no screen asks it. `history` returns the saves of a kind newest first, so the
question has an answer without a second table.

Task ids: M37.1.1.1
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from brain.tables.migration_record import MigrationRecordRow, RecordKind

#: The most versions one history returns. A screen showing more is a log.
MOST_VERSIONS: Final = 50


@dataclass(frozen=True)
class Saved:
    """One saved version of one document: its body, who saved it and when."""

    kind: RecordKind
    body: dict[str, Any]
    by: str
    at: datetime


def saved_of(row: MigrationRecordRow) -> Saved:
    return Saved(
        kind=RecordKind(row.kind), body=dict(row.body), by=row.recorded_by, at=row.recorded_at
    )


async def save(session: AsyncSession, kind: RecordKind, body: dict[str, Any], *, by: str) -> None:
    """Append a version of `kind`, as `by`, in the caller's transaction. Does not commit."""
    await session.execute(text("SELECT set_config('app.principal_id', :by, true)"), {"by": by})
    await session.execute(
        insert(MigrationRecordRow).values(kind=kind.value, body=body, recorded_by=by)
    )


async def newest(session: AsyncSession, kind: RecordKind) -> Saved | None:
    """The current version of a document, or None when nobody has saved one."""
    found = await session.execute(
        select(MigrationRecordRow)
        .where(MigrationRecordRow.kind == kind.value)
        .order_by(MigrationRecordRow.recorded_at.desc(), MigrationRecordRow.id)
        .limit(1)
    )
    row = found.scalar_one_or_none()
    return None if row is None else saved_of(row)


async def history(
    session: AsyncSession, kind: RecordKind, *, limit: int = MOST_VERSIONS
) -> tuple[Saved, ...]:
    """The saved versions of a document, newest first, at most `MOST_VERSIONS`."""
    found = await session.execute(
        select(MigrationRecordRow)
        .where(MigrationRecordRow.kind == kind.value)
        .order_by(MigrationRecordRow.recorded_at.desc(), MigrationRecordRow.id)
        .limit(min(limit, MOST_VERSIONS))
    )
    return tuple(saved_of(row) for row in found.scalars().all())
