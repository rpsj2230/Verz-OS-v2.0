"""What a crash leaves behind, what the driver does with it, and what is re-asked on the way
back.

`tests/invariants/test_crash_exactly_once.py` holds the one property that must never bend,
which is that a kill after any boundary leaves at most one side effect. This file is about
behaviour: that the join between the queue's verdict and the operation record narrows and
never widens, that the derived checks can be shown producing their own findings, that a
read-back refuses an answer nobody declared, and that a policy or a principal changing between
two attempts is judged at the attempt rather than at the enqueue.

**Every date here is 2019 or 2999 on purpose.** `brain.ops.queue.verdict_for` and
`EntitlementSet.scope_for` both compare against a clock, and a fixture near the wall clock is
a test that reports a defect on a schedule nobody chose. `tests/unit/test_scope_and_capability.py`
makes the same choice for the same reason and says so. It matters twice over in the
entitlement tests below, where an instant *before* an expiry that has already passed in real
time is the whole point: those pass only because the instant is a parameter.

Task ids: M17.2.2, M17.2.3, M17.2.4, M17.2.5, M30.4.4, M30.4.6, M30.4.7
"""

from __future__ import annotations

import enum
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType, ModuleType

import pytest

from brain.connectors.throttle import HTTP_TOO_MANY_REQUESTS, CallOutcome, classify
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition
from brain.core.field_policy import Classification, FieldPolicy, FieldRule
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.leash import (
    Action,
    CheckName,
    Decision,
    Leash,
    LeashEntry,
    Route,
    decide,
    route_for,
)
from brain.ops import crash
from brain.ops.crash import (
    ANSWERS,
    NOTHING_HAPPENED,
    QUARANTINE_WITH_A_RECORD,
    SOMETHING_MAY_HAVE_HAPPENED,
    VERDICT_FLOOR,
    Boundary,
    CrashError,
    Crossing,
    Machine,
    Recovery,
    answer_of,
    boundary_gaps,
    durable_machines,
    machine_gaps,
    recovery_for,
    redrive,
    resume_points,
    runnable_again,
    side_effect_boundaries,
    stored_reach_gaps,
    unplanned_dispositions,
    verify_once,
)
from brain.ops.idempotency import (
    Disposition,
    Operation,
    OperationState,
    Verification,
    derive_key,
    resume,
    state_after_call,
)
from brain.ops.jobs import JobRecord
from brain.ops.queue import MAX_REDRIVES, InFlight, Redrive, Verdict, stale_after, verdict_for

#: Pinned decades away from any plausible wall clock; see the module docstring.
NOW = datetime(2019, 3, 4, 12, 0, tzinfo=UTC)

KEY = derive_key(principal_id="u_1", tool="xero.create_invoice", intent_ref="turn_1")

OPERATION_MACHINE = "brain.ops.idempotency.ALLOWED_TRANSITIONS"
JOB_MACHINE = "brain.ops.jobs.ALLOWED_TRANSITIONS"


def an_operation(state: OperationState = OperationState.PENDING) -> Operation:
    return Operation(
        key=KEY,
        connector="xero",
        tool="xero.create_invoice",
        principal_id="u_1",
        intent_ref="turn_1",
        state=state,
    )


def an_entry(
    *,
    verdict: Verdict,
    task: str = "xero.raise_invoice",
    job_id: str = "j_1",
) -> InFlight:
    """An in-flight row that `verdict_for` gives exactly `verdict` for.

    Built through the verdict rather than by copying its three conditions, and asserted at the
    end. A fixture that constructs a row it believes is quarantined and is actually running is
    a test whose subject silently moved, which is the failure the whole of `verdict_for`'s own
    docstring is about.
    """
    fresh = NOW - timedelta(seconds=1)
    stale = NOW - stale_after() - timedelta(seconds=1)
    heartbeat = fresh if verdict is Verdict.RUNNING else stale
    redrives = MAX_REDRIVES if verdict is Verdict.DEAD_LETTER else 0
    safe = Redrive.SAFE if verdict in (Verdict.REDRIVE, Verdict.RUNNING) else Redrive.UNSAFE
    entry = InFlight(
        job_id=job_id,
        task=task,
        worker_id="w_1",
        heartbeat_at=heartbeat,
        redrives=redrives,
        redrive=safe,
    )
    assert verdict_for(entry, NOW) is verdict, "the fixture does not produce the verdict it names"
    return entry


def a_machine(
    *,
    name: str = "somewhere.else",
    states: tuple[str, ...] = ("DRAFT", "PLACED", "DOUBTFUL", "CLEARED"),
    start: str = "DRAFT",
    edges: tuple[tuple[str, str], ...] = (
        ("DRAFT", "PLACED"),
        ("PLACED", "CLEARED"),
        ("PLACED", "DOUBTFUL"),
    ),
    terminal: frozenset[str] = frozenset({"CLEARED"}),
    plan: dict[str, tuple[str, str]] | None = None,
    plan_from: str = "somewhere.else.RESUME_PLAN",
) -> Machine:
    """A durable machine this repository does not have.

    Every derived check below takes its machines as a parameter, following
    `brain.ops.queue.concurrency_gaps`, and this is what those parameters are for: the findings
    those functions exist to produce cannot be provoked with the two tables that ship here,
    because both of them are correct.
    """
    return Machine(
        module=name,
        symbol="ALLOWED_TRANSITIONS",
        kind=f"{name}.Payment",
        states=states,
        start=start,
        edges=edges,
        terminal=terminal,
        plan=MappingProxyType(
            plan
            if plan is not None
            else {
                "DRAFT": ("DRAFT", "ISSUE"),
                "PLACED": ("DOUBTFUL", "VERIFY"),
                "DOUBTFUL": ("DOUBTFUL", "VERIFY"),
                "CLEARED": ("CLEARED", "DONE"),
            }
        ),
        plan_from=plan_from,
    )


