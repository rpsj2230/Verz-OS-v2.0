"""Starting and stopping an installed automation from the agent's Automations tab.

`brain.console.automation_gallery` installs an automation paused and says that starting it is a
schedule change somebody else approves. `brain.console.agent_automations` holds the rules that
change needs: `may_change_schedule`, `resume`, `pause`, and who may see an automation at all. This
module is the two controls those rules were written for, and decides nothing they already decide.

**Starting is the gated direction and needs somebody who is not the automation.** A start moves an
automation from nothing to a run at its cadence, which `CHANGING_WHEN_SOMETHING_RUNS_UNWATCHED_IS_
TRUSTING_IT_FURTHER` makes a gated change, and `may_change_schedule` refuses an approver who is the
principal it runs as. So a start needs `AUTOMATION_AUTHORITY` in a scope matching the automation's
agent, task and principal, held by somebody else. See
`A_START_IS_APPROVED_BY_SOMEBODY_IT_DOES_NOT_RUN_AS`.

**Stopping is the fail-safe direction and needs no approval.** The person it runs as may always stop
it, and so may anybody holding the authority over it. That is `brain.ops.halt.
THE_GUARDED_ACT_IS_RESUME_AND_NEVER_STOP` one level down, and a stop that waited for an approver
would be a stop nobody can make during the week an automation is wrong.

**A task this install cannot perform cannot be started.** `brain.ops.automation_run.TASKS` says
what each still needs, and a start of one would be refused by the first run and paused, which reads
as a start that worked and an automation that broke. The control is withheld and the sentence
saying what the task needs is shown instead.

**Confirmed means the write carries what was shown.** `ScheduleShown.confirmation` is a digest over
the automation, whose grants it runs at, its cadence, its next run now and the one the change would
leave, and the route recomputes it at the moment of the write, as `automation_gallery.
InstallPreview` does. A start confirmed an hour before the cadence's hour went by is refused and
shown again rather than started at a next run nobody saw.

**Audited by the row that says why.** The change is written as `agent.automation_schedule`, whose
trigger appends the ledger entry in the same transaction; see
`migrations/versions/0067_automation_run.py`.

Task ids: M39.6.1.5, M39.6.2.2, M38.2.2.5
"""

from __future__ import annotations

import enum
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.agents.model import AgentRecord, entitlement_ceiling
from brain.console.agent_automations import (
    Automation,
    SchedulerChange,
    may_change_schedule,
    pause,
    resume,
)
from brain.console.automation_gallery import AUTOMATION_AUTHORITY, Cadence
from brain.core.entitlement import EntitlementSet
from brain.ops.automation_run import TaskDeclaration, next_run_after, task_declaration

# ------------------------------------------------------------------ written-down reasons
#: Why a start needs somebody other than the automation's own principal.
A_START_IS_APPROVED_BY_SOMEBODY_IT_DOES_NOT_RUN_AS: Final = (
    "Starting an automation moves it from doing nothing to acting at its cadence with nobody "
    "watching, which is a gated change, and an automation whose own principal approved its start "
    "is an automation approving itself. So a start needs the automation authority over this "
    "agent, task and person, held by somebody the automation does not run as."
)

#: What a start that cannot happen because the task is unbuilt says, before what it needs.
THIS_OUTCOME_CANNOT_RUN_ON_THIS_INSTALL: Final = (
    "This install cannot perform this outcome yet, so it cannot be started. What it needs:"
)


class ScheduleControlError(Exception):
    """A start or a stop was asked for in a shape that cannot be written."""


class NotConfirmedError(ScheduleControlError):
    """The change carried no confirmation of what was shown, or a stale one."""


class Direction(enum.StrEnum):
    START = "start"
    STOP = "stop"


def scope_row(one: Automation) -> dict[str, str]:
    """The fields the authority's scope is matched against: `agent_automations._scope_row`'s."""
    return {"agent_id": one.agent_id, "task": one.task, "principal_id": one.runs_as.id}


def holds_authority(one: Automation, reader: EntitlementSet, now: datetime) -> bool:
    """Whether this reader holds the automation authority in a scope over this automation."""
    scope = reader.scope_for(AUTOMATION_AUTHORITY, now)
    return scope is not None and scope.matches(scope_row(one))


