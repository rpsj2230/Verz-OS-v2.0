"""The two recovery sweeps a worker's schedule runs: re-driving what a dead worker or a transient
failure left behind, and asking the connected system what an interrupted side effect did before
anybody retries it.

`brain.ops.crash` decides both and runs neither. `redrive` sorts every job the queue holds into
run it again, ask the source, or a person decides, and `verify_once` asks a source what happened
to one operation, refusing an answer nobody declared. Nothing called either, and the schedule's
two runners said so (`brain.ops.schedule_runner`, `queue_redrive` and `side_effect_resume`). This
module is the sweep around each decision: it reads the rows, calls the decision, and makes the one
move the decision allows. It decides nothing itself.

**A job is re-driven only when `redrive` says it may run again.** Two kinds of job reach it. A job
the queue believes is running whose worker has stopped heartbeating is orphaned: it is re-driven
when its task is declared re-drive safe and set aside as failed for a person otherwise, rather
than left in running where every queue figure counts it as work in progress. A job that failed
on its own, which for a task of ours is always a single attempt because no task is registered
with a retry of the driver's, is re-driven when its task is declared safe, and left failed
otherwise. Both are capped by `brain.ops.queue.MAX_REDRIVES`, counted from the queue's own record
of each time the job was put back, so a job that kills its worker or fails every time stops
after three. What a task declares is `REDRIVE_BY_TASK`, held to the job each task's builder makes
by a test. See `A_JOB_RUNS_TWICE_ONLY_WHEN_ITS_TASK_SAYS_IT_MAY`.

**What a person sees of the queue half is the run's own report.** The queue's tables are refused
to the application (`brain.jobs_routes` says so), so no screen lists a job row; the sweep's report
names every job it set aside by its id and task, and that report is what the Scheduled jobs
screen shows for `queue_redrive`. A job's arguments are never in it.

**An interrupted side effect is read back and never re-issued.** Every operation left in `SENT`,
`UNKNOWN` or `VERIFYING` for longer than a live worker could be holding it is moved by
`brain.ops.idempotency.resume`, which answers `VERIFY` for every one of those states and `ISSUE`
for none. Where the operation's connector declares a read-back in `READ_BACKS`, the record is
moved to `VERIFYING` and committed before the source is asked, then settled on what the source
said through `crash.verify_once`, which refuses an answer outside the vocabulary. Where it
declares none, the record stays `UNKNOWN` and is listed for a person by
`brain.operation_routes`. Nothing here holds the effect, so nothing here could issue it again;
retrying is a person's decision made after they have seen what the source said. See
`NOTHING_IS_RETRIED_BEFORE_A_PERSON_HAS_SEEN_WHAT_THE_SOURCE_SAID`.

**Each move is its own committed transaction.** A settle inside the sweep's own transaction would
be rolled back with it, and a read-back asked after a write-ahead that was rolled back is the crash
`brain.ops.idempotency.verify` moves to `VERIFYING` first to make visible. `StoredOperations` opens
a transaction per move, as `brain.ops.operation_store` does for the call itself.

Rejected: joining a job to its operation record. `crash.redrive` can, and nothing links the two
yet: no task of ours issues a side effect through `ops.operation`, so an absent record is the
truth about every job today, and the join is the place to add when one does. Rejected too: a
read-back for every connector in one release. A read-back is a question only the connector can
answer, in its own vendor's terms, and one written for a connector with nothing to ask would be a
guess settling a record. No shipped connector issues a side effect with a declared read-back yet,
so every interrupted operation goes to a person, which is the honest answer and the one
`brain.ops.idempotency.NO_READ_BACK_MEANS_READ_ONLY` already gives for issuing.

Task ids: M23.3.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol

from sqlalchemy import ColumnElement, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.knowledge.embed_queue import EMBED_TASK, REEMBED_TASK
from brain.knowledge.ingest_queue import INGEST_TASK
from brain.ops.crash import JobRecovery, Recovery, redrive, verify_once
from brain.ops.heartbeat import stale_after
from brain.ops.idempotency import (
    Disposition,
    IllegalTransitionError,
    Operation,
    OperationState,
    advance,
    resume,
)
from brain.ops.queue import InFlight, Redrive
from brain.tables.operation import OperationRow

# ------------------------------------------------------------------ written-down reasons
#: Why a job is run a second time only on its task's own word.
A_JOB_RUNS_TWICE_ONLY_WHEN_ITS_TASK_SAYS_IT_MAY: Final = (
    "A job whose worker died, or that failed on its own, is run again only when its task is "
    "declared re-drive safe, because running it twice changes nothing the first run had not "
    "already changed. Every other task, and any task nobody declared, is set aside as failed for "
    "a person, so a duplicate side effect is never the price of a crashed worker."
)

#: Why the read-back sweep never issues.
NOTHING_IS_RETRIED_BEFORE_A_PERSON_HAS_SEEN_WHAT_THE_SOURCE_SAID: Final = (
    "An interrupted side effect may have happened. The sweep asks the connected system and "
    "records its answer, or, where the connector can answer nothing, leaves the record unknown "
    "and lists it for a person. It never issues the effect again: retrying is a decision a "
    "person makes after seeing what the source said."
)

#: Why a report-only tick moves nothing.
A_RECOVERY_SWEEP_IN_REPORT_ONLY_MODE_MOVES_NOTHING: Final = (
    "Report-only mode exists for controls that remove data, and neither recovery sweep removes "
    "any, so brain.ops.schedule never asks for it. A sweep that moved jobs or settled records "
    "anyway when told to report would ignore the mode it was given."
)

#: What each task of ours declares about running twice, as its own job builder declares it.
#: Held to the builders by `tests/unit/test_recovery_run.py`, so the two cannot drift.
REDRIVE_BY_TASK: Final[Mapping[str, Redrive]] = {
    "brain.controls.run": Redrive.UNSAFE,
    EMBED_TASK: Redrive.SAFE,
    REEMBED_TASK: Redrive.SAFE,
    INGEST_TASK: Redrive.SAFE,
}

#: States a crash can leave an operation in that nobody has settled.
UNSETTLED: Final[tuple[OperationState, ...]] = (
    OperationState.SENT,
    OperationState.UNKNOWN,
    OperationState.VERIFYING,
)

#: How many set-aside jobs a report names before it says how many more there were.
NAMED_IN_A_REPORT: Final = 10

#: The words every sweep's report carries, which is how a reader of the run records tells a sweep
#: that looked from a runner that declined or found nothing to look with.
LOOKED_AT: Final = "looked at"


def redrive_for(task: str) -> Redrive:
    """What a task declares about running twice; unsafe for a task nobody declared."""
    return REDRIVE_BY_TASK.get(task, Redrive.UNSAFE)


# ------------------------------------------------------------------------ the queue half
class QueueRows(Protocol):
    """The queue's recoverable rows and the two moves the sweep may make on one.

    `brain.ops.queue.DriverQueue` over the driver; a test or an install check hands another. A
    move answers False when the row had already left the state the sweep read it in, which is
    a race the sweep loses gracefully rather than a failure.
    """

    async def running(self) -> tuple[InFlight, ...]:
        """Every job the queue believes is running, with its worker's newest heartbeat."""
        ...

    async def failed(self) -> tuple[InFlight, ...]:
        """Failed jobs of tasks declared re-drive safe that are still under the re-drive cap."""
        ...

    async def run_again(self, job_id: str, now: datetime) -> bool:
        """Put this job back on its queue to be fetched again."""
        ...

    async def set_aside(self, job_id: str) -> bool:
        """Mark this running job failed, and leave it for a person."""
        ...


