"""An index hit, read again from its source while the asker waits, before anything is said.

A connector keeps a minimal index of a source
(`brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`) and the fast lane finds a record through
it: the row plane reads `proj.record` at the asker's reach and hands back a row carrying the ids,
the name, the status and the dates the index holds. That row finds the record; it is not the answer.
**Every value an answer uses from a connected source is read from the source at that moment
(M11.9.2)**, so this module takes the rows the index found, reads each of those records live through
`brain.connectors.live_read.read_live`, and hands the lane the live record in place of the index
row, to be redacted at the same reach as everything else.

**The live values are laid over the index row, and the index row's fields stay where the source has
none.** A source's visibility is carried on its index rows as the fields its predicate tests
(`brain.ops.connector_sync.THE_SOURCE_S_VISIBILITY_IS_STORED_AS_THE_FIELDS_ITS_PREDICATE_TESTS`),
and a vendor's reply does not repeat them. Dropping them would leave the redactor a record no scope
can match, which it withholds from everybody; keeping the index's copy of a field the source did
return would answer with a value the source has since changed. So the source wins wherever it
answered, and the index fills only what the source never sends.

**A record the source no longer returns is not answered from the index.** It is left out, so the
lane says what it says about any record that is not there; answering from the index row would be a
copy of a value served as though it were read, which is the bulk sync the owner's rule forbids,
arriving through the back door of a fallback.

**A read that did not answer is carried out as the reason, never papered over (M11.5.5).**
`Refreshed.result` is None when any record could not be read, and the lane then says what
`federation.PartialAnswer.notice` says, naming the source only to an asker whose catalogue already
disclosed it. Answering from the rows that did come back would leave the asker unable to tell a
record that is absent from one that was not read.

**It lives outside the gate, which knows it only as `brain.gate.live_records.LiveRecords`.** The
gate imports no connector (`tests/unit/test_repo_shape.py`): it decides what a caller may see and
never fetches, so the seam is a protocol the gate owns and this module, which reads through the
connectors' executor, is the one implementation `brain.api_routes` hands the lane.

Scope: nothing here opens a connection. What is connected, the throttle, the flights and the clock
are handed in by whoever built the lane.

Task ids: M11.9.2, M11.5.1, M11.5.5
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from brain.connectors.contract import FetchRequest
from brain.connectors.live_read import (
    LIVE_READ_BUDGET_MS,
    RECORD_ID_FILTER,
    LiveCall,
    LiveFlights,
    LiveSources,
    LiveThrottle,
    read_live,
)
from brain.core.envelope import TypedResult
from brain.gate.live_records import Refreshed
from brain.knowledge.rows import ENTITY_KEY, ID_KEY, RowRecord

#: Why an index row is never the answer's value on its own.
THE_INDEX_FINDS_A_RECORD_AND_THE_SOURCE_ANSWERS_FOR_IT: Final = (
    "The minimal index holds what finding a record takes: its id, its name, its status and its "
    "dates, as they were when the source was last read. An answer from those would be a copy "
    "served as though it were read, and the owner's rule is that every value an answer uses is "
    "read from the source when the question is asked, at the asker's reach. So a pair the source "
    "is read live for is answered from the live record, and a record the source no longer "
    "returns is not answered at all."
)


@dataclass(frozen=True)
class SourceRecords:
    """`brain.gate.live_records.LiveRecords` over the connected sources and their executor.

    `connected` is asked once per refresh, so a source connected or disconnected on the
    Connectors screen is read or not from the next question, with nothing restarted.
    """

    connected: Callable[[], Awaitable[LiveSources]]
    throttle: LiveThrottle = field(default_factory=LiveThrottle)
    flights: LiveFlights = field(default_factory=LiveFlights)
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    budget_ms: int = LIVE_READ_BUDGET_MS

    async def refresh(
        self,
        result: TypedResult[RowRecord],
        *,
        source: str,
        entity: str,
        asker: str,
        trace_id: str = "",
    ) -> Refreshed | None:
        """Read each of these index rows from the source, or None when this pair is not read live.

        None leaves the lane answering from the rows it has, which is right for the product's
        own records (the price list, an uploaded table) and for a source with no live lookup.
        A result with no rows is None too: there is nothing to read, and a read of nothing
        would spend a source call to say what the index already said.
        """
        if not result.records:
            return None
        sources = await self.connected()
        mode = sources.reads(source, entity)
        if mode is None:
            return None
        calls = tuple(
            LiveCall(
                call_id=f"record-{index}",
                connector=source,
                request=FetchRequest(
                    entity=entity, filters=((RECORD_ID_FILTER, record.id),), limit=1
                ),
                identity_mode=mode,
            )
            for index, record in enumerate(result.records)
        )
        read = await read_live(
            calls,
            sources=sources,
            asker=asker,
            throttle=self.throttle,
            flights=self.flights,
            clock=self.clock,
            budget_ms=self.budget_ms,
            trace_id=trace_id,
        )
        if any(call.call_id not in read.rows for call in calls):
            return Refreshed(result=None, partial=read.partial, calls=len(calls))
        merged: list[RowRecord] = []
        fetched_at = result.fetched_at
        for call, indexed in zip(calls, result.records, strict=True):
            live = read.rows[call.call_id]
            fetched_at = live.fetched_at or fetched_at
            match = next((one for one in live.records if one.id == indexed.id), None)
            if match is None:
                # Gone at the source. See THE_INDEX_FINDS_A_RECORD_AND_THE_SOURCE_ANSWERS_FOR_IT.
                continue
            fields = match.model_dump(exclude={ENTITY_KEY, ID_KEY})
            merged.append(RowRecord.model_validate({**indexed.model_dump(), **fields}))
        return Refreshed(
            result=TypedResult[RowRecord](
                records=tuple(merged),
                source=result.source or source,
                fetched_at=fetched_at,
                truncated=result.truncated,
            ),
            partial=read.partial,
            calls=len(calls),
        )
