"""The worker's half of reading a connected source: the key, the call, the pages, what each left.

`brain.ops.connector_sync` decides whether a connection may be read, what is kept from a row and
what an attempt costs; `brain.ops.connector_sync_store` holds the SQL. This is the four things
neither can hold, and `run_connector_sync_now` is what the worker's schedule starts as the
`connector_sync` control.

**The worker reads a source's key, and it is the only process that does.** The application writes a
key when an administrator connects a source and reads only the slot's metadata, because it runs no
connector. The worker runs them, so `ops/openbao/policies/worker.hcl` grants read on
`connector_keys/data/+` and nothing else under that engine, and `WorkerConnectorKeys` refuses a
reference outside `connector_keys/` and one not made for the worker's role before the vault is
asked. The reference comes from the manifest the connection's own settings build
(`brain.ops.connectable.key_reference`), never from a column somebody could edit to point at a
provider key. See `THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES`.

**The key goes into one header of one request and nowhere else.** It is not logged, not put in an
exception, not kept on the reading, and not in a run's record: every detail a run leaves is one of
`brain.ops.connector_sync`'s constant sentences, chosen by the kind of thing that happened. A caller
that fails reports the failure's kind, never its message, because a message can quote a header.

**Every call is admitted by the source's verified ceiling before it is made.** `plan.limits` is
`brain.connectors.throttle.limits_for`, and each call is checked with `brain.ops.limits.check` and
recorded only once admitted, so the run takes its fair share of the source's minute and waits for
room rather than spending the client's allowance. The window counts this run's calls: the shared
window store (`brain.ops.limit_store`) has no caller anywhere yet, and the source's own figure,
Xero's `X-DayLimit-Remaining`, is what catches the calls other integrations made.

**The connection goes to the address the address rule checked**, through the same pinned connection
`brain.ops.webhook_delivery` sends through, for its reason: a name that answered outside to the
check and inside to the connection is the ordinary way past the rule.

**A page is written when it is read.** Each page's records are upserted in a transaction of their
own before the next page is asked for, so a run that fails on page four keeps pages one to three,
with the reading time each was read at.

Rejected: reading through `brain.tools.fetch.Fetcher`, which the connectors' own `connector_fetch`
closures take. It carries no headers and no status, so a key cannot be sent through it and a 429
cannot come back through it as anything but an exception, which is the collapse
`xero.AN_UNREACHABLE_LEDGER_IS_NOT_AN_EMPTY_ONE` refuses.

Task ids: M42.6.5
"""

from __future__ import annotations

import asyncio
import http.client
import json
import ssl
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Protocol
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.projection import ProjectedRecord
from brain.connectors.rest import MAX_RESPONSE_BYTES
from brain.connectors.throttle import CallOutcome, classify
from brain.knowledge.chunk_store import ChunkStoreError, ingest_document
from brain.knowledge.item import KnowledgeItem
from brain.ops.connectable import READING_ROLE
from brain.ops.connector_sync import (
    ADDRESS_REFUSED,
    DOCUMENTS_WITHHELD,
    MAX_PAGES_PER_ENTITY,
    MAX_SECONDS_WAITING_IN_A_RUN,
    NO_KEY,
    NO_VAULT,
    OWN_SHARE_SPENT,
    READ_BUT_CUT_SHORT,
    READ_TO_THE_END,
    READINGS,
    SHAPE_DISAGREED,
    SOURCE_ALLOWANCE_REFUSED,
    VAULT_REFUSED,
    VAULT_UNREACHABLE,
    Attempt,
    SourceReading,
    StoredValue,
    SyncOutcome,
    SyncPlan,
    SyncState,
    after_attempt,
    failure_detail,
    plan_for,
    stored_fields,
)
from brain.ops.connector_sync_store import (
    LiveConnection,
    attempt_row,
    read_live,
    read_states,
    record_upsert,
)
from brain.ops.credentials import KEY_FIELD
from brain.ops.limits import LimiterState, check
from brain.ops.object_store import StaticKvReader
from brain.ops.openbao import (
    CONNECTOR_KEY_PREFIX,
    OpenBaoVault,
    VaultRefusedError,
    VaultUnreachableError,
)
from brain.ops.queue import Job
from brain.ops.secrets import SecretRef, SecretsUnavailableError, VaultRole
from brain.ops.webhook_delivery import HTTPS_PORT, SystemResolver, _PinnedHTTPSConnection
from brain.tools.fetch import Resolver, UnsafeAddressError

