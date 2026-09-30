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

**The socket's timeout is the live read's.** The call is blocking and runs in a thread, which the
executor cannot cancel, so the caller is built with `live_read.LIVE_READ_TIMEOUT_MS` as its timeout
and the thread ends when the executor stops waiting for it rather than thirty seconds later.

Scope: every part that touches the world is handed in (the keys, the caller, the resolver, the
clock), so the tests drive it over recorded replies, and `live_records_for` is the one place the
real ones are chosen.

Task ids: M11.9.2, M11.5.1, M11.2.5
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Final

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.contract import ConnectorContractError, FetchRequest
from brain.connectors.declaration import ConnectorDeclaration, shipped
from brain.connectors.live_read import (
    LIVE_READ_TIMEOUT_MS,
    RECORD_ID_FILTER,
    LiveReply,
    LiveSource,
    LiveSources,
)
from brain.connectors.manifest import manifest_digest
from brain.connectors.rest import MAX_RESPONSE_BYTES
from brain.connectors.throttle import CallOutcome, classify
from brain.core.envelope import IdentityMode
from brain.ops.connectable import NotConnectableError, manifest_for
from brain.ops.connector_store import Connection, StoredConnections
from brain.ops.connector_sync_run import (
    ConnectorKeys,
    HttpsSourceCaller,
    RunTokenVault,
    SourceCaller,
    WorkerConnectorKeys,
    authorization,
)
from brain.ops.live_records import SourceRecords
from brain.ops.secrets import SecretsUnavailableError
from brain.ops.webhook_delivery import SystemResolver
from brain.tools.fetch import Resolver

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
    ) -> None:
        self._connections = MappingProxyType(dict(connections))
        self._keys = keys
        self._caller = caller
        self._resolver = resolver
        self._clock = clock
        self._declarations = shipped() if declarations is None else declarations

    def __repr__(self) -> str:
        return f"ConnectedSources(connected={sorted(self._connections)})"

    def _declared(self, connector: str) -> ConnectorDeclaration | None:
        declared = self._declarations.get(connector)
        if connector not in self._connections or declared is None:
            return None
        if declared.live is None or declared.reading is None:
            return None
        return declared

    def reads(self, connector: str, entity: str) -> IdentityMode | None:
        declared = self._declared(connector)
        if declared is None or declared.live is None or entity not in declared.live.entities():
            return None
        return declared.live.identity_mode(entity)

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
        """One record, read under a key borrowed for this read and given back when it ends."""
        live, reading = declared.live, declared.reading
        assert live is not None and reading is not None  # `_declared` admits no other
        ids = [value for key, value in request.filters if key == RECORD_ID_FILTER]
        if len(ids) != 1 or len(request.filters) != 1:
            return _refused(connection.connector, NOT_ONE_RECORD)
        try:
            manifest = manifest_for(connection.connector, connection.settings)
        except (NotConnectableError, ConnectorContractError):
            return _refused(connection.connector, NOT_CONNECTABLE)
        if manifest_digest(manifest) != connection.digest:
            return _refused(connection.connector, DECLARATION_CHANGED)
        lease = self._keys.lease(manifest.credential.ref, now=self._clock())
        try:
            try:
                key = lease.key()
            except SecretsUnavailableError:
                return _refused(connection.connector, NO_KEY_FOR_THE_READ)
            headers = {
                **reading.call_headers(connection.settings),
                "Accept": "application/json",
                "Authorization": authorization(reading.key_scheme(), key),
            }
            try:
                # The lookup's own one-record call where it names one, otherwise the reading's
                # list narrowed to the record. See `A_RECORD_IS_READ_BY_THE_CALL_THAT_HOLDS_IT`.
                own = live.operation(
                    request.entity, settings=connection.settings, resolver=self._resolver
                )
                operation = own or reading.operation(
                    request.entity, settings=connection.settings, resolver=self._resolver
                )
                arguments = {
                    **({} if own is not None else reading.first_page(request.entity)),
                    **live.arguments_for(request.entity, ids[0]),
                }
                checked = operation.prepare(arguments, resolver=self._resolver)
            except Exception:
                # Broad, and the type is not kept: a refusal can quote the id it refused.
                return _refused(connection.connector, ADDRESS_OR_SHAPE)
            answer = self._caller.get(
                checked.url, address=checked.address, headers=headers, max_bytes=MAX_RESPONSE_BYTES
            )
            call = classify(
                status=answer.status,
                timed_out=answer.timed_out,
                connection_failed=answer.connection_failed or answer.status is None,
            )
            if call is not CallOutcome.OK:
                said = answer.headers or {}
                wait = reading.retry_after(said) if call is CallOutcome.QUOTA else None
                return LiveReply(outcome=call, retry_after_seconds=wait)
            try:
                reply = reading.interpret(
                    operation,
                    status=answer.status or 0,
                    body=json.loads(answer.body),
                    fetched_at=self._clock().isoformat(),
                )
            except Exception:
                return _refused(connection.connector, ADDRESS_OR_SHAPE)
            return LiveReply(outcome=reply.call, rows=reply.rows)
        finally:
            lease.close(self._clock())


def _refused(connector: str, why: str) -> LiveReply:
    """A read this process would not make, as a rejection: not the source's ill health, no retry."""
    log.warning("live_read.refused", connector=connector, why=why)
    return LiveReply(outcome=CallOutcome.REJECTED)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def live_records_for(
    sessions: async_sessionmaker[AsyncSession] | None, vault: RunTokenVault | None
) -> SourceRecords | None:
    """The live reads this process makes, over its database and its vault, or None with no database.

    None leaves the answer lane answering from the rows it has, which is every process with no
    connection table to read. A process with no vault still reads its connections and refuses each
    read for want of a key, so the answer says the source could not be reached rather than
    answering from the index.
    """
    if sessions is None:
        return None
    keys = WorkerConnectorKeys(vault)
    caller = HttpsSourceCaller(timeout_seconds=LIVE_READ_TIMEOUT_MS / 1000)
    resolver = SystemResolver()
    stored = StoredConnections(sessions)

    async def connected() -> LiveSources:
        rows = await stored.connected()
        return ConnectedSources(
            {one.connector: one for one in rows},
            keys=keys,
            caller=caller,
            resolver=resolver,
            clock=_utc_now,
        )

    return SourceRecords(connected=connected, clock=_utc_now)
