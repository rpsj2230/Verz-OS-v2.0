"""The one door every side effect goes through: claimed, won once, issued, settled.

`brain.ops.idempotency.issue_once` over `tests.fixtures.operation_ledger.MemoryLedger`, which has
the same three answers `brain.ops.operation_store.PostgresOperationLedger` gives and no
connection. What is under test is the order of the steps and what each outcome leaves in the
ledger; that the database's own key and conditional update give the same answers under a real
race is `tests/unit/test_operation_store.py`'s, against a server.

The leaf's own sentence is the first pair: **a repeated operation with the same key has its
effect once, and a different key has its own.**

Task ids: M17.3.1
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from brain.connectors.throttle import CallOutcome
from brain.core.envelope import IdentityMode, SideEffect, ToolDefinition
from brain.ops.idempotency import (
    Disposition,
    IdempotencyError,
    Intent,
    Operation,
    OperationState,
    assert_no_side_effect,
    derive_key,
    issue_once,
    operation_for,
)
from tests.fixtures.operation_ledger import MemoryLedger

INTENT = Intent(principal_id="u_weiling", intent_ref="run_2026_09_16")


def _operation(intent: Intent = INTENT, *, to: str = "oc_room") -> Operation:
    return operation_for(intent, connector="lark", tool="lark.send", arguments={"to": to})


class _Effect:
    """Counts how often it ran, and answers or raises as it was told to."""

    def __init__(self, *, answers: CallOutcome = CallOutcome.OK, raises: bool = False) -> None:
        self.runs: list[Operation] = []
        self.answers = answers
        self.raises = raises

    def __call__(self, operation: Operation) -> CallOutcome:
        self.runs.append(operation)
        if self.raises:
            raise TimeoutError("the answer did not come back")
        return self.answers


# ------------------------------------------------------------------ the leaf
def test_a_repeated_operation_with_the_same_key_has_its_effect_once() -> None:
    """Three attempts at one intent: one effect, one record, settled as succeeded, and the two
    repeats told the record is done.

    Delete this and a retried delivery is two messages, which is the whole of M17.3.1."""
    ledger = MemoryLedger()
    effect = _Effect()

    results = [issue_once(ledger, _operation(), effect) for _ in range(3)]

    assert len(effect.runs) == 1
    assert [one.issued for one in results] == [True, False, False]
    assert len(ledger.records) == 1
    assert results[0].operation.state is OperationState.SUCCEEDED
    assert all(
        one.resumption is not None and one.resumption.disposition is Disposition.DONE
        for one in results[1:]
    )


def test_a_different_key_has_its_own_effect() -> None:
    """The positive sibling. Another destination, and another intent, are each issued.

    Delete this and a door that issued the first operation it ever saw and nothing after would
    pass the test above."""
    ledger = MemoryLedger()
    effect = _Effect()
    tomorrow = Intent(principal_id="u_weiling", intent_ref="run_2026_09_17")

    issued = [
        issue_once(ledger, _operation(), effect),
        issue_once(ledger, _operation(to="oc_other"), effect),
        issue_once(ledger, _operation(tomorrow), effect),
    ]

    assert [one.issued for one in issued] == [True, True, True]
    assert len({one.key for one in effect.runs}) == 3
    assert ledger.issued() == 3


def test_the_effect_is_handed_the_record_as_sent_so_it_runs_after_the_write() -> None:
    """Delete this and the effect could run before the record says a request may have left,
    which is the window `THE_RECORD_IS_WRITTEN_BEFORE_THE_CALL` exists to close."""
    ledger = MemoryLedger()
    seen: list[OperationState] = []

    def effect(operation: Operation) -> CallOutcome:
        seen.append(operation.state)
        seen.append(ledger.records[operation.key].state)
        return CallOutcome.OK

    issue_once(ledger, _operation(), effect)

    assert seen == [OperationState.SENT, OperationState.SENT]


# ------------------------------------------------------------------ racing and crashing
def test_a_second_worker_that_loses_the_win_issues_nothing() -> None:
    """Both workers claim a pending record; the ledger lets one of them win. The loser is told
    what the record holds and does not issue.

    Delete this and the two-workers case `WHAT_THE_CRASH_MODEL_DOES_NOT_COVER` names would issue
    twice whenever both found the record pending."""

    class Raced(MemoryLedger):
        def win(self, key: str) -> bool:
            # The other worker won between this one's claim and its win.
            super().win(key)
            return False

    ledger = Raced()
    effect = _Effect()

    result = issue_once(ledger, _operation(), effect)

    assert effect.runs == []
    assert result.issued is False
    assert result.operation.state is OperationState.SENT
    assert result.resumption is not None
    assert result.resumption.disposition is Disposition.VERIFY


def test_a_pending_record_left_by_a_crash_before_the_win_is_issued_once() -> None:
    """The record was written and nothing was issued: the next attempt issues, and the one after
    does not.

    Delete this and a crash between claiming and winning would leave an operation that never
    happens, because every later attempt would treat pending as taken."""
    ledger = MemoryLedger()
    ledger.claim(_operation())
    effect = _Effect()

    first = issue_once(ledger, _operation(), effect)
    second = issue_once(ledger, _operation(), effect)

    assert (first.issued, second.issued) == (True, False)
    assert len(effect.runs) == 1


def test_an_effect_that_raises_leaves_the_record_unknown_and_is_not_issued_again() -> None:
    """A timeout is a request that may have landed. The record is unknown, the exception carries
    on, and the next attempt verifies rather than issuing.

    Delete this and a retry after a timeout sends twice, which is `UNKNOWN_IS_NOT_FAILED`."""
    ledger = MemoryLedger()
    effect = _Effect(raises=True)

    with pytest.raises(TimeoutError):
        issue_once(ledger, _operation(), effect)
    again = issue_once(ledger, _operation(), _Effect())

    assert ledger.records[_operation().key].state is OperationState.UNKNOWN
    assert again.issued is False
    assert again.resumption is not None
    assert again.resumption.disposition is Disposition.VERIFY


def test_a_refusal_the_source_stated_settles_as_failed_and_is_not_retried_by_the_door() -> None:
    """Delete this and a stated refusal could be settled as success, or retried as a new send."""
    ledger = MemoryLedger()

    refused = issue_once(ledger, _operation(), _Effect(answers=CallOutcome.REJECTED))
    again = issue_once(ledger, _operation(), _Effect())

    assert refused.operation.state is OperationState.FAILED
    assert again.issued is False
    assert again.resumption is not None
    assert again.resumption.disposition is Disposition.STOP


def test_an_outcome_no_write_can_have_leaves_the_record_unknown_and_raises() -> None:
    """A truncated result set is a read's outcome. The effect ran, so the record is unknown
    rather than left sent, and the mistake is raised.

    Delete this and a caller classifying a write as a read would leave the record sent, which a
    recovering worker would read correctly and a person reading the table would not."""
    ledger = MemoryLedger()

    with pytest.raises(IdempotencyError):
        issue_once(ledger, _operation(), _Effect(answers=CallOutcome.TRUNCATED))

    assert ledger.records[_operation().key].state is OperationState.UNKNOWN


def test_a_key_held_by_a_record_of_another_intent_is_refused_and_nothing_is_issued() -> None:
    """Delete this and a collision, or a record edited by hand, would issue somebody else's
    effect under their key."""

    class Forged(MemoryLedger):
        def claim(self, operation: Operation) -> Operation:
            return replace(operation, principal_id="u_somebody_else")

    effect = _Effect()

    with pytest.raises(IdempotencyError, match="different intent"):
        issue_once(Forged(), _operation(), effect)
    assert effect.runs == []


@pytest.mark.parametrize("part", ["connector", "tool", "intent_ref"])
def test_every_part_of_the_intent_is_compared_against_the_record_the_key_holds(part: str) -> None:
    """Delete this and the comparison could drop one field, so a record for another tool under a
    colliding key would be issued as this one."""

    class Forged(MemoryLedger):
        def claim(self, operation: Operation) -> Operation:
            changed: dict[str, Any] = {part: "something_else"}
            return replace(operation, **changed)

    with pytest.raises(IdempotencyError):
        issue_once(Forged(), _operation(), _Effect())


# ------------------------------------------------------------------ the key and the guard
def test_an_operation_is_keyed_by_the_same_derivation_a_connector_tool_is() -> None:
    """`operation_for` and `derive_key` agree, so a channel send and a connector write are keyed
    by one function.

    Delete this and a second derivation could appear for sends, which is a second place for the
    key to include a clock."""
    operation = _operation()

    assert operation.key == derive_key(
        principal_id="u_weiling",
        tool="lark.send",
        intent_ref="run_2026_09_16",
        arguments={"to": "oc_room"},
    )
    assert (operation.connector, operation.tool, operation.principal_id, operation.intent_ref) == (
        "lark",
        "lark.send",
        "u_weiling",
        "run_2026_09_16",
    )
    assert operation.state is OperationState.PENDING


def _tool(effect: SideEffect) -> ToolDefinition:
    return ToolDefinition(
        name="invoice.send_reminder",
        description="a tool",
        entity="invoice",
        required_capability="write:invoice.status",
        side_effect=effect,
        identity_mode=IdentityMode.DELEGATED,
    )


@pytest.mark.parametrize("effect", [one for one in SideEffect if one is not SideEffect.NONE])
def test_a_path_with_no_ledger_refuses_every_tool_that_declares_a_side_effect(
    effect: SideEffect,
) -> None:
    """Delete this and `assert_no_side_effect` could admit a sending tool, and the invariant that
    trusts it would admit the unkeyed call after it."""
    with pytest.raises(IdempotencyError, match=effect.value):
        assert_no_side_effect(_tool(effect))


def test_a_path_with_no_ledger_calls_a_tool_that_changes_nothing() -> None:
    """The positive sibling. Delete this and a guard refusing every tool passes the test above."""
    assert_no_side_effect(_tool(SideEffect.NONE))
