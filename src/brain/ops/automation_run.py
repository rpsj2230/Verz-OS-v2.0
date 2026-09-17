"""Running an installed automation: as whom, at what reach, when next, and what stops it.

`brain.console.automation_gallery` installs an automation paused and `brain.console.
agent_automations` decides what an automation is, who may see it and when a failing one pauses.
Nothing ran one. This module is the decisions a run makes, and `brain.ops.automation_run_store` is
the half that holds a connection and is what the worker's schedule starts. Nothing here reads a
clock, opens a connection or writes a row.

**A run is its owner's, at `flow_reach`, and the owner is read when the run starts.** The reach is
`agent_automations.automation_reach` over the owner's entitlements as the resolver answers them at
the run's instant, admitted at `AUTOMATION_CHANNEL` and `AUTOMATION_ASSURANCE`, which is
`brain.ops.automation.flow_reach` over the owner and the agent's ceiling. There is no arithmetic
here and no copy of the owner's grants anywhere: a grant deleted at noon is absent from the run at
one. See `A_RUN_IS_ITS_OWNERS_AT_THE_INSTANT_IT_STARTS`.

**An owner who cannot run it runs nothing, and the automation stops with the reason.** Four ways,
decided in this order: the owner is no longer a live principal, the agent is gone or not enabled,
the task has no performer on this install, or the run's reach does not hold what the task reads.
Each is recorded as a refused run and pauses the automation with a closed reason code. Rejected:
refusing the run and leaving the automation scheduled. It would be refused on every cadence for
ever, which is a schedule that is permanently on time and permanently doing nothing, and the
owner would be told about it by nothing. See `AN_AUTOMATION_ITS_OWNER_CANNOT_RUN_STOPS`.

**The reach test is asked of the run's reach and never of the owner's own.** An owner who holds
what the task reads and whose agent's ceiling no longer admits it is exactly as unable to run it
as an owner who lost the grant, and asking the owner's reach alone would run the task at a reach
that then holds nothing, which reads as a quiet week rather than a stopped automation.

**A failure pauses at `agent_automations.FAILURES_BEFORE_PAUSE`, through `failure_pause`.** The
threshold and the notice are that module's, so this module decides only how many consecutive
failures a run brings the count to. What `failure_pause` also builds is a halt scoped to the agent,
and it is not stored: `brain.ops.halt.ENFORCED_AXES` enforces no agent axis, so storing it would be
a halt that reports itself in force and refuses nothing. See `automation_gaps` in that module.

**A slot runs once.** The run's id is derived from the automation and the instant it was due, so a
second worker, a retried tick or a run whose transaction was rolled back and picked up again writes
the same id, and the table's key refuses the second. See `run_id`.

**The next run is the cadence's next instant after the run, not after the slot.** A worker that
was down for three days finds the automation due once and runs it once; deriving the next run from
the slot would fire it once for every missed day, one tick apart, which is
`agent_automations.resume`'s argument about a resumed automation arriving from the scheduler's side.

**What a run sends leaves through the outbox, and the outbox leaves through `issue_once`.** A
finished run is recorded as an `automation.run_finished` event in the transaction that records the
run, and `brain.ops.webhook_delivery` sends it through `issue_once` on the worker's schedule.
Rejected: calling `issue_once` from the run itself. Its ledger commits on its own connection
before the effect and the run's transaction commits after, so a run rolled back after its effect
either loses the effect or tells somebody about a run that was never recorded, and the outbox is
the construction this repository already uses to make the two one fact. See
`WHAT_A_RUN_SENDS_LEAVES_WITH_THE_RUN_OR_NOT_AT_ALL`.

**Of the product's four automation templates, one has a performer.** `TASKS` says for each either
what it reads or what it still needs, and a task that cannot run refuses to start: see
`brain.automation_schedule_routes`. The three unbuilt ones are named work rather than runs that
report nothing, for `brain.ops.schedule_runner.
A_SCHEDULER_WITH_NOTHING_TO_RUN_IS_HONEST_AND_A_SCHEDULER_THAT_PRETENDS_IS_NOT`'s reason.

Task ids: M39.6.2.1, M39.6.2.3, M38.2.2.5
"""

from __future__ import annotations

import enum
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Final