# ----------------------------------------------------- M17.2.2 the re-drive driver
def test_the_only_job_a_recovery_runs_again_is_a_safe_one_that_issued_nothing() -> None:
    """The exactly-once property of the driver, over every combination rather than a sample.

    Four verdicts by seven record situations, which is the whole input space, and exactly one
    cell of it re-runs work: a job the task author declared safe to repeat whose record says
    nothing left the process, plus the same job with no record at all. Everything else is left
    alone, verified or handed to a person.

    Delete this and any single branch of `recovery_for` can start returning `RUN_AGAIN`
    without a test noticing, which is a duplicated side effect in the only place this system
    produces one.
    """
    records: list[Operation | None] = [None, *[an_operation(state) for state in OperationState]]
    ran: set[tuple[str, str]] = set()
    for verdict in Verdict:
        entry = an_entry(verdict=verdict)
        for record in records:
            outcome = recovery_for(entry, record, NOW)
            if outcome.may_run_again:
                ran.add((verdict.value, record.state.value if record else "no record"))

    assert ran == {
        ("redrive", "no record"),
        ("redrive", "pending"),
    }


def test_a_live_job_is_left_alone_whatever_its_record_says() -> None:
    """A fresh heartbeat means a worker is still writing states into that record, so a sweep
    that verified it would be racing the process that is about to move it.

    Delete this and a recovery sweep reads a running job's mid-flight record, calls it a crash
    and issues a read-back against a source the live worker is still talking to."""
    entry = an_entry(verdict=Verdict.RUNNING)
    for state in OperationState:
        outcome = recovery_for(entry, an_operation(state), NOW)
        assert outcome.recovery is Recovery.LEAVE_IT, state


def test_a_quarantined_job_whose_side_effect_nobody_can_settle_becomes_a_read_back() -> None:
    """The one new answer in the module, and the reason it exists.

    `verdict_for` sends every orphaned unsafe job to a person, which is right when nothing is
    known. When a record says nobody knows whether the effect landed, asking the source is
    what resolves that, and asking is a machine's job.

    Delete this and every orphaned job with a side effect goes to a human queue, which is the
    queue people stop reading."""
    entry = an_entry(verdict=Verdict.QUARANTINE)
    unsettled = [
        state
        for state in OperationState
        if resume(an_operation(state)).disposition is Disposition.VERIFY
    ]
    assert unsettled, "no state resumes by verifying, so this test asserts nothing"
    for state in unsettled:
        outcome = recovery_for(entry, an_operation(state), NOW)
        assert outcome.recovery is Recovery.VERIFY, state


def test_a_quarantined_job_whose_side_effect_is_settled_still_needs_a_person() -> None:
    """The defect the first draft of this module shipped, pinned so it cannot come back.

    That version ordered the four actions by how much work they are and took the smaller of
    the queue's answer and the record's, so a quarantined job whose operation record said
    `DONE` scored below `NEEDS_A_PERSON` and came out as `LEAVE_IT`. The side effect had
    indeed happened once. The *job* was still orphaned, still not declared safe to repeat, and
    nothing was ever going to come back for it: `brain.ops.queue.Verdict` names that exact end
    state, which is a row that sits in running for ever.

    Delete this and the record is allowed to settle a question it was never asked."""
    entry = an_entry(verdict=Verdict.QUARANTINE)
    settled = [
        state
        for state in OperationState
        if resume(an_operation(state)).disposition is not Disposition.VERIFY
    ]
    assert settled, "every state resumes by verifying, so this test asserts nothing"
    for state in settled:
        outcome = recovery_for(entry, an_operation(state), NOW)
        assert outcome.recovery is Recovery.NEEDS_A_PERSON, state


def test_a_dead_letter_is_not_narrowed_by_anything_its_record_says() -> None:
    """The cap is about the worker, not about the work.

    A job that has taken three containers down will take a fourth, whatever its record says
    about the side effect, so no disposition may turn a dead letter into a run, a verification
    or a row nobody looks at.

    Delete this and a poison pill with a tidy operation record gets quietly re-driven."""
    entry = an_entry(verdict=Verdict.DEAD_LETTER)
    for state in OperationState:
        outcome = recovery_for(entry, an_operation(state), NOW)
        assert outcome.recovery is Recovery.NEEDS_A_PERSON, state


def test_a_task_that_declares_itself_safe_while_its_record_says_it_issued_goes_to_a_person() -> (
    None
):
    """Two declarations that cannot both be true, and the reason both halves are in the
    sentence.

    Believing the task author re-runs a side effect nobody can withdraw. Believing the record
    parks work that was genuinely safe. Neither is defensible without knowing which is wrong,
    so the row names both and a person decides.

    Delete this and whichever of the two the code happens to read first silently wins."""
    entry = an_entry(verdict=Verdict.REDRIVE)
    outcome = recovery_for(entry, an_operation(OperationState.SENT), NOW)
    assert outcome.recovery is Recovery.NEEDS_A_PERSON
    assert "re-drive safe" in outcome.reason
    assert str(OperationState.SENT) in outcome.reason


def test_every_verdict_has_a_floor_and_only_one_of_them_can_reach_running_again() -> None:
    """The constant, asserted against something outside itself.

    A mapping tested by comparing its own values to themselves is green for every value it
    could hold. What makes this one right is a property of `brain.ops.queue`: the verdict that
    may run again is the one `verdict_for` gives an orphaned job whose task was declared safe
    to repeat, and every other verdict is a reason to do less.

    Delete this and an entry can be repointed at `RUN_AGAIN` with the whole suite green."""
    assert set(VERDICT_FLOOR) == set(Verdict)
    runnable = [
        verdict for verdict, action in VERDICT_FLOOR.items() if action is Recovery.RUN_AGAIN
    ]
    assert runnable == [verdict_for(an_entry(verdict=Verdict.REDRIVE), NOW)]
    assert VERDICT_FLOOR[verdict_for(an_entry(verdict=Verdict.RUNNING), NOW)] is Recovery.LEAVE_IT


def test_a_record_may_only_replace_a_quarantine_with_a_read_back() -> None:
    """`THE_RECORD_NARROWS_THE_VERDICT_AND_NEVER_WIDENS_IT` as data, and exhaustive.

    A missing disposition would pick a behaviour by accident, and the accident nobody notices
    is the one that leaves an orphaned job where nothing will find it. The one entry that is
    not `NEEDS_A_PERSON` is the disposition that means nobody knows, which is the only
    question a read-back can answer.

    Delete this and a fifth disposition arrives with no answer, or a fourth one is repointed
    at `RUN_AGAIN`."""
    assert set(QUARANTINE_WITH_A_RECORD) == set(Disposition)
    assert {
        disposition
        for disposition, action in QUARANTINE_WITH_A_RECORD.items()
        if action is not Recovery.NEEDS_A_PERSON
    } == {Disposition.VERIFY}
    assert QUARANTINE_WITH_A_RECORD[Disposition.VERIFY] is Recovery.VERIFY


