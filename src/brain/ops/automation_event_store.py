"""The worker's half of starting an automation by a change: find changes, run each once, record it.

`brain.ops.automation_event` decides what is due and holds no connection. This is the SQL between
those decisions and the worker's `automation_run` control, which runs it as the second half of
every tick when `brain.ops.features.AUTOMATION_EVENTS` is on. Nothing here is a second runner: the
reach is `brain.ops.automation_run.admitted_run`, the performer is
`brain.ops.automation_run_store.perform`, the run is a `RunRecord` in the same table, its
consequences leave through the same outbox event and its failures pause through the same
`afterwards`. What differs is what makes it due.

**An armed automation is one whose `next_run_at` holds the instant it was armed.** A change starts
nothing before that instant, and no cadence ever moves it, so what the console shows as the next
run of an automation a change starts is the instant it began listening. It is the one column that
already meant "something will pick this up", which is why no migration was needed and why the
scheduled runner now refuses these rows (`brain.ops.automation_run_store.owed_ids`): without that a
row armed at noon would be due at once, claimed as a schedule with no cadence and refused.

**One automation is one transaction and the row lock is the claim**, as in the scheduled runner and
for its reason: a second worker skips a locked automation and a stop from the console waits for the
pass. The pass's runs, their outbox events, the failure count and any pause commit together.

**The owner's reach decides which changes count, inside the statement.** The reach is the owner's
entitlements at the pass's instant narrowed by the agent's ceiling. For each entity of the source
the row scope that reach holds (`brain.knowledge.rows.row_scope_for`) is compiled by
`brain.core.scope_sql.compile_where` into the WHERE clause that finds changed rows, so a record the
owner may not read is never selected. An entity the reach holds no grant on contributes nothing.
See `brain.ops.automation_event.A_CHANGE_OUTSIDE_THE_OWNERS_REACH_STARTS_NOTHING`. Rejected: finding
every change and filtering in Python, which moves the hidden rows' ids into this process for the
reason `brain.knowledge.rows` gives.

**An automation that could not run is refused at the door, once, and paused.** When `admitted_run`
refuses (the owner has gone, the agent is not enabled, the task has no performer, the reach no
longer holds what the task reads) the pass records one refused run keyed to the arming and removes
the next run, as a scheduled run does. It does that without waiting for a change, because waiting
would leave an automation that listens for ever to nobody and says nothing.

**A halt holds the pass and loses no change.** The halts are read before the claim as in
`run_one`; a pass held by one writes nothing and finds the same changes when the halt is lifted,
inside `MAX_AGE`.

Task ids: M17.4.1
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import one_agent, record_of
from brain.agents.model import AgentRecord
from brain.console.agent_automations import Automation
from brain.console.automation_authoring import AUTHORED_TEMPLATE
from brain.core.scope_sql import compile_where
from brain.gate.entitlement_store import StoredEntitlements
from brain.gate.resolve import EntitlementStore
from brain.identity.principal_store import StoredPrincipals
from brain.knowledge.rows import RECORD, ROW_LAYOUT, SCOPE_PREFIX, row_scope_for
from brain.ops import automation_run_store as runs
from brain.ops.automation_change_store import removed_ids
from brain.ops.automation_event import (
    REFUSED_AT_THE_DOOR,
    RUNS_WINDOW,
    Change,
    Window,
    allowance,
    change_key,
    due_changes,
    event_run_id,
    fetch_limit,
    refusal_run_id,
    window,
)
from brain.ops.automation_owner import PrincipalRecords
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.ops.automation_run import (
    PAUSE_AFTER,
    RUNNER_ACTOR,
    Admitted,
    PausedBecause,
    RunOutcome,
    RunRecord,
    admitted_run,
    afterwards,
    failures_in_a_row,
    run_event,
)
from brain.ops.features import AUTOMATION_EVENTS, is_on
from brain.ops.halt_store import Work, read_state, refusal_in
from brain.ops.outbox_store import record_event, subscribers
from brain.orchestration.unattended import TriggerKind
from brain.tables.agent_automation import AgentAutomationRow
from brain.tables.automation_run import AutomationRunRow

log = structlog.get_logger()

#: How many armed automations one pass looks at. The rest wait for the next pass, a minute later.
ARMED_BATCH: Final = 20


async def event_starts_are_on(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether a change may start an automation on this install. Off until somebody turns it on."""
    async with sessions() as session:
        return await is_on(session, AUTOMATION_EVENTS)


