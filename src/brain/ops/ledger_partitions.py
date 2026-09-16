"""The metadata ledger's monthly partitions, created ahead and detached behind, in plain SQL.

`brain.ops.partitioning` derives the scheme: one partition per calendar month, enough of them
made ahead to survive a restore from the oldest backup, and a period leaving the live table only
once its newest possible row has passed the ledger's horizon. `0039` built the table partitioned
with a default partition and nothing else, so until this module every row landed in the default
partition and the scheme was data nothing applied. This is the executor, and the general worker
runs it on the retention sweep's daily schedule through `brain.ops.schedule_runner`.

**Plain SQL and not pg_partman, and the reason is the image.** pg_partman is an extension, and
the database image every install runs does not carry it. Using it meant this product building,
publishing and pinning its own PostgreSQL image, and every install's database container changing
to it, for a job that is two statements a month. The owner chose this on 2026-09-16. What
pg_partman would also have brought, its background worker, is replaced by a schedule this system
already has and already alerts on.

**Three operations, and only one of them removes a row from anywhere.**

*Create* makes a month's partition, with row-level security enabled as `0039` enables it on the
default partition, when no row for that month is sitting in the default partition. It is
`CREATE TABLE IF NOT EXISTS`, so a second run changes nothing.

*Move* is create for a month that already has rows in the default partition, which is every
month on the first run of an install that has been answering questions. PostgreSQL refuses to
create a partition whose range the default partition holds rows for, so the default partition is
detached, the month's partition created, its rows copied across, the same rows deleted from the
default partition and the default partition attached again, **in one transaction, and the copy
and the delete must count the same number of rows or the transaction is rolled back.** That
delete is the only one in this module, and it never removes a row that is not already in the
month's partition in the same transaction. See `A_MOVE_IS_A_COPY_AND_A_DELETE_THAT_MUST_AGREE`.

*Detach* removes a month from the live table once every row it could hold is past the horizon,
and keeps the table. **Nothing here drops a table or deletes a detached partition's rows.** The
detached table stays in `obs` under its own name, row-level security still on, and
`brain.ops.retention_store` attributes it to the ledger store, so the retention sweep counts its
rows as past their window and queued. Dropping it after `brain.ops.partitioning.SETTLE_DAYS` is
the retention executor's step and is not built. See `A_DETACH_KEEPS_EVERY_ROW`.

**Detach waits for the same release the retention sweep does.** A detached month is gone from
every read of the ledger, which is a retention decision, so in report-only mode this names the
months it would detach and detaches none. Create and move remove nothing from any read and run in
either mode, because a month with no partition is a month whose rows pile up in the default
partition until somebody releases a sweep.

**Every operation takes the table's lock and decides inside it.** Whether a month's rows are in
the default partition is read after `LOCK TABLE ... IN ACCESS EXCLUSIVE MODE`, so a request
writing into that month between the read and the create waits rather than turning a create into
an error. The lock is held for one month's transaction, which on every run after the first is a
catalogue change, and on the first is the copy of that month's rows.

**A month is named by its UTC calendar month, and the bounds are half-open.** The partition for
September 2026 holds `2026-09-01 00:00:00+00` up to and not including `2026-10-01 00:00:00+00`, so
the last microsecond of a month and the first of the next land in different partitions and no
instant belongs to two. `received_at` is a timestamp with a time zone, so a row stamped in any
zone is routed by the instant it names. See `A_MONTH_IS_A_UTC_CALENDAR_MONTH`.

Task ids: M36.1.1.1
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import psycopg
from psycopg import pq, sql

from brain.ops.partitioning import CONTROL_COLUMN, PARTITION_INTERVAL, PREMAKE, Interval
from brain.ops.telemetry import LEDGER_RETENTION_DAYS

#: The ledger, its schema and its name, as `0039` built it.
SCHEMA: Final = "obs"
TABLE: Final = "request_telemetry"
LEDGER: Final = f"{SCHEMA}.{TABLE}"

#: The default partition `0039` built, which holds every row no month's partition does.
DEFAULT_PARTITION: Final = f"{LEDGER}_default"

#: A month's partition, by name: the table's name, `_p`, the year and the month.
PARTITION_NAME: Final = re.compile(r"\A" + TABLE + r"_p(\d{4})(\d{2})\Z")

A_MONTH_IS_A_UTC_CALENDAR_MONTH: Final = (
    "A partition holds one calendar month in UTC, from the first instant of the month up to and "
    "not including the first instant of the next. Half-open, so the last microsecond of a month "
    "and the first of the next are in different partitions and no instant is in two; UTC, so a "
    "month does not move with the zone of whoever is reading and a row is routed by the instant "
    "it records."
)

A_MOVE_IS_A_COPY_AND_A_DELETE_THAT_MUST_AGREE: Final = (
    "Rows already in the default partition are moved by copying them into the month's partition "
    "and deleting the same predicate from the default partition, inside one transaction holding "
    "the table's lock. The two counts must be equal, and when they are not the transaction is "
    "rolled back, so a row is never deleted without being in the month's partition first and a "
    "move that went wrong leaves the table as it was."
)

A_DETACH_KEEPS_EVERY_ROW: Final = (
    "Detaching a partition takes it out of the live table and leaves the table and every row in "
    "it where it was. Nothing in this module drops a table, truncates one or deletes from a "
    "detached one: removing the rows after they have settled is the retention executor's step, "
    "released by a person, and not a side effect of keeping the partitions in order."
)

A_DETACH_IS_A_RETENTION_DECISION: Final = (
    "A detached month is gone from every read of the ledger, so detaching is removal as far as "
    "any reader can tell, and it waits for the release the retention sweep waits for. Creating "
    "and moving remove nothing from any read and run whether or not the sweep is released."
)

A_DATABASE_WITH_NO_LEDGER_HAS_NOTHING_TO_PARTITION: Final = (
    "The ledger arrives with 0039. A database migrated to an earlier head has no table to "
    "partition, and that is an answer rather than a failure: the run says so and changes nothing."
)


class LedgerPartitionError(Exception):
    """Raised when the ledger is not in a shape this module may change."""


@dataclass(frozen=True, order=True)
class Month:
    """One UTC calendar month. See `A_MONTH_IS_A_UTC_CALENDAR_MONTH`."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            msg = f"{self.month} is not a month"
            raise LedgerPartitionError(msg)
        if not 1 <= self.year <= 9998:
            msg = f"{self.year} is not a year a partition name can hold with the month after it"
            raise LedgerPartitionError(msg)

    @classmethod
    def of(cls, instant: datetime) -> Month:
        """The month an instant falls in, in UTC. Refuses a naive instant, which names none."""
        if instant.tzinfo is None or instant.utcoffset() is None:
            msg = f"{instant.isoformat()} has no time zone, so which month it is in is a guess"
            raise LedgerPartitionError(msg)
        at = instant.astimezone(UTC)
        return cls(at.year, at.month)

    @classmethod
    def named(cls, name: str) -> Month | None:
        """The month a partition's table name is for, or None for any other name."""
        matched = PARTITION_NAME.match(name)
        if matched is None:
            return None
        return cls(int(matched.group(1)), int(matched.group(2)))

    def following(self) -> Month:
        return Month(self.year + 1, 1) if self.month == 12 else Month(self.year, self.month + 1)

    @property
    def start(self) -> datetime:
        return datetime(self.year, self.month, 1, tzinfo=UTC)

    @property
    def end(self) -> datetime:
        """The first instant of the next month, which this month does not include."""
        return self.following().start

    @property
    def name(self) -> str:
        return f"{TABLE}_p{self.year:04d}{self.month:02d}"

    @property
    def qualified(self) -> str:
        return f"{SCHEMA}.{self.name}"


