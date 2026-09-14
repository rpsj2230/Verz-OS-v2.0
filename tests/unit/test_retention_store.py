"""The retention executor: what it counts, what it removes, and every store it will not touch.

Two halves. Without a server: `retention.sweep` over a sweeper that reports whatever a test
tells it to, so the run's own refusals can be shown to fire. With one: `PostgresSweeper` in a
database this file creates, with a fixed-window table attributed to the trace store so there is
something old enough to remove, which the real estate does not have yet.

Every removal test has a sibling that proves the rows which must survive did.

Task ids: M25.1.5
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from brain.ops.retention import (
    ONLY_A_CLOCK_IS_ENFORCED_BY_AGE,
    TRACE_RETENTION_DAYS,
    RetentionError,
    Store,
    StoreCensus,
    sweep,
)
from brain.ops.retention_store import (
    A_HOLD_THIS_CANNOT_MATCH_TO_A_ROW_STOPS_THE_SWEEP,
    A_RECORD_LIFETIME_NEEDS_A_SUBJECT_REFERENCE_NOBODY_HAS_DECLARED,
    A_TABLE_IN_A_SHARED_SCHEMA_BELONGS_TO_NOBODY_UNTIL_IT_IS_ATTRIBUTED,
    ATTRIBUTED,
    NOT_HELD_IN_POSTGRES,
    PostgresSweeper,
    attribution_gaps,
    run_retention_sweep,
)
from tests.fixtures.scratch_postgres import drop, fresh, sql

#: Far outside any plausible wall clock.
NOW = datetime(2999, 1, 1, tzinfo=UTC)
OLD = NOW - timedelta(days=TRACE_RETENTION_DAYS + 10)
YOUNG = NOW - timedelta(days=TRACE_RETENTION_DAYS - 10)

TRACE_TABLE = "obs.scratch_trace"


# ------------------------------------------------------------------- without a server
@dataclass
class Scripted:
    """A sweeper that answers each store with what the test scripted, and records removals."""

    answers: dict[Store, StoreCensus | RetentionError]
    expired: list[Store] = field(default_factory=list)

    def census(self, store: Store, now: datetime) -> StoreCensus:
        answer = self.answers.get(store, RetentionError("not scripted"))
        if isinstance(answer, RetentionError):
            raise answer
        return answer

    def expire(self, store: Store, now: datetime) -> int:
        self.expired.append(store)
        census = self.answers[store]
        assert isinstance(census, StoreCensus)
        return census.due


def test_a_store_the_sweeper_cannot_count_is_named_with_its_reason() -> None:
    """The refusal's message is on the report beside "not reached", and the run is incomplete.

    Delete this and a refused store could be dropped from the report with its reason, leaving an
    operator told the run was incomplete and nothing about what would complete it."""
    report = sweep(
        Scripted({Store.TRACE: StoreCensus(store=Store.TRACE, beyond_horizon=0)}),
        now=NOW,
        report_only=True,
    )
    assert report.complete is False
    assert "ledger: not counted, because not scripted" in report.findings
    assert Store.TRACE not in report.unreached()
    assert not any(one.startswith("trace:") for one in report.findings)


def test_a_fixed_window_with_items_due_is_expired_and_the_removal_is_reported() -> None:
    """Delete this and `sweep` could count forever and remove nothing, with a clean report."""
    sweeper = Scripted({Store.TRACE: StoreCensus(store=Store.TRACE, beyond_horizon=4, held=1)})
    report = sweep(sweeper, now=NOW, report_only=False)

    assert sweeper.expired == [Store.TRACE]
    assert "trace: 3 removed" in report.findings


def test_report_only_removes_nothing_and_says_so() -> None:
    """Delete this and a control released for reporting would delete on its first run."""
    sweeper = Scripted({Store.TRACE: StoreCensus(store=Store.TRACE, beyond_horizon=4)})
    report = sweep(sweeper, now=NOW, report_only=True)

    assert sweeper.expired == []
    assert "trace: 4 due and none removed, report only" in report.findings


def test_a_census_claiming_a_lifetime_without_a_clock_has_items_due_removes_nothing() -> None:
    """The audit store and a record-lifetime store both report items due; neither is expired.

    Delete this and a sweeper that miscounted the audit chain would cut it on the next run."""
    sweeper = Scripted(
        {
            Store.AUDIT: StoreCensus(store=Store.AUDIT, beyond_horizon=2),
            Store.MEMORY: StoreCensus(store=Store.MEMORY, beyond_horizon=5),
        }
    )
    report = sweep(sweeper, now=NOW, report_only=False)

    assert sweeper.expired == []
    assert any(ONLY_A_CLOCK_IS_ENFORCED_BY_AGE in one for one in report.findings)
    assert any("never expires" in one for one in report.findings)


def test_a_removal_larger_than_the_count_is_a_finding() -> None:
    """Delete this and an executor removing rows the census never counted reads as a clean run."""

    class Overreaching(Scripted):
        def expire(self, store: Store, now: datetime) -> int:
            return 9

    report = sweep(
        Overreaching({Store.TRACE: StoreCensus(store=Store.TRACE, beyond_horizon=2)}),
        now=NOW,
        report_only=False,
    )
    assert any("disagree about what was past its window" in one for one in report.findings)


def test_the_shipped_attributions_point_at_stores_that_claim_their_schemas() -> None:
    """Clean as shipped, and a table attributed to a store outside its schema is a finding.

    Delete this and `obs.audit_entry` attributed to the rows store would never be read, and the
    table would refuse every store sharing `obs`."""
    assert attribution_gaps() == ()
    assert attribution_gaps({"obs.audit_entry": Store.ROWS}, {}, {})
    assert attribution_gaps(ATTRIBUTED, {"nowhere.table": "at"}, {})


# ------------------------------------------------------------------------ with a server
@dataclass(frozen=True)
class AHold:
    """The three things `brain.ops.erasure.Hold` reads."""

    subjects: frozenset[str] = frozenset()
    all_subjects: bool = False
    active: bool = True

    def is_active(self, now: datetime | None = None) -> bool:
        return self.active


@pytest.fixture
def server() -> Iterator[str]:
    """A database with the schemas `0001` leaves, a trace-class table, an audit table, and a
    table in the one-store `ops` schema."""
    database = "brain_retention_store_check"
    url = fresh(database)
    try:
        sql(url, f"CREATE TABLE {TRACE_TABLE} (at timestamptz NOT NULL, subject text NOT NULL)")
        sql(url, "CREATE TABLE obs.audit_entry (at timestamptz NOT NULL)")
        sql(url, "CREATE TABLE ops.something (at timestamptz NOT NULL)")
        for at, subject in ((OLD, "u_one"), (OLD, "u_two"), (YOUNG, "u_one")):
            sql(url, "INSERT INTO obs.scratch_trace VALUES (%s, %s)", at, subject)
        sql(url, "INSERT INTO obs.audit_entry VALUES (%s)", NOW - timedelta(days=4000))
        yield url
    finally:
        drop(database)


def a_sweeper(conn: psycopg.Connection[tuple[object, ...]], **overrides: object) -> PostgresSweeper:
    declared: dict[str, object] = {
        "attributed": {**ATTRIBUTED, TRACE_TABLE: Store.TRACE},
        "clocks": {"obs.audit_entry": "at", TRACE_TABLE: "at"},
        "subjects": {TRACE_TABLE: "subject"},
    }
    declared.update(overrides)
    return PostgresSweeper(conn, **declared)  # type: ignore[arg-type]


def remaining(url: str) -> list[tuple[object, ...]]:
    return sql(url, "SELECT subject, at FROM obs.scratch_trace ORDER BY subject, at")


def test_rows_past_a_fixed_window_are_removed_and_younger_rows_are_kept(server: str) -> None:
    """Two rows forty days old go, one twenty days old stays, and the census counted two.

    Delete this and the executor could delete by the wrong comparison, or by no clock at all,
    and nothing else here would see a row go."""
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn)
        census = sweeper.census(Store.TRACE, NOW)
        assert census.beyond_horizon == 2
        assert census.oldest_days == TRACE_RETENTION_DAYS + 10
        report = sweep(sweeper, now=NOW, report_only=False)
        conn.commit()

    assert "trace: 2 removed" in report.findings
    assert remaining(server) == [("u_one", YOUNG)]


def test_a_held_subjects_rows_are_counted_as_held_and_survive_the_sweep(server: str) -> None:
    """A hold on u_two: one of the two old rows is held, one is removed.

    Delete this and a legal hold would be honoured by the report and ignored by the delete."""
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn, holds=(AHold(subjects=frozenset({"u_two"})),))
        census = sweeper.census(Store.TRACE, NOW)
        assert (census.beyond_horizon, census.held) == (2, 1)
        sweep(sweeper, now=NOW, report_only=False)
        conn.commit()

    assert remaining(server) == [("u_one", YOUNG), ("u_two", OLD)]


def test_a_hold_over_every_subject_removes_nothing_and_a_lifted_hold_does_not_count(
    server: str,
) -> None:
    """Delete this and a company-wide hold, the one issued in litigation, protects nobody."""
    with psycopg.connect(server) as conn:
        assert a_sweeper(conn, holds=(AHold(all_subjects=True),)).expire(Store.TRACE, NOW) == 0
        held = a_sweeper(conn, holds=(AHold(all_subjects=True),)).census(Store.TRACE, NOW)
        assert held.held == 2
        lifted = a_sweeper(conn, holds=(AHold(all_subjects=True, active=False),))
        assert lifted.census(Store.TRACE, NOW).held == 0
        conn.rollback()
    assert len(remaining(server)) == 3


def test_a_hold_that_cannot_be_matched_to_rows_refuses_the_store_and_removes_nothing(
    server: str,
) -> None:
    """A subject hold over a table with no declared subject column: the trace store is not
    reached, nothing is removed, and the report says why.

    Delete this and a hold would be skipped for any table nobody had described, which is every
    table added after the hold was written."""
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn, subjects={}, holds=(AHold(subjects=frozenset({"u_two"})),))
        report = sweep(sweeper, now=NOW, report_only=False)
        conn.commit()

    assert Store.TRACE in report.unreached()
    with psycopg.connect(server) as conn:
        assert a_sweeper(conn, subjects={}).census(Store.TRACE, NOW).beyond_horizon == 2
    assert any(A_HOLD_THIS_CANNOT_MATCH_TO_A_ROW_STOPS_THE_SWEEP in one for one in report.findings)
    assert len(remaining(server)) == 3


def test_an_unattributed_table_in_a_shared_schema_refuses_every_store_sharing_it(
    server: str,
) -> None:
    """The shipped attributions do not know the scratch table: every `obs` store is unreached
    and nothing is removed.

    Delete this and the metadata ledger arriving in `obs` unattributed could be swept on the
    trace store's thirty days."""
    with psycopg.connect(server) as conn:
        report = sweep(PostgresSweeper(conn), now=NOW, report_only=False)
        conn.commit()

    assert {Store.LEDGER, Store.TRACE, Store.PAYLOAD, Store.AUDIT} <= set(report.unreached())
    assert any(
        A_TABLE_IN_A_SHARED_SCHEMA_BELONGS_TO_NOBODY_UNTIL_IT_IS_ATTRIBUTED in one
        for one in report.findings
    )
    assert len(remaining(server)) == 3


