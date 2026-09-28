"""The Automations module: what every installed automation is now, and who may pause, resume,
reschedule, remove or adopt it.

`brain.console.agent_automations` decides what an automation is and who may see it, and
`brain.console.automation_schedule` who may start or stop one from its agent's page. This module is
the five controls the module page adds, and it decides nothing those two already decide: each
control below is one of theirs with the one fact it adds.

**What an automation is now is its install with its changes folded over it.** `agent.automation`
keeps the install as it was made, and `agent.automation_change` keeps every change after it, insert
only. The owner is the newest adoption's or the installer; the cadence is the newest schedule
change's or the template's; and one removal is final. See `folded` and
`AN_AUTOMATION_IS_ITS_INSTALL_AND_EVERY_CHANGE_SINCE`. Rejected: updating the install in place. It
loses whose automation it was the moment an adoption overwrites it, and `0067`'s update policy is
permissive, so nothing could pin an adopter to the session's own principal.

**Four states and one order.** Removed first, because it is final; then ownerless, because an
automation whose person has gone runs as nobody whatever its schedule says; then paused or running,
which is the next run and nothing else (`agent_automations.
A_PAUSED_FLAG_BESIDE_A_NEXT_RUN_TIME_IS_TWO_FACTS_THAT_DISAGREE`). An ownerless automation that is
still scheduled is stopped by the runner at its next slot, which records why; see
`brain.ops.automation_owner.AN_OWNERLESS_AUTOMATION_STOPS_AND_WAITS`.

**The fail-safe acts need no approval and the widening ones do.** Pausing and removing are
`automation_schedule.may_stop`'s rule: whom it runs as, or the authority over it. Resuming is
`may_start`'s, and a schedule change is `agent_automations.may_change_schedule`'s, because moving
when something runs unwatched is a gated change whichever direction the hour moves: both need the
authority, held by somebody the automation does not run as.

**Adoption is the one way out of waiting, and it leaves the automation paused.** Only an ownerless
automation can be adopted, only by somebody who could have installed it on that agent themselves,
and always in their own name, so it then runs at the adopter's reach. It does not start again by
itself: a start is somebody else's approval, for `automation_schedule.
A_START_IS_APPROVED_BY_SOMEBODY_IT_DOES_NOT_RUN_AS`, and an adoption that restarted it would be the
adopter approving their own automation. See `ADOPTING_IS_LENDING_YOUR_REACH_AND_NOT_STARTING_IT`.

**Confirmed means the write carries what was shown.** `shown` is a digest over the automation as a
reader saw it: its owner, cadence, next run and whether it is removed. The route recomputes it
before any write and the store compares the row again under its lock, so a pause confirmed over an
automation that was adopted in the meantime writes nothing.

Task ids: M27.12.3, M27.15.37, M39.6.1.5
"""

from __future__ import annotations

import enum
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from brain.agents.model import AgentRecord
from brain.console.agent_automations import Automation, may_change_schedule
from brain.console.automation_gallery import AUTOMATION_AUTHORITY, Cadence
from brain.console.automation_schedule import may_start, may_stop
from brain.core.entitlement import EntitlementSet
from brain.ops.automation_run import next_run_after

# ------------------------------------------------------------------ written-down reasons
#: Why an automation is read as its install and its changes.
AN_AUTOMATION_IS_ITS_INSTALL_AND_EVERY_CHANGE_SINCE: Final = (
    "The install row keeps what was installed, and every pause, resume, schedule change, removal "
    "and adoption after it is a row of its own. What the automation is now is the install with "
    "the changes folded over it, so nothing that was true of it is overwritten and every change "
    "has its own ledger entry."
)

#: Why adoption leaves the automation paused.
ADOPTING_IS_LENDING_YOUR_REACH_AND_NOT_STARTING_IT: Final = (
    "Adopting an automation makes it run at the adopter's reach, which is the adopter's own "
    "decision. Starting it again is a separate decision somebody else approves, as every start "
    "is, so an adoption leaves the automation paused and says so."
)