from brain.agents.model import AgentRecord
from brain.console.agent_automations import (
    FAILURES_BEFORE_PAUSE,
    Automation,
    AutomationRun,
    OwnerNotice,
    automation_reach,
    failure_pause,
)
from brain.console.automation_gallery import BUILT_IN, WEEKDAYS, Cadence, Every
from brain.console.questions_view import QUESTION_AUTHORITY
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.principal import Principal
from brain.gate.admission import admit
from brain.ops.automation_owner import AUTOMATION_ASSURANCE, AUTOMATION_CHANNEL
from brain.ops.jobs import JobState
from brain.ops.outbox import EventKind, OutboxEvent

# ------------------------------------------------------------------ written-down reasons
#: Why nothing about the owner's reach is kept between runs.
A_RUN_IS_ITS_OWNERS_AT_THE_INSTANT_IT_STARTS: Final = (
    "An automation runs as the person who installed it, at what that person may reach when the "
    "run starts, narrowed by the agent's ceiling through flow_reach. Nothing about the owner's "
    "grants is stored beside the automation, so a grant deleted before a run is absent from it "
    "and the run can never reach more than its owner holds now."
)

#: Why a refused run pauses the automation instead of waiting for the next slot.
AN_AUTOMATION_ITS_OWNER_CANNOT_RUN_STOPS: Final = (
    "An owner who has gone, an agent that is not enabled, a task with no performer and a reach "
    "that no longer holds what the task reads each refuse the run. Leaving the automation "
    "scheduled would refuse it on every slot for ever while every screen said it was scheduled, "
    "so the refusal is recorded as a run and the automation is paused with the reason, and "
    "starting it again is a decision somebody makes after reading why it stopped."
)

#: Why the run's effect is an outbox event and not a call of its own through the door.
WHAT_A_RUN_SENDS_LEAVES_WITH_THE_RUN_OR_NOT_AT_ALL: Final = (
    "A finished run is written as an outbox event in the transaction that writes the run, so the "
    "event exists exactly when the run does, and the worker's outbox dispatch sends it through "
    "issue_once under the delivery's key. A call through issue_once from inside the run would "
    "commit its ledger record on another connection before the run commits, and a run rolled "
    "back afterwards would have sent something about a run nobody can find."
)

#: The actor a run's writes are attributed to. The ledger's identifier grammar, and not a person.
RUNNER_ACTOR: Final = "automation-runner"

#: How far back a weekly report reads. A week, because every template reporting over a period
#: says "this week" in its outcome.
REPORT_PERIOD: Final = timedelta(days=7)

#: The entity a finished run's event names, in `brain.core.envelope.OBJECT_NAME_PATTERN`.
RUN_ENTITY: Final = "automation_run"

#: The prefix on a run's id, which is also its event's id.
RUN_ID_PREFIX: Final = "run_"

#: Hex characters of the digest a run id carries. 128 bits, well inside an event id's width.
RUN_ID_DIGEST_CHARS: Final = 32


class AutomationRunError(Exception):
    """A run was described in a shape that would run at the wrong reach or be recorded wrongly."""


class RunOutcome(enum.StrEnum):
    """How one run ended. Closed, and every member is terminal."""

    #: The task ran at the run's reach and its result was recorded.
    SUCCEEDED = "succeeded"
    #: The task raised. Counts towards the failure pause.
    FAILED = "failed"
    #: Nothing ran, for a reason in `PausedBecause`. Pauses at once.
    REFUSED = "refused"


class PausedBecause(enum.StrEnum):
    """Why an automation has no next run. Closed, and stored beside the empty next run."""

    #: A person stopped it from the Automations tab.
    STOPPED = "stopped"
    #: It failed `FAILURES_BEFORE_PAUSE` runs in a row.
    FAILED_REPEATEDLY = "failed_repeatedly"
    #: Its owner is no longer a live principal.
    OWNER_GONE = "owner_gone"
    #: Its agent is gone, disabled or archived.
    AGENT_UNAVAILABLE = "agent_unavailable"
    #: Its task has no performer on this install.
    TASK_UNBUILT = "task_unbuilt"
    #: The run's reach does not hold what the task reads.
    OWNER_LOST_REACH = "owner_lost_reach"


#: The reasons a run is refused before anything is read, as against the two a person or a
#: failure count produces.
REFUSALS: Final[frozenset[PausedBecause]] = frozenset(
    {
        PausedBecause.OWNER_GONE,
        PausedBecause.AGENT_UNAVAILABLE,
        PausedBecause.TASK_UNBUILT,
        PausedBecause.OWNER_LOST_REACH,
    }
)

