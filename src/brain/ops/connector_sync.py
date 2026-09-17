"""Reading a connected source on a schedule: may it be read, what is kept, what a failure costs.

`brain.ops.connector_admin` connects a source from the console and until this module nothing on any
install read one: no worker ran a connector, so a connected source was never synced, projected,
health-checked or answered from, and its key sat in the vault read by nothing. This is the policy
half of the control that reads them. It opens no connection, reads no clock and holds no key;
`brain.ops.connector_sync_run` is the worker's half and `brain.ops.connector_sync_store` the SQL,
for the split CLAUDE.md names: nothing that decides policy owns a client.

**A source is read only when four things already in the repository agree that it may be.**
`plan_for` asks them in order and stops at the first that refuses, and each refusal is a sentence
the Connectors screen shows rather than a source quietly left out:

- this release has a reading for the source (`READINGS`);
- the manifest its stored settings build today is the one agreed to at connect, which is
  `brain.connectors.registry.reconnect`'s pin applied to a scheduled read: a release that changed
  what a connector declares waits for a person, it is not read under a declaration nobody accepted;
- every entity it projects keeps a visibility predicate this store can carry (see below);
- `brain.connectors.throttle.limits_for` finds a verified ceiling, which it refuses to invent. That
  is why HubSpot is not read today: `hubspot.A_CEILING_NOBODY_VERIFIED_IS_NOT_A_CEILING`.

**The source's visibility travels on the record as fields, because that is the only place the row
plane can evaluate it.** `brain.tables.projection` has no visibility column, and argues why: the
predicate is the manifest's. But nothing evaluates a manifest at read time; `brain.knowledge.rows`
compiles the *reader's* grant scope into the WHERE clause, over the record's stored fields, and the
redactor tests the same scope against the record it is handed. A record that does not carry the
field a scope tests satisfies neither, so nobody reaches it, which `brain.demo.
A_RECORD_NO_SCOPE_CAN_MATCH_IS_A_RECORD_NOBODY_REACHES` measured on the seeded company. So each
equality clause of the source's predicate (Xero's tenant, HubSpot's portal) is laid over the
projected fields, and a grant scoped to that tenant reaches the row while a grant scoped to a
department does not. See `THE_SOURCE_S_VISIBILITY_IS_STORED_AS_THE_FIELDS_ITS_PREDICATE_TESTS`. Only
an equality can be stored this way: a prefix or a set is a predicate over many values and a row
holds one, so a manifest declaring one is not read at all rather than read into rows no predicate
can reach.

**A document is handed to the corpus with the owner and the visibility its reading gave it, and the
owner's reach decides whether it is indexed.** `brain.knowledge.chunk_store.ingest_document`
resolves the owner's grants and refuses a document its owner cannot reach; a refusal here withholds
that one document and says so in one sentence with no count. Neither console-connectable source
produces documents, so no install exercises this leg today: see
`NO_CONNECTABLE_SOURCE_YIELDS_A_DOCUMENT`.

**A failure makes the next attempt later and marks the source unhealthy after the third in a row.**
`after_attempt` is the whole rule and `A_FAILING_SOURCE_IS_ASKED_LESS_OFTEN_AND_AT_LEAST_DAILY`
argues it. A quota refusal is not a failure, for `throttle.A_QUOTA_REFUSAL_IS_NOT_ILL_HEALTH`'s
reason, and it waits as long as the source asked.

**Nothing a sync reads is retired by a sync.** A record the source stops returning keeps its last
`last_seen_at` and ages into STALE by `brain.connectors.projection.assess_staleness`, and is served
with its age. See `A_SYNC_RETIRES_NOTHING`, which says why the id sweep the change signals promise
is left for a decision rather than built here.

Rejected: registering a `ConnectorRegistry` from the stored connections and driving `reconnect` on
every run. It would quarantine a connection in memory that the next run rebuilds from the same row,
so the quarantine would last one run, and it would add a second in-memory opinion about whether a
source is connected beside the table that already says so.

Task ids: M42.6.5
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, Protocol

from brain.connectors import hubspot, xero
from brain.connectors.contract import ConnectorContractError, HealthState
from brain.connectors.manifest import ConnectorManifest, manifest_digest
from brain.connectors.projection import MISSED_REFRESHES_BEFORE_STALE, ProjectedRecord
from brain.connectors.rest import RestOperation
from brain.connectors.throttle import CallOutcome, UnmeasuredSourceError, limits_for, retry_delay
from brain.connectors.transports import SourceRecord
from brain.core.envelope import TypedResult
from brain.core.scope import Op, Scope
from brain.knowledge.item import KnowledgeItem
from brain.ops.connectable import NotConnectableError, manifest_for
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.connector_store import Connection
from brain.ops.limits import Limit
from brain.tools.fetch import Resolver

# ------------------------------------------------------------------ written-down reasons

#: Why the predicate's fields are written onto the record.
THE_SOURCE_S_VISIBILITY_IS_STORED_AS_THE_FIELDS_ITS_PREDICATE_TESTS: Final = (
    "The row plane compiles a reader's grant scope into the WHERE clause over proj.record's stored "
    "fields, and the redactor evaluates the same scope against the record it builds. Nothing reads "
    "the manifest's predicate when a row is read. So the only way a source's own rule narrows who "
    "reaches its rows is for each row to carry the field the rule tests, with the value the rule "
    "names: a grant scoped to that value then reaches the row, a grant scoped to anything else "
    "does not, and no grant reaches it by the field being absent. A projected field that already "
    "holds a different value under that name is refused rather than overwritten, because one field "
    "with two values is two answers to who may read the row."
)

#: Why a failing source is not retried on every run, and why it is still retried.
A_FAILING_SOURCE_IS_ASKED_LESS_OFTEN_AND_AT_LEAST_DAILY: Final = (
    "A source that failed is asked again after its own refresh interval, then after twice that, "
    "and so on, doubling per failure in a row, and never later than a day. Retrying on every run "
    "turns an expired key into a call spent every few minutes on a refusal already known, against "
    "an allowance the client shares with every other integration. Never retrying, or retrying "
    "weekly, means a key replaced in the source's own settings is not noticed working for a week. "
    "A day is the longest a person fixing a source should wait to see it read."
)

#: Why the health word turns to down at the third failure and not the first.
A_SOURCE_IS_UNHEALTHY_AFTER_THREE_FAILURES_IN_A_ROW: Final = (
    "One failed read is a network that dropped a connection, two can be a coincidence, and three "
    "in a row is the source or its key not working. The number is "
    "brain.connectors.projection.MISSED_REFRESHES_BEFORE_STALE, reached by the same argument about "
    "the same pipeline, so the projection turns stale and the source turns down at the same point. "
    "A refused authorisation is down at once, because a retry reproduces it exactly."
)

#: Why a quota refusal carries the failure count over rather than adding to it.
A_QUOTA_REFUSAL_WAITS_AS_LONG_AS_THE_SOURCE_ASKED: Final = (
    "A 429 is the source's allowance working, not the source failing, and counting it would mark "
    "the busiest source unhealthy for being asked. It waits for the longer of what the platform's "
    "backoff computes and what the source said, and it neither clears nor adds to the failures in "
    "a row."
)

#: Why nothing from the source can reach a run's record.
A_RUN_RECORD_CARRIES_NO_VALUE_FROM_THE_SOURCE: Final = (
    "A run's record is read on the Connectors screen by whoever may see the connection, which is a "
    "different audience and a different retention from the rows the run wrote. Its detail is one "
    "of this module's constant sentences, chosen by what kind of thing happened, and never a "
    "response body, an exception's message, a setting or a filter value, which could carry a "
    "client's name or the key itself."
)

#: Why a sync retires nothing.
A_SYNC_RETIRES_NOTHING: Final = (
    "A record the source stops returning could be retired by an id sweep over a complete pass, and "
    "that is what the change signals promise. It is not done here because retiring a projected row "
    "is final: 0045's update policy never touches a retired row again, so a record retired by a "
    "sweep that was wrong (a page the source skipped, a filter it changed) could never be written "
    "back by the next sync, and would be absent from every answer for good. So a record that is "
    "not seen again keeps its last reading and ages, and brain.connectors.projection serves it "
    "with its age. Retiring belongs with whoever decides what a missed record means, with a report "
    "first, as brain.ops.schedule does for the retention sweep."
)

#: Why the document leg exists with nothing to feed it today.
NO_CONNECTABLE_SOURCE_YIELDS_A_DOCUMENT: Final = (
    "Xero and HubSpot, the two sources the console can connect, keep records and no documents. The "
    "sources whose items are documents, Lark Wiki and Google Drive, are connected with a steward "
    "and a department declaration the console cannot collect, and brain.ops.connectable says so "
    "for each. The leg is in the one loop every reading goes through so that the day one of them "
    "is connectable its documents reach the corpus through the owner's reach, rather than through "
    "a second loop written for documents that nobody holds against the first."
)

# -------------------------------------------------------------------------- the numbers

#: Failures in a row after which a source is down. See
#: `A_SOURCE_IS_UNHEALTHY_AFTER_THREE_FAILURES_IN_A_ROW`.
UNHEALTHY_AFTER_FAILURES: Final = MISSED_REFRESHES_BEFORE_STALE

#: The longest a failing source waits before it is asked again.
LONGEST_WAIT_AFTER_FAILURES: Final = timedelta(days=1)

#: How often the control runs. A third of the shortest interval any source this release reads
#: promises (HubSpot's quarter-hourly cursor), so a source due a read is late by at most a third of
#: its own promise, and the tick never equals an interval, which is `brain.ops.schedule.TICK`'s
#: reason about a cadence that would start a control every other tick.
CONTROL_EVERY: Final = timedelta(minutes=5)

#: How many pages of one entity one run reads. A pass that reaches it stops, keeps what it read and
#: says it was cut short; the next run reads from the start again. Fifty pages of a hundred records
#: is five thousand invoices, and against Xero's day it is a hundredth of the allowance per pass.
MAX_PAGES_PER_ENTITY: Final = 50

#: How long one run may wait, in total, for its own share of a source's minute to have room before
#: it stops that source for this run. Well inside `brain.ops.schedule_runner.STALLED_AFTER`.
MAX_SECONDS_WAITING_IN_A_RUN: Final = 120.0

#: The principal a scheduled read is counted against in `brain.ops.limits`. Not a person and not a
#: row in `auth.principal`: it is the subject of a window, so the worker's reads take their fair
#: share of a source's minute and leave the rest for questions.
SYNC_PRINCIPAL: Final = "worker.connector_sync"

# ------------------------------------------------------------------------ the sentences

#: Why a connected source is not read, one per check in `plan_for`.
NO_READING: Final = "Nothing reads this source: this release has no scheduled reading for it."
DECLARATION_CANNOT_BE_REBUILT: Final = (
    "Nothing reads this source: this release cannot rebuild what it was connected as. Disconnect "
    "it and connect it again."
)
DECLARATION_NOT_AGREED: Final = (
    "Nothing reads this source: what it declares today is not what was agreed to when it was "
    "connected, so it is not read until somebody connects it again and agrees to the new "
    "declaration."
)
VISIBILITY_NOT_STORABLE: Final = (
    "Nothing reads this source: its visibility rule is not one a stored record can carry, so a "
    "record read from it could be reached by no grant."
)
NO_VERIFIED_CEILING: Final = (
    "Nothing reads this source: no verified call ceiling is recorded for it, and it is not read "
    "against a ceiling nobody measured."
)

#: What an attempt came to, one per kind of thing that happened. Constants, for
#: `A_RUN_RECORD_CARRIES_NO_VALUE_FROM_THE_SOURCE`.
READ_TO_THE_END: Final = "Read to the end."
READ_BUT_CUT_SHORT: Final = (
    "Read as far as one run reads, which was not the end; the next run reads it again from the "
    "start."
)
DOCUMENTS_WITHHELD: Final = (
    "Read to the end. One or more documents were not indexed, because the person answerable for "
    "them reaches no part of the document plane."
)
SOURCE_ALLOWANCE_REFUSED: Final = (
    "The source's call allowance refused the read. It is tried again once the source said it would "
    "have room."
)
OWN_SHARE_SPENT: Final = (
    "This install's share of the source's call allowance ran out during the read. It is read again "
    "on a later run."
)
SOURCE_UNREACHABLE: Final = "The source did not answer."
SOURCE_TIMED_OUT: Final = "The source did not answer in time."
KEY_DECLINED: Final = (
    "The source declined the key this install holds for it. Replace the key by disconnecting the "
    "source and connecting it again."
)
SHAPE_DISAGREED: Final = (
    "The source answered in a shape its declaration does not describe, so nothing from that answer "
    "was kept."
)
ADDRESS_REFUSED: Final = (
    "The source's address resolved inside this network, so nothing was sent to it."
)
NO_VAULT: Final = (
    "The worker has no secrets vault, so the source's key could not be read. Set "
    "BRAIN_VAULT_ADDRESS and BRAIN_VAULT_TOKEN in the worker's environment, with a token minted "
    "against the worker policy, and restart the worker."
)
NO_KEY: Final = (
    "The vault holds no key for this source. Disconnect it and connect it again with its key."
)
VAULT_REFUSED: Final = (
    "The vault refused the worker's read of this source's key, or minted a run token wider than a "
    "run may hold. The worker and connector-run policies or the connector-run token role may not "
    "be loaded: ops/openbao/credential-slots.md has the steps."
)
VAULT_UNREACHABLE: Final = "The vault did not answer, so the source's key could not be read."
NOT_READ_YET: Final = "Not read yet. The worker reads it on its next run."

#: The screen's words for an attempt's outcome, by what follows it.
TRIED_AGAIN: Final = "It is tried again after"
FAILED_IN_A_ROW: Final = "Attempts that failed in a row:"


class SyncOutcome(enum.StrEnum):
    """What one attempt came to. Three, and `brain.tables.connector_sync.OUTCOMES` holds them.

    `QUOTA` is its own outcome rather than a kind of failure, for
    `A_QUOTA_REFUSAL_WAITS_AS_LONG_AS_THE_SOURCE_ASKED`.
    """

    SYNCED = "synced"
    QUOTA = "quota"
    FAILED = "failed"


class ConnectorSyncError(Exception):
    """A reading produced something this store cannot keep. Raised before anything is written."""


# ------------------------------------------------------------------------- what is kept


@dataclass(frozen=True)
class SyncState:
    """What a connection's last attempt left behind, as the next run and the screen read it."""

    connector: str
    finished_at: datetime
    outcome: SyncOutcome
    health: HealthState
    consecutive_failures: int
    next_attempt_at: datetime
    detail: str
    #: When the source was last read to the end, which may be long before this attempt.
    last_synced_at: datetime | None


