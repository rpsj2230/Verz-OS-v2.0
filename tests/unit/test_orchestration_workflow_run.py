"""Running a workflow: named outputs, conditions, parallel steps, retries and failure paths.

The door is a script that answers each step from a table and remembers every call, which is where
a step's arguments, its key and its attempts are seen. Everything else is the engine.

Task ids: M17.6.2, M17.6.3, M17.6.4, M17.6.5, M17.6.6, M17.6.7
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable, Coroutine, Mapping
from typing import Any

from brain.orchestration.workflow import Definition, read_definition
from brain.orchestration.workflow_run import (
    REPEATED_FAILURES_BEFORE_A_CANDIDATE,
    Cause,
    Outcome,
    RunRecord,
    Status,
    StepCall,
    StepFailedError,
    StepRefusedError,
    StepResult,
    repeats,
    run_workflow,
    signal_of,
)


def _sync(test: Callable[[], Coroutine[Any, Any, None]]) -> Callable[[], None]:
    @functools.wraps(test)
    def runner() -> None:
        asyncio.run(test())

    return runner


class Door:
    """Answers `script[step]` (a record, a list of records, or an exception per attempt)."""

    def __init__(self, script: Mapping[str, Any], *, writes: bool = False) -> None:
        self.script = dict(script)
        self.calls: list[StepCall] = []
        self.writes = writes
        self.running = 0
        self.most_at_once = 0
        self.pause = 0.0

    @property
    def writes_offered(self) -> bool:
        return self.writes

    async def carry_out(self, call: StepCall) -> StepResult:
        self.calls.append(call)
        self.running += 1
        self.most_at_once = max(self.most_at_once, self.running)
        try:
            if self.pause:
                await asyncio.sleep(self.pause)
            given = self.script[call.step_id]
            if isinstance(given, list):
                given = given[min(call.attempt, len(given)) - 1]
            if isinstance(given, Exception):
                raise given
            return StepResult(records=(dict(given),))
        finally:
            self.running -= 1

    def for_step(self, step: str) -> list[StepCall]:
        return [one for one in self.calls if one.step_id == step]


def _step(step_id: str, *after: str, **more: Any) -> dict[str, Any]:
    return {
        "id": step_id,
        "kind": "tool",
        "target": "alpha.read_beta",
        "after": list(after),
        "outputs": [{"name": "n", "kind": "integer", "path": "n"}],
        **more,
    }


def _definition(*steps: dict[str, Any]) -> Definition:
    return read_definition({"name": "w", "steps": list(steps)})


async def _run(definition: Definition, door: Door, sleeps: list[float] | None = None) -> RunRecord:
    async def sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return await run_workflow(
        run_id="r1",
        workflow_id="monthly",
        version=3,
        agent_id="lead",
        definition=definition,
        door=door,
        sleep=sleep,
    )


def _by(record: RunRecord) -> dict[str, Any]:
    return {one.step_id: one for one in record.steps}


@_sync
async def test_a_step_is_handed_the_declared_outputs_it_references_and_nothing_else() -> None:
    """Delete this and a step can be handed an earlier result's other fields, or none.

    The first step returns a field it never declared; the second references the declared one and
    receives that value only.
    """
    definition = _definition(
        _step("first"),
        _step("second", "first", arguments={"count": {"$ref": "first.n"}, "month": "2026-09"}),
    )
    door = Door({"first": {"n": 7, "secret": "x"}, "second": {"n": 8}})
    record = await _run(definition, door)
    assert record.outcome is Outcome.SUCCESS and record.failed_step is None
    assert dict(door.for_step("second")[0].arguments) == {"count": 7, "month": "2026-09"}
    assert "secret" not in repr(door.calls[1].arguments)


@_sync
async def test_an_output_that_is_missing_or_of_the_wrong_kind_fails_the_step_without_a_retry() -> (
    None
):
    """Delete this and a malformed result is retried for ever, or passed on as a value."""
    for given in ({}, {"n": "seven"}, {"n": True}):
        definition = _definition(_step("first", retry={"limit": 2}))
        door = Door({"first": given})
        record = await _run(definition, door)
        assert _by(record)["first"].cause is Cause.INVALID_OUTPUT
        assert len(door.calls) == 1
    ok = await _run(_definition(_step("first")), Door({"first": {"n": 7}}))
    assert ok.outcome is Outcome.SUCCESS


@_sync
async def test_a_step_whose_input_was_never_produced_does_not_run() -> None:
    """Delete this and a step runs on a guess when the step it reads failed."""
    definition = _definition(
        _step("first", on_failure="continue"),
        _step("second", "first", arguments={"count": {"$ref": "first.n"}}, on_failure="continue"),
    )
    door = Door({"first": StepRefusedError(), "second": {"n": 1}})
    record = await _run(definition, door)
    assert _by(record)["second"].cause is Cause.INPUT_MISSING
    assert door.for_step("second") == []
    assert record.outcome is Outcome.PARTIAL


@_sync
async def test_a_condition_runs_or_skips_a_step_and_a_skip_says_which_condition() -> None:
    """Delete this and a step runs whatever the condition, or a skip names nothing."""
    when = {"ref": "first.n", "op": "gt", "value": 100}
    definition = _definition(_step("first"), _step("second", "first", when=when))
    skipped = await _run(definition, Door({"first": {"n": 5}, "second": {"n": 1}}))
    one = _by(skipped)["second"]
    assert (one.status, one.cause, one.detail) == (
        Status.SKIPPED,
        Cause.CONDITION_NOT_MET,
        "first.n gt 100",
    )
    assert skipped.outcome is Outcome.SUCCESS
    door = Door({"first": {"n": 500}, "second": {"n": 1}})
    ran = await _run(definition, door)
    assert _by(ran)["second"].status is Status.OK and len(door.for_step("second")) == 1


@_sync
async def test_a_condition_over_an_output_nobody_produced_skips_and_says_so() -> None:
    """Delete this and a condition is decided over a value that does not exist."""
    definition = _definition(
        _step("first", on_failure="continue"),
        _step("second", "first", when={"ref": "first.n", "op": "is_true"}),
    )
    record = await _run(definition, Door({"first": StepRefusedError()}))
    assert _by(record)["second"].cause is Cause.INPUT_MISSING


@_sync
async def test_parallel_steps_start_together_and_the_join_waits_and_records_the_gap() -> None:
    """Delete this and parallel steps run in turn, a failing sibling cancels the other, or the join
    starts before both have finished.

    Two parallel steps wait on each other (they only finish if both started), one of them fails,
    and the step that follows them runs after both and records the failure as a gap.
    """
    barrier = asyncio.Barrier(2)

    class Waiting(Door):
        async def carry_out(self, call: StepCall) -> StepResult:
            if call.step_id in ("a", "b"):
                await asyncio.wait_for(barrier.wait(), timeout=2)
            return await super().carry_out(call)

    definition = _definition(
        _step("a", parallel=True, on_failure="continue"),
        _step("b", parallel=True),
        _step("join", "a", "b"),
    )
    door = Waiting({"a": StepRefusedError(), "b": {"n": 2}, "join": {"n": 3}})
    record = await _run(definition, door)
    by = _by(record)
    assert (by["a"].status, by["a"].cause) == (Status.FAILED, Cause.REFUSED)
    assert by["b"].status is Status.OK and by["join"].status is Status.OK
    assert [c.step_id for c in door.calls][-1] == "join"
    assert record.outcome is Outcome.PARTIAL and record.failed_step == "a"


@_sync
async def test_steps_not_marked_parallel_run_one_after_another() -> None:
    """Delete this and every wave runs together whatever the author said."""
    definition = _definition(_step("a"), _step("b"), _step("c"))
    door = Door({"a": {"n": 1}, "b": {"n": 1}, "c": {"n": 1}})
    door.pause = 0.01
    await _run(definition, door)
    assert door.most_at_once == 1


@_sync
async def test_a_transient_failure_is_retried_with_the_same_key_and_a_growing_wait() -> None:
    """Delete this and a retry is a different operation to the far end, or waits no time."""
    definition = _definition(_step("a", retry={"limit": 3, "backoff_seconds": 2}))
    door = Door({"a": [StepFailedError(), RuntimeError("down"), {"n": 1}]})
    sleeps: list[float] = []
    record = await _run(definition, door, sleeps)
    assert _by(record)["a"].attempts == 3 and record.outcome is Outcome.SUCCESS
    assert {c.idempotency_key for c in door.calls} == {"r1:a"}
    assert [c.attempt for c in door.calls] == [1, 2, 3]
    assert sleeps == [2.0, 4.0]


@_sync
async def test_a_step_that_uses_its_retries_takes_its_failure_path() -> None:
    """Delete this and a step that never succeeds is retried for ever or ends the run unrecorded."""
    definition = _definition(_step("a", retry={"limit": 1}))
    door = Door({"a": StepFailedError()})
    record = await _run(definition, door)
    assert (_by(record)["a"].cause, _by(record)["a"].attempts) == (Cause.FAILED_AFTER_RETRIES, 2)
    assert len(door.calls) == 2


@_sync
async def test_a_refusal_is_never_retried() -> None:
    """Delete this and a step the gate refused is asked again and again."""
    definition = _definition(_step("a", retry={"limit": 3}))
    door = Door({"a": StepRefusedError()})
    record = await _run(definition, door)
    assert _by(record)["a"].cause is Cause.REFUSED and len(door.calls) == 1


@_sync
async def test_a_step_that_changes_something_is_retried_only_through_its_key() -> None:
    """Delete this and a write is refused by a door that offers none, or retried under a new key."""
    definition = _definition(_step("a", writes=True, retry={"limit": 1}))
    refused = await _run(definition, Door({"a": {"n": 1}}, writes=False))
    assert _by(refused)["a"].cause is Cause.WRITE_NOT_OFFERED
    door = Door({"a": [StepFailedError(), {"n": 1}]}, writes=True)
    record = await _run(definition, door)
    assert record.outcome is Outcome.SUCCESS
    assert [c.idempotency_key for c in door.calls] == ["r1:a", "r1:a"]


@_sync
async def test_a_stop_ends_the_run_and_every_later_step_says_so() -> None:
    """Delete this and the steps after a stop run, or are missing from the trace."""
    definition = _definition(_step("a"), _step("b", "a"), _step("c", "b"))
    door = Door({"a": StepRefusedError(), "b": {"n": 1}, "c": {"n": 1}})
    record = await _run(definition, door)
    assert record.outcome is Outcome.FAILURE and record.failed_step == "a"
    assert [(s.step_id, s.cause) for s in record.steps[1:]] == [
        ("b", Cause.RUN_STOPPED),
        ("c", Cause.RUN_STOPPED),
    ]
    assert [c.step_id for c in door.calls] == ["a"]


@_sync
async def test_a_continue_records_a_gap_and_the_run_goes_on() -> None:
    """Delete this and one failed step costs the run the steps that do not need it."""
    definition = _definition(_step("a", on_failure="continue"), _step("b"))
    record = await _run(definition, Door({"a": StepRefusedError(), "b": {"n": 1}}))
    assert record.outcome is Outcome.PARTIAL and _by(record)["b"].status is Status.OK


@_sync
async def test_a_handler_runs_only_when_the_step_it_handles_failed() -> None:
    """Delete this and a handler runs on every run, or never."""
    definition = _definition(
        _step("a", on_failure="handler"),
        _step("fallback", "a", handles="a"),
    )
    failed = Door({"a": StepRefusedError(), "fallback": {"n": 1}})
    record = await _run(definition, failed)
    assert _by(record)["fallback"].status is Status.OK and record.outcome is Outcome.PARTIAL
    fine = Door({"a": {"n": 1}, "fallback": {"n": 1}})
    record = await _run(definition, fine)
    assert _by(record)["fallback"].cause is Cause.HANDLER_NOT_NEEDED
    assert fine.for_step("fallback") == [] and record.outcome is Outcome.SUCCESS


@_sync
async def test_a_trace_holds_statuses_and_words_and_no_value() -> None:
    """Delete this and the trace becomes a second copy of what the run read."""
    definition = _definition(
        _step("a"), _step("b", "a", when={"ref": "a.n", "op": "gt", "value": 9})
    )
    record = await _run(definition, Door({"a": {"n": 123456}, "b": {"n": 1}}))
    assert "123456" not in repr(record)


def test_a_signal_names_the_workflow_the_agent_and_the_first_step_that_failed() -> None:
    """Delete this and a failure says only that it failed."""
    definition = _definition(_step("a", on_failure="continue"), _step("b", on_failure="continue"))
    record = asyncio.run(_run(definition, Door({"a": StepRefusedError(), "b": StepRefusedError()})))
    signal = signal_of(record)
    assert (signal.workflow_id, signal.agent_id, signal.outcome, signal.failed_step) == (
        "monthly",
        "lead",
        "failure",
        "a",
    )
    ok = asyncio.run(_run(_definition(_step("a")), Door({"a": {"n": 1}})))
    assert signal_of(ok).outcome == "success" and signal_of(ok).failed_step is None


def test_a_step_that_fails_in_each_of_the_last_runs_is_a_repeat_and_one_that_does_not_is_not() -> (
    None
):
    """Delete this and a candidate opens on one bad night, or never."""
    failing = frozenset({"a"})
    n = REPEATED_FAILURES_BEFORE_A_CANDIDATE
    assert repeats([failing] * n, "a")
    assert not repeats([failing] * (n - 1), "a")
    assert not repeats([failing, frozenset(), failing], "a")
    assert not repeats([failing] * n, "b")
    assert repeats([failing] * (n + 4), "a")
