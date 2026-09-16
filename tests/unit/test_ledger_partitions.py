"""The metadata ledger's monthly partitions, made and detached by the worker in plain SQL
(M36.1.1.1).

Two layers. Everything that decides something, which month an instant is in, which months must
exist, which may leave, what each statement says and what the executor does when a move
disagrees with itself, is tested here against no server. What PostgreSQL does with the
statements is tested against a real one: a row either side of a month boundary lands in the
partition it belongs to, a second run changes nothing, and a detach leaves every row where a
reader can still count it. Those are skipped where `DATABASE_URL` is unset, and CI always sets it.

Task ids: M36.1.1.1
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import psycopg
import pytest
from psycopg import pq
from psycopg import sql as psql

from brain.ops import schedule_runner
from brain.ops.controls import call_sites
from brain.ops.ledger_partitions import (
    A_DETACH_KEEPS_EVERY_ROW,
    A_MOVE_IS_A_COPY_AND_A_DELETE_THAT_MUST_AGREE,
    DEFAULT_PARTITION,
    LEDGER,
    LedgerPartitionError,
    Maintenance,
    Month,
    declared_as,
    detach_statement,
    detachable,
    maintain,
    months_ahead,
    move_statements,
    plan_statements,
)
from brain.ops.partitioning import CONTROL_COLUMN, PREMAKE
from brain.ops.retention import BACKUP_RETENTION_DAYS, Store
from brain.ops.retention_store import CLOCKS, PostgresSweeper
from brain.ops.schedule_runner import runner_for
from brain.ops.telemetry import LEDGER_RETENTION_DAYS
from tests.fixtures.scratch_postgres import drop, fresh, migrate, sql

#: Far from any wall clock, so no fixture here goes off on a date nobody chose.
NOW = datetime(2999, 11, 15, 9, 30, tzinfo=UTC)


# =========================================================================== which month
def test_the_last_microsecond_of_a_month_and_the_first_of_the_next_are_different_months() -> None:
    """The boundary, and the reason the bounds are half-open. Delete this and a month's end can
    be made inclusive, putting the first instant of the next month in two partitions or none."""
    last = datetime(2999, 1, 31, 23, 59, 59, 999999, tzinfo=UTC)
    first = datetime(2999, 2, 1, tzinfo=UTC)

    assert Month.of(last) == Month(2999, 1)
    assert Month.of(first) == Month(2999, 2)
    assert Month(2999, 1).end == Month(2999, 2).start == first
    assert Month(2999, 1).start <= last < Month(2999, 1).end


def test_an_instant_is_placed_by_the_utc_month_whatever_zone_it_was_written_in() -> None:
    """Eight in the morning on the first in Singapore is still the last day of the previous month
    in UTC. Delete this and a month can follow the zone of whoever wrote the row."""
    singapore = timezone(timedelta(hours=8))

    assert Month.of(datetime(2999, 2, 1, 7, 59, 59, tzinfo=singapore)) == Month(2999, 1)
    assert Month.of(datetime(2999, 2, 1, 8, 0, 0, tzinfo=singapore)) == Month(2999, 2)


def test_a_naive_instant_is_refused_rather_than_placed_in_a_guessed_month() -> None:
    """Delete this and a timestamp with no zone is read as local time on whichever host runs it."""
    with pytest.raises(LedgerPartitionError, match="no time zone"):
        # A naive datetime, on purpose: the refusal of one is the property.
        Month.of(datetime(2999, 1, 1))


def test_december_is_followed_by_january_of_the_next_year() -> None:
    """Delete this and the year rollover can make a thirteenth month, which is a partition name
    that parses and a bound PostgreSQL refuses on the last day of the year."""
    assert Month(2999, 12).following() == Month(3000, 1)
    assert Month(2999, 12).end == datetime(3000, 1, 1, tzinfo=UTC)
    with pytest.raises(LedgerPartitionError):
        Month(2999, 13)


def test_a_partition_name_is_read_back_as_its_month_and_nothing_else_is() -> None:
    """The executor finds the months by name. Delete this and the default partition, or a table
    that merely starts with the ledger's name, can be read as a month and detached."""
    assert Month.named(Month(2999, 3).name) == Month(2999, 3)
    for other in ("request_telemetry_default", "request_telemetry_p29993", "request_telemetry"):
        assert Month.named(other) is None


