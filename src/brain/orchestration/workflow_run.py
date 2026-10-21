"""Running a workflow: each step through a door, outputs named and checked, and one trace.

`brain.orchestration.workflow` reads a definition. This runs it. **The engine decides order,
conditions, retries and what a failure does, and decides nothing about reach**: every step goes
through a `StepDoor`, which in production is the gate's own path for a tool call
(`brain.workflow_routes.GateDoor`: `call_piece`, the projected catalogue at the run's reach, the
field policy and the redactor), so a step is judged exactly as an agent's own call is and this
module has no `intersect` and no list of what a run may touch.

**What a step returns reaches the next step only as the outputs it declared** (M17.6.3). The door
hands back the redacted records; the engine takes each declared output from the first record by its
path, checks it against its kind with the contract's own `value_refusals`, and keeps only those. A
value that is missing or of the wrong kind makes the step a stated failure, not a retry, because the
same call will return the same shape. A step that reads an output that was never produced fails
with `input_missing` and never runs on a guess.

**A condition skips a step and the trace says which** (M17.6.4). A skipped step is recorded with
the cause and the condition's words as the definition wrote them. The output values the condition
compared are never in the trace: the trace is statuses, causes and the definition's own text, so a
person can follow a run without the run being a second copy of the data it read.

**Parallel steps start together and the step that follows them waits for each** (M17.6.5). A wave's
`parallel` steps run in one `gather`; each catches its own failure, so one failing never cancels its
siblings, and the following wave starts only when every one has finished or been recorded as a gap.

**A retry reuses the key** (M17.6.6). Every call carries `{run}:{step}` as its idempotency key and
the same on every attempt, so a step that changes something and is retried is the same operation to
the far end. A step marked `writes` is refused (`write_not_offered`) by a door that does not offer
writes, which is the gate's own: `brain.workflow_routes.GateDoor` runs with an empty leash, under
which a workflow reads, and a write waits for the day a held action from an unattended run has been
shown to reach the right person (the same reason `brain.ops.automation_owner` gives). A refusal is
never retried. Back-off is `backoff * attempt`, bounded by the definition's own limit.

**The failure path is the definition's.** A step that has used its retries stops the run, is
recorded as a gap and the run goes on, or hands over to the step that handles it. The handler runs
only then and is otherwise recorded as not needed. After a stop every step that has not run is
recorded as skipped because the run stopped, so the trace always names every step.

**Repeated failure of one step is a learning candidate and never a change to the workflow**
(M17.6.7). `repeats` says whether a step has failed in each of the last runs. What is done with that
is `brain.ops.quality_store.open_candidates`, which opens a row for a person to decide, and nothing
here or there edits a definition: a workflow that changed itself after failing would be an agent
rewriting its own procedure with nobody deciding.

Task ids: M17.6.2, M17.6.3, M17.6.4, M17.6.5, M17.6.6, M17.6.7
"""

from __future__ import annotations

import asyncio
import enum
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

import structlog

from brain.orchestration.contract import FieldKind, FieldSpec, value_refusals
from brain.orchestration.workflow import (
    Condition,
    Definition,
    OnFailure,
    Op,
    Ref,
    Step,
    StepKind,
)

log = structlog.get_logger()

#: How many runs in a row a step must fail in before a candidate is opened for a person.
REPEATED_FAILURES_BEFORE_A_CANDIDATE: Final = 3

#: Why a step's reads are the declared outputs and nothing else.
A_TRACE_HOLDS_STATUSES_AND_NEVER_VALUES: Final = (
    "A run's trace names every step with a status, a cause from a closed list and, for a skipped "
    "step, the condition as the definition wrote it. It holds no output value, no argument and no "
    "record, so it is not a second copy of what the run read under permissions of its own."
)


class Outcome(enum.StrEnum):
    """How a run ended. `partial` is a run that went on past a step recorded as a gap."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


class Status(enum.StrEnum):
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


class Cause(enum.StrEnum):
    """Why a step did not complete. Closed, so a trace cannot carry a value or a message."""

    CONDITION_NOT_MET = "condition_not_met"
    HANDLER_NOT_NEEDED = "handler_not_needed"
    RUN_STOPPED = "run_stopped"
    INPUT_MISSING = "input_missing"
    REFUSED = "refused"
    FAILED_AFTER_RETRIES = "failed_after_retries"
    INVALID_OUTPUT = "invalid_output"
    WRITE_NOT_OFFERED = "write_not_offered"


@dataclass(frozen=True)
class StepCall:
    """What the door is handed for one attempt of one step."""

    run_id: str
    step_id: str
    kind: StepKind
    target: str
    arguments: Mapping[str, object]
    #: The same on every attempt of the step, so a retry is the same operation to the far end.
    idempotency_key: str
    attempt: int


@dataclass(frozen=True)
class StepResult:
    """The records a step's tool returned, already through the redactor."""

    records: tuple[Mapping[str, object], ...]


