"""The request ledger's questions from people the directory placed nowhere, read at head.

`brain.ops.telemetry_store.unplaced_rows` is the read that makes the Usage screen count what the
Dashboard counts. Found on the owner's install on 2026-09-29: ten requests in the ledger, no row in
`ops.question_asked`, and Usage said nought, because every asker there had no department. The
statement is run against a database migrated to head, in a transaction rolled back after, so the
join to the principal table, the traffic class and the absence of a question row are each proved
against the real tables rather than as text.

Dates are 2999, far from any wall clock, because nothing here is about the present.

Task ids: M27.7.14
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from brain.ops.telemetry_store import unplaced_rows

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
NOW = datetime(2999, 6, 15, 12, 0, tzinfo=UTC)
HASH = "0" * 32


@pytest.fixture
def head() -> Iterator[str]:
    from tests.unit.test_decision_entries import at_head

    with at_head("brain_test_m27714_unplaced") as url:
        yield url


def test_a_persons_question_with_no_question_row_is_read_and_nothing_else_is(head: str) -> None:
    """Four requests in the window: a person's with no question row, which is read; a person's
    with one, a schedule's, and a stranger's, which are not; and one outside the window.

    Delete this and the read could count automation, count a question twice, or count an asker
    this install does not hold, with every screen test green because they hand the rows in."""
    import psycopg

    statement = unplaced_rows(NOW - timedelta(days=7), NOW).compile(
        dialect=DIALECT, compile_kwargs={"render_postcompile": True}
    )
    insert = (
        "INSERT INTO obs.request_telemetry (received_at, trace_id, traffic_class, principal,"
        " entitlement_hash, lane, cache_hit, status, duration_ms)"
        " VALUES (%s, %s, %s, %s, %s, 'answer', false, 'answered', 10)"
    )
    with psycopg.connect(head) as conn, conn.transaction(force_rollback=True):
        conn.execute("SELECT set_config('brain.actor_id', 'u_setup', true)")
        conn.execute("SELECT set_config('brain.trace_id', 'trace-unplaced', true)")
        for pid in ("u_owner", "u_placed"):
            conn.execute(
                "INSERT INTO auth.principal (id, kind, employment, display_name)"
                " VALUES (%s, 'human', 'staff', %s)",
                (pid, pid),
            )
        conn.execute(
            "INSERT INTO ops.question_asked"
            " (trace_id, principal_id, principal_kind, channel, department, at)"
            " VALUES ('t-placed', 'u_placed', 'human', 'console', 'support', %s)",
            (NOW - timedelta(hours=1),),
        )
        rows = [
            (NOW - timedelta(hours=2), "t-owner", "human_interactive", "u_owner"),
            (NOW - timedelta(hours=2), "t-owner", "human_interactive", "u_owner"),
            (NOW - timedelta(hours=1), "t-placed", "human_interactive", "u_placed"),
            (NOW - timedelta(hours=1), "t-schedule", "automation", "u_owner"),
            (NOW - timedelta(hours=1), "t-stranger", "human_interactive", "u_nobody"),
            (NOW - timedelta(days=9), "t-old", "human_interactive", "u_owner"),
        ]
        for at, trace, traffic, pid in rows:
            conn.execute(insert, (at, trace, traffic, pid, HASH))
        found = conn.execute(str(statement), statement.params).fetchall()

    assert [(trace, pid, traffic) for trace, pid, traffic, _ in found] == [
        ("t-owner", "u_owner", "human_interactive")
    ]
