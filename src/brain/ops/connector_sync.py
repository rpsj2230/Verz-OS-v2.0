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

- this release has a reading for the source (`READINGS`, read off each connector's own
  `CONNECTOR` declaration at start-up, so a new source is read with no edit here);
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

**What a sync keeps is the source's minimal index and nothing else, and it is checked at the
write.** The owner's rule is that connectors never bulk-sync
(`brain.connectors.declaration.CONNECTORS_NEVER_BULK_SYNC`): ids, names, dates, status and the few
fields a manifest names, with every value read live at question time. `kept_fields` holds each row
to its manifest with `brain.connectors.minimal_index.assert_minimal_index` before the page is
written, so a connector whose code keeps a field its manifest never declared is refused at the
write rather than found in the table. Until 2026-09-28 a reading could also hand each row to the
corpus as a document, embedded into `know.chunk`; that was a bulk sync of bodies, and it was
removed rather than left unfed. See `A_SYNC_KEEPS_NO_BODY`.

**A failure makes the next attempt later and marks the source unhealthy after the third in a row.**
`after_attempt` is the whole rule and `A_FAILING_SOURCE_IS_ASKED_LESS_OFTEN_AND_AT_LEAST_DAILY`
argues it. A quota refusal is not a failure, for `throttle.A_QUOTA_REFUSAL_IS_NOT_ILL_HEALTH`'s
reason, and it waits as long as the source asked.

**Nothing a sync reads is retired by a sync.** A record the source stops returning keeps its last
`last_seen_at` and ages into STALE by `brain.connectors.projection.assess_staleness`, and is served
with its age. See `A_SYNC_RETIRES_NOTHING`, which says why the id sweep the change signals promise
is left for a decision rather than built here.

**A field the source has renamed or removed is found by the scheduled read, shown on its health
and answered as degraded (M11.8.7).** Every scheduled read already fetches each entity's pages, so
it is also the schema check, and every source is read at least once a day
(`A_SCHEDULED_READ_IS_THE_SCHEMA_CHECK_AND_RUNS_AT_LEAST_DAILY`). A field the index keeps is lost
when a record that carried it is read again without it and no record of the read carries it, or
when the newest read before this one had found it lost and this one still finds it on nothing
(`lost_fields`, and `A_FIELD_IS_LOST_WHEN_THE_RECORDS_THAT_CARRIED_IT_NO_LONGER_DO`). A field read
only live, never kept, is not judged here: nothing holds what it used to be. The attempt is still a
read, its health is degraded, and its sentence names each lost field as `entity.field` in the
connector's own names and never a value. `brain.ops.live_records.SourceRecords` then reads that
sentence back with `fields_lost_of` and answers a question over that entity as a source that could
not be read, rather than with records missing the field.

Rejected: a nightly control of its own that reads every source's schema separately. It would spend
a second call per entity on what the scheduled read already fetched, against the same vendor
ceiling, and judge a different page from the one the index was written from.

Rejected: registering a `ConnectorRegistry` from the stored connections and driving `reconnect` on
every run. It would quarantine a connection in memory that the next run rebuilds from the same row,
so the quarantine would last one run, and it would add a second in-memory opinion about whether a
source is connected beside the table that already says so.

Task ids: M42.6.5, M11.9.1, M11.4.1, M27.15.8, M11.8.7
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final

from brain.connectors.contract import ConnectorContractError, HealthState
from brain.connectors.declaration import PageReply as PageReply
from brain.connectors.declaration import SourceReading as SourceReading
from brain.connectors.declaration import ViewReading as ViewReading
from brain.connectors.declaration import shipped
from brain.connectors.manifest import ConnectorManifest, manifest_digest
from brain.connectors.minimal_index import MinimalIndexError, StoredRow, assert_minimal_index
from brain.connectors.projection import MISSED_REFRESHES_BEFORE_STALE, ProjectedRecord
from brain.connectors.throttle import CallOutcome, UnmeasuredSourceError, limits_for, retry_delay
from brain.core.scope import Op, Scope
from brain.ops.connectable import NotConnectableError, manifest_for
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.connector_store import Connection
from brain.ops.limits import Limit

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