# ------------------------------------------------------------------ the statements
def _armed() -> tuple[object, ...]:
    """What makes an automation one a change starts and that is listening now."""
    return (
        AgentAutomationRow.next_run_at.is_not(None),
        AgentAutomationRow.template_id == AUTHORED_TEMPLATE,
        AgentAutomationRow.trigger_kind == TriggerKind.CONNECTOR_EVENT.value,
        AgentAutomationRow.trigger_source.is_not(None),
        AgentAutomationRow.automation_id.not_in(removed_ids()),
    )


def armed_ids(limit: int) -> Select[tuple[str]]:
    """The automations listening for a change, in the order they were armed, bounded."""
    return (
        select(AgentAutomationRow.automation_id)
        .where(*_armed())  # type: ignore[arg-type]
        .order_by(AgentAutomationRow.next_run_at, AgentAutomationRow.automation_id)
        .limit(limit)
    )


def claim_armed(automation_id: str) -> Select[tuple[AgentAutomationRow]]:
    """One armed automation, locked, unless another worker holds it."""
    return (
        select(AgentAutomationRow)
        .where(AgentAutomationRow.automation_id == automation_id, *_armed())  # type: ignore[arg-type]
        .with_for_update(skip_locked=True)
    )


def entities_of(source: str) -> Select[tuple[str]]:
    """The kinds of record this source's index holds, live only."""
    return (
        select(RECORD.c.entity)
        .where(RECORD.c.source == source, RECORD.c.deleted_at.is_(None))
        .distinct()
        .order_by(RECORD.c.entity)
    )


def changed_records(
    source: str,
    entity: str,
    reading: Window,
    scope_where: str,
    params: dict[str, object],
    limit: int,
) -> Select[tuple[str, datetime]]:
    """Live records of one entity whose fields changed in the window, in the owner's row scope.

    The scope is `compile_where`'s output, every value bound; nothing a person wrote is spliced.
    """
    return (
        select(RECORD.c.source_id, RECORD.c.updated_at)
        .where(
            RECORD.c.source == source,
            RECORD.c.entity == entity,
            RECORD.c.deleted_at.is_(None),
            RECORD.c.updated_at > reading.after,
            RECORD.c.updated_at >= reading.not_before,
            text(scope_where).bindparams(**params),
        )
        .order_by(RECORD.c.updated_at, RECORD.c.source_id)
        .limit(limit)
    )


def newest_change_run(automation_id: str, armed_at: datetime) -> Select[Any]:
    """The newest change this automation has run since it was armed, or null."""
    return select(func.max(AutomationRunRow.due_at)).where(
        AutomationRunRow.automation_id == automation_id, AutomationRunRow.due_at > armed_at
    )


def runs_recorded_in(automation_id: str, reading: Window) -> Select[tuple[int]]:
    """How many changes in the window this automation has already run."""
    return select(func.count()).where(
        AutomationRunRow.automation_id == automation_id,
        AutomationRunRow.due_at > reading.after,
        AutomationRunRow.due_at >= reading.not_before,
    )


def runs_started_since(automation_id: str, since: datetime) -> Select[tuple[int]]:
    """How many runs this automation has made since `since`, counted for the hourly bound."""
    return select(func.count()).where(
        AutomationRunRow.automation_id == automation_id, AutomationRunRow.started_at > since
    )


def recorded_among(ids: Sequence[str]) -> Select[tuple[str]]:
    """Which of these run ids are already recorded."""
    return select(AutomationRunRow.run_id).where(AutomationRunRow.run_id.in_(list(ids)))


