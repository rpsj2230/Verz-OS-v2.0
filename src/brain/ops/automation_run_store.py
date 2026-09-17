"""The worker's half of running an installed automation: claim what is due, run it, record it.

`brain.ops.automation_run` decides every question a run asks and holds no connection. This is the
SQL between those decisions, the one performer this install has, and `run_automations_now`, which
is what the worker's schedule starts as the `automation_run` control.

**One automation is one transaction, and the row lock is the claim.** The ids due at the run's
instant are read first, then each is locked `FOR UPDATE SKIP LOCKED` and read again in its own
transaction, and it runs only if it is still due. A second worker skips a locked automation, and one
started or stopped from the console while a run was queued is found as it now is. The run row, the
outbox event, the next run and any schedule row commit together. See
`A_RUN_IS_CLAIMED_BY_ITS_ROW_AND_WRITTEN_WITH_ITS_CONSEQUENCES`.

**The owner and their reach are read through the product's own readers.** The principal through
`brain.identity.principal_store.StoredPrincipals` and the entitlements through
`brain.gate.entitlement_store.StoredEntitlements`, each on its own connection, so the run's reach is
the reach a request from that person would be resolved at, and nothing here writes a query for it.

**A task that raises is a failed run and not a failed batch.** The performer runs under a savepoint,
so an exception from a read rolls back the read alone and the failure is recorded in the same
transaction. The exception's text is not kept anywhere: its type reaches the operator's log, for
`brain.tables.automation_run`'s reason.

**On the worker's own connection**, which is the database owner's, as `brain.ops.erasure_store`
argues: the application role holds SELECT on the runs, so no request the console serves can record
one, and a policy narrowing what the run reads would hide an automation from the worker that has to
run it. What the run may read is narrowed by the reach, which is the only narrowing a run has.

**The console's half is here too, and it writes as the application role.**
`StoredAutomationSchedules` lists an agent's automations with their newest runs and the reason on
the newest schedule row, and writes a start or a stop as `moving` plus one
`agent.automation_schedule` row, conditional on the automation still having the next run that was
shown, in the caller's name so `0067`'s policies and trigger attribute it. Who may do either is
`brain.console.automation_schedule`'s question.

Task ids: M39.6.2.1, M39.6.2.3, M38.2.2.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

import structlog
from sqlalchemy import Select, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import one_agent, record_of
from brain.agents.model import AgentRecord
from brain.console.agent_automations import Automation, SchedulerChange
from brain.console.automation_gallery import template_by_id
from brain.console.questions_view import gap_lines
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.gate.entitlement_store import StoredEntitlements
from brain.gate.resolve import EntitlementStore
from brain.identity.principal_store import StoredPrincipals
from brain.ops.automation_owner import PrincipalRecords
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.ops.automation_run import (
    PAUSE_AFTER,
    REPORT_PERIOD,
    RUNNER_ACTOR,
    Admitted,
    AutomationRunError,
    PausedBecause,
    RunOutcome,
    RunRecord,
    admitted_run,
    afterwards,
    failures_in_a_row,
    run_event,
    run_id,
)
from brain.ops.outbox_store import record_event, subscribers
from brain.ops.question_gap_store import gaps_between
from brain.session import make_app_engine, make_session_factory
from brain.tables.agent_automation import AgentAutomationRow
from brain.tables.audit import ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.automation_run import STARTED, AutomationRunRow, AutomationScheduleRow
from brain.tables.identity import PrincipalRow

log = structlog.get_logger()

#: Why the claim, the run and its consequences are one transaction.
A_RUN_IS_CLAIMED_BY_ITS_ROW_AND_WRITTEN_WITH_ITS_CONSEQUENCES: Final = (
    "The automation's row is locked for the length of its run, so a second worker skips it and a "
    "console change waits for it. The run, the event that says it finished, the next run and the "
    "reason it stopped commit together, so there is no instant at which a run is recorded and "
    "the automation is still due for the same slot, or paused with no run saying why."
)

#: How many automations one tick runs. The rest wait for the next tick, a minute later.
RUN_BATCH: Final = 20

#: How often the control is owed. A minute, because the cadences are on the hour and a run
#: started up to a minute late is on time for an outcome that is a weekly or a daily report.
RUN_EVERY: Final = timedelta(minutes=1)


# ------------------------------------------------------------------ the statements
def owed_ids(now: datetime, limit: int) -> Select[tuple[str]]:
    """The automations owed a run at `now`, soonest first, bounded. Read without a lock.

    Not named for the word `brain.ops.controls` reads as a recurrence predicate: this is the
    control's query rather than a second schedule, and the control is registered.
    """
    return (
        select(AgentAutomationRow.automation_id)
        .where(AgentAutomationRow.next_run_at.is_not(None), AgentAutomationRow.next_run_at <= now)
        .order_by(AgentAutomationRow.next_run_at, AgentAutomationRow.automation_id)
        .limit(limit)
    )


def claim(automation_id: str, now: datetime) -> Select[tuple[AgentAutomationRow]]:
    """One automation, locked, if it is still due and no other worker holds it."""
    return (
        select(AgentAutomationRow)
        .where(
            AgentAutomationRow.automation_id == automation_id,
            AgentAutomationRow.next_run_at.is_not(None),
            AgentAutomationRow.next_run_at <= now,
        )
        .with_for_update(skip_locked=True)
    )


def last_started(automation_id: str) -> Select[tuple[datetime]]:
    """When this automation was last started from the console, or null."""
    return select(func.max(AutomationScheduleRow.at)).where(
        AutomationScheduleRow.automation_id == automation_id,
        AutomationScheduleRow.reason == STARTED,
    )


def outcomes_since(automation_id: str, since: datetime | None, limit: int) -> Select[tuple[str]]:
    """The newest runs' outcomes since the last start, newest first, bounded."""
    query = select(AutomationRunRow.outcome).where(AutomationRunRow.automation_id == automation_id)
    if since is not None:
        query = query.where(AutomationRunRow.finished_at > since)
    return query.order_by(AutomationRunRow.finished_at.desc()).limit(limit)