@dataclass(frozen=True)
class Attempt:
    """One finished attempt, as the row `brain.tables.connector_sync` keeps."""

    connector: str
    started_at: datetime
    finished_at: datetime
    outcome: SyncOutcome
    health: HealthState
    records: int
    documents: int
    consecutive_failures: int
    next_attempt_at: datetime
    detail: str
    #: How the attempt's vault lease ended. Set by `brain.ops.connector_sync_run.attempt`, which
    #: holds the lease; this module decides nothing about it. See `brain.ops.connector_lease`.
    lease: LeaseOutcome = LeaseOutcome.NONE


#: A value `proj.record.fields` can hold as JSON.
StoredValue = str | int | float | bool | None


def storable_predicate(visibility: Scope) -> bool:
    """Whether every clause of a source's predicate is an equality a record can carry.

    See `THE_SOURCE_S_VISIBILITY_IS_STORED_AS_THE_FIELDS_ITS_PREDICATE_TESTS`. An unrestricted
    predicate is not storable either: `ProjectedEntity` already refuses one, and a record carrying
    no visibility field is a record the demo measured nobody reaching.
    """
    return bool(visibility.clauses) and all(
        clause.op is Op.EQ and isinstance(clause.value, str) for clause in visibility.clauses
    )


def stored_fields(record: ProjectedRecord, visibility: Scope) -> dict[str, StoredValue]:
    """What `proj.record.fields` holds for one record: its projected fields and its predicate's.

    Built through `ProjectedRecord` a second time, over the whole set, because the table's cap
    counts every key and the constructor is where the cap is enforced: the projected fields plus
    the predicate's must still be twelve or fewer. A timestamp is written as ISO 8601 with its zone,
    which is how `brain.connectors.projection.assess_staleness` and a reader both parse it back.
    """
    if not storable_predicate(visibility):
        raise ConnectorSyncError(VISIBILITY_NOT_STORABLE)
    placed = {clause.field: str(clause.value) for clause in visibility.clauses}
    clashing = sorted(
        name
        for name, value in placed.items()
        if name in record.fields and record.fields[name] != value
    )
    if clashing:
        msg = (
            f"{record.source}.{record.entity} {record.source_id} holds {clashing} with a value its "
            f"source's visibility rule does not name. "
            f"{THE_SOURCE_S_VISIBILITY_IS_STORED_AS_THE_FIELDS_ITS_PREDICATE_TESTS}"
        )
        raise ConnectorSyncError(msg)
    whole = ProjectedRecord(
        source=record.source,
        entity=record.entity,
        source_id=record.source_id,
        last_seen_at=record.last_seen_at,
        fields={**record.fields, **placed},
    )
    return {
        name: value.isoformat() if isinstance(value, datetime) else value
        for name, value in sorted(whole.fields.items())
    }