#: Why a sync hands nothing to the corpus.
A_SYNC_KEEPS_NO_BODY: Final = (
    "A scheduled read keeps each record's minimal index in proj.record and nothing else. It once "
    "also handed a reading's rows to the corpus as documents, where they were chunked and "
    "embedded: a copy of every body the source held, refreshed on a timer, which is the bulk sync "
    "the owner has ruled out twice. A document from a connected source is found by its indexed "
    "title and id and read live when a question needs it; `docs/needs-rupash.md` item 99 asks the "
    "owner to confirm that for Drive and Wiki bodies, and this is its recommended answer."
)

#: Why a test's row copies the schedule's figures rather than moving them.
A_TEST_LEAVES_THE_SCHEDULE_AS_IT_FOUND_IT: Final = (
    "A test is one call a person asked for, and its row is the source's newest attempt, so the "
    "screen shows what the test found as the source's health. It does not move the schedule: the "
    "failures in a row and the next attempt are copied from the attempt before it, so a test that "
    "fails does not push a failing source further into its backoff and a test that works does not "
    "clear a backoff the scheduled read earned. The one exception is the source's own word: a test "
    "the source refused for volume waits as long as the source asked, as a scheduled read would."
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
#: What a read that found fields lost says, before the fields' names. See `fields_lost_detail`.
FIELDS_LOST: Final = (
    "Read, and these fields the source's tools read were in none of the records it answered, so "
    "it has renamed or removed them:"
)
READ_BUT_CUT_SHORT: Final = (
    "Read as far as one run reads, which was not the end; the next run reads it again from the "
    "start."
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
    "The source declined the key this install holds for it. Replace the key from this source's "
    "Manage menu."
)
#: What a database's refusal leaves, which a key's refusal does not describe: the password, the
#: grant on the views and the views themselves are the database administrator's, and any of them
#: moving is the same refusal to this install (M11.6.1).
DATABASE_REFUSED: Final = (
    "The database refused the read: the user's password, its grant on the views, or a view itself "
    "is no longer what was connected. Its administrator can say which; replace the user from this "
    "source's Manage menu if its password changed."
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
    "The vault holds no key for this source. Replace the key from this source's Manage menu."
)
VAULT_REFUSED: Final = (
    "The vault refused the worker's read of this source's key, or minted a run token wider than a "
    "run may hold. The worker and connector-run policies or the connector-run token role may not "
    "be loaded: ops/openbao/credential-slots.md has the steps."
)
VAULT_UNREACHABLE: Final = "The vault did not answer, so the source's key could not be read."
#: A source whose key file is exchanged for a token, read by a process given no way to post for one.
NO_KEY_FILE_EXCHANGE: Final = (
    "This process was given no way to exchange the source's key file for a token, so the source "
    "was not asked."
)
NOT_READ_YET: Final = "Not read yet. The worker reads it on its next run."

#: The screen's words for an attempt's outcome, by what follows it.
TRIED_AGAIN: Final = "It is tried again after"
FAILED_IN_A_ROW: Final = "Attempts that failed in a row:"

#: What a test of the connection came to, when it is not one of the failures above. Constants, for
#: `A_RUN_RECORD_CARRIES_NO_VALUE_FROM_THE_SOURCE`.
PROBE_ANSWERED: Final = (
    "The source accepted this install's key and answered in the shape this release reads. Nothing "
    "it sent was kept."
)
PROBE_REFUSED_FOR_NOW: Final = (
    "The source said its call allowance is spent for now, so the key could not be tested. Test "
    "again once the source has room."
)
PROBE_NOT_SENT_WHILE_WAITING: Final = (
    "No call was made: the source asked this install to wait before calling it again. Test again "
    "once that wait is over."
)
PROBE_NOT_SENT_SHARE_SPENT: Final = (
    "No call was made: tests have used this install's share of the source's call allowance for "
    "now. Test again later."
)
#: What the screen puts before a test's sentence, so it is not read as a scheduled read.
TESTED_ON_REQUEST: Final = "Tested on request:"


class SyncOutcome(enum.StrEnum):
    """What one attempt came to. Four, and `brain.tables.connector_sync.OUTCOMES` holds them.

    `QUOTA` is its own outcome rather than a kind of failure, for
    `A_QUOTA_REFUSAL_WAITS_AS_LONG_AS_THE_SOURCE_ASKED`. `PROBED` is a test a person asked for,
    for `A_TEST_LEAVES_THE_SCHEDULE_AS_IT_FOUND_IT`; what the test found is its health and its
    sentence, read back by `verdict_of`.
    """

    SYNCED = "synced"
    QUOTA = "quota"
    FAILED = "failed"
    PROBED = "probed"


class ConnectorSyncError(Exception):
    """A reading produced something this store cannot keep. Raised before anything is written."""


INDEX_EXCEEDED: Final = (
    "A record read from this source holds a field its declaration does not name, so nothing from "
    "that answer was kept."
)


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
    #: The sentence of the newest attempt that was a read, which is where a lost field is said and
    #: kept until a later read finds it again. See `fields_lost_of`.
    synced_detail: str = ""


@dataclass(frozen=True)
class Attempt:
    """One finished attempt, as the row `brain.tables.connector_sync` keeps."""

    connector: str
    started_at: datetime
    finished_at: datetime
    outcome: SyncOutcome
    health: HealthState
    records: int
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


def kept_fields(record: ProjectedRecord, manifest: ConnectorManifest) -> dict[str, StoredValue]:
    """`stored_fields` for a record of this manifest, held to its minimal index before it is kept.

    The entity's projection is the manifest's, so a record of an entity the manifest does not
    project is refused, and the fields `stored_fields` lays out are checked by
    `assert_minimal_index`: declared, pointer-shaped, the predicate's value, and no longer than a
    label. A refusal carries `INDEX_EXCEEDED` and never the row, for
    `A_RUN_RECORD_CARRIES_NO_VALUE_FROM_THE_SOURCE`.
    """
    projection = manifest.projection_for(record.entity)
    if projection is None:
        raise ConnectorSyncError(INDEX_EXCEEDED)
    fields = stored_fields(record, projection.visibility)
    row = StoredRow(
        source=record.source, entity=record.entity, source_id=record.source_id, fields=fields
    )
    try:
        assert_minimal_index(manifest, (row,))
    except MinimalIndexError as exceeded:
        raise ConnectorSyncError(INDEX_EXCEEDED) from exceeded
    return fields


# ------------------------------------------------------------------------- the readings


#: Every source this release reads on a schedule, by connector name, read off each connector's
#: `CONNECTOR` declaration at start-up. `PageReply`, `SourceReading` and `ViewReading` are
#: `brain.connectors.declaration`'s, named here for the modules that read them from this one.
READINGS: Final[Mapping[str, SourceReading | ViewReading]] = MappingProxyType(
    {name: one.reading for name, one in shipped().items() if one.reading is not None}
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
    reading: SourceReading | ViewReading | None = None
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
    readings: Mapping[str, SourceReading | ViewReading] = READINGS,
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


#: Why a field is judged lost record by record.
A_FIELD_IS_LOST_WHEN_THE_RECORDS_THAT_CARRIED_IT_NO_LONGER_DO: Final = (
    "A vendor may leave an empty field out of a record rather than send it empty, and the index "
    "keeps records the source has since deleted, so neither a field absent from every record of "
    "one read nor one the index once held is yet a renamed one. What says it was renamed or "
    "removed is a record that carried it, read again without it, while no record of the read "
    "carries it. A "
    "field already found lost stays lost until a read finds it again, because the read that found "
    "it wrote its records without it."
)

#: Why the scheduled read is the nightly schema check.
A_SCHEDULED_READ_IS_THE_SCHEMA_CHECK_AND_RUNS_AT_LEAST_DAILY: Final = (
    "Every shipped reading is read at least once a day, and a failing one is asked at least daily "
    "as well (LONGEST_WAIT_AFTER_FAILURES), so judging each read's records against what it maps "
    "checks every connected source's schema every night without a second call to any vendor."
)

#: The longest interval any reading may declare and still be checked every night.
SCHEMA_CHECKED_AT_LEAST_EVERY: Final = timedelta(days=1)

#: What one lost field is called: the connector's own entity and field names, never a value.
_LOST_NAME: Final = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


def lost_fields(
    entity: str,
    *,
    dropped: Iterable[str],
    carried: Iterable[str],
    seen: Iterable[str],
) -> tuple[str, ...]:
    """The fields of `entity` a read lost, as `entity.field`, in name order.

    `dropped` is every kept field some record of this read carried in the index and does not carry
    now, `carried` the fields of this entity the newest read before this one had found lost, and
    `seen` every field any record of this read carries. See
    `A_FIELD_IS_LOST_WHEN_THE_RECORDS_THAT_CARRIED_IT_NO_LONGER_DO`.
    """
    names = (set(dropped) | set(carried)) - set(seen)
    return tuple(f"{entity}.{one}" for one in sorted(names))


def carried_for(entity: str, lost: Iterable[str]) -> frozenset[str]:
    """The field names of `entity` among `entity.field` names, as `fields_lost_of` reads them."""
    return frozenset(
        field for name in lost for owner, _, field in (name.partition("."),) if owner == entity
    )


def fields_lost_detail(lost: Iterable[str]) -> str:
    """The sentence a read that lost fields leaves, naming each."""
    return f"{FIELDS_LOST} {', '.join(sorted(lost))}."


def fields_lost_of(detail: str) -> frozenset[str]:
    """The fields a read's sentence says it lost, or none for any other sentence.

    The one reader of `fields_lost_detail`'s sentence, as `verdict_of` is for a test's. A name
    that is not `entity.field` makes the whole sentence one this build did not write, which is
    read as saying nothing rather than as a partial list.
    """
    if not detail.startswith(FIELDS_LOST + " ") or not detail.endswith("."):
        return frozenset()
    named = [one.strip() for one in detail[len(FIELDS_LOST) + 1 : -1].split(",")]
    if not named or not all(_LOST_NAME.match(one) for one in named):
        return frozenset()
    return frozenset(named)


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
    cut_short: bool = False,
    drifted: bool = False,
) -> Attempt:
    """The row one attempt leaves: its health, the failures in a row, and when to try again.

    A read that found a field lost (`drifted`) is degraded, as a read cut short is: it was read,
    and what it answers is not all there.

    The whole backoff rule is here and nowhere else. See
    `A_FAILING_SOURCE_IS_ASKED_LESS_OFTEN_AND_AT_LEAST_DAILY`,
    `A_SOURCE_IS_UNHEALTHY_AFTER_THREE_FAILURES_IN_A_ROW` and
    `A_QUOTA_REFUSAL_WAITS_AS_LONG_AS_THE_SOURCE_ASKED`.
    """
    carried = 0 if previous is None else previous.consecutive_failures
    if outcome is SyncOutcome.SYNCED:
        failures = 0
        health = HealthState.DEGRADED if cut_short or drifted else HealthState.OK
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
        consecutive_failures=failures,
        next_attempt_at=finished_at + wait,
        detail=detail,
    )


