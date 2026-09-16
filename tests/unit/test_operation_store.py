"""The operation ledger in PostgreSQL: one record per key, won once, moved only by the machine.

Two halves. Without a server: the migration's copy of the transition table and of the settled
states against `brain.ops.idempotency`'s own, and the ledger's refusal of a connection that would
hold its writes in somebody else's transaction. With one: `ops.operation` built by `0051` itself,
the leaf asserted through `PostgresOperationLedger` rather than a stand-in, two connections racing
for one key, and the trigger refusing a move the machine has no edge for.

The server half did not run where this was written: no PostgreSQL could be started there. CI runs
it.

Task ids: M17.3.1
"""

from __future__ import annotations

import importlib.util
import types
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from brain.connectors.throttle import CallOutcome
from brain.ops.idempotency import (
    ALLOWED_TRANSITIONS,
    TERMINAL,
    IdempotencyError,
    IllegalTransitionError,
    Intent,
    Operation,
    OperationState,
    issue_once,
    operation_for,
)
from brain.ops.operation_store import (
    A_LEDGER_INSIDE_THE_CALLERS_TRANSACTION_FORGETS_WHAT_IT_ISSUED,
    PostgresOperationLedger,
)
from tests.fixtures.scratch_postgres import drop, fresh, migrate, sql

MIGRATION = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0051_operation_ledger.py"
)