def test_every_in_flight_row_gets_a_row_back_including_the_ones_left_alone() -> None:
    """A sweep whose output omits the rows it decided to leave alone is one a reader cannot
    tell apart from a sweep that never saw them.

    Delete this and a recovery report can silently shrink to the interesting rows, and the
    live job it dropped looks like a job nothing is tracking."""
    entries = [an_entry(verdict=verdict, job_id=f"j_{verdict.value}") for verdict in Verdict]
    plan = redrive(entries, {}, NOW)
    assert [one.job_id for one in plan] == [one.job_id for one in entries]
    assert runnable_again(plan) == ("j_redrive",)


def test_a_recovery_that_needs_a_person_says_which_record_sent_it_there() -> None:
    """An action name on its own does not tell whoever picks the row up which of the two
    records is the problem, and a queue of rows that do not say why is a queue nobody triages.

    **Distinct rather than merely present**, because four verdicts that all say the same thing
    is the same failure as four that say nothing. Each of the four branches was individually
    removable with the earlier version of this test green: deleting the dead-letter branch made
    a poison pill read as a re-drive-safe job, and deleting the re-drive branch made it read as
    a fresh heartbeat, and neither is what happened.

    Delete this and the reasons can go empty, or converge, with every verdict assertion still
    green."""
    reasons: dict[Verdict, str] = {}
    for verdict in Verdict:
        entry = an_entry(verdict=verdict)
        reasons[verdict] = recovery_for(entry, None, NOW).reason
        assert reasons[verdict].strip()
        for state in OperationState:
            assert recovery_for(entry, an_operation(state), NOW).reason.strip()

    assert len(set(reasons.values())) == len(Verdict)
    assert "nothing to read back" in reasons[Verdict.QUARANTINE]
    assert "doing this to workers" in reasons[Verdict.DEAD_LETTER]
    assert "declared re-drive safe" in reasons[Verdict.REDRIVE]
    assert "heartbeat is fresh" in reasons[Verdict.RUNNING]


def test_a_job_with_no_record_is_not_a_job_that_issued_nothing() -> None:
    """The default that keeps the absence of evidence from reading as evidence of absence.

    An orphaned job with no operation record is a job that issued nothing *this layer can
    see*. `Redrive.UNSAFE` is what makes that safe: only a task the author positively declared
    repeatable is run again on the strength of an absent record.

    Delete this and a missing row becomes a licence to re-run."""
    quarantined = recovery_for(an_entry(verdict=Verdict.QUARANTINE), None, NOW)
    assert quarantined.recovery is Recovery.NEEDS_A_PERSON
    assert "nothing to read back" in quarantined.reason
    assert recovery_for(an_entry(verdict=Verdict.REDRIVE), None, NOW).may_run_again


# -------------------------------------------- M17.2.3 the boundaries, and the checks over them
def test_the_two_scans_and_the_recovery_plans_agree_about_this_repository() -> None:
    """The enumeration's own health check, run against the tree rather than a fixture.

    A disagreement between the syntactic and the runtime scan means the boundary set depends
    on which one a caller asked, and a machine with no recovery plan it can reach means a
    crash in it is not answerable at all.

    Delete this and the derivation can start disagreeing with itself, which shows up as a
    boundary set that is different in a test from what it is in a sweep."""
    assert machine_gaps() == ()
    assert boundary_gaps() == ()
    assert unplanned_dispositions() == ()


def test_the_two_scans_walk_the_same_tree() -> None:
    """The scopes, asserted against each other rather than each against itself.

    This is the defect the first draft of `machine_gaps` shipped: it read the syntax of every
    file under `src/brain` and the objects of `brain.ops` alone, so a state machine written
    anywhere else in the tree would have been reported as the two scans disagreeing rather
    than as a machine. The finding would have named a real module and been entirely wrong
    about what was wrong with it.

    Narrowing the runtime scan is the mutation that matters, and it is invisible today because
    both machines happen to live in `brain.ops`. Tying the package the runtime scan walks to
    the directory the syntactic scan reads is what makes it visible.

    Delete this and the two halves can drift apart again, silently, in the direction that
    reports the difference between two scopes as a difference between two scans."""
    assert crash.SRC.name == crash.PACKAGE
    assert crash.SRC == crash.REPO / "src" / crash.PACKAGE
    assert {module for module, _ in crash.declared_tables()} == {
        module for module, _ in crash.imported_tables()
    }


def test_a_machine_with_no_recovery_plan_it_can_reach_is_reported() -> None:
    """The check shown producing its own finding, which the two correct tables here cannot do.

    `brain.ops.jobs` declares a machine and no plan and is not a gap, because it imports one.
    A third machine that neither declares nor borrows is a state graph nobody can recover
    from, and it would otherwise arrive looking exactly like the one that is fine.

    Delete this and the distinction between borrowing an answer and having none stops being
    checked."""
    findings = machine_gaps([a_machine(plan={}, plan_from="")])
    assert any("declares no recovery plan and imports none" in one for one in findings)
    assert machine_gaps([a_machine()]) == ()


def test_a_machine_whose_records_declare_no_starting_state_is_reported() -> None:
    """The write that created the record is a boundary and it is not an edge, so a machine
    that cannot name where a new record lands has a crash point nothing enumerates.

    Delete this and the first line of `CRASH_POINTS` quietly has no derived counterpart for
    the next machine somebody writes."""
    findings = machine_gaps([a_machine(start="")])
    assert any("the write that creates a record lands nowhere" in one for one in findings)


def test_an_edge_from_a_state_that_may_have_issued_into_one_that_reissues_is_reported() -> None:
    """The duplicate-side-effect bug as a graph property, and the check shown firing.

    This is the edge `brain.ops.idempotency.NO_PATH_FROM_UNKNOWN_TO_A_SECOND_ISSUE` exists to
    forbid: a helpful "a verified-absent operation can just be issued again", from the state
    where nobody knows back to the state a worker issues from. The first draft of
    `boundary_gaps` compared the landing state against itself, and `ISSUE` is classified as
    nothing-having-happened, so the two halves of its condition were disjoint by construction
    and no table could ever have produced the finding.

    Delete this and that check goes back to being unfireable, which reads exactly like a check
    that passes."""
    reissuing = a_machine(
        edges=(
            ("DRAFT", "PLACED"),
            ("PLACED", "CLEARED"),
            ("PLACED", "DOUBTFUL"),
            ("DOUBTFUL", "DRAFT"),
        )
    )
    findings = boundary_gaps([reissuing])
    assert any("DOUBTFUL to DRAFT" in one and "resumes by issuing" in one for one in findings)
    assert boundary_gaps([a_machine()]) == ()


