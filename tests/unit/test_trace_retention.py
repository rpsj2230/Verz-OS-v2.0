"""The trace store is kept for its declared window: every table in `obs` has a store, and a step
past thirty days is what the sweep counts.

`brain.ops.tracing.RETENTION` declares how long a trace is kept and `brain.ops.retention` turns it
into the trace store's horizon, and neither reached a stored trace until `0150` gave the trace a
table. That table arrived in `obs`, which four stores share, with no attribution, and
`brain.ops.retention_store.store_tables` refuses every store sharing a schema that holds an
unattributed table, so the declaration would have stopped reaching anything on the deploy that
first wrote a trace. The first half holds every modelled table in a shared schema to an
attribution, read from the models rather than from a list, so the next table added to `obs` fails
here. The second half is the sweep over the schema at head: the four stores in `obs` are reached,
and a step recorded past the window is counted as due while a step from today is not.

Task ids: M32.1.1.3
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from brain.db import Base
from brain.ops.ledger_partitions import declared_as
from brain.ops.retention import STORES, TRACE_RETENTION_DAYS, Lifetime, Store, horizon_of
from brain.ops.retention_store import (
    A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO,
    ATTRIBUTED,
    CLOCKS,
    PostgresSweeper,
    store_tables,
)
from brain.ops.tracing import MASKED_PAYLOADS, TraceRecord, retention_for

#: Far outside any plausible wall clock, for the reason CLAUDE.md gives about fixtures that go off.
NOW = datetime(2999, 1, 1, tzinfo=UTC)

#: The stores that share `obs`, which is every store an unattributed table there refuses.
SHARING_OBS = tuple(one.store for one in STORES if "obs" in one.schemas)


def _shared_schemas() -> set[str]:
    """Every schema more than one store claims."""
    claims: dict[str, int] = {}
    for facts in STORES:
        for schema in facts.schemas:
            claims[schema] = claims.get(schema, 0) + 1
    return {schema for schema, count in claims.items() if count > 1}


# ------------------------------------------------------------------- without a server
def test_every_table_in_a_shared_schema_is_attributed() -> None:
    """Every modelled table in a schema two stores share names its store, and every one in a
    fixed-window store names the column its age is read from.

    Read from `Base.metadata` rather than from a list, because the defect this pins is a table
    nobody listed: `0150` put `obs.trace_step` and `obs.trace_read` in `obs` with no attribution,
    and `store_tables` would then have refused the ledger, trace, payload and audit stores for
    every retention run and every erasure. Delete this and the next table added to `obs` does the
    same with every other test green."""
    import brain.tables  # noqa: F401 - registers every table on the metadata
    from brain.tables.telemetry import TraceStepRow

    # Asserted, because an empty metadata would make the loop below pass while checking nothing.
    assert TraceStepRow.__table__ in Base.metadata.sorted_tables

    shared = _shared_schemas()
    assert "obs" in shared
    unattributed: list[str] = []
    unclocked: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.schema not in shared:
            continue
        name = declared_as(table.fullname)
        store = ATTRIBUTED.get(name)
        if store is None:
            unattributed.append(name)
        elif horizon_of(store).lifetime is Lifetime.FIXED_WINDOW and name not in CLOCKS:
            unclocked.append(name)
    assert unattributed == []
    assert unclocked == []


def test_a_trace_step_is_the_trace_stores_and_a_read_of_one_is_the_audit_stores() -> None:
    """`obs.trace_step` belongs to the trace store, aged by `recorded_at`; `obs.trace_read` to the
    audit store, aged by `at`; and the trace store's window is the one `tracing.RETENTION` declares
    for a trace.

    Spelled out because either placement is a decision: a step is the shape of a run and never its
    content in the clear, which is what the trace store holds and not what the payload store
    holds; and who read a trace is kept as long as the audit ledger, which
    `brain.ops.erasure_store.RETAINED` already argues. Delete this and a step could move to a
    store with another window, or a read could expire with the trace it accounts for."""
    assert ATTRIBUTED["obs.trace_step"] is Store.TRACE
    assert CLOCKS["obs.trace_step"] == "recorded_at"
    assert ATTRIBUTED["obs.trace_read"] is Store.AUDIT
    assert CLOCKS["obs.trace_read"] == "at"
    assert horizon_of(Store.TRACE).days == retention_for(TraceRecord.TRACE).days
    assert horizon_of(Store.AUDIT).lifetime is Lifetime.NEVER_EXPIRES


# ---------------------------------------------------------------------- with a server
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    from tests.unit.test_acceptance import at_head

    with at_head("brain_trace_retention") as url:
        yield url


def _step(conn: psycopg.Connection[tuple[object, ...]], trace: str, at: datetime) -> None:
    """One request step, as `TraceRecorder` writes one, recorded at `at`."""
    conn.execute(
        "INSERT INTO obs.trace_step (trace_id, step, parent, kind, name, attributes,"
        " payload_in, payload_out, recorded_at)"
        " VALUES (%s, 0, NULL, 'request', 'answer', '{}'::jsonb, %s, %s, %s)",
        (trace, MASKED_PAYLOADS[0], MASKED_PAYLOADS[0], at),
    )


@pytest.mark.needs_db
def test_the_stores_in_obs_are_reached_at_head_and_a_step_past_its_window_is_due(
    head: str,
) -> None:
    """At head, every store sharing `obs` lists its tables without refusing, the trace store holds
    `obs.trace_step`, and its census counts a step recorded past thirty days as due and one from
    today as not, queued behind the migration that grants the application no DELETE.

    Delete this and the attribution could be right in the mapping and wrong against the schema a
    migration actually builds, which is the only place the sweep reads."""
    with psycopg.connect(head) as conn:
        for store in SHARING_OBS:
            store_tables(conn, store)
        assert "obs.trace_step" in store_tables(conn, Store.TRACE)
        assert "obs.trace_read" in store_tables(conn, Store.AUDIT)

        _step(conn, "trace-retention-old", NOW - timedelta(days=TRACE_RETENTION_DAYS + 1))
        _step(conn, "trace-retention-new", NOW - timedelta(days=1))
        census = PostgresSweeper(conn).census(Store.TRACE, NOW)
        conn.rollback()

    assert census.beyond_horizon == 1
    assert census.queued == 1
    assert A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO in census.queued_because