# ------------------------------------------------------------------ one automation
async def _found(
    session: AsyncSession,
    admitted: Admitted,
    source: str,
    reading: Window,
    limit: int,
    now: datetime,
) -> list[Change]:
    """The changed records this owner's reach may read, across every entity the source holds."""
    found: list[Change] = []
    for entity in (await session.execute(entities_of(source))).scalars().all():
        scope = row_scope_for(entity, admitted.reach, now)
        if scope is None:
            continue
        predicate = compile_where(scope, ROW_LAYOUT, param_prefix=SCOPE_PREFIX)
        rows = await session.execute(
            changed_records(source, entity, reading, predicate.where, predicate.params, limit)
        )
        found.extend(
            Change(source=source, entity=entity, source_id=str(source_id), changed_at=changed_at)
            for source_id, changed_at in rows.all()
        )
    return found


async def run_changes_of(
    sessions: async_sessionmaker[AsyncSession],
    automation_id: str,
    *,
    now: datetime,
    principals: PrincipalRecords,
    entitlements: EntitlementStore,
) -> list[runs.Ran] | None:
    """Run every change that is due for one armed automation, and write the runs and their effects.

    None when another worker holds it, a stop made it not armed, its row does not construct, or a
    halt holds it. The runs a pass made otherwise, oldest change first, which is empty when nothing
    changed.
    """
    halts = await read_state(sessions)
    async with sessions() as session, session.begin():
        await session.execute(runs._set_config(PRINCIPAL_SETTING, RUNNER_ACTOR))
        row = (await session.execute(claim_armed(automation_id))).scalar_one_or_none()
        if row is None or row.next_run_at is None or row.trigger_source is None:
            return None
        armed_at = row.next_run_at
        now_is = await runs._folded(session, row, None)
        owner_id = now_is.owner_id
        owner = await principals.live_principal(owner_id)
        if refusal_in(
            halts,
            Work(
                person=owner_id,
                department="" if owner is None else owner.primary_department or "",
                agent=row.agent_id,
            ),
        ):
            log.info("automation held by a halt", automation=automation_id)
            return None
        try:
            automation = Automation(
                automation_id=row.automation_id,
                agent_id=row.agent_id,
                name=row.name,
                runs_as=owner if owner is not None else runs._stand_in(owner_id),
                task=row.task,
                next_run_at=armed_at,
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
        decided = admitted_run(
            automation,
            owner=owner,
            owner_entitlements=await entitlements.load(owner_id, now),
            agent=agent,
            now=now,
        )
        stopper = owner_id if agent is None else agent.audience.owner_id
        if isinstance(decided, PausedBecause):
            return await _refused_at_the_door(
                session, row, automation, decided, owner_id, stopper, now
            )

        newest = (await session.execute(newest_change_run(row.automation_id, armed_at))).scalar()
        reading = window(armed_at=armed_at, newest_run=newest, now=now)
        ran_this_hour = (
            await session.execute(runs_started_since(row.automation_id, now - RUNS_WINDOW))
        ).scalar_one()
        may_run = allowance(ran_this_hour=ran_this_hour)
        recorded_in_window = (
            await session.execute(runs_recorded_in(row.automation_id, reading))
        ).scalar_one()
        found = await _found(
            session,
            decided,
            row.trigger_source,
            reading,
            fetch_limit(recorded_in_window=recorded_in_window),
            now,
        )
        recorded = set(
            (
                await session.execute(
                    recorded_among([event_run_id(row.automation_id, one) for one in found])
                )
            )
            .scalars()
            .all()
        )
        due = due_changes(row.automation_id, found, recorded=recorded, allowed=may_run)
        if not due:
            return []

        since = (await session.execute(runs.last_started(row.automation_id))).scalar_one_or_none()
        before = [
            RunOutcome(one)
            for one in (
                await session.execute(runs.outcomes_since(row.automation_id, since, PAUSE_AFTER))
            )
            .scalars()
            .all()
        ]
        done: list[runs.Ran] = []
        outcomes = list(before)
        for change in due:
            outcome, result = await _perform(session, decided, now, automation_id)
            record = RunRecord(
                run_id=event_run_id(row.automation_id, change),
                automation_id=row.automation_id,
                agent_id=row.agent_id,
                principal_id=owner_id,
                due_at=change.changed_at,
                started_at=now,
                finished_at=now,
                outcome=outcome,
                ent_hash=decided.reach.ent_hash(),
                result=result,
                change_key=change_key(change),
            )
            if (await session.execute(runs.writing_run(record))).scalar_one_or_none() is None:
                continue
            await record_event(session, run_event(record), await subscribers(session))
            outcomes.insert(0, outcome)
            then = afterwards(
                automation,
                outcome=outcome,
                refused_because=None,
                failures_before=failures_in_a_row(outcomes[1:]),
                cadence=None,
                owner_id=stopper,
                guards=row.guards,
                at=now,
                armed_at=armed_at,
            )
            if then.paused_because is None:
                done.append(runs.Ran(outcome=outcome, paused=False))
                continue
            await session.execute(runs.rescheduling(row.automation_id, None))
            await session.execute(
                runs.schedule_change(
                    automation_id=row.automation_id,
                    agent_id=row.agent_id,
                    next_run_at=None,
                    reason=then.paused_because.value,
                    changed_by=RUNNER_ACTOR,
                    at=now,
                )
            )
            done.append(runs.Ran(outcome=outcome, paused=True))
            break
        return done


async def _perform(
    session: AsyncSession, admitted: Admitted, now: datetime, automation_id: str
) -> tuple[RunOutcome, tuple[str, ...]]:
    """The task at the run's reach, under a savepoint: a task that raises is a failed run."""
    try:
        async with session.begin_nested():
            return RunOutcome.SUCCEEDED, await runs.perform(admitted, session, now=now)
    except Exception as exc:
        # Broad on purpose, and for the scheduled runner's reason: only the type is logged.
        log.warning("automation run failed", automation=automation_id, error=type(exc).__name__)
        return RunOutcome.FAILED, ()


async def _refused_at_the_door(
    session: AsyncSession,
    row: AgentAutomationRow,
    automation: Automation,
    why: PausedBecause,
    owner_id: str,
    stopper: str,
    now: datetime,
) -> list[runs.Ran]:
    """Record the one refusal this arming can have, and stop listening, with the reason."""
    armed_at = automation.next_run_at
    assert armed_at is not None  # claimed as armed
    record = RunRecord(
        run_id=refusal_run_id(row.automation_id, armed_at),
        automation_id=row.automation_id,
        agent_id=row.agent_id,
        principal_id=owner_id,
        due_at=armed_at,
        started_at=now,
        finished_at=now,
        outcome=RunOutcome.REFUSED,
        reason=why,
        change_key=REFUSED_AT_THE_DOOR,
    )
    if (await session.execute(runs.writing_run(record))).scalar_one_or_none() is not None:
        await record_event(session, run_event(record), await subscribers(session))
    then = afterwards(
        automation,
        outcome=RunOutcome.REFUSED,
        refused_because=why,
        failures_before=0,
        cadence=None,
        owner_id=stopper,
        guards=row.guards,
        at=now,
    )
    await session.execute(runs.rescheduling(row.automation_id, then.next_run_at))
    await session.execute(
        runs.schedule_change(
            automation_id=row.automation_id,
            agent_id=row.agent_id,
            next_run_at=None,
            reason=why.value,
            changed_by=RUNNER_ACTOR,
            at=now,
        )
    )
    return [runs.Ran(outcome=RunOutcome.REFUSED, paused=True)]


# ------------------------------------------------------------------ one pass
async def run_changes(
    sessions: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    principals: PrincipalRecords | None = None,
    entitlements: EntitlementStore | None = None,
    limit: int = ARMED_BATCH,
) -> list[runs.Ran]:
    """Every armed automation's due changes at `now`, each automation in its own transaction.

    The caller decides whether the switch is on: this runs when asked, so a test and the install
    acceptance check can drive it without turning anything on.
    """
    async with sessions() as session:
        ids = (await session.execute(armed_ids(limit))).scalars().all()
    readers = StoredPrincipals(sessions) if principals is None else principals
    loader = StoredEntitlements(sessions) if entitlements is None else entitlements
    ran: list[runs.Ran] = []
    for one in ids:
        done = await run_changes_of(sessions, one, now=now, principals=readers, entitlements=loader)
        if done:
            ran.extend(done)
    return ran