def cannot_start_because(one: Automation, agent: AgentRecord, now: datetime) -> str | None:
    """The sentence saying why this automation cannot be started, or None if nothing stops it.

    Two facts that need nobody's grants: whether the install can perform the task, and whether
    the agent's ceiling admits what the task reads. The second is `A_CEILING_THAT_CANNOT_READ_IT_
    CANNOT_RUN_IT`; whether the owner still holds the read is the run's question, asked of the
    owner's reach when the run starts, and a start is not a place to read somebody else's grants.
    """
    declaration: TaskDeclaration | None = task_declaration(one.task)
    if declaration is None:
        return f"{THIS_OUTCOME_CANNOT_RUN_ON_THIS_INSTALL} a declaration of what {one.task} reads."
    if declaration.reads is None:
        return f"{THIS_OUTCOME_CANNOT_RUN_ON_THIS_INSTALL} {declaration.needs}."
    if entitlement_ceiling(agent).scope_for(declaration.reads, now) is None:
        return f"{THIS_AGENT_CANNOT_READ_WHAT_IT_READS} {declaration.reads.value}."
    return None


#: What a start refused by the agent's ceiling says, before the capability.
THIS_AGENT_CANNOT_READ_WHAT_IT_READS: Final = (
    "This agent's ceiling does not admit what this outcome reads, so every run of it would be "
    "refused. It needs the agent to be allowed"
)

#: Why the ceiling is asked before a start.
A_CEILING_THAT_CANNOT_READ_IT_CANNOT_RUN_IT: Final = (
    "A run's reach is its owner's narrowed by the agent's ceiling, so an agent whose ceiling does "
    "not name what a task reads refuses every run of that task, whoever owns it. Starting one "
    "would be a start that the first run undoes, which reads as an automation that broke."
)


def may_start(
    one: Automation,
    reader: EntitlementSet,
    *,
    agent: AgentRecord,
    becomes: datetime,
    now: datetime,
) -> bool:
    """Whether this reader may start this automation at `becomes`. See the module docstring."""
    if not one.paused or cannot_start_because(one, agent, now) is not None:
        return False
    if not holds_authority(one, reader, now):
        return False
    return may_change_schedule(one, becomes=becomes, approved_by=reader.principal_id)


def may_stop(one: Automation, reader: EntitlementSet, *, now: datetime) -> bool:
    """Whether this reader may stop this automation: its own principal, or the authority over it."""
    if one.paused:
        return False
    return one.runs_as.id == reader.principal_id or holds_authority(one, reader, now)


@dataclass(frozen=True)
class ScheduleShown:
    """Everything a person confirms before a start or a stop, and the digest over it."""

    direction: Direction
    automation: Automation
    cadence: Cadence
    #: The next run the change leaves: the cadence's next instant for a start, None for a stop.
    becomes: datetime | None

    def __post_init__(self) -> None:
        if (self.direction is Direction.START) != (self.becomes is not None):
            msg = "a start leaves a next run and a stop leaves none"
            raise ScheduleControlError(msg)

    @property
    def confirmation(self) -> str:
        one = self.automation
        shown = {
            "direction": self.direction.value,
            "automation_id": one.automation_id,
            "agent_id": one.agent_id,
            "name": one.name,
            "runs_as": one.runs_as.id,
            "task": one.task,
            "cadence": self.cadence.words(),
            "next_run_at": None if one.next_run_at is None else one.next_run_at.isoformat(),
            "becomes": None if self.becomes is None else self.becomes.isoformat(),
        }
        encoded = json.dumps(shown, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def shown_start(one: Automation, cadence: Cadence, *, now: datetime) -> ScheduleShown:
    """What starting this automation now would leave: its cadence's next instant after `now`."""
    return ScheduleShown(
        direction=Direction.START,
        automation=one,
        cadence=cadence,
        becomes=next_run_after(cadence, now),
    )


def shown_stop(one: Automation, cadence: Cadence) -> ScheduleShown:
    """What stopping this automation would leave: no next run."""
    return ScheduleShown(direction=Direction.STOP, automation=one, cadence=cadence, becomes=None)


def changed(shown: ScheduleShown, *, confirmation: str, guards: str) -> SchedulerChange:
    """The change a confirmed request writes, through `agent_automations.resume` or `pause`.

    `shown` is recomputed by the server at the moment of the write, never sent by the client.
    Whether the reader may make it is the route's question, asked first through `may_start` and
    `may_stop`, for `agent_automations.resume`'s reason about deciding and acting separately.
    """
    if not secrets.compare_digest(confirmation, shown.confirmation):
        msg = (
            f"the {shown.direction.value} of {shown.automation.automation_id!r} did not confirm "
            "what would change now"
        )
        raise NotConfirmedError(msg)
    if shown.becomes is None:
        return pause(shown.automation, guards=guards)
    return resume(shown.automation, next_run_at=shown.becomes, guards=guards)