#: Why a removed automation cannot be changed again.
A_REMOVAL_IS_FINAL_AND_KEEPS_ITS_HISTORY: Final = (
    "A removed automation never runs again and cannot be resumed, rescheduled or adopted. Its "
    "runs and its changes stay readable, because the record of what ran in a person's name "
    "outlives the automation."
)


class AutomationsError(Exception):
    """A change or a fold was described in a shape that cannot be written or read."""


class ChangeKind(enum.StrEnum):
    """What one change did. `brain.tables.automation_change.CHANGE_KINDS` restates it."""

    PAUSED = "paused"
    RESUMED = "resumed"
    RESCHEDULED = "rescheduled"
    REMOVED = "removed"
    ADOPTED = "adopted"


class State(enum.StrEnum):
    """Where an automation stands now. Derived, never stored."""

    RUNNING = "running"
    PAUSED = "paused"
    OWNERLESS = "ownerless"
    REMOVED = "removed"


#: The kinds that leave no next run, which `0145` holds as a constraint too.
LEAVES_NO_NEXT_RUN: Final[frozenset[ChangeKind]] = frozenset(
    {ChangeKind.PAUSED, ChangeKind.REMOVED, ChangeKind.ADOPTED}
)


@dataclass(frozen=True)
class Change:
    """One stored change: what it did, by whom, when, and what it left."""

    kind: ChangeKind
    at: datetime
    changed_by: str
    next_run_at: datetime | None = None
    #: The new cadence. Set exactly for a schedule change.
    cadence: Cadence | None = None
    #: The new owner. Set exactly for an adoption, and always the adopter.
    runs_as_id: str | None = None

    def __post_init__(self) -> None:
        if (self.kind is ChangeKind.RESCHEDULED) != (self.cadence is not None):
            msg = "a schedule change carries its cadence, and no other change carries one"
            raise AutomationsError(msg)
        if (self.kind is ChangeKind.ADOPTED) != (self.runs_as_id is not None):
            msg = "an adoption names its new owner, and no other change names one"
            raise AutomationsError(msg)
        if self.runs_as_id is not None and self.runs_as_id != self.changed_by:
            msg = "an automation is adopted in the adopter's own name and nobody else's"
            raise AutomationsError(msg)
        if self.kind in LEAVES_NO_NEXT_RUN and self.next_run_at is not None:
            msg = f"a change of kind {self.kind.value} leaves no next run"
            raise AutomationsError(msg)
        if self.kind is ChangeKind.RESUMED and self.next_run_at is None:
            msg = "a resume leaves a next run"
            raise AutomationsError(msg)


@dataclass(frozen=True)
class Folded:
    """An install with its changes folded over it: whose it is, when it runs, and whether it is
    removed."""

    owner_id: str
    #: None only when the template is gone and no schedule change named a cadence.
    cadence: Cadence | None
    removed: bool
    #: Newest last.
    changes: tuple[Change, ...]


def folded(
    *, installed_as: str, template_cadence: Cadence | None, changes: Sequence[Change]
) -> Folded:
    """What an automation is now: the newest adoption's owner, the newest schedule change's cadence,
    and whether any change removed it. See `AN_AUTOMATION_IS_ITS_INSTALL_AND_EVERY_CHANGE_SINCE`."""
    ordered = tuple(sorted(changes, key=lambda one: one.at))
    owner, cadence, removed = installed_as, template_cadence, False
    for one in ordered:
        if one.runs_as_id is not None:
            owner = one.runs_as_id
        if one.cadence is not None:
            cadence = one.cadence
        if one.kind is ChangeKind.REMOVED:
            removed = True
    return Folded(owner_id=owner, cadence=cadence, removed=removed, changes=ordered)


def state_of(one: Automation, *, removed: bool, owner_live: bool) -> State:
    """Where this automation stands. See the module docstring's order."""
    if removed:
        return State.REMOVED
    if not owner_live:
        return State.OWNERLESS
    return State.PAUSED if one.paused else State.RUNNING


