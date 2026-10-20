"""Where a person's ask to be deleted is kept and read: `ops.deletion_request` (`0273`).

**Written as the person, decided as the retention owner.** `ask` inserts as the person the
transaction names, because `0273`'s insert policy holds a row to the session's principal. `waiting`
reads the rows nobody has acted on, and `decide` sets the three decision columns once, as the
retention owner filing the erasure, in the same session as nothing else: the erasure itself is
filed through `brain.ops.erasure_store.StoredErasures`, whose transaction this one deliberately does
not share. If filing succeeds and this fails, the erasure is queued and the ask still reads as
waiting, which is a duplicate prompt for an administrator and not a lost erasure; the reverse order
would close an ask nobody had filed.

**One waiting ask for a person.** A second `ask` while one waits inserts nothing and answers the
first row, so pressing the button twice is one ask and the page shows when it was first made.

Task ids: M40.4.2.3
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.knowledge.search import PRINCIPAL_SETTING
from brain.tables.member_deletion import DeletionRequestRow


@dataclass(frozen=True)
class Asked:
    """One person's ask as it is stored. Waiting while `filed_as` is empty."""

    request_id: str
    subject_id: str
    requested_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None
    filed_as: str | None = None

    @property
    def waiting(self) -> bool:
        return self.decided_at is None


def _as(principal_id: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(
        name=PRINCIPAL_SETTING, value=principal_id
    )


def _asked(row: DeletionRequestRow) -> Asked:
    return Asked(
        request_id=str(row.id),
        subject_id=row.subject_id,
        requested_at=row.requested_at,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
        filed_as=row.erasure_request_id,
    )


@runtime_checkable
class DeletionRequests(Protocol):
    """What the routes need of the asks. `StoredDeletionRequests` is one; a test stands one in."""

    async def ask(self, subject_id: str, *, at: datetime) -> tuple[Asked, bool]: ...

    async def latest(self, subject_id: str) -> Asked | None: ...

    async def waiting(self, *, limit: int) -> tuple[Asked, ...]: ...

    async def decide(
        self, subject_id: str, *, by: str, erasure_request_id: str, at: datetime
    ) -> bool: ...


class StoredDeletionRequests:
    """`ops.deletion_request` read and written."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def ask(self, subject_id: str, *, at: datetime) -> tuple[Asked, bool]:
        """Keep one ask as its person. The ask and whether this call made it.

        Where one is already waiting the answer is that one and the flag is False.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(_as(subject_id))
            made = await session.execute(
                pg_insert(DeletionRequestRow)
                .values(subject_id=subject_id, requested_at=at)
                .on_conflict_do_nothing(
                    index_elements=["subject_id"], index_where=text("decided_at IS NULL")
                )
                .returning(DeletionRequestRow)
            )
            row = made.scalars().first()
            if row is not None:
                return _asked(row), True
            waiting = (
                await session.execute(
                    select(DeletionRequestRow).where(
                        DeletionRequestRow.subject_id == subject_id,
                        DeletionRequestRow.decided_at.is_(None),
                    )
                )
            ).scalar_one()
            return _asked(waiting), False

    async def latest(self, subject_id: str) -> Asked | None:
        """This person's newest ask, waiting or decided, or None."""
        async with self._sessions() as session, session.begin():
            row = (
                await session.execute(
                    select(DeletionRequestRow)
                    .where(DeletionRequestRow.subject_id == subject_id)
                    .order_by(DeletionRequestRow.requested_at.desc(), DeletionRequestRow.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            return None if row is None else _asked(row)

    async def waiting(self, *, limit: int) -> tuple[Asked, ...]:
        """The asks nobody has acted on, oldest first, at most `limit`."""
        async with self._sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        select(DeletionRequestRow)
                        .where(DeletionRequestRow.decided_at.is_(None))
                        .order_by(DeletionRequestRow.requested_at, DeletionRequestRow.id)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return tuple(_asked(one) for one in rows)

    async def decide(
        self, subject_id: str, *, by: str, erasure_request_id: str, at: datetime
    ) -> bool:
        """Mark this person's waiting ask as filed, as the retention owner who filed it.

        False where there was no waiting ask, which is the ordinary case of an erasure an
        administrator filed on their own account.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(_as(by))
            marked = await session.execute(
                update(DeletionRequestRow)
                .where(
                    DeletionRequestRow.subject_id == subject_id,
                    DeletionRequestRow.decided_at.is_(None),
                )
                .values(decided_by=by, decided_at=at, erasure_request_id=erasure_request_id)
                .returning(DeletionRequestRow.id)
            )
            return marked.first() is not None
