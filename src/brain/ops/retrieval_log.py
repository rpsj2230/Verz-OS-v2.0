"""The retrieval log: which passages a question's search returned, kept at its trace (M15.3.4).

`brain.knowledge.quality.RetrievalEvent` decided in September what the learning signal reads of a
retrieval, and nothing on an install ever made one: the tracker's audit of 2026-09-17 reopened
M15.3.4 because no retrieval was written anywhere. This module is the writer and the two readers,
over `mem.retrieval` (`0197`).

**What is kept is the ids of the passages the model was shown, in ranked order, at the trace,
and the positions among them the answer cited.** Not the passages the search returned before
redaction: `brain.gate.model_lane.redact_passages` can drop a passage the search found and the
caller's field grants do not reach, and an id kept for one of those is a record of something the
caller was not shown, which `brain.knowledge.quality.A_COUNT_OF_WHAT_WAS_SHOWN_IS_NOT_A_COUNT_OF_
WHAT_WAS_HIDDEN` forbids from the other side. So `LoggedSearch` runs the one redactor over what the
search returned and keeps the ids of what survived it, cut as `brain.gate.model_lane.shown` cuts,
which is exactly the list `draft` shows the model. See
`A_RETRIEVAL_KEEPS_ONLY_WHAT_THE_MODEL_WAS_SHOWN`.

**`brain.knowledge.quality` rejected a log carrying references, and this one carries them, so
the two have to be reconciled rather than left to disagree.** That module's rejection is of
`(principal, chunk_id, used)` read across callers to learn a per-document boost: one person's
reach leaking into another's ordering, and a second memory store with none of M16's controls. Both
halves are closed here by who may read what. **A person reads their own retrievals' ids and nobody
else's**, by the policy `0197` puts on the table, and those ids are of passages they were shown.
**The install reads a retrieval only as a `RetrievalEvent`**, through `mem.retrieval_events`, which
returns how many passages, which positions were cited and how long, and no id, no trace and no
person, so `brain.knowledge.quality.signal` is computed over exactly the record that module
designed. And nothing that ranks reads this table: the test of that walks the imports of every
package that decides an answer. See
`THE_INSTALL_READS_A_RETRIEVAL_AS_A_RANKING_AND_ITS_ASKER_AS_IDS`.

**Collected while the question is answered, written once after it.** `LoggedSearch` wraps the
lane's search for one request and holds what it saw in a `Retrieved`; `kept_retrieval` writes it
once the answer exists, because the cited positions are only known then. A write that fails is
logged and the answer goes out, for `brain.ops.signal_store.
A_SIGNAL_NEVER_COSTS_THE_PERSON_THEIR_TRANSCRIPT`'s reason. A search that found nothing is kept
too, with no ids: a question nothing answered is the evidence FEAT-5.14's knowledge gaps are
read from.

Task ids: M15.3.4, M16.2.8
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.ledger import TRACE_ID
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.core.redaction import ID_KEYS
from brain.gate.answer import Answered
from brain.gate.model_lane import ModelLane, PassageSearch, redact_passages, shown
from brain.gate.provenance import DOCUMENT_KIND
from brain.knowledge.document_tools import KnowledgePassage
from brain.knowledge.quality import RetrievalEvent
from brain.knowledge.search import CHUNK_ID_CHARS
from brain.tables.signal_log import RetrievalRow

log = structlog.get_logger(__name__)

#: Why the ids kept are the passages the model was shown and not what the search found.
A_RETRIEVAL_KEEPS_ONLY_WHAT_THE_MODEL_WAS_SHOWN: Final = (
    "The search reads at the caller's reach and the redactor can still drop a passage their "
    "field grants do not reach, so an id kept from the search's own list could be a record of "
    "something the caller was not shown. The ids kept are the redactor's survivors, cut as the "
    "prompt cuts them, in ranked order: exactly the passages the model was shown."
)

#: Why the asker reads ids and the install reads a ranking measurement.
THE_INSTALL_READS_A_RETRIEVAL_AS_A_RANKING_AND_ITS_ASKER_AS_IDS: Final = (
    "A retrieval's passage ids are readable by the person it ran for and nobody else, by the "
    "table's policy, and they are ids of passages that person was shown. Everybody's "
    "retrievals are read only as RetrievalEvents, through a function returning a count, the "
    "cited positions and a duration, with no id, no trace and no person, so the learning signal "
    "measures the ranking and never learns which documents one person's reach holds."
)

#: The one retriever that runs today: the library's hybrid search, named as quality names one.
RETRIEVER: Final = "search_documents"

#: The most retrievals one read of the install returns. A resource bound, not a sample.
MOST_EVENTS: Final = 10_000

_TRACE: Final = re.compile(TRACE_ID)

_SET_PRINCIPAL: Final = text("SELECT set_config('app.principal_id', :principal, true)")

#: `0197`'s function, written out so no statement here is assembled at run time.
_EVENTS: Final = text(
    "SELECT returned, used, latency_ms FROM mem.retrieval_events(:after, :until, :most)"
)


@dataclass
class Retrieved:
    """What one request's search returned, as the model was shown it. Mutable, one per request.

    `chunk_ids` is None until a search has run, so a question the fast lane answered, which
    searched nothing, keeps no retrieval at all; an empty tuple is a search that found nothing.
    """

    chunk_ids: tuple[str, ...] | None = None
    latency_ms: int = 0


def _id_of(record: Mapping[str, Any]) -> str:
    return str(next((record[key] for key in ID_KEYS if key in record), ""))


def shown_ids(
    found: TypedResult[KnowledgePassage], *, entitlement: EntitlementSet, now: datetime | None
) -> tuple[str, ...]:
    """The ids of the passages the model is shown from `found`, in ranked order.

    `redact_passages` and `shown`, the two functions `brain.gate.model_lane.draft` calls, so
    this is the prompt's list by construction rather than by a copy of its rules. See
    `A_RETRIEVAL_KEEPS_ONLY_WHAT_THE_MODEL_WAS_SHOWN`.
    """
    payload = shown(redact_passages(found, entitlement=entitlement, now=now).payload)
    return tuple(_id_of(record) for record in payload.records)


@dataclass(frozen=True)
class LoggedSearch:
    """`PassageSearch` that answers as `inner` does and notes what it returned in `kept`."""

    inner: PassageSearch
    kept: Retrieved

    async def passages(
        self, question: str, *, entitlement: EntitlementSet, now: datetime
    ) -> TypedResult[KnowledgePassage]:
        started = time.perf_counter()
        found = await self.inner.passages(question, entitlement=entitlement, now=now)
        if self.kept.chunk_ids is None:
            # The first search of a request is its retrieval; a lane that searched again would
            # be a second retrieval at the same trace, which the table keeps one of.
            self.kept.latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            self.kept.chunk_ids = shown_ids(found, entitlement=entitlement, now=now)
        return found


def logging_retrievals(lane: ModelLane | None, kept: Retrieved) -> ModelLane | None:
    """The model step with its search noting what it returned in `kept`, or None for none."""
    if lane is None:
        return None
    return replace(lane, search=LoggedSearch(inner=lane.search, kept=kept))


def cited_positions(chunk_ids: Sequence[str], answered: Answered) -> tuple[int, ...]:
    """The one-based positions in `chunk_ids` of the passages the answer cited, sorted.

    Read from the answer's own document evidence, by the chunk each citation's anchor names,
    which is how `brain.chat.remember` records what an answer drew on. A passage cited that is
    not among the ids is not a position: it was recalled for a follow-up rather than found.
    """
    from brain.chat.remember import chunk_of

    if answered.provenance is None:
        return ()
    cited = {
        chunk_of(view)
        for view in (one.view() for one in answered.provenance.documents)
        if view.get("kind", "") == DOCUMENT_KIND
    }
    return tuple(place for place, one in enumerate(chunk_ids, start=1) if one in cited)


async def kept_retrieval(
    sessions: async_sessionmaker[AsyncSession],
    *,
    trace_id: str,
    principal_id: str,
    retrieved: Retrieved,
    answered: Answered,
    now: datetime,
) -> bool:
    """Write one request's retrieval at its trace, in the asker's name; whether one was written.

    Nothing when no search ran, when the trace does not fit the ledger's grammar (there would be
    nothing to keep it at), or when an id is longer than a passage id can be, which only a source
    outside the library could hand back. A failure is logged and swallowed by the caller.
    """
    chunk_ids = retrieved.chunk_ids
    if chunk_ids is None or not _TRACE.fullmatch(trace_id):
        return False
    if any(len(one) > CHUNK_ID_CHARS or not one for one in chunk_ids):
        log.warning("retrieval.not_kept", reason="an id no passage carries")
        return False
    async with sessions() as session, session.begin():
        await session.execute(_SET_PRINCIPAL, {"principal": principal_id})
        await session.execute(
            pg_insert(RetrievalRow)
            .values(
                trace_id=trace_id,
                principal_id=principal_id,
                chunk_ids=list(chunk_ids),
                used=list(cited_positions(chunk_ids, answered)),
                latency_ms=retrieved.latency_ms,
                at=now,
            )
            .on_conflict_do_nothing(index_elements=[RetrievalRow.trace_id])
        )
    return True


@dataclass(frozen=True)
class KeptRetrieval:
    """One retrieval as its asker reads it back: the passages shown, and the places cited."""

    chunk_ids: tuple[str, ...]
    used: tuple[int, ...]


class StoredRetrievals:
    """`mem.retrieval`, read as one person's own ids or as the install's ranking measurements."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def at_trace(self, principal_id: str, trace_id: str) -> KeptRetrieval | None:
        """This person's retrieval at this trace, or None for none.

        None alike for a trace that kept no retrieval and one that is somebody else's: the
        policy shows a person their own rows only, so the two read the same.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(_SET_PRINCIPAL, {"principal": principal_id})
            found = (
                await session.execute(
                    select(RetrievalRow.chunk_ids, RetrievalRow.used).where(
                        RetrievalRow.trace_id == trace_id
                    )
                )
            ).first()
        if found is None:
            return None
        chunk_ids, used = found
        return KeptRetrieval(
            chunk_ids=tuple(str(one) for one in chunk_ids), used=tuple(int(one) for one in used)
        )

    async def events(
        self, *, since: datetime, until: datetime, most: int = MOST_EVENTS
    ) -> tuple[RetrievalEvent, ...]:
        """Every retrieval in `(since, until]`, as `brain.knowledge.quality` records one.

        Through `mem.retrieval_events`, so the one read of everybody's retrievals holds no
        passage, trace or person; `brain.knowledge.quality.signal` is the arithmetic over it.
        """
        async with self._sessions() as session, session.begin():
            rows = (
                await session.execute(_EVENTS, {"after": since, "until": until, "most": most})
            ).all()
        return tuple(
            RetrievalEvent(
                retrievers=(RETRIEVER,),
                returned=int(returned),
                used=tuple(int(one) for one in used),
                latency_ms=int(latency),
            )
            for returned, used, latency in rows
        )