def test_a_fixed_window_table_with_no_clock_refuses_the_store(server: str) -> None:
    """Delete this and a table with no declared clock would be skipped, and kept forever."""
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn, clocks={"obs.audit_entry": "at"})
        with pytest.raises(RetentionError, match="declares no clock column"):
            sweeper.census(Store.TRACE, NOW)
        with pytest.raises(RetentionError, match="declares no clock column"):
            sweeper.expire(Store.TRACE, NOW)


def test_the_audit_store_is_reached_with_nothing_due_and_its_age_reported(server: str) -> None:
    """A row eleven years old in a class that never expires: nothing due, the age visible, and
    `expire` refuses outright.

    Delete this and the audit store could be counted on some window, or left unreached, and a
    chain that stopped growing would have no age anywhere."""
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn)
        census = sweeper.census(Store.AUDIT, NOW)
        assert (census.beyond_horizon, census.oldest_days) == (0, 4000)
        assert a_sweeper(conn, clocks={}).census(Store.AUDIT, NOW).oldest_days is None
        with pytest.raises(RetentionError, match="only a fixed window"):
            sweeper.expire(Store.AUDIT, NOW)
    assert sql(server, "SELECT count(*) FROM obs.audit_entry") == [(1,)]


def test_record_lifetime_stores_and_stores_outside_postgres_are_refused_by_name(
    server: str,
) -> None:
    """`ops` holds a table and is a record-lifetime store; the recordings bucket is not in
    PostgreSQL. Both refuse with their reasons, and the table in `ops` keeps its row.

    Delete this and either could be reported as reached with nothing due, which is a clean line
    for a store nobody counted."""
    sql(server, "INSERT INTO ops.something VALUES (%s)", OLD)
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(conn)
        with pytest.raises(RetentionError) as operations:
            sweeper.census(Store.OPERATIONS, NOW)
        with pytest.raises(RetentionError) as recordings:
            sweeper.census(Store.RECORDING, NOW)
        run_retention_sweep(conn, now=NOW, report_only=False)

    assert str(operations.value) == A_RECORD_LIFETIME_NEEDS_A_SUBJECT_REFERENCE_NOBODY_HAS_DECLARED
    assert str(recordings.value) == NOT_HELD_IN_POSTGRES
    assert sql(server, "SELECT count(*) FROM ops.something") == [(1,)]