def run_values(record: RunRecord) -> dict[str, Any]:
    """What a run writes."""
    return {
        "run_id": record.run_id,
        "automation_id": record.automation_id,
        "agent_id": record.agent_id,
        "principal_id": record.principal_id,
        "due_at": record.due_at,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "outcome": record.outcome.value,
        "reason": None if record.reason is None else record.reason.value,
        "ent_hash": record.ent_hash,
        "result": list(record.result),
    }


def writing_run(record: RunRecord) -> Any:
    """The run's insert, which writes nothing for a slot already recorded."""
    return (
        upsert(AutomationRunRow)
        .values(**run_values(record))
        .on_conflict_do_nothing(index_elements=[AutomationRunRow.run_id])
        .returning(AutomationRunRow.run_id)
    )


def rescheduling(automation_id: str, next_run_at: datetime | None) -> Any:
    """The automation's next run, or none."""
    return (
        update(AgentAutomationRow)
        .where(AgentAutomationRow.automation_id == automation_id)
        .values(next_run_at=next_run_at, updated_at=func.now())
    )


def schedule_change(
    *,
    automation_id: str,
    agent_id: str,
    next_run_at: datetime | None,
    reason: str,
    changed_by: str,
    at: datetime,
) -> Any:
    """One start, stop or pause, whose trigger appends the ledger entry."""
    return insert(AutomationScheduleRow).values(
        automation_id=automation_id,
        agent_id=agent_id,
        next_run_at=next_run_at,
        reason=reason,
        changed_by=changed_by,
        at=at,
    )


def _set_config(name: str, value: str) -> Any:
    # Transaction-local, as `brain.ops.agent_automation_store` sets the same setting.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


# ------------------------------------------------------------------ the performer
async def perform(admitted: Admitted, session: AsyncSession, *, now: datetime) -> tuple[str, ...]:
    """What one runnable task found, at the run's reach, as lines. Reads and writes nothing else.

    One arm per task `automation_run.TASKS` declares runnable, and a declared-runnable task with no
    arm raises, which records a failed run rather than a success that examined nothing.
    """
    match admitted.declaration.task:
        case "automation.unanswered_questions":
            gaps = await gaps_between(session, start=now - REPORT_PERIOD, end=now)
            lines = gap_lines(gaps, admitted.reach, now=now)
            if not lines:
                return (NOTHING_THIS_WEEK,)
            return tuple(
                f"{one.asked} asked in {one.department} that "
                f"{one.source if one.source is not None else 'a source you are not told of'} "
                "would have answered"
                for one in lines
            )
        case _:
            msg = f"{admitted.declaration.task!r} is declared runnable and nothing performs it"
            raise AutomationRunError(msg)


