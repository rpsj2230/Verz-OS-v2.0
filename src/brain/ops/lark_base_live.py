"""A switched-on Lark Base while somebody waits: its schema for the question, a record read live.

`brain.ops.lark_base_index` keeps the Base's minimal index on the worker's schedule. This is the
question's half, and it is two things the answer route needs and the index cannot give it.

**The Base's schema, read for questions and kept for a few minutes.** A question about a Base
table is asked in the table's own words (its primary field names a record, every other field is
something to ask about), and which tables and fields there are is the Base's own statement of
itself, read from Lark's table and field listings (`lark_base.A_BASE_IS_READ_BY_ITS_OWN_SCHEMA`).
Read on the question that first needs it and kept for `SCHEMA_KEPT_FOR`, so a busy install reads
the schema a few times an hour rather than on every question, and a column added this morning is
asked about within minutes. A schema that could not be read leaves the one read before it in
place, and with none there are no Base questions: an install whose Lark is unreachable answers as
one with no Base, for everybody alike. See `A_SCHEMA_IS_READ_FOR_QUESTIONS_AND_KEPT_BRIEFLY`.
Rejected: storing the schema in the database from the worker, which is a second copy of the
Base's own statement that goes stale on the day somebody renames a column.

**One record, read from Lark by its id, under a key borrowed for that read.** `LarkBaseSources`
is `brain.connectors.live_read.LiveSources` for the Base alone: a service read (the app's own
token, `IdentityMode.SERVICE`), made the way `brain.ops.live_read_run.ConnectedSources` makes one
for a connected source, and `Together` puts it beside those, so the live read's executor,
throttle and breaker treat a Base like any other source. Every value a Base answer gives is read
here, at the asker's reach, and never kept: `lark_base_index.A_BASE_IS_INDEXED_AND_NEVER_COPIED`.

Task ids: M11.6.3, M11.9.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

import structlog

from brain.connectors import lark_base
from brain.connectors.contract import ConnectorContractError, FetchRequest
from brain.connectors.lark_base import (
    LARK_BASE,
    Endpoint,
    LarkBaseBudgetError,
    LarkBaseRefusedError,
    LarkBaseUnreachableError,
    PageCursor,
    decode_row,
)
from brain.connectors.live_read import RECORD_ID_FILTER, LiveReply, LiveSource, LiveSources
from brain.connectors.throttle import CallOutcome
from brain.connectors.transports import SourceRecord, TransportError
from brain.core.envelope import IdentityMode, TypedResult
from brain.ops.lark_base_index import (
    KnownTable,
    LarkBaseUse,
    LarkCaller,
    TokenIssuer,
    discovered,
    opened,
    tables_named,
)
from brain.tools.fetch import Resolver

if TYPE_CHECKING:
    from brain.ops.connector_sync_run import ConnectorKeys

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the Base's schema is read for questions and kept only briefly.
A_SCHEMA_IS_READ_FOR_QUESTIONS_AND_KEPT_BRIEFLY: Final = (
    "Which tables a Base holds and what their fields are is the Base's own statement of itself, "
    "so it is read from Lark when a question first needs it and kept in this process for a few "
    "minutes. A schema stored from the worker would be a second copy that goes stale when a "
    "column is renamed; one read on every question would spend the tenant's minute on listings. "
    "A schema that could not be read leaves the last one in place, and with none the install "
    "answers as one with no Base, for every asker alike."
)

#: Why a Base's record is read as the app and never as the asker.
A_BASE_IS_READ_AS_THE_APP: Final = (
    "The Lark app reads a Base with its own tenant token; nobody's own Lark credential is held "
    "here. So a Base read is a service read, and who may be told what it returns is decided by "
    "this install's grants and the Base's field rules before the answer is written, exactly as "
    "for a connected source read with its key."
)

__all__ = [
    "A_BASE_IS_READ_AS_THE_APP",
    "A_FAILED_SCHEMA_IS_NOT_READ_ON_EVERY_QUESTION",
    "A_SCHEMA_IS_READ_FOR_QUESTIONS_AND_KEPT_BRIEFLY",
]

# The sentences a read this process would not make leaves in the operator's log.
NOT_ONE_RECORD: Final = "the read did not name exactly one Base record by its id"
NOT_A_KNOWN_TABLE: Final = "the read named a table the Base's schema does not hold"

#: How long a schema read for a question answers the questions after it.
SCHEMA_KEPT_FOR: Final = timedelta(minutes=10)

#: How long after a failed reading the schema is not read again. A minute: long enough that a
#: Lark that is down costs one question in a minute a wait, short enough that a Base shared with
#: the app a moment ago is asked about within one.
SCHEMA_RETRIED_AFTER: Final = timedelta(minutes=1)

#: Why a failed reading is not repeated on every question.
A_FAILED_SCHEMA_IS_NOT_READ_ON_EVERY_QUESTION: Final = (
    "A schema reading that failed, because Lark did not answer or the app was never added to the "
    "Base, is not tried again for a minute. Tried on every question, every person asking anything "
    "would wait for Lark's timeout first, and the tenant's minute would be spent on listings that "
    "are refused."
)


# ------------------------------------------------------------------------ the schema
@dataclass(frozen=True)
class _Read:
    base_id: str
    tables: tuple[KnownTable, ...]
    at: datetime


class BaseSchema:
    """The switched-on Base's tables as its schema binds them, kept for `SCHEMA_KEPT_FOR`.

    One per process, like `brain.ops.live_records.SourceRecords`: kept on the application's state
    so that every question reads the same copy, and so that a schema read by one question spares
    the next the listings. Keyed by the Base, so switching to another Base reads again at once.
    """

    def __init__(
        self,
        *,
        keys: ConnectorKeys,
        caller: LarkCaller,
        resolver: Resolver,
        issuer: TokenIssuer,
        clock: Callable[[], datetime],
        kept_for: timedelta = SCHEMA_KEPT_FOR,
        retry: timedelta = SCHEMA_RETRIED_AFTER,
    ) -> None:
        self._keys = keys
        self._caller = caller
        self._resolver = resolver
        self._issuer = issuer
        self._clock = clock
        self._kept_for = kept_for
        self._retry = retry
        self._last: _Read | None = None
        self._failed: tuple[str, datetime] | None = None

    def __repr__(self) -> str:
        return f"BaseSchema(read={self._last is not None})"

    async def tables(self, use: LarkBaseUse) -> tuple[KnownTable, ...]:
        """The Base's tables now: kept, read again, or the last read where this one failed.

        A reading that failed is not tried again for `SCHEMA_RETRIED_AFTER`, so a Lark that is
        down, or a Base the app was never added to, costs one question a wait and not every one:
        `A_FAILED_SCHEMA_IS_NOT_READ_ON_EVERY_QUESTION`.
        """
        now = self._clock()
        last = self._last if self._last is not None and self._last.base_id == use.base_id else None
        if last is not None and now - last.at < self._kept_for:
            return last.tables
        kept = () if last is None else last.tables
        failed = self._failed
        if failed is not None and failed[0] == use.base_id and now - failed[1] < self._retry:
            return kept
        found = await asyncio.to_thread(self.read, use, now)
        if found is None:
            self._failed = (use.base_id, now)
            return kept
        self._failed = None
        self._last = _Read(base_id=use.base_id, tables=found, at=now)
        return found

    def read(self, use: LarkBaseUse, now: datetime) -> tuple[KnownTable, ...] | None:
        """One reading of the schema under a key borrowed for it, or None where there is none."""
        with opened(
            use,
            keys=self._keys,
            caller=self._caller,
            resolver=self._resolver,
            issuer=self._issuer,
            now=now,
        ) as reads:
            if isinstance(reads, str):
                log.warning("lark_base.schema_unread", why=reads)
                return None
            try:
                found, _ = discovered(reads, budget=lark_base.fair_share_budget())
            except (
                LarkBaseUnreachableError,
                LarkBaseRefusedError,
                LarkBaseBudgetError,
                ConnectorContractError,
            ) as failed:
                log.warning("lark_base.schema_unread", error=type(failed).__name__)
                return None
            return found


# --------------------------------------------------------------------- the live read
class LarkBaseSources:
    """`LiveSources` for one switched-on Base: each of its tables read by record id, as the app."""

    def __init__(
        self,
        use: LarkBaseUse,
        tables: Mapping[str, KnownTable],
        *,
        keys: ConnectorKeys,
        caller: LarkCaller,
        resolver: Resolver,
        issuer: TokenIssuer,
        clock: Callable[[], datetime],
    ) -> None:
        self._use = use
        self._tables = dict(tables)
        self._keys = keys
        self._caller = caller
        self._resolver = resolver
        self._issuer = issuer
        self._clock = clock

    def __repr__(self) -> str:
        return f"LarkBaseSources(tables={len(self._tables)})"

    def reads(self, connector: str, entity: str) -> IdentityMode | None:
        if connector != LARK_BASE or entity not in self._tables:
            return None
        # See A_BASE_IS_READ_AS_THE_APP.
        return IdentityMode.SERVICE

    def source_for(self, connector: str, *, mode: IdentityMode, asker: str) -> LiveSource | None:
        del asker  # a service read is the same read whoever asked
        if connector != LARK_BASE or mode is not IdentityMode.SERVICE:
            return None

        async def fetch(request: FetchRequest) -> LiveReply:
            return await asyncio.to_thread(self.read_one, request)

        return fetch

    def read_one(self, request: FetchRequest) -> LiveReply:
        """One record by its id, decoded by its table's bindings, and nothing kept."""
        ids = [value for key, value in request.filters if key == RECORD_ID_FILTER]
        known = self._tables.get(request.entity)
        if len(ids) != 1 or len(request.filters) != 1:
            return _refused(NOT_ONE_RECORD)
        if known is None:
            return _refused(NOT_A_KNOWN_TABLE)
        try:
            cursor = PageCursor(endpoint=Endpoint.GET_RECORD, record_id=ids[0])
        except ConnectorContractError:
            return _refused(NOT_ONE_RECORD)
        now = self._clock()
        with opened(
            self._use,
            keys=self._keys,
            caller=self._caller,
            resolver=self._resolver,
            issuer=self._issuer,
            now=now,
        ) as reads:
            if isinstance(reads, str):
                return _refused(reads)
            table = known.table
            try:
                row, _ = lark_base.read_record(
                    table.operation(Endpoint.GET_RECORD, host=self._use.host),
                    reads.records(table, Endpoint.GET_RECORD),
                    cursor,
                    budget=lark_base.fair_share_budget(),
                )
                fields = decode_row(table.bindings, row)
            except (LarkBaseUnreachableError, LarkBaseRefusedError) as failed:
                wait = getattr(failed, "wait_for", None) or None
                return LiveReply(outcome=failed.call_outcome, retry_after_seconds=wait)
            except (LarkBaseBudgetError, ConnectorContractError, TransportError) as failed:
                log.warning("lark_base.record_unread", error=type(failed).__name__)
                return LiveReply(outcome=CallOutcome.REJECTED)
        record = SourceRecord(entity=request.entity, id=str(row["id"]), **fields)
        return LiveReply(
            outcome=CallOutcome.OK,
            rows=TypedResult[SourceRecord](
                records=(record,), source=LARK_BASE, fetched_at=now.isoformat()
            ),
        )


