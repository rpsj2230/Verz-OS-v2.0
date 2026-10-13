"""A trace step is removable by the application once it is thirty days old and not before.

Run on PostgreSQL at head: the policy `0232` writes admits a delete of a step past the window and of
nothing else, the application still cannot read a step, and the retention sweep, which asks the
catalogue whether the role may delete, now removes an expired step where it queued one.

Task ids: M25.1.3, M25.1.4
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from brain.ops.retention import PAYLOAD_RETENTION_DAYS, Store
from brain.ops.retention_store import PostgresSweeper
from brain.ops.tracing import MASKED_PAYLOADS, TraceRecord, retention_for

#: Far outside any plausible clock, because what is tested is the window and not the present.
LONG_AGO = datetime(2019, 1, 1, tzinfo=UTC)


def test_the_policy_names_the_window_the_trace_ledger_declares() -> None:
    """The thirty in the migration is the thirty declared in `tracing.RETENTION` and the payload
    store's own. Delete this and a window changed in one place leaves the policy admitting deletes
    of steps the declaration says are still kept, or refusing ones it says are due."""
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0232_payload_expiry.py"
    )
    spec = importlib.util.spec_from_file_location("payload_expiry_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert retention_for(TraceRecord.TRACE).days == migration.RETENTION_DAYS
    assert migration.RETENTION_DAYS == PAYLOAD_RETENTION_DAYS


@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    from tests.unit.test_acceptance import at_head

    with at_head("brain_trace_expiry") as url:
        yield url


def _step(conn: psycopg.Connection[tuple[object, ...]], trace: str, at: datetime) -> None:
    conn.execute(
        "INSERT INTO obs.trace_step (trace_id, step, parent, kind, name, attributes,"
        " payload_in, payload_out, recorded_at)"
        " VALUES (%s, 0, NULL, 'request', 'answer', '{}'::jsonb, %s, %s, %s)",
        (trace, MASKED_PAYLOADS[0], MASKED_PAYLOADS[0], at),
    )


@pytest.mark.needs_db
def test_the_application_deletes_a_step_past_the_window_and_no_other(head: str) -> None:
    """As the application role, an unqualified delete removes the expired step and leaves the one
    from yesterday, and the role still cannot read either. Delete this and the grant could widen to
    every step, which is the property `0150` is written to refuse."""
    now = datetime.now(UTC)
    with psycopg.connect(head) as conn:
        _step(conn, "payload-expiry-old", now - timedelta(days=PAYLOAD_RETENTION_DAYS + 1))
        _step(conn, "payload-expiry-new", now - timedelta(days=1))
        conn.execute("SET LOCAL ROLE brain_app")
        removed = conn.execute("DELETE FROM obs.trace_step").rowcount
        assert removed == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT trace_id FROM obs.trace_step")
        conn.rollback()
        conn.execute("RESET ROLE")
        _step(conn, "payload-expiry-old", LONG_AGO)
        _step(conn, "payload-expiry-new", now)
        conn.execute("SET LOCAL ROLE brain_app")
        assert conn.execute("DELETE FROM obs.trace_step").rowcount == 1
        conn.rollback()


@pytest.mark.needs_db
def test_the_sweep_removes_an_expired_step_now_and_keeps_a_fresh_one(head: str) -> None:
    """With the grant and the policy, `expire` removes the step past the window where it used to
    queue it, and leaves one from today. Delete this and the daily sweep goes on reporting a step
    due and removing none, which is the state this migration ends."""
    now = datetime.now(UTC)
    with psycopg.connect(head) as conn:
        _step(conn, "payload-sweep-old", now - timedelta(days=PAYLOAD_RETENTION_DAYS + 1))
        _step(conn, "payload-sweep-new", now - timedelta(days=1))
        sweeper = PostgresSweeper(conn)
        assert sweeper.removal_rule("obs.trace_step") == ""
        census = sweeper.census(Store.TRACE, now)
        assert (census.beyond_horizon, census.queued) == (1, 0)
        assert sweeper.expire(Store.TRACE, now) == 1
        left = conn.execute("SELECT trace_id FROM obs.trace_step").fetchall()
        assert left == [("payload-sweep-new",)]
        conn.rollback()
