"""The worker's half of the nightly schema check: one page of each kind of record, and the finding.

`brain.ops.schema_drift` decides what a night's reading means and `brain.ops.schema_drift_store`
holds the SQL. This makes the calls, and `run_schema_check_now` is what the worker's schedule
starts as the `connector_schema_check` control, once a night.

**It reads the way the scheduled read does, with the same parts.** Each live connection is planned
by `brain.ops.connector_sync.plan_for`, so a connection the scheduled read refuses (a declaration
that changed and was not agreed again, a source this release cannot read) is not read here either.
Its key is leased for the check and given back in a `finally`, its calls go to the address the
address rule checked through the same `SourceCaller`, and every call is admitted by the source's
verified ceiling before it is made. See `brain.ops.connector_sync_run`, whose arguments all apply.

**One page of each kind of record, and nothing is kept but names and counts.** The first page the
scheduled read would ask for is enough to see which mapped fields a source still answers, and a
night's check that cost a source's allowance more than a page per kind of record would be a second
scheduled read by another name. The page is projected by the connector's own mapping and only the
names of the fields any record answered, and how many records there were, leave this module. No
record is written to the index, and the page is discarded. See
`brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`.

**A call that failed reads no record, and a night that read none says nothing.** A refused call, a
spent allowance or a page the connector could not read is an observation of nought records, which
`brain.ops.schema_drift.judged` answers by keeping the last night's finding. The check never turns
a source's outage into a field gone. See `A_FAILED_CALL_IS_NOT_A_MISSING_FIELD`.

Rejected: reading each record live instead of a page. It is one call per record for a finding one
page makes, and a small ledger's single page already holds every kind of record it has.

Task ids: M11.8.7
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.declaration import SourceReading
from brain.connectors.rest import MAX_RESPONSE_BYTES
from brain.connectors.throttle import CallOutcome, classify
from brain.ops.connector_sync import READINGS, plan_for
from brain.ops.connector_sync_run import (
    ConnectorKeys,
    HttpsSourceCaller,
    SourceCaller,
    call_headers,
    worker_connector_keys,
)
from brain.ops.connector_sync_store import LiveConnection, read_live
from brain.ops.limits import LimiterState, check
from brain.ops.schema_drift import Observation, SchemaFinding, judged
from brain.ops.schema_drift_store import finding_row, read_findings
from brain.ops.secrets import SecretsUnavailableError
from brain.ops.webhook_delivery import SystemResolver
from brain.tools.fetch import Resolver

#: Why a failed call is an observation of no records rather than of every field missing.
A_FAILED_CALL_IS_NOT_A_MISSING_FIELD: Final = (
    "A call that was refused, timed out, found the allowance spent or came back in a shape the "
    "connector could not read has shown nothing about the source's fields. It is recorded as a "
    "call that read no record, and the night keeps the last night's finding for the fields that "
    "call reads, so an outage is never reported as a renamed field."
)


@dataclass(frozen=True)
class SchemaRun:
    """What one night's check came to, as counts. No source is named, as `SyncRun` names none."""

    checked: int
    changed: int
    cannot_be_read: int

    def summary(self) -> str:
        if not (self.checked or self.cannot_be_read):
            return "no source is connected"
        return (
            f"{self.checked} checked, {self.changed} with a field no longer answered, "
            f"{self.cannot_be_read} that cannot be read"
        )


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _page(
    reading: SourceReading,
    entity: str,
    live: LiveConnection,
    *,
    headers: Mapping[str, str],
    caller: SourceCaller,
    resolver: Resolver,
) -> Observation:
    """The first page of one kind of record, as the fields its mapping reads and those answered.

    Broad on the reading and the projection, as `connector_sync_run` is: a refusal raised while
    reading a row can quote the row, so neither its type nor its message is kept, and the call is
    an observation of no records. See `A_FAILED_CALL_IS_NOT_A_MISSING_FIELD`.
    """
    try:
        operation = reading.operation(entity, settings=live.connection.settings, resolver=resolver)
        depended = frozenset(one.target for one in operation.transport.fields)
    except Exception:
        return Observation(depended=frozenset(), answered=frozenset(), sampled=0)
    try:
        prepared = operation.prepare(reading.first_page(entity), resolver=resolver)
        answer = caller.get(
            prepared.url, address=prepared.address, headers=headers, max_bytes=MAX_RESPONSE_BYTES
        )
        outcome = classify(
            status=answer.status,
            timed_out=answer.timed_out,
            connection_failed=answer.connection_failed or answer.status is None,
        )
        if outcome is not CallOutcome.OK:
            return Observation(depended=depended, answered=frozenset(), sampled=0)
        rows = operation.project(json.loads(answer.body))
    except Exception:
        return Observation(depended=depended, answered=frozenset(), sampled=0)
    answered = frozenset(name for row in rows for name in row)
    return Observation(depended=depended, answered=answered, sampled=len(rows))


async def check_schemas(
    *,
    sessions: async_sessionmaker[AsyncSession],
    now: datetime,
    keys: ConnectorKeys,
    caller: SourceCaller,
    resolver: Resolver,
    clock: Callable[[], datetime],
    readings: Mapping[str, SourceReading] = READINGS,
) -> SchemaRun:
    """Every live connection's schema, read once, and each kind of record's finding appended."""
    async with sessions() as session:
        live = await read_live(session)
        previous = await read_findings(session)
    checked = changed = cannot = 0
    for one in live:
        plan = plan_for(one.connection, last=None, now=now, readings=readings)
        if plan.refused or plan.manifest is None or plan.reading is None:
            cannot += 1
            continue
        reading = plan.reading
        lease = keys.lease(plan.manifest.credential.ref, now=clock())
        findings: list[SchemaFinding] = []
        try:
            try:
                headers = call_headers(reading, one.connection.settings, lease.key())
            except SecretsUnavailableError:
                headers = None
            limiter = LimiterState()
            for entity in reading.entities():
                decision = check(now=clock(), limits=plan.limits, state=limiter)
                if headers is None or not decision.allowed:
                    # No key, or the source's share is spent: nothing was read, so nothing is
                    # judged afresh. See A_FAILED_CALL_IS_NOT_A_MISSING_FIELD.
                    seen = Observation(depended=frozenset(), answered=frozenset(), sampled=0)
                else:
                    limiter = limiter.record(clock(), plan.limits)
                    seen = _page(
                        reading, entity, one, headers=headers, caller=caller, resolver=resolver
                    )
                last = previous.get((one.id, entity))
                if seen.sampled == 0 and not seen.depended and last is not None:
                    # The fields a call that never began would have read are the last night's.
                    seen = Observation(
                        depended=frozenset(last.answered) | frozenset(last.missing),
                        answered=frozenset(),
                        sampled=0,
                    )
                findings.append(judged(entity, (seen,), last, now=now))
        finally:
            lease.close(clock())
        async with sessions() as session, session.begin():
            for finding in findings:
                await session.execute(finding_row(one.id, one.connection.connector, finding))
        checked += 1
        changed += any(finding.missing for finding in findings)
    return SchemaRun(checked=checked, changed=changed, cannot_be_read=cannot)


def run_schema_check_now(
    database_url: str,
    *,
    now: datetime,
    vault_address: str,
    vault_token: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> SchemaRun:
    """`check_schemas`, from a thread with no event loop of its own, with the worker's real parts.

    The shape `brain.ops.connector_sync_run.run_connector_sync_now` takes, for its reasons.
    """
    from brain.session import make_app_engine, make_session_factory

    async def go() -> SchemaRun:
        engine = make_app_engine(database_url)
        try:
            return await check_schemas(
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