@dataclass(frozen=True)
class QueueSweep:
    """What one queue sweep decided for each job it read, and what it did."""

    decided: tuple[JobRecovery, ...]
    ran_again: tuple[str, ...]
    set_aside: tuple[str, ...]
    #: Jobs that had moved on by themselves between the read and the move.
    moved_on: tuple[str, ...]
    #: The task each job id belongs to, for the report.
    tasks: Mapping[str, str]

    def summary(self) -> str:
        """One line for the run record: counts, and the set-aside jobs by id and task."""
        acted = len(self.ran_again) + len(self.set_aside) + len(self.moved_on)
        said = (
            f"{len(self.decided)} job(s) {LOOKED_AT}: {len(self.ran_again)} re-driven, "
            f"{len(self.set_aside)} set aside for a person, {len(self.decided) - acted} left "
            "as they were"
        )
        if self.moved_on:
            said += f", {len(self.moved_on)} had moved on by themselves"
        if self.set_aside:
            named = ", ".join(
                f"job {one} ({self.tasks.get(one, 'unknown task')})"
                for one in self.set_aside[:NAMED_IN_A_REPORT]
            )
            more = len(self.set_aside) - NAMED_IN_A_REPORT
            said += f". Set aside: {named}" + (f" and {more} more" if more > 0 else "")
        return said


