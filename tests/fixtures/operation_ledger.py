"""An `OperationLedger` in a dictionary, for tests that are not about the database.

`brain.ops.operation_store.PostgresOperationLedger` is the ledger, and
`tests/unit/test_operation_store.py` runs it against a server. Everything else that issues a side
effect needs a ledger to be called at all, and most of those tests are about a channel's refusals
or a digest's wording, so they get this: the same three answers, the same refusal of a move the
state machine has no edge for, and no connection.

It keeps every move it was asked to make, so a test can assert on what was claimed and settled
rather than only on what came out.
"""

from __future__ import annotations

from brain.ops.idempotency import (
    IllegalTransitionError,
    Operation,
    OperationState,
    advance,
)


class MemoryLedger:
    """`claim`, `win` and `settle` over a dictionary keyed like `ops.operation`."""

    def __init__(self) -> None:
        self.records: dict[str, Operation] = {}
        self.moves: list[tuple[str, OperationState]] = []

    def claim(self, operation: Operation) -> Operation:
        return self.records.setdefault(operation.key, operation)

    def win(self, key: str) -> bool:
        record = self.records[key]
        if record.state is not OperationState.PENDING:
            return False
        self.records[key] = record.advanced(OperationState.SENT)
        self.moves.append((key, OperationState.SENT))
        return True

    def settle(self, key: str, *, frm: OperationState, to: OperationState) -> Operation:
        advance(frm, to)
        record = self.records[key]
        if record.state is not frm:
            msg = f"the record is {record.state.value}, not {frm.value}"
            raise IllegalTransitionError(msg)
        self.records[key] = record.advanced(to)
        self.moves.append((key, to))
        return self.records[key]

    def issued(self) -> int:
        """How many records reached SENT, which is how many effects were issued."""
        return sum(1 for _, state in self.moves if state is OperationState.SENT)
