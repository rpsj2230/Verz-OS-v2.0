"""Where workflows are kept: versions, assignments and the trace of each run.

`ops.workflow_version`, `agent.workflow_assignment`, `ops.workflow_run` and `ops.workflow_step_run`
(`0273`). This is the whole of the translation in both directions and it decides nothing: a
definition read back is read again by `brain.orchestration.workflow.read_definition`, so a row that
somehow held something the reader refuses cannot come back as a workflow that runs.

**A version is the next number and the table is the lock.** Saving reads the newest version and
writes one more; two saves at once both compute the same number and the unique key refuses the
second, which the caller reads as "somebody else saved first" and not as a fault.

**Every write is in the session's own name**, by `app.principal_id`, set here in the caller's
transaction before the insert, because the insert policies admit nothing else.

**The trace is written whole or not at all.** A run row and its step rows are added in one
transaction, and a step row is admitted only for a run the same person wrote. What is written is the
engine's `RunRecord`: statuses and words from closed lists.

**Repeated failure is read, not remembered.** `failed_steps_by_run` answers from the step rows which
steps failed in each of a workflow's last runs, newest first, so the counting is `repeats`' and
there is no counter to drift. `candidate_ref` is the one token a candidate for a step is filed
under.

Task ids: M17.6.1, M17.6.7, M17.6.8, M17.7.7
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Final

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from brain.ops.outbox import EventKind, OutboxEvent
from brain.ops.outbox_store import record_event, subscribers
from brain.ops.quality_store import open_candidates
from brain.orchestration.workflow import Definition, WorkflowError, read_definition
from brain.orchestration.workflow_run import (
    REPEATED_FAILURES_BEFORE_A_CANDIDATE,
    RunRecord,
    Status,
    repeats,
    signal_of,
)
from brain.tables.quality import CandidateSource
from brain.tables.workflow import (
    WorkflowAssignmentRow,
    WorkflowRunRow,
    WorkflowStepRunRow,
    WorkflowVersionRow,
)

#: The entity a workflow run is filed under in the outbox, beside an automation run's.
RUN_ENTITY: Final = "workflow_run"

#: The most workflows one listing returns. A screen showing more is a log.
MOST_LISTED: Final = 200

#: The most runs one read returns, newest first.
MOST_RUNS: Final = 50


class SavedFirstError(Exception):
    """Somebody saved the same workflow between the read and the write. Read it again."""


@dataclass(frozen=True)
class Stored:
    """One saved version, read back through the definition reader."""

    workflow_id: str
    version: int
    definition: Definition
    saved_by: str
    saved_at: datetime


@dataclass(frozen=True)
class Listed:
    """One workflow as a list shows it: its newest version and name."""

    workflow_id: str
    version: int
    name: str


async def _as(session: AsyncSession, principal: str) -> None:
    await session.execute(
        text("SELECT set_config('app.principal_id', :who, true)"), {"who": principal}
    )


def _stored(row: WorkflowVersionRow) -> Stored:
    return Stored(
        workflow_id=row.workflow_id,
        version=row.version,
        definition=read_definition(row.definition),
        saved_by=row.saved_by,
        saved_at=row.saved_at,
    )


async def save(session: AsyncSession, *, workflow_id: str, raw: Any, by: str) -> int:
    """Save the definition as the next version, in the saver's name, and say which number it is.

    Raises `WorkflowError` for a definition the reader refuses, with every reason, before anything
    is written, and `SavedFirstError` when another save took the number.
    """
    definition = read_definition(raw)
    newest = (
        await session.execute(
            select(func.max(WorkflowVersionRow.version)).where(
                WorkflowVersionRow.workflow_id == workflow_id
            )
        )
    ).scalar_one_or_none()
    number = (newest or 0) + 1
    await _as(session, by)
    try:
        async with session.begin_nested():
            session.add(
                WorkflowVersionRow(
                    workflow_id=workflow_id,
                    version=number,
                    name=definition.name,
                    definition=raw,
                    saved_by=by,
                )
            )
            await session.flush()
    except IntegrityError as taken:
        raise SavedFirstError from taken
    return number


async def latest(session: AsyncSession, workflow_id: str) -> Stored | None:
    """The newest saved version of a workflow, or None when there is none."""
    row = (
        await session.execute(
            select(WorkflowVersionRow)
            .where(WorkflowVersionRow.workflow_id == workflow_id)
            .order_by(WorkflowVersionRow.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return None if row is None else _stored(row)


async def version_of(session: AsyncSession, workflow_id: str, version: int) -> Stored | None:
    """One named version, or None."""
    row = (
        await session.execute(
            select(WorkflowVersionRow).where(
                WorkflowVersionRow.workflow_id == workflow_id,
                WorkflowVersionRow.version == version,
            )
        )
    ).scalar_one_or_none()
    return None if row is None else _stored(row)


async def listing(session: AsyncSession) -> tuple[Listed, ...]:
    """Every workflow with its newest version, by id."""
    rows = (
        await session.execute(
            select(
                WorkflowVersionRow.workflow_id, WorkflowVersionRow.version, WorkflowVersionRow.name
            )
            .distinct(WorkflowVersionRow.workflow_id)
            .order_by(WorkflowVersionRow.workflow_id, WorkflowVersionRow.version.desc())
            .limit(MOST_LISTED)
        )
    ).all()
    return tuple(Listed(str(a), int(b), str(c)) for a, b, c in rows)


# ------------------------------------------------------------------------------ assignments
async def assigned_to(session: AsyncSession, agent_id: str) -> tuple[str, ...]:
    """The workflows an agent may run, sorted."""
    rows = (
        await session.execute(
            select(WorkflowAssignmentRow.workflow_id)
            .where(
                WorkflowAssignmentRow.agent_id == agent_id,
                WorkflowAssignmentRow.removed_at.is_(None),
            )
            .order_by(WorkflowAssignmentRow.workflow_id)
        )
    ).scalars()
    return tuple(rows)


async def assign(session: AsyncSession, *, agent_id: str, workflow_id: str, by: str) -> bool:
    """Let an agent run a workflow, in the assigner's name. False when it already could."""
    if workflow_id in await assigned_to(session, agent_id):
        return False
    await _as(session, by)
    session.add(WorkflowAssignmentRow(agent_id=agent_id, workflow_id=workflow_id, assigned_by=by))
    await session.flush()
    return True


