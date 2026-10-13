"""Counting which documents an agent's answers cite, and reading the counts back (M39.2.3.5).

`brain.console.agent_tabs.item_usage` decided what an agent's Knowledge section would say about use:
the documents it reached for most and the ones in its slice it never touched, as a report and never
as a ranking input. Nothing kept a count, because `ops.retrieval_event` keeps no document by design.
This keeps one, in `ops.agent_item_use`: an agent, a document, a day and how many answers cited it.

**What is kept is the least that answers the question.** No question, no person, no passage and no
reach, so the counts are the agent's use of a document and not anybody's, and the basis the
Knowledge section states is everybody who asked that agent. A person who asked nothing is in no row
and a row names nobody. See `A_COUNT_IS_THE_AGENTS_USE_OF_A_DOCUMENT_AND_NOBODYS_QUESTION`.

**A document is counted once per answer, from what the person was shown.** The ids come from the
composed answer's post-redaction records, the same records the citation frames are made from, so a
document an answer drew on and withheld words from is not counted as cited, and a retrieval that
was ranked and not shown is not counted at all. Two passages of one document in one answer are one
use.

**Nothing here may fail an answer, and nothing here may feed ranking.** The count is written after
the answer is decided, an exception is logged and swallowed by the caller, and the only reader is
the Knowledge section, which asks for the documents its reader may already open. A count of a
document the reader may not see contributes to no figure they are shown. See
`brain.console.agent_tabs.A_PER_ITEM_COUNT_IS_A_REPORT_AND_NEVER_A_RANKING_INPUT`.

**Behind a switch that ships off** (`brain.ops.features.AGENT_ITEM_COUNTS`), because it is a new
record kept on every answer. Off, nothing is written and the section shows no figure, never a
nought: a nought would read as a document the agent never touched.

Task ids: M39.2.3.5
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from typing import Any, Final

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

#: Why the table names no question and no person.
A_COUNT_IS_THE_AGENTS_USE_OF_A_DOCUMENT_AND_NOBODYS_QUESTION: Final = (
    "A count of how often an agent cited a document is about the agent and the document. Adding "
    "who asked or what was asked would make the table a log of what each person read, which the "
    "retrieval log refuses to be and which a per-document report does not need. So a row is an "
    "agent, a document, a day and a number, and the report says whose activity it counts: "
    "everybody who asked that agent."
)

#: How many days the Knowledge section's figures cover, today included.
WINDOW_DAYS: Final = 30

#: The most documents one answer adds to, a resource bound: an answer cites a handful of passages.
MAX_DOCUMENTS_PER_ANSWER: Final = 50

#: The most documents one read is asked about, a resource bound over one page of a list.
MAX_DOCUMENTS_PER_READ: Final = 200

#: One statement adds one to every document of an answer, atomically, so two answers at once both
#: count. A document first cited today is inserted at one; every other is raised by one.
_COUNT: Final = text(
    "INSERT INTO ops.agent_item_use (agent_id, item_id, day, uses)"
    " SELECT :agent_id, d, :day, 1 FROM unnest(CAST(:items AS text[])) AS d"
    " ON CONFLICT (agent_id, item_id, day)"
    " DO UPDATE SET uses = ops.agent_item_use.uses + 1"
)

#: The sum of each asked document's days inside the window. A document with no row is absent from
#: the answer, which the caller reads as none.
_USES: Final = text(
    "SELECT item_id, sum(uses) AS uses FROM ops.agent_item_use"
    " WHERE agent_id = :agent_id AND day >= :since AND item_id = ANY(CAST(:items AS text[]))"
    " GROUP BY item_id"
)


async def counting_is_on(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether `agent_item_counts` is switched on now. Off when nobody has said otherwise."""
    from brain.ops.features import AGENT_ITEM_COUNTS, is_on

    async with sessions() as session:
        return await is_on(session, AGENT_ITEM_COUNTS)


def cited_item_ids(records: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """The documents an answer's records came from, each once, sorted, and bounded.

    `document_id` is the item id every passage of a document carries. A record with none, or with
    one that is not a plain string, names no document and is not counted.
    """
    found = {
        one
        for record in records
        for one in [record.get("document_id")]
        if isinstance(one, str) and one.strip()
    }
    return tuple(sorted(found))[:MAX_DOCUMENTS_PER_ANSWER]


def window_start(today: date) -> date:
    """The first day a figure counts, so `WINDOW_DAYS` days including today."""
    return today - timedelta(days=WINDOW_DAYS - 1)


class StoredItemUses:
    """The counts over this install's database."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def count(self, agent_id: str, item_ids: Sequence[str], day: date) -> None:
        """Add one use of each document to this agent's count for the day."""
        if not item_ids:
            return
        async with self._sessions() as session, session.begin():
            await session.execute(
                _COUNT,
                {
                    "agent_id": agent_id,
                    "day": day,
                    "items": list(item_ids[:MAX_DOCUMENTS_PER_ANSWER]),
                },
            )

    async def uses(self, agent_id: str, item_ids: Sequence[str], *, today: date) -> dict[str, int]:
        """How many answers cited each of these documents in the window, by document.

        A document with no use is absent from the answer and not a nought, so the caller says
        which it means. Asked only about documents the caller already may see.
        """
        if not item_ids:
            return {}
        async with self._sessions() as session:
            rows = await session.execute(
                _USES,
                {
                    "agent_id": agent_id,
                    "since": window_start(today),
                    "items": list(item_ids[:MAX_DOCUMENTS_PER_READ]),
                },
            )
            return {str(row["item_id"]): int(row["uses"]) for row in rows.mappings()}