# ====================================================================== which months exist
def test_the_months_ahead_cover_the_restore_window_across_a_year_end() -> None:
    """Made ahead from the partitioning module's own premake, which is sized so a restore from
    the oldest backup still has a partition for tomorrow. Delete this and the executor can make
    only the current month."""
    ahead = months_ahead(NOW)

    assert ahead == (Month(2999, 11), Month(2999, 12), Month(3000, 1), Month(3000, 2))
    assert len(ahead) == PREMAKE + 1
    # The months after the current one cover the whole backup window at their shortest.
    assert (len(ahead) - 1) * 28 >= BACKUP_RETENTION_DAYS


def test_a_month_leaves_only_when_its_newest_possible_row_is_past_the_horizon() -> None:
    """The removal is on the newest row, never the oldest. Delete this and a month can be detached
    while rows from its last days are still inside the ledger's window."""
    month = Month(2990, 1)
    exactly = month.end + timedelta(days=LEDGER_RETENTION_DAYS)

    assert detachable([month], exactly) == (month,)
    assert detachable([month], exactly - timedelta(microseconds=1)) == ()
    # Every row from the month's first day is past the horizon by then, and it still stays.
    assert month.start + timedelta(days=LEDGER_RETENTION_DAYS) < exactly - timedelta(days=1)
    assert detachable([month], exactly - timedelta(days=1)) == ()


# ===================================================================== what is said to SQL
def test_no_statement_this_module_can_issue_drops_or_truncates_anything() -> None:
    """The property `A_DETACH_KEEPS_EVERY_ROW` states, over every statement for a year of months.
    Delete this and a drop can be added to the detach step, and data past its horizon is gone
    without the release the retention executor waits for."""
    statements = plan_statements([Month(2999, one) for one in range(1, 13)])

    assert statements
    for statement in statements:
        words = statement.upper().split()
        assert "DROP" not in words and "TRUNCATE" not in words, statement
    assert "drops a table" in A_DETACH_KEEPS_EVERY_ROW


def test_the_only_delete_is_the_moves_and_it_takes_exactly_what_the_copy_took() -> None:
    """Delete this and the delete's predicate can differ from the copy's, which removes rows the
    month's partition never received."""
    month = Month(2999, 6)
    detach_default, create, secure, copy, delete, attach = (
        one.as_string(None) for one in move_statements(month)
    )
    predicate = copy.split(" WHERE ", 1)[1]

    copy_head = copy.split(" WHERE ", 1)[0]
    delete_head, delete_predicate = delete.split(" WHERE ", 1)
    assert copy_head == (
        'INSERT INTO "obs"."request_telemetry_p299906" '
        'SELECT * FROM "obs"."request_telemetry_default"'
    )
    assert delete_head == 'DELETE FROM "obs"."request_telemetry_default"'
    assert delete_predicate == predicate
    assert predicate == (
        f'"{CONTROL_COLUMN}" >= \'2999-06-01 00:00:00+00\' AND "{CONTROL_COLUMN}" < '
        "'2999-07-01 00:00:00+00'"
    )
    assert "DETACH PARTITION" in detach_default and "request_telemetry_default" in detach_default
    assert attach.endswith('ATTACH PARTITION "obs"."request_telemetry_default" DEFAULT')
    assert "FOR VALUES FROM ('2999-06-01 00:00:00+00') TO ('2999-07-01 00:00:00+00')" in create
    assert secure.endswith("ENABLE ROW LEVEL SECURITY")
    others = [one for one in plan_statements([month]) if one.upper().startswith("DELETE")]
    assert others == [delete]


def test_a_detach_names_the_month_and_never_the_default_partition() -> None:
    """Delete this and the detach can take the default partition away, after which every row for
    a month with no partition is refused at the door."""
    text = detach_statement(Month(2999, 6)).as_string(None)

    assert text == (
        'ALTER TABLE "obs"."request_telemetry" DETACH PARTITION "obs"."request_telemetry_p299906"'
    )


# ============================================================== the executor, with no server
class FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]], rowcount: int = 0) -> None:
        self.rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


class FakeInfo:
    transaction_status = pq.TransactionStatus.IDLE