def _migration() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("operation_ledger_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _operation(intent_ref: str = "turn_1", *, to: str = "oc_room") -> Operation:
    return operation_for(
        Intent(principal_id="u_weiling", intent_ref=intent_ref),
        connector="lark",
        tool="lark.send",
        arguments={"to": to},
    )


# ------------------------------------------------------------------ without a server
def test_the_trigger_admits_exactly_the_moves_the_machine_has_edges_for() -> None:
    """The migration copies the transition table rather than importing it, so the copy is held
    to the original here.

    Delete this and an edge added to `ALLOWED_TRANSITIONS` would be refused by the database with
    every Python test green, or an edge removed would still be admitted to a hand edit."""
    declared = {
        (frm.value, to.value) for frm, onward in ALLOWED_TRANSITIONS.items() for to in onward
    }

    assert set(_migration().TRANSITIONS) == declared


def test_the_update_policy_locks_exactly_the_states_the_machine_calls_settled() -> None:
    """Delete this and a settled record could be moved by the application role once somebody
    adds a terminal state to the machine and not to the policy."""
    assert set(_migration().SETTLED) == {state.value for state in TERMINAL}


def test_the_migration_grants_no_removal_and_no_edit_of_what_a_record_describes() -> None:
    """Delete this and a DELETE grant, or an UPDATE on the key, would let a record be removed or
    repointed, and the next attempt at its intent would issue again."""
    grants = _migration().GRANTS

    assert all("DELETE" not in one for one in grants)
    assert "GRANT UPDATE (state, updated_at) ON ops.operation TO brain_app" in grants
    assert all("UPDATE (" not in one or "key" not in one for one in grants)


class _Connection:
    """The one attribute the ledger reads before anything else."""

    def __init__(self, *, autocommit: bool) -> None:
        self.autocommit = autocommit


def test_a_ledger_refuses_a_connection_whose_writes_wait_for_somebody_elses_commit() -> None:
    """And accepts one that commits each statement.

    Delete this and a caller holding a transaction open across the effect would lose the record
    of an effect it issued the moment it rolled back."""
    with pytest.raises(IdempotencyError) as refused:
        PostgresOperationLedger(_Connection(autocommit=False))  # type: ignore[arg-type]

    assert str(refused.value) == A_LEDGER_INSIDE_THE_CALLERS_TRANSACTION_FORGETS_WHAT_IT_ISSUED
    assert PostgresOperationLedger(_Connection(autocommit=True)).conn is not None  # type: ignore[arg-type]


# ------------------------------------------------------------------------ with a server
@pytest.fixture
def server() -> Iterator[str]:
    """A database holding `ops.operation` as `0051` builds it, and nothing it does not need."""
    database = "brain_operation_ledger_check"
    url = fresh(database)
    try:
        migrate(database, "stamp", "0050")
        migrate(database, "upgrade", "0051")
        yield url
    finally:
        drop(database)


def _ledger(url: str) -> Iterator[PostgresOperationLedger]:
    with psycopg.connect(url, autocommit=True) as conn:
        yield PostgresOperationLedger(conn)


def test_a_repeated_operation_with_the_same_key_has_its_effect_once_in_postgresql(
    server: str,
) -> None:
    """**The leaf, against the table.** Three attempts, one effect, one row, succeeded.

    Delete this and the store's insert could raise on a duplicate instead of answering the record,
    or its read could answer the attempt instead of the row, and the stand-in would not show it."""
    runs: list[str] = []

    def effect(operation: Operation) -> CallOutcome:
        runs.append(operation.key)
        return CallOutcome.OK

    for ledger in _ledger(server):
        results = [issue_once(ledger, _operation(), effect) for _ in range(3)]

    assert len(runs) == 1
    assert [one.issued for one in results] == [True, False, False]
    assert sql(server, "SELECT state FROM ops.operation") == [("succeeded",)]


def test_a_different_key_has_its_own_effect_in_postgresql(server: str) -> None:
    """The sibling. Delete this and a store keyed on something coarser than the key would pass the
    test above and send one message where two were meant."""
    runs: list[str] = []

    def effect(operation: Operation) -> CallOutcome:
        runs.append(operation.key)
        return CallOutcome.OK

    for ledger in _ledger(server):
        issue_once(ledger, _operation(), effect)
        issue_once(ledger, _operation(to="oc_other"), effect)
        issue_once(ledger, _operation("turn_2"), effect)

    assert len(set(runs)) == 3
    assert sql(server, "SELECT count(*) FROM ops.operation") == [(3,)]


def test_two_connections_claiming_one_key_both_see_the_record_and_only_one_wins(
    server: str,
) -> None:
    """The race the unique key and the conditional move exist for, with two real connections.

    Delete this and a store whose win was an unconditional update would let both workers issue."""
    operation = _operation()
    with (
        psycopg.connect(server, autocommit=True) as first,
        psycopg.connect(server, autocommit=True) as second,
    ):
        one, two = PostgresOperationLedger(first), PostgresOperationLedger(second)
        assert one.claim(operation).state is OperationState.PENDING
        assert two.claim(operation).state is OperationState.PENDING
        wins = [one.win(operation.key), two.win(operation.key)]

    assert wins == [True, False]
    assert sql(server, "SELECT state FROM ops.operation") == [("sent",)]


def test_a_settle_that_finds_the_record_already_moved_is_refused(server: str) -> None:
    """Delete this and a settle racing another settle would write over it."""
    operation = _operation()
    for ledger in _ledger(server):
        ledger.claim(operation)
        ledger.win(operation.key)
        ledger.settle(operation.key, frm=OperationState.SENT, to=OperationState.UNKNOWN)
        with pytest.raises(IllegalTransitionError, match="no longer sent"):
            ledger.settle(operation.key, frm=OperationState.SENT, to=OperationState.SUCCEEDED)
        with pytest.raises(IllegalTransitionError):
            ledger.settle(operation.key, frm=OperationState.UNKNOWN, to=OperationState.PENDING)

    assert sql(server, "SELECT state FROM ops.operation") == [("unknown",)]


def test_the_database_refuses_a_move_the_machine_has_no_edge_for_and_a_repointed_record(
    server: str,
) -> None:
    """Straight to the table, as a person with a session would: unknown back to pending, and a
    record given another intent, are both refused; an edge the machine has is admitted.

    Delete this and the second issue the machine forbids could be made by an UPDATE nobody
    reviewed."""
    operation = _operation()
    for ledger in _ledger(server):
        ledger.claim(operation)
        ledger.win(operation.key)
        ledger.settle(operation.key, frm=OperationState.SENT, to=OperationState.UNKNOWN)

    with pytest.raises(psycopg.errors.RaiseException, match="cannot move from unknown to pending"):
        sql(server, "UPDATE ops.operation SET state = 'pending'")
    with pytest.raises(psycopg.errors.RaiseException, match="cannot be repointed"):
        sql(server, "UPDATE ops.operation SET intent_ref = 'turn_9'")
    sql(server, "UPDATE ops.operation SET state = 'verifying'")

    assert sql(server, "SELECT state, intent_ref FROM ops.operation") == [("verifying", "turn_1")]


def test_a_record_that_is_not_a_derived_key_or_not_a_state_is_refused_by_the_table(
    server: str,
) -> None:
    """Delete this and a minted identifier could be stored as a key, which is the idempotency that
    changes on every retry."""
    with pytest.raises(psycopg.errors.CheckViolation):
        sql(
            server,
            "INSERT INTO ops.operation (key, connector, tool, principal_id, intent_ref, state) "
            "VALUES ('not-a-digest', 'lark', 'lark.send', 'u_1', 'turn_1', 'pending')",
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        sql(
            server,
            "INSERT INTO ops.operation (key, connector, tool, principal_id, intent_ref, state) "
            "VALUES (%s, 'lark', 'lark.send', 'u_1', 'turn_1', 'maybe')",
            _operation().key,
        )
