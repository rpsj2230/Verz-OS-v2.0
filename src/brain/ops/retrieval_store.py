"""`ops.retrieval_event`, written and read as the application role (M15.3.4).

`brain.knowledge.retrieval_log` turns a question's search into a `RetrievalEvent`; this keeps it,
adds a position when a person follows a citation, and reads the recent ones back into
`brain.knowledge.quality.signal`. Nothing here decides what a record may hold: the record's type
refuses a field it has no room for, and the table has no column for one.

**A use only ever adds a position, inside what the person was shown, once.** One statement reads
the positions already there, adds the new one, sorts and deduplicates, and applies only where the
position is inside `returned`; a position outside it, or an id that names no retrieval, changes
nothing and the caller is told nothing was recorded, the same for both. See
`A_USE_IS_A_PLACE_IN_THE_READERS_OWN_LIST`.

**The signal is read over the most recent retrievals, not over all of them.** A ranking changes
when weights, the corpus or the embedding model change, and a mean over a year of retrievals
answers a question about a system that no longer exists. `SIGNAL_WINDOW` is the window, and
`quality.signal` still answers None below its own floor.

Task ids: M15.3.4
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.knowledge.quality import (
    RETRIEVER_SEPARATOR,
    RetrievalEvent,
    RetrievalSignal,
    signal,
)
from brain.tables.retrieval import RetrievalEventRow

#: Why a use is a position and nothing else.
A_USE_IS_A_PLACE_IN_THE_READERS_OWN_LIST: Final = (
    "A person following a citation is the one act the learning signal counts, and what is kept "
    "of it is the place in their own list: the second passage of some retrieval, which names no "
    "document and nobody. A place outside what they were shown, and an id naming no retrieval, "
    "record nothing and are told so alike, so the route answers nothing about which ids exist."
)

#: How many of the most recent retrievals the signal is read over.
SIGNAL_WINDOW: Final = 1_000

#: Adds one position to a retrieval's uses, sorted and once, inside what was shown.
_USED: Final = text(
    "UPDATE ops.retrieval_event"
    " SET used = ARRAY("
    "SELECT DISTINCT p FROM unnest(array_append(used, CAST(:position AS integer))) AS p ORDER BY p"
    ")"
    " WHERE event_id = :event_id AND CAST(:position AS integer) BETWEEN 1 AND returned"
    " RETURNING event_id"
)


def event_from(row: RetrievalEventRow) -> RetrievalEvent:
    """The record a row holds. Refuses a row the type would refuse, which the table cannot hold."""
    return RetrievalEvent(
        retrievers=tuple(row.retrievers.split(RETRIEVER_SEPARATOR)),
        returned=row.returned,
        corroborated=row.corroborated,
        used=tuple(row.used),
        latency_ms=row.latency_ms,
    )


class StoredRetrievals:
    """The retrieval log over this install's database."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(self, event: RetrievalEvent) -> str:
        """Keep one retrieval with no uses; its id, for the page to send a use back against."""
        event_id = uuid.uuid4()
        async with self._sessions() as session, session.begin():
            session.add(
                RetrievalEventRow(
                    event_id=event_id,
                    retrievers=RETRIEVER_SEPARATOR.join(event.retrievers),
                    returned=event.returned,
                    corroborated=event.corroborated,
                    used=[],
                    latency_ms=event.latency_ms,
                )
            )
        return str(event_id)

    async def use(self, event_id: str, position: int) -> bool:
        """Add `position` to a retrieval's uses. False, changing nothing, for an id naming no
        retrieval or a position outside what it showed.

        See `A_USE_IS_A_PLACE_IN_THE_READERS_OWN_LIST`.
        """
        try:
            wanted = uuid.UUID(event_id)
        except ValueError:
            return False
        async with self._sessions() as session, session.begin():
            found = await session.execute(_USED, {"event_id": wanted, "position": position})
            return found.first() is not None

    async def recent(self, limit: int = SIGNAL_WINDOW) -> tuple[RetrievalEvent, ...]:
        """The most recent retrievals, newest first.

        Each row becomes its record inside the transaction, so this answers the same under a
        session factory that expires what it loaded on commit as under one that does not.
        """
        async with self._sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        select(RetrievalEventRow)
                        .order_by(RetrievalEventRow.at.desc(), RetrievalEventRow.event_id)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return tuple(event_from(row) for row in rows)

    async def signal(self) -> RetrievalSignal | None:
        """The learning signal over `SIGNAL_WINDOW`, or None below `quality`'s floor."""
        return signal(await self.recent())
