"""The job row: the states it may take, the attempts it is allowed, and who may read it.

Every test here is about a job that would run, or be run twice, or stop being run at all,
with nothing anywhere reporting it. Real `EntitlementSet`s and real `Scope`s throughout: a
stand-in for either would test this surface against a fixture rather than against the two
objects it has to agree with, and the agreement is the point.

Task ids: M17.1.1, M17.1.3, M17.1.4, M17.1.5
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import TrafficClass
from brain.ops.idempotency import OperationState
from brain.ops.jobs import (
    ALLOWED_TRANSITIONS,
    DEAD_LETTER_ACTIONABLE_DAYS,
    DEAD_LETTER_CAPABILITY,
    DEFAULT_TIMEOUT_SECONDS,
    DRIVER_MAPPING,
    MAX_ATTEMPTS,
    OPERATOR_SURFACE,
    RETRY_BASE_SECONDS,
    STATES_WITHOUT_AN_ATTEMPT,
    TERMINAL,
    DeadLetter,
    DeadLetterReason,
    DeadLetterSummary,
    DriverConcept,
    IllegalJobTransitionError,
    Interruption,
    InterruptionKind,
    JobRecord,
    JobsError,
    JobState,
    TaskPool,
    advance,
    dead_letter_for,
    dead_letter_summary,
    driver_mapping_gaps,
    driver_table_name,
    hidden_count_fields,
    interrupt,
    may_see,
    next_attempt_at,
    ours_alone,
    pool_ceiling,
    pool_gaps,
    reach_carrying_fields,
    reachable_from,
    retry_gaps,
    timeout_gaps,
    visible_dead_letters,
    worst_case_runs,
)
from brain.ops.limits import BACKOFF_AFTER_REFUSALS
from brain.ops.queue import (
    CONCURRENCY,
    FALLBACK_POLL_SECONDS,
    HEARTBEAT_SECONDS,
    MAX_REDRIVES,
    MIB_PER_SLOT,
    Job,
    Redrive,
    stale_after,
)
from brain.ops.retention import PAYLOAD_RETENTION_DAYS
from brain.ops.wiring import component

NOW = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)

READER = "u_operator"
OWNER = "u_priya"
STRANGER = "u_wei"


def _job(**overrides: object) -> Job:
    base: dict[str, object] = {
        "task": "answer.compose",
        "traffic_class": TrafficClass.HUMAN_ASYNC,
        "args": {"question_id": "q_1"},
        "redrive": Redrive.UNSAFE,
    }
    base.update(overrides)
    return Job(**base)  # type: ignore[arg-type]


def _record(**overrides: object) -> JobRecord:
    base: dict[str, object] = {
        "job_id": "j_1",
        "job": _job(),
        "principal_id": OWNER,
        "scheduled_at": NOW,
        "state": JobState.QUEUED,
        "attempts": 0,
    }
    base.update(overrides)
    return JobRecord(**base)  # type: ignore[arg-type]


def _dead_letter(**overrides: object) -> DeadLetter:
    base: dict[str, object] = {
        "job_id": "j_1",
        "task": "answer.compose",
        "principal_id": OWNER,
        "traffic_class": TrafficClass.HUMAN_ASYNC,
        "reason": DeadLetterReason.ATTEMPTS_EXHAUSTED,
        "attempts": MAX_ATTEMPTS,
        "at": NOW,
    }
    base.update(overrides)
    return DeadLetter(**base)  # type: ignore[arg-type]


def _reader(*grants: Grant, principal_id: str = READER) -> EntitlementSet:
    return EntitlementSet(principal_id=principal_id, grants=grants)


def _dead_letter_grant(scope: Scope | None = None) -> Grant:
    return Grant(
        capability=DEAD_LETTER_CAPABILITY,
        scope=Scope.unrestricted() if scope is None else scope,
    )


# --------------------------------------------------- the state machine (M17.1.1)
def test_a_job_runs_from_queued_through_running_to_succeeded() -> None:
    """The path every working job takes, and the positive sibling of every refusal below. A
    machine tested only by what it rejects is satisfied by one that rejects everything.
    Delete this and the transition table could be emptied with every guard test still
    green."""
    queued = _record()
    running = queued.started()
    assert running.state is JobState.RUNNING
    assert running.attempts == 1
    done = running.advanced(JobState.SUCCEEDED)
    assert done.state is JobState.SUCCEEDED
    assert done.is_settled


def test_a_job_that_fails_and_is_retried_reaches_success_on_a_later_attempt() -> None:
    """The other positive path, and the one the attempt counter exists for. A retry is the
    same job going round again, so the state returns to queued and the count does not.
    Delete this and a retry could reset the attempts, which is an uncapped loop with a cap
    that reads as untouched."""
    first = _record().started()
    requeued = first.advanced(JobState.QUEUED, scheduled_at=NOW + timedelta(seconds=5))
    assert requeued.attempts == 1
    assert requeued.scheduled_at == NOW + timedelta(seconds=5)
    second = requeued.started()
    assert second.attempts == 2
    assert second.advanced(JobState.SUCCEEDED).state is JobState.SUCCEEDED


def test_every_job_state_has_a_row_in_the_transition_table() -> None:
    """A member added with no entry is a state with no way out, and a job that reaches it
    sits there for ever while every screen reports it as work in progress. Delete this and
    the next state added is a silent dead end."""
    assert set(ALLOWED_TRANSITIONS) == set(JobState)
    for state, onward in ALLOWED_TRANSITIONS.items():
        assert onward <= set(JobState), state


def test_a_terminal_state_is_one_with_nothing_after_it_rather_than_one_declared_so() -> None:
    """Derived rather than listed, so a state cannot be called terminal here and given an
    outgoing edge above. Delete this and the two can disagree, with whichever a reader found
    first deciding what happens to the row."""
    assert set(TERMINAL) == {
        JobState.SUCCEEDED,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.ABORTED,
        JobState.DEAD_LETTER,
    }
    for state in TERMINAL:
        assert ALLOWED_TRANSITIONS[state] == frozenset()
        with pytest.raises(IllegalJobTransitionError, match="terminal"):
            advance(state, JobState.SUCCEEDED)


def test_a_job_cannot_enter_running_without_spending_an_attempt() -> None:
    """The attempt count is the only thing between a failing job and a worker that processes
    nothing else, and a move that set the state without it would leave a job retrying for
    ever with the cap reading as untouched. Delete this and `advanced(RUNNING)` becomes the
    obvious way to start a job."""
    with pytest.raises(IllegalJobTransitionError, match="spends an attempt"):
        _record().advanced(JobState.RUNNING)
    assert _record().started().attempts == 1


def test_a_job_that_is_not_queued_cannot_be_started() -> None:
    """The other half of the same rule. Starting a running job is two workers on one row, and
    starting a settled one is work somebody already decided had stopped. Delete this and
    `started` becomes a way round the transition table rather than the only way through
    it."""
    with pytest.raises(IllegalJobTransitionError, match="cannot be started"):
        _record().started().started()
    with pytest.raises(IllegalJobTransitionError, match="terminal"):
        _record(state=JobState.CANCELLED).started()


def test_a_job_due_later_is_a_queued_job_with_a_time_rather_than_a_state_of_its_own() -> None:
    """A second way to be ready means the fetch query has to know about both, and the day
    somebody adds a state without touching the query is the day a schedule stops firing with
    nothing to see. Delete this and a SCHEDULED member arrives as a tidying."""
    assert not any(state.value == "scheduled" for state in JobState)
    later = _record(scheduled_at=NOW + timedelta(minutes=5))
    assert not later.is_due(NOW)
    assert later.is_due(NOW + timedelta(minutes=5))
    assert _record().is_due(NOW)
    assert not _record().started().is_due(NOW)


def test_a_state_only_a_started_job_reaches_cannot_be_written_with_no_attempt_on_it() -> None:
    """A row saying it ran with nothing having run it is a row the cap has never been applied
    to, so it is a job with no budget. The permitted set is derived from the table, so a new
    edge out of queued cannot arrive with this guard silently wrong. Delete this and the
    attempts column becomes decorative."""
    assert set(STATES_WITHOUT_AN_ATTEMPT) == {JobState.QUEUED, JobState.CANCELLED}
    with pytest.raises(JobsError, match="no attempt on it"):
        _record(state=JobState.SUCCEEDED, attempts=0)
    _record(state=JobState.SUCCEEDED, attempts=1)
    _record(state=JobState.CANCELLED, attempts=0)


def test_a_job_row_counts_attempts_and_has_nowhere_to_record_a_re_drive() -> None:
    """A retry is the job asking for another go; a re-drive is the machine dying underneath
    one. `brain.ops.queue.InFlight` holds the second and refuses the first, and this is the
    mirror of it: one counter for both dead-letters healthy jobs on the one host whose
    expected failure is an out-of-memory kill. Delete this and the two get merged as
    tidying."""
    assert "attempts" in JobRecord.__dataclass_fields__
    assert "redrives" not in JobRecord.__dataclass_fields__
    with pytest.raises(JobsError, match="attempts"):
        _record(attempts=-1)


def test_the_worst_case_number_of_runs_adds_both_counters_rather_than_reporting_one() -> None:
    """The figure an operator needs before deciding whether a side effect is survivable is
    how many times the body can possibly have executed, and each counter alone understates
    it. Delete this and the answer silently becomes whichever cap somebody was looking at."""
    assert worst_case_runs() == MAX_ATTEMPTS + MAX_REDRIVES
    assert worst_case_runs() > MAX_ATTEMPTS
    assert worst_case_runs() > MAX_REDRIVES


# --------------------------------------------------- attempts and scheduling (M17.1.1)
def test_a_later_retry_is_scheduled_further_out_than_an_early_one() -> None:
    """The backoff has to actually back off. A flat curve asks a failing dependency the same
    question at a fixed interval until the attempts run out, which is the load pattern that
    keeps it down. Delete this and the spacing can be made constant with every other retry
    test still green."""
    early = next_attempt_at(attempts=1, failed_at=NOW)
    late = next_attempt_at(attempts=MAX_ATTEMPTS, failed_at=NOW)
    assert late > early
    assert early > NOW


def test_a_retry_budget_that_never_reaches_the_doubling_is_reported() -> None:
    """A budget at or below the point where the curve starts doubling means every attempt is
    the same distance from the last and the backoff is decoration. Delete this and
    `MAX_ATTEMPTS` can be lowered to three, which reads as prudence and switches the spacing
    off."""
    assert MAX_ATTEMPTS > BACKOFF_AFTER_REFUSALS
    assert any("never applies" in gap for gap in retry_gaps(max_attempts=BACKOFF_AFTER_REFUSALS))
    assert any("nothing is ever retried" in gap for gap in retry_gaps(max_attempts=0))
    assert retry_gaps() == ()


def test_a_retry_is_never_scheduled_sooner_than_a_worker_with_no_notifications_polls() -> None:
    """Behind a transaction pooler a worker receives no notifications and raises nothing, so
    the poll interval is the queue's whole latency. A retry due sooner than that is a time the
    queue cannot honour in exactly the degraded mode it was written for. Delete this and the
    base interval can be tuned below the poll with nothing reporting it."""
    assert RETRY_BASE_SECONDS >= FALLBACK_POLL_SECONDS
    assert any("cannot honour" in gap for gap in retry_gaps(base_seconds=1.0))


def test_a_failure_time_with_no_timezone_cannot_produce_a_next_attempt() -> None:
    """Two workers on two hosts produce an ordering that cannot be compared, and the
    comparison is the only thing a schedule is for. Delete this and the failure appears only
    once a second worker runs somewhere else."""
    with pytest.raises(JobsError, match="no timezone"):
        next_attempt_at(attempts=1, failed_at=datetime(2026, 9, 7, 11, 0))
    with pytest.raises(JobsError, match="cannot be negative"):
        next_attempt_at(attempts=-1, failed_at=NOW)


def test_a_job_scheduled_at_a_time_with_no_timezone_is_refused() -> None:
    """The same rule on the row rather than on the arithmetic. A naive timestamp compares
    against a worker's clock in whatever the container's zone happens to be. Delete this and
    a job is fetched hours early or never."""
    with pytest.raises(JobsError, match="no timezone"):
        _record(scheduled_at=datetime(2026, 9, 7, 11, 0))
    with pytest.raises(JobsError, match="no timezone"):
        _record().advanced(JobState.CANCELLED, scheduled_at=datetime(2026, 9, 7, 11, 0))


# --------------------------------------------------- a job carries no reach (M17.1.1)
def test_a_job_row_has_no_field_whose_type_could_hold_an_entitlement() -> None:
    """A row carrying a serialised reach is a permission decision taken at enqueue time and
    applied after the person moved department or left, which is the one place a revocation
    does not reach. Delete this and the field is added by whoever finds resolving the reach
    at run time inconvenient."""
    assert reach_carrying_fields(JobRecord) == ()

    @dataclass(frozen=True)
    class WithAReach:
        job_id: str
        entitlement: EntitlementSet

    # The check has to be able to fail, or the assertion above is satisfied by a function
    # that answers nothing for every class it is ever handed.
    assert reach_carrying_fields(WithAReach) == ("entitlement",)


def test_a_job_argument_that_is_a_capability_is_refused() -> None:
    """The one place a reach can hide as text. `brain.ops.queue.Job` refuses an argument long
    enough to be content and a capability is fifteen characters, so the length rule cannot
    see it. Delete this and a frozen permission decision travels in the argument mapping,
    which is the shape that looks most like a reference."""
    with pytest.raises(JobsError, match="is a capability"):
        _record(job=_job(args={"grant": "read:client.name"}))
    with pytest.raises(JobsError, match="is a capability"):
        _record(job=_job(args={"grant": "read:client.*"}))
    # A reference to a grant is exactly what should travel instead, and it has to still work.
    _record(job=_job(args={"grant_id": "g_4471"}))


def test_a_job_with_no_principal_is_refused() -> None:
    """The reach an attempt runs at is resolved from a principal, so a row without one can
    only run as nobody or as everybody, and a helpful default picks the second. Delete this
    and a job with a blank principal is enqueued and runs unentitled or over-entitled
    depending on which call site built it."""
    with pytest.raises(JobsError, match="names no principal"):
        _record(principal_id="   ")
    with pytest.raises(JobsError, match="no id"):
        _record(job_id="")


# --------------------------------------------------- the driver's model (M17.1.2)
def test_every_job_state_is_named_against_the_drivers_own_vocabulary() -> None:
    """A state nobody decided how to persist is discovered by the first row that reaches it,
    in production, on the driver the mapping was supposed to describe. Delete this and a state
    can be added here with no answer to how it is written down."""
    assert driver_mapping_gaps() == ()
    partial = tuple(c for c in DRIVER_MAPPING if c.ours != JobState.ABORTED.value)
    assert any("no driver concept" in gap for gap in driver_mapping_gaps(partial))


def test_nothing_may_claim_to_be_verified_against_a_driver_that_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mapping written from documentation and never run is a set of plausible names, and the
    sentence a later reader trusts is the one saying it was checked. Delete this and the
    honesty of this whole module becomes a habit rather than a check.

    **The gate is now asserted in both directions, because on 2026-09-11 it stopped firing on
    its own.** `driver_mapping_gaps` asks whether the driver can be imported, and the answer
    changed when `procrastinate` became a dependency: a row claiming verification is no longer
    a false claim, it is merely an unchecked one, and this check was built to stop asking on
    exactly that day. Asserting the absence as well as the presence is what keeps that from
    reading as the check having been quietly removed."""
    assert all(not concept.verified for concept in DRIVER_MAPPING)
    claimed = (DriverConcept(ours="attempts", theirs="x", note="y", verified=True),)

    monkeypatch.setattr("brain.ops.jobs.driver_is_installed", lambda: False)
    assert any("claims to be verified" in gap for gap in driver_mapping_gaps(claimed))

    monkeypatch.setattr("brain.ops.jobs.driver_is_installed", lambda: True)
    assert not any("claims to be verified" in gap for gap in driver_mapping_gaps(claimed))