# ------------------------------------------------------------------------- the readings


@dataclass(frozen=True)
class PageReply:
    """One page, as the connector's own `interpret` read it: the call's outcome and any rows."""

    call: CallOutcome
    rows: TypedResult[SourceRecord] | None


class SourceReading(Protocol):
    """How the worker reads one source page by page. One per connector this release reads.

    Everything a reading does is a connector's own function called with the right arguments: the
    operation, the paging parameters, the one header a connection contributes, the interpretation
    of a response and the projection of a row. A reading decides nothing about who may see a row,
    which is the manifest's predicate and the reader's grant, and holds no key.
    """

    def entities(self) -> tuple[str, ...]:
        """Every entity kind the source projects, in the order a run reads them."""
        ...

    def refresh_interval(self) -> timedelta:
        """How often a healthy source is read, which is the interval its freshness is judged by."""
        ...

    def operation(self, entity: str, *, resolver: Resolver) -> RestOperation:
        """The bound operation that lists one entity kind."""
        ...

    def first_page(self, entity: str) -> Mapping[str, str]:
        """The arguments of the first page of one entity kind."""
        ...

    def next_page(
        self, entity: str, asked: Mapping[str, str], body: Any, returned: int
    ) -> Mapping[str, str] | None:
        """The arguments of the page after this one, or None when this was the last."""
        ...

    def call_headers(self, settings: Mapping[str, str]) -> Mapping[str, str]:
        """The headers the connection contributes to a call. Never `Authorization`."""
        ...

    def interpret(
        self, operation: RestOperation, *, status: int, body: Any, fetched_at: str
    ) -> PageReply:
        """One answered call, as the connector's own `interpret` classifies it."""
        ...

    def retry_after(self, headers: Mapping[str, str]) -> float | None:
        """What the source asked to wait, or None when it said nothing."""
        ...

    def allowance_spent(self, headers: Mapping[str, str]) -> bool:
        """Whether the source said its allowance is spent, on an answer that was not a refusal."""
        ...

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        """The record kept for one row, or None for a row with nothing to keep."""
        ...

    def document(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> KnowledgeItem | None:
        """The document one row is, with its owner and visibility, or None for a row that is not."""
        ...


def _reply(outcome: CallOutcome, rows: TypedResult[SourceRecord] | None) -> PageReply:
    return PageReply(call=outcome, rows=rows)


#: Xero's page size, fixed by the vendor. A page holding fewer is the last.
XERO_PAGE_SIZE: Final = 100


class XeroReading:
    """Xero's invoices and contacts, a page at a time, as `brain.connectors.xero` reads them."""

    def entities(self) -> tuple[str, ...]:
        return (xero.ENTITY_INVOICE, xero.ENTITY_CONTACT)

    def refresh_interval(self) -> timedelta:
        return xero.RECONCILIATION_INTERVAL

    def operation(self, entity: str, *, resolver: Resolver) -> RestOperation:
        return xero.operation_for(entity, resolver=resolver)

    def first_page(self, entity: str) -> Mapping[str, str]:
        del entity
        return MappingProxyType({"page": "1"})

    def next_page(
        self, entity: str, asked: Mapping[str, str], body: Any, returned: int
    ) -> Mapping[str, str] | None:
        del entity, body
        if returned < XERO_PAGE_SIZE:
            return None
        return MappingProxyType({**asked, "page": str(int(asked["page"]) + 1)})

    def call_headers(self, settings: Mapping[str, str]) -> Mapping[str, str]:
        return xero.XeroConnection(tenant_id=settings["tenant_id"]).call_headers()

    def interpret(
        self, operation: RestOperation, *, status: int, body: Any, fetched_at: str
    ) -> PageReply:
        reply = xero.interpret(operation, status=status, body=body, fetched_at=fetched_at)
        return _reply(reply.call, reply.rows)

    def retry_after(self, headers: Mapping[str, str]) -> float | None:
        return xero.retry_after(headers)

    def allowance_spent(self, headers: Mapping[str, str]) -> bool:
        return xero.day_remaining(headers) == 0

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        return xero.projected_record(entity, row, last_seen_at=seen_at)

    def document(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> KnowledgeItem | None:
        del entity, row, seen_at
        return None


class HubSpotReading:
    """HubSpot's clients, contacts and deals, cursor by cursor, as its connector reads them.

    Not read on any install today, because `plan_for` stops at the missing verified ceiling. It is
    here so the day the ceiling is recorded the source is read with no other change, which is the
    edit `hubspot.A_CEILING_NOBODY_VERIFIED_IS_NOT_A_CEILING` says should be the only one.
    """

    def entities(self) -> tuple[str, ...]:
        return tuple(sorted(hubspot.PROJECTED_FIELDS))

    def refresh_interval(self) -> timedelta:
        return hubspot.CURSOR_POLL_INTERVAL

    def operation(self, entity: str, *, resolver: Resolver) -> RestOperation:
        return hubspot.operation_for(entity, resolver=resolver)

    def first_page(self, entity: str) -> Mapping[str, str]:
        return MappingProxyType(dict(hubspot.default_arguments(entity)))

    def next_page(
        self, entity: str, asked: Mapping[str, str], body: Any, returned: int
    ) -> Mapping[str, str] | None:
        del entity, returned
        paging = body.get("paging") if isinstance(body, Mapping) else None
        following = paging.get("next") if isinstance(paging, Mapping) else None
        cursor = following.get("after") if isinstance(following, Mapping) else None
        if not isinstance(cursor, str) or not cursor.strip():
            return None
        return MappingProxyType({**asked, hubspot.CURSOR_PARAMETER: cursor})

    def call_headers(self, settings: Mapping[str, str]) -> Mapping[str, str]:
        # Built for its refusal of a portal that narrows nothing; it contributes no header.
        hubspot.HubSpotConnection(portal_id=settings["portal_id"])
        return MappingProxyType({})

    def interpret(
        self, operation: RestOperation, *, status: int, body: Any, fetched_at: str
    ) -> PageReply:
        reply = hubspot.interpret(operation, status=status, body=body, fetched_at=fetched_at)
        return _reply(reply.call, reply.rows)

    def retry_after(self, headers: Mapping[str, str]) -> float | None:
        return hubspot.retry_after(headers)

    def allowance_spent(self, headers: Mapping[str, str]) -> bool:
        del headers
        return False

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        return hubspot.projected_record(entity, row, last_seen_at=seen_at)

    def document(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> KnowledgeItem | None:
        del entity, row, seen_at
        return None


#: Every source this release reads on a schedule, by connector name.
READINGS: Final[Mapping[str, SourceReading]] = MappingProxyType(
    {xero.CONNECTOR_NAME: XeroReading(), hubspot.CONNECTOR_NAME: HubSpotReading()}
)


# ---------------------------------------------------------------------------- the plan


@dataclass(frozen=True)
class SyncPlan:
    """Whether one connection may be read, and everything a read needs when it may.

    `refused` is empty exactly when `manifest` and `reading` are set, and the constructor holds
    that, so a plan cannot say it may run while missing what running needs.
    """

    connector: str
    refused: str = ""
    manifest: ConnectorManifest | None = None
    reading: SourceReading | None = None
    limits: tuple[Limit, ...] = ()
    #: Whether its next attempt is owed now. False for a refused plan.
    due: bool = False

    def __post_init__(self) -> None:
        runnable = self.manifest is not None and self.reading is not None
        if runnable == bool(self.refused):
            msg = (
                f"a plan for {self.connector!r} must either say why it cannot run or carry what "
                "running needs, and this one does both or neither"
            )
            raise ConnectorSyncError(msg)
        if self.due and not runnable:
            msg = f"a refused plan for {self.connector!r} cannot be due"
            raise ConnectorSyncError(msg)


def plan_for(
    connection: Connection,
    *,
    last: SyncState | None,
    now: datetime,
    readings: Mapping[str, SourceReading] = READINGS,
) -> SyncPlan:
    """Whether this connection may be read now, asked in the order the module docstring gives."""
    name = connection.connector
    reading = readings.get(name)
    if reading is None:
        return SyncPlan(connector=name, refused=NO_READING)
    try:
        manifest = manifest_for(name, connection.settings)
    except (NotConnectableError, ConnectorContractError):
        return SyncPlan(connector=name, refused=DECLARATION_CANNOT_BE_REBUILT)
    if manifest_digest(manifest) != connection.digest:
        return SyncPlan(connector=name, refused=DECLARATION_NOT_AGREED)
    if not all(storable_predicate(one.visibility) for one in manifest.projections):
        return SyncPlan(connector=name, refused=VISIBILITY_NOT_STORABLE)
    try:
        limits = limits_for(manifest, principal_id=SYNC_PRINCIPAL)
    except UnmeasuredSourceError:
        return SyncPlan(connector=name, refused=NO_VERIFIED_CEILING)
    return SyncPlan(
        connector=name,
        manifest=manifest,
        reading=reading,
        limits=limits,
        due=last is None or now >= last.next_attempt_at,
    )


# ----------------------------------------------------------------- what an attempt costs


def after_attempt(
    *,
    connector: str,
    started_at: datetime,
    finished_at: datetime,
    outcome: SyncOutcome,
    detail: str,
    interval: timedelta,
    previous: SyncState | None,
    call: CallOutcome | None = None,
    retry_after_seconds: float | None = None,
    records: int = 0,
    documents: int = 0,
    cut_short: bool = False,
) -> Attempt:
    """The row one attempt leaves: its health, the failures in a row, and when to try again.

    The whole backoff rule is here and nowhere else. See
    `A_FAILING_SOURCE_IS_ASKED_LESS_OFTEN_AND_AT_LEAST_DAILY`,
    `A_SOURCE_IS_UNHEALTHY_AFTER_THREE_FAILURES_IN_A_ROW` and
    `A_QUOTA_REFUSAL_WAITS_AS_LONG_AS_THE_SOURCE_ASKED`.
    """
    carried = 0 if previous is None else previous.consecutive_failures
    if outcome is SyncOutcome.SYNCED:
        failures = 0
        health = HealthState.DEGRADED if cut_short else HealthState.OK
        wait = interval
    elif outcome is SyncOutcome.QUOTA:
        failures = carried
        health = HealthState.DEGRADED
        stated = 0.0 if retry_after_seconds is None else retry_after_seconds
        waited = retry_delay(retry_after_seconds=retry_after_seconds, consecutive_refusals=0)
        wait = timedelta(seconds=max(waited, stated))
    else:
        failures = carried + 1
        down = failures >= UNHEALTHY_AFTER_FAILURES or call is CallOutcome.REJECTED
        health = HealthState.DOWN if down else HealthState.DEGRADED
        # The exponent stops growing long after the cap binds, so a source failing for a year
        # cannot overflow the arithmetic that says to wait a day.
        wait = min(interval * 2 ** min(failures - 1, 16), LONGEST_WAIT_AFTER_FAILURES)
    return Attempt(
        connector=connector,
        started_at=started_at,
        finished_at=finished_at,
        outcome=outcome,
        health=health,
        records=records,
        documents=documents,
        consecutive_failures=failures,
        next_attempt_at=finished_at + wait,
        detail=detail,
    )


def failure_detail(call: CallOutcome, *, timed_out: bool = False) -> str:
    """The sentence a failed call leaves, by what kind of failure it was and nothing else."""
    if timed_out:
        return SOURCE_TIMED_OUT
    if call is CallOutcome.REJECTED:
        return KEY_DECLINED
    return SOURCE_UNREACHABLE


def sync_in_words(plan: SyncPlan | None, state: SyncState | None) -> str:
    """What the Connectors screen says about reading one source.

    A refused plan says why nothing reads it, whatever an older attempt said, because the refusal is
    what is true now. A source nothing has tried says so rather than drawing a blank.
    """
    if plan is not None and plan.refused:
        return plan.refused
    if state is None:
        return NOT_READ_YET
    if state.outcome is SyncOutcome.SYNCED:
        return state.detail
    said = f"{state.detail} {TRIED_AGAIN} {state.next_attempt_at.isoformat()}."
    if state.consecutive_failures > 1:
        said = f"{said} {FAILED_IN_A_ROW} {state.consecutive_failures}."
    return said
