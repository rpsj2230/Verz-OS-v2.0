"""What the registry tells the answer lane about records it read: which client each is, and
whether a reviewer has a pair of them open (M14.6.5).

`brain.gate.fast_lane.respond` holds records it read at the asker's reach that answer to one
name, and asks this, through `fast_lane.AmbiguityReader`, whether they are more than one client.
The gate opens no connection, so the question is asked through a protocol and answered here.

**The registry decides what a client is, not the name.** A record is the client its `er.link`
names, followed through the forwarding pointer to the entity in force, the walk `er.resolved_alias`
makes. Two records merged into one entity are one client and are not ambiguous. A record the
registry has not linked is left out of the answer, and the lane then falls through: the registry
has said nothing about it, and calling it a client of its own would name a price list's two rows
of one service as two clients. Rejected for that reason.

**It reads nothing about anybody the asker could not already read.** It is handed only records
the lane already read at the asker's reach, and what it returns is entity ids and a review
reference, which the answer route renders as one sentence and shows the reference only to a
reviewer. See `fast_lane.NAMING_AMBIGUITY_ONLY_AMONG_RECORDS_THE_ASKER_READS`.

**Nothing here imports the calibration.** The answer lane is the request path, and
`tests/invariants/test_no_ml_on_the_request_path.py` keeps a fitted model off it; this module
reads three tables and imports none of `brain.resolution.matching_store`, which does.

Task ids: M14.6.5
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

#: Each record's current entity: its link, followed through the pointer to the one in force.
CURRENT_OF_RECORDS: Final = """
WITH RECURSIVE walk(source, entity, source_id, entity_id, merged_into, depth) AS (
        SELECT l.source, l.entity, l.source_id, c.entity_id, c.merged_into, 0
        FROM er.link l JOIN er.canonical c ON c.entity_id = l.entity_id
        WHERE (l.source, l.entity, l.source_id) IN (
            SELECT * FROM unnest(CAST(:sources AS text[]), CAST(:entities AS text[]),
                                 CAST(:ids AS text[]))
        )
    UNION ALL
        SELECT w.source, w.entity, w.source_id, c.entity_id, c.merged_into, w.depth + 1
        FROM walk w JOIN er.canonical c ON c.entity_id = w.merged_into
        WHERE w.depth < 16
)
SELECT source, entity, source_id, entity_id FROM walk WHERE merged_into IS NULL
"""

#: An open review item whose two entities are both among these.
OPEN_REVIEW_BETWEEN: Final = """
SELECT item_id FROM er.review_item
WHERE state = 'open' AND left_entity_id = ANY(:ids) AND right_entity_id = ANY(:ids)
ORDER BY raised_at, item_id
LIMIT 1
"""


class StoredAmbiguity:
    """`fast_lane.AmbiguityReader` over this install's registry, as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def current_entities(
        self, records: Sequence[tuple[str, str, str]]
    ) -> Mapping[tuple[str, str, str], str]:
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    text(CURRENT_OF_RECORDS),
                    {
                        "sources": [one[0] for one in records],
                        "entities": [one[1] for one in records],
                        "ids": [one[2] for one in records],
                    },
                )
            ).all()
        return {(str(a), str(b), str(c)): str(entity_id) for a, b, c, entity_id in rows}

    async def open_review(self, entity_ids: Sequence[str]) -> str | None:
        async with self._sessions() as session:
            found = (
                await session.execute(text(OPEN_REVIEW_BETWEEN), {"ids": list(entity_ids)})
            ).first()
        return None if found is None else str(found[0])