def test_the_parts_the_driver_cannot_hold_are_named_rather_than_glossed_over() -> None:
    """These are the columns a table of our own would need, which is the specification for a
    migration that does not exist. Delete this and the gaps read as an oversight rather than
    as the list of what is still owed."""
    ours = ours_alone()
    assert JobState.DEAD_LETTER.value in ours
    assert "deadline" in ours
    assert "per-task concurrency" in ours
    assert "dead-letter reason" in ours
    # And the driver does hold most of it, or the mapping would be saying nothing.
    assert len(ours) < len(DRIVER_MAPPING)


def test_the_drivers_table_name_is_derived_rather_than_written_out() -> None:
    """`brain.ops.queue` is the one file permitted to name an implementation, and the seam is
    a fact only while every other file derives from it. Delete this and the table name is
    pasted in, which is the first of the imports that closes the seam quietly."""
    assert driver_table_name("elsewhere") == "elsewhere_jobs"
    assert driver_table_name() != "elsewhere_jobs"


def test_a_driver_concept_with_no_note_cannot_be_recorded() -> None:
    """A correspondence with no explanation is a pair of strings somebody once believed. The
    note is what makes it checkable by the next person. Delete this and the mapping fills up
    with rows nobody can evaluate."""
    with pytest.raises(JobsError, match="no note"):
        DriverConcept(ours="attempts", theirs="x", note="  ")