class FakeLedger:
    """Answers the executor's reads from a script and records every statement it is sent."""

    def __init__(
        self,
        *,
        waiting: list[datetime],
        copied: int,
        deleted: int,
        attached: tuple[Month, ...] = (),
    ) -> None:
        self.info = FakeInfo()
        self.attached = attached
        self.waiting = waiting
        self.copied = copied
        self.deleted = deleted
        self.sent: list[str] = []
        self.rolled_back = 0

    @contextmanager
    def transaction(self) -> Iterator[None]:
        try:
            yield
        except Exception:
            self.rolled_back += 1
            raise

    def execute(self, query: object, params: object = None) -> FakeResult:
        text = query if isinstance(query, str) else cast(Any, query).as_string(None)
        self.sent.append(text)
        if text.startswith("SELECT to_regclass"):
            return FakeResult([(True, True)])
        if "pg_inherits" in text:
            return FakeResult([(one.name,) for one in self.attached])
        if "pg_namespace" in text:
            return FakeResult([])
        if text.startswith("SELECT DISTINCT date_trunc"):
            return FakeResult([(one,) for one in self.waiting])
        if text.startswith("SELECT EXISTS"):
            return FakeResult([(bool(self.waiting),)])
        if text.startswith("INSERT"):
            return FakeResult([], self.copied)
        if text.startswith("DELETE"):
            return FakeResult([], self.deleted)
        return FakeResult([])


def test_a_move_whose_copy_and_delete_disagree_raises_inside_its_transaction() -> None:
    """The one delete in the module is refused when it would remove a row the copy did not take.
    Raised inside the month's transaction, so the database rolls the delete back, and before the
    default partition is attached again. Delete this and a mismatch is logged and committed."""
    ledger = FakeLedger(waiting=[datetime(2999, 11, 1, tzinfo=UTC)], copied=3, deleted=4)

    with pytest.raises(LedgerPartitionError) as refused:
        maintain(cast(psycopg.Connection[Any], ledger), now=NOW, report_only=False)

    assert A_MOVE_IS_A_COPY_AND_A_DELETE_THAT_MUST_AGREE in str(refused.value)
    assert ledger.rolled_back == 1
    assert not any("ATTACH PARTITION" in one for one in ledger.sent)


def test_a_move_whose_counts_agree_attaches_the_default_again_and_says_how_many() -> None:
    """The positive half. Delete this and a check refusing every move passes the test above."""
    ledger = FakeLedger(waiting=[datetime(2999, 11, 1, tzinfo=UTC)], copied=3, deleted=3)

    done = maintain(cast(psycopg.Connection[Any], ledger), now=NOW, report_only=False)

    assert (Month(2999, 11), 3) in done.moved
    assert ledger.rolled_back == 0
    assert any("ATTACH PARTITION" in one and "DEFAULT" in one for one in ledger.sent)


def test_a_month_past_its_horizon_is_detached_only_once_the_sweep_is_released() -> None:
    """Report-only names the month and sends no detach; released sends exactly one, for that
    month. Delete this and the executor can detach before anybody released the retention sweep,
    which removes a month from every read of the ledger without the decision the release records."""
    old = Month(2990, 1)
    held = FakeLedger(waiting=[], copied=0, deleted=0, attached=(old, *months_ahead(NOW)))

    waiting = maintain(cast(psycopg.Connection[Any], held), now=NOW, report_only=True)

    assert waiting.awaiting_release == (old,)
    assert waiting.detached == ()
    assert not any("DETACH PARTITION" in one for one in held.sent)

    released = FakeLedger(waiting=[], copied=0, deleted=0, attached=(old, *months_ahead(NOW)))
    done = maintain(cast(psycopg.Connection[Any], released), now=NOW, report_only=False)

    assert done.detached == (old,)
    assert [one for one in released.sent if "DETACH PARTITION" in one] == [
        detach_statement(old).as_string(None)
    ]


def test_the_executor_refuses_a_connection_already_inside_a_transaction() -> None:
    """Every lock is meant to end with its month's commit. Delete this and a caller's open
    transaction holds the ledger's exclusive lock for the whole run, and every request waits."""
    ledger = FakeLedger(waiting=[], copied=0, deleted=0)
    ledger.info.transaction_status = pq.TransactionStatus.INTRANS

    with pytest.raises(LedgerPartitionError, match="inside a transaction"):
        maintain(cast(psycopg.Connection[Any], ledger), now=NOW, report_only=False)

    assert ledger.sent == []