class StepRefusedError(Exception):
    """The gate refused the step: the reach did not cover it, the tool is not there, the arguments
    are not taken. One refusal for all of them, and never retried."""


class StepFailedError(Exception):
    """The step could not be completed this time (a source down, a timeout). Retried."""


class StepDoor(Protocol):
    """Whatever runs one step through the gate. The engine knows no more of it than this."""

    @property
    def writes_offered(self) -> bool: ...

    async def call(self, call: StepCall) -> StepResult: ...


Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class StepRecord:
    """One step of the trace."""

    step_id: str
    status: Status
    cause: Cause | None = None
    #: A skipped step's condition in the definition's words; empty otherwise.
    detail: str = ""
    attempts: int = 0
    seconds: float = 0.0


@dataclass(frozen=True)
class RunRecord:
    """A finished run: how it ended, the first step that failed, and every step."""

    run_id: str
    workflow_id: str
    version: int
    agent_id: str
    outcome: Outcome
    failed_step: str | None
    steps: tuple[StepRecord, ...]
    finished_at: datetime | None = None


@dataclass(frozen=True)
class RunSignal:
    """What a finished run tells whoever is listening: success or failure, and where it failed."""

    workflow_id: str
    agent_id: str
    run_id: str
    #: `success` or `failure`. A run that went on past a gap is a failure that names its step.
    outcome: str
    failed_step: str | None


def signal_of(record: RunRecord) -> RunSignal:
    """The signal a run emits when it finishes (M17.6.7). It names the workflow, the agent and the
    first step that failed, in the definition's order."""
    return RunSignal(
        workflow_id=record.workflow_id,
        agent_id=record.agent_id,
        run_id=record.run_id,
        outcome="success" if record.outcome is Outcome.SUCCESS else "failure",
        failed_step=record.failed_step,
    )


def repeats(failed_steps_by_run: Sequence[frozenset[str]], step_id: str) -> bool:
    """Whether this step failed in each of the last runs, newest first, and there were enough.

    Fewer runs than the threshold is not a repeat, however they ended, and a run in which the step
    did not fail ends the streak.
    """
    recent = failed_steps_by_run[:REPEATED_FAILURES_BEFORE_A_CANDIDATE]
    return len(recent) == REPEATED_FAILURES_BEFORE_A_CANDIDATE and all(
        step_id in one for one in recent
    )


# ------------------------------------------------------------------------------ the engine
def _compare(condition: Condition, value: object) -> bool:
    op = condition.op
    if op is Op.IS_TRUE:
        return value is True
    if op is Op.IS_FALSE:
        return value is False
    wanted = condition.value
    if op is Op.EQ:
        return value == wanted
    if op is Op.NE:
        return value != wanted
    if isinstance(value, bool) or isinstance(wanted, bool):
        return False
    if isinstance(value, (int, float)) and isinstance(wanted, (int, float)):
        pair: tuple[float, float] = (float(value), float(wanted))
    elif isinstance(value, str) and isinstance(wanted, str):
        return {Op.GT: value > wanted, Op.GE: value >= wanted, Op.LT: value < wanted}.get(
            op, value <= wanted
        )
    else:
        return False
    left, right = pair
    return {Op.GT: left > right, Op.GE: left >= right, Op.LT: left < right}.get(op, left <= right)


def _value_at(record: Mapping[str, object], path: str) -> tuple[bool, object]:
    """The value a path names in a first record: a field, or an index and a field."""
    return (True, record[path]) if path in record else (False, None)


def _outputs_of(step: Step, result: StepResult) -> dict[str, object] | None:
    """The declared outputs of a step out of its result, or None when one is missing or wrong."""
    taken: dict[str, object] = {}
    for out in step.outputs:
        index, _, field_name = out.path.rpartition(".")
        position = int(index) if index else 0
        if position >= len(result.records):
            return None
        found, value = _value_at(result.records[position], field_name)
        if not found:
            return None
        if out.kind is FieldKind.TIMESTAMP and isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return None
        if value_refusals(FieldSpec(name=out.name, kind=out.kind), value):
            return None
        taken[out.name] = value
    return taken