# --------------------------------------------------- the worker pool (M17.1.3)
def test_one_task_may_not_hold_every_slot_in_a_class_that_has_more_than_one() -> None:
    """The class split exists to stop one kind of work starving another, and a class fully
    occupied by one task has reproduced that failure inside itself while the class as a whole
    looks correctly sized. Delete this and the ceiling can be raised to the whole
    allocation."""
    for traffic_class, slots in CONCURRENCY.items():
        if slots > 1:
            assert pool_ceiling(traffic_class) < slots, traffic_class
        assert pool_ceiling(traffic_class) <= slots


def test_a_pool_over_its_classs_ceiling_is_reported() -> None:
    """The check has to fail when it should. Delete this and `pool_gaps` could compare the
    request against itself and admit every number."""
    greedy = TaskPool(
        task="backfill.reindex",
        traffic_class=TrafficClass.HUMAN_ASYNC,
        at_once=CONCURRENCY[TrafficClass.HUMAN_ASYNC],
    )
    assert any("cannot occupy the whole" in gap for gap in pool_gaps([greedy]))


def test_a_pool_that_fits_its_class_is_reported_as_nothing() -> None:
    """A check that refuses everything is a check that gets switched off. Delete this and
    `pool_gaps` could return a finding unconditionally with every refusal test above still
    green."""
    fits = TaskPool(
        task="answer.compose",
        traffic_class=TrafficClass.HUMAN_ASYNC,
        at_once=pool_ceiling(TrafficClass.HUMAN_ASYNC),
    )
    assert pool_gaps([fits]) == ()
    assert pool_gaps([]) == ()