#: What a report with nothing in it says. The same sentence whatever the reason there is nothing.
NOTHING_THIS_WEEK: Final = "Nothing to report this week."


# ------------------------------------------------------------------ one run
@dataclass(frozen=True)
class Ran:
    """What one automation's run did, for the tick's summary."""

    outcome: RunOutcome
    paused: bool


def _stand_in(principal_id: str, display_name: str | None = None) -> Principal:
    """The principal an automation names, as a name and an id and nothing a reach is computed from.

    A refused run and a listing need only the id and a name, and `Automation` takes a whole
    principal. A stand-in is never handed to anything that computes a reach: a run's reach is the
    resolver's answer for the id, and `admitted_run` refuses the run first when the directory no
    longer holds the person.
    """
    return Principal(
        id=principal_id,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name=display_name or principal_id,
    )


async def run_one(
    sessions: async_sessionmaker[AsyncSession],
    automation_id: str,
    *,
    now: datetime,
    principals: PrincipalRecords,
    entitlements: EntitlementStore,
) -> Ran | None:
    """Run one automation if it is still due, and write the run and its consequences.

    None when another worker holds it, a console change made it not due, or its row no longer
    constructs, which is logged and left for the next tick rather than paused on a guess.
    """
    async with sessions() as session, session.begin():
        await session.execute(_set_config(PRINCIPAL_SETTING, RUNNER_ACTOR))
        row = (await session.execute(claim(automation_id, now))).scalar_one_or_none()
        if row is None or row.next_run_at is None:
            return None
        owner = await principals.live_principal(row.runs_as_id)
        try:
            automation = Automation(
                automation_id=row.automation_id,
                agent_id=row.agent_id,
                name=row.name,
                runs_as=owner if owner is not None else _stand_in(row.runs_as_id),
                task=row.task,
                next_run_at=row.next_run_at,
            )
        except ValueError as exc:
            log.warning(
                "automation row does not construct",
                automation=automation_id,
                error=type(exc).__name__,
            )
            return None
        agent_row = (await session.execute(one_agent(row.agent_id))).scalar_one_or_none()
        agent: AgentRecord | None = None if agent_row is None else record_of(agent_row)
        template = template_by_id(row.template_id)
        decided: Admitted | PausedBecause
        if template is None:
            decided = PausedBecause.TASK_UNBUILT
        else:
            decided = admitted_run(
                automation,
                owner=owner,
                owner_entitlements=await entitlements.load(row.runs_as_id, now),
                agent=agent,
                now=now,
            )

        result: tuple[str, ...] = ()
        if isinstance(decided, PausedBecause):
            outcome, refused, ent_hash = RunOutcome.REFUSED, decided, None
        else:
            refused, ent_hash = None, decided.reach.ent_hash()
            try:
                async with session.begin_nested():
                    result = await perform(decided, session, now=now)
                outcome = RunOutcome.SUCCEEDED
            except Exception as exc:
                # Broad on purpose: whatever a task raised is a failed run of it, and the text of
                # an exception from a read can quote a column, so only its type is logged.
                log.warning(
                    "automation run failed", automation=automation_id, error=type(exc).__name__
                )
                outcome, result = RunOutcome.FAILED, ()

        since = (await session.execute(last_started(row.automation_id))).scalar_one_or_none()
        before = [
            RunOutcome(one)
            for one in (
                await session.execute(outcomes_since(row.automation_id, since, PAUSE_AFTER))
            )
            .scalars()
            .all()
        ]
        record = RunRecord(
            run_id=run_id(row.automation_id, row.next_run_at),
            automation_id=row.automation_id,
            agent_id=row.agent_id,
            principal_id=row.runs_as_id,
            due_at=row.next_run_at,
            started_at=now,
            finished_at=now,
            outcome=outcome,
            reason=refused,
            ent_hash=ent_hash,
            result=result,
        )
        if (await session.execute(writing_run(record))).scalar_one_or_none() is None:
            # The slot is already recorded: a run somebody else finished, whose consequences are
            # theirs. Not reachable while the row lock is held, and kept because the key is the
            # guarantee and the lock is only how it is usually not needed.
            return None
        await record_event(session, run_event(record), await subscribers(session))

        then = afterwards(
            automation,
            outcome=outcome,
            refused_because=refused,
            failures_before=failures_in_a_row(before),
            cadence=None if template is None else template.cadence,
            owner_id=row.runs_as_id if agent is None else agent.audience.owner_id,
            guards=row.guards,
            at=now,
        )
        await session.execute(rescheduling(row.automation_id, then.next_run_at))
        if then.paused_because is None:
            return Ran(outcome=outcome, paused=False)
        await session.execute(
            schedule_change(
                automation_id=row.automation_id,
                agent_id=row.agent_id,
                next_run_at=None,
                reason=then.paused_because.value,
                changed_by=RUNNER_ACTOR,
                at=now,
            )
        )
        return Ran(outcome=outcome, paused=True)