def _refused(why: str) -> LiveReply:
    """A read this process would not make, as a rejection: not the source's ill health."""
    log.warning("lark_base.read_refused", why=why)
    return LiveReply(outcome=CallOutcome.REJECTED)


class Together:
    """`LiveSources` over the connected sources and a switched-on Base, each asked of its own."""

    def __init__(self, connected: LiveSources, base: LiveSources) -> None:
        self._connected = connected
        self._base = base

    def _of(self, connector: str) -> LiveSources:
        return self._base if connector == LARK_BASE else self._connected

    def reads(self, connector: str, entity: str) -> IdentityMode | None:
        return self._of(connector).reads(connector, entity)

    def source_for(self, connector: str, *, mode: IdentityMode, asker: str) -> LiveSource | None:
        return self._of(connector).source_for(connector, mode=mode, asker=asker)


def with_base(
    connected: LiveSources,
    use: LarkBaseUse | None,
    tables: tuple[KnownTable, ...],
    *,
    keys: ConnectorKeys,
    caller: LarkCaller,
    resolver: Resolver,
    issuer: TokenIssuer,
    clock: Callable[[], datetime],
) -> LiveSources:
    """The connected sources, and the Base beside them when one is switched on with tables."""
    if use is None or not tables:
        return connected
    return Together(
        connected,
        LarkBaseSources(
            use,
            tables_named(tables),
            keys=keys,
            caller=caller,
            resolver=resolver,
            issuer=issuer,
            clock=clock,
        ),
    )