def test_a_pool_declared_against_a_class_with_no_slots_is_reported() -> None:
    """Interactive traffic is allocated zero deliberately, so a pool against it is a task that
    is enqueued and never fetched, which presents as a queue that fills and never drains and
    takes a day to find. Delete this and the zero reads as a small number."""
    assert CONCURRENCY[TrafficClass.HUMAN_INTERACTIVE] == 0
    stranded = TaskPool(
        task="answer.compose", traffic_class=TrafficClass.HUMAN_INTERACTIVE, at_once=1
    )
    assert any("never fetched" in gap for gap in pool_gaps([stranded]))


def test_a_pool_bigger_than_the_containers_memory_is_reported() -> None:
    """The slot sum for the whole container belongs to `brain.ops.queue.concurrency_gaps` and
    is not repeated, but a pool checked against an allocation somebody passed in can exceed
    the container on its own. On this host that is an out-of-memory kill on a box shared with
    somebody else's production. Delete this and the memory check only ever runs against the
    declared allocation, where it cannot fail."""
    limit = component("brain-worker").memory_mib
    slots = limit // MIB_PER_SLOT + 10
    gaps = pool_gaps(
        [TaskPool(task="x", traffic_class=TrafficClass.SYSTEM, at_once=slots)],
        {**CONCURRENCY, TrafficClass.SYSTEM: slots * 2},
    )
    assert any("over the" in gap for gap in gaps), gaps


