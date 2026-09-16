"""The retention executor for PostgreSQL: count what is past its window, remove what may go, and
write the report down.

`brain.ops.retention` decides every horizon and builds the report, and its `StoreSweeper` has
been a protocol nothing implemented. This implements it for the stores that live in PostgreSQL,
and it decides nothing that module decides: the window is `horizon_of(store)`, the report is
`enforcement_report`, and `retention.sweep` is what calls this.

**A store is reached only when it can be counted honestly, and every other store is named with
the reason.** That is `A_SWEEP_THAT_SKIPS_A_STORE_KEEPS_IT_FOREVER` applied to the executor
rather than to the report. Four cases, and only the first two are reached today:

*A fixed window* is counted by a declared clock column on every table the store holds. A table
with no declared clock refuses the store rather than being skipped, because a table skipped is a
table kept forever.

*A class that never expires* is reached with nothing due, because that is what its lifetime
says rather than what a count found, and its oldest row is still reported where a clock is
declared, so an audit chain that has stopped growing is visible as an age.

*A record lifetime* is refused. `StoreCensus` says a record-lifetime store's figure is the rows
whose subject record is gone, and which record a row is about is a per-table fact nothing in
this repository declares. Counting soft-deleted rows instead would be a plausible answer and a
wrong one: `brain.db.SoftDeleteMixin` retires rows so the trail survives, and a sweep treating
retirement as expiry would be deleting what that mixin exists to keep. See
`A_RECORD_LIFETIME_NEEDS_A_SUBJECT_REFERENCE_NOBODY_HAS_DECLARED`.

*A store outside PostgreSQL* is refused: recordings, attachments, exports and backups are in the
object store, and the cache and the index are not tables. **There is no object-store sweeper**,
because `brain.ops.storage.StorageBackend` is a protocol with no implementation anywhere here,
and its `list_objects` returns keys with no age, so even an implementation of it could not
count by window. The bucket lifecycle rules `brain.ops.storage.BUCKETS` declare are what expire
those objects today, and nothing here verifies that they do.

**What is due is removed only where the table lets this role remove it, and the rest is queued
with the rule that removes it.** Nothing in this system hard-deletes a row whose table says it
leaves another way, and the table says so in two places the catalogue can be asked about. A
partitioned table leaves a partition at a time: `obs.request_telemetry` is the metadata ledger
and `0039` argues that it is pruned by detaching and dropping partitions, never by DELETE. And a
table whose migration grants the application role no DELETE has argued, in that migration, for
how its rows go; every table at head is one. So `removal_rule` reads both from the catalogue and a
row in either kind of table is counted as queued, reported with the rule, and not touched. See
`brain.ops.retention.A_SWEEP_REMOVES_ONLY_WHAT_ITS_TABLE_LETS_IT_AND_QUEUES_THE_REST`. The
privilege is asked of the application role by name rather than of whoever is connected, because
the worker may connect as a role that owns the tables and an owner's privileges are not the rule.

**Which store a table belongs to is read from the catalogue, and a shared schema needs an
attribution.** Every schema but `obs` is claimed by one store, so every table in it is that
store's, including one added next year. `obs` is claimed by four stores with four lifetimes, so
a table there has to be attributed in `ATTRIBUTED`, and an unattributed one refuses every store
sharing the schema. **`obs.request_telemetry` arrived in `0039` without one**, which is the case
this rule was written for: from that migration until this change every run reported the ledger,
trace, payload and audit stores as not reached. It is attributed to the ledger now, and
`obs.legal_hold` to the audit store it explains. See
`A_TABLE_IN_A_SHARED_SCHEMA_BELONGS_TO_NOBODY_UNTIL_IT_IS_ATTRIBUTED`.

**A legal hold is read from `obs.legal_hold` inside the run's own transaction, and fails
closed.** Rows under an active hold are counted as held and never removed. A hold naming
subjects, over a table with no declared subject column, refuses the store: which rows it covers
cannot be told, and removing some of them to find out is not available. See
`A_HOLD_THIS_CANNOT_MATCH_TO_A_ROW_STOPS_THE_SWEEP`. A run that cannot read the holds table
raises and removes nothing, because a hold it cannot see is a hold that does not hold.

**Every run writes its report to `ops.retention_report`, including a run that raised.** The run
record's detail column holds two thousand characters, which a report over seventeen stores does
not fit in. A run that raised is rolled back, so it removed nothing, and a report saying exactly
that is written in a transaction of its own before the exception carries on to the run record.
See `A_RUN_THAT_RAISED_IS_A_REPORT_TOO`.

**The sweep acts only after a person released it, and the release names the report they read.**
`brain.ops.schedule.DESTRUCTIVE` keeps the sweep in report-only mode until the installation
releases it, and until now nothing could. `release_sweep` writes the record, and refuses unless
the report it names is the newest one, was produced in report-only mode and did not fail, so a
release is always a decision about what the sweep said it would do. `released_controls` is what
the worker's tick reads. See `A_RELEASE_IS_A_DECISION_ABOUT_THE_NEWEST_REPORT`.

What this finds on a database migrated to head, reasoned from the migrations rather than
measured, because no server was reachable where this was written: the ledger store is reached
and whatever is past five years in `obs.request_telemetry` is queued for partition removal; the
trace and payload stores are reached with nothing due, because no table holds those classes;
the audit store is reached with nothing due; every other store is refused by name.

Rejected: a sync of each table's retention into a policy table the sweeper reads. It is a
second declaration of the windows `brain.ops.retention` already declares, and the copy nobody
reads is the one that gets raised.

Task ids: M25.1.5
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, assert_never, cast

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from brain.audit.ledger import LegalHold
from brain.ops.erasure import Hold
from brain.ops.retention import (
    STORES,
    CitedHold,
    Lifetime,
    RetentionError,
    RetentionReport,
    Store,
    StoreCensus,
    SweptStore,
    enforcement_report,
    facts_for,
    horizon_of,
    sweep,
)
from brain.session import APPLICATION_ROLE
from brain.tables.retention import (
    FAILURE_CHARS,
    LegalHoldRow,
    RetentionReleaseRow,
    RetentionReportRow,
)

# ------------------------------------------------------------------ written-down reasons
#: Why a record-lifetime store is not reached.
A_RECORD_LIFETIME_NEEDS_A_SUBJECT_REFERENCE_NOBODY_HAS_DECLARED: Final = (
    "a record-lifetime store has nothing past its horizon until the record a row describes is "
    "gone, and which record each of its tables describes is not declared anywhere; counting "
    "soft-deleted rows instead would treat a retirement, which exists to keep the trail, as an "
    "expiry, so the store is not counted and nothing in it is removed"
)

#: Why a store outside PostgreSQL is not reached by this executor.
NOT_HELD_IN_POSTGRES: Final = (
    "it is not held in PostgreSQL, and there is no object-store or cache executor: "
    "brain.ops.storage.StorageBackend has no implementation and lists keys with no age"
)

#: Why an unattributed table in a shared schema stops the sweep for that schema.
A_TABLE_IN_A_SHARED_SCHEMA_BELONGS_TO_NOBODY_UNTIL_IT_IS_ATTRIBUTED: Final = (
    "several stores with different windows share this schema, so a table in it is governed by "
    "whichever store it is attributed to, and a table attributed to none would be swept on "
    "somebody's window by guesswork or not swept at all"
)

#: Why a hold that cannot be matched to rows refuses the store.
A_HOLD_THIS_CANNOT_MATCH_TO_A_ROW_STOPS_THE_SWEEP: Final = (
    "an active legal hold names subjects and this table declares no column saying whose a row "
    "is, so which of its rows the hold covers cannot be told; removing rows past the window "
    "would remove held ones with them"
)

#: The rule a partitioned table's rows leave by.
A_PARTITIONED_TABLE_LEAVES_A_PARTITION_AT_A_TIME: Final = (
    "the table is partitioned, and its rows leave when their partition is detached and dropped "
    "(brain.ops.partitioning), never one row at a time"
)

#: The rule a table with no DELETE for the application role leaves by.
A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO: Final = (
    "the application role holds no DELETE on it, and the migration that built it argues how its "
    "rows leave; this sweep does not grant itself a second way out"
)

#: Why a run that raised still writes a report.
A_RUN_THAT_RAISED_IS_A_REPORT_TOO: Final = (
    "A run that raised was rolled back, so it removed nothing, and the run record holds one "
    "sentence of why. An administrator reading the retention screen the next morning would "
    "otherwise see yesterday's clean report as the latest one and read it as today's. So a "
    "failed run writes a report of its own, every store unreached, the failure on it, in a "
    "transaction that does not share the failed one's fate."
)

#: Why a release has to name the newest report, produced in report-only mode, that did not fail.
A_RELEASE_IS_A_DECISION_ABOUT_THE_NEWEST_REPORT: Final = (
    "The release is the record that a person read what the sweep would remove and agreed to it. "
    "Naming an older report agrees to a backlog that has since changed; naming a report the "
    "sweep produced while already released agrees to something that has already happened; and "
    "naming a failed run agrees to a report with no counts in it. Each of those is a deletion "
    "nobody approved, arriving through the one record meant to prove somebody did."
)


class RetentionStoreError(Exception):
    """A hold or a release was asked for in a shape this store will not record."""


class ReleaseRefusal(enum.StrEnum):
    """Why the sweep was not released. See `A_RELEASE_IS_A_DECISION_ABOUT_THE_NEWEST_REPORT`."""

    #: No report has been written, so there is nothing a person could have read.
    NO_REPORT = "no_report"
    #: A newer report exists than the one named.
    NOT_THE_NEWEST = "not_the_newest"
    #: The named report was produced while the sweep was already released.
    NOT_A_REPORT_ONLY_RUN = "not_a_report_only_run"
    #: The named report is a run that raised.
    A_FAILED_RUN = "a_failed_run"
    #: The release is dated before the report it names.
    BEFORE_THE_REPORT = "before_the_report"
    #: A release is already live.
    ALREADY_RELEASED = "already_released"


class ReleaseRefusedError(RetentionStoreError):
    """The sweep was not released, and why."""

    def __init__(self, reason: ReleaseRefusal) -> None:
        self.reason = reason
        super().__init__(f"the retention sweep was not released: {reason.value}")


# --------------------------------------------------------------------------- declarations
#: Tables in a schema more than one store shares, and the store each belongs to.
ATTRIBUTED: Final[Mapping[str, Store]] = MappingProxyType(
    {
        "obs.audit_entry": Store.AUDIT,
        "obs.legal_hold": Store.AUDIT,
        "obs.request_telemetry": Store.LEDGER,
    }
)

#: The column a table's age is read from. Required for every table in a fixed-window store.
CLOCKS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "obs.audit_entry": "at",
        "obs.legal_hold": "placed_at",
        "obs.request_telemetry": "received_at",
    }
)

#: The column naming whose a row is, for matching a legal hold.
SUBJECTS: Final[Mapping[str, str]] = MappingProxyType({"obs.request_telemetry": "principal"})


def attribution_gaps(
    attributed: Mapping[str, Store] = ATTRIBUTED,
    clocks: Mapping[str, str] = CLOCKS,
    subjects: Mapping[str, str] = SUBJECTS,
) -> tuple[str, ...]:
    """Every declaration here that points at something no store could hold.

    An attribution to a store that does not claim the table's schema would never be read, so
    the table would fall to whichever store does. A clock or a subject column on a table in no
    store's schema is a declaration nothing consults.
    """
    findings: list[str] = []
    claimed = {schema for entry in STORES for schema in entry.schemas}
    for table, store in sorted(attributed.items()):
        schema = table.partition(".")[0]
        if schema not in facts_for(store).schemas:
            findings.append(
                f"{table} is attributed to {store.value}, which does not claim schema "
                f"{schema!r}, so the attribution is never read"
            )
    for table in sorted({*clocks, *subjects}):
        if table.partition(".")[0] not in claimed:
            findings.append(f"{table} has a column declared here and is in no store's schema")
    return tuple(findings)


class PostgresSweeper:
    """`brain.ops.retention.StoreSweeper` over one PostgreSQL connection.

    Every declaration is a parameter defaulting to this module's own, for the reason
    `brain.ops.retention.retention_policy_gaps` takes its surfaces as parameters: an executor
    that can only be pointed at the real estate, which holds no deletable fixed-window table
    yet, is an executor nobody has watched remove a row.
    """

    def __init__(
        self,
        conn: psycopg.Connection[Any],
        *,
        holds: Sequence[Hold] = (),
        attributed: Mapping[str, Store] = ATTRIBUTED,
        clocks: Mapping[str, str] = CLOCKS,
        subjects: Mapping[str, str] = SUBJECTS,
        role: str = APPLICATION_ROLE,
    ) -> None:
        self.conn = conn
        self.holds = tuple(holds)
        self.attributed = attributed
        self.clocks = clocks
        self.subjects = subjects
        self.role = role

    # ------------------------------------------------------------------- which tables
    def tables_of(self, store: Store) -> tuple[str, ...]:
        """The tables this store holds, read from the catalogue. Refuses what it cannot place."""
        schemas = facts_for(store).schemas
        if not schemas:
            raise RetentionError(NOT_HELD_IN_POSTGRES)
        found = self.conn.execute(
            "SELECT n.nspname, c.relname FROM pg_catalog.pg_class AS c "
            "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE n.nspname = ANY(%s) AND c.relkind IN ('r', 'p') AND NOT c.relispartition "
            "ORDER BY 1, 2",
            (sorted(schemas),),
        ).fetchall()
        owned: list[str] = []
        for schema, name in found:
            table = f"{schema}.{name}"
            if table in self.attributed:
                if self.attributed[table] is store:
                    owned.append(table)
                continue
            sharing = sum(1 for entry in STORES if schema in entry.schemas)
            if sharing > 1:
                msg = (
                    f"{table} is attributed to no store: "
                    f"{A_TABLE_IN_A_SHARED_SCHEMA_BELONGS_TO_NOBODY_UNTIL_IT_IS_ATTRIBUTED}"
                )
                raise RetentionError(msg)
            owned.append(table)
        return tuple(owned)

    def removal_rule(self, table: str) -> str:
        """Why this sweep may not remove rows from `table` itself, or an empty string if it may.

        Read from the catalogue each time rather than declared here, because the rule belongs
        to the table's own migration and a copy of it in this module would be the copy that is
        wrong the day a migration grants or partitions. See the module docstring.
        """
        row = self.conn.execute(
            "SELECT c.relkind, has_table_privilege(%s, c.oid, 'DELETE') "
            "FROM pg_catalog.pg_class AS c "
            "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relname = %s",
            (self.role, *table.split(".", 1)),
        ).fetchone()
        if row is None:
            msg = f"{table} is not in the catalogue, so nothing can be said about removing from it"
            raise RetentionError(msg)
        kind, may_delete = row
        if kind == "p":
            return A_PARTITIONED_TABLE_LEAVES_A_PARTITION_AT_A_TIME
        if not may_delete:
            return A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO
        return ""

    # ------------------------------------------------------------------- the protocol
    def census(self, store: Store, now: datetime) -> StoreCensus:
        """How much in this store is past its window, how much is held, and how much is queued."""
        horizon = horizon_of(store)
        tables = self.tables_of(store)
        match horizon.lifetime:
            case Lifetime.WHILE_THE_RECORD_EXISTS | Lifetime.FOLLOWS_ITS_SOURCE:
                raise RetentionError(
                    A_RECORD_LIFETIME_NEEDS_A_SUBJECT_REFERENCE_NOBODY_HAS_DECLARED
                )
            case Lifetime.NEVER_EXPIRES:
                return StoreCensus(
                    store=store, beyond_horizon=0, oldest_days=self._oldest(tables, now)
                )
            case Lifetime.FIXED_WINDOW:
                cutoff = self._cutoff(store, now)
                beyond = held = queued = 0
                rules: list[str] = []
                for table in tables:
                    clock = self._clock(table)
                    found = self._count(table, clock, cutoff, None)
                    kept = self._held(table, clock, cutoff, now)
                    beyond += found
                    held += kept
                    rule = self.removal_rule(table)
                    if rule and found > kept:
                        queued += found - kept
                        if rule not in rules:
                            rules.append(rule)
                return StoreCensus(
                    store=store,
                    beyond_horizon=beyond,
                    held=held,
                    oldest_days=self._oldest(tables, now),
                    queued=queued,
                    queued_because="; ".join(rules),
                )
            case _:  # pragma: no cover - unreachable while Lifetime is exhaustive
                assert_never(horizon.lifetime)

    def expire(self, store: Store, now: datetime) -> int:
        """Remove what is past a fixed window, not held, and in a table this role may delete from.

        Refuses every other lifetime. A table with a removal rule of its own is skipped here and
        was counted as queued by `census`.
        """
        horizon = horizon_of(store)
        if horizon.lifetime is not Lifetime.FIXED_WINDOW:
            msg = (
                f"{store.value} is {horizon.lifetime.value}, and only a fixed window is enforced "
                "by age"
            )
            raise RetentionError(msg)
        cutoff = self._cutoff(store, now)
        removed = 0
        for table in self.tables_of(store):
            clock = self._clock(table)
            if self.removal_rule(table):
                continue
            active = self._active(now)
            if any(hold.all_subjects for hold in active):
                continue
            subjects = frozenset().union(*(hold.subjects for hold in active))
            query = sql.SQL("DELETE FROM {table} WHERE {clock} < %s").format(
                table=_identifier(table), clock=sql.Identifier(clock)
            )
            params: tuple[object, ...] = (cutoff,)
            if subjects:
                column = self._subject(table)
                query = sql.SQL("{base} AND {column} <> ALL(%s)").format(
                    base=query, column=sql.Identifier(column)
                )
                params = (cutoff, sorted(subjects))
            removed += self.conn.execute(query, params).rowcount
        return removed

    # ------------------------------------------------------------------------ helpers
    def _cutoff(self, store: Store, now: datetime) -> datetime:
        # A cast rather than a guard: `Horizon`'s constructor refuses a fixed window with no
        # days, so a None here cannot be built and a check for it could not be reached.
        return now - timedelta(days=cast(int, horizon_of(store).days))

    def _clock(self, table: str) -> str:
        clock = self.clocks.get(table)
        if clock is None:
            msg = (
                f"{table} holds a fixed-window class and declares no clock column, so its rows "
                "have no age and a sweep that skipped it would keep them forever"
            )
            raise RetentionError(msg)
        return clock

    def _subject(self, table: str) -> str:
        column = self.subjects.get(table)
        if column is None:
            raise RetentionError(f"{table}: {A_HOLD_THIS_CANNOT_MATCH_TO_A_ROW_STOPS_THE_SWEEP}")
        return column

    def _active(self, now: datetime) -> tuple[Hold, ...]:
        return tuple(hold for hold in self.holds if hold.is_active(now))

    def _count(
        self, table: str, clock: str, cutoff: datetime, subjects: Sequence[str] | None
    ) -> int:
        query = sql.SQL("SELECT count(*) FROM {table} WHERE {clock} < %s").format(
            table=_identifier(table), clock=sql.Identifier(clock)
        )
        params: tuple[object, ...] = (cutoff,)
        if subjects is not None:
            query = sql.SQL("{base} AND {column} = ANY(%s)").format(
                base=query, column=sql.Identifier(self._subject(table))
            )
            params = (cutoff, list(subjects))
        row = self.conn.execute(query, params).fetchone()
        return int(row[0]) if row is not None else 0

    def _held(self, table: str, clock: str, cutoff: datetime, now: datetime) -> int:
        active = self._active(now)
        if not active:
            return 0
        if any(hold.all_subjects for hold in active):
            return self._count(table, clock, cutoff, None)
        subjects = sorted(frozenset().union(*(hold.subjects for hold in active)))
        return self._count(table, clock, cutoff, subjects)

    def _oldest(self, tables: Sequence[str], now: datetime) -> int | None:
        """Age in whole days of the oldest row with a declared clock, or None when none has one."""
        oldest: datetime | None = None
        for table in tables:
            clock = self.clocks.get(table)
            if clock is None:
                continue
            row = self.conn.execute(
                sql.SQL("SELECT min({clock}) FROM {table}").format(
                    clock=sql.Identifier(clock), table=_identifier(table)
                )
            ).fetchone()
            first = None if row is None else row[0]
            if first is not None and (oldest is None or first < oldest):
                oldest = first
        return None if oldest is None else (now - oldest).days


def _identifier(table: str) -> sql.Identifier:
    schema, _, name = table.partition(".")
    return sql.Identifier(schema, name)


# -------------------------------------------------------------------------- legal holds
def active_holds(conn: psycopg.Connection[Any], now: datetime) -> tuple[LegalHold, ...]:
    """Every hold placed by `now` and not lifted by then, as `brain.audit.ledger.LegalHold`.

    Built through the model rather than handed on as rows, so a row the model refuses is a
    raised run rather than a hold quietly read as something else. The activity test is the
    model's own `is_active` as well as the query's, and the two agree by construction: the query
    narrows what is read and the model decides.
    """
    rows = conn.execute(
        "SELECT id, reason_code, subjects, actors, all_subjects, placed_at, released_at "
        "FROM obs.legal_hold WHERE placed_at <= %s AND (released_at IS NULL OR released_at > %s) "
        "ORDER BY placed_at, id",
        (now, now),
    ).fetchall()
    holds = tuple(
        LegalHold(
            id=hold_id,
            reason_code=reason_code,
            subjects=frozenset(subjects),
            actors=frozenset(actors),
            all_subjects=all_subjects,
            placed_at=placed_at,
            released_at=released_at,
        )
        for hold_id, reason_code, subjects, actors, all_subjects, placed_at, released_at in rows
    )
    return tuple(hold for hold in holds if hold.is_active(now))


def cite(holds: Sequence[LegalHold]) -> tuple[CitedHold, ...]:
    """How a report names the holds a run was under: identifier and reason, never subjects."""
    return tuple(
        CitedHold(hold_id=hold.id, reason_code=hold.reason_code, company_wide=hold.all_subjects)
        for hold in holds
    )


# ------------------------------------------------------------------------------ reports
def report_document(report: RetentionReport) -> dict[str, list[Any]]:
    """The three JSON columns a report is written as. Counts and reasons, never a subject."""
    return {
        "stores": [
            {
                "store": one.store.value,
                "reached": one.reached,
                "beyond_horizon": one.beyond_horizon,
                "held": one.held,
                "oldest_days": one.oldest_days,
                "removed": one.removed,
                "queued": one.queued,
                "queued_because": one.queued_because,
                "unreached_because": one.unreached_because,
            }
            for one in report.swept
        ],
        "holds": [
            {
                "hold_id": hold.hold_id,
                "reason_code": hold.reason_code,
                "company_wide": hold.company_wide,
            }
            for hold in report.holds
        ],
        "findings": list(report.findings),
    }


def report_from_document(
    *,
    at: datetime,
    report_only: bool,
    stores: Sequence[Mapping[str, Any]],
    holds: Sequence[Mapping[str, Any]],
    findings: Sequence[str],
) -> RetentionReport:
    """A stored report read back into the model the console decides over.

    The class, lifetime and window of each store are taken from the policy as it stands rather
    than from the row, because a stored copy of a window is a second declaration of it; a report
    read after a window changed describes its counts against the window that governs them now,
    and the counts are what was stored. A store the policy no longer declares is refused rather
    than dropped, and a declared store missing from the row is read as unreached, which is what
    `enforcement_report` would have said about it.
    """
    by_store: dict[Store, Mapping[str, Any]] = {}
    for written in stores:
        by_store[Store(written["store"])] = written
    swept: list[SweptStore] = []
    for store in Store:
        horizon = horizon_of(store)
        entry = by_store.get(store)
        swept.append(
            SweptStore(
                store=store,
                data_class=horizon.data_class,
                lifetime=horizon.lifetime,
                days=horizon.days,
                reached=False if entry is None else bool(entry["reached"]),
                beyond_horizon=0 if entry is None else int(entry["beyond_horizon"]),
                held=0 if entry is None else int(entry["held"]),
                oldest_days=None if entry is None else entry["oldest_days"],
                removed=0 if entry is None else int(entry["removed"]),
                queued=0 if entry is None else int(entry["queued"]),
                queued_because="" if entry is None else str(entry["queued_because"]),
                unreached_because="" if entry is None else str(entry["unreached_because"]),
            )
        )
    return RetentionReport(
        at=at,
        swept=tuple(swept),
        findings=tuple(findings),
        report_only=report_only,
        holds=tuple(
            CitedHold(
                hold_id=str(hold["hold_id"]),
                reason_code=str(hold["reason_code"]),
                company_wide=bool(hold["company_wide"]),
            )
            for hold in holds
        ),
    )


def record_report(
    conn: psycopg.Connection[Any], report: RetentionReport, *, failure: str | None = None
) -> uuid.UUID:
    """Append one report. Returns its key, which is what a release names."""
    document = report_document(report)
    row = conn.execute(
        "INSERT INTO ops.retention_report "
        "(at, report_only, complete, stores, holds, findings, failure) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (
            report.at,
            report.report_only,
            report.complete,
            Jsonb(document["stores"]),
            Jsonb(document["holds"]),
            Jsonb(document["findings"]),
            None if failure is None else failure[:FAILURE_CHARS],
        ),
    ).fetchone()
    if row is None:  # pragma: no cover - an INSERT ... RETURNING returns its row or raises
        msg = "the retention report was not written"
        raise RetentionError(msg)
    return cast(uuid.UUID, row[0])


def run_retention_sweep(conn: psycopg.Connection[Any], *, now: datetime, report_only: bool) -> str:
    """One scheduled retention run over PostgreSQL, in one transaction, as report lines.

    The holds are read, the sweep runs and the report is written in that one transaction, so a
    run that fails halfway removes nothing rather than some of it, and a hold placed after the
    holds were read is a hold on the next run. A run that raises writes a report saying so in a
    transaction of its own and raises on, so the run record carries the failure as well. See
    `A_RUN_THAT_RAISED_IS_A_REPORT_TOO`.

    The shape `brain.ops.schedule_runner.Runner.run` needs once a connection is bound: an instant
    and whether the control may act, returning a sentence for `ops.control_run.detail`.
    """
    try:
        with conn.transaction():
            holds = active_holds(conn, now)
            report = sweep(
                PostgresSweeper(conn, holds=holds),
                now=now,
                report_only=report_only,
                holds=cite(holds),
            )
            record_report(conn, report)
    except Exception as exc:
        record_failure(conn, now=now, report_only=report_only, failure=exc)
        raise
    return "\n".join(report.lines())


def record_failure(
    conn: psycopg.Connection[Any], *, now: datetime, report_only: bool, failure: Exception
) -> None:
    """Write the report of a run that raised: every store unreached, and why.

    In a transaction of its own, because the run's was rolled back. A database that cannot take
    this write either is a database that is gone, and the run's own exception is the better
    account of that, so a failure here is not raised over it. See
    `A_RUN_THAT_RAISED_IS_A_REPORT_TOO`.
    """
    unreached = enforcement_report(now=now, census=())
    try:
        with conn.transaction():
            record_report(
                conn,
                replace(unreached, report_only=report_only),
                failure=f"{type(failure).__name__}: {failure}",
            )
    except psycopg.Error:
        return


# ------------------------------------------------------------- reading and releasing
@dataclass(frozen=True)
class StoredReport:
    """A report as it was written: its key, whether the run raised, and the report itself."""

    id: uuid.UUID
    report: RetentionReport
    failure: str | None


def _stored(row: RetentionReportRow) -> StoredReport:
    return StoredReport(
        id=row.id,
        report=report_from_document(
            at=row.at,
            report_only=row.report_only,
            stores=row.stores,
            holds=row.holds,
            findings=row.findings,
        ),
        failure=row.failure,
    )


async def latest_report(session: AsyncSession) -> StoredReport | None:
    """The newest report written, or None when no run has written one.

    Newest by the instant the run was asked about, which is the instant its counts are as of.
    Whether the reader may be shown it is not decided here: it is
    `brain.console.govern_surfaces.retention_view`'s decision, taken on the report this returns.
    """
    row = (
        await session.execute(
            select(RetentionReportRow)
            .order_by(RetentionReportRow.at.desc(), RetentionReportRow.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return None if row is None else _stored(row)


async def released_controls(session: AsyncSession, *, now: datetime) -> frozenset[str]:
    """The destructive controls a person has released as of `now`, for the worker's tick.

    One today, `retention_sweep`, because it is the one member of
    `brain.ops.schedule.DESTRUCTIVE`; a test holds the two equal so a second destructive control
    cannot be added without somewhere to record its release.
    """
    live = (
        await session.execute(
            select(RetentionReleaseRow.id)
            .where(
                RetentionReleaseRow.withdrawn_at.is_(None),
                RetentionReleaseRow.released_at <= now,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return frozenset() if live is None else frozenset({RETENTION_SWEEP})


#: The control a release in `ops.retention_release` releases.
RETENTION_SWEEP: Final = "retention_sweep"


def release_refusal(
    newest: StoredReport | None, *, after_report: uuid.UUID, at: datetime, live: bool
) -> ReleaseRefusal | None:
    """Why a release naming `after_report` at `at` may not be recorded, or None when it may.

    The whole decision, apart from the reads that feed it, so it can be shown to refuse without
    a database. Ordered so the reason given is the first thing a person would have to fix: there
    has to be a report, it has to be the one they read, it has to be a report of what the sweep
    would do rather than of what it did, it has to have counts in it, the release cannot predate
    it, and nothing may already be released. See
    `A_RELEASE_IS_A_DECISION_ABOUT_THE_NEWEST_REPORT`.
    """
    if newest is None:
        return ReleaseRefusal.NO_REPORT
    if newest.id != after_report:
        return ReleaseRefusal.NOT_THE_NEWEST
    if not newest.report.report_only:
        return ReleaseRefusal.NOT_A_REPORT_ONLY_RUN
    if newest.failure is not None:
        return ReleaseRefusal.A_FAILED_RUN
    if at < newest.report.at:
        return ReleaseRefusal.BEFORE_THE_REPORT
    if live:
        return ReleaseRefusal.ALREADY_RELEASED
    return None


async def release_sweep(
    session: AsyncSession, *, after_report: uuid.UUID, by: str, at: datetime
) -> uuid.UUID:
    """Record that `by` released the sweep after reading `after_report`. Refuses otherwise.

    `release_refusal` is the decision. The unique index on a live release is the guard a
    concurrent pair of releases meets; the check is what turns the ordinary case into a refusal
    with a reason rather than an integrity error.
    """
    refusal = release_refusal(
        await latest_report(session),
        after_report=after_report,
        at=at,
        live=bool(await released_controls(session, now=at)),
    )
    if refusal is not None:
        raise ReleaseRefusedError(refusal)
    made = (
        await session.execute(
            insert(RetentionReleaseRow)
            .values(after_report=after_report, released_at=at, released_by=by)
            .returning(RetentionReleaseRow.id)
        )
    ).scalar_one()
    return made


async def withdraw_release(session: AsyncSession, *, by: str, at: datetime) -> bool:
    """Put the sweep back to reporting. True when a live release was withdrawn."""
    withdrawn = (
        await session.execute(
            update(RetentionReleaseRow)
            .where(RetentionReleaseRow.withdrawn_at.is_(None))
            .values(withdrawn_at=at, withdrawn_by=by)
            .returning(RetentionReleaseRow.id)
        )
    ).scalar_one_or_none()
    return withdrawn is not None


async def place_hold(session: AsyncSession, hold: LegalHold, *, by: str) -> None:
    """Record a hold. A hold that arrives already lifted is refused: it would hold nothing."""
    if hold.released_at is not None:
        msg = f"hold {hold.id!r} arrives already lifted, so recording it would hold nothing"
        raise RetentionStoreError(msg)
    await session.execute(
        insert(LegalHoldRow).values(
            id=hold.id,
            reason_code=hold.reason_code,
            subjects=sorted(hold.subjects),
            actors=sorted(hold.actors),
            all_subjects=hold.all_subjects,
            placed_at=hold.placed_at,
            placed_by=by,
        )
    )


async def lift_hold(session: AsyncSession, hold_id: str, *, by: str, at: datetime) -> bool:
    """Mark a hold lifted at `at`. True when a live hold placed by then was lifted.

    Marked, never removed: see `brain.tables.retention`. A hold already lifted is not lifted
    again, so the first lift's instant and name are the ones that stand.
    """
    lifted = (
        await session.execute(
            update(LegalHoldRow)
            .where(
                LegalHoldRow.id == hold_id,
                LegalHoldRow.released_at.is_(None),
                LegalHoldRow.placed_at <= at,
            )
            .values(released_at=at, released_by=by)
            .returning(LegalHoldRow.id)
        )
    ).scalar_one_or_none()
    return lifted is not None