def test_a_disposition_nobody_has_classified_is_not_read_as_nothing_having_happened() -> None:
    """The partition, and the direction its failure has to take.

    A disposition in neither set takes the safe-looking branch of an `in NOTHING_HAPPENED`
    test, which is the wrong branch: unclassified means nobody thought about it, and
    nobody-thought-about-it must never read as nothing-happened.

    Delete this and a fifth disposition joins the machine silently, on the flattering side."""
    invented = a_machine(
        plan={
            "DRAFT": ("DRAFT", "ISSUE"),
            "PLACED": ("DOUBTFUL", "PROBABLY_FINE"),
            "DOUBTFUL": ("DOUBTFUL", "VERIFY"),
            "CLEARED": ("CLEARED", "DONE"),
        }
    )
    assert unplanned_dispositions([invented]) == ("PROBABLY_FINE",)
    assert "PROBABLY_FINE" in boundary_gaps([invented])
    assert frozenset() == NOTHING_HAPPENED & SOMETHING_MAY_HAVE_HAPPENED


def test_the_two_sets_of_dispositions_partition_the_vocabulary_they_describe() -> None:
    """The constants, asserted against `Disposition` rather than against themselves.

    Each is also tied to what `brain.ops.idempotency.resume` actually does: the state a
    recovering worker issues from is one where nothing happened, and the state it asks about
    is one where something may have.

    Delete this and either set can be repointed with the suite green, which puts a state that
    may have billed somebody on the nothing-happened side."""
    assert {one.name for one in Disposition} == NOTHING_HAPPENED | SOMETHING_MAY_HAVE_HAPPENED
    assert frozenset() == NOTHING_HAPPENED & SOMETHING_MAY_HAVE_HAPPENED
    assert resume(an_operation(OperationState.PENDING)).disposition.name in NOTHING_HAPPENED
    assert resume(an_operation(OperationState.SENT)).disposition.name in SOMETHING_MAY_HAVE_HAPPENED


def test_a_machine_that_borrows_its_recovery_plan_does_not_answer_for_its_own_boundaries() -> None:
    """The second defect the first draft shipped, and the more dangerous of the two.

    `brain.ops.jobs` borrows `RESUME_PLAN`, which is keyed on an operation's states, so it has
    no answer of its own to "may this job write have left the world different". The first
    version answered `False` at every job boundary, which puts that module on record as saying
    a job killed mid-flight cannot have changed anything, in flat contradiction of its own
    `_side_effect_state`. `None` is the honest value: a sweep can act on `False`, and acting
    on it means re-driving a job that had already sent something.

    Delete this and the flattering default comes back as an optimisation."""
    borrowed = [one for one in side_effect_boundaries() if one.machine == JOB_MACHINE]
    assert borrowed, "the job machine contributed no boundaries, so this asserts nothing"
    assert {one.world_may_have_changed for one in borrowed} == {None}

    own = [one for one in side_effect_boundaries() if one.machine == OPERATION_MACHINE]
    assert {one.world_may_have_changed for one in own} == {True, False}


def test_the_call_is_derived_as_the_step_from_nothing_issued_to_nobody_knowing() -> None:
    """Why the edge from pending to failed is not a side-effect boundary and the other one is.

    A refusal before anything left the process is a claim, not a doubt, so a crash after it
    has nothing to verify. Derived from the pair of dispositions rather than from a rule about
    terminal states, which was the first draft's construction and only happened to give the
    right answer for this table.

    Delete this and the effect boundary becomes whichever edge somebody remembers."""
    effects = [
        (one.before, one.after)
        for one in side_effect_boundaries()
        if one.crossing is Crossing.EFFECT
    ]
    assert effects == [("PENDING", "SENT")]


# ------------------------------------------------- M17.2.4 resuming with the state intact
def test_resuming_from_every_boundary_keeps_everything_the_next_attempt_needs() -> None:
    """State intact means the identifiers survive, because they are the whole of the state.

    A recovering worker has to be able to read the record back, ask the source about it under
    the same key, and put it in front of a person if it cannot. Every one of those needs the
    key, the connector, the tool, the principal and the intent, and `Operation.__post_init__`
    refuses a record missing any of them.

    Delete this and a resume can quietly return a record that no longer identifies what it was
    for, which presents as a read-back against the wrong key."""
    for boundary in side_effect_boundaries():
        if boundary.machine != OPERATION_MACHINE:
            continue
        before = an_operation(OperationState[boundary.after])
        after = resume(before).operation
        assert (after.key, after.connector, after.tool) == (
            before.key,
            before.connector,
            before.tool,
        )
        assert (after.principal_id, after.intent_ref) == (before.principal_id, before.intent_ref)


def test_resuming_twice_from_one_boundary_reaches_the_same_place() -> None:
    """A restart during a restart is an ordinary event, so the recovery step has to be stable.

    A resume that moved the record a second time would walk it through the graph on every
    restart, which for the state that means nobody knows is a record that leaves the one place
    a read-back would have found it.

    Delete this and a worker crash-looping quietly advances records nobody issued anything
    for."""
    for state in OperationState:
        once = resume(an_operation(state)).operation
        twice = resume(once).operation
        assert twice.state is once.state, state


# ----------------------------------------- M17.2.5 the re-check at every resume point
def test_no_record_a_resume_reads_back_carries_a_permission_decision() -> None:
    """The whole of the resume-time entitlement guarantee, stated as an absence.

    There is no re-check step to test, and that is the design: a resumable record carries
    identifiers and no entitlement set, so the work cannot be reconstituted without going back
    through the gate, and going back through the gate is what resolves the reach at that
    instant.

    Delete this and a `reach` field can be added to a job row underneath the paragraph that
    says it must not be, which is a revoked grant still in force at the next attempt."""
    assert stored_reach_gaps() == ()
    assert set(resume_points()) >= {Operation, JobRecord}