def test_the_largest_pool_any_class_allows_fits_the_workers_memory_limit() -> None:
    """The figures are anchored outside themselves: the ceiling comes from the queue's own
    allocation and the cost of a slot and the limit come from `brain.ops.wiring`, which is
    held equal to the deployed compose file by test. Delete this and the pool ceilings can
    drift away from the container they run in."""
    largest = max(pool_ceiling(traffic_class) for traffic_class in CONCURRENCY)
    assert largest * MIB_PER_SLOT <= component("brain-worker").memory_mib


def test_a_task_capped_twice_in_one_class_is_reported() -> None:
    """Whichever declaration is read second silently decides, and which that is depends on the
    order somebody wrote them in. Delete this and a pool raised in one place and left in
    another produces whichever answer the loop reached last."""
    pool = TaskPool(task="answer.compose", traffic_class=TrafficClass.SYSTEM, at_once=1)
    assert any("capped twice" in gap for gap in pool_gaps([pool, pool]))


def test_a_pool_that_allows_nothing_is_refused() -> None:
    """A task capped at nothing is enqueued and never run, which is indistinguishable from a
    task nobody asked for. The same argument `brain.ops.queue.Shard` makes about a worker with
    no slots. Delete this and a pool of zero is how somebody switches a task off invisibly."""
    with pytest.raises(JobsError, match="capped at nothing"):
        TaskPool(task="x", traffic_class=TrafficClass.SYSTEM, at_once=0)
    with pytest.raises(JobsError, match="no task name"):
        TaskPool(task="  ", traffic_class=TrafficClass.SYSTEM, at_once=1)


# --------------------------------------------------- cancellation and timeout (M17.1.4)
def test_a_cancellation_before_anything_ran_leaves_nothing_to_verify() -> None:
    """Nothing was issued, so there is no side effect to be unknown about, and reporting one
    would send somebody to a read-back for an operation that was never raised. Delete this and
    every cancellation looks like an interrupted one."""
    stopped = interrupt(_record(), InterruptionKind.CANCELLATION, now=NOW)
    assert stopped.record.state is JobState.CANCELLED
    assert stopped.operation_state is None
    assert not stopped.retriable


def test_a_cancellation_of_a_running_job_is_a_request_the_worker_has_to_acknowledge() -> None:
    """Stopping is the worker's to do and asking is all anybody else can do, so the row says
    the request is outstanding until it acknowledges. Delete this and a screen reports work as
    stopped while it is still running, which is the state an operator then acts on."""
    running = _record().started()
    asked = interrupt(running, InterruptionKind.CANCELLATION, now=NOW)
    assert asked.record.state is JobState.CANCELLING
    assert asked.record.advanced(JobState.ABORTED).state is JobState.ABORTED


def test_a_cancellation_that_arrives_too_late_records_the_success_that_happened() -> None:
    """Nothing can stop work that has already finished, and a machine that refused to record
    it would leave the row lying about the world. Delete this and a job that succeeded is
    filed as aborted, which is a wrong answer with a full audit trail behind it."""
    asked = interrupt(_record().started(), InterruptionKind.CANCELLATION, now=NOW)
    assert asked.record.advanced(JobState.SUCCEEDED).state is JobState.SUCCEEDED
    assert asked.record.advanced(JobState.FAILED).state is JobState.FAILED


def test_a_cancelled_job_is_never_retried_and_a_timed_out_one_may_be() -> None:
    """The difference the whole leaf is about. A timeout is this system giving up on its own
    deadline; a cancellation is a person's instruction, and retrying one is doing the thing
    they asked not to happen. Delete this and the two share a retry rule, which is wrong in
    the direction that acts against the instruction."""
    running = _record().started()
    assert not interrupt(running, InterruptionKind.CANCELLATION, now=NOW).retriable
    assert interrupt(running, InterruptionKind.TIMEOUT, now=NOW).retriable


def test_a_timeout_under_the_cap_queues_the_job_again_further_out() -> None:
    """The positive case for the timeout branch: the work is not lost, it is spaced out. The
    schedule has to move as well as the state, or the job is fetched again immediately and the
    backoff is a comment. Delete this and a timeout can requeue at the same instant."""
    timed_out = interrupt(_record().started(), InterruptionKind.TIMEOUT, now=NOW)
    assert timed_out.record.state is JobState.QUEUED
    assert timed_out.record.scheduled_at > NOW
    assert timed_out.record.attempts == 1


