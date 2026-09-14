"""The retention executor for PostgreSQL: count what is past its window, and remove it.

`brain.ops.retention` decides every horizon and builds the report, and its `StoreSweeper` has
been a protocol nothing implemented. This implements it for the stores that live in PostgreSQL,
and it decides nothing that module decides: the window is `horizon_of(store)`, the report is
`enforcement_report`, and `retention.sweep` is what calls this.

**A store is reached only when it can be counted honestly, and every other store is named with
the reason.** That is `A_SWEEP_THAT_SKIPS_A_STORE_KEEPS_IT_FOREVER` applied to the executor
rather than to the report. Four cases, and only the first two are reached today:

*A fixed window* is counted by a declared clock column on every table the store holds, and
rows older than the window are removed. A table with no declared clock refuses the store
rather than being skipped, because a table skipped is a table kept forever.

*A class that never expires* is reached with nothing due, because that is what its lifetime
says rather than what a count found, and its oldest row is still reported where a clock is
declared, so an audit chain that has stopped growing is visible as an age.

*A record lifetime* is refused. `StoreCensus` says a record-lifetime store's figure is the rows
whose subject record is gone, and which record a row is about is a per-table fact nothing in
this repository declares. Counting soft-deleted rows instead would be a plausible answer and a
wrong one: `brain.db.SoftDeleteMixin` retires rows so the trail survives, and a sweep treating
retirement as expiry would be deleting what that mixin exists to keep. Removal of a person's
record-lifetime rows is `brain.ops.erasure`'s, which is unbuilt, and says so. See
`A_RECORD_LIFETIME_NEEDS_A_SUBJECT_REFERENCE_NOBODY_HAS_DECLARED`.

*A store outside PostgreSQL* is refused: recordings, attachments, exports and backups are in the
object store, and the cache and the index are not tables. **There is no object-store sweeper**,
because `brain.ops.storage.StorageBackend` is a protocol with no implementation anywhere here,
and its `list_objects` returns keys with no age, so even an implementation of it could not
count by window. The bucket lifecycle rules `brain.ops.storage.BUCKETS` declare are what expire
those objects today, and nothing here verifies that they do.

**Which store a table belongs to is read from the catalogue, and a shared schema needs an
attribution.** Every schema but `obs` is claimed by one store, so every table in it is that
store's, including one added next year. `obs` is claimed by four stores with four lifetimes, so
a table there has to be attributed in `ATTRIBUTED`, and an unattributed one refuses every store
sharing the schema. The metadata ledger arriving in `obs` without an attribution is therefore
an incomplete retention report on the next morning, rather than a five-year table swept on a
thirty-day window. See `A_TABLE_IN_A_SHARED_SCHEMA_BELONGS_TO_NOBODY_UNTIL_IT_IS_ATTRIBUTED`.

**A legal hold fails closed.** Rows under an active hold are counted as held and never removed.
A hold naming subjects, over a table with no declared subject column, refuses the store: which
rows it covers cannot be told, and removing some of them to find out is not available. See
`A_HOLD_THIS_CANNOT_MATCH_TO_A_ROW_STOPS_THE_SWEEP`. Nothing in this repository records holds
yet, so a runner passes none, and that is stated rather than implied.

What this finds on a database migrated to head, measured rather than predicted: the ledger, the
trace and the payload stores are reached with nothing due, because no table in `obs` holds
those classes yet; the audit store is reached with nothing due; every other store is refused by
name. That is an incomplete report, and it is the true one.

Rejected: a sync of each table's retention into a policy table the sweeper reads. It is a
second declaration of the windows `brain.ops.retention` already declares, and the copy nobody
reads is the one that gets raised.

Task ids: M25.1.5
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, assert_never, cast

import psycopg
from psycopg import sql

from brain.ops.erasure import Hold
from brain.ops.retention import (
    STORES,
    Lifetime,
    RetentionError,
    Store,
    StoreCensus,
    facts_for,
    horizon_of,
    sweep,
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


# --------------------------------------------------------------------------- declarations
#: Tables in a schema more than one store shares, and the store each belongs to.
ATTRIBUTED: Final[Mapping[str, Store]] = MappingProxyType({"obs.audit_entry": Store.AUDIT})

#: The column a table's age is read from. Required for every table in a fixed-window store.
CLOCKS: Final[Mapping[str, str]] = MappingProxyType({"obs.audit_entry": "at"})

#: The column naming whose a row is, for matching a legal hold. None is declared yet.
SUBJECTS: Final[Mapping[str, str]] = MappingProxyType({})


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
    that can only be pointed at the real estate, which holds no fixed-window table yet, is an
    executor nobody has watched remove a row.
    """

    def __init__(
        self,
        conn: psycopg.Connection[Any],
        *,
        holds: Sequence[Hold] = (),
        attributed: Mapping[str, Store] = ATTRIBUTED,
        clocks: Mapping[str, str] = CLOCKS,
        subjects: Mapping[str, str] = SUBJECTS,
    ) -> None:
        self.conn = conn
        self.holds = tuple(holds)
        self.attributed = attributed
        self.clocks = clocks
        self.subjects = subjects

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

    # ------------------------------------------------------------------- the protocol
    def census(self, store: Store, now: datetime) -> StoreCensus:
        """How much in this store is past its window, and how much of that is held."""
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
                beyond = held = 0
                for table in tables:
                    clock = self._clock(table)
                    beyond += self._count(table, clock, cutoff, None)
                    held += self._held(table, clock, cutoff, now)
                return StoreCensus(
                    store=store,
                    beyond_horizon=beyond,
                    held=held,
                    oldest_days=self._oldest(tables, now),
                )
            case _:  # pragma: no cover - unreachable while Lifetime is exhaustive
                assert_never(horizon.lifetime)

    def expire(self, store: Store, now: datetime) -> int:
        """Remove what is past a fixed window and not held. Refuses every other lifetime."""
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


def run_retention_sweep(
    conn: psycopg.Connection[Any],
    *,
    now: datetime,
    report_only: bool,
    holds: Sequence[Hold] = (),
) -> str:
    """One scheduled retention run over PostgreSQL, in one transaction, as report lines.

    The shape `brain.ops.schedule_runner.Runner.run` needs once a connection is bound: an instant
    and whether the control may act, returning a sentence for `ops.control_run.detail`. One
    transaction, so a run that fails halfway removes nothing rather than some of it.
    """
    with conn.transaction():
        report = sweep(PostgresSweeper(conn, holds=holds), now=now, report_only=report_only)
    return "\n".join(report.lines())