def test_a_record_that_carried_a_reach_would_be_reported() -> None:
    """The check shown refusing something, which the records here cannot do because none of
    them carries one.

    The question of what a reach looks like is `brain.ops.jobs.reach_carrying_fields`'s rather
    than this module's, so the two resume points cannot come to different answers about
    whether a `Scope` is a permission decision.

    Delete this and a guard that has never been seen to fire is the whole of M17.2.5."""

    @dataclass(frozen=True)
    class Resumable:
        job_id: str
        state: OperationState
        reach: EntitlementSet

    findings = stored_reach_gaps([Resumable])
    assert len(findings) == 1
    assert "carries ['reach']" in findings[0]
    assert stored_reach_gaps([Operation]) == ()


def test_every_machine_contributes_the_record_a_resume_would_read_back() -> None:
    """The derivation, rather than a list of two classes somebody wrote down.

    A third machine with a record on it arrives here without anybody remembering, which is the
    same argument the boundary set makes about itself: what would go stale is a list.

    Delete this and a new record type is outside the reach check that says no resume carries a
    permission decision."""
    machines = durable_machines()
    assert machines
    for machine in machines:
        _, _, enum_name = machine.kind.rpartition(".")
        matching = [
            record
            for record in resume_points()
            if any(
                enum_name in str(getattr(spec, "type", ""))
                for spec in getattr(record, "__dataclass_fields__", {}).values()
            )
        ]
        assert matching, f"{machine.name} has no record type a resume could read back"


# --------------------------------- M30.4.4 a connector answering rubbish, and a 429
def test_a_read_back_that_answered_a_word_nobody_declared_settles_nothing() -> None:
    """A read-back is the only exit from the state where nobody knows, so the one thing it may
    never be is generous.

    Delete this and the natural repair for a lookup that keeps raising in production is
    `.get(answer, FOUND)`, which settles an operation as having succeeded on a value carrying
    no evidence at all."""
    for rubbish in ("ok", "FOUND", "yes", "", "found "):
        with pytest.raises(CrashError, match="not settled on a word"):
            answer_of(rubbish)


def test_a_read_back_that_answered_with_something_other_than_a_word_is_refused() -> None:
    """`True` is what a hurried adapter returns for "yes it is there", and
    `isinstance(True, int)` is `True`, so any check admitting a number admits it.

    Delete this and a connector that answers with a boolean, a dict or nothing at all settles
    a side effect as having happened."""
    for rubbish in (True, False, 1, 0, None, {"found": True}, Verification):
        with pytest.raises(CrashError, match="which is not one of"):
            answer_of(rubbish)


def test_every_answer_the_vocabulary_contains_is_accepted() -> None:
    """The positive sibling. A guard tested only by its refusals is satisfied by a function
    that refuses everything, and a read-back that refuses everything leaves every operation in
    the state that needs a person.

    Delete this and `answer_of` can be tightened into a function nothing can get through."""
    for answer in Verification:
        assert answer_of(answer) is answer
        assert answer_of(answer.value) is answer
    assert {one.value for one in Verification} == ANSWERS


def test_a_refused_answer_leaves_the_record_where_it_can_be_asked_again() -> None:
    """Recoverable by construction rather than by care.

    `RESUME_PLAN` sends both the state where nobody knows and the state where a read-back was
    in flight to `VERIFY`, so a connector that answered rubbish is asked again. That is the
    whole reason verification rather than retry is the way out.

    Delete this and a malformed answer can be made to settle the record on the way past."""
    operation = an_operation(OperationState.UNKNOWN)
    with pytest.raises(CrashError):
        verify_once(operation, lambda _: "probably")
    assert operation.state is OperationState.UNKNOWN
    assert resume(operation).disposition is Disposition.VERIFY


def test_a_read_back_that_answers_properly_still_settles_the_operation() -> None:
    """The other positive sibling, and the one that keeps `verify_once` a wrapper rather than
    a second implementation.

    Delete this and the delegation to `brain.ops.idempotency.verify` can be replaced by
    something that only ever raises."""
    found = verify_once(an_operation(OperationState.UNKNOWN), lambda _: Verification.FOUND)
    assert found.state is OperationState.SUCCEEDED
    absent = verify_once(an_operation(OperationState.UNKNOWN), lambda _: "absent")
    assert absent.state is OperationState.FAILED


def test_a_rate_limit_refusal_settles_an_operation_without_asking_the_source() -> None:
    """The 429 half of this leaf, driven from the status rather than from the outcome name.

    A 429 is the one status this system takes as a definite answer with no read-back, on the
    grounds that a rate limiter refuses at the door. The risk in that is real and is written
    down in `brain.ops.idempotency.WHAT_THE_CRASH_MODEL_DOES_NOT_COVER`; what must not happen
    is the set of statuses that settle an operation growing quietly.

    Delete this and an outcome added to the vocabulary and mapped to failed joins that set
    without anybody arguing for it."""
    assert classify(status=HTTP_TOO_MANY_REQUESTS) is CallOutcome.QUOTA
    assert state_after_call(CallOutcome.QUOTA) is OperationState.FAILED
    assert set(crash.definite_refusals()) == {CallOutcome.QUOTA, CallOutcome.REJECTED}


def test_a_source_that_never_answered_is_not_a_definite_refusal() -> None:
    """The positive sibling of the set above, and the branch this whole subject exists for.

    A timeout, a dropped connection and a 500 all mean the request may have been processed and
    the answer lost, which is not a refusal and must never be classified as one.

    Delete this and `definite_refusals` can widen to every outcome with the suite green."""
    assert classify(timed_out=True) is CallOutcome.UNAVAILABLE
    assert state_after_call(CallOutcome.UNAVAILABLE) is OperationState.UNKNOWN
    assert CallOutcome.UNAVAILABLE not in crash.definite_refusals()


# ------------------------------------ M30.4.6 a policy that changed between two attempts
class Ticket(Entity):
    status: str = ""


UPDATE_STATUS = ToolDefinition(
    name="ticket.update_status",
    description="Set the status of a support ticket",
    entity="ticket",
    required_capability="write:ticket.status",
    side_effect=SideEffect.WRITE,
    identity_mode=IdentityMode.DELEGATED,
)

CLEAN = RiskAssessment(score=0, matched=())

AGENT = "ag_support"


def entitlement(
    *capabilities: str,
    principal_id: str = "u_weiling",
    not_after: datetime | None = None,
) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(
            Grant(capability=Capability(value=value), scope=Scope.unrestricted())
            for value in capabilities
        ),
        not_after=not_after,
    )