async def sweep_queue(queue: QueueRows, *, now: datetime) -> QueueSweep:
    """Decide every recoverable job with `crash.redrive` and make the move it allows (M23.3.1).

    No operation record is joined; see the module docstring. A running job the decision does not
    run again or leave is set aside as failed. A failed job is only ever run again or left where
    it is, because failed is already where a job that needs a person rests.
    """
    running = await queue.running()
    failed = await queue.failed()
    tasks = {one.job_id: one.task for one in (*running, *failed)}
    ran_again: list[str] = []
    set_aside: list[str] = []
    moved_on: list[str] = []
    decided_running = redrive(running, {}, now)
    decided_failed = redrive(failed, {}, now)
    for one in decided_running:
        if one.may_run_again:
            moved = await queue.run_again(one.job_id, now)
            (ran_again if moved else moved_on).append(one.job_id)
        elif one.recovery is not Recovery.LEAVE_IT:
            moved = await queue.set_aside(one.job_id)
            (set_aside if moved else moved_on).append(one.job_id)
    for one in decided_failed:
        if one.may_run_again:
            moved = await queue.run_again(one.job_id, now)
            (ran_again if moved else moved_on).append(one.job_id)
    return QueueSweep(
        decided=(*decided_running, *decided_failed),
        ran_again=tuple(ran_again),
        set_aside=tuple(set_aside),
        moved_on=tuple(moved_on),
        tasks=tasks,
    )


# -------------------------------------------------------------------- the side-effect half
#: One connector's read-back: given the operation, what the source says it holds. Typed as
#: returning an object because `crash.verify_once` checks the answer rather than trusting it.
ReadBack = Callable[[Operation], object]

#: The read-backs this release ships, by connector. Empty: no connector issues a side effect
#: with a declared read-back yet, so every interrupted operation goes to a person.
READ_BACKS: Final[Mapping[str, ReadBack]] = {}


class OperationRecords(Protocol):
    """Where interrupted operations are found and settled, one committed move at a time."""

    async def unsettled(self, before: datetime) -> tuple[Operation, ...]:
        """Every operation in an unsettled state last moved before `before`."""
        ...

    async def settle(self, key: str, *, frm: OperationState, to: OperationState) -> Operation:
        """Move one record from `frm` to `to`, refusing if it is not in `frm`, and commit."""
        ...


#: The outcomes, as the list for a person shows them.
READ_BACK_FOUND: Final = "the connected system has it"
READ_BACK_ABSENT: Final = "the connected system does not have it"
READ_BACK_UNANSWERED: Final = "the connected system could not say"
NO_READ_BACK: Final = "this connector cannot be asked, so a person decides"
NOT_YET_SWEPT: Final = "not looked at yet: the sweep reads it once its worker has had time to"


@dataclass(frozen=True)
class Settled:
    """One interrupted operation: where it stands now and what the sweep learnt."""

    operation: Operation
    learnt: str


@dataclass(frozen=True)
class ResumeSweep:
    """Every interrupted operation the sweep looked at, and what each came to."""

    settled: tuple[Settled, ...]

    def summary(self) -> str:
        """One line for the run record, in counts."""
        waiting = sum(1 for one in self.settled if not one.operation.is_settled)
        return (
            f"{len(self.settled)} interrupted operation(s) {LOOKED_AT}: "
            f"{len(self.settled) - waiting} settled by asking the connected system, "
            f"{waiting} waiting for a person"
        )


def _grace(grace: timedelta | None) -> timedelta:
    """How long a record may sit unsettled before its worker is treated as gone."""
    return stale_after() if grace is None else grace


async def resume_side_effects(
    records: OperationRecords,
    *,
    now: datetime,
    read_backs: Mapping[str, ReadBack] = READ_BACKS,
    grace: timedelta | None = None,
) -> ResumeSweep:
    """Read back every interrupted side effect it can, and list the rest (M23.3.1).

    `grace` defaults to the heartbeat staleness the queue sweep uses, so the two sweeps agree
    about when a worker has stopped.
    """
    settled: list[Settled] = []
    for found in await records.unsettled(now - _grace(grace)):
        plan = resume(found)
        current = found
        if plan.operation.state is not found.state:
            current = await records.settle(found.key, frm=found.state, to=plan.operation.state)
        if plan.disposition is not Disposition.VERIFY:
            settled.append(Settled(operation=current, learnt=plan.reason))
            continue
        read_back = read_backs.get(current.connector)
        if read_back is None:
            settled.append(Settled(operation=current, learnt=NO_READ_BACK))
            continue
        if current.state is OperationState.UNKNOWN:
            current = await records.settle(
                current.key, frm=OperationState.UNKNOWN, to=OperationState.VERIFYING
            )
        try:
            answered = verify_once(current, read_back)
        except Exception:  # CrashError for an answer nobody declared; anything else unanswered
            # A read-back that raised has shown nothing about the source, which is what an
            # inconclusive answer means, so the record goes back to unknown to be asked again.
            current = await records.settle(
                current.key, frm=OperationState.VERIFYING, to=OperationState.UNKNOWN
            )
            settled.append(Settled(operation=current, learnt=READ_BACK_UNANSWERED))
            continue
        current = await records.settle(current.key, frm=OperationState.VERIFYING, to=answered.state)
        learnt = {
            OperationState.SUCCEEDED: READ_BACK_FOUND,
            OperationState.FAILED: READ_BACK_ABSENT,
        }.get(current.state, READ_BACK_UNANSWERED)
        settled.append(Settled(operation=current, learnt=learnt))
    return ResumeSweep(settled=tuple(settled))