def _bound(instant: datetime) -> sql.Literal:
    """A bound as a string literal in UTC with its offset, so no session zone can move it."""
    return sql.Literal(instant.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S") + "+00")


def _table(name: str) -> sql.Identifier:
    return sql.Identifier(SCHEMA, name)


LEDGER_IDENTIFIER: Final = _table(TABLE)
DEFAULT_IDENTIFIER: Final = _table(f"{TABLE}_default")


def _in_month(month: Month) -> sql.Composed:
    return sql.SQL("{column} >= {start} AND {column} < {end}").format(
        column=sql.Identifier(CONTROL_COLUMN), start=_bound(month.start), end=_bound(month.end)
    )


def declared_as(table: str) -> str:
    """The table a schema-qualified name is declared under: the ledger for a month's partition.

    A detached month is an ordinary table in `obs`, and `brain.ops.retention_store` refuses every
    store sharing `obs` when it meets a table nobody attributed. So a month's table is read as
    the ledger it came from, with the ledger's clock and subject column, and its rows are counted
    by the retention sweep rather than stopping it. Any other name is itself.
    """
    schema, _, name = table.partition(".")
    return LEDGER if schema == SCHEMA and Month.named(name) is not None else table


def months_ahead(now: datetime, *, premake: int = PREMAKE) -> tuple[Month, ...]:
    """The month `now` is in and the `premake` months after it, which must all exist."""
    if premake < 0:
        msg = f"{premake} months ahead is not a number of months"
        raise LedgerPartitionError(msg)
    found = [Month.of(now)]
    for _ in range(premake):
        found.append(found[-1].following())
    return tuple(found)


def detachable(
    months: Iterable[Month], now: datetime, *, retention_days: int = LEDGER_RETENTION_DAYS
) -> tuple[Month, ...]:
    """The months whose newest possible row is past the horizon, which may leave the live table.

    A month leaves when its end plus the horizon is not after `now`: every row in it is older
    than `end`, so every row is past its window. Leaving on the start instead would take rows
    still inside it, which `brain.ops.partitioning` refuses as
    `A_DROP_ON_THE_OLDEST_ROW_TAKES_ROWS_STILL_INSIDE_THE_WINDOW`.
    """
    if now.tzinfo is None:
        msg = "a naive instant cannot be compared against a partition bound"
        raise LedgerPartitionError(msg)
    horizon = timedelta(days=retention_days)
    return tuple(sorted(one for one in set(months) if one.end + horizon <= now))


def create_statements(month: Month) -> tuple[sql.Composed, sql.Composed]:
    """The month's partition, made when the default partition holds no row for it."""
    return (
        sql.SQL(
            "CREATE TABLE IF NOT EXISTS {partition} PARTITION OF {ledger} "
            "FOR VALUES FROM ({start}) TO ({end})"
        ).format(
            partition=_table(month.name),
            ledger=LEDGER_IDENTIFIER,
            start=_bound(month.start),
            end=_bound(month.end),
        ),
        sql.SQL("ALTER TABLE {partition} ENABLE ROW LEVEL SECURITY").format(
            partition=_table(month.name)
        ),
    )


def move_statements(month: Month) -> tuple[sql.Composed, ...]:
    """Detach the default, create the month, copy, delete, attach the default. In that order.

    The copy is the fourth statement and the delete the fifth, and the executor compares their
    counts. See `A_MOVE_IS_A_COPY_AND_A_DELETE_THAT_MUST_AGREE`.
    """
    create, secure = create_statements(month)
    return (
        sql.SQL("ALTER TABLE {ledger} DETACH PARTITION {default}").format(
            ledger=LEDGER_IDENTIFIER, default=DEFAULT_IDENTIFIER
        ),
        create,
        secure,
        sql.SQL("INSERT INTO {partition} SELECT * FROM {default} WHERE {rows}").format(
            partition=_table(month.name), default=DEFAULT_IDENTIFIER, rows=_in_month(month)
        ),
        sql.SQL("DELETE FROM {default} WHERE {rows}").format(
            default=DEFAULT_IDENTIFIER, rows=_in_month(month)
        ),
        sql.SQL("ALTER TABLE {ledger} ATTACH PARTITION {default} DEFAULT").format(
            ledger=LEDGER_IDENTIFIER, default=DEFAULT_IDENTIFIER
        ),
    )


def detach_statement(month: Month) -> sql.Composed:
    """Take the month out of the live table and keep it. See `A_DETACH_KEEPS_EVERY_ROW`."""
    return sql.SQL("ALTER TABLE {ledger} DETACH PARTITION {partition}").format(
        ledger=LEDGER_IDENTIFIER, partition=_table(month.name)
    )


LOCK_STATEMENT: Final = sql.SQL("LOCK TABLE {ledger} IN ACCESS EXCLUSIVE MODE").format(
    ledger=LEDGER_IDENTIFIER
)

#: Whether the default partition holds a row for one month, read under the table's lock.
_WAITING_IN_MONTH: Final = sql.SQL("SELECT EXISTS (SELECT 1 FROM {default} WHERE {rows})")

#: The months the default partition holds rows for, truncated in UTC.
_MONTHS_WAITING: Final = sql.SQL(
    "SELECT DISTINCT date_trunc('month', {column}, 'UTC') FROM {default}"
)


@dataclass(frozen=True)
class Maintenance:
    """What one run did, and what it left for a release."""

    created: tuple[Month, ...] = ()
    #: Months moved out of the default partition, against how many rows each moved.
    moved: tuple[tuple[Month, int], ...] = ()
    detached: tuple[Month, ...] = ()
    #: Months past the horizon that stayed attached because the run was report-only.
    awaiting_release: tuple[Month, ...] = ()
    #: Months with rows in the default partition whose table is already detached.
    stranded: tuple[Month, ...] = ()
    #: Set when there was no ledger to partition.
    skipped: str = ""

    def summary(self) -> str:
        """One line for the run record."""
        if self.skipped:
            return f"ledger partitions: {self.skipped}"
        parts = [
            f"created {', '.join(one.name for one in self.created) or 'none'}",
            "moved "
            + (", ".join(f"{one.name} ({rows} rows)" for one, rows in self.moved) or "none"),
            f"detached {', '.join(one.name for one in self.detached) or 'none'}",
        ]
        if self.awaiting_release:
            parts.append(
                "awaiting the retention release "
                + ", ".join(one.name for one in self.awaiting_release)
            )
        if self.stranded:
            parts.append(
                "rows in the default partition for detached "
                + ", ".join(one.name for one in self.stranded)
            )
        return "ledger partitions: " + "; ".join(parts)


def maintain(
    conn: psycopg.Connection[Any],
    *,
    now: datetime,
    report_only: bool,
    premake: int = PREMAKE,
    retention_days: int = LEDGER_RETENTION_DAYS,
) -> Maintenance:
    """Create the months ahead, move rows out of the default partition, and detach what is due.

    Takes a connection with no transaction open and opens one per step, so the table's lock is
    held for one month at a time and released at that month's commit. Idempotent: a second run
    at the same instant finds every month made, the default partition empty for them, and every
    due month already detached, and changes nothing.
    """
    if PARTITION_INTERVAL is not Interval.MONTHLY:
        msg = f"the ledger is cut {PARTITION_INTERVAL.value} and this executor cuts it monthly"
        raise LedgerPartitionError(msg)
    if conn.info.transaction_status is not pq.TransactionStatus.IDLE:
        msg = (
            "the connection is inside a transaction, so every lock taken here would be held "
            "until the caller commits rather than for one month"
        )
        raise LedgerPartitionError(msg)

    with conn.transaction():
        row = conn.execute(
            "SELECT to_regclass(%s) IS NOT NULL, to_regclass(%s) IS NOT NULL",
            (LEDGER, DEFAULT_PARTITION),
        ).fetchone()
        has_ledger, has_default = (bool(row[0]), bool(row[1])) if row else (False, False)
        if not has_ledger:
            return Maintenance(skipped=A_DATABASE_WITH_NO_LEDGER_HAS_NOTHING_TO_PARTITION)
        if not has_default:
            msg = (
                f"{LEDGER} has no default partition, so a row for a month with no partition "
                "has nowhere to go; restore it from 0039 before partitions are made"
            )
            raise LedgerPartitionError(msg)
        attached = {
            month
            for (name,) in conn.execute(
                "SELECT c.relname FROM pg_catalog.pg_inherits AS i "
                "JOIN pg_catalog.pg_class AS c ON c.oid = i.inhrelid "
                "WHERE i.inhparent = %s::regclass",
                (LEDGER,),
            ).fetchall()
            if (month := Month.named(str(name))) is not None
        }
        detached_already = {
            month
            for (name,) in conn.execute(
                "SELECT c.relname FROM pg_catalog.pg_class AS c "
                "JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relkind = 'r' AND NOT c.relispartition",
                (SCHEMA,),
            ).fetchall()
            if (month := Month.named(str(name))) is not None
        }
        waiting = {
            Month.of(value)
            for (value,) in conn.execute(
                _MONTHS_WAITING.format(
                    column=sql.Identifier(CONTROL_COLUMN), default=DEFAULT_IDENTIFIER
                )
            ).fetchall()
        }

    wanted = (set(months_ahead(now, premake=premake)) | waiting) - attached
    stranded = tuple(sorted(wanted & detached_already))
    created: list[Month] = []
    moved: list[tuple[Month, int]] = []
    for month in sorted(wanted - detached_already):
        with conn.transaction():
            conn.execute(LOCK_STATEMENT)
            exists = conn.execute(
                _WAITING_IN_MONTH.format(default=DEFAULT_IDENTIFIER, rows=_in_month(month))
            ).fetchone()
            if exists is None or not exists[0]:
                for statement in create_statements(month):
                    conn.execute(statement)
                created.append(month)
                continue
            detach_default, create, secure, copy, delete, attach_default = move_statements(month)
            conn.execute(detach_default)
            conn.execute(create)
            conn.execute(secure)
            copied = conn.execute(copy).rowcount
            deleted = conn.execute(delete).rowcount
            if copied != deleted:
                msg = (
                    f"{month.name}: copied {copied} rows and would delete {deleted}. "
                    f"{A_MOVE_IS_A_COPY_AND_A_DELETE_THAT_MUST_AGREE}"
                )
                raise LedgerPartitionError(msg)
            conn.execute(attach_default)
            moved.append((month, copied))

    present = attached | set(created) | {one for one, _ in moved}
    due = detachable(present, now, retention_days=retention_days)
    detached: list[Month] = []
    if not report_only:
        for month in due:
            with conn.transaction():
                conn.execute(LOCK_STATEMENT)
                conn.execute(detach_statement(month))
            detached.append(month)
    return Maintenance(
        created=tuple(created),
        moved=tuple(moved),
        detached=tuple(detached),
        awaiting_release=due if report_only else (),
        stranded=stranded,
    )


def plan_statements(months: Sequence[Month]) -> tuple[str, ...]:
    """Every statement this module can issue for these months, as text, for a test to read."""
    return tuple(
        statement.as_string(None)
        for month in months
        for statement in (
            LOCK_STATEMENT,
            *create_statements(month),
            *move_statements(month),
            detach_statement(month),
        )
    )