# ------------------------------------------------------------------ written-down reasons

#: Why the worker holds read on the connector keys and the application does not.
THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES: Final = (
    "A source's key is used for one thing, reading the source, and only the worker reads a source. "
    "So the worker's policy reads connector_keys/data/+ and the application's does not: the "
    "application writes a key when an administrator connects a source and reads the slot's "
    "metadata to say it is held, and a process that talks to a model has no reason to hold every "
    "source's key. The reader refuses a path outside connector_keys/ and a reference not made for "
    "the worker, so a declaration edited to point at a provider key is refused here before the "
    "vault is asked."
)

#: How long one call may take, connect to last byte. A page is a list of a hundred records and a
#: source that takes longer is reported as not answering in time, and tried again on its backoff.
CALL_TIMEOUT_SECONDS: Final = 30.0

#: What a source sees as the client. Names the product and nothing about the install.
USER_AGENT: Final = "company-brain-connectors/1"


class ConnectorKeyAbsentError(SecretsUnavailableError):
    """The vault answered and holds no key at this source's slot."""


# ------------------------------------------------------------------------ the key


class ConnectorKeys(Protocol):
    """Whatever hands the worker one source's key for one run."""

    def key_for(self, ref: SecretRef) -> str:
        """The key at this reference, or a `SecretsUnavailableError` saying why there is none."""
        ...


class WorkerConnectorKeys:
    """`ConnectorKeys` over the worker's vault, or over no vault at all.

    See `THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES`. The representation
    names whether a vault is configured and nothing else, so a traceback holding this object prints
    no address, token or key.
    """

    def __init__(self, vault: StaticKvReader | None) -> None:
        self._vault = vault

    def __repr__(self) -> str:
        return f"WorkerConnectorKeys(configured={self._vault is not None})"

    __str__ = __repr__

    def key_for(self, ref: SecretRef) -> str:
        if not ref.path.startswith(CONNECTOR_KEY_PREFIX) or ref.path == CONNECTOR_KEY_PREFIX:
            msg = (
                f"a source's key is read from {CONNECTOR_KEY_PREFIX} and nowhere else, and this "
                f"reference names the {ref.path.split('/', 1)[0]} engine. "
                f"{THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES}"
            )
            raise SecretsUnavailableError(msg)
        if ref.role is not READING_ROLE:
            msg = (
                f"this reference was made for the {ref.role.value} role and the worker reads "
                f"only references made for {READING_ROLE.value}"
            )
            raise SecretsUnavailableError(msg)
        if self._vault is None:
            raise SecretsUnavailableError(NO_VAULT)
        try:
            fields = self._vault.read_static_kv(ref.path)
        except VaultRefusedError as refused:
            if refused.status == http.client.NOT_FOUND:
                raise ConnectorKeyAbsentError(NO_KEY) from refused
            raise
        value = fields.get(KEY_FIELD)
        if not isinstance(value, str) or not value.strip():
            raise ConnectorKeyAbsentError(NO_KEY)
        return value


def worker_connector_keys(address: str, token: str) -> WorkerConnectorKeys:
    """The worker's reader, from the two settings the worker's environment carries.

    Both must be set, and an address that is not a URL is no vault, for
    `brain.ops.webhook_delivery.worker_signing_keys`' reasons.
    """
    if not address or not token:
        return WorkerConnectorKeys(None)
    try:
        return WorkerConnectorKeys(OpenBaoVault(address, token, role=VaultRole.WORKER))
    except ValueError:
        return WorkerConnectorKeys(None)


def key_detail(failure: SecretsUnavailableError) -> str:
    """The sentence a key that could not be read leaves, by the kind of failure only."""
    if isinstance(failure, ConnectorKeyAbsentError):
        return NO_KEY
    if isinstance(failure, VaultRefusedError):
        return VAULT_REFUSED
    if isinstance(failure, VaultUnreachableError):
        return VAULT_UNREACHABLE
    return NO_VAULT


# ----------------------------------------------------------------------- the call


@dataclass(frozen=True)
class SourceAnswer:
    """What one call came back with: a status, headers and a body, or that it came back not at all.

    No field for the request, so an answer kept for a moment longer than it should be still holds
    no header that was sent.
    """

    status: int | None = None
    headers: Mapping[str, str] | None = None
    body: bytes = b""
    timed_out: bool = False
    connection_failed: bool = False


