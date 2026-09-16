"""The Scheduled jobs screen over HTTP: every job the worker ticks, how it last went, and the three
controls that can be real.

Live runs (`brain.operate_routes`) answers what is running this minute and what is owed. What it
cannot answer is the question an administrator arrives with when something has stopped working:
how did this job last go, when did it last succeed, and can I stop it or make it go now. This is
that screen, beside Live runs under Operate, and it does not change what Live runs answers.

**What is listed is the controls the worker's schedule starts.** `brain.ops.schedule.schedulable`
is the list, in registry order, and a job whose runner cannot start yet is listed with the
runner's own sentence about what it needs rather than left out, because a guarantee nothing runs
is the one worth seeing. Who may see a job is `brain.console.operate.may_watch_unattended` under
the queue screen's grant, which is the decision Live runs already uses for what is owed; there is
no second one here. A reader without that grant is answered an empty list, which is what an
install with no schedule is answered, and nothing on the response says a narrowing happened.

**A failed run is shown as the kind of failure and never as its message.** The worker writes a
failure as the exception's type and message, and a message can carry a value: a database refusal
names the key it collided on, a validation error quotes its input. The type name is the class, a
product identifier, so that is what is served; the message stays in the run record for whoever
reads the database. A report from a run that finished is the runner's own sentence, written for
this column as "a sentence for a person, never a payload", and is served. See
`AN_EXCEPTION_MESSAGE_IS_A_VALUE_UNTIL_SHOWN_OTHERWISE`.

**Three controls, and why a fourth is absent.** Pause, resume and run now are rows the worker's
tick reads (`brain.ops.schedule_control`). Stopping a run in progress is not offered, for
`brain.operate_routes.NO_RUN_CAN_BE_STOPPED_FROM_HERE`, and the answer carries that as a field.

**Every control needs `admin:schedule` over everything and the job's own read.** The authority is
asked through `brain.console.govern._in_reach` at `NOWHERE`, because the schedule is the whole
install's. The read is the same `may_watch_unattended` the list is built from, so a job this
caller could not have been shown cannot be paused by a caller who guessed its name, which is
`brain.session_routes.end_session`'s rule about a session. Both are asked before the database, so
a caller without them is refused identically whether or not this process has a pool.

**Pausing and running now are behind the `schedule_control` feature, and resuming is not.** See
`brain.ops.features.A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED`. A caller holding the
authority is told by name that the feature is off and where it is switched on.

**Recorded on the row, and in the ledger.** A pause and a request keep who and when on their
`ops.setting` row, which the next press overwrites, and `0059`'s trigger on that table appends a
`setting` entry for every press that moves the row, in the same transaction. The route sets who, at
what reach and for which request first, so the entry carries the request's trace; the answer says
every change is in the audit trail.

**Claimed: M27.8.13, and what the claim does not include is written here rather than rounded
away.** The background work this product starts is the scheduled controls, and a control run
somebody enqueues from the worker's shell runs through the same `start_owed` and lands in the same
run record, so every run is seen here and on Live runs once it has started. What is not seen is a
queued run that no worker has fetched, because the queue's tables are refused to the application,
and what is not controlled is a run already in progress, because nothing can stop one. Run now
here replaces the shell's enqueue for every purpose the shell had.

Task ids: M27.8.13
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.console.govern import NOWHERE, _in_reach
from brain.console.operate import QUEUE_SCREEN, may_watch_unattended
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.ops.controls import Control
from brain.ops.features import SCHEDULE_CONTROL, is_on
from brain.ops.jobs import JobState
from brain.ops.retention_store import released_controls
from brain.ops.schedule import DESTRUCTIVE, Owed, report_only_now, schedulable
from brain.ops.schedule_control import (
    ScheduleControlError,
    control_refusal,
    pause_states,
    paused_controls,
    paused_in,
    request_run,
    request_states,
    requested_at,
    run_requests,
    set_paused,
)
from brain.ops.schedule_runner import due_now
from brain.ops.schedule_store import last_successes
from brain.ops.setting_store import SettingState
from brain.routing_routes import sessions_of
from brain.tables.audit import attributed_to
from brain.tables.schedule import ControlRunRow

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a failed run is shown by its type.
AN_EXCEPTION_MESSAGE_IS_A_VALUE_UNTIL_SHOWN_OTHERWISE: Final = (
    "The worker records a failed run as the exception's type and its message. The type is a "
    "class name the product defines or imports; the message is whatever the raiser put in it, "
    "and a database refusal quotes the key it collided on while a validation error quotes its "
    "input. Nothing redacts that text on its way into the run record, so the console serves "
    "the type and says the message is kept on the server."
)

# ------------------------------------------------------------------------ the figures
#: Pauses, resumes and runs a scheduled job. Held over everything or not at all.
SCHEDULE_AUTHORITY: Final = Capability(value="admin:schedule")

#: The screen's word in a refusal, identical on every install.
JOBS_SCREEN: Final = "jobs"

#: What a failure's recorded type may look like: a dotted Python identifier and nothing else.
_TYPE_NAME: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,119}$")


def may_control(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach holds the schedule's authority over everything."""
    return _in_reach(reach, SCHEDULE_AUTHORITY, NOWHERE, now)