def test_a_timeout_on_the_last_attempt_is_set_aside_rather_than_queued_again() -> None:
    """A job given every attempt and taking none of them is not fixed by another one, and an
    uncapped retry is a slot spent for ever on work that never completes. Delete this and the
    cap has no effect at the one moment it matters."""
    spent = _record(state=JobState.QUEUED, attempts=MAX_ATTEMPTS - 1).started()
    assert spent.attempts == MAX_ATTEMPTS
    finished = interrupt(spent, InterruptionKind.TIMEOUT, now=NOW)
    assert finished.record.state is JobState.DEAD_LETTER
    assert not finished.retriable


def test_a_job_stopped_mid_flight_leaves_its_side_effect_unknown_rather_than_failed() -> None:
    """FAILED means it definitely did not happen, which means it is safe to try again, and
    retrying an unknown side effect is how a client is billed twice. The state is read out of
    `brain.ops.idempotency`'s own table rather than named here. Delete this and an interrupted
    job reports a definite answer nobody has."""
    running = _record(job=_job(redrive=Redrive.UNSAFE)).started()
    for kind in InterruptionKind:
        stopped = interrupt(running, kind, now=NOW)
        assert stopped.operation_state is not OperationState.FAILED, kind
        assert stopped.operation_state is OperationState.UNKNOWN, kind


def test_a_job_that_changes_nothing_the_world_can_see_leaves_no_operation_behind() -> None:
    """The positive sibling of the test above. A job declared safe to repeat has nothing to be
    unknown about, and reporting one would put every interrupted read in front of a person for
    a verification there is nothing to verify. Delete this and the unknown branch is
    unconditional, which is indistinguishable from a correct one until somebody counts the
    quarantine queue."""
    safe = _record(job=_job(redrive=Redrive.SAFE)).started()
    assert interrupt(safe, InterruptionKind.TIMEOUT, now=NOW).operation_state is None


def test_a_job_that_did_not_declare_itself_safe_is_treated_as_side_effecting() -> None:
    """Default-deny, in the same shape as the queue's own re-drive default. A task author who
    has not thought about it gets the answer that cannot report a side effect as definitely
    absent. Delete this and the default can be flipped as a convenience."""
    undeclared = Job(task="x", traffic_class=TrafficClass.SYSTEM)
    assert undeclared.redrive is Redrive.UNSAFE
    running = _record(job=undeclared).started()
    assert interrupt(running, InterruptionKind.TIMEOUT, now=NOW).operation_state is not None


def test_a_queued_job_cannot_time_out() -> None:
    """Nothing is running, so no deadline is being exceeded; what a queued job can outlive is
    a schedule, and this model has no expiry on one. Answering would let a caller record a
    timeout against work that never began. Delete this and a queued job accumulates attempts
    it never made."""
    with pytest.raises(JobsError, match="no deadline is running"):
        interrupt(_record(), InterruptionKind.TIMEOUT, now=NOW)


def test_a_settled_job_cannot_be_interrupted() -> None:
    """A job that has already stopped cannot be stopped again, and a cancellation recorded
    against a succeeded job is a row saying the work was prevented after it happened. Delete
    this and a late cancellation rewrites history."""
    done = _record(state=JobState.SUCCEEDED, attempts=1)
    with pytest.raises(JobsError, match="cannot be interrupted"):
        interrupt(done, InterruptionKind.CANCELLATION, now=NOW)


def test_no_cancelled_or_aborted_job_can_reach_running_in_any_number_of_steps() -> None:
    """It is not enough that the direct edge is missing. The edge somebody adds is a requeue
    control on a screen, and that puts a cancelled job two hops from running again, with the
    table row still reading correctly on the day it was added. Delete this and a person's
    stop becomes later."""
    for state in (JobState.CANCELLED, JobState.ABORTED, JobState.DEAD_LETTER):
        assert JobState.RUNNING not in reachable_from(state), state
        assert reachable_from(state) == frozenset(), state
    # And the closure is not empty for everything, or the assertion above is vacuous.
    assert JobState.RUNNING in reachable_from(JobState.QUEUED)


def test_the_declared_deadline_sits_between_a_heartbeat_and_the_staleness_window() -> None:
    """Both ends are the queue's figures rather than this module's. Past the staleness window
    the recovery sweep starts a second copy while the first is still inside its deadline;
    under one heartbeat a job is abandoned before it has said it was running once, and a
    timeout then looks exactly like a dead worker. Delete this and the deadline can be set to
    a round number that is neither."""
    assert HEARTBEAT_SECONDS <= DEFAULT_TIMEOUT_SECONDS < stale_after().total_seconds()
    assert timeout_gaps() == ()


def test_a_deadline_past_the_staleness_window_is_reported() -> None:
    """The check has to fail when it should, and this is the failure with no error in it: the
    symptom is a duplicated job rather than a message, and the log says orphaned for what was
    a slow job. Delete this and the deadline can be raised to whatever a slow connector
    needs."""
    gaps = timeout_gaps(stale_after().total_seconds())
    assert any("second copy" in gap for gap in gaps), gaps