# ------------------------------------------------------------------ one tick
@dataclass(frozen=True)
class AutomationTick:
    """What one tick did, as counts of this install's own automations. Names nothing."""

    succeeded: int
    failed: int
    refused: int
    paused: int

    def summary(self) -> str:
        if not (self.succeeded or self.failed or self.refused):
            return "no automation was due"
        return (
            f"{self.succeeded} ran, {self.failed} failed, {self.refused} refused; "
            f"{self.paused} paused"
        )


async def run_automations(
    sessions: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    principals: PrincipalRecords | None = None,
    entitlements: EntitlementStore | None = None,
    limit: int = RUN_BATCH,
) -> AutomationTick:
    """Every automation due at `now`, up to `limit`, each in its own transaction."""
    async with sessions() as session:
        ids = (await session.execute(owed_ids(now, limit))).scalars().all()
    readers = StoredPrincipals(sessions) if principals is None else principals
    loader = StoredEntitlements(sessions) if entitlements is None else entitlements
    ran: list[Ran] = []
    for one in ids:
        done = await run_one(sessions, one, now=now, principals=readers, entitlements=loader)
        if done is not None:
            ran.append(done)
    return tick_of(ran)


def tick_of(ran: Sequence[Ran]) -> AutomationTick:
    """The counts a tick's runs come to."""
    outcomes = [one.outcome for one in ran]
    return AutomationTick(
        succeeded=outcomes.count(RunOutcome.SUCCEEDED),
        failed=outcomes.count(RunOutcome.FAILED),
        refused=outcomes.count(RunOutcome.REFUSED),
        paused=sum(1 for one in ran if one.paused),
    )