async def unassign(session: AsyncSession, *, agent_id: str, workflow_id: str, by: str) -> bool:
    """Withdraw an assignment, in the remover's name. False when there was none live."""
    await _as(session, by)
    done = await session.execute(
        update(WorkflowAssignmentRow)
        .where(
            WorkflowAssignmentRow.agent_id == agent_id,
            WorkflowAssignmentRow.workflow_id == workflow_id,
            WorkflowAssignmentRow.removed_at.is_(None),
        )
        .values(removed_by=by, removed_at=text("statement_timestamp()"))
        .returning(WorkflowAssignmentRow.id)
    )
    return done.first() is not None


# ------------------------------------------------------------------------------ the trace
async def keep_run(session: AsyncSession, record: RunRecord, *, at: datetime, by: str) -> None:
    """Write one run and every step of it, in the runner's name. Does not commit."""
    await _as(session, by)
    session.add(
        WorkflowRunRow(
            run_id=record.run_id,
            workflow_id=record.workflow_id,
            version=record.version,
            agent_id=record.agent_id,
            run_by=by,
            started_at=at,
            outcome=record.outcome.value,
            failed_step=record.failed_step,
        )
    )
    await session.flush()
    for position, step in enumerate(record.steps):
        session.add(
            WorkflowStepRunRow(
                run_id=record.run_id,
                step_id=step.step_id,
                position=position,
                status=step.status.value,
                cause=None if step.cause is None else step.cause.value,
                detail=step.detail,
                attempts=step.attempts,
                seconds=step.seconds,
            )
        )
    await session.flush()


@dataclass(frozen=True)
class KeptStep:
    step_id: str
    status: str
    cause: str | None
    detail: str
    attempts: int
    seconds: float


@dataclass(frozen=True)
class KeptRun:
    run_id: str
    workflow_id: str
    version: int
    agent_id: str
    run_by: str
    started_at: datetime
    outcome: str
    failed_step: str | None
    steps: tuple[KeptStep, ...]


