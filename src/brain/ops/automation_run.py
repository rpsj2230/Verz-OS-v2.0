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
and this module does not store it: the pause is the scheduler forgetting the automation, which is
what stops its next run. The agent axis has been enforced since M13.7.3, so storing the halt would
now also refuse that agent's questions, which is a wider stop than a failing automation asked for
and is left as a decision rather than made here. See `automation_gaps` in that module.

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

**A task that needs a person says where, and for how long.** A drafting task declares its approval
points on `TaskDeclaration.approvals`, each a step and a window, and `approval_gaps` holds every
window to `brain.orchestration.unattended.window_refusals` against the cadence of each template that
names the task: no longer than the platform's maximum and shorter than the gap between two runs, so
two runs are never waiting on a person at once. A drafting template whose task declares none, and a
task declaring one that no template drafts for, are gaps. Nothing a run does today raises one:
`brain.ops.automation_hold` is what raises a hold through the approvals queue and says when nobody
answered, and it waits for the first performer allowed to draft (needs-rupash 210). See
`AN_APPROVAL_WINDOW_IS_DECLARED_WITH_THE_TASK_AND_HELD_TO_THE_CADENCE`.

Task ids: M39.6.2.1, M39.6.2.3, M38.2.2.5, M17.4.5
"""

from __future__ import annotations

import enum
import hashlib
import re
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
from brain.console.automation_gallery import BUILT_IN, WEEKDAYS, AutomationTemplate, Cadence, Every
from brain.console.questions_view import QUESTION_AUTHORITY
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.principal import Principal
from brain.gate.admission import admit
from brain.ops.automation_owner import AUTOMATION_ASSURANCE, AUTOMATION_CHANNEL
from brain.ops.jobs import JobState
from brain.ops.outbox import EventKind, OutboxEvent
from brain.orchestration.unattended import ApprovalStep, window_refusals

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

#: Why a task's approval windows are declared with it and checked before any automation of it runs.
AN_APPROVAL_WINDOW_IS_DECLARED_WITH_THE_TASK_AND_HELD_TO_THE_CADENCE: Final = (
    "How long a person has to answer is a property of the task and of how often it runs, and both "
    "are known before an automation exists. A window found too long when the first hold is raised "
    "is found at four in the morning with a person's draft already made, so it is found when the "
    "task is declared instead: the window may not outlast the platform's maximum and may not reach "
    "the next run, which would put two runs waiting on one person."
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

#: What a run id looks like, from the two constants it is built with.
RUN_ID_SHAPE: Final = f"{RUN_ID_PREFIX}[0-9a-f]{{{RUN_ID_DIGEST_CHARS}}}"


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
class ApprovalPoint:
    """A point in a task's run where a person has to say yes, and how long they have (M17.4.5).

    The same two facts as `brain.orchestration.unattended.ApprovalStep` less the automation, which a
    task does not have until somebody installs it. `step` builds the step for one automation, and
    in doing so is refused by the step's own constructor for an empty id or a window of nothing.
    """

    step_id: str
    window: timedelta

    def __post_init__(self) -> None:
        self.step("declaration")

    def step(self, automation_id: str) -> ApprovalStep:
        """This point as the step of one automation."""
        return ApprovalStep(step_id=self.step_id, automation_id=automation_id, window=self.window)


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
    #: Where a person has to say yes before the run goes on. Empty for a task that only reads and
    #: tells; required for one a template says drafts. See `approval_gaps`.
    approvals: tuple[ApprovalPoint, ...] = ()

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


#: How long a person has to answer a draft: half a day, so a draft made at the end of one day is
#: answered or gone before the next run, and inside both the platform's maximum and the shortest
#: gap between two runs of any template that drafts.
DRAFT_APPROVAL_WINDOW: Final = timedelta(hours=12)

#: The task an automation a person wrote in words runs. Not a template's, so `task_gaps` does not
#: ask a template to name it, and `brain.console.automation_authoring.AUTHORED_TASK` is this.
INSTRUCTION_TASK: Final = "automation.instruction"

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
    TaskDeclaration(
        task="automation.daily_brief",
        needs=(
            "a calendar, a task list and a mailbox to read as the person it runs as, and a "
            "performer that composes them. No connector of those kinds is read by a scheduled run "
            "yet, so a brief would report that nothing waits"
        ),
    ),
    TaskDeclaration(
        task="automation.deal_capture",
        approvals=(ApprovalPoint(step_id="approve_the_draft", window=DRAFT_APPROVAL_WINDOW),),
        needs=(
            "a group chat to read, a customer-record source to draft against, and a place a "
            "person approves a draft. Nothing drafts a record from a chat, and a draft held for "
            "approval from an unattended run has not yet been shown to reach the right person"
        ),
    ),
    TaskDeclaration(
        task="automation.email_replies",
        approvals=(ApprovalPoint(step_id="approve_the_reply", window=DRAFT_APPROVAL_WINDOW),),
        needs=(
            "a mailbox to read as the person it runs as and a place a drafted reply waits for "
            "them. Nothing drafts a reply, and an unattended run may not call a model until the "
            "owner decides (needs-rupash 210)"
        ),
    ),
    TaskDeclaration(
        task=INSTRUCTION_TASK,
        needs=(
            "an agent run with nobody present. The agent runtime answers a person who asked, and "
            "nothing starts one on a schedule at its owner's reach with every write held, so an "
            "instruction a person wrote is saved and shown and cannot be started yet"
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


def shortest_gap(cadence: Cadence) -> timedelta:
    """The least time between two runs of this cadence: a day for a daily or weekday one, a week
    for a weekly one. Weekday runs are a day apart Monday to Friday and three days over the
    weekend, and the least is the one an approval window must fit inside."""
    return timedelta(days=7) if cadence.every is Every.WEEK else timedelta(days=1)


def approval_gaps(
    declarations: Sequence[TaskDeclaration] = TASKS,
    catalogue: Sequence[AutomationTemplate] = BUILT_IN,
) -> tuple[str, ...]:
    """Every way a task's approval points disagree with the templates that run it (M17.4.5).

    A template that drafts must have a task that declares an approval point, and a task that
    declares one must be a task some template drafts for. Each declared window is held to
    `window_refusals` against the shortest gap of every template naming the task, which is the
    rule a run raising the hold is held to. See
    `AN_APPROVAL_WINDOW_IS_DECLARED_WITH_THE_TASK_AND_HELD_TO_THE_CADENCE`.
    """
    gaps: list[str] = []
    drafting = {one.task for one in catalogue if one.drafts}
    for declaration in declarations:
        if declaration.task in drafting and not declaration.approvals:
            gaps.append(
                f"{declaration.task!r} drafts and declares no point where a person approves"
            )
        if declaration.approvals and declaration.task not in drafting:
            gaps.append(f"{declaration.task!r} declares an approval and no template drafts for it")
        for template in catalogue:
            if template.task != declaration.task:
                continue
            steps = tuple(one.step(template.template_id) for one in declaration.approvals)
            gaps.extend(
                f"{declaration.task!r} on {template.template_id!r}: {reason}"
                for reason in window_refusals(
                    template.template_id, shortest_gap(template.cadence), steps
                )
            )
    return tuple(gaps)


def task_gaps(declarations: Sequence[TaskDeclaration] = TASKS) -> tuple[str, ...]:
    """Every template task with no declaration, and every declaration no template names."""
    named = {one.task for one in BUILT_IN} | {INSTRUCTION_TASK}
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
    gaps.extend(approval_gaps(declarations))
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


def slots_before(cadence: Cadence, before: datetime, count: int) -> tuple[datetime, ...]:
    """The last `count` instants strictly before `before` at which this cadence ran, newest first.

    The mirror of `next_run_after`, over the same `_runs_on`, so a rehearsal replays the slots the
    scheduler would have used and not a second reading of the cadence. At most `7 * count + 1`
    days back are looked at, which covers a weekly cadence however `count` falls.
    """
    if before.tzinfo is None:
        msg = "a naive instant has no hour in UTC to count a cadence back from"
        raise AutomationRunError(msg)
    at = before.astimezone(UTC)
    candidate = at.replace(hour=cadence.hour_utc, minute=0, second=0, microsecond=0)
    if candidate >= at:
        candidate -= timedelta(days=1)
    found: list[datetime] = []
    for _ in range(len(WEEKDAYS) * max(count, 1) + 1):
        if len(found) == count:
            break
        if _runs_on(cadence, candidate.weekday()):
            found.append(candidate)
        candidate -= timedelta(days=1)
    return tuple(found)


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
    armed_at: datetime | None = None,
) -> Afterwards:
    """The automation's next run, or its pause, after one run ended with `outcome`.

    `armed_at` is for an automation a change starts: it has no cadence, and what stays on it
    between runs is the instant it was armed, so a success or a failure under the threshold
    leaves exactly that and only a refusal or the failure pause removes it.

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
        if armed_at is not None:
            return Afterwards(next_run_at=armed_at, paused_because=None)
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
def run_id(automation_id: str, due_at: datetime, change_key: str = "") -> str:
    """One run's id: derived from the automation and the instant it was due, never minted.

    The instant is normalised to UTC in microseconds, so one slot read back through two drivers
    with two offsets is one id. A run a change started also hashes the change's key
    (`brain.ops.automation_event.change_key`), because a source writes a page of records in one
    transaction and so several records share one instant: the instant alone would call the
    second record's run the first's and refuse it. With no key the digest is exactly what it was
    before changes could start a run, so no scheduled slot's id moved.
    """
    if due_at.tzinfo is None:
        msg = "a naive due instant names a different slot on every host"
        raise AutomationRunError(msg)
    slot = due_at.astimezone(UTC).isoformat(timespec="microseconds")
    material = (
        f"{automation_id}\n{slot}" if not change_key else f"{automation_id}\n{slot}\n{change_key}"
    )
    digest = hashlib.sha256(material.encode()).hexdigest()
    return f"{RUN_ID_PREFIX}{digest[:RUN_ID_DIGEST_CHARS]}"


#: The key a change-started run carries when it was read back from the table. The key is hashed
#: into the id and not stored, so a stored run cannot say which change it answered and nobody asks
#: it to: what the constructor guards is a writer building an id wrongly, and a stored id was
#: built by a writer.
CHANGE_NOT_KEPT: Final = "<not kept>"


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
    #: The change that started this run, or empty for a scheduled slot. See `run_id`.
    change_key: str = ""

    def __post_init__(self) -> None:
        if self.change_key == CHANGE_NOT_KEPT:
            if not re.fullmatch(RUN_ID_SHAPE, self.run_id):
                msg = f"{self.run_id!r} is not the shape of a run id"
                raise AutomationRunError(msg)
        elif self.run_id != run_id(self.automation_id, self.due_at, self.change_key):
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