#: How each outcome reads as a job state, for `agent_automations.AutomationRun`. A refusal is a
#: known and final reason, which is what `JobState.FAILED` says and `DEAD_LETTER` does not.
JOB_STATE_OF: Final = MappingProxyType(
    {
        RunOutcome.SUCCEEDED: JobState.SUCCEEDED,
        RunOutcome.FAILED: JobState.FAILED,
        RunOutcome.REFUSED: JobState.FAILED,
    }
)


# ------------------------------------------------------------------ the tasks
@dataclass(frozen=True)
class TaskDeclaration:
    """One automation task: what its run reads, or what it still needs before it can run.

    Exactly one of the two, so a task cannot read as runnable and unbuilt at once, which is
    `brain.ops.schedule_runner.Runner`'s construction.
    """

    task: str
    #: What the run's reach must hold for the task to run at all. None when it cannot run.
    reads: Capability | None = None
    #: What still has to exist before it can run, empty when it can.
    needs: str = ""

    def __post_init__(self) -> None:
        if (self.reads is None) == (not self.needs.strip()):
            msg = (
                f"{self.task!r} must say either what it reads or what it still needs, and not "
                "both, or it reads as runnable and unbuilt at once"
            )
            raise AutomationRunError(msg)

    @property
    def runnable(self) -> bool:
        return self.reads is not None


#: Every task the product's templates name, and whether this install can run it.
TASKS: Final[tuple[TaskDeclaration, ...]] = (
    TaskDeclaration(task="automation.unanswered_questions", reads=QUESTION_AUTHORITY),
    TaskDeclaration(
        task="automation.work_summary",
        needs=(
            "which agent each question was asked of. ops.question_asked records the person, the "
            "channel and the department and no agent, so this agent's week cannot be told from "
            "anybody else's"
        ),
    ),
    TaskDeclaration(
        task="automation.source_freshness",
        needs=(
            "a record of when each source was last read successfully. Nothing on an install "
            "stores a connector's last completed sync for a run to compare with the clock"
        ),
    ),
    TaskDeclaration(
        task="automation.approvals_waiting",
        needs=(
            "a reach that may be told what waits on a person. A held action is offered only to "
            "a reach holding its approve capability, and an automation is admitted at read only, "
            "so at its own reach the run would find nothing and report that nothing waits"
        ),
    ),
)


def task_declaration(
    task: str, declarations: Sequence[TaskDeclaration] = TASKS
) -> TaskDeclaration | None:
    """The declaration for one task, or None for a task nothing declares."""
    for one in declarations:
        if one.task == task:
            return one
    return None


def task_gaps(declarations: Sequence[TaskDeclaration] = TASKS) -> tuple[str, ...]:
    """Every template task with no declaration, and every declaration no template names."""
    named = {one.task for one in BUILT_IN}
    declared = [one.task for one in declarations]
    gaps = [
        f"{task!r} is a template's task and nothing declares it"
        for task in sorted(named)
        if task not in declared
    ]
    gaps.extend(
        f"{task!r} is declared twice" for task in sorted(set(declared)) if declared.count(task) > 1
    )
    gaps.extend(
        f"{task!r} is declared and no template names it" for task in sorted(set(declared) - named)
    )
    return tuple(gaps)


# ------------------------------------------------------------------ the cadence
def next_run_after(cadence: Cadence, after: datetime) -> datetime:
    """The first instant strictly after `after` at which this cadence runs, in UTC.

    Strictly after, so a run that finished at exactly its hour is not due again at once. At most
    eight candidate days are looked at: seven for a weekly cadence and one more because the first
    candidate is today's hour, which may already have passed.
    """
    if after.tzinfo is None:
        msg = "a naive instant has no hour in UTC to count a cadence from"
        raise AutomationRunError(msg)
    at = after.astimezone(UTC)
    candidate = at.replace(hour=cadence.hour_utc, minute=0, second=0, microsecond=0)
    if candidate <= at:
        candidate += timedelta(days=1)
    for _ in range(len(WEEKDAYS) + 1):
        if _runs_on(cadence, candidate.weekday()):
            return candidate
        candidate += timedelta(days=1)
    msg = f"{cadence.words()} names no day it runs on"  # not reachable: `Cadence` refuses it
    raise AutomationRunError(msg)