def standing_of(operation: Operation, read_backs: Mapping[str, ReadBack] = READ_BACKS) -> str:
    """What a person is told about one unsettled operation, from its state and its connector.

    Only an `UNKNOWN` record has been through the sweep; `SENT` and `VERIFYING` are either
    younger than the grace or mid-sweep, and saying so is more honest than guessing.
    """
    if operation.state is not OperationState.UNKNOWN:
        return NOT_YET_SWEPT
    return READ_BACK_UNANSWERED if operation.connector in read_backs else NO_READ_BACK


def _operation(row: OperationRow) -> Operation:
    return Operation(
        key=row.key,
        connector=row.connector,
        tool=row.tool,
        principal_id=row.principal_id,
        intent_ref=row.intent_ref,
        state=OperationState(row.state),
    )


@dataclass(frozen=True)
class Waiting:
    """One unsettled operation as the list for a person reads it."""

    operation: Operation
    since: datetime


class StoredOperations:
    """`OperationRecords` over `ops.operation`, one committed transaction per call."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def _read(self, *where: ColumnElement[bool]) -> tuple[Waiting, ...]:
        statement = (
            select(OperationRow).where(*where).order_by(OperationRow.updated_at, OperationRow.key)
        )
        async with self.sessions() as session:
            rows = (await session.execute(statement)).scalars().all()
        return tuple(Waiting(operation=_operation(row), since=row.updated_at) for row in rows)

    async def unsettled(self, before: datetime) -> tuple[Operation, ...]:
        found = await self._read(
            OperationRow.state.in_([one.value for one in UNSETTLED]),
            OperationRow.updated_at < before,
        )
        return tuple(one.operation for one in found)

    async def waiting(self, before: datetime) -> tuple[Waiting, ...]:
        """What a person is shown: every `UNKNOWN` record, and the others once past `before`.

        `UNKNOWN` at any age, because it is the state a record rests in waiting for somebody:
        the sweep's own move to it stamps the record now, and a list held to the grace would hide
        each record for a minute after the sweep had finished with it.
        """
        return await self._read(
            or_(
                OperationRow.state == OperationState.UNKNOWN.value,
                and_(
                    OperationRow.state.in_([one.value for one in UNSETTLED]),
                    OperationRow.updated_at < before,
                ),
            )
        )

    async def settle(self, key: str, *, frm: OperationState, to: OperationState) -> Operation:
        advance(frm, to)
        async with self.sessions() as session, session.begin():
            moved = (
                await session.execute(
                    update(OperationRow)
                    .where(OperationRow.key == key, OperationRow.state == frm.value)
                    .values(state=to.value, updated_at=func.now())
                    .returning(OperationRow)
                )
            ).scalar_one_or_none()
            if moved is None:
                msg = f"operation {key} was not {frm} when the sweep went to move it to {to}"
                raise IllegalTransitionError(msg)
            return _operation(moved)


# ------------------------------------------------------------------ what the schedule calls
def run_queue_redrive_now(
    queue_url: str,
    *,
    now: datetime,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> QueueSweep:
    """`sweep_queue` over the driver, from a thread with no event loop of its own.

    One connection, as `brain.knowledge_intake_routes` opens one to count the queue: the sweep
    makes a handful of statements a minute and holds nothing between them.
    """
    from brain.ops.queue import DriverQueue, queue_app

    async def run() -> QueueSweep:
        app = queue_app(queue_url, pool_max=1)
        async with app.open_async():
            return await sweep_queue(DriverQueue(app, REDRIVE_BY_TASK), now=now)

    return asyncio.run(run(), loop_factory=loop_factory)


def run_side_effect_resume_now(
    database_url: str,
    *,
    now: datetime,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> ResumeSweep:
    """`resume_side_effects` over `ops.operation`, from a thread with no event loop of its own."""
    from brain.session import make_app_engine, make_session_factory

    async def run() -> ResumeSweep:
        engine = make_app_engine(database_url)
        try:
            return await resume_side_effects(
                StoredOperations(make_session_factory(engine)), now=now
            )
        finally:
            await engine.dispose()

    return asyncio.run(run(), loop_factory=loop_factory)
