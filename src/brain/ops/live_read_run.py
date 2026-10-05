"""The application's half of reading a connected source while somebody waits: the key, the call.

`brain.connectors.live_read` runs a question's reads inside the budget and knows no vendor.
`brain.ops.live_records` turns an index hit into a live record. This is what neither can hold:
which sources are connected now, the key borrowed for one read, the one GET to the address the rule
checked, and the source's own interpretation of the reply. It is the question-time twin of
`brain.ops.connector_sync_run`, and it reuses that module's parts rather than copying them.

**The key is borrowed for one read and given back when the read ends (needs-rupash 99).** The
owner's decision is that a question borrows the source's key for that one question, rather than
handing every live read to the worker. So the application mints a child token against the same
`connector-run` role the worker's attempts use, reads the key with it and revokes it in a `finally`,
through `brain.ops.connector_sync_run.WorkerConnectorKeys`, which already refuses a reference
outside the connector key engine and a minted token wider than the role
(`connector_lease.judge_minted`). The application's vault policy grants that one mint and still
reads no key itself (`ops/openbao/policies/application.hcl`). See
`A_QUESTION_BORROWS_A_KEY_FOR_ONE_READ`.

**Only a service read is made here, and a delegated read is refused rather than upgraded
(M11.2.5).** This process holds no person's own credential for any source, so
`ConnectedSources.source_for` answers None for the requester's credentials and the executor records
the source as not read, rather than reading it with the connection's key. A source's
`declaration.LiveLookup` says which its reads are; the default is the requester's.

**The manifest a live read runs under is the one agreed to at connect.** A release that changed what
a connector declares waits for a person before the worker reads it on a schedule
(`connector_sync.plan_for`), and a question does not get round that by asking: a digest that
disagrees is a read refused, with a constant sentence in the operator's log.

**A record listed under another is named by both ids when it is read back (M11.7.3).** A
Cloudflare DNS record's index id is its zone's and its own, and the lookup lays both into the path
from it; the record read back is named the same way, so `brain.ops.live_records` matches it to its
index row.

**A record's figures are read by the report its source declares (M11.7.1, M11.7.2).** Google
Analytics' traffic for a property is not the property read again: `declaration.LiveReport` names the
calls a report is (one POST for Analytics; several for Search Console, POSTs and a GET), the
address rule checks each, and they are sent at once on pinned connections,
`SourcePoster` for a call with a body. When every call answered, the connector's own
interpretation turns the bodies into one record carrying the record's id, which the lane lays over
the index row as it lays a live record. A read may carry one range beside the id (`RANGE_FILTER`),
which only a report reads and only when it is a window this product wrote; that is how a figure
tool asks for any range within Google's sixteen months. A Google source's key file is exchanged
for a token first, for this one read, through `connector_sync_run.presented`, and the token goes
with the read. A process given no poster reads no report that posts and mints no token, and the
read is refused rather than made some other way.

**The socket's timeout is the live read's.** The call is blocking and runs in a thread, which the
executor cannot cancel, so the caller is built with `live_read.LIVE_READ_TIMEOUT_MS` as its timeout
and the thread ends when the executor stops waiting for it rather than thirty seconds later.

Scope: every part that touches the world is handed in (the keys, the caller, the resolver, the
clock), so the tests drive it over recorded replies, and `live_records_for` is the one place the
real ones are chosen.

Task ids: M11.9.2, M11.5.1, M11.2.5, M11.7.3, M11.7.1, M11.7.2, M11.6.3, M11.6.4
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Final

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.contract import ConnectorContractError, FetchRequest
from brain.connectors.date_range import DateWindow
from brain.connectors.declaration import (
    ChecksLiveFacts,
    ConnectorDeclaration,
    LiveLookup,
    PageReply,
    ReportCall,
    RoutedReading,
    listed_under,
    shipped,
)
from brain.connectors.google_token import TokenNotIssuedError
from brain.connectors.live_read import (
    LIVE_READ_TIMEOUT_MS,
    RANGE_FILTER,
    RECORD_ID_FILTER,
    LiveReply,
    LiveSource,
    LiveSources,
)
from brain.connectors.manifest import manifest_digest
from brain.connectors.rest import MAX_RESPONSE_BYTES
from brain.connectors.throttle import CallOutcome, classify
from brain.connectors.transports import SourceRecord
from brain.core.envelope import IdentityMode, TypedResult
from brain.ops.connectable import NotConnectableError, manifest_for
from brain.ops.connector_store import Connection, StoredConnections
from brain.ops.connector_sync_run import (
    ConnectorKeys,
    HttpsSourceCaller,
    RunTokenVault,
    SourceAnswer,
    SourceCaller,
    SourcePoster,
    WorkerConnectorKeys,
    borrowed,
    call_headers,
    page_operation,
    presented,
)
from brain.ops.lark_base_index import HttpsTokenIssuer, switched_on
from brain.ops.lark_base_live import BaseSchema, with_base
from brain.ops.lark_wiki_live import WikiPassages, WithheldPages, wiki_host
from brain.ops.lark_wiki_spaces import declared_spaces
from brain.ops.live_records import SourceRecords
from brain.ops.secrets import SecretsUnavailableError
from brain.ops.webhook_delivery import SystemResolver
from brain.tools.fetch import Fetchable, Resolver, UnsafeAddressError, assert_fetchable

log = structlog.get_logger(__name__)

#: The owner's decision about whose key a question reads with, and for how long.
A_QUESTION_BORROWS_A_KEY_FOR_ONE_READ: Final = (
    "A live read borrows the source's key for that one read: a run token minted against the "
    "connector-run role, the key read with it, and the token revoked when the read ends, whatever "
    "it came to. The application's own token may mint that token and read no key, so a copy of it "
    "reads nothing without leaving a mint in the vault's audit log. Handing every live read to the "
    "worker instead would put a queue between a person and every answer that reads a source."
)

# The sentences a refused read leaves in the operator's log. Constant, and never a value: a
# setting, a key or a reply's text could carry a client's name or the key itself.
NOT_CONNECTABLE: Final = "the connection's settings no longer build a manifest"
DECLARATION_CHANGED: Final = "the connector now declares something other than was agreed at connect"
NO_KEY_FOR_THE_READ: Final = "the source's key could not be borrowed for this read"
NOT_ONE_RECORD: Final = "the read did not name exactly one record by its id"
ADDRESS_OR_SHAPE: Final = "the source's address or reply was not one this reads"
NO_POSTER: Final = "this process was given no way to post, so no token or report could be asked for"


class ConnectedSources:
    """`LiveSources` over the connections live when a question was asked.

    Built per question from the connection rows, so a source connected on the Connectors screen is
    read from the next question with nothing restarted, and one disconnected is not.
    """

    def __init__(
        self,
        connections: Mapping[str, Connection],
        *,
        keys: ConnectorKeys,
        caller: SourceCaller,
        resolver: Resolver,
        clock: Callable[[], datetime],
        declarations: Mapping[str, ConnectorDeclaration] | None = None,
        poster: SourcePoster | None = None,
    ) -> None:
        self._connections = MappingProxyType(dict(connections))
        self._keys = keys
        self._caller = caller
        self._resolver = resolver
        self._clock = clock
        self._declarations = shipped() if declarations is None else declarations
        self._poster = poster

    def __repr__(self) -> str:
        return f"ConnectedSources(connected={sorted(self._connections)})"

    def _declared(self, connector: str) -> ConnectorDeclaration | None:
        declared = self._declarations.get(connector)
        if connector not in self._connections or declared is None:
            return None
        if declared.reading is None or (declared.live is None and declared.report is None):
            return None
        return declared

    def reads(self, connector: str, entity: str) -> IdentityMode | None:
        declared = self._declared(connector)
        if declared is None:
            return None
        if declared.live is not None and entity in declared.live.entities():
            return declared.live.identity_mode(entity)
        if declared.report is not None and entity in declared.report.entities():
            return declared.report.identity_mode(entity)
        return None

    def source_for(self, connector: str, *, mode: IdentityMode, asker: str) -> LiveSource | None:
        del asker  # a service read is the same read whoever asked; see the module docstring
        if mode is not IdentityMode.SERVICE:
            # See live_read.A_DELEGATED_READ_IS_NEVER_SHARED_OR_UPGRADED.
            return None
        declared = self._declared(connector)
        if declared is None:
            return None
        connection = self._connections[connector]

        async def fetch(request: FetchRequest) -> LiveReply:
            return await asyncio.to_thread(self.read_one, connection, declared, request)

        return fetch

    def read_one(
        self, connection: Connection, declared: ConnectorDeclaration, request: FetchRequest
    ) -> LiveReply:
        """One record, read under a key borrowed for this read and given back when it ends.

        A record whose figures the source declares as a report is read by that report
        (`declaration.LiveReport`); every other record by the reading's own operation.
        """
        live, report, reading = declared.live, declared.report, declared.reading
        assert reading is not None  # `_declared` admits no other
        ids = [value for key, value in request.filters if key == RECORD_ID_FILTER]
        ranges = [value for key, value in request.filters if key == RANGE_FILTER]
        if len(ids) != 1 or len(ranges) > 1 or len(request.filters) != 1 + len(ranges):
            return _refused(connection.connector, NOT_ONE_RECORD)
        window: DateWindow | None = None
        if ranges:
            # A range is a report's, and only a window this product wrote is one.
            if report is None or request.entity not in report.entities():
                return _refused(connection.connector, NOT_ONE_RECORD)
            try:
                window = DateWindow.parsed(ranges[0])
            except ValueError:
                return _refused(connection.connector, ADDRESS_OR_SHAPE)
        try:
            manifest = manifest_for(connection.connector, connection.settings)
        except (NotConnectableError, ConnectorContractError):
            return _refused(connection.connector, NOT_CONNECTABLE)
        if manifest_digest(manifest) != connection.digest:
            return _refused(connection.connector, DECLARATION_CHANGED)
        lease = borrowed(self._keys, reading, manifest.credential.ref, now=self._clock())
        try:
            try:
                key = lease.key()
            except SecretsUnavailableError:
                return _refused(connection.connector, NO_KEY_FOR_THE_READ)
            try:
                shown = presented(
                    reading,
                    key,
                    poster=self._poster,
                    resolver=self._resolver,
                    now=self._clock(),
                )
            except UnsafeAddressError:
                return _refused(connection.connector, ADDRESS_OR_SHAPE)
            except TokenNotIssuedError as refused:
                if self._poster is None:
                    return _refused(connection.connector, NO_POSTER)
                return LiveReply(outcome=refused.call)
            # A source that takes no key is sent no `Authorization` at all (M11.7.4).
            headers = call_headers(reading, connection.settings, shown)
            if report is not None and request.entity in report.entities():
                return self._read_report(
                    connection, declared, request.entity, ids[0], headers, window
                )
            if live is None:
                return _refused(connection.connector, NOT_ONE_RECORD)
            entity, fetched_at = request.entity, self._clock().isoformat()
            if isinstance(reading, RoutedReading):
                said_so = reading.unpublished(
                    entity, ids[0], settings=connection.settings, fetched_at=fetched_at
                )
                if said_so is not None:
                    # No server publishes it: it is told as that, with no call made.
                    return LiveReply(
                        outcome=CallOutcome.OK, rows=self._with_facts(live, entity, said_so)
                    )
            try:
                # A record listed under another is named by both ids, and what is read back is
                # named the same way. See `brain.connectors.declaration.A_RECORD_LISTED_UNDER_...`.
                under = listed_under(reading, request.entity)
                parent_id = None if under is None else under.split(ids[0])[0]
                # The lookup's own one-record call where it names one, otherwise the reading's
                # page narrowed to the record. See `A_RECORD_IS_READ_BY_THE_CALL_THAT_HOLDS_IT`.
                own = live.operation(entity, settings=connection.settings, resolver=self._resolver)
                arguments = dict(live.arguments_for(entity, ids[0]))
                if own is None and not isinstance(reading, RoutedReading):
                    arguments = {**reading.first_page(entity), **arguments}
                operation = own or page_operation(
                    reading,
                    entity,
                    arguments,
                    settings=connection.settings,
                    resolver=self._resolver,
                )
                checked = operation.prepare(arguments, resolver=self._resolver)
            except Exception:
                # Broad, and the type is not kept: a refusal can quote the id it refused.
                return _refused(connection.connector, ADDRESS_OR_SHAPE)
            answer = self._caller.get(
                checked.url, address=checked.address, headers=headers, max_bytes=MAX_RESPONSE_BYTES
            )

            def interpreted(status: int, body: Any, at: str) -> PageReply:
                reply = reading.interpret(operation, status=status, body=body, fetched_at=at)
                if reply.rows is None or under is None or parent_id is None:
                    return reply
                return replace(reply, rows=under.named(reply.rows, parent_id))

            replied = self._answered(connection, declared, answer, interpreted)
            if replied.rows is None:
                return replied
            return replace(replied, rows=self._with_facts(live, entity, replied.rows))
        finally:
            lease.close(self._clock())

    def _read_report(
        self,
        connection: Connection,
        declared: ConnectorDeclaration,
        entity: str,
        source_id: str,
        headers: Mapping[str, str],
        window: DateWindow | None,
    ) -> LiveReply:
        """The figures one record names, by the calls its source's report is, made at once.

        See `declaration.A_REPORT_S_CALLS_ARE_MADE_AT_ONCE_AND_ANSWER_TOGETHER`: every call is sent
        at the same moment on its own pinned connection, the report costs its slowest call, and
        the first call that did not answer is the report's outcome.
        """
        report = declared.report
        assert report is not None  # `read_one` sends only a declared report's entities here
        today = self._clock().date()
        try:
            asked = report.request_for(
                entity, source_id, settings=connection.settings, today=today, window=window
            )
            checked = tuple((one, assert_fetchable(one.url, self._resolver)) for one in asked)
        except Exception:
            # Broad, and the type is not kept, for `read_one`'s reason.
            return _refused(connection.connector, ADDRESS_OR_SHAPE)
        if not checked:
            return _refused(connection.connector, ADDRESS_OR_SHAPE)
        poster = self._poster
        if poster is None and any(one.body is not None for one, _ in checked):
            return _refused(connection.connector, NO_POSTER)

        def send(pair: tuple[ReportCall, Fetchable]) -> SourceAnswer:
            one, where = pair
            if one.body is None:
                return self._caller.get(
                    where.url, address=where.address, headers=headers, max_bytes=MAX_RESPONSE_BYTES
                )
            assert poster is not None  # a call with a body was refused above without one
            return poster.post(
                where.url,
                address=where.address,
                headers={**headers, "Content-Type": "application/json"},
                body=one.body,
                max_bytes=MAX_RESPONSE_BYTES,
            )

        if len(checked) == 1:
            answers = [send(checked[0])]
        else:
            with ThreadPoolExecutor(max_workers=len(checked)) as pool:
                answers = list(pool.map(send, checked))
        for answer in answers:
            failed = self._failed(declared, answer)
            if failed is not None:
                return failed
        try:
            reply = report.interpret(
                entity,
                source_id,
                answers=tuple(json.loads(one.body) for one in answers),
                today=today,
                window=window,
                fetched_at=self._clock().isoformat(),
            )
        except Exception:
            return _refused(connection.connector, ADDRESS_OR_SHAPE)
        return LiveReply(outcome=reply.call, rows=reply.rows)

    def _failed(self, declared: ConnectorDeclaration, answer: SourceAnswer) -> LiveReply | None:
        """The reply for an answer that was not an answer, or None when the source answered."""
        reading = declared.reading
        assert reading is not None  # `_declared` admits no other
        call = classify(
            status=answer.status,
            timed_out=answer.timed_out,
            connection_failed=answer.connection_failed or answer.status is None,
        )
        if call is CallOutcome.OK:
            return None
        said = answer.headers or {}
        wait = reading.retry_after(said) if call is CallOutcome.QUOTA else None
        return LiveReply(outcome=call, retry_after_seconds=wait)

    def _answered(
        self,
        connection: Connection,
        declared: ConnectorDeclaration,
        answer: SourceAnswer,
        interpret: Callable[[int, Any, str], PageReply],
    ) -> LiveReply:
        """One answer, classified, and interpreted by the source's own code when it answered."""
        failed = self._failed(declared, answer)
        if failed is not None:
            return failed
        try:
            reply = interpret(
                answer.status or 0, json.loads(answer.body), self._clock().isoformat()
            )
        except Exception:
            return _refused(connection.connector, ADDRESS_OR_SHAPE)
        return LiveReply(outcome=reply.call, rows=reply.rows)

    def _with_facts(
        self, live: LiveLookup, entity: str, rows: TypedResult[SourceRecord]
    ) -> TypedResult[SourceRecord]:
        """The rows with the facts a lookup reads besides its source's record, where it reads any.

        See `brain.connectors.declaration.ChecksLiveFacts`. Each fact is a value read for this
        question, laid over its row and kept nowhere.
        """
        if not isinstance(live, ChecksLiveFacts):
            return rows
        records = tuple(
            SourceRecord.model_validate(
                {
                    **one.model_dump(),
                    **live.facts(entity, one.id, caller=self._caller, resolver=self._resolver),
                }
            )
            for one in rows.records
        )
        return rows.model_copy(update={"records": records})


