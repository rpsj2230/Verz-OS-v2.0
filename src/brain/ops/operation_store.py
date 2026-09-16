"""The operation ledger in PostgreSQL: claim a key, win it once, settle it.

`brain.ops.idempotency` decides everything about an operation that can be wrong without a
database: how its key is derived, which moves its state may make, and the order `issue_once`
takes the steps in. This is `OperationLedger` over `ops.operation`, and it re-decides none of it:
every move is checked by `advance` before the statement that makes it, and the trigger `0051`
installs checks it again for whatever did not come through here.

**Each method is its own committed transaction, on a connection in autocommit mode.** A record
written inside the caller's transaction is rolled back with it, and a record rolled back after
the effect was issued is the window `THE_RECORD_IS_WRITTEN_BEFORE_THE_CALL` exists to close: the
next attempt finds no key and issues again. So the ledger refuses a connection that is not in
autocommit mode rather than trusting its callers to have opened one. See
`A_LEDGER_INSIDE_THE_CALLERS_TRANSACTION_FORGETS_WHAT_IT_ISSUED`.

**Claiming is an insert that does nothing on conflict, followed by a read.** Two attempts at one
intent both succeed at claiming, and both are told what the key holds. Which of them issues is
decided by `win`, an update conditional on the record still being pending, which the database
applies to one of them: the other's update matches no row. That pair is
`brain.ops.idempotency.THE_KEY_IS_CLAIMED_AND_THEN_WON`, and the unique key it rests on is the
primary key of `ops.operation`.

**A settle that finds the record already moved is refused, not repeated.** It means something
else moved the record between the win and the settle, which is either a second process holding
the same key or a hand edit, and in both cases the honest thing is to say so rather than write
over it.

What has never run: no PostgreSQL server was reachable where this was written, so every
statement below is exercised by `tests/unit/test_operation_store.py` against a server in CI and
by nothing on the machine that wrote it.

Task ids: M17.3.1
"""

from __future__ import annotations

from typing import Any, Final

import psycopg

from brain.ops.idempotency import (
    IdempotencyError,
    IllegalTransitionError,
    Operation,
    OperationState,
    advance,
)

#: Why the ledger refuses a connection that is not autocommitting.
A_LEDGER_INSIDE_THE_CALLERS_TRANSACTION_FORGETS_WHAT_IT_ISSUED: Final = (
    "The record has to be durable before the effect is issued, and a statement on a connection "
    "with an open transaction is durable only when that transaction commits. A caller that "
    "issues and then rolls back, or dies before committing, leaves no record of an effect that "
    "happened, and the next attempt issues it again. An autocommitting connection makes every "
    "method here a transaction of its own, which is the only arrangement where that cannot be "
    "forgotten by a caller."
)


def _record(row: tuple[Any, ...]) -> Operation:
    key, connector, tool, principal_id, intent_ref, state = row
    return Operation(
        key=key,
        connector=connector,
        tool=tool,
        principal_id=principal_id,
        intent_ref=intent_ref,
        state=OperationState(state),
    )


class PostgresOperationLedger:
    """`brain.ops.idempotency.OperationLedger` over `ops.operation`, one statement at a time."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        if not conn.autocommit:
            raise IdempotencyError(A_LEDGER_INSIDE_THE_CALLERS_TRANSACTION_FORGETS_WHAT_IT_ISSUED)
        self.conn = conn

    def claim(self, operation: Operation) -> Operation:
        """Record the intent pending if its key is new; answer the record the key holds."""
        with self.conn.transaction():
            self.conn.execute(
                "INSERT INTO ops.operation (key, connector, tool, principal_id, intent_ref, state) "
                "VALUES (%s, %s, %s, %s, %s, 'pending') ON CONFLICT (key) DO NOTHING",
                (
                    operation.key,
                    operation.connector,
                    operation.tool,
                    operation.principal_id,
                    operation.intent_ref,
                ),
            )
            row = self.conn.execute(
                "SELECT key, connector, tool, principal_id, intent_ref, state "
                "FROM ops.operation WHERE key = %s",
                (operation.key,),
            ).fetchone()
        if row is None:  # pragma: no cover - the insert or the conflict left a row to read
            msg = f"the key {operation.key[:16]!r} was claimed and holds no record"
            raise IdempotencyError(msg)
        return _record(row)

    def win(self, key: str) -> bool:
        """Move the record from pending to sent, for exactly one caller."""
        row = self.conn.execute(
            "UPDATE ops.operation SET state = 'sent', updated_at = statement_timestamp() "
            "WHERE key = %s AND state = 'pending' RETURNING key",
            (key,),
        ).fetchone()
        return row is not None

    def settle(self, key: str, *, frm: OperationState, to: OperationState) -> Operation:
        """Move the record from `frm` to `to`, or refuse because it is no longer in `frm`."""
        advance(frm, to)
        row = self.conn.execute(
            "UPDATE ops.operation SET state = %s, updated_at = statement_timestamp() "
            "WHERE key = %s AND state = %s "
            "RETURNING key, connector, tool, principal_id, intent_ref, state",
            (to.value, key, frm.value),
        ).fetchone()
        if row is None:
            msg = (
                f"the record under {key[:16]!r} is no longer {frm.value}, so it was not moved to "
                f"{to.value}: something else moved it first"
            )
            raise IllegalTransitionError(msg)
        return _record(row)
