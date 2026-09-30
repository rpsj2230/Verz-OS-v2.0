"""The install acceptance checks for the two recovery sweeps: a stopped worker's job is put back
only when its task is safe, and an interrupted side effect is read back or listed for a person
before anything retries it.

**Each check has two halves, and they prove different things.** The first reads the install's own
record of the worker's schedule: the last run of the sweep in `ops.control_run` finished, acted
rather than reported, looked at what it sweeps, and started recently enough that the schedule is
still running it. That is the half only the install can show, because it is the worker on that
server, over that server's queue and operation records, doing it on its own. The second hands the
sweep the product's own decision code with rows the check chose, so every verdict is exercised on
every run whatever the install happens to have stuck at the time, which on a healthy install is
nothing at all.

**The queue half is handed a stand-in queue, and says so.** The queue's tables are the driver's,
refused to the application role the check runs as, and a check that put real jobs back or set
them aside would be acting on the install's work rather than proving it. So the jobs are the
check's own, carrying the install's real task names and their real declarations, and the moves
are recorded rather than made. That the driver makes those moves on its own tables is proved in
CI against a real queue (`tests/unit/test_recovery_run.py`), and on the install by the schedule's
own record in the first half.

**The side-effect half uses the real table.** Three operations are recorded in `ops.operation`
inside the check's transaction, as a worker would have left them, under connector names only this
run uses: one whose stand-in read-back finds it, one whose read-back says it is absent, and one
whose connector declares no read-back at all. The sweep settles the first two on what they said,
leaves the third unknown, and the list a person reads is asked, through the route's own function,
for a reserved reader of the whole queue and for a reserved reader with no grant at all. Nothing
is issued: there is no issuing function anywhere in the sweep for the check to stop. Everything
is rolled back with the check.

**Only the check's own rows are swept.** `OnlyThese` narrows the store to the keys the check
wrote, so a real interrupted operation on the install is neither read back by a stand-in nor
listed in the check's comparison.

Task ids: M23.3.1
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import insert, select, update

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness
from brain.ops.idempotency import Intent, Operation, OperationState, operation_for
from brain.ops.queue import MAX_REDRIVES, InFlight
from brain.ops.recovery_run import (
    LOOKED_AT,
    NO_READ_BACK,
    StoredOperations,
    redrive_for,
    resume_side_effects,
    sweep_queue,
)

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 250

# ------------------------------------------------------------------ written-down reasons
#: Why a run older than a few minutes is still the schedule running the sweep.
A_TICK_RUNS_ITS_CONTROLS_ONE_AFTER_ANOTHER: Final = (
    "The worker's tick starts every owed control in registry order, one after another, and the "
    "acceptance run is registered last, so the sweep that ran in the same tick may have started "
    "minutes before the check, behind every slower control between them. A run within "
    "SCHEDULE_EVIDENCE_WINDOW is the schedule running it; one older is a schedule that stopped."
)

#: Said when the install has no run of the sweep to judge.
NO_SCHEDULED_RUN_YET: Final = (
    "the worker's schedule has recorded no run of this sweep on this install yet, so there is no "
    "scheduled run to judge; the next acceptance run after the worker's first tick judges it"
)

# ------------------------------------------------------------------------ the figures
#: How recent the sweep's last run must be. See `A_TICK_RUNS_ITS_CONTROLS_ONE_AFTER_ANOTHER`.
SCHEDULE_EVIDENCE_WINDOW: Final = timedelta(minutes=15)

#: Long enough ago that no live worker could still hold what the check records.
LEFT_BEHIND: Final = timedelta(minutes=10)


# ------------------------------------------------------------------------ the helpers
async def _schedule_ran(h: Harness, control: str) -> None:
    """The first half: the worker's schedule is running this sweep on this install, and acting."""
    from brain.tables.schedule import ControlRunRow

    async with h.sessions() as session:
        last = (
            await session.execute(
                select(ControlRunRow)
                .where(ControlRunRow.name == control)
                .order_by(ControlRunRow.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if last is None:
        raise CheckNotRunError(NO_SCHEDULED_RUN_YET)
    if last.outcome != "ok" or last.report_only:
        raise CheckFailedError("the schedule's last run of the sweep did not finish acting")
    if LOOKED_AT not in (last.detail or ""):
        raise CheckFailedError("the schedule's last run of the sweep had nothing to look with")
    if h.now - last.started_at > SCHEDULE_EVIDENCE_WINDOW:
        raise CheckFailedError("the schedule has not run the sweep recently, so nothing sweeps")


class _Queue:
    """A queue holding only the check's jobs, recording each move instead of making it."""

    def __init__(self, running: tuple[InFlight, ...], failed: tuple[InFlight, ...]) -> None:
        self._running = running
        self._failed = failed
        self.moves: list[tuple[str, str]] = []

    async def running(self) -> tuple[InFlight, ...]:
        return self._running

    async def failed(self) -> tuple[InFlight, ...]:
        return self._failed

    async def run_again(self, job_id: str, now: datetime) -> bool:
        self.moves.append(("run_again", job_id))
        return True

    async def set_aside(self, job_id: str) -> bool:
        self.moves.append(("set_aside", job_id))
        return True


class OnlyThese:
    """`StoredOperations` narrowed to the keys the check wrote."""

    def __init__(self, store: StoredOperations, keys: frozenset[str]) -> None:
        self.store = store
        self.keys = keys

    async def unsettled(self, before: datetime) -> tuple[Operation, ...]:
        return tuple(one for one in await self.store.unsettled(before) if one.key in self.keys)

    async def settle(self, key: str, *, frm: OperationState, to: OperationState) -> Operation:
        return await self.store.settle(key, frm=frm, to=to)


# ------------------------------------------------------------------- 1. the queue
@check(
    leaves=("M23.3.1",),
    sentence=(
        "The worker's schedule last ran the job redrive recently and it acted; and the sweep, "
        "handed jobs carrying the install's own task names, puts back an orphaned and a failed "
        "job of safe tasks, sets aside an orphaned control run and a job past the cap, and "
        "leaves a live job and a failed control run where they are."
    ),
)
async def a_stopped_worker_s_job_is_put_back_only_when_its_task_is_safe(h: Harness) -> None:
    from brain.knowledge.embed_queue import EMBED_TASK
    from brain.knowledge.ingest_queue import INGEST_TASK
    from brain.ops.worker import CONTROL_TASK

    await _schedule_ran(h, "queue_redrive")

    def job(job_id: str, task: str, *, left: timedelta, redrives: int = 0) -> InFlight:
        return InFlight(
            job_id=job_id,
            task=task,
            worker_id=f"acceptance-{h.run}",
            heartbeat_at=h.now - left,
            redrives=redrives,
            redrive=redrive_for(task),
        )

    stopped = LEFT_BEHIND
    queue = _Queue(
        running=(
            job("orphan-safe", EMBED_TASK, left=stopped),
            job("orphan-control", CONTROL_TASK, left=stopped),
            job("live", EMBED_TASK, left=timedelta(seconds=1)),
            job("capped", EMBED_TASK, left=stopped, redrives=MAX_REDRIVES),
        ),
        failed=(
            job("failed-safe", INGEST_TASK, left=stopped, redrives=1),
            job("failed-control", CONTROL_TASK, left=stopped),
        ),
    )
    await sweep_queue(queue, now=h.now)
    moved = {job_id: move for move, job_id in queue.moves}
    if moved.get("orphan-safe") != "run_again" or moved.get("failed-safe") != "run_again":
        raise CheckFailedError("a job of a task declared safe was not put back on its queue")
    if moved.get("orphan-control") != "set_aside" or moved.get("capped") != "set_aside":
        raise CheckFailedError("a job that may not run twice was not set aside for a person")
    if "live" in moved or "failed-control" in moved:
        raise CheckFailedError("the sweep moved a job it should have left where it was")


# -------------------------------------------------------------- 2. the side effects
@check(
    leaves=("M23.3.1",),
    sentence=(
        "The worker's schedule last ran the side-effect read-back recently and it acted; and of "
        "three actions a stopped worker left sent, the one its connector finds is settled "
        "succeeded, the one it says is absent failed, and the one no connector can answer for "
        "stays unknown and is listed for a reader of the whole queue and for nobody else."
    ),
)
async def an_interrupted_action_is_read_back_or_listed_before_any_retry(h: Harness) -> None:
    from brain.console.reads import Plane, plane_capability
    from brain.console.screens import screen
    from brain.core.scope import Scope
    from brain.operation_routes import interrupted_before, interrupted_for
    from brain.tables.operation import OperationRow

    await _schedule_ran(h, "side_effect_resume")

    asked = f"acceptance-{h.run}-asked"
    silent = f"acceptance-{h.run}-silent"
    issuer = h.principal(A, "issuer")

    def intent(n: int, connector: str) -> Operation:
        return operation_for(
            Intent(principal_id=issuer, intent_ref=f"acceptance-{h.run}-{n}"),
            connector=connector,
            tool=f"{connector}.effect",
        )

    found, absent, unanswerable = intent(1, asked), intent(2, asked), intent(3, silent)
    left_at = h.now - LEFT_BEHIND
    for one in (found, absent, unanswerable):
        await h.execute(
            insert(OperationRow).values(
                key=one.key,
                connector=one.connector,
                tool=one.tool,
                principal_id=one.principal_id,
                intent_ref=one.intent_ref,
                state=OperationState.PENDING.value,
            ),
            update(OperationRow)
            .where(OperationRow.key == one.key)
            .values(state=OperationState.SENT.value, updated_at=left_at),
        )

    def read_back(one: Operation) -> object:
        return "found" if one.key == found.key else "absent"

    store = StoredOperations(h.sessions)
    keys = frozenset({found.key, absent.key, unanswerable.key})
    await resume_side_effects(OnlyThese(store, keys), now=h.now, read_backs={asked: read_back})

    held = select(OperationRow.key, OperationRow.state).where(OperationRow.key.in_(keys))
    async with h.sessions() as session:
        states = {str(row.key): str(row.state) for row in (await session.execute(held)).all()}
    if states.get(found.key) != "succeeded" or states.get(absent.key) != "failed":
        raise CheckFailedError("an action its connector answered for was not settled on the answer")
    if states.get(unanswerable.key) != "unknown":
        raise CheckFailedError("an action no connector can answer for was settled without a person")

    reader, stranger = h.principal(A, "queue"), h.principal(A, "stranger")
    everywhere = Scope.unrestricted()
    await h.person(
        reader,
        department=A,
        grants=[
            (screen("queue").read.requires.value, everywhere),
            (plane_capability(Plane.CONFIGURATION).value, everywhere),
        ],
    )
    await h.person(stranger, department=A)
    waiting = tuple(
        one for one in await store.waiting(interrupted_before(h.now)) if one.operation.key in keys
    )
    shown = interrupted_for(waiting, await h.reach(reader), h.now)
    if [(one.key, one.standing) for one in shown] != [(unanswerable.key, NO_READ_BACK)]:
        raise CheckFailedError("the list did not show the waiting action to a reader of the queue")
    if interrupted_for(waiting, await h.reach(stranger), h.now):
        raise CheckFailedError("the list showed an interrupted action to a reader with no grant")