class SourceCaller(Protocol):
    """One GET to a source, to the address the rule checked, with these headers, never following."""

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        """The answer, or a timeout or a failed connection. Never raises for the network."""
        ...


class HttpsSourceCaller:
    """`SourceCaller` over `http.client`, pinned to the checked address, reading a bounded body.

    A redirect is an answer with a 3xx status and nothing is followed, for
    `brain.ops.outbox_store.A_REDIRECT_IS_NOT_A_DELIVERY`'s reason turned round: a source that
    moved is a source whose new address has not passed the rule.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = CALL_TIMEOUT_SECONDS,
        context: ssl.SSLContext | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._context = context if context is not None else ssl.create_default_context()

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme != "https" or not host:
            return SourceAnswer(connection_failed=True)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        connection = _PinnedHTTPSConnection(
            host,
            parts.port or HTTPS_PORT,
            address=address,
            timeout=self._timeout,
            context=self._context,
        )
        try:
            connection.request("GET", path, headers={**headers, "User-Agent": USER_AGENT})
            answer = connection.getresponse()
            body = answer.read(max_bytes + 1)
            if len(body) > max_bytes:
                # A body past the bound is not parsed as a truncated one, which would read as a
                # shorter list; it is a source that did not answer in a shape this reads.
                return SourceAnswer(status=answer.status, headers={}, body=b"")
            return SourceAnswer(
                status=answer.status,
                headers={key.lower(): value for key, value in answer.getheaders()},
                body=body,
            )
        except TimeoutError:
            return SourceAnswer(timed_out=True)
        except (OSError, http.client.HTTPException):
            return SourceAnswer(connection_failed=True)
        finally:
            connection.close()


# ------------------------------------------------------------------------- one run


@dataclass(frozen=True)
class SyncRun:
    """What one run did, as counts. No source is named: a control run's detail has other readers."""

    read: int
    waiting: int
    failed: int
    not_due: int
    cannot_be_read: int

    def summary(self) -> str:
        if not (self.read or self.waiting or self.failed or self.not_due or self.cannot_be_read):
            return "no source is connected"
        return (
            f"{self.read} read, {self.waiting} waiting for a source's allowance, "
            f"{self.failed} failed, {self.not_due} not yet due, "
            f"{self.cannot_be_read} that cannot be read"
        )


#: What carries a synced document into the corpus. `ingest_document` bound to its sessions and
#: queue; it raises `ChunkStoreError` for a document its owner cannot reach.
DocumentSink = Callable[[KnowledgeItem], Awaitable[object]]


@dataclass
class _Reading:
    """One attempt in progress. Private, and never handed to anything that could keep it."""

    plan: SyncPlan
    started_at: datetime
    records: int = 0
    documents: int = 0
    withheld: bool = False
    cut_short: bool = False
    waited: float = 0.0


def _finish(
    one: _Reading,
    *,
    clock: Callable[[], datetime],
    outcome: SyncOutcome,
    detail: str,
    previous: SyncState | None,
    call: CallOutcome | None = None,
    retry_after_seconds: float | None = None,
) -> Attempt:
    reading = one.plan.reading
    assert reading is not None  # a plan that may run carries its reading; SyncPlan holds that
    return after_attempt(
        connector=one.plan.connector,
        started_at=one.started_at,
        finished_at=clock(),
        outcome=outcome,
        detail=detail,
        interval=reading.refresh_interval(),
        previous=previous,
        call=call,
        retry_after_seconds=retry_after_seconds,
        records=one.records,
        documents=one.documents,
        cut_short=one.cut_short,
    )


async def _write_page(
    sessions: async_sessionmaker[AsyncSession],
    kept: Sequence[tuple[ProjectedRecord, Mapping[str, StoredValue]]],
) -> None:
    if not kept:
        return
    async with sessions() as session, session.begin():
        for record, fields in kept:
            await session.execute(record_upsert(record, fields))


