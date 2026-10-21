"""Where a person's run has got to, decided from the records that say so (M40.7.6).

The rule is pure, so it is driven over the facts the store would read. The same records over
PostgreSQL, with the person's own rows told from anybody else's, are the install check in
`tests/unit/test_acceptance_checks_thread_states.py`. Every refusal has a sibling that succeeds.

Task ids: M40.7.6
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from brain.gate.context import GateStep
from brain.gate.leash import ApprovalState
from brain.member_task_state import (
    STEP_NOT_RECORDED,
    STEP_WORDS,
    UNSETTLED,
    WORDS,
    HeldAction,
    RunFacts,
    TaskState,
    failed_step,
    lapsed,
    last_step,
    state_of,
)
from brain.ops.idempotency import OperationState
from brain.tables.chat import RunState

THEN = datetime(2999, 1, 1, tzinfo=UTC)


def _held(
    state: ApprovalState, *, gone: bool = False, operation: OperationState | None = None
) -> HeldAction:
    return HeldAction(state=state, lapsed=gone, operation=operation)


def test_a_run_that_answered_is_done_and_a_run_that_failed_is_failed() -> None:
    """The positive cases for everything below: with nothing held, the answer's own run state
    decides. Delete this and every other test passes against a rule that never says done."""
    for ended in (RunState.ANSWERED, RunState.ABSTAINED, RunState.DEGRADED, None):
        assert state_of(RunFacts(run_state=ended)) is TaskState.DONE
    assert state_of(RunFacts(run_state=RunState.FAILED)) is TaskState.FAILED


def test_an_action_held_for_a_person_is_waiting_whatever_the_answer_said() -> None:
    """A pending, unexpired action makes the run waiting even though its answer was recorded as
    answered. Delete this and a run that prepared something for a colleague to approve reads as
    done while it is still waiting."""
    held = (_held(ApprovalState.PENDING),)
    assert (
        state_of(RunFacts(run_state=RunState.ANSWERED, held=held)) is TaskState.WAITING_FOR_APPROVAL
    )
    assert (
        state_of(RunFacts(run_state=RunState.FAILED, held=held)) is TaskState.WAITING_FOR_APPROVAL
    )


def test_a_held_action_that_lapsed_or_was_rejected_waits_for_nobody() -> None:
    """A pending action whose window passed, and a rejected one, leave the run to its own run
    state. Delete this and a run waits for ever for an approval that can no longer be given."""
    for held in (
        (_held(ApprovalState.PENDING, gone=True),),
        (_held(ApprovalState.REJECTED),),
    ):
        assert state_of(RunFacts(run_state=RunState.ANSWERED, held=held)) is TaskState.DONE


def test_an_approved_action_is_running_until_the_worker_has_settled_it() -> None:
    """Approved with no run recorded yet, and approved with a run sent or unknown, are running;
    approved and succeeded is done; approved and failed is failed. Delete this and a run
    approved and still being carried out reads as done."""
    approved = ApprovalState.APPROVED
    for operation in (None, *UNSETTLED):
        assert state_of(RunFacts(held=(_held(approved, operation=operation),))) is TaskState.RUNNING
    assert (
        state_of(RunFacts(held=(_held(approved, operation=OperationState.SUCCEEDED),)))
        is TaskState.DONE
    )
    assert (
        state_of(RunFacts(held=(_held(approved, operation=OperationState.FAILED),)))
        is TaskState.FAILED
    )


def test_an_approved_action_whose_window_passed_unrun_is_not_running() -> None:
    """Approved, never run and lapsed is not running: the worker will not run it now. Delete this
    and a lapsed approval shows as running for ever."""
    assert state_of(RunFacts(held=(_held(ApprovalState.APPROVED, gone=True),))) is TaskState.DONE


def test_waiting_comes_before_running_when_two_actions_were_held() -> None:
    """One action pending and another approved and running: the run is waiting, because it is not
    over until the person's colleague has decided. Delete this and the order of the rules is
    whatever the list happens to hold."""
    held = (_held(ApprovalState.APPROVED), _held(ApprovalState.PENDING))
    assert state_of(RunFacts(held=held)) is TaskState.WAITING_FOR_APPROVAL


def test_a_failed_run_names_the_last_step_it_entered_in_a_person_s_words() -> None:
    """The last gate step among those recorded is the one named, whatever order they are listed
    in; a step the gate does not have is ignored. Delete this and the phrase names the first step,
    which every request reached, or breaks on a name a later release adds."""
    facts = RunFacts(run_state=RunState.FAILED, steps=("invoke", "identify", "made_up", "entitle"))
    assert failed_step(facts) == f"It stopped while {STEP_WORDS[GateStep.INVOKE]}."
    assert last_step(["identify", "entitle"]) is GateStep.ENTITLE
    assert last_step(["made_up"]) is None


def test_a_failed_run_whose_steps_were_not_recorded_says_so_and_guesses_nothing() -> None:
    """Delete this and a failed run with no timings is told it stopped at some step it may never
    have reached."""
    assert failed_step(RunFacts(run_state=RunState.FAILED)) == STEP_NOT_RECORDED


def test_only_a_failed_run_has_a_failed_step_and_a_failed_approval_says_so() -> None:
    """A done run and a running one carry no phrase; an approved action that did not happen says
    so in its own words rather than naming a gate step. Delete this and every row of the list
    carries a failure phrase."""
    assert failed_step(RunFacts(run_state=RunState.ANSWERED, steps=("invoke",))) == ""
    assert failed_step(RunFacts(held=(_held(ApprovalState.PENDING),))) == ""
    said = failed_step(
        RunFacts(held=(_held(ApprovalState.APPROVED, operation=OperationState.FAILED),))
    )
    assert "did not happen" in said and "stopped while" not in said


def test_every_state_and_every_gate_step_has_words() -> None:
    """The person reads a word for each state and a phrase for each step the gate has. Delete this
    and a step added to the gate reaches the list as a KeyError for whoever it failed."""
    assert set(WORDS) == set(TaskState)
    assert set(STEP_WORDS) == set(GateStep)
    assert len(set(WORDS.values())) == len(WORDS)


def test_a_window_has_passed_exactly_when_it_ends_at_or_before_the_instant() -> None:
    """Delete this and a window ending this very instant is treated as open."""
    assert lapsed(THEN, THEN) and lapsed(THEN, THEN + timedelta(seconds=1))
    assert not lapsed(THEN + timedelta(seconds=1), THEN)
