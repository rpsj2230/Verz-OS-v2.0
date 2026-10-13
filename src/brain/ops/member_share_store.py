"""An artifact handed to a colleague, kept and read as the two people it names (`0229`).

`record` and `withdraw` write as the sharer, because `0229`'s policies hold an insert and a
delete to the person the transaction names; `sent_by` and `received_by` read for one person and
the policy shows each only the rows they are on. **A row is a record that somebody was handed
something and admits nobody to anything**: whether the colleague may open it is
`brain.member_library.open_share`, asked at the moment of the read.

Task ids: M40.3.3.3
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.knowledge.search import PRINCIPAL_SETTING
from brain.member_library import Share
from brain.tables.member_share import ArtifactShareRow


def _as(principal_id: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(
        name=PRINCIPAL_SETTING, value=principal_id
    )


def _share(row: ArtifactShareRow) -> Share:
    return Share(
        artifact_id=row.artifact_id,
        shared_by=row.shared_by,
        shared_with=row.shared_with,
        at=row.shared_at,
    )


class StoredShares:
    """`agent.artifact_share` read and written."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(self, one: Share) -> None:
        """Keep one share as its sharer. The same artifact to the same colleague is one row."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(one.shared_by))
            await session.execute(
                pg_insert(ArtifactShareRow)
                .values(
                    artifact_id=one.artifact_id,
                    shared_by=one.shared_by,
                    shared_with=one.shared_with,
                    shared_at=one.at,
                )
                .on_conflict_do_nothing(index_elements=["artifact_id", "shared_by", "shared_with"])
            )

    async def withdraw(self, artifact_id: str, *, shared_by: str, shared_with: str) -> bool:
        """Take one share back as its sharer. False when there was none to take back."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(shared_by))
            gone = await session.execute(
                delete(ArtifactShareRow)
                .where(
                    ArtifactShareRow.artifact_id == artifact_id,
                    ArtifactShareRow.shared_by == shared_by,
                    ArtifactShareRow.shared_with == shared_with,
                )
                .returning(ArtifactShareRow.id)
            )
            return gone.first() is not None

    async def sent_by(self, principal_id: str) -> tuple[Share, ...]:
        """What this person has handed to colleagues, newest first."""
        return await self._read(principal_id, ArtifactShareRow.shared_by == principal_id)

    async def received_by(self, principal_id: str) -> tuple[Share, ...]:
        """What colleagues have handed this person, newest first."""
        return await self._read(principal_id, ArtifactShareRow.shared_with == principal_id)

    async def _read(self, principal_id: str, where: ColumnElement[bool]) -> tuple[Share, ...]:
        async with self._sessions() as session, session.begin():
            await session.execute(_as(principal_id))
            rows = (
                (
                    await session.execute(
                        select(ArtifactShareRow)
                        .where(where)
                        .order_by(ArtifactShareRow.shared_at.desc(), ArtifactShareRow.id)
                    )
                )
                .scalars()
                .all()
            )
        return tuple(_share(one) for one in rows)