async def attempt(
    live: LiveConnection,
    plan: SyncPlan,
    *,
    previous: SyncState | None,
    sessions: async_sessionmaker[AsyncSession],
    documents: DocumentSink,
    keys: ConnectorKeys,
    caller: SourceCaller,
    resolver: Resolver,
    clock: Callable[[], datetime],
    sleep: Callable[[float], Awaitable[object]],
) -> Attempt:
    """Read one connection to the end, or as far as it can be read, and say what that came to."""
    manifest, reading = plan.manifest, plan.reading
    assert manifest is not None and reading is not None  # SyncPlan holds this for a runnable plan
    one = _Reading(plan=plan, started_at=clock())

    def finish(
        outcome: SyncOutcome,
        detail: str,
        *,
        call: CallOutcome | None = None,
        retry_after_seconds: float | None = None,
    ) -> Attempt:
        return _finish(
            one,
            clock=clock,
            outcome=outcome,
            detail=detail,
            previous=previous,
            call=call,
            retry_after_seconds=retry_after_seconds,
        )

    try:
        key = keys.key_for(manifest.credential.ref)
    except SecretsUnavailableError as unavailable:
        return finish(SyncOutcome.FAILED, key_detail(unavailable))
    headers = {
        **reading.call_headers(live.connection.settings),
        "Accept": "application/json",
        "Authorization": f"Bearer {key}",
    }
    visibility = {projection.entity: projection.visibility for projection in manifest.projections}
    limiter = LimiterState()

    for entity in reading.entities():
        try:
            operation = reading.operation(entity, resolver=resolver)
        except UnsafeAddressError:
            # The specification's own server is checked when it is loaded, before any path is
            # built, so a source whose name answers inside the network is refused here first.
            return finish(SyncOutcome.FAILED, ADDRESS_REFUSED)
        except Exception:
            return finish(SyncOutcome.FAILED, SHAPE_DISAGREED)
        arguments: Mapping[str, str] | None = reading.first_page(entity)
        pages = 0
        while arguments is not None:
            if pages >= MAX_PAGES_PER_ENTITY:
                one.cut_short = True
                break
            decision = check(now=clock(), limits=plan.limits, state=limiter)
            if not decision.allowed:
                if one.waited + decision.retry_after_seconds > MAX_SECONDS_WAITING_IN_A_RUN:
                    return finish(
                        SyncOutcome.QUOTA,
                        OWN_SHARE_SPENT,
                        retry_after_seconds=decision.retry_after_seconds,
                    )
                one.waited += decision.retry_after_seconds
                await sleep(decision.retry_after_seconds)
                continue
            limiter = limiter.record(clock(), plan.limits)
            try:
                checked = operation.prepare(arguments, resolver=resolver)
            except UnsafeAddressError:
                return finish(SyncOutcome.FAILED, ADDRESS_REFUSED)
            except Exception:
                return finish(SyncOutcome.FAILED, SHAPE_DISAGREED)
            answer = caller.get(
                checked.url, address=checked.address, headers=headers, max_bytes=MAX_RESPONSE_BYTES
            )
            read_at = clock()
            call = classify(
                status=answer.status,
                timed_out=answer.timed_out,
                connection_failed=answer.connection_failed or answer.status is None,
            )
            said = answer.headers or {}
            if call is CallOutcome.QUOTA:
                return finish(
                    SyncOutcome.QUOTA,
                    SOURCE_ALLOWANCE_REFUSED,
                    retry_after_seconds=reading.retry_after(said),
                )
            if call in (CallOutcome.REJECTED, CallOutcome.UNAVAILABLE):
                return finish(
                    SyncOutcome.FAILED,
                    failure_detail(call, timed_out=answer.timed_out),
                    call=call,
                )
            try:
                body = json.loads(answer.body)
                reply = reading.interpret(
                    operation, status=answer.status or 0, body=body, fetched_at=read_at.isoformat()
                )
                rows = [] if reply.rows is None else [r.model_dump() for r in reply.rows.records]
                kept: list[tuple[ProjectedRecord, Mapping[str, StoredValue]]] = []
                found: list[KnowledgeItem] = []
                for row in rows:
                    projected = reading.projected(entity, row, seen_at=read_at)
                    if projected is not None:
                        kept.append((projected, stored_fields(projected, visibility[entity])))
                    document = reading.document(entity, row, seen_at=read_at)
                    if document is not None:
                        found.append(document)
                returned = len(operation.project(body))
            except Exception:
                # Broad on purpose, and the type is not kept either: a refusal raised while reading
                # a row can quote the row. Nothing from this page was written.
                return finish(SyncOutcome.FAILED, SHAPE_DISAGREED)
            await _write_page(sessions, kept)
            one.records += len(kept)
            for document in found:
                try:
                    await documents(document)
                except ChunkStoreError:
                    one.withheld = True
                else:
                    one.documents += 1
            pages += 1
            arguments = reading.next_page(entity, arguments, body, returned)
            if arguments is not None and reading.allowance_spent(said):
                return finish(SyncOutcome.QUOTA, SOURCE_ALLOWANCE_REFUSED)

    if one.cut_short:
        detail = READ_BUT_CUT_SHORT
    elif one.withheld:
        detail = DOCUMENTS_WITHHELD
    else:
        detail = READ_TO_THE_END
    return finish(SyncOutcome.SYNCED, detail)