CALLER = entitlement("write:ticket.status", "read:ticket.status")
CEILING = entitlement("write:ticket.status", "read:ticket.status", principal_id="ag_support")


def an_action() -> Action:
    return Action(
        agent_id=AGENT,
        tool=UPDATE_STATUS,
        target="ticket.update_status",
        touched_fields=("status",),
        row={"department": "maintenance"},
        args={"status": "closed"},
    )


def a_leash(rung: AutonomyTier) -> Leash:
    return Leash(
        entries=(
            LeashEntry(
                agent_id=AGENT,
                target="ticket.update_status",
                scope=Scope.unrestricted(),
                rung=rung,
            ),
        )
    )


def a_policy(capability: str) -> FieldPolicy:
    return FieldPolicy(
        rules=(FieldRule.of("ticket", "status", capability, Classification.INTERNAL),)
    )


def attempt(
    *,
    leash: Leash,
    policy: FieldPolicy,
    caller: EntitlementSet = CALLER,
    at: datetime = NOW,
) -> Decision:
    """One attempt at the same action, under whatever policy is in force at `at`."""
    return decide(
        an_action(),
        caller=caller,
        agent_ceiling=CEILING,
        policy=policy,
        leash=leash,
        assessment=CLEAN,
        now=at,
    )


def test_a_leash_tightened_between_two_attempts_binds_the_second_one() -> None:
    """M30.4.6, as a state rather than as infrastructure: the same job, attempted twice, with
    the autonomy rung changed in between.

    The decision is taken at the attempt and nothing about it is carried from the first one,
    which is what makes tightening a leash take effect on work that is already in flight. A
    system that cached the first decision would go on executing for as long as the job lived.

    Delete this and a rung lowered during an incident applies only to jobs enqueued after
    somebody lowered it."""
    first = attempt(leash=a_leash(AutonomyTier.AUTONOMOUS), policy=a_policy("read:ticket.status"))
    assert route_for(first) is Route.EXECUTE

    second = attempt(leash=a_leash(AutonomyTier.SHADOW), policy=a_policy("read:ticket.status"))
    assert route_for(second) is Route.SIMULATE
    assert second.tier is AutonomyTier.SHADOW


def test_a_field_reclassified_between_two_attempts_masks_the_second_one() -> None:
    """The other half of a policy change, and the half that is silent.

    A leash change moves the route, which somebody watching would see. A field policy change
    moves what the same action is allowed to touch, and the second attempt of a job that was
    permitted an hour ago has to be re-checked against the policy in force now rather than the
    one in force when it was queued.

    Delete this and reclassifying a field protects only the requests that arrive afterwards."""
    permitted = attempt(
        leash=a_leash(AutonomyTier.AUTONOMOUS), policy=a_policy("read:ticket.status")
    )
    assert permitted.permitted

    tightened = attempt(
        leash=a_leash(AutonomyTier.AUTONOMOUS), policy=a_policy("read:ticket.restricted")
    )
    assert not tightened.permitted
    assert [one.name for one in tightened.checks if not one.permits] == [CheckName.MASK]


# -------------------------------- M30.4.7 a principal disabled between two attempts
def test_a_caller_disabled_between_two_attempts_is_refused_at_the_second() -> None:
    """M30.4.7 on the request path, and the reason a queue row carries an identifier and never
    a reach.

    The same action, the same leash, the same policy, attempted twice with the caller's
    entitlement set expiring in between. `E_run(caller, agent)` is evaluated at the attempt, so
    the second one is refused. A row that had carried the first attempt's answer would be the
    one place in this system where a revocation does not take effect.

    Delete this and a leaver's queued work runs at the reach they had when they queued it."""
    disabled_at = NOW + timedelta(hours=1)
    leaver = entitlement("write:ticket.status", "read:ticket.status", not_after=disabled_at)

    first = attempt(
        leash=a_leash(AutonomyTier.AUTONOMOUS),
        policy=a_policy("read:ticket.status"),
        caller=leaver,
        at=NOW,
    )
    assert first.permitted

    second = attempt(
        leash=a_leash(AutonomyTier.AUTONOMOUS),
        policy=a_policy("read:ticket.status"),
        caller=leaver,
        at=disabled_at + timedelta(seconds=1),
    )
    assert not second.permitted
    assert [one.name for one in second.checks if not one.permits] == [CheckName.CAPABILITY]


def test_a_reader_disabled_between_two_attempts_is_judged_at_the_instant_it_is_asked() -> None:
    """The shape the defect fixed on 2026-09-08 got wrong, pinned from the other side.

    The four surfaces that ask "may this reader be told this" are written
    `requirement(thing).intersect(reader)`, which puts the real principal on the right, and
    the right-hand side's expiry is the one `intersect` evaluates. Until that method could be
    told the instant it used the process clock, so a reader was judged against whenever the
    process happened to be running rather than against the moment being reasoned about.

    **The dates are what make this a test rather than a coincidence.** The reader's access
    lapses in 2019, which is in the past by every wall clock this will ever run on, and the
    first assertion asks about an instant before that. It passes only because the instant is a
    parameter. `tests/invariants/test_single_implementation.py` pins which call sites pass one.

    Delete this and the wall clock comes back, silently and in the permissive direction."""
    lapses_at = datetime(2019, 6, 1, tzinfo=UTC)
    reader = entitlement("read:ticket.status", not_after=lapses_at)
    requirement = entitlement("read:ticket.status", principal_id="ticket")
    capability = Capability(value="read:ticket.status")

    before = requirement.intersect(reader, lapses_at - timedelta(seconds=1))
    assert before.holds(capability, lapses_at - timedelta(seconds=1))

    after = requirement.intersect(reader, lapses_at + timedelta(seconds=1))
    assert after.grants == ()


def test_a_principal_who_is_still_entitled_is_not_refused_by_either_shape() -> None:
    """The positive sibling of both cases above.

    A re-check tested only by its refusals is satisfied by one that refuses everybody, and an
    entitlement check that refuses everybody is indistinguishable from an outage.

    Delete this and tightening the resume-time check has no counterweight."""
    live = entitlement(
        "write:ticket.status", "read:ticket.status", not_after=NOW + timedelta(days=1)
    )
    decision = attempt(
        leash=a_leash(AutonomyTier.AUTONOMOUS),
        policy=a_policy("read:ticket.status"),
        caller=live,
        at=NOW,
    )
    assert decision.permitted

    reader = entitlement("read:ticket.status", not_after=datetime(2999, 1, 1, tzinfo=UTC))
    requirement = entitlement("read:ticket.status", principal_id="ticket")
    assert requirement.intersect(reader, NOW).holds(Capability(value="read:ticket.status"), NOW)