def _refused(connector: str, why: str) -> LiveReply:
    """A read this process would not make, as a rejection: not the source's ill health, no retry."""
    log.warning("live_read.refused", connector=connector, why=why)
    return LiveReply(outcome=CallOutcome.REJECTED)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def base_schema_for(vault: RunTokenVault | None) -> BaseSchema:
    """The process's one reading of a switched-on Lark Base's schema, over its vault."""
    return BaseSchema(
        keys=WorkerConnectorKeys(vault),
        caller=HttpsSourceCaller(timeout_seconds=LIVE_READ_TIMEOUT_MS / 1000),
        resolver=SystemResolver(),
        issuer=HttpsTokenIssuer(),
        clock=_utc_now,
    )


def wiki_passages_for(
    sessions: async_sessionmaker[AsyncSession] | None,
    vault: RunTokenVault | None,
    *,
    withheld: WithheldPages | None = None,
) -> WikiPassages | None:
    """The Wiki's passages for the answer lane's model step, or None with no Wiki switched on.

    Asked on each question, so a Wiki switched on or off in Connect Lark is read or not from the
    next one, and its declared spaces are read from the database on each question too
    (`brain.ops.lark_wiki_spaces.declared_spaces`).
    """
    host = wiki_host()
    if sessions is None or host is None:
        return None
    return WikiPassages(
        host,
        lambda: declared_spaces(sessions),
        keys=WorkerConnectorKeys(vault),
        caller=HttpsSourceCaller(timeout_seconds=LIVE_READ_TIMEOUT_MS / 1000),
        resolver=SystemResolver(),
        issuer=HttpsTokenIssuer(),
        withheld=withheld,
    )