#: Monday is nought, so Saturday and Sunday are these two.
WEEKEND: Final[frozenset[int]] = frozenset({5, 6})


def _runs_on(cadence: Cadence, weekday: int) -> bool:
    match cadence.every:
        case Every.DAY:
            return True
        case Every.WEEKDAY:
            return weekday not in WEEKEND
        case Every.WEEK:
            return weekday == cadence.weekday


# ------------------------------------------------------------------ the reach
@dataclass(frozen=True)
class Admitted:
    """A run that may start: the reach it runs at and the declaration of what it does."""

    reach: EntitlementSet
    declaration: TaskDeclaration


def admitted_run(
    automation: Automation,
    *,
    owner: Principal | None,
    owner_entitlements: EntitlementSet,
    agent: AgentRecord | None,
    now: datetime,
    declarations: Sequence[TaskDeclaration] = TASKS,
) -> Admitted | PausedBecause:
    """The reach this run starts at, or why it may not start. See the module docstring's order.

    `owner` is the principal the automation runs as, read from the directory for this run, and
    None when it is not a live principal there. `owner_entitlements` is the resolver's answer for
    that id at `now`. Either belonging to somebody else is a wiring fault and raises, because
    answering it would run one person's automation at another's reach.
    """
    if owner_entitlements.principal_id != automation.runs_as.id:
        msg = (
            f"{automation.automation_id!r} runs as {automation.runs_as.id!r} and was handed the "
            f"entitlements of {owner_entitlements.principal_id!r}"
        )
        raise AutomationRunError(msg)
    if owner is not None and owner.id != automation.runs_as.id:
        msg = f"{automation.automation_id!r} was handed the principal record of {owner.id!r}"
        raise AutomationRunError(msg)
    if owner is None or not owner.is_active(now):
        return PausedBecause.OWNER_GONE
    if agent is None or agent.agent_id != automation.agent_id or not agent.is_selectable:
        return PausedBecause.AGENT_UNAVAILABLE
    declaration = task_declaration(automation.task, declarations)
    if declaration is None or declaration.reads is None:
        return PausedBecause.TASK_UNBUILT
    reach = automation_reach(
        admit(owner_entitlements, AUTOMATION_CHANNEL, AUTOMATION_ASSURANCE), agent
    )
    if reach.scope_for(declaration.reads, now) is None:
        return PausedBecause.OWNER_LOST_REACH
    return Admitted(reach=reach, declaration=declaration)


# ------------------------------------------------------------------ after a run
@dataclass(frozen=True)
class Afterwards:
    """What one run leaves the automation with: a next run, or a reason it has none.

    Exactly one of the two, which is `agent_automations.
    A_PAUSED_FLAG_BESIDE_A_NEXT_RUN_TIME_IS_TWO_FACTS_THAT_DISAGREE` at the point of writing.
    `notice` is carried when the pause is the failure pause, so whatever writes that pause is
    holding what its owner is told. No channel sends it to a person yet: the store writes the
    reason beside the empty next run, and the Automations tab shows it to whoever may see the
    automation, which `brain.ops.notices` says in the notice's own row.
    """

    next_run_at: datetime | None
    paused_because: PausedBecause | None
    notice: OwnerNotice | None = None

    def __post_init__(self) -> None:
        if (self.next_run_at is None) == (self.paused_because is None):
            msg = "an automation after a run has a next run or a reason it has none, not both"
            raise AutomationRunError(msg)
        if (self.notice is not None) != (self.paused_because is PausedBecause.FAILED_REPEATEDLY):
            msg = "the failure pause carries its owner's notice, and nothing else carries one"
            raise AutomationRunError(msg)