def test_a_boundary_names_the_table_it_came_out_of_rather_than_the_enum() -> None:
    """Two machines could be keyed on one enum, and a boundary that named only the enum would
    be a boundary nobody could trace back to a table.

    Delete this and the machine field can drift back to the enum's name, which reads correctly
    right up until a second table uses the same states."""
    assert {one.machine for one in side_effect_boundaries()} == {
        one.name for one in durable_machines()
    }
    assert all(one.machine.endswith(".ALLOWED_TRANSITIONS") for one in side_effect_boundaries())


def test_a_boundary_records_the_state_a_next_process_would_find() -> None:
    """What makes a boundary testable at all: a kill is not simulated, it is a resume from the
    state the write landed in.

    Delete this and `after` can start meaning the state before the write, which inverts every
    property asserted over the boundary set."""
    created = [one for one in side_effect_boundaries() if one.crossing is Crossing.CREATE]
    assert [(one.machine, one.before, one.after) for one in created] == [
        (OPERATION_MACHINE, "", "PENDING"),
        (JOB_MACHINE, "", "QUEUED"),
    ]
    assert all(isinstance(one, Boundary) for one in side_effect_boundaries())


# ------------------------------- the scans themselves, driven over a tree nobody ships
#: Source that reads as a transition table, and eight that deliberately do not.
#:
#: `_is_transition_table` calls itself "deliberately narrow", and narrowness is a claim about
#: what it *refuses*: a matcher that accepted an ordinary lookup table would put an invented
#: machine in the boundary set, which is worse than a set that is short, because the runtime
#: scan beside it exists to catch short. Nothing checked any of the refusals, so every one of
#: them survived a mutation to `if False:`.
A_REAL_TABLE = "ALLOWED = MappingProxyType({State.A: frozenset({State.B}), State.B: frozenset()})"

AN_ANNOTATED_TABLE = (
    "ALLOWED: Mapping[State, frozenset[State]] = MappingProxyType({State.A: frozenset()})"
)

NEAR_MISSES: Mapping[str, str] = MappingProxyType(
    {
        "the target is an attribute rather than a name": (
            "holder.ALLOWED = MappingProxyType({State.A: frozenset({State.B})})"
        ),
        "the value is a dictionary rather than a call": (
            "ALLOWED = {State.A: frozenset({State.B})}"
        ),
        "the call is not MappingProxyType": "ALLOWED = dict({State.A: frozenset({State.B})})",
        "the argument is a name rather than a dictionary": "ALLOWED = MappingProxyType(elsewhere)",
        "a key is not an attribute of anything": ('ALLOWED = MappingProxyType({"a": frozenset()})'),
        "a value is a set literal rather than a call": (
            "ALLOWED = MappingProxyType({State.A: {State.B}})"
        ),
        "a value is a set rather than a frozenset": "ALLOWED = MappingProxyType({State.A: set()})",
        "the keys belong to two different enums": (
            "ALLOWED = MappingProxyType({State.A: frozenset(), Other.B: frozenset()})"
        ),
    }
)


def a_tree(tmp_path: Path, **modules: str) -> Path:
    """A source root holding fabricated modules, for the syntactic scan to read.

    `declared_tables` names a module by its path under the root, so a file `fake.py` under a
    root called `brain` is `brain.fake`, which is what lets these tests pair a fabricated
    source with a fabricated module object below.
    """
    root = tmp_path / "brain"
    root.mkdir(exist_ok=True, parents=True)
    for name, source in modules.items():
        (root / f"{name}.py").write_text(f"{source}\n", encoding="utf-8", newline="\n")
    return root


def test_a_table_is_recognised_by_its_shape_and_by_nothing_else(tmp_path: Path) -> None:
    """Both halves of "deliberately narrow", and only the first was ever checked.

    A shape that is not a transition table must not be read as one, and there are eight ways
    to nearly be one. Every one of them survived being replaced by `if False:` until this
    existed, because the two tables this repository ships are both correct and no test had
    ever shown the matcher a near miss.

    Delete this and the matcher can widen one clause at a time, and each widening puts a
    machine in the boundary set that nothing can recover from because it was never a machine.
    """
    root = a_tree(tmp_path, real=A_REAL_TABLE, annotated=AN_ANNOTATED_TABLE)
    assert crash.declared_tables(root) == (
        ("brain.annotated", "ALLOWED"),
        ("brain.real", "ALLOWED"),
    )

    for reason, source in NEAR_MISSES.items():
        folder = tmp_path / reason.replace(" ", "_")
        near = a_tree(folder, miss=source)
        assert crash.declared_tables(near) == (), reason


# ---------------------------------------------------------------- a machine nobody ships
class Payment(enum.StrEnum):
    """The states of a machine that exists only in this file."""

    DRAFT = "draft"
    PLACED = "placed"
    DOUBTFUL = "doubtful"
    CLEARED = "cleared"


class Settlement(enum.StrEnum):
    """A second enum, so a plan's action can be shown to be a different vocabulary."""

    ISSUE = "issue"
    VERIFY = "verify"
    DONE = "done"


@dataclass(frozen=True)
class PaymentRecord:
    payment_id: str
    state: Payment = Payment.DRAFT


WHOLE_TABLE: Mapping[Payment, frozenset[Payment]] = MappingProxyType(
    {
        Payment.DRAFT: frozenset({Payment.PLACED}),
        Payment.PLACED: frozenset({Payment.CLEARED, Payment.DOUBTFUL}),
        Payment.DOUBTFUL: frozenset({Payment.CLEARED}),
        Payment.CLEARED: frozenset(),
    }
)

WHOLE_PLAN: Mapping[Payment, tuple[Payment, Settlement]] = MappingProxyType(
    {
        Payment.DRAFT: (Payment.DRAFT, Settlement.ISSUE),
        Payment.PLACED: (Payment.DOUBTFUL, Settlement.VERIFY),
        Payment.DOUBTFUL: (Payment.DOUBTFUL, Settlement.VERIFY),
        Payment.CLEARED: (Payment.CLEARED, Settlement.DONE),
    }
)