def test_a_deadline_shorter_than_a_heartbeat_or_no_deadline_at_all_is_reported() -> None:
    """A timeout and a crashed worker are treated differently, one retried and the other
    re-driven or quarantined, so a deadline that fires before the job has ever reported itself
    alive makes the two indistinguishable in the row. Delete this and the floor is never seen
    to fail."""
    assert any("running once" in gap for gap in timeout_gaps(HEARTBEAT_SECONDS - 1))
    assert any("abandons it" in gap for gap in timeout_gaps(0))


# --------------------------------------------------- the dead letter (M17.1.5)
def test_a_dead_letter_can_only_be_built_from_a_job_that_was_set_aside() -> None:
    """A row built from a job that is still running puts work that is still happening in front
    of somebody as work that has stopped, and the action they take is taken against a running
    job. Delete this and the operator's list fills with live work."""
    dead = _record(state=JobState.DEAD_LETTER, attempts=MAX_ATTEMPTS)
    entry = dead_letter_for(dead, DeadLetterReason.ATTEMPTS_EXHAUSTED, at=NOW)
    assert entry.job_id == "j_1"
    assert entry.principal_id == OWNER
    assert entry.attempts == MAX_ATTEMPTS
    with pytest.raises(JobsError, match="not dead_letter"):
        dead_letter_for(_record().started(), DeadLetterReason.ATTEMPTS_EXHAUSTED, at=NOW)


def test_a_dead_letter_carries_no_arguments_and_no_failure_text() -> None:
    """Those are the two fields that turn an operational row into a copy of somebody's data
    with a different retention on it, which is what the queue refuses at the other end. The
    identifiers are enough to fetch what is needed through the gate at the reach whoever is
    asking holds now. Delete this and the screen becomes a payload store nobody redacts."""
    carried = set(DeadLetter.__dataclass_fields__)
    assert not carried & {"args", "arguments", "error", "traceback", "detail", "message"}


def test_an_operator_sees_a_dead_letter_they_hold_a_grant_for() -> None:
    """The positive case, and the one that makes the surface worth having. A filter tested only
    by what it hides is satisfied by one that hides everything, which is a screen that reports
    a healthy queue while jobs sit in it. Delete this and the refusals below pass over an empty
    list for ever."""
    reader = _reader(_dead_letter_grant())
    assert visible_dead_letters([_dead_letter()], reader) == (_dead_letter(),)


def test_an_operator_with_no_grant_sees_nothing_and_is_told_nothing() -> None:
    """DENIED and ABSENT stay indistinguishable: no refusal is raised, no placeholder appears
    and no number is emitted. Delete this and the screen either raises, which says the row
    exists, or shows a gap, which says the same more quietly."""
    assert visible_dead_letters([_dead_letter()], _reader()) == ()
    assert not may_see(_dead_letter(), _reader())


def test_a_person_sees_their_own_dead_letter_without_holding_any_grant() -> None:
    """Refusing this means the only person who knows what the job was for is the one person
    who cannot be told it will not happen. Delete this and somebody's own failed work becomes
    invisible to them."""
    owner = _reader(principal_id=OWNER)
    assert may_see(_dead_letter(principal_id=OWNER), owner)
    assert not may_see(_dead_letter(principal_id=STRANGER), owner)


def test_the_view_of_a_queue_holding_hidden_rows_is_identical_to_one_that_never_held_them() -> None:
    """The strong form, and the only version of indistinguishable worth having: a placeholder,
    a gap in an ordering, or a count that differs by one all reconstruct exactly what was
    hidden. Delete this and a later 'showing 3 of 47' passes every other test here."""
    mine = _dead_letter(job_id="j_mine", principal_id=OWNER)
    theirs = _dead_letter(job_id="j_theirs", principal_id=STRANGER)
    owner = _reader(principal_id=OWNER)
    assert visible_dead_letters([mine, theirs], owner) == visible_dead_letters([mine], owner)
    assert dead_letter_summary([mine, theirs], owner, NOW) == dead_letter_summary(
        [mine], owner, NOW
    )


def test_a_summary_counts_only_the_rows_the_reader_may_see() -> None:
    """An operator wants a total and the total is the one thing this cannot give: a count of
    everything says how many jobs belong to people they may not see, and it says it by
    subtraction. Delete this and the figure above the list becomes the count that was
    filtered out."""
    owner = _reader(principal_id=OWNER)
    summary = dead_letter_summary(
        [
            _dead_letter(job_id="a", principal_id=OWNER),
            _dead_letter(
                job_id="b", principal_id=OWNER, reason=DeadLetterReason.RE_DRIVEN_TOO_OFTEN
            ),
            _dead_letter(job_id="c", principal_id=STRANGER),
        ],
        owner,
        NOW,
    )
    assert summary.by_reason[DeadLetterReason.ATTEMPTS_EXHAUSTED] == 1
    assert summary.by_reason[DeadLetterReason.RE_DRIVEN_TOO_OFTEN] == 1
    assert sum(summary.by_reason.values()) == 2