def afterwards(
    automation: Automation,
    *,
    outcome: RunOutcome,
    refused_because: PausedBecause | None,
    failures_before: int,
    cadence: Cadence | None,
    owner_id: str,
    guards: str,
    at: datetime,
) -> Afterwards:
    """The automation's next run, or its pause, after one run ended with `outcome`.

    `failures_before` is how many runs immediately before this one failed. A refusal pauses at
    once with its reason; a failure brings the count to one more and pauses through
    `failure_pause` at its threshold; a success schedules the next slot. `cadence` is None for an
    automation whose template is gone, which can only be refused.
    """
    if (outcome is RunOutcome.REFUSED) != (refused_because is not None):
        msg = "a refused run names why, and a run that was not refused names nothing"
        raise AutomationRunError(msg)
    if refused_because is not None:
        if refused_because not in REFUSALS:
            msg = f"{refused_because.value} is not a reason a run is refused"
            raise AutomationRunError(msg)
        return Afterwards(next_run_at=None, paused_because=refused_because)
    if outcome is RunOutcome.FAILED:
        paused = failure_pause(
            automation,
            consecutive_failures=failures_before + 1,
            owner_id=owner_id,
            at=at,
            guards=guards,
            declared_by=RUNNER_ACTOR,
        )
        if paused is not None:
            return Afterwards(
                next_run_at=None,
                paused_because=PausedBecause.FAILED_REPEATEDLY,
                notice=paused.notice,
            )
    if cadence is None:
        msg = f"{automation.automation_id!r} ran with no cadence to schedule its next run from"
        raise AutomationRunError(msg)
    return Afterwards(next_run_at=next_run_after(cadence, at), paused_because=None)


def failures_in_a_row(outcomes_newest_first: Sequence[RunOutcome]) -> int:
    """How many runs failed immediately before now, stopping at the first that did not.

    A refusal ends the count as a success does: it paused the automation, and a person started it
    again, so what failed before it is not the same run of trouble.
    """
    count = 0
    for one in outcomes_newest_first:
        if one is not RunOutcome.FAILED:
            break
        count += 1
    return count


#: The threshold, restated here only as the bound the count is compared against in a query.
PAUSE_AFTER: Final = FAILURES_BEFORE_PAUSE


# ------------------------------------------------------------------ the record
def run_id(automation_id: str, due_at: datetime) -> str:
    """One slot's run id: derived from the automation and the instant it was due, never minted.

    The instant is normalised to UTC in microseconds, so one slot read back through two drivers
    with two offsets is one id.
    """
    if due_at.tzinfo is None:
        msg = "a naive due instant names a different slot on every host"
        raise AutomationRunError(msg)
    slot = due_at.astimezone(UTC).isoformat(timespec="microseconds")
    digest = hashlib.sha256(f"{automation_id}\n{slot}".encode()).hexdigest()
    return f"{RUN_ID_PREFIX}{digest[:RUN_ID_DIGEST_CHARS]}"


@dataclass(frozen=True)
class RunRecord:
    """One run as it is written: which slot, as whom, how it ended, and what it found.

    `result` is the task's lines at the run's reach and is empty for a run that did not succeed.
    `reason` is set exactly when the run was refused. `ent_hash` is the run reach's digest, and
    None for a run refused before a reach was computed.
    """

    run_id: str
    automation_id: str
    agent_id: str
    principal_id: str
    due_at: datetime
    started_at: datetime
    finished_at: datetime
    outcome: RunOutcome
    reason: PausedBecause | None = None
    ent_hash: str | None = None
    result: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.run_id != run_id(self.automation_id, self.due_at):
            msg = f"{self.run_id!r} is not the id of {self.automation_id!r}'s slot"
            raise AutomationRunError(msg)
        if (self.outcome is RunOutcome.REFUSED) != (self.reason is not None):
            msg = "a run carries a reason exactly when it was refused"
            raise AutomationRunError(msg)
        if self.result and self.outcome is not RunOutcome.SUCCEEDED:
            msg = "only a run that succeeded has a result, and a failure's text is nobody's to keep"
            raise AutomationRunError(msg)
        if self.finished_at < self.started_at:
            msg = "a run cannot finish before it started"
            raise AutomationRunError(msg)

    def as_history(self) -> AutomationRun:
        """The run as `agent_automations.history` reads one."""
        return AutomationRun(
            automation_id=self.automation_id,
            at=self.finished_at,
            state=JOB_STATE_OF[self.outcome],
            principal_id=self.principal_id,
        )


def run_event(record: RunRecord) -> OutboxEvent:
    """The outbox event a finished run is written with. Identifiers only.

    The event id is the run id, so a run written twice is one event, and the attributes name the
    automation, its agent and the outcome, never the result and never the person.
    """
    return OutboxEvent(
        event_id=record.run_id,
        kind=EventKind.AUTOMATION_RUN_FINISHED,
        entity=RUN_ENTITY,
        record_id=record.run_id,
        occurred_at=record.finished_at,
        attributes=MappingProxyType(
            {
                "automation_id": record.automation_id,
                "agent_id": record.agent_id,
                "outcome": record.outcome.value,
            }
        ),
    )