def run_automations_now(
    database_url: str,
    *,
    now: datetime,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> str:
    """`run_automations` from a thread with no event loop of its own, as a summary line.

    The shape `brain.knowledge.item_store.run_reverification_now` takes, for its reasons.
    """

    async def once() -> AutomationTick:
        engine = make_app_engine(database_url)
        try:
            return await run_automations(make_session_factory(engine), now=now)
        finally:
            await engine.dispose()

    return asyncio.run(once(), loop_factory=loop_factory).summary()


# ------------------------------------------------------------------ the console's half
#: How many of an automation's newest runs the Automations tab reads.
RUNS_SHOWN: Final = 5


@dataclass(frozen=True)
class Listed:
    """One of an agent's automations as the Automations tab reads it.

    `stopped_because` is the reason on the newest schedule row when the automation has no next run,
    and None both for one that is running and for one that was installed and never started.
    """

    automation: Automation
    template_id: str
    guards: str
    stopped_because: str | None
    #: Newest first.
    runs: tuple[RunRecord, ...]


def automations_of_agent(agent_id: str) -> Select[tuple[AgentAutomationRow, str]]:
    """One agent's automations, each with the name the directory holds for whom it runs as."""
    return (
        select(AgentAutomationRow, PrincipalRow.display_name)
        .outerjoin(PrincipalRow, PrincipalRow.id == AgentAutomationRow.runs_as_id)
        .where(AgentAutomationRow.agent_id == agent_id)
        .order_by(AgentAutomationRow.automation_id)
    )


def newest_schedule_reason(automation_id: str) -> Select[tuple[str]]:
    """The reason on this automation's newest schedule row."""
    return (
        select(AutomationScheduleRow.reason)
        .where(AutomationScheduleRow.automation_id == automation_id)
        .order_by(AutomationScheduleRow.at.desc(), AutomationScheduleRow.id)
        .limit(1)
    )


def newest_runs(automation_id: str, limit: int) -> Select[tuple[AutomationRunRow]]:
    """This automation's newest runs, newest first, bounded."""
    return (
        select(AutomationRunRow)
        .where(AutomationRunRow.automation_id == automation_id)
        .order_by(AutomationRunRow.finished_at.desc(), AutomationRunRow.run_id)
        .limit(limit)
    )


def record_of_run(row: AutomationRunRow) -> RunRecord | None:
    """A stored run as the domain's record, or None and a log line when it does not construct."""
    try:
        return RunRecord(
            run_id=row.run_id,
            automation_id=row.automation_id,
            agent_id=row.agent_id,
            principal_id=row.principal_id,
            due_at=row.due_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            outcome=RunOutcome(row.outcome),
            reason=None if row.reason is None else PausedBecause(row.reason),
            ent_hash=row.ent_hash,
            result=tuple(row.result),
        )
    except ValueError as exc:
        log.warning("automation run does not construct", run=row.run_id, error=type(exc).__name__)
        return None


def moving(change: SchedulerChange) -> Any:
    """The next run a change leaves, written only where the automation still has the one shown.

    `IS NOT DISTINCT FROM` because the one shown is null for a start, and `=` is never true of a
    null, so a start would write nothing.
    """
    before, after = change.before, change.after
    assert after is not None  # a start and a stop both leave the automation; a removal is not here
    return (
        update(AgentAutomationRow)
        .where(
            AgentAutomationRow.automation_id == before.automation_id,
            AgentAutomationRow.next_run_at.is_not_distinct_from(before.next_run_at),
        )
        .values(next_run_at=after.next_run_at, updated_at=func.now())
        .returning(AgentAutomationRow.automation_id)
    )


class StoredAutomationSchedules:
    """`brain.automation_schedule_routes.AutomationSchedules` over this install's database."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def listed(self, agent_id: str) -> tuple[Listed, ...]:
        found: list[Listed] = []
        async with self._sessions() as session, session.begin():
            rows = (await session.execute(automations_of_agent(agent_id))).all()
            for row, display_name in rows:
                try:
                    automation = Automation(
                        automation_id=row.automation_id,
                        agent_id=row.agent_id,
                        name=row.name,
                        runs_as=_stand_in(row.runs_as_id, display_name),
                        task=row.task,
                        next_run_at=row.next_run_at,
                    )
                except ValueError as exc:
                    log.warning(
                        "automation row does not construct",
                        automation=row.automation_id,
                        error=type(exc).__name__,
                    )
                    continue
                reason = None
                if row.next_run_at is None:
                    reason = (
                        await session.execute(newest_schedule_reason(row.automation_id))
                    ).scalar_one_or_none()
                runs = (
                    (await session.execute(newest_runs(row.automation_id, RUNS_SHOWN)))
                    .scalars()
                    .all()
                )
                found.append(
                    Listed(
                        automation=automation,
                        template_id=row.template_id,
                        guards=row.guards,
                        stopped_because=reason,
                        runs=tuple(one for one in map(record_of_run, runs) if one is not None),
                    )
                )
        return tuple(found)

    async def change(
        self,
        change: SchedulerChange,
        *,
        reason: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        at: datetime,
    ) -> bool:
        """Write one start or stop and the row whose trigger records it, or nothing.

        False when the automation no longer has the next run that was shown, which is somebody
        else's change or a run arriving first; nothing is written then, and the route says to look
        again.
        """
        after = change.after
        if after is None:
            msg = "a removal is not a start or a stop and nothing here writes one"
            raise AutomationRunError(msg)
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, actor))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            if (await session.execute(moving(change))).scalar_one_or_none() is None:
                return False
            await session.execute(
                schedule_change(
                    automation_id=after.automation_id,
                    agent_id=after.agent_id,
                    next_run_at=after.next_run_at,
                    reason=reason,
                    changed_by=actor,
                    at=at,
                )
            )
        return True