async def run_workflow(
    *,
    run_id: str,
    workflow_id: str,
    version: int,
    agent_id: str,
    definition: Definition,
    door: StepDoor,
    sleep: Sleep = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> RunRecord:
    """Run every step in order of readiness and return the trace. A step's fault is not raised."""
    values: dict[str, dict[str, object]] = {}
    records: dict[str, StepRecord] = {}
    state = {"stopped": False}

    def settle(record: StepRecord) -> None:
        records[record.step_id] = record

    def reads(step: Step) -> Mapping[str, Ref]:
        return {k: v for k, v in step.arguments.items() if isinstance(v, Ref)}

    def known(ref: Ref) -> bool:
        return ref.step_id in values and ref.name in values[ref.step_id]

    def fail(step: Step, cause: Cause, attempts: int, began: float) -> None:
        settle(
            StepRecord(step.id, Status.FAILED, cause, attempts=attempts, seconds=clock() - began)
        )
        if step.on_failure is OnFailure.STOP:
            state["stopped"] = True

    async def one(step: Step) -> None:
        began = clock()
        if state["stopped"]:
            settle(StepRecord(step.id, Status.SKIPPED, Cause.RUN_STOPPED))
            return
        if step.handles is not None and records[step.handles].status is not Status.FAILED:
            settle(StepRecord(step.id, Status.SKIPPED, Cause.HANDLER_NOT_NEEDED))
            return
        if step.when is not None:
            if not known(step.when.ref):
                settle(StepRecord(step.id, Status.SKIPPED, Cause.INPUT_MISSING, step.when.words()))
                return
            if not _compare(step.when, values[step.when.ref.step_id][step.when.ref.name]):
                settle(
                    StepRecord(step.id, Status.SKIPPED, Cause.CONDITION_NOT_MET, step.when.words())
                )
                return
        wanted = reads(step)
        if not all(known(ref) for ref in wanted.values()):
            fail(step, Cause.INPUT_MISSING, 0, began)
            return
        if step.writes and not door.writes_offered:
            fail(step, Cause.WRITE_NOT_OFFERED, 0, began)
            return
        arguments = {
            key: values[value.step_id][value.name] if isinstance(value, Ref) else value
            for key, value in step.arguments.items()
        }
        key = f"{run_id}:{step.id}"
        attempts = 1 + step.retry.limit
        for attempt in range(1, attempts + 1):
            call = StepCall(run_id, step.id, step.kind, step.target, arguments, key, attempt)
            try:
                result = await door.call(call)
            except StepRefusedError:
                fail(step, Cause.REFUSED, attempt, began)
                return
            except Exception as failed:
                # The class is logged and no message is: a message can carry a row the tool read.
                log.warning(
                    "workflow.step_failed", run=run_id, step=step.id, error=type(failed).__name__
                )
                if attempt < attempts:
                    await sleep(step.retry.backoff_seconds * attempt)
                    continue
                fail(step, Cause.FAILED_AFTER_RETRIES, attempt, began)
                return
            taken = _outputs_of(step, result)
            if taken is None:
                fail(step, Cause.INVALID_OUTPUT, attempt, began)
                return
            values[step.id] = taken
            settle(StepRecord(step.id, Status.OK, attempts=attempt, seconds=clock() - began))
            return

    for wave in definition.waves():
        steps = [definition.step(one) for one in wave]
        together = [one for one in steps if one.parallel]
        if together:
            await asyncio.gather(*(one(step) for step in together))
        for step in steps:
            if not step.parallel:
                await one(step)
    return _closed(run_id, workflow_id, version, agent_id, definition, records)


def _closed(
    run_id: str,
    workflow_id: str,
    version: int,
    agent_id: str,
    definition: Definition,
    records: Mapping[str, StepRecord],
) -> RunRecord:
    ordered = tuple(records[one.id] for one in definition.steps)
    failed = [one for one in ordered if one.status is Status.FAILED]
    stopped = any(definition.step(one.step_id).on_failure is OnFailure.STOP for one in failed)
    outcome = Outcome.FAILURE if stopped else Outcome.PARTIAL if failed else Outcome.SUCCESS
    return RunRecord(
        run_id=run_id,
        workflow_id=workflow_id,
        version=version,
        agent_id=agent_id,
        outcome=outcome,
        failed_step=failed[0].step_id if failed else None,
        steps=ordered,
    )
