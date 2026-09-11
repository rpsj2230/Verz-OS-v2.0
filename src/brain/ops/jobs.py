"""One job's life: the states it moves through, what stops it, and where it goes when it will
not run.

`brain.ops.queue` decides what a queue *is*: the connection it may use, the queue names that
exist, how many slots each traffic class gets, and what happens to a job whose worker died
underneath it. This file is the row rather than the queue, and it deliberately repeats none
of that. It holds the state machine one job moves through, the attempts it is allowed and
when the next one is due, what a cancellation and a timeout each leave behind, and what an
operator sees of the jobs that will never run at all.

**A job carries a principal and never a reach.** A queue row holding a serialised entitlement
set is a permission decision frozen at enqueue time and executed later, possibly after the
person has moved department or left. `brain.ops.checkpoints.ENTITLEMENT_IS_RESOLVED_AT_THE_ATTEMPT`
is that rule already written down for saved graph state, and this is the same rule for a job
row, so the sentence is imported rather than restated. It is made structural in two ways
rather than promised: `JobRecord` has no field whose type could hold one, which
`reach_carrying_fields` asks of the class rather than of a reviewer, and the one place a
reach could hide as text is refused, because a capability is short and
`brain.ops.queue.Job`'s length rule cannot see it. That second check belongs beside the
principal rather than in `Job`: a capability string in a job with nobody attached is merely
odd, and the same string in a job that names a principal is a stored answer to the question
the gate exists to ask.

**Scheduling is a timestamp, not a state.** A job due later is queued, with a time on it that
the fetch query filters against. A `SCHEDULED` member would be a second way to be ready, and
the fetch would have to know about both, so the day somebody adds a state and forgets the
query is the day a schedule silently stops firing. The driver's own model draws it the same
way, which is a reason to believe the cut rather than the reason for it.

**Attempts and re-drives are two counters, and this file holds one of them.** A retry is the
job asking for another go after failing; a re-drive is the machine dying underneath a job
that never reached a verdict. `brain.ops.queue.InFlight` counts the second and refuses to
carry the first, and `JobRecord` is the mirror of that: it counts attempts and has no field
for re-drives. `worst_case_runs` is the sum, which is the figure an operator actually needs
before deciding whether a side effect is survivable, and it is a sum rather than a product
because both counters are per job.

**A timeout is the system giving up and a cancellation is a person changing their mind, and
they leave different things behind.** A timeout spends an attempt and the job may be tried
again, because the deadline was ours and the intent has not changed. A cancellation spends
nothing and the job is never tried again, because trying again is doing the thing somebody
asked not to be done. The states differ too: a job cancelled before it started is `CANCELLED`
and nothing happened, and a job cancelled while running is `ABORTED` and what it had already
done is not knowable from here. That last sentence is `brain.ops.idempotency`'s subject, so
the state it leaves behind is **read out of `RESUME_PLAN` rather than named here**: this file
never writes `UNKNOWN`, it asks the table what a record found mid-flight becomes. A second
spelling of that answer would be a second place for the most expensive state in the system to
be got wrong.

**A cancellation is a request, not an undo.** A running job can be asked to stop and can
finish first, so `CANCELLING` has edges to `SUCCEEDED` and `FAILED` as well as to `ABORTED`.
Refusing to record a success that happened would leave the row lying about the world. What
must not exist is a path back: **no cancelled or aborted job reaches `RUNNING` in any number
of steps**, which is a property of the closure rather than of one row, for the reason
`brain.ops.idempotency.NO_PATH_FROM_UNKNOWN_TO_A_SECOND_ISSUE` gives about its own graph. The
edge somebody adds is never the direct one; it is a helpful requeue control on a dead letter,
and that puts a cancelled job two hops from running again.

**A dead letter is where jobs go to be forgotten, so the surface is entitlement-filtered,
dated, and carries no count of what it did not show.** An operator wants a number and a
number is the one thing this cannot give: "showing 3 of 47" tells the reader that 44 jobs
exist belonging to people they may not see, which is 44 facts about the estate they did not
have. So every count here is computed after filtering and there is no field anywhere that
could hold a total; `hidden_count_fields` asks that of the surface rather than leaving it to
review. The filtering itself is `brain.audit.view`'s, in the same two branches and the same
order, because a second implementation of who may read what is a second place for it to be
wrong and the permissive copy is the one that ships. The date is the other half:
`DEAD_LETTER_ACTIONABLE_DAYS` is `brain.ops.retention.PAYLOAD_RETENTION_DAYS`, because a job
carries references and a dead letter older than the things it refers to can be neither
diagnosed nor re-raised. Marking that is what stops the surface being a list nobody reads.

**Per-task concurrency cannot be expressed in the driver's model, and saying so is the
finding.** The driver takes one concurrency per worker process and a list of queues, so the
only allocation it can enforce is per queue, which `brain.ops.queue.worker_shards` already
does per traffic class. Expressing a per-task cap in it would need a queue per task, and
`queue_name_for` refuses exactly that: a task author choosing a queue is a task author
choosing a priority. So `TaskPool` is a cap whoever runs the pool has to enforce, and today
nobody does. What it protects is the failure a class-wide number cannot see, which is one
task inside a class occupying every slot in it while the class as a whole looks correctly
sized. It cannot break the memory arithmetic, because a per-task cap only ever reduces what
is in flight, so `concurrency_gaps` keeps that sum and it is not repeated here.

**This file has never persisted anything, and on 2026-09-11 the reason changed.** It used to
be that the queue driver `brain.ops.queue.DRIVER_IMPORT_NAME` names was not a dependency at
all, so `brain.ops.worker` exited 69 rather than looping on a queue it could not read.
M32.4.1.1 made it one, and a worker now drains a real queue against a real PostgreSQL. What is
still true, and is the only thing that was ever true of *this* module, is that nothing here has
been written, fetched or run: these are the rows a table of our own would hold, and there is no
such table. M17.1.2 names the same integration as M32.4.1.1 from the other end of the plan and
is not claimed here, because the part it would close is the part that is built. What is written
instead is the shape such a row
would take, with every part named against the driver's own concept in `DRIVER_MAPPING`, and
the parts that have no counterpart at all marked as ours: those are exactly the columns a
table of our own would need, which is the specification for a migration this file is not
allowed to write and which does not exist. Every row is `verified=False` and
`driver_mapping_gaps` refuses a row that claims otherwise while `driver_is_installed` is
False, so the honesty is a check rather than a habit. The driver's own names are read off its
documented model and nothing has run against it; there is no PostgreSQL on the machine this
was written on, so the parts that could only fail against a real database cannot have been
seen to work here.

Rejected: a second state machine for the side effect. `OperationState` already holds it, and
a job state meaning "we think it half happened" would be that machine's `UNKNOWN` with a
worse name and no read-back to leave it by.

Rejected: collapsing `CANCELLED` and `ABORTED` into one member. They differ on the only
question anybody asks after a cancellation, which is whether anything happened, and one
member answers it wrongly for whichever case it was not named for.

Rejected: deriving the dead letter from `attempts >= MAX_ATTEMPTS` wherever it is read. That
is a rule every reader has to evaluate identically, and the console and the recovery sweep
would disagree the day the cap moves. It is a state, written once.

Rejected: a requeue edge out of `DEAD_LETTER`. Re-raising a job somebody has looked at is a
new job with its own identifier, raised by whoever decided to, which is what
`brain.ops.idempotency` says about a `FAILED` operation in the same words and for the same
reason: an automatic path from "a person looked at this" back to "it is running" is the one
edge that makes the closure property above false.

Rejected: sizing the per-task pool with `brain.ops.limits.principal_share_of`. The property
is the same one, that a share is strictly below the whole above a ceiling of one, and the
fraction is not: a quarter is right for a connector shared by an unknown number of callers,
and a quarter of four slots is one, which serialises the only busy task in a class in order
to reserve three slots for tasks that may not exist.

Scope: domain logic. Nothing here opens a connection, reads a clock or stores a row; `now` is
a parameter everywhere it is needed, for the reason `brain.ops.limits` gives about a policy
module that owns a client. Where these rows live is a table this module does not name and
`src/brain/tables/` does not hold, which is the same sentence `brain.ops.idempotency` writes
about its own records and is true here for the stronger reason that the driver owns most of
the columns; `ours_alone` is the rest.

**Nothing in this repository calls anything in this module, and that is the defect
`brain.ops.worker` names as the most common one here: a correct, tested, documented mechanism
nobody runs.** Two call sites would have to exist. The state machine and the deadline belong
in the loop `brain.ops.worker.main` refuses to start, which is refused for want of a driver
rather than for want of this. The dead-letter surface belongs behind a
`brain.console.reads.ConsoleRead` naming a registered tool and `DEAD_LETTER_CAPABILITY`, on
the queue screen M27's operate section asks for and the console does not have. Saying so is
worth more than a wire that looks live.

Task ids: M17.1.1, M17.1.3, M17.1.4, M17.1.5
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final

from brain.core.entitlement import CAPABILITY_RE, Capability, EntitlementSet
from brain.gate.context import TrafficClass
from brain.ops.checkpoints import ENTITLEMENT_IS_RESOLVED_AT_THE_ATTEMPT
from brain.ops.idempotency import RESUME_PLAN, OperationState
from brain.ops.limits import BACKOFF_AFTER_REFUSALS, backoff_seconds
from brain.ops.queue import (
    CONCURRENCY,
    DRIVER_IMPORT_NAME,
    FALLBACK_POLL_SECONDS,
    HEARTBEAT_SECONDS,
    MAX_REDRIVES,
    MIB_PER_SLOT,
    Job,
    Redrive,
    driver_is_installed,
    stale_after,
)
from brain.ops.retention import PAYLOAD_RETENTION_DAYS
from brain.ops.wiring import component

# ------------------------------------------------------------------ written-down reasons
#: Why a job row names a principal and holds nothing about what that principal may reach.
A_JOB_CARRIES_A_PRINCIPAL_AND_NEVER_A_REACH: Final = (
    "A job runs later, and later is exactly when the answer to 'what may this person see' "
    "has had time to change. A row carrying a serialised entitlement set is a permission "
    "decision taken at enqueue time and applied after the person moved department or left, "
    "which is the one place a revocation does not take effect, because revocation here is "
    "the deletion of a grant and a copy in a queue table is not covered by it. So the row "
    "carries an identifier and the reach is resolved when the attempt runs. "
    + ENTITLEMENT_IS_RESOLVED_AT_THE_ATTEMPT
)

#: Why a job due later is a queued job with a time on it rather than a state of its own.
SCHEDULING_IS_A_TIMESTAMP_AND_NOT_A_STATE: Final = (
    "A SCHEDULED state is a second way for a job to be ready, so the fetch query has to know "
    "about both, and the day somebody adds a state without touching the query is the day a "
    "schedule stops firing with nothing to see: the row is present, the state reads as "
    "correct, and no worker asks for it. A timestamp has one reader and one comparison."
)

#: Why a cancellation and a timeout are not the same event with different words.
A_TIMEOUT_IS_THE_SYSTEM_GIVING_UP_AND_A_CANCELLATION_IS_A_PERSON: Final = (
    "A timeout means this system stopped waiting. The intent has not changed, the deadline "
    "was ours, and another attempt is the ordinary response. A cancellation means somebody "
    "decided the work should not happen, so another attempt is the system doing the thing "
    "they asked it not to do. Sharing one state makes the retry rule wrong for one of them, "
    "and the direction it is wrong in is the one that acts against a person's instruction."
)

#: Why the property is stated over the closure rather than over one row of the table.
NO_PATH_FROM_A_CANCELLED_JOB_BACK_TO_RUNNING: Final = (
    "It is not enough that CANCELLED has no edge to RUNNING. There must be no path of any "
    "length, because the edge somebody adds is never the direct one: it is a requeue control "
    "on the dead-letter screen, or an 'operators can revive a cancelled job' convenience, "
    "and either puts a cancelled job two hops from running. The table row would still read "
    "correctly on the day it was added, so the property is asserted over the closure."
)

#: Why a cancellation that arrives late is recorded as the success it interrupted.
A_CANCELLATION_IS_A_REQUEST_NOT_AN_UNDO: Final = (
    "Nothing can stop work that has already finished, so a cancellation asked for while a "
    "job was running can arrive after it succeeded. CANCELLING therefore has edges to "
    "SUCCEEDED and FAILED as well as to ABORTED. A machine that refused those would leave "
    "the row saying the work was stopped when the world had already changed, which is worse "
    "than telling the person who asked that they were too late."
)

#: Why the operator surface counts only what the reader may already see.
A_COUNT_OF_HIDDEN_JOBS_IS_A_COUNT_OF_HIDDEN_PEOPLE: Final = (
    "An operator wants a total and the total is the one thing this cannot give. 'Showing 3 "
    "of 47' says forty-four jobs exist belonging to principals the reader may not see, which "
    "is forty-four facts they did not have, and it says it by subtraction rather than "
    "directly, which is the spelling that survives review. Every figure here is computed "
    "after filtering, and there is no field on the surface that could hold a total: "
    "hidden_count_fields asks that of the shape rather than leaving it to whoever reads the "
    "diff. DENIED and ABSENT stay indistinguishable, here as everywhere."
)

#: What is not claimed about the driver, in the words the report has to use.
#:
#: Rewritten on 2026-09-11 when M32.4.1.1 made the driver a dependency. The sentence it
#: replaced opened "the queue driver is not a dependency of this project", which stopped being
#: true that day, and the only reader of this constant is a branch that runs when
#: `driver_is_installed()` is False. That is now a different situation from the one the old
#: words described: not a project that has not added the driver, but an environment that does
#: not have the one the project declares. A report that names the wrong cause sends whoever
#: reads it to the wrong place, and this one is printed exactly when somebody is looking.
THE_DRIVER_INTEGRATION_IS_UNBUILT: Final = (
    "No driver can be imported here, so nothing in this module has been written to a table, "
    "fetched from one, or run in this environment. The driver is a dependency of this "
    "project, so an environment without it is an image built wrongly rather than a feature "
    "nobody has added. Separately, and whatever the environment: what is written here is the "
    "shape a driver-backed row would take, named against the driver's own documented "
    "concepts, and the parts it has no counterpart for are marked as ours rather than glossed "
    "over. Those are the columns a table of our own would need, and there is no such table "
    "and no migration for one."
)


class JobsError(Exception):
    """A job was described in a shape the queue could not run or an operator could not read.

    Outside `brain.core.errors` for the reason `brain.ops.idempotency.IdempotencyError` gives
    about itself: nobody asking a question ever sees one of these. It is a mistake by
    whoever wired the call site up.
    """


class IllegalJobTransitionError(JobsError):
    """A move the job state machine has no edge for.

    A distinct type rather than a message, so a recovery sweep can catch a bad transition
    without also catching a malformed record, and so the moves that must never exist have
    something specific to fail with.
    """


# ----------------------------------------------------------- the state machine (M17.1.1)
class JobState(enum.StrEnum):
    """Where one job has got to. Eight values, and the two pairs are the point.

    `CANCELLED` and `ABORTED` are both a person's decision and they differ on whether
    anything happened: the first was never fetched, the second was stopped mid-flight and
    what it had already done is not knowable from here.

    `FAILED` and `DEAD_LETTER` are both an end without a success and they differ the way
    `OperationState.FAILED` and `OperationState.UNKNOWN` differ one level down. `FAILED` is a
    claim: this will not happen, and the reason is known and final, so there is nothing to
    look at. `DEAD_LETTER` is the absence of a claim: it stopped happening repeatedly and
    nobody knows why, which is what needs a person.
    """

    #: Written down, nothing has fetched it. A job due later is this with a time on it; see
    #: `SCHEDULING_IS_A_TIMESTAMP_AND_NOT_A_STATE`.
    QUEUED = "queued"
    #: A worker holds it and an attempt has been spent on it.
    RUNNING = "running"
    #: A person asked for it to stop and the worker has not acknowledged. See
    #: `A_CANCELLATION_IS_A_REQUEST_NOT_AN_UNDO`.
    CANCELLING = "cancelling"
    #: It ran and finished.
    SUCCEEDED = "succeeded"
    #: It will not happen, and something knows why.
    FAILED = "failed"
    #: A person stopped it before it started. Nothing happened.
    CANCELLED = "cancelled"
    #: A person stopped it while it was running. What it had already done is unknown.
    ABORTED = "aborted"
    #: It stopped happening and nobody knows why. Somebody has to look; see the dead-letter
    #: surface below.
    DEAD_LETTER = "dead_letter"


#: Every move the machine has an edge for. Exhaustive over `JobState`, and a test keeps it
#: that way: a member added with no entry is a state with no way out, and a job in it sits
#: for ever while every screen reports it as work in progress.
ALLOWED_TRANSITIONS: Mapping[JobState, frozenset[JobState]] = MappingProxyType(
    {
        # No edge to FAILED. A job that has not been fetched has not failed at anything, and
        # a refusal before it runs is a refusal to enqueue rather than a state on the row.
        JobState.QUEUED: frozenset({JobState.RUNNING, JobState.CANCELLED}),
        JobState.RUNNING: frozenset(
            {
                JobState.SUCCEEDED,
                JobState.FAILED,
                # A failed attempt with attempts left, scheduled for its next one.
                JobState.QUEUED,
                JobState.CANCELLING,
                JobState.DEAD_LETTER,
            }
        ),
        # Three ways out and none of them back to RUNNING. See
        # `A_CANCELLATION_IS_A_REQUEST_NOT_AN_UNDO` for why two of them are not ABORTED.
        JobState.CANCELLING: frozenset({JobState.ABORTED, JobState.SUCCEEDED, JobState.FAILED}),
        JobState.SUCCEEDED: frozenset(),
        JobState.FAILED: frozenset(),
        JobState.CANCELLED: frozenset(),
        JobState.ABORTED: frozenset(),
        JobState.DEAD_LETTER: frozenset(),
    }
)

#: States with nothing after them. Derived rather than listed, following
#: `brain.ops.idempotency.TERMINAL`, so a state cannot be declared terminal here and given an
#: outgoing edge above.
TERMINAL: Final[frozenset[JobState]] = frozenset(
    state for state, onward in ALLOWED_TRANSITIONS.items() if not onward
)

#: The only states a job with no attempt on it may be in. Derived from the table rather than
#: listed, so a new edge out of `QUEUED` cannot arrive with this guard silently wrong.
STATES_WITHOUT_AN_ATTEMPT: Final[frozenset[JobState]] = frozenset(
    {JobState.QUEUED, *(ALLOWED_TRANSITIONS[JobState.QUEUED] - {JobState.RUNNING})}
)


def reachable_from(state: JobState) -> frozenset[JobState]:
    """Every state this one can reach, in any number of steps.

    A closure over this table rather than a call to `brain.ops.idempotency.reachable_from`,
    which is bound to its own. The property being asserted is the same shape and is named
    after it: see `NO_PATH_FROM_A_CANCELLED_JOB_BACK_TO_RUNNING`.
    """
    seen: set[JobState] = set()
    frontier = list(ALLOWED_TRANSITIONS[state])
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(ALLOWED_TRANSITIONS[current])
    return frozenset(seen)


def advance(state: JobState, to: JobState) -> JobState:
    """Move a job, or refuse the move.

    Raises rather than returning the old state, for the reason `brain.ops.idempotency.advance`
    gives about itself: a refusal reported in a return value is a refusal a caller who wrote
    the call on a line of its own has ignored, and it reads as a check.

    `RUNNING` is refused here even though the table admits it from `QUEUED`, and that is the
    one asymmetry in this function. Entering `RUNNING` spends an attempt, and a move that
    could set the state without spending one is how a retry loop runs for ever while the
    attempt cap reads as untouched. `JobRecord.started` is the move that does both.
    """
    if to is JobState.RUNNING:
        msg = (
            "a job enters running by being started, which spends an attempt; advancing to it "
            "directly would let a job be retried without its attempt count moving, and the "
            "cap is the only thing standing between a failing job and a worker that does "
            "nothing else. Use JobRecord.started"
        )
        raise IllegalJobTransitionError(msg)
    onward = sorted(ALLOWED_TRANSITIONS[state])
    if to not in onward:
        allowed = ", ".join(onward) if onward else "nothing; it is terminal"
        msg = (
            f"a job cannot move from {state} to {to}; from {state} it may go to {allowed}. "
            f"{A_TIMEOUT_IS_THE_SYSTEM_GIVING_UP_AND_A_CANCELLATION_IS_A_PERSON}"
        )
        raise IllegalJobTransitionError(msg)
    return to


# ----------------------------------------------------------- attempts and scheduling
#: How many attempts one job gets before it is set aside for a person.
#:
#: Above `brain.ops.limits.BACKOFF_AFTER_REFUSALS`, and that relation is the whole of the
#: choice. The spacing between attempts is that module's curve: exact for the first few and
#: doubling after, because something refused that many times in a row is not going to succeed
#: on the next one at the same interval. A budget at or below the point where the doubling
#: starts means every attempt is the same distance apart and the backoff is decoration; a
#: much larger one means the last attempts are minutes apart while whoever asked is waiting.
MAX_ATTEMPTS: Final = 5

#: The delay before a first retry, which is the queue's own fallback poll interval.
#:
#: Not chosen beside it: a retry scheduled sooner than the interval the worker polls on is a
#: promise the queue cannot keep on the day notifications stop being delivered, which is the
#: day `brain.ops.queue` was written about and the day it raises nothing.
RETRY_BASE_SECONDS: Final[float] = float(FALLBACK_POLL_SECONDS)


def next_attempt_at(*, attempts: int, failed_at: datetime, jitter: float = 0.0) -> datetime:
    """When a job that has just failed its `attempts`-th go may be tried again.

    The curve is `brain.ops.limits.backoff_seconds` rather than one of this module's own.
    Two backoff curves in one system drift, and the drift is discovered by whichever of them
    somebody was not looking at. The price of the single curve is stated rather than hidden:
    it was written to space out a client that is not reading its retry hint, so tuning it for
    a client moves this too, and that coupling is the reason the base above is anchored to the
    queue rather than to anything in the limiter.

    Jitter is the caller's and only ever lengthens, exactly as it is there. Its job is to
    decorrelate jobs that all failed in the same second, which a value generated from anything
    stable would look like and not do.
    """
    if attempts < 0:
        msg = "attempts counts attempts and cannot be negative"
        raise JobsError(msg)
    if failed_at.tzinfo is None:
        msg = "a failure time with no timezone cannot be compared across two workers"
        raise JobsError(msg)
    delay = backoff_seconds(RETRY_BASE_SECONDS, consecutive_refusals=attempts, jitter=jitter)
    return failed_at + timedelta(seconds=delay)


def retry_gaps(
    max_attempts: int = MAX_ATTEMPTS, base_seconds: float = RETRY_BASE_SECONDS
) -> tuple[str, ...]:
    """Every reason this retry budget does not do what it reads as doing.

    Three, and two of them are silent. A budget below one is a queue that never retries
    anything while carrying the machinery for it. A budget at or below the point where
    `brain.ops.limits.backoff_seconds` starts doubling means every attempt is the same
    distance from the last, so the backoff is decoration and a failing dependency is asked
    the same question at a fixed interval until the attempts run out. And a base delay under
    the queue's fallback poll interval is a schedule the worker cannot honour on the day
    notifications stop being delivered, which is the day nothing raises anything.

    Both figures are parameters defaulting to the declared ones, for the reason
    `brain.ops.queue.concurrency_gaps` takes its allocation: a check that can only be run
    against the constants beside it cannot be shown to fail.
    """
    findings: list[str] = []
    if max_attempts < 1:
        findings.append(
            f"a job gets {max_attempts} attempt(s), so nothing is ever retried and every "
            "transient failure is final"
        )
    elif max_attempts <= BACKOFF_AFTER_REFUSALS:
        findings.append(
            f"a job gets {max_attempts} attempt(s) and the spacing starts doubling after "
            f"{BACKOFF_AFTER_REFUSALS}, so every attempt is {base_seconds}s after the last "
            "and the backoff never applies to a job at all"
        )
    if base_seconds < FALLBACK_POLL_SECONDS:
        findings.append(
            f"a retry is scheduled {base_seconds}s out and a worker with no notifications "
            f"polls every {FALLBACK_POLL_SECONDS}s, so the schedule is a time the queue "
            "cannot honour in the degraded mode it was written for"
        )
    return tuple(findings)


def worst_case_runs() -> int:
    """The most times one job's body can execute before anybody looks at it.

    A sum rather than a product, because both counters are per job: `MAX_ATTEMPTS` here and
    `brain.ops.queue.MAX_REDRIVES` there. The two must not share a counter, which that module
    argues at length, and they do have to be added when the question is the one an operator
    asks before deciding whether a side effect is survivable, which is how many times this
    thing can possibly have happened.
    """
    return MAX_ATTEMPTS + MAX_REDRIVES


# ----------------------------------------------------------- the row itself (M17.1.1)
#: Field types a job row may never carry, matched on the annotation rather than on a value.
#:
#: Names rather than the classes themselves, because `from __future__ import annotations`
#: leaves every annotation a string, and reading it as text is what makes the check work for
#: a field that has not been imported here at all: the point is to catch the addition, and
#: somebody adding a reach to a job row will import whatever they need to do it.
REACH_TYPE_NAMES: Final[frozenset[str]] = frozenset(
    {"EntitlementSet", "Capability", "Grant", "Scope"}
)


def reach_carrying_fields(record_type: type) -> tuple[str, ...]:
    """Fields on this dataclass whose type could hold a permission decision, in name order.

    Asked of the class rather than promised in a comment, so that
    `A_JOB_CARRIES_A_PRINCIPAL_AND_NEVER_A_REACH` is a check somebody has to defeat rather
    than a paragraph they can leave in place while adding the field underneath it.

    Reads `__dataclass_fields__` rather than calling `dataclasses.fields`, which is typed for
    a dataclass instance or type and would need a cast to be asked about an arbitrary class.
    A non-dataclass answers with nothing, which is the honest reply to "which of this class's
    dataclass fields carry a reach".
    """
    declared: Mapping[str, Any] = getattr(record_type, "__dataclass_fields__", {})
    return tuple(
        sorted(
            name
            for name, spec in declared.items()
            if any(banned in str(spec.type) for banned in REACH_TYPE_NAMES)
        )
    )


@dataclass(frozen=True)
class JobRecord:
    """One row: which job, for whom, where it has got to, and when it is next due.

    Frozen and moved by `started` and `advanced` rather than by assignment, so every change
    of state goes through `advance` and the transition table is not advisory.

    `job` is `brain.ops.queue.Job` rather than a second copy of a task name, a traffic class
    and an argument mapping. That type already refuses an argument long enough to be content
    and defaults its re-drive safety to unsafe, and restating any of it here would be a
    second set of rules for one row, with the looser copy winning wherever it was reached
    first.

    There is deliberately no `redrives` field. See the module docstring: a retry and a
    re-drive are counted separately, `brain.ops.queue.InFlight` holds the other one, and a
    single field for both dead-letters healthy jobs on the one host whose expected failure is
    an out-of-memory kill.
    """

    job_id: str
    job: Job
    #: Who the work is for, as an identifier. What they may reach is resolved when the
    #: attempt runs and is never stored; see `A_JOB_CARRIES_A_PRINCIPAL_AND_NEVER_A_REACH`.
    principal_id: str
    #: The earliest this may be fetched. A job due now carries the time it was enqueued.
    scheduled_at: datetime
    state: JobState = JobState.QUEUED
    #: Attempts that have started. Incremented by `started` and by nothing else.
    attempts: int = 0

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            msg = "a job row with no id cannot be completed, cancelled or reported"
            raise JobsError(msg)
        if not self.principal_id.strip():
            msg = (
                f"job {self.job_id!r} names no principal. The reach an attempt runs at is "
                "resolved from one, so a row without it can only run as nobody or as "
                "everybody, and the second is what a helpful default would pick"
            )
            raise JobsError(msg)
        if self.scheduled_at.tzinfo is None:
            # The same rule as every other timestamp in this package. Two workers on two
            # hosts produce an ordering that cannot be compared, and the comparison is the
            # whole of what this field is for.
            msg = f"job {self.job_id!r} is scheduled at a time with no timezone"
            raise JobsError(msg)
        if self.attempts < 0:
            msg = f"job {self.job_id!r} reports {self.attempts} attempts"
            raise JobsError(msg)
        if self.attempts == 0 and self.state not in STATES_WITHOUT_AN_ATTEMPT:
            msg = (
                f"job {self.job_id!r} is {self.state} with no attempt on it, which is a row "
                "saying it ran without anything having run it; the attempt count is what the "
                "cap is applied to, so a state reached without one is a job with no budget"
            )
            raise JobsError(msg)
        for key, value in self.job.args.items():
            if isinstance(value, str) and CAPABILITY_RE.match(value):
                msg = (
                    f"job {self.job_id!r} argument {key!r} is a capability. "
                    f"{A_JOB_CARRIES_A_PRINCIPAL_AND_NEVER_A_REACH} Pass the identifier of "
                    "the grant or the record instead"
                )
                raise JobsError(msg)

    def started(self) -> JobRecord:
        """Fetch this job and spend an attempt on it. The only way into `RUNNING`.

        One method for the two changes, because they are one event. A worker that could set
        the state without the counter would leave a job retrying for ever with a cap that
        reads as untouched, and the cap is the only thing between a failing job and a worker
        that processes nothing else.
        """
        onward = ALLOWED_TRANSITIONS[self.state]
        if JobState.RUNNING not in onward:
            allowed = ", ".join(sorted(onward)) if onward else "nothing; it is terminal"
            msg = (
                f"a job cannot be started from {self.state}; from {self.state} it may go to "
                f"{allowed}"
            )
            raise IllegalJobTransitionError(msg)
        return replace(self, state=JobState.RUNNING, attempts=self.attempts + 1)

    def advanced(self, to: JobState, *, scheduled_at: datetime | None = None) -> JobRecord:
        """Move this job, optionally putting its next attempt in the future.

        `scheduled_at` is here rather than on a separate method because the only move that
        needs it is the retry, and a retry that changed the state without moving the time
        would be fetched again immediately, which is the failure the backoff exists to
        prevent.
        """
        moved = advance(self.state, to)
        if scheduled_at is None:
            return replace(self, state=moved)
        if scheduled_at.tzinfo is None:
            msg = f"job {self.job_id!r} would be rescheduled to a time with no timezone"
            raise JobsError(msg)
        return replace(self, state=moved, scheduled_at=scheduled_at)

    @property
    def is_settled(self) -> bool:
        return self.state in TERMINAL

    def is_due(self, now: datetime) -> bool:
        """Whether a worker may fetch this now.

        Both halves, and the second is what makes scheduling a timestamp rather than a state:
        a queued job whose time has not come is not ready, and there is no separate state
        saying so for a fetch query to forget about.
        """
        return self.state is JobState.QUEUED and self.scheduled_at <= now


# --------------------------------------------------- what the driver would persist (M17.1.2)
@dataclass(frozen=True)
class DriverConcept:
    """One part of this model, and what the queue driver calls it.

    `theirs` may be empty and that is the useful case rather than an omission: it means the
    driver's model has no counterpart, so the part is ours to store, and the set of them is
    the specification for a table that does not exist.

    `verified` exists to be False. A mapping written from a package's documentation and never
    run against it is a set of plausible names, and the difference between that and a
    checked one is exactly what gets lost when somebody reads the file six months later.
    """

    ours: str
    theirs: str
    note: str
    #: Whether this correspondence has been observed against a running driver. Never True
    #: while the driver is absent; `driver_mapping_gaps` refuses the claim.
    verified: bool = False

    def __post_init__(self) -> None:
        for name in ("ours", "note"):
            if not str(getattr(self, name)).strip():
                msg = f"a driver concept with no {name} says nothing anybody can check"
                raise JobsError(msg)


def driver_table_name(driver: str = DRIVER_IMPORT_NAME) -> str:
    """What the driver calls its own job table.

    Built from the module name rather than written out, so the one file permitted to name an
    implementation stays the only one that does, and so a swap changes this with it. The
    parameter is what makes the derivation checkable: a check that could only be run against
    the constant beside it cannot be shown to fail, which is the argument
    `brain.ops.queue.concurrency_gaps` makes about its own signature.
    """
    return f"{driver}_jobs"


#: Every part of the model above, against the driver's own vocabulary.
#:
#: The status names are the driver's documented job statuses and the columns are its
#: documented job table. Nothing here has been run: see `THE_DRIVER_INTEGRATION_IS_UNBUILT`.
DRIVER_MAPPING: Final[tuple[DriverConcept, ...]] = (
    DriverConcept(
        ours=JobState.QUEUED.value,
        theirs="todo",
        note=(
            "written down and not yet fetched. The driver's fetch filters this status on the "
            "scheduled timestamp, which is why a job due later is this rather than a state "
            "of its own"
        ),
    ),
    DriverConcept(
        ours=JobState.RUNNING.value,
        theirs="doing",
        note="a worker holds it; the driver sets this when the job is fetched",
    ),
    DriverConcept(
        ours=JobState.CANCELLING.value,
        theirs="aborting",
        note=(
            "an abort has been requested on a job that is already running, and the running "
            "task is the only thing that can act on it. The driver draws the same line "
            "between asking and stopping"
        ),
    ),
    DriverConcept(ours=JobState.SUCCEEDED.value, theirs="succeeded", note="it ran and finished"),
    DriverConcept(
        ours=JobState.FAILED.value,
        theirs="failed",
        note="terminal there as here: the driver retries by re-queueing, not by this status",
    ),
    DriverConcept(
        ours=JobState.CANCELLED.value,
        theirs="cancelled",
        note="cancelled before anything fetched it, so nothing happened",
    ),
    DriverConcept(
        ours=JobState.ABORTED.value,
        theirs="aborted",
        note="stopped while running. What it had already done is not knowable from the row",
    ),
    DriverConcept(
        ours=JobState.DEAD_LETTER.value,
        theirs="",
        note=(
            "no counterpart. A job that exhausts its attempts is left in the driver's failed "
            "status and nothing sets it aside, so a dead letter is a column of ours or it is "
            "a screen nobody can build"
        ),
    ),
    DriverConcept(
        ours="attempts",
        theirs=f"the attempt counter on {driver_table_name()}",
        note="one counter for retries. The re-drive counter is ours; see brain.ops.queue",
    ),
    DriverConcept(
        ours="scheduled_at",
        theirs=f"the scheduled timestamp on {driver_table_name()}",
        note=SCHEDULING_IS_A_TIMESTAMP_AND_NOT_A_STATE,
    ),
    DriverConcept(
        ours="principal_id",
        theirs="the job's argument mapping",
        note=(
            "carried as a reference, which is where a reference belongs, but the driver's "
            "row has nothing that distinguishes it from any other argument. So the rule that "
            "a job names a principal has nowhere to be enforced in that table, and this "
            "module is where it is enforced instead"
        ),
    ),
    DriverConcept(
        ours="per-traffic-class concurrency",
        theirs="one concurrency per worker process over a list of queues",
        note=(
            "already translated by brain.ops.queue.worker_shards, which is why a per-class "
            "allocation is a process layout rather than a setting"
        ),
    ),
    DriverConcept(
        ours="per-task concurrency",
        theirs="",
        note=(
            "no counterpart. The driver allocates per queue, so expressing this would need a "
            "queue per task, and queue_name_for refuses that because a task choosing a queue "
            "is a task choosing a priority. TaskPool is a cap whoever runs the pool enforces"
        ),
    ),
    DriverConcept(
        ours="deadline",
        theirs="",
        note=(
            "no counterpart. The driver bounds how long a worker waits for a job, not how "
            "long a job may take, so a per-job deadline is ours to hold and ours to enforce "
            "inside the task"
        ),
    ),
    DriverConcept(
        ours="dead-letter reason",
        theirs="",
        note="no counterpart, and it is what the operator surface is a view over",
    ),
)


def driver_mapping_gaps(mapping: Sequence[DriverConcept] | None = None) -> tuple[str, ...]:
    """Every way this correspondence could be read as more settled than it is.

    Two checks, and each one is a way the record lies quietly.

    A `JobState` missing from the mapping is a state nobody decided how to persist, which
    presents as a job whose status cannot be written and is discovered by the first row that
    reaches it, in production, on the driver the mapping was supposed to describe.

    A row claiming verification while the driver cannot even be imported is the more
    dangerous one, because it is the sentence a reader trusts. `driver_is_installed` asks
    rather than assumes, so on the day the dependency lands this check stops firing on its
    own rather than needing somebody to remember it was there.

    The mapping is a parameter defaulting to the declared one, for the reason
    `brain.ops.queue.deploy_plan_gaps` takes one: a check that can only ever be run against
    the constant beside it cannot be shown to fail.
    """
    concepts = DRIVER_MAPPING if mapping is None else tuple(mapping)
    named = {concept.ours for concept in concepts}
    findings = [
        f"{state.value}: no driver concept is named for it, so nothing says how a job in "
        "this state is written down or read back"
        for state in JobState
        if state.value not in named
    ]
    if not driver_is_installed():
        findings.extend(
            f"{concept.ours!r} claims to be verified against the driver, which is not "
            f"installed in this environment. {THE_DRIVER_INTEGRATION_IS_UNBUILT}"
            for concept in concepts
            if concept.verified
        )
    return tuple(findings)


def ours_alone(mapping: Sequence[DriverConcept] | None = None) -> tuple[str, ...]:
    """The parts of this model the driver's table cannot hold, in declared order.

    Not a list of problems: it is the specification for the table this repository does not
    have. `brain.ops.queue.THE_QUEUE_SCHEMA_IS_NOT_ALEMBICS` explains why the driver's own
    tables are a deploy step rather than a migration, and this is the other half of that
    sentence, which is what would still have to be a migration of ours.
    """
    concepts = DRIVER_MAPPING if mapping is None else tuple(mapping)
    return tuple(concept.ours for concept in concepts if not concept.theirs.strip())


# ------------------------------------------------------------ the worker pool (M17.1.3)
@dataclass(frozen=True)
class TaskPool:
    """How many instances of one task may run at once inside one traffic class.

    Not a priority and not a queue. `brain.ops.queue.queue_name_for` derives the queue from
    the traffic class and the slot class and refuses anything hand-written, so a pool cannot
    be used to move work into a faster lane: the only thing a pool can do is run less of one
    task at a time.
    """

    task: str
    traffic_class: TrafficClass
    at_once: int

    def __post_init__(self) -> None:
        if not self.task.strip():
            msg = "a pool with no task name caps nothing and reads as though it caps something"
            raise JobsError(msg)
        if self.at_once < 1:
            # The same argument `brain.ops.queue.Shard` makes about a shard with no slots. A
            # pool of zero is a task that is enqueued and never run, which looks exactly like
            # a task nobody enqueued.
            msg = (
                f"pool for {self.task!r} allows {self.at_once} at once; a task capped at "
                "nothing is enqueued and never run, which is indistinguishable from a task "
                "nobody asked for"
            )
            raise JobsError(msg)


def pool_ceiling(
    traffic_class: TrafficClass, concurrency: Mapping[TrafficClass, int] | None = None
) -> int:
    """The most instances of one task a class may hold at once.

    The class's own allocation less one, so a class with several slots always keeps one for
    another task. The property that matters is the one
    `brain.ops.limits.principal_share_of` states about a connector: strictly below the whole,
    above a ceiling of one. A class allocated a single slot serialises every task in it, and
    that is a fact about the allocation rather than something a share can fix, which is the
    same edge that function records.

    The fraction is not shared and the module docstring says why: a quarter is right for a
    connector divided among an unknown number of callers, and a quarter of four slots is one.
    """
    slots = (CONCURRENCY if concurrency is None else concurrency).get(traffic_class, 0)
    if slots <= 0:
        return 0
    return max(1, slots - 1)


def pool_gaps(
    pools: Sequence[TaskPool],
    concurrency: Mapping[TrafficClass, int] | None = None,
    *,
    worker_component: str = "brain-worker",
) -> tuple[str, ...]:
    """Every reason this set of task pools will not run as written.

    Three findings, and the third is the only one that is about memory. The slot arithmetic
    for the whole container is `brain.ops.queue.concurrency_gaps` and is deliberately not
    repeated: a per-task cap can only ever reduce what is in flight, so it cannot break a sum
    that already holds. What it can do is exceed the container on its own when the allocation
    it is checked against is not the declared one, which is exactly the case a caller reaches
    by passing an allocation in, so the check earns its place rather than restating one.

    A class with no slots is reported first and unconditionally. `HUMAN_INTERACTIVE` is
    allocated zero deliberately, so a pool declared against it is a task that will be
    enqueued and never fetched, and that presents as a queue which fills and never drains.

    Returns all of them, matching every other gap function in this package: a deployment with
    two problems that is fixed one at a time is two restarts.
    """
    allocation = CONCURRENCY if concurrency is None else concurrency
    limit = component(worker_component).memory_mib
    findings: list[str] = []
    seen: set[tuple[str, TrafficClass]] = set()
    for pool in pools:
        key = (pool.task, pool.traffic_class)
        if key in seen:
            findings.append(
                f"{pool.task!r} is capped twice in {pool.traffic_class.value}; whichever is "
                "read second silently decides, and which one that is depends on the order "
                "somebody wrote them in"
            )
        seen.add(key)
        ceiling = pool_ceiling(pool.traffic_class, allocation)
        if ceiling == 0:
            findings.append(
                f"{pool.task!r} is capped in {pool.traffic_class.value}, which is allocated "
                "no slots, so its jobs are enqueued and never fetched"
            )
            continue
        if pool.at_once > ceiling:
            findings.append(
                f"{pool.task!r} may hold {pool.at_once} of {pool.traffic_class.value}'s "
                f"{allocation.get(pool.traffic_class, 0)} slot(s); at most {ceiling}, so one "
                "task cannot occupy the whole of a class that was split to keep one kind of "
                "work from starving another"
            )
        wanted = pool.at_once * MIB_PER_SLOT
        if wanted > limit:
            findings.append(
                f"{pool.task!r} at {pool.at_once} concurrent is {wanted} MiB at "
                f"{MIB_PER_SLOT} MiB a slot, over the {limit} MiB limit on "
                f"{worker_component!r}"
            )
    return tuple(findings)


# --------------------------------------------- cancellation and timeout (M17.1.4)
#: The longest a job may run before this system gives up on it. Derived, not chosen.
#:
#: Bounded above by the queue's own staleness window. A worker blocked inside a call writes
#: no heartbeat, and `brain.ops.queue.verdict_for` treats a job whose heartbeat is older than
#: `stale_after()` as orphaned, so a deadline at or past that figure is never the thing that
#: fires: the recovery sweep gets there first, a second copy of the job starts while the
#: first is still inside its deadline, and the log says "orphaned" for what was a slow job.
#: One heartbeat of margin, which is the smallest unit the queue measures staleness in.
#:
#: `brain.knowledge.embed_policy.EMBED_TIMEOUT_SECONDS` reaches the same figure from the
#: other end and for the same reason. Neither can compute the other: that one bounds a single
#: request and this bounds a whole job, so the day a job makes two requests the two numbers
#: stop agreeing and both are still right.
DEFAULT_TIMEOUT_SECONDS: Final[float] = stale_after().total_seconds() - HEARTBEAT_SECONDS


def timeout_gaps(seconds: float = DEFAULT_TIMEOUT_SECONDS) -> tuple[str, ...]:
    """Every reason a job deadline is one this system cannot honour.

    Three, and they fail differently. A deadline of nothing abandons every job before it
    starts, which is loud. A deadline past the staleness window is not a deadline at all,
    because the recovery sweep acts first and the symptom is a duplicated job rather than a
    message. A deadline shorter than one heartbeat abandons a job before it has ever reported
    itself alive, which makes a timeout and a crashed worker indistinguishable in the row,
    and those two get different treatment: one is retried, and the other is re-driven or
    quarantined depending on whether it is safe to repeat.

    A parameter with a default rather than a check over the constant beside it, for the
    reason `brain.ops.queue.driver_schema_gaps` gives about its own signature.
    """
    stale_seconds = stale_after().total_seconds()
    findings: list[str] = []
    if seconds <= 0:
        findings.append(
            f"a job is allowed {seconds}s, which abandons it before the worker has read it"
        )
        return tuple(findings)
    if seconds >= stale_seconds:
        findings.append(
            f"a job is allowed {seconds}s and the queue treats one as orphaned after "
            f"{stale_seconds}s; the recovery sweep would start a second copy while the first "
            "is still inside its deadline, so this deadline never fires and the incident "
            "reads as a crash rather than as a slow job"
        )
    if seconds < HEARTBEAT_SECONDS:
        findings.append(
            f"a job is allowed {seconds}s and a worker writes its heartbeat every "
            f"{HEARTBEAT_SECONDS}s, so a job can be abandoned before it has said it was "
            "running once; a timeout and a dead worker then look identical in the row and "
            "they are not treated the same way"
        )
    return tuple(findings)


class InterruptionKind(enum.StrEnum):
    """Why a job stopped without reaching a verdict of its own. Two, and no third.

    A "cancelled by the system" rung would be selected by whoever is writing the shutdown
    path, and it would inherit a cancellation's rule that the job is never tried again, which
    for a deployment restart is data loss with an audit trail.
    """

    #: This system stopped waiting. The intent has not changed.
    TIMEOUT = "timeout"
    #: A person decided the work should not happen.
    CANCELLATION = "cancellation"


@dataclass(frozen=True)
class Interruption:
    """What one interruption left behind: the row as it now stands, and what is known.

    Shaped after `brain.ops.idempotency.Resumption`, and carrying the reason for the same
    reason: an interruption that puts a job in front of a person has to say why this row is
    theirs, and a state name on its own does not.
    """

    record: JobRecord
    kind: InterruptionKind
    #: What is now known about any side effect this job had issued, or None when it cannot
    #: have issued one. Read from `brain.ops.idempotency.RESUME_PLAN`, never named here.
    operation_state: OperationState | None
    #: Whether this job will be attempted again. A cancellation is never retried.
    retriable: bool
    reason: str


def _side_effect_state(record: JobRecord) -> OperationState | None:
    """What a mid-flight stop leaves behind for this job's side effect, if it has one.

    The answer is `RESUME_PLAN`'s rather than this module's. A job stopped while running is a
    process that died between issuing something and recording that it did, which is the exact
    case that table is about, so the state is looked up from the entry for a record found in
    `SENT` rather than written out here. A second spelling of the most expensive state in the
    system is a second place for it to be got wrong, and the wrong one is the optimistic one.

    A job whose re-drive safety says it changes nothing the world can see has nothing to be
    unknown about, so the answer is None. That default is `brain.ops.queue.Redrive.UNSAFE`,
    which means a task author who has not thought about it gets the answer that cannot report
    a side effect as definitely absent.
    """
    if record.job.redrive is Redrive.SAFE:
        return None
    return RESUME_PLAN[OperationState.SENT][0]


def interrupt(
    record: JobRecord, kind: InterruptionKind, *, now: datetime, jitter: float = 0.0
) -> Interruption:
    """Stop a job, and say what that left behind.

    The two kinds diverge on both questions a person asks afterwards.

    A cancellation of a job that has not started is `CANCELLED` and nothing happened. A
    cancellation of a running job is `CANCELLING`, because stopping is the worker's to do and
    asking is all anybody else can do; the row reaches `ABORTED` when the worker acknowledges,
    and it may reach `SUCCEEDED` instead if it finished first. See
    `A_CANCELLATION_IS_A_REQUEST_NOT_AN_UNDO`.

    A timeout is refused for a job that has not started, and that refusal is deliberate rather
    than an omission. Nothing is running, so no deadline is being exceeded; what a queued job
    can outlive is a schedule, and this model has no expiry on one. Calling this for a queued
    job is a caller who has confused the two, and answering would let them record a timeout
    against work that never began.

    A timeout of a running job spends the attempt. Under the cap it goes back to `QUEUED` with
    its next attempt scheduled by `next_attempt_at`; at the cap it is dead-lettered, because a
    job that has been given every attempt and taken none of them is not a job anybody can fix
    by giving it another.
    """
    if record.state is JobState.QUEUED:
        if kind is InterruptionKind.TIMEOUT:
            msg = (
                f"job {record.job_id!r} is queued, so no deadline is running against it. "
                f"{A_TIMEOUT_IS_THE_SYSTEM_GIVING_UP_AND_A_CANCELLATION_IS_A_PERSON}"
            )
            raise JobsError(msg)
        return Interruption(
            record=record.advanced(JobState.CANCELLED),
            kind=kind,
            operation_state=None,
            retriable=False,
            reason=(
                "cancelled before anything fetched it, so nothing was issued and there is "
                "nothing to verify"
            ),
        )
    if record.state is not JobState.RUNNING:
        msg = (
            f"job {record.job_id!r} is {record.state} and cannot be interrupted; only a "
            "queued or a running job can be stopped, and a settled one has already stopped"
        )
        raise JobsError(msg)

    unknown = _side_effect_state(record)
    if kind is InterruptionKind.CANCELLATION:
        return Interruption(
            record=record.advanced(JobState.CANCELLING),
            kind=kind,
            operation_state=unknown,
            retriable=False,
            reason=(
                "a person asked for this to stop while it was running. Stopping is the "
                "worker's to do, so the row says the request is outstanding until it "
                "acknowledges, and trying again is not a recovery, it is the thing they "
                "asked not to happen"
            ),
        )
    if record.attempts >= MAX_ATTEMPTS:
        return Interruption(
            record=record.advanced(JobState.DEAD_LETTER),
            kind=kind,
            operation_state=unknown,
            retriable=False,
            reason=(
                f"it has had {record.attempts} attempt(s) of {MAX_ATTEMPTS} and reached a "
                "deadline on the last one. Another attempt is the same wait again, so it is "
                "set aside for somebody to look at"
            ),
        )
    return Interruption(
        record=record.advanced(
            JobState.QUEUED,
            scheduled_at=next_attempt_at(attempts=record.attempts, failed_at=now, jitter=jitter),
        ),
        kind=kind,
        operation_state=unknown,
        retriable=True,
        reason=(
            "this system stopped waiting. The intent has not changed and the deadline was "
            "ours, so it is queued again with its next attempt spaced out"
        ),
    )


# ------------------------------------------------ dead letters and the operator (M17.1.5)
class DeadLetterReason(enum.StrEnum):
    """Why a job was set aside. Three, and each one sends a person somewhere different.

    That is the test for a member here rather than tidiness of vocabulary: two reasons that
    lead to the same action are one reason with two names, and a reader triaging a screen
    learns to ignore the column.
    """

    #: It failed on its own terms every time it was tried. Look at the task.
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    #: The deadline was reached on every attempt. Look at what it waits on, or at the
    #: deadline; see `timeout_gaps` for what makes one unenforceable.
    TIMED_OUT_EVERY_ATTEMPT = "timed_out_every_attempt"
    #: It took its worker down with it repeatedly, which is `brain.ops.queue.Verdict`'s
    #: dead-letter verdict arriving here. Look at the host or at the size of the job, not at
    #: the task's own logic.
    RE_DRIVEN_TOO_OFTEN = "re_driven_too_often"


#: What a reader needs to see somebody else's dead letters.
#:
#: The tool's own capability, not the console's. `brain.console.reads.ConsoleRead` refuses a
#: plane capability in that position precisely so a screen cannot be admitted by the grant
#: that lets somebody open the console, and the plane check is that module's to make on top
#: of this one.
DEAD_LETTER_CAPABILITY: Final = Capability(value="read:job.dead_letter")

#: How long a dead letter can still be acted on, taken from the payload store's window rather
#: than chosen here. A job carries references, so a dead letter older than the things it
#: refers to can be neither diagnosed nor raised again: the arguments still read correctly and
#: resolve to nothing. `brain.ops.retention.PAYLOAD_RETENTION_DAYS` is itself the trace window
#: for the same nesting reason, which is that a copy outliving what it points at is a row that
#: looks complete and is not.
DEAD_LETTER_ACTIONABLE_DAYS: Final[int] = PAYLOAD_RETENTION_DAYS


@dataclass(frozen=True)
class DeadLetter:
    """One job nobody is going to run, as an operator sees it.

    Carries no argument mapping and no failure text. Those are the two fields that turn an
    operational row into a copy of somebody's data with a different retention on it, which is
    what `brain.ops.queue.Job` refuses at the other end; the identifiers are enough to fetch
    what is needed through the gate, at the reach whoever is asking holds now.
    """

    job_id: str
    task: str
    principal_id: str
    traffic_class: TrafficClass
    reason: DeadLetterReason
    attempts: int
    #: When it was set aside. Compared against `DEAD_LETTER_ACTIONABLE_DAYS`.
    at: datetime

    def __post_init__(self) -> None:
        if not self.job_id.strip() or not self.task.strip():
            msg = "a dead letter with no job id or no task names nothing anybody can act on"
            raise JobsError(msg)
        if not self.principal_id.strip():
            msg = (
                f"dead letter {self.job_id!r} names no principal, so nothing decides who may "
                "see it and the surface would show it to everybody who can open the screen"
            )
            raise JobsError(msg)
        if self.at.tzinfo is None:
            msg = f"dead letter {self.job_id!r} is dated with no timezone"
            raise JobsError(msg)

    def is_actionable(self, now: datetime) -> bool:
        """Whether the things this row refers to still exist.

        False is not a suggestion to hide the row. It is the surface admitting that the job's
        references have outlived the store behind them, which is the difference between a
        dead letter somebody can still investigate and one that is only a record that
        something failed.
        """
        return (now - self.at) <= timedelta(days=DEAD_LETTER_ACTIONABLE_DAYS)


def dead_letter_for(record: JobRecord, reason: DeadLetterReason, *, at: datetime) -> DeadLetter:
    """The operator's row for a job that has been set aside.

    Refuses a record that is not dead-lettered. A row built from a job that is still queued or
    still running is an item in somebody's work list for work that is still happening, and the
    action they take on it is taken against a running job.
    """
    if record.state is not JobState.DEAD_LETTER:
        msg = (
            f"job {record.job_id!r} is {record.state}, not {JobState.DEAD_LETTER}; a dead "
            "letter built from it would put a job that is still running in front of somebody "
            "as work that has stopped"
        )
        raise JobsError(msg)
    return DeadLetter(
        job_id=record.job_id,
        task=record.job.task,
        principal_id=record.principal_id,
        traffic_class=record.job.traffic_class,
        reason=reason,
        attempts=record.attempts,
        at=at,
    )


def _scope_row(entry: DeadLetter) -> dict[str, Any]:
    """The fields a dead-letter grant's scope may be written against.

    Four, all of them closed vocabularies or references, and none of them a business
    attribute. `brain.audit.view._scope_row` makes the same choice for the same reason: a
    grant scoped on something the row does not carry admits nothing, which fails closed, and a
    wider row would let a grant be written against a field this surface cannot evaluate.
    """
    return {
        "task": entry.task,
        "traffic_class": entry.traffic_class.value,
        "reason": entry.reason.value,
        "principal_id": entry.principal_id,
    }


def may_see(entry: DeadLetter, reader: EntitlementSet, now: datetime | None = None) -> bool:
    """Whether this reader is entitled to this dead letter. Two ways in, and no third.

    **It is their own job.** A person may see that the work they asked for is not going to
    happen. Refusing that would mean the only person who knows what the job was for is the
    one person who cannot be told it failed.

    **A grant covers dead letters, in a scope that matches the row.** `EntitlementSet` and
    `Scope` decide it, which is the same machinery every other narrowing in this system uses.
    There is deliberately no second rule here: a second implementation of who may read what is
    a second place for it to be wrong, and the permissive copy is the one that wins the day
    they disagree.
    """
    if entry.principal_id == reader.principal_id:
        return True
    scope = reader.scope_for(DEAD_LETTER_CAPABILITY, now)
    if scope is None:
        return False
    return scope.matches(_scope_row(entry))


def visible_dead_letters(
    entries: Sequence[DeadLetter], reader: EntitlementSet, now: datetime | None = None
) -> tuple[DeadLetter, ...]:
    """The dead letters this reader may see, in the order they were given.

    One pass, one predicate, and nothing recorded about what was skipped. The strong form of
    the rule is what the test asserts: this list is identical to the list produced from
    entries where the invisible ones were never written. That is the only version of
    "indistinguishable" worth having, because a placeholder, a gap in a numbering, or a count
    that differs by one all reconstruct exactly what was hidden. See
    `A_COUNT_OF_HIDDEN_JOBS_IS_A_COUNT_OF_HIDDEN_PEOPLE`.
    """
    return tuple(entry for entry in entries if may_see(entry, reader, now))


@dataclass(frozen=True)
class DeadLetterSummary:
    """What the dead-letter screen shows above the list.

    Every figure is computed from the rows the reader may see and from nothing else, so the
    summary of a queue holding other people's failures is identical to the summary of a queue
    that never held them.

    Every reason is a key, including the ones at zero, for the reason
    `brain.ops.queue.redrive_plan` names every verdict: a caller writing
    `by_reason.get(RE_DRIVEN_TOO_OFTEN, 0)` reads as though that reason were optional, and the
    most serious one is the one most likely to be missing on a quiet day.

    There is no field here for a total, a hidden count, or a number of rows removed;
    `hidden_count_fields` is the check that keeps it that way.
    """

    by_reason: Mapping[DeadLetterReason, int]
    #: Visible rows whose references have outlived the payload store. A count of things the
    #: reader is already looking at, which is the only kind of count this surface has.
    unactionable: int
    #: The oldest visible row, or None when there are none. What makes forgetting visible.
    oldest_at: datetime | None


def dead_letter_summary(
    entries: Sequence[DeadLetter], reader: EntitlementSet, now: datetime
) -> DeadLetterSummary:
    """The screen's figures, over the rows this reader may see.

    Filtering happens first and the arithmetic happens on what is left, which is the ordering
    that makes the rule structural rather than remembered: there is no point in this function
    at which a count of everything exists to be accidentally returned.
    """
    visible = visible_dead_letters(entries, reader, now)
    counts = dict.fromkeys(DeadLetterReason, 0)
    for entry in visible:
        counts[entry.reason] += 1
    return DeadLetterSummary(
        by_reason=MappingProxyType(counts),
        unactionable=sum(1 for entry in visible if not entry.is_actionable(now)),
        oldest_at=min((entry.at for entry in visible), default=None),
    )


#: The types an operator reads. Listed rather than discovered, following
#: `brain.ops.retention.POLICY_MODELS`: a type added to this surface and not to this tuple is
#: a type the check below never sees, and the whole value of the check is that it is asked of
#: everything a screen renders.
OPERATOR_SURFACE: Final[tuple[type, ...]] = (DeadLetter, DeadLetterSummary)

#: Field names that would be a count of what the reader was not shown. Names rather than a
#: rule about values, because the failure arrives as a field somebody adds to make a screen
#: more useful, and it arrives with one of these names on it.
NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT: Final[frozenset[str]] = frozenset(
    {
        "total",
        "total_count",
        "hidden",
        "hidden_count",
        "denied",
        "omitted",
        "suppressed",
        "filtered",
        "removed",
        "of_total",
    }
)


def hidden_count_fields(surface: Sequence[type] = OPERATOR_SURFACE) -> tuple[str, ...]:
    """Fields on the operator surface that would tell a reader what they were not shown.

    A check rather than a paragraph, for the reason `brain.ops.limits.VolumeAssessment` has no
    field meaning "stop them": a rule that lives only in prose is defeated by somebody adding
    one field, and the field will be added by somebody making a screen better rather than by
    somebody being careless. Reported as `Type.field` so the finding names the edit.
    """
    findings: list[str] = []
    for record_type in surface:
        declared: Mapping[str, Any] = getattr(record_type, "__dataclass_fields__", {})
        findings.extend(
            f"{record_type.__name__}.{name}"
            for name in declared
            if name in NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
        )
    return tuple(findings)