class ProbeVerdict(enum.StrEnum):
    """What a test found, read back from its sentence. `verdict_of` is the only reader."""

    #: The source took the key and answered in a shape this release reads.
    ANSWERED = "answered"
    #: The source refused for volume; the key is neither proved nor refused.
    WAITING = "waiting"
    #: The call was made, or the key could not be read, and it did not work.
    FAILED = "failed"
    #: No call was made, and the sentence says why.
    NOT_SENT = "not_sent"


#: Every sentence a test that made no call can leave: the plan's refusals, and the two waits.
NOT_SENT_SENTENCES: Final[frozenset[str]] = frozenset(
    {
        NO_READING,
        DECLARATION_CANNOT_BE_REBUILT,
        DECLARATION_NOT_AGREED,
        VISIBILITY_NOT_STORABLE,
        NO_VERIFIED_CEILING,
        PROBE_NOT_SENT_WHILE_WAITING,
        PROBE_NOT_SENT_SHARE_SPENT,
    }
)


def verdict_of(detail: str) -> ProbeVerdict:
    """What a test's row found, from its sentence, which is always one of this module's constants.

    Anything not named as answered, waiting or not sent is a failure, which is the direction to be
    wrong in: a sentence this build does not know is shown as not working rather than as working.
    """
    if detail == PROBE_ANSWERED:
        return ProbeVerdict.ANSWERED
    if detail == PROBE_REFUSED_FOR_NOW:
        return ProbeVerdict.WAITING
    if detail in NOT_SENT_SENTENCES:
        return ProbeVerdict.NOT_SENT
    return ProbeVerdict.FAILED