def test_every_dead_letter_reason_is_a_key_in_the_summary_including_the_empty_ones() -> None:
    """A caller writing `by_reason.get(reason, 0)` reads as though that reason were optional,
    and the most serious one is the one most likely to be missing on a quiet day. The same rule
    `brain.ops.queue.redrive_plan` keeps about its verdicts. Delete this and the keys become
    whatever happened to occur today."""
    summary = dead_letter_summary([], _reader(_dead_letter_grant()), NOW)
    assert set(summary.by_reason) == set(DeadLetterReason)
    assert summary.oldest_at is None
    assert summary.unactionable == 0


def test_the_operator_surface_has_no_field_that_could_hold_a_count_of_hidden_jobs() -> None:
    """The failure arrives as a field somebody adds to make a screen more useful, not as
    carelessness, so the rule is a check rather than a paragraph. Delete this and `total`
    appears on the summary the first time an operator asks how many there are."""
    assert hidden_count_fields() == ()

    @dataclass(frozen=True)
    class Helpful:
        shown: int
        total: int

    # The check has to be able to fail, or it is a function that answers nothing.
    assert hidden_count_fields([Helpful]) == ("Helpful.total",)
    assert set(OPERATOR_SURFACE) == {DeadLetter, DeadLetterSummary}


def test_a_dead_letter_older_than_the_payload_store_is_marked_unactionable() -> None:
    """A job carries references, so a dead letter older than the things it refers to can be
    neither diagnosed nor raised again: the arguments still read correctly and resolve to
    nothing. Delete this and the screen shows rows nobody can act on as though they were work
    waiting to be done."""
    assert DEAD_LETTER_ACTIONABLE_DAYS == PAYLOAD_RETENTION_DAYS
    fresh = _dead_letter(at=NOW)
    stale = _dead_letter(at=NOW - timedelta(days=DEAD_LETTER_ACTIONABLE_DAYS + 1))
    assert fresh.is_actionable(NOW)
    assert not stale.is_actionable(NOW)
    owner = _reader(principal_id=OWNER)
    assert dead_letter_summary([fresh, stale], owner, NOW).unactionable == 1


def test_a_grant_scoped_on_a_field_the_row_does_not_carry_admits_nothing() -> None:
    """The scope is matched against the row's own closed fields and nothing else, so a grant
    written against a business attribute fails closed rather than admitting everything. Delete
    this and a departmental scope silently becomes unrestricted over the whole queue."""
    departmental = _reader(_dead_letter_grant(Scope.department("maintenance")))
    assert visible_dead_letters([_dead_letter()], departmental) == ()
    by_task = _reader(
        _dead_letter_grant(Scope(clauses=(Clause(field="task", op=Op.EQ, value="answer.compose"),)))
    )
    assert visible_dead_letters([_dead_letter()], by_task) == (_dead_letter(),)
    assert visible_dead_letters([_dead_letter(task="ingest.parse")], by_task) == ()


def test_a_dead_letter_with_no_principal_or_no_date_is_refused() -> None:
    """Without a principal nothing decides who may see the row, so the surface would show it
    to everybody who can open the screen; without a timezone the actionable window compares
    against whatever zone the container is in. Delete this and both failures arrive on the one
    screen built to show a lot at once."""
    with pytest.raises(JobsError, match="names no principal"):
        _dead_letter(principal_id="")
    with pytest.raises(JobsError, match="no timezone"):
        _dead_letter(at=datetime(2026, 9, 7, 11, 0))
    with pytest.raises(JobsError, match="no job id or no task"):
        _dead_letter(task=" ")


def test_the_capability_a_reader_needs_is_the_tools_own_and_not_the_consoles() -> None:
    """`brain.console.reads.ConsoleRead` refuses a plane capability in that position precisely
    so a screen cannot be admitted by the grant that lets somebody open the console. Delete
    this and the dead-letter screen is reachable by whoever is trusted with settings."""
    assert DEAD_LETTER_CAPABILITY.value == "read:job.dead_letter"
    assert not DEAD_LETTER_CAPABILITY.value.startswith("read:console.")
    # And it is a real capability rather than a string that looks like one, so a grant
    # written against it is evaluated by the same machinery as every other grant.
    assert isinstance(DEAD_LETTER_CAPABILITY, Capability)


def test_an_interruption_says_why_this_row_is_in_front_of_somebody() -> None:
    """A state name on its own does not tell the person who has to act why the row is theirs,
    which is the same reason `brain.ops.idempotency.Resumption` carries its reason. Delete this
    and an operator gets a verdict with no cause and goes looking in the logs for one."""
    stopped = interrupt(_record().started(), InterruptionKind.TIMEOUT, now=NOW)
    assert isinstance(stopped, Interruption)
    assert stopped.reason.strip()
    assert stopped.kind is InterruptionKind.TIMEOUT