def test_the_worker_runs_it_on_the_retention_sweeps_schedule_under_the_same_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ "By the worker": the retention sweep's runner is the one the general worker's schedule
    starts, and it calls `maintain` with the sweep's own report-only flag. Read from the source as
    well, the way `brain.ops.controls` reads every call site. Delete this and the executor can be
    left with no caller, which is where the scheme spent its first week."""
    calls: list[tuple[str, bool]] = []

    @contextmanager
    def connect(*_: object, **__: object) -> Iterator[object]:
        yield object()

    def swept(_conn: object, *, now: datetime, report_only: bool) -> str:
        calls.append(("sweep", report_only))
        return "metadata_ledger: swept"

    def partitioned(_conn: object, *, now: datetime, report_only: bool) -> Maintenance:
        calls.append(("partitions", report_only))
        return Maintenance(created=(Month(2999, 11),))

    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(schedule_runner, "run_retention_sweep", swept)
    monkeypatch.setattr(schedule_runner, "maintain_ledger_partitions", partitioned)

    said = schedule_runner.retention_sweep(NOW, True, "postgresql://u@h/db")

    assert calls == [("sweep", True), ("partitions", True)]
    assert said.splitlines()[-1].startswith("ledger partitions: created request_telemetry_p299911")
    assert call_sites("brain.ops.ledger_partitions:maintain") == ("brain.ops.schedule_runner",)
    assert runner_for("retention_sweep").run is not None


def test_a_detached_month_is_counted_by_the_retention_sweep_as_the_ledger() -> None:
    """A detached month is an ordinary table in `obs`, which four stores share. Delete this and
    the first detach, five years into an install, stops the retention sweep for every one of
    them with a table nobody attributed."""
    detached = f"obs.{Month(2990, 1).name}"

    class Catalogue:
        def execute(self, query: object, params: object = None) -> FakeResult:
            return FakeResult([("obs", "request_telemetry"), ("obs", Month(2990, 1).name)])

    sweeper = PostgresSweeper(cast(psycopg.Connection[Any], Catalogue()))

    assert declared_as(detached) == LEDGER
    assert declared_as(DEFAULT_PARTITION) == DEFAULT_PARTITION
    assert declared_as("ops.request_telemetry_p299001") == "ops.request_telemetry_p299001"
    assert detached in sweeper.tables_of(Store.LEDGER)
    assert sweeper._clock(detached) == CLOCKS[LEDGER]


# ======================================================================= against a server
INSERT_ROW = (
    "INSERT INTO obs.request_telemetry (received_at, trace_id, traffic_class, principal, "
    "entitlement_hash, lane, cache_hit, status, duration_ms) VALUES "
    "(%s, 't', 'system', 'u_one', '0123456789abcdef0123456789abcdef', 'fast', false, "
    "'answered', 1.0)"
)


@contextmanager
def a_ledger(database: str) -> Iterator[str]:
    """A fresh database with `0039` run for real on `0038` stamped, as the telemetry tests do."""
    url = fresh(database)
    try:
        migrate(database, "stamp", "0038")
        migrate(database, "upgrade", "0039")
        yield url
    finally:
        drop(database)


def partition_of(url: str, at: datetime) -> str:
    rows = sql(
        url,
        "SELECT tableoid::regclass::text FROM obs.request_telemetry WHERE received_at = %s",
        at,
    )
    assert len(rows) == 1, rows
    return str(rows[0][0])


def rows_in(url: str, qualified: str) -> int:
    """How many rows one table holds, named as `schema.table`."""
    schema, _, name = qualified.partition(".")
    with psycopg.connect(url, autocommit=True) as conn:
        row = conn.execute(
            psql.SQL("SELECT count(*) FROM {table}").format(table=psql.Identifier(schema, name))
        ).fetchone()
    assert row is not None
    return int(row[0])


def run_maintenance(url: str, *, now: datetime, report_only: bool) -> Maintenance:
    with psycopg.connect(url) as conn:
        return maintain(conn, now=now, report_only=report_only)


def test_rows_either_side_of_a_month_boundary_land_in_their_own_partitions() -> None:
    """On a real server: two rows already in the default partition are moved to their months, and
    a row written afterwards for a month made ahead goes straight to its partition. Delete this
    and nothing proves PostgreSQL routes the half-open bounds the way the pure tests say."""
    last = datetime(2999, 10, 31, 23, 59, 59, 999999, tzinfo=UTC)
    first = datetime(2999, 11, 1, tzinfo=UTC)
    ahead = datetime(3000, 2, 28, 23, 59, 59, 999999, tzinfo=UTC)
    with a_ledger("brain_test_ledger_partitions_boundary") as url:
        sql(url, INSERT_ROW, last)
        sql(url, INSERT_ROW, first)

        done = run_maintenance(url, now=NOW, report_only=True)
        sql(url, INSERT_ROW, ahead)

        assert partition_of(url, last) == f"obs.{Month(2999, 10).name}"
        assert partition_of(url, first) == f"obs.{Month(2999, 11).name}"
        assert partition_of(url, ahead) == f"obs.{Month(3000, 2).name}"
        assert dict(done.moved) == {Month(2999, 10): 1, Month(2999, 11): 1}
        assert rows_in(url, DEFAULT_PARTITION) == 0
        # The ledger's partitions read off `pg_inherits`, each with its row-level security. This
        # was `bool_and(relrowsecurity) FROM pg_class WHERE relname LIKE 'request_telemetry_p%'`
        # until 2026-09-17, which also matched every partition's primary key and indexes. An
        # index never has row-level security, so it was False on a correct schema.
        secured = dict(
            sql(
                url,
                "SELECT c.relname, c.relrowsecurity FROM pg_inherits AS i "
                "JOIN pg_class AS c ON c.oid = i.inhrelid WHERE i.inhparent = %s::regclass",
                LEDGER,
            )
        )
        made = {one.name for one in done.created} | {one.name for one, _ in done.moved}
        assert {Month(2999, 10).name, Month(2999, 11).name, Month(3000, 2).name} <= made
        assert secured == dict.fromkeys((*made, DEFAULT_PARTITION.partition(".")[2]), True)


def test_a_second_run_at_the_same_instant_changes_nothing() -> None:
    """Idempotent. Delete this and a run repeated after a worker restart can move rows twice or
    fail on a partition that already exists, and the retention sweep's run is recorded failed."""
    with a_ledger("brain_test_ledger_partitions_idempotent") as url:
        sql(url, INSERT_ROW, datetime(2999, 11, 3, tzinfo=UTC))
        run_maintenance(url, now=NOW, report_only=False)
        before = sql(url, "SELECT count(*) FROM obs.request_telemetry")

        again = run_maintenance(url, now=NOW, report_only=False)

        assert again == Maintenance()
        assert sql(url, "SELECT count(*) FROM obs.request_telemetry") == before == [(1,)]