def after_probe(
    *,
    connector: str,
    started_at: datetime,
    finished_at: datetime,
    detail: str,
    interval: timedelta,
    previous: SyncState | None,
    call: CallOutcome | None = None,
    retry_after_seconds: float | None = None,
) -> Attempt:
    """The row one test leaves: what it found, and the schedule as the attempt before left it.

    See `A_TEST_LEAVES_THE_SCHEDULE_AS_IT_FOUND_IT`. The health of a failure and the length of a
    wait are `after_attempt`'s, asked as though the test were a scheduled read, so there is one rule
    for when a source is down and one for how long a refusal waits. A test that made no call has
    learned nothing about the source and keeps the health it had; with no attempt before it, the
    only way to make no call is a plan that refuses, and a source nothing can read is down.
    """
    failures = 0 if previous is None else previous.consecutive_failures
    carried = finished_at if previous is None else max(previous.next_attempt_at, finished_at)

    def as_read(outcome: SyncOutcome) -> Attempt:
        return after_attempt(
            connector=connector,
            started_at=started_at,
            finished_at=finished_at,
            outcome=outcome,
            detail=detail,
            interval=interval,
            previous=previous,
            call=call,
            retry_after_seconds=retry_after_seconds,
        )

    next_at = carried
    match verdict_of(detail):
        case ProbeVerdict.ANSWERED:
            health = HealthState.OK
        case ProbeVerdict.WAITING:
            waited = as_read(SyncOutcome.QUOTA)
            health, next_at = waited.health, max(carried, waited.next_attempt_at)
        case ProbeVerdict.FAILED:
            health = as_read(SyncOutcome.FAILED).health
        case ProbeVerdict.NOT_SENT:
            health = HealthState.DOWN if previous is None else previous.health
    return Attempt(
        connector=connector,
        started_at=started_at,
        finished_at=finished_at,
        outcome=SyncOutcome.PROBED,
        health=health,
        records=0,
        consecutive_failures=failures,
        next_attempt_at=next_at,
        detail=detail,
    )