def may_see_job(name: str, reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may be shown this job: Live runs' own decision for what is owed."""
    return may_watch_unattended(name, JobState.QUEUED, reach, now, screen_key=QUEUE_SCREEN)


def failure_kind(detail: str | None) -> str | None:
    """The exception type a failed run recorded, or None when the detail does not start with one.

    The worker writes `f"{type(exc).__name__}: {exc}"`, so the type is everything before the
    first colon when that is an identifier. Anything else is withheld whole rather than guessed
    at. See `AN_EXCEPTION_MESSAGE_IS_A_VALUE_UNTIL_SHOWN_OTHERWISE`.
    """
    if not detail:
        return None
    head, colon, _ = detail.partition(":")
    return head if colon and _TYPE_NAME.fullmatch(head) else None


# ------------------------------------------------------------------------ the shapes
class JobView(BaseModel):
    """One scheduled job, how it last went, and what a person has done to it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    control: str
    #: The registry's `guards` sentence. Product text.
    keeps_true: str
    every_seconds: float
    #: A destructive job that nobody has released runs in report-only mode.
    destructive: bool
    report_only: bool
    #: False when the runner cannot start yet, and `needs` says what it needs.
    runnable: bool
    needs: str | None
    last_started_at: datetime | None
    last_finished_at: datetime | None
    #: `ok`, `failed` or `refused`, or null for a run with no finish and for a job never run.
    last_outcome: str | None
    #: The runner's sentence for a run that finished ok or refused.
    last_report: str | None
    #: The exception type of a failed run. Never its message.
    last_failure_kind: str | None
    last_succeeded_at: datetime | None
    owed: bool
    late_by_seconds: float | None
    paused: bool
    #: Who last paused or resumed it, and when.
    pause_changed_by: str | None
    pause_changed_at: datetime | None
    #: When a person last asked for a run, and whether no run has started since.
    run_requested_at: datetime | None
    run_requested_by: str | None
    run_pending: bool


class JobsPage(BaseModel):
    """Every scheduled job this reader may see. No count: the list is narrowed per reader."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: datetime
    jobs: list[JobView]
    #: Whether `schedule_control` is switched on. Presentation: every control asks again.
    controls_switched_on: bool
    #: Whether this caller holds the authority. Presentation: every control asks again.
    may_control: bool
    #: A run in progress cannot be stopped. See `NO_RUN_CAN_BE_STOPPED_FROM_HERE` in
    #: `brain.operate_routes`.
    no_run_can_be_stopped: bool = True
    #: A pause or a request shows its last change on its row, and every change is an entry in the
    #: audit trail, from `0059`'s trigger.
    every_change_is_in_the_audit_trail: bool = True


class JobChanged(BaseModel):
    """What one control changed, as the database now holds it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    control: str
    paused: bool
    run_requested_at: datetime | None
    changed_by: str
    changed_at: datetime


# ---------------------------------------------------------------- the statements
#: One run record as the screen reads it: name, start, finish, outcome and detail.
LastRun = tuple[str, datetime, datetime | None, str | None, str | None]


def last_run_of_each_control() -> Select[LastRun]:
    """Each control's newest run with how it ended. `DISTINCT ON`, one row per control."""
    return (
        select(
            ControlRunRow.name,
            ControlRunRow.started_at,
            ControlRunRow.finished_at,
            ControlRunRow.outcome,
            ControlRunRow.detail,
        )
        .order_by(ControlRunRow.name, ControlRunRow.started_at.desc())
        .distinct(ControlRunRow.name)
    )


# ---------------------------------------------------------------- the projection
def job_view(
    control: Control,
    *,
    last: LastRun | None,
    succeeded: datetime | None,
    owed: Owed | None,
    pause: SettingState | None,
    request: SettingState | None,
    released: frozenset[str],
) -> JobView:
    """One job, from the rows already read. Decides nothing about who may see it."""
    refusal = control_refusal(control.name)
    paused = pause is not None and control.name in paused_in({control.name: pause})
    requested = requested_at(request) if request is not None else None
    started = last[1] if last is not None else None
    outcome = last[3] if last is not None else None
    detail = last[4] if last is not None else None
    return JobView(
        control=control.name,
        keeps_true=control.guards,
        every_seconds=control.every.total_seconds(),
        destructive=control.name in DESTRUCTIVE,
        report_only=control.name in report_only_now(released),
        runnable=not refusal,
        needs=refusal or None,
        last_started_at=started,
        last_finished_at=last[2] if last is not None else None,
        last_outcome=outcome,
        last_report=detail if outcome in {"ok", "refused"} else None,
        last_failure_kind=failure_kind(detail) if outcome == "failed" else None,
        last_succeeded_at=succeeded,
        owed=owed is not None,
        late_by_seconds=owed.late_by.total_seconds() if owed is not None else None,
        paused=paused,
        pause_changed_by=pause.updated_by if pause is not None else None,
        pause_changed_at=pause.updated_at if pause is not None else None,
        run_requested_at=requested,
        run_requested_by=request.updated_by if request is not None and requested else None,
        run_pending=requested is not None and (started is None or started < requested),
    )


def jobs_for(
    reach: EntitlementSet,
    now: datetime,
    *,
    runs: Sequence[LastRun],
    successes: Mapping[str, datetime],
    pauses: Mapping[str, SettingState],
    requests: Mapping[str, SettingState],
    released: frozenset[str],
) -> list[JobView]:
    """Every schedulable job this reach may see, in registry order.

    Filtered by `may_see_job` before a view exists, so there is no point here at which a job the
    reader may not see has been built to be dropped.
    """
    last = {row[0]: row for row in runs}
    attempts = {row[0]: row[1] for row in runs}
    owed = {
        one.name: one
        for one in due_now(
            now=now, last_attempt=attempts, last_success=successes, released=sorted(released)
        )
    }
    return [
        job_view(
            one,
            last=last.get(one.name),
            succeeded=successes.get(one.name),
            owed=owed.get(one.name),
            pause=pauses.get(one.name),
            request=requests.get(one.name),
            released=released,
        )
        for one in schedulable()
        if may_see_job(one.name, reach, now)
    ]


# ------------------------------------------------------------------------ the wiring
def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _not_controllable() -> Absent:
    """The one refusal a caller without the authority, or without the job's read, gets."""
    return Absent(f"that {JOBS_SCREEN} change is not writable by this caller")


def _refused_because(reason: str) -> Absent:
    """A refusal for a caller holding the authority, naming what to fix."""
    message = f"that job was not changed: {reason}"
    return Absent(message, public_message=message)


#: What a caller holding the authority is told when the feature is off.
SWITCHED_OFF: Final = (
    "pausing and running jobs from the console is switched off on this install, and an "
    "administrator switches it on under Install, Features"
)


def _authorised(name: str, asked: Asking) -> None:
    if not may_control(asked.reach, asked.now) or not may_see_job(name, asked.reach, asked.now):
        log.info("job control refused", principal=asked.caller.principal.id)
        raise _not_controllable()


async def _attribute(session: AsyncSession, asked: Asking) -> None:
    """Who is pressing, at what reach, for which request, for the entry `0059`'s trigger appends."""
    trace_id = str(structlog.contextvars.get_contextvars().get("trace_id", ""))
    for statement in attributed_to(
        actor_id=asked.caller.principal.id, ent_hash=asked.reach.ent_hash(), trace_id=trace_id
    ):
        await session.execute(statement)


async def _now_holds(session: AsyncSession, name: str) -> tuple[bool, datetime | None]:
    """Whether the job is paused and when a run was last asked for, read back after the write."""
    return name in await paused_controls(session), (await run_requests(session)).get(name)


router = APIRouter(prefix=API_PREFIX, tags=["operate"])


@router.get("/jobs", response_model=JobsPage, responses=COMMON_RESPONSES)
async def jobs(request: Request, asked: Asked) -> JobsPage:
    """Every scheduled job this reader may see, how it last went, and what was done to it.

    Read for everybody and narrowed per job, which is `brain.operate_routes.live_runs`' order and
    its argument.
    """
    factory = _require_sessions(request)
    async with factory() as session:
        runs = [row._tuple() for row in (await session.execute(last_run_of_each_control())).all()]
        successes = await last_successes(session)
        released = await released_controls(session, now=asked.now)
        pauses = await pause_states(session)
        requests = await request_states(session)
        switched_on = await is_on(session, SCHEDULE_CONTROL)
    return JobsPage(
        as_of=asked.now,
        jobs=jobs_for(
            asked.reach,
            asked.now,
            runs=runs,
            successes=successes,
            pauses=pauses,
            requests=requests,
            released=released,
        ),
        controls_switched_on=switched_on,
        may_control=may_control(asked.reach, asked.now),
    )


@router.post("/jobs/{name}/pause", response_model=JobChanged, responses=COMMON_RESPONSES)
async def pause_job(request: Request, name: str, asked: Asked) -> JobChanged:
    """Pause one job: the worker's schedule stops starting it from its next tick."""
    _authorised(name, asked)
    async with _require_sessions(request)() as session:
        if not await is_on(session, SCHEDULE_CONTROL):
            await session.rollback()
            raise _refused_because(SWITCHED_OFF)
        try:
            await _attribute(session, asked)
            await set_paused(session, name, paused=True, by=asked.caller.principal.id)
        except ScheduleControlError as refused:
            await session.rollback()
            raise _refused_because(str(refused)) from None
        paused, requested = await _now_holds(session, name)
        await session.commit()
    return JobChanged(
        control=name,
        paused=paused,
        run_requested_at=requested,
        changed_by=asked.caller.principal.id,
        changed_at=asked.now,
    )


@router.post("/jobs/{name}/resume", response_model=JobChanged, responses=COMMON_RESPONSES)
async def resume_job(request: Request, name: str, asked: Asked) -> JobChanged:
    """Resume one job. Not behind the feature switch; see the module docstring."""
    _authorised(name, asked)
    async with _require_sessions(request)() as session:
        try:
            await _attribute(session, asked)
            await set_paused(session, name, paused=False, by=asked.caller.principal.id)
        except ScheduleControlError as refused:
            await session.rollback()
            raise _refused_because(str(refused)) from None
        paused, requested = await _now_holds(session, name)
        await session.commit()
    return JobChanged(
        control=name,
        paused=paused,
        run_requested_at=requested,
        changed_by=asked.caller.principal.id,
        changed_at=asked.now,
    )


@router.post("/jobs/{name}/run", response_model=JobChanged, responses=COMMON_RESPONSES)
async def run_job(request: Request, name: str, asked: Asked) -> JobChanged:
    """Ask for one run now: the worker starts it on its next tick, paused or not."""
    _authorised(name, asked)
    async with _require_sessions(request)() as session:
        if not await is_on(session, SCHEDULE_CONTROL):
            await session.rollback()
            raise _refused_because(SWITCHED_OFF)
        try:
            await _attribute(session, asked)
            await request_run(session, name, at=asked.now, by=asked.caller.principal.id)
        except ScheduleControlError as refused:
            await session.rollback()
            raise _refused_because(str(refused)) from None
        paused, requested = await _now_holds(session, name)
        await session.commit()
    return JobChanged(
        control=name,
        paused=paused,
        run_requested_at=requested,
        changed_by=asked.caller.principal.id,
        changed_at=asked.now,
    )