def live_records_for(
    sessions: async_sessionmaker[AsyncSession] | None,
    vault: RunTokenVault | None,
    *,
    schema: BaseSchema | None = None,
) -> SourceRecords | None:
    """The live reads this process makes, over its database and its vault, or None with no database.

    None leaves the answer lane answering from the rows it has, which is every process with no
    connection table to read. A process with no vault still reads its connections and refuses each
    read for want of a key, so the answer says the source could not be reached rather than
    answering from the index. A Lark Base switched on in Connect Lark is read beside the connected
    sources (`brain.ops.lark_base_live`), its schema from `schema`, which the answer route shares
    so that the question and its live read see the same tables.
    """
    if sessions is None:
        return None
    keys = WorkerConnectorKeys(vault)
    caller = HttpsSourceCaller(timeout_seconds=LIVE_READ_TIMEOUT_MS / 1000)
    resolver = SystemResolver()
    stored = StoredConnections(sessions)
    tables = base_schema_for(vault) if schema is None else schema
    issuer = HttpsTokenIssuer()

    async def connected() -> LiveSources:
        rows = await stored.connected()
        sources = ConnectedSources(
            {one.connector: one for one in rows},
            keys=keys,
            caller=caller,
            resolver=resolver,
            clock=_utc_now,
            poster=caller,
        )
        use = switched_on()
        return with_base(
            sources,
            use,
            () if use is None else await tables.tables(use),
            keys=keys,
            caller=caller,
            resolver=resolver,
            issuer=issuer,
            clock=_utc_now,
        )

    return SourceRecords(connected=connected, clock=_utc_now)
