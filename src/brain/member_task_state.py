"""Where a person's own run has got to: running, waiting for approval, done or failed (M40.7.6).

A thread on the member's list is the questions a person asked and the answers they were given, and
nothing on it said whether the last run was still going, was held for somebody to approve, had
finished or had broken. The records that say so already exist and belong to the person: the answer's
own run state (`chat.message`), the action their run held for approval (`gate.suspension`, which
`0042`'s policy lets its raiser read), what the worker did with it once approved (`ops.operation`,
keyed by the approval's id) and how the request ended (`obs.request_telemetry`). **This module is
the one rule that reads them together, and it reads nothing else.**

**The order is the argument.** An action held for a person is *waiting* before anything else,
because the run is not over; an approved action the worker has not finished is *running*, because
the run is still going on without the person; and only when nothing is held or approved is the
answer's own run state asked. A held action that lapsed, was rejected, or was approved and then done
is not waiting or running any more, and the run state of the answer settles what is left. Reading
the run state first would call a run that is waiting for a colleague "done", because the answer it
gave said it had prepared something.

**A failed run says which step it stopped at, from a closed list, and never why.** The step is the
last gate step the request entered (`obs.request_telemetry.stage_ms` holds the steps it reached, in
the gate's own words), put in a plain phrase. A request whose steps were not recorded says that they
were not, rather than guessing one. The phrase names a stage of the product's pipeline and carries
nothing the request read, so it discloses nothing about what the person may or may not see.

**A state is the person's own.** Every record read here was written for, or raised by, the person
asking, and the store names them to row-level security before it reads
(`brain.ops.task_state_store`). No count of anything is made, and a thread whose records cannot be
found is simply *done*: an older answer written before the run state was recorded has nothing to say
and says nothing.

Task ids: M40.7.6
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.gate.context import GateStep
from brain.gate.leash import ApprovalState
from brain.ops.idempotency import OperationState
from brain.tables.chat import RunState


class TaskState(enum.StrEnum):
    """The four things the member's list says. Closed, and each is a word the person reads."""

    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    DONE = "done"
    FAILED = "failed"


#: Why the order of the rules in `state_of` is not a style choice.
HELD_AND_APPROVED_COME_BEFORE_THE_RUN_STATE: Final = (
    "An action held for a person means the run is not over, and an approved one the worker has not "
    "finished means it is still going on; the answer's own run state is asked only when neither is "
    "so, because an answer that says it prepared something is a finished answer to a run that is "
    "still waiting."
)

#: What a person is told for each state, in the product's words.
WORDS: Final[dict[TaskState, str]] = {
    TaskState.RUNNING: "Running",
    TaskState.WAITING_FOR_APPROVAL: "Waiting for approval",
    TaskState.DONE: "Done",
    TaskState.FAILED: "Failed",
}

#: Said when a failed run's steps were not recorded: the step is not guessed.
STEP_NOT_RECORDED: Final = "The step it stopped at was not recorded."

#: What each gate step is, for a person, as the place a run stopped. Every step the gate has.
STEP_WORDS: Final[dict[GateStep, str]] = {
    GateStep.RECORD: "recording the question",
    GateStep.INGEST: "reading the question",
    GateStep.IDENTIFY: "checking who was asking",
    GateStep.ENTITLE: "working out what you may use",
    GateStep.SCREEN: "screening the question",
    GateStep.CLASSIFY: "deciding what kind of question it was",
    GateStep.SELECT: "choosing the agent",
    GateStep.CACHE: "looking for an answer already given",
    GateStep.ROUTE: "choosing how to answer",
    GateStep.PROJECT: "preparing what to read",
    GateStep.INVOKE: "reading and asking",
    GateStep.REDACT: "removing what you may not see",
    GateStep.COMPOSE: "writing the answer",
}


@dataclass(frozen=True)
class HeldAction:
    """One action the person's run held for approval, and where it has got to.

    `operation` is the state of the worker's run of it once approved, or None while no run has
    been recorded. `lapsed` is whether its window has passed.
    """

    state: ApprovalState
    lapsed: bool
    operation: OperationState | None = None


@dataclass(frozen=True)
class RunFacts:
    """Everything this module reads about one answer's run."""

    run_state: RunState | None = None
    held: tuple[HeldAction, ...] = ()
    #: The names of the gate steps the request entered, from `stage_ms`, or empty when unrecorded.
    steps: tuple[str, ...] = ()


#: What a worker's run of an approved action is while it has not settled.
UNSETTLED: Final = frozenset(
    {
        OperationState.PENDING,
        OperationState.SENT,
        OperationState.UNKNOWN,
        OperationState.VERIFYING,
    }
)


def state_of(facts: RunFacts) -> TaskState:
    """Where the run behind an answer has got to (`HELD_AND_APPROVED_COME_BEFORE_THE_RUN_STATE`)."""
    held = facts.held
    if any(one.state is ApprovalState.PENDING and not one.lapsed for one in held):
        return TaskState.WAITING_FOR_APPROVAL
    approved = [one for one in held if one.state is ApprovalState.APPROVED]
    if any(
        one.operation in UNSETTLED or (one.operation is None and not one.lapsed) for one in approved
    ):
        return TaskState.RUNNING
    if any(one.operation is OperationState.FAILED for one in approved):
        return TaskState.FAILED
    if facts.run_state is RunState.FAILED:
        return TaskState.FAILED
    return TaskState.DONE


def last_step(names: Iterable[str]) -> GateStep | None:
    """The latest gate step among these names, or None when none of them is one.

    A name the gate does not have is left out, so a row written by a later release never breaks
    the list.
    """
    wanted = {one.lower() for one in names}
    known = [step for step in GateStep if step.name.lower() in wanted]
    return max(known) if known else None


def failed_step(facts: RunFacts) -> str:
    """For a failed run, the phrase for the step it stopped at; empty for any other state."""
    if state_of(facts) is not TaskState.FAILED:
        return ""
    if any(one.operation is OperationState.FAILED for one in facts.held):
        return "It was approved, and the action did not happen."
    step = last_step(facts.steps)
    if step is None:
        return STEP_NOT_RECORDED
    return f"It stopped while {STEP_WORDS[step]}."


def lapsed(expires_at: datetime, now: datetime) -> bool:
    """Whether a held action's window has passed at this instant."""
    return expires_at <= now