def failure_detail(call: CallOutcome, *, timed_out: bool = False) -> str:
    """The sentence a failed call leaves, by what kind of failure it was and nothing else."""
    if timed_out:
        return SOURCE_TIMED_OUT
    if call is CallOutcome.REJECTED:
        return KEY_DECLINED
    return SOURCE_UNREACHABLE


def database_failure_detail(call: CallOutcome) -> str:
    """The sentence a failed read of a database's view leaves. See `DATABASE_REFUSED`."""
    return DATABASE_REFUSED if call is CallOutcome.REJECTED else failure_detail(call)


def sync_in_words(plan: SyncPlan | None, state: SyncState | None) -> str:
    """What the Connectors screen says about reading one source.

    A refused plan says why nothing reads it, whatever an older attempt said, because the refusal is
    what is true now. A source nothing has tried says so rather than drawing a blank.
    """
    if plan is not None and plan.refused:
        return plan.refused
    if state is None:
        return NOT_READ_YET
    if state.outcome is SyncOutcome.PROBED:
        return f"{TESTED_ON_REQUEST} {state.detail}"
    if state.outcome is SyncOutcome.SYNCED:
        return state.detail
    said = f"{state.detail} {TRIED_AGAIN} {state.next_attempt_at.isoformat()}."
    if state.consecutive_failures > 1:
        said = f"{said} {FAILED_IN_A_ROW} {state.consecutive_failures}."
    return said