def test_a_detach_keeps_every_row_and_waits_for_the_release() -> None:
    """The whole of the data-safety claim, on a real server. A month past its horizon stays
    attached in report-only mode; released, it leaves the live table and every row is still in
    its own table, which is still there, still secured, and counted. Delete this and a detach
    that dropped the table, or took the month before the release, passes."""
    old = datetime(2990, 1, 15, tzinfo=UTC)
    recent = datetime(2999, 11, 2, tzinfo=UTC)
    month = Month.of(old)
    with a_ledger("brain_test_ledger_partitions_detach") as url:
        for offset in range(3):
            sql(url, INSERT_ROW, old + timedelta(hours=offset))
        sql(url, INSERT_ROW, recent)

        waiting = run_maintenance(url, now=NOW, report_only=True)

        assert month in waiting.awaiting_release
        assert waiting.detached == ()
        assert sql(url, "SELECT count(*) FROM obs.request_telemetry") == [(4,)]

        released = run_maintenance(url, now=NOW, report_only=False)

        assert released.detached == (month,)
        assert sql(url, "SELECT count(*) FROM obs.request_telemetry") == [(1,)]
        assert rows_in(url, month.qualified) == 3
        assert sql(
            url,
            "SELECT relispartition, relrowsecurity FROM pg_class WHERE oid = %s::regclass",
            f"obs.{month.name}",
        ) == [(False, True)]

        # A late row for the detached month lands in the default partition, and the month is
        # not made again under a name its detached table already holds.
        sql(url, INSERT_ROW, old + timedelta(days=1))
        stranded = run_maintenance(url, now=NOW, report_only=False)

        assert stranded.stranded == (month,)
        assert rows_in(url, month.qualified) == 3
        assert rows_in(url, DEFAULT_PARTITION) == 1


def test_a_database_with_no_ledger_is_skipped_rather_than_failed() -> None:
    """The retention runner's own tests migrate to `0037`, before the ledger. Delete this and the
    runner fails on every database that predates `0039`."""
    with a_ledger("brain_test_ledger_partitions_none") as url:
        sql(url, "DROP TABLE obs.request_telemetry")

        done = run_maintenance(url, now=NOW, report_only=False)

        assert done.skipped
        assert done.summary().startswith("ledger partitions: ")