#: The source a fabricated module needs for the syntactic scan to find its table. What the
#: symbol is bound to at runtime is decided by `a_module`, which is the whole point: the two
#: scans are meant to be independent, so the tests that drive them supply each half separately.
A_TABLE_IN_SOURCE = "ALLOWED = MappingProxyType({Payment.DRAFT: frozenset()})"


def a_module(name: str, monkeypatch: pytest.MonkeyPatch, **contents: object) -> ModuleType:
    """A module object registered under `name`, which `importlib.import_module` hands back.

    Registered rather than written and imported, because what is being exercised is what
    `durable_machines` does with the *objects* a module binds, and a file on disk would have
    to be importable as well as parseable. `a_tree` is the source half and this is the runtime
    half; the two are paired by the module name.
    """
    module = ModuleType(name)
    for attribute, value in contents.items():
        setattr(module, attribute, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def test_a_table_that_is_only_one_on_paper_is_refused_rather_than_picked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disagreement between the two scans that cannot be reported, because it is fatal.

    A symbol the source reads as a transition table and that is a partial mapping at runtime
    is a machine with a default somewhere, which is a state graph where the state nobody
    thought about picks a behaviour by accident. Refused, because the alternative is a
    boundary set that depends on which scan the caller happened to ask.

    Delete this and the exhaustiveness requirement in `_keyed_by_one_enum` can be removed with
    the whole suite green, and a partial table becomes a machine.
    """
    root = a_tree(tmp_path, partial=A_TABLE_IN_SOURCE)
    a_module(
        "brain.partial",
        monkeypatch,
        Payment=Payment,
        ALLOWED=MappingProxyType({Payment.DRAFT: frozenset({Payment.PLACED})}),
    )
    with pytest.raises(CrashError, match="is not one at runtime"):
        durable_machines(root)


def test_a_recovery_plan_is_recognised_by_its_shape_and_by_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three ways to nearly be a recovery plan, none of which may be read as one.

    A mapping over the machine's states whose values are the wrong length, whose action is not
    an enum, or whose action is another *state* rather than a disposition, are all shapes a
    reader would call a plan and none of them says what a recovering worker does. The third is
    the interesting one: a mapping from state to (state, state) is a transition table written
    as pairs, and reading it as a plan would produce dispositions named after states.

    Delete this and the plan matcher can widen, which puts a machine on record as answering
    for its own boundaries when it answers nothing.
    """
    root = a_tree(tmp_path, nearly=A_TABLE_IN_SOURCE)
    a_module(
        "brain.nearly",
        monkeypatch,
        Payment=Payment,
        Settlement=Settlement,
        ALLOWED=WHOLE_TABLE,
        THREE_PARTS=MappingProxyType({one: (one, Settlement.DONE, "why") for one in Payment}),
        ACTION_IS_A_STRING=MappingProxyType({one: (one, "issue") for one in Payment}),
        ACTION_IS_A_STATE=MappingProxyType({one: (one, Payment.CLEARED) for one in Payment}),
        PaymentRecord=PaymentRecord,
    )
    machine = durable_machines(root)[0]
    assert machine.plan == {}
    assert not machine.declares_its_own_plan


def test_a_machine_reads_its_starting_state_off_the_record_it_belongs_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The create boundary, derived for a machine this repository does not have.

    The positive sibling of the near-miss tests above, and the one that shows the derivation
    working rather than refusing: a fabricated table, a fabricated record with a default, and
    the boundary set that falls out of them without a line here naming any of it.

    Delete this and every assertion about the start state rests on two tables that were
    written before it.
    """
    root = a_tree(tmp_path, whole=A_TABLE_IN_SOURCE)
    a_module(
        "brain.whole",
        monkeypatch,
        Payment=Payment,
        Settlement=Settlement,
        ALLOWED=WHOLE_TABLE,
        PLAN=WHOLE_PLAN,
        PaymentRecord=PaymentRecord,
    )
    machine = durable_machines(root)[0]
    assert machine.start == "DRAFT"
    assert machine.plan_from == "brain.whole.PLAN"
    assert [(one.crossing, one.before, one.after) for one in side_effect_boundaries([machine])][
        :2
    ] == [(Crossing.CREATE, "", "DRAFT"), (Crossing.RECORD, "DRAFT", "PLACED")]


def test_a_dataclass_instance_is_not_a_record_type_a_resume_could_read_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resume point is a type, and a module binds instances as well as classes.

    `resume_points` returns the class, because what a caller does with it is ask
    `brain.ops.jobs.reach_carrying_fields` about it. An instance carries the same
    `__dataclass_fields__` and no `__name__`, so admitting one turns the reach check into an
    attribute error inside whichever sweep asked.

    Delete this and the guard separating the two is unreachable, which reads exactly like a
    guard that is not needed.
    """
    root = a_tree(tmp_path, held=A_TABLE_IN_SOURCE)
    a_module(
        "brain.held",
        monkeypatch,
        Payment=Payment,
        ALLOWED=WHOLE_TABLE,
        AN_INSTANCE=PaymentRecord(payment_id="p_1"),
        PaymentRecord=PaymentRecord,
    )
    machine = durable_machines(root)[0]
    assert resume_points([machine]) == (PaymentRecord,)


def test_a_machine_that_imports_its_plan_says_where_it_imported_it_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Borrowing, driven end to end over two fabricated modules.

    `brain.ops.jobs` is the only borrower in this repository and it is correct, so the import
    walk had nothing to be wrong about. This is a second borrower, and it is what shows the
    walk reading `from ... import ...` rather than every node it passes.

    Delete this and `plan_from` can start answering from whichever node the walk reaches
    first, which for a borrower is a name that is not there.
    """
    root = a_tree(
        tmp_path,
        lender=A_TABLE_IN_SOURCE,
        borrower=f"from brain.lender import PLAN\n{A_TABLE_IN_SOURCE}",
    )
    a_module("brain.lender", monkeypatch, Payment=Payment, ALLOWED=WHOLE_TABLE, PLAN=WHOLE_PLAN)
    a_module("brain.borrower", monkeypatch, Payment=Payment, ALLOWED=WHOLE_TABLE)

    borrower, lender = durable_machines(root)
    assert (borrower.module, lender.module) == ("brain.borrower", "brain.lender")
    assert lender.declares_its_own_plan
    assert borrower.plan_from == "brain.lender.PLAN"
