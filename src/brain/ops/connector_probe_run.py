"""The worker's half of testing a connection: the one call, under a lease and the source's ceiling.

`brain.ops.connector_probe` decides when a test is owed and how often, `brain.ops.connector_sync`
what a test's row says, and `brain.ops.connector_sync_store` holds the SQL. This is the part none of
them can hold, because it needs the key, and only the worker reads a source's key: see
`brain.ops.connector_sync_run.THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES`.

**One call, the first page a scheduled read would ask for, and the answer is read and dropped.**
The first page of the source's first entity is the call whose success means a read would work: the
same address, the same headers (`brain.ops.connector_sync_run.call_headers`), the same key. The
answer is interpreted by the connector's own `interpret`, so an answer in a shape this release does
not read fails the test rather than passing it, and then it goes out of scope: nothing is projected,
nothing reaches `proj.record`, nothing is returned, and the row carries one of
`brain.ops.connector_sync`'s constant sentences. See `A_TEST_KEEPS_NOTHING_THE_SOURCE_SENT`.

**The key is leased for the one call, as a scheduled read leases it.** The same
`brain.ops.connector_sync_run.ConnectorKeys`, minted for this attempt and given back in a `finally`,
and the row records how the lease ended, so a test is counted on the Secrets vault screen with every
other attempt. Nothing is leased for a test that makes no call.

**Where it runs.** `tick_probes` is called by `brain.ops.worker.run_schedule` after each tick of the
control schedule. It reads the requests in the worker's own loop, which is two small statements, and
only when a test is owed does it start a thread with its own loop and engine, the shape
`brain.ops.connector_sync_run.run_connector_sync_now` takes, because the call blocks.

Task ids: M27.15.8
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.rest import MAX_RESPONSE_BYTES
from brain.connectors.throttle import CallOutcome, classify
from brain.ops.connector_probe import (
    PROBE_LOCK,
    TESTS_COUNTED_OVER,
    in_quota_wait,
    owed_probes,
    probe_limits,
    probe_requests,
    windows_after,
)
from brain.ops.connector_sync import (
    ADDRESS_REFUSED,
    PROBE_ANSWERED,
    PROBE_NOT_SENT_SHARE_SPENT,
    PROBE_NOT_SENT_WHILE_WAITING,
    PROBE_REFUSED_FOR_NOW,
    READINGS,
    SHAPE_DISAGREED,
    Attempt,
    ProbeVerdict,
    SourceReading,
    SyncPlan,
    SyncState,
    after_probe,
    failure_detail,
    plan_for,
    verdict_of,
)
from brain.ops.connector_sync_run import (
    ConnectorKeys,
    HttpsSourceCaller,
    KeyLease,
    SourceCaller,
    borrowed,
    call_headers,
    first_arguments,
    key_detail,
    page_operation,
    worker_connector_keys,
)
from brain.ops.connector_sync_store import (
    LiveConnection,
    attempt_row,
    read_live,
    read_probe_starts,
    read_probe_targets,
    read_states,
)
from brain.ops.limits import check
from brain.ops.schedule_store import take_the_lock
from brain.ops.secrets import SecretsUnavailableError
from brain.ops.webhook_delivery import SystemResolver
from brain.tools.fetch import Resolver, UnsafeAddressError

# ------------------------------------------------------------------ written-down reasons
#: Why the answer to a test is read and then dropped.
A_TEST_KEEPS_NOTHING_THE_SOURCE_SENT: Final = (
    "A test proves a key and an address, and the owner's rule is that connectors never bulk-sync. "
    "So the answer is read only as far as the connector's own interpretation of it, which is what "
    "tells an answer this release reads from one it does not, and nothing of it is kept: no record "
    "is projected, nothing is written but the attempt's row, and that row holds a constant "
    "sentence. The page shows whether it worked and never what the source said."
)

#: What a test that made no call waits on before the next one: nothing, it spent nothing.
NO_INTERVAL: Final = timedelta(0)


@dataclass(frozen=True)
class ProbeRun:
    """What one pass made of the tests owed. Counts only: no source is named."""

    answered: int = 0
    not_working: int = 0
    not_sent: int = 0
    #: A scheduled read held the lock, so nothing was tested this pass and the requests wait.
    held_by_a_read: bool = False

    def summary(self) -> str:
        if self.held_by_a_read:
            return "a scheduled read was running, so the tests asked for wait for the next pass"
        return f"{self.answered} answered, {self.not_working} not working, {self.not_sent} not sent"


# ------------------------------------------------------------------------- one test
def _call_under(
    live: LiveConnection,
    reading: SourceReading,
    lease: KeyLease,
    *,
    finish: Callable[..., Attempt],
    caller: SourceCaller,
    resolver: Resolver,
    clock: Callable[[], datetime],
) -> Attempt:
    """The one call, with the key the lease holds. See `A_TEST_KEEPS_NOTHING_THE_SOURCE_SENT`."""
    try:
        key = lease.key()
    except SecretsUnavailableError as unavailable:
        return finish(key_detail(unavailable))
    settings = live.connection.settings
    try:
        entity = reading.entities()[0]
        first = first_arguments(reading, entity, settings=settings)
        if first is None:
            # A routed reading whose list holds nothing a server publishes has no call to test.
            return finish(SHAPE_DISAGREED)
        operation = page_operation(reading, entity, first, settings=settings, resolver=resolver)
        checked = operation.prepare(first, resolver=resolver)
    except UnsafeAddressError:
        return finish(ADDRESS_REFUSED)
    except Exception:
        return finish(SHAPE_DISAGREED)
    answer = caller.get(
        checked.url,
        address=checked.address,
        headers=call_headers(reading, settings, key),
        max_bytes=MAX_RESPONSE_BYTES,
    )
    call = classify(
        status=answer.status,
        timed_out=answer.timed_out,
        connection_failed=answer.connection_failed or answer.status is None,
    )
    if call is CallOutcome.QUOTA:
        said = answer.headers or {}
        return finish(PROBE_REFUSED_FOR_NOW, retry_after_seconds=reading.retry_after(said))
    if call in (CallOutcome.REJECTED, CallOutcome.UNAVAILABLE):
        return finish(failure_detail(call, timed_out=answer.timed_out), call=call)
    try:
        reading.interpret(
            operation,
            status=answer.status or 0,
            body=json.loads(answer.body),
            fetched_at=clock().isoformat(),
        )
    except Exception:
        # Broad and typeless for `brain.ops.connector_sync_run`'s reason: a refusal raised while
        # reading an answer can quote it.
        return finish(SHAPE_DISAGREED)
    return finish(PROBE_ANSWERED)


def probe_one(
    live: LiveConnection,
    plan: SyncPlan,
    *,
    previous: SyncState | None,
    recent: tuple[datetime, ...],
    keys: ConnectorKeys,
    caller: SourceCaller,
    resolver: Resolver,
    clock: Callable[[], datetime],
) -> Attempt:
    """Test one connection a plan admits, or say why no call was made, and give the lease back.

    The wait the source asked for and the source's windows are asked before a lease is taken, so a
    test held back reads no key. `recent` is when this connection's tests over
    `brain.ops.connector_probe.TESTS_COUNTED_OVER` started.
    """
    manifest, reading = plan.manifest, plan.reading
    assert manifest is not None and reading is not None  # SyncPlan holds this for a runnable plan
    started = clock()

    def finish(
        detail: str, *, call: CallOutcome | None = None, retry_after_seconds: float | None = None
    ) -> Attempt:
        return after_probe(
            connector=plan.connector,
            started_at=started,
            finished_at=clock(),
            detail=detail,
            interval=reading.refresh_interval(),
            previous=previous,
            call=call,
            retry_after_seconds=retry_after_seconds,
        )

    if in_quota_wait(previous, now=started):
        return finish(PROBE_NOT_SENT_WHILE_WAITING)
    limits = probe_limits(manifest)
    if not check(now=started, limits=limits, state=windows_after(recent, limits)).allowed:
        return finish(PROBE_NOT_SENT_SHARE_SPENT)
    lease = borrowed(keys, reading, manifest.credential.ref, now=clock())
    try:
        done = _call_under(
            live, reading, lease, finish=finish, caller=caller, resolver=resolver, clock=clock
        )
    finally:
        ended = lease.close(clock())
    return replace(done, lease=ended)


# ------------------------------------------------------------------------ one pass
async def probe_on(
    *,
    sessions: async_sessionmaker[AsyncSession],
    now: datetime,
    keys: ConnectorKeys,
    caller: SourceCaller,
    resolver: Resolver,
    clock: Callable[[], datetime],
    readings: Mapping[str, SourceReading] = READINGS,
) -> ProbeRun:
    """Every test owed at `now`, made once and recorded, under the scheduled read's lock.

    The lock is held for the whole pass in a transaction of its own, which is
    `brain.ops.schedule_store.take_the_lock`'s constraint, and the requests are read again inside
    it, so two replicas that both saw a request make one test between them.
    """
    async with sessions() as held, held.begin():
        if not await take_the_lock(held, PROBE_LOCK):
            return ProbeRun(held_by_a_read=True)
        async with sessions() as session, session.begin():
            requested = await probe_requests(session)
            owed = set(owed_probes(requested, await read_probe_targets(session), now=now))
            live = await read_live(session) if owed else ()
            states = await read_states(session) if owed else {}
        answered = not_working = not_sent = 0
        for one in live:
            if one.connection.connector not in owed:
                continue
            previous = states.get(one.id)
            plan = plan_for(one.connection, last=previous, now=now, readings=readings)
            if plan.refused:
                at = clock()
                done = after_probe(
                    connector=plan.connector,
                    started_at=at,
                    finished_at=at,
                    detail=plan.refused,
                    interval=NO_INTERVAL,
                    previous=previous,
                )
            else:
                async with sessions() as session:
                    recent = await read_probe_starts(session, one.id, now - TESTS_COUNTED_OVER)
                done = probe_one(
                    one,
                    plan,
                    previous=previous,
                    recent=recent,
                    keys=keys,
                    caller=caller,
                    resolver=resolver,
                    clock=clock,
                )
            async with sessions() as session, session.begin():
                await session.execute(attempt_row(one.id, done))
            match verdict_of(done.detail):
                case ProbeVerdict.ANSWERED:
                    answered += 1
                case ProbeVerdict.NOT_SENT:
                    not_sent += 1
                case ProbeVerdict.WAITING | ProbeVerdict.FAILED:
                    not_working += 1
    return ProbeRun(answered=answered, not_working=not_working, not_sent=not_sent)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def run_connector_probes_now(
    database_url: str,
    *,
    now: datetime,
    vault_address: str,
    vault_token: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> ProbeRun:
    """`probe_on`, from a thread with no event loop of its own, with the worker's real parts.

    `brain.ops.connector_sync_run.run_connector_sync_now`'s shape, for its reasons.
    """
    from brain.session import make_app_engine, make_session_factory

    async def go() -> ProbeRun:
        engine = make_app_engine(database_url)
        try:
            return await probe_on(
                sessions=make_session_factory(engine),
                now=now,
                keys=worker_connector_keys(vault_address, vault_token),
                caller=HttpsSourceCaller(),
                resolver=SystemResolver(),
                clock=_utc_now,
            )
        finally:
            await engine.dispose()

    return asyncio.run(go(), loop_factory=loop_factory)


def _probe_in_thread(database_url: str, now: datetime) -> ProbeRun:
    """What the thread runs: a literal call to `run_connector_probes_now`, with the worker's vault.

    The vault is the worker's own, read from this process's settings, as the `connector_sync`
    runner reads it, and the loop is the worker's, for `brain.ops.worker._loop_factory`'s reason.
    """
    from brain.ops.worker import _loop_factory
    from brain.settings import process_environment, settings_from

    settings = settings_from(process_environment())
    return run_connector_probes_now(
        database_url,
        now=now,
        vault_address=settings.vault_address,
        vault_token=settings.vault_token,
        loop_factory=_loop_factory(),
    )


async def tick_probes(
    sessions: async_sessionmaker[AsyncSession], *, now: datetime, database_url: str
) -> ProbeRun | None:
    """Make the tests owed at `now`, or return None having read two small statements.

    Called on every tick of the worker's schedule, so the common case, nothing asked, is one read
    of one namespace of `ops.setting` in the worker's own loop. The thread's work is a literal call
    to `_probe_in_thread`, which `brain.ops.controls` can follow to `connector_sync`'s `plan_for`,
    where a function handed to the thread as a value would read as a caller nothing reaches.
    """
    async with sessions() as session:
        requested = await probe_requests(session)
        targets = await read_probe_targets(session) if requested else ()
    if not owed_probes(requested, targets, now=now):
        return None
    return await asyncio.to_thread(lambda: _probe_in_thread(database_url, now))