async def sync_on(
    *,
    sessions: async_sessionmaker[AsyncSession],
    documents: DocumentSink,
    now: datetime,
    keys: ConnectorKeys,
    caller: SourceCaller,
    resolver: Resolver,
    clock: Callable[[], datetime],
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    readings: Mapping[str, SourceReading] = READINGS,
) -> SyncRun:
    """Every live connection that may be read and is due, read once, and each attempt recorded."""
    async with sessions() as session, session.begin():
        live = await read_live(session)
        states = await read_states(session)
    read = waiting = failed = not_due = cannot = 0
    for one in live:
        previous = states.get(one.id)
        plan = plan_for(one.connection, last=previous, now=now, readings=readings)
        if plan.refused:
            cannot += 1
            continue
        if not plan.due:
            not_due += 1
            continue
        done = await attempt(
            one,
            plan,
            previous=previous,
            sessions=sessions,
            documents=documents,
            keys=keys,
            caller=caller,
            resolver=resolver,
            clock=clock,
            sleep=sleep,
        )
        async with sessions() as session, session.begin():
            await session.execute(attempt_row(one.id, done))
        if done.outcome is SyncOutcome.SYNCED:
            read += 1
        elif done.outcome is SyncOutcome.QUOTA:
            waiting += 1
        else:
            failed += 1
    return SyncRun(
        read=read, waiting=waiting, failed=failed, not_due=not_due, cannot_be_read=cannot
    )


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


@asynccontextmanager
async def corpus_sink(database_url: str, *, now: datetime) -> AsyncIterator[DocumentSink]:
    """`ingest_document` over application sessions, with the queue opened only if a document comes.

    The queue is opened on the first document and closed when the run ends, so a run over sources
    that yield none, which is every run today, spends no connection on it. The sessions are the
    application role's, because `know.chunk`'s policy binds that role and a document is written as
    its owner: see `brain.knowledge.chunk_store.THE_STORE_RUNS_AS_THE_OWNER_AND_NEVER_AS_ITSELF`.
    """
    from brain.ops.queue import enqueue_job, queue_app
    from brain.ops.worker import register_tasks
    from brain.session import make_app_engine, make_application_sessions

    engine = make_app_engine(database_url)
    async with AsyncExitStack() as stack:
        opened: list[Any] = []

        async def enqueue(job: Job) -> object:
            if not opened:
                app = queue_app(database_url, pool_max=1)
                register_tasks(app, database_url=database_url)
                opened.append(await stack.enter_async_context(app.open_async()))
            return await enqueue_job(opened[0], job)

        async def sink(item: KnowledgeItem) -> object:
            return await ingest_document(
                make_application_sessions(engine), item, enqueue=enqueue, now=now
            )

        try:
            yield sink
        finally:
            await engine.dispose()


def run_connector_sync_now(
    database_url: str,
    *,
    now: datetime,
    vault_address: str,
    vault_token: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> SyncRun:
    """`sync_on`, from a thread with no event loop of its own, with the worker's real parts.

    The shape `brain.ops.webhook_delivery.run_dispatch_now` takes, for its reasons. The records and
    the attempts are written through sessions over the worker's own login; see
    `brain.ops.connector_sync_store`.
    """
    from brain.session import make_app_engine, make_session_factory

    async def go() -> SyncRun:
        engine = make_app_engine(database_url)
        try:
            async with corpus_sink(database_url, now=now) as documents:
                return await sync_on(
                    sessions=make_session_factory(engine),
                    documents=documents,
                    now=now,
                    keys=worker_connector_keys(vault_address, vault_token),
                    caller=HttpsSourceCaller(),
                    resolver=SystemResolver(),
                    clock=_utc_now,
                )
        finally:
            await engine.dispose()

    return asyncio.run(go(), loop_factory=loop_factory)