def test_a_scheduled_run_returns_one_line_per_store_and_commits_its_removals(server: str) -> None:
    """`run_retention_sweep` over the shipped declarations, with the scratch table dropped so
    `obs` is attributable: the ledger, trace, payload and audit stores are reached, the rest are
    named, and the text carries a line for every store.

    Delete this and the entry point a scheduler calls could return before its transaction
    commits, or return the census without the report."""
    sql(server, f"DROP TABLE {TRACE_TABLE}")
    with psycopg.connect(server) as conn:
        text = run_retention_sweep(conn, now=NOW, report_only=False)

    lines = text.splitlines()
    for store in Store:
        assert any(line.startswith(f"{store.value}") for line in lines), store
    assert "ledger (metadata_ledger, 1825d): 0 due, 0 held" in lines
    assert "audit (audit, never_expires): 0 due, 0 held, oldest 4000d" in lines
    assert "recording: not reached, so nothing in it was considered" in lines


def test_the_oldest_age_is_the_oldest_row_across_every_table_a_store_holds(server: str) -> None:
    """A second trace-class table holding only a young row, read after the first: the store's
    oldest age is still the old row's.

    Delete this and the comparison across tables could keep the last table's minimum, so a store
    with one stale table and one busy one would report the busy one's age."""
    sql(server, "CREATE TABLE obs.scratch_trace_young (at timestamptz NOT NULL)")
    sql(server, "INSERT INTO obs.scratch_trace_young VALUES (%s)", YOUNG)
    young = "obs.scratch_trace_young"
    with psycopg.connect(server) as conn:
        sweeper = a_sweeper(
            conn,
            attributed={**ATTRIBUTED, TRACE_TABLE: Store.TRACE, young: Store.TRACE},
            clocks={"obs.audit_entry": "at", TRACE_TABLE: "at", young: "at"},
        )
        census = sweeper.census(Store.TRACE, NOW)
    assert (census.beyond_horizon, census.oldest_days) == (2, TRACE_RETENTION_DAYS + 10)