# ------------------------------------------------------------------ who may do what
def may_pause(one: Automation, reader: EntitlementSet, *, removed: bool, now: datetime) -> bool:
    """A running automation, paused by whom it runs as or the authority over it."""
    return not removed and may_stop(one, reader, now=now)


def may_resume(
    one: Automation,
    reader: EntitlementSet,
    *,
    agent: AgentRecord,
    cadence: Cadence | None,
    removed: bool,
    owner_live: bool,
    now: datetime,
) -> bool:
    """A paused automation with an owner, resumed by the authority held by somebody else."""
    if removed or not owner_live or cadence is None:
        return False
    return may_start(one, reader, agent=agent, becomes=next_run_after(cadence, now), now=now)


def holds_authority_as(
    one: Automation, reader: EntitlementSet, principal_id: str, now: datetime
) -> bool:
    """Whether this reader holds the automation authority over this agent and task, for the person
    named as the one it runs as. `automation_schedule.holds_authority` asks it for the owner."""
    scope = reader.scope_for(AUTOMATION_AUTHORITY, now)
    row = {"agent_id": one.agent_id, "task": one.task, "principal_id": principal_id}
    return scope is not None and scope.matches(row)


def may_reschedule(
    one: Automation,
    reader: EntitlementSet,
    *,
    becomes: Cadence,
    removed: bool,
    now: datetime,
) -> bool:
    """A schedule change: the authority over it, held by somebody it does not run as.

    Asked whether the automation is running or paused, because a paused automation's cadence is
    the one a resume will use, and moving it is moving when it runs.
    """
    if removed or not holds_authority_as(one, reader, one.runs_as.id, now):
        return False
    return may_change_schedule(
        one, becomes=next_run_after(becomes, now), approved_by=reader.principal_id
    )


def may_remove(one: Automation, reader: EntitlementSet, *, removed: bool, now: datetime) -> bool:
    """Removed, running or paused, by whom it runs as or the authority over it. The fail-safe
    direction, so it needs no second person."""
    if removed:
        return False
    return one.runs_as.id == reader.principal_id or holds_authority_as(
        one, reader, one.runs_as.id, now
    )


def may_adopt(
    one: Automation,
    reader: EntitlementSet,
    *,
    removed: bool,
    owner_live: bool,
    now: datetime,
) -> bool:
    """An ownerless automation, adopted by somebody who could have installed it themselves.

    The authority in a scope matching the agent, the task and the reader as the person it would
    run as, which is `automation_gallery.may_install`'s question asked of an automation that
    exists. See `ADOPTING_IS_LENDING_YOUR_REACH_AND_NOT_STARTING_IT`.
    """
    if removed or owner_live or one.runs_as.id == reader.principal_id:
        return False
    return holds_authority_as(one, reader, reader.principal_id, now)


# ------------------------------------------------------------------ what was confirmed
def shown(one: Automation, *, cadence: Cadence | None, removed: bool) -> str:
    """The digest a change must carry: the automation as the reader saw it.

    Over the owner, the cadence, the next run and whether it is removed, so a change confirmed over
    an automation that has since been adopted, rescheduled, started, stopped or removed is refused.
    """
    material = {
        "automation_id": one.automation_id,
        "agent_id": one.agent_id,
        "name": one.name,
        "runs_as": one.runs_as.id,
        "task": one.task,
        "cadence": None if cadence is None else cadence.words(),
        # In UTC, so one instant read back through two sessions with two offsets is one digest.
        "next_run_at": (
            None if one.next_run_at is None else one.next_run_at.astimezone(UTC).isoformat()
        ),
        "removed": removed,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def rescheduled_next_run(one: Automation, *, becomes: Cadence, now: datetime) -> datetime | None:
    """The next run a schedule change leaves: the new cadence's next instant while it runs, and
    none while it is paused, because a schedule change is not a resume."""
    return None if one.paused else next_run_after(becomes, now)