async def recent_runs(
    session: AsyncSession, *, workflow_id: str | None = None, limit: int = MOST_RUNS
) -> tuple[KeptRun, ...]:
    """The newest runs first, with their steps in the order they were listed."""
    query = select(WorkflowRunRow).order_by(WorkflowRunRow.started_at.desc(), WorkflowRunRow.id)
    if workflow_id is not None:
        query = query.where(WorkflowRunRow.workflow_id == workflow_id)
    runs = (await session.execute(query.limit(min(limit, MOST_RUNS)))).scalars().all()
    if not runs:
        return ()
    steps = (
        (
            await session.execute(
                select(WorkflowStepRunRow)
                .where(WorkflowStepRunRow.run_id.in_([one.run_id for one in runs]))
                .order_by(WorkflowStepRunRow.run_id, WorkflowStepRunRow.position)
            )
        )
        .scalars()
        .all()
    )
    by_run: dict[str, list[KeptStep]] = {}
    for one in steps:
        by_run.setdefault(one.run_id, []).append(
            KeptStep(one.step_id, one.status, one.cause, one.detail, one.attempts, one.seconds)
        )
    return tuple(
        KeptRun(
            run_id=one.run_id,
            workflow_id=one.workflow_id,
            version=one.version,
            agent_id=one.agent_id,
            run_by=one.run_by,
            started_at=one.started_at,
            outcome=one.outcome,
            failed_step=one.failed_step,
            steps=tuple(by_run.get(one.run_id, ())),
        )
        for one in runs
    )


async def failed_steps_by_run(session: AsyncSession, workflow_id: str) -> list[frozenset[str]]:
    """Which steps failed in each of a workflow's last runs, newest first."""
    runs = (
        (
            await session.execute(
                select(WorkflowRunRow.run_id)
                .where(WorkflowRunRow.workflow_id == workflow_id)
                .order_by(WorkflowRunRow.started_at.desc(), WorkflowRunRow.id)
                .limit(REPEATED_FAILURES_BEFORE_A_CANDIDATE)
            )
        )
        .scalars()
        .all()
    )
    if not runs:
        return []
    failed = (
        await session.execute(
            select(WorkflowStepRunRow.run_id, WorkflowStepRunRow.step_id).where(
                WorkflowStepRunRow.run_id.in_(runs),
                WorkflowStepRunRow.status == Status.FAILED.value,
            )
        )
    ).all()
    by_run: dict[str, set[str]] = {one: set() for one in runs}
    for run_id, step_id in failed:
        by_run[str(run_id)].add(str(step_id))
    return [frozenset(by_run[one]) for one in runs]


@dataclass(frozen=True)
class Finished:
    """What finishing a run did beyond keeping it: the steps a candidate was opened for."""

    candidates: tuple[str, ...]


def run_event(record: RunRecord, *, at: datetime) -> OutboxEvent:
    """The outbox event a finished run is written with: identifiers and a word, never a value.

    `automation.run_finished` with the entity `workflow_run`, so a subscriber to run endings is told
    of a workflow's as it is of an automation's, and the signal names the workflow, the agent and
    the first step that failed (M17.6.7). Adding an event kind was rejected: it widens two check
    constraints and every subscriber's vocabulary for a distinction the entity already carries.
    """
    attributes: dict[str, str | int] = {
        "workflow_id": record.workflow_id,
        "agent_id": record.agent_id,
        "outcome": signal_of(record).outcome,
    }
    if record.failed_step is not None:
        attributes["failed_step"] = record.failed_step
    return OutboxEvent(
        event_id=record.run_id,
        kind=EventKind.AUTOMATION_RUN_FINISHED,
        entity=RUN_ENTITY,
        record_id=record.run_id,
        occurred_at=at,
        attributes=MappingProxyType(attributes),
    )


async def finish(session: AsyncSession, record: RunRecord, *, at: datetime, by: str) -> Finished:
    """Keep the run, tell the subscribers it ended, and open a candidate for a repeated failure.

    One transaction, so there is no instant at which a run is kept and nobody is told, or told of a
    run that was never kept. A candidate is opened for a step that failed in each of the last runs,
    this one included, against the agent that ran it; it changes no workflow.
    """
    await keep_run(session, record, at=at, by=by)
    await record_event(session, run_event(record, at=at), await subscribers(session))
    opened: list[str] = []
    for step in record.steps:
        if step.status is not Status.FAILED:
            continue
        history = await failed_steps_by_run(session, record.workflow_id)
        if repeats(history, step.step_id):
            made = await open_candidates(
                session,
                agent_id=record.agent_id,
                source=CandidateSource.WORKFLOW,
                failed_case_refs=[candidate_ref(record.workflow_id, step.step_id)],
                by=by,
            )
            if made:
                opened.append(step.step_id)
    return Finished(candidates=tuple(opened))


def candidate_ref(workflow_id: str, step_id: str) -> str:
    """The one token a candidate about a step is filed under: no spaces, bounded."""
    return f"workflow:{workflow_id}:{step_id}"


__all__ = ["SavedFirstError", "WorkflowError", "candidate_ref"]
