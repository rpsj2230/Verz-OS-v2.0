"""When the staff sync changes what a person reaches, the automations they own that would lose some
of it are paused and not quietly narrowed (M26.2.3).

`brain.identity.lifecycle.reevaluate_delegations` has said since it was written that a delegation
the delegator can no longer sustain is **suspended and never narrowed**, and nothing called it,
because nothing on this install is a delegation record. Needs-rupash item 216 asks which thing is
one. Under both of the options that name something that exists today (A: automations and deputy
appointments, B: automations only) an **automation a person owns** is one, so this builds exactly
that half and leaves the deputy appointment, which only A names, unbuilt. Option C, a delegation
as an object of its own, is not touched.

**An automation already runs as its owner at `flow_reach`, so a move narrows it whether anybody
decides to or not.** The run after the move is the owner's new reach intersected with the agent's
ceiling, and nothing tells the owner, their administrator or the person reading the report it
produces that last week's report read a department the automation no longer reaches. That is
narrowing by a side effect, the one outcome the lifecycle rule exists to forbid, and it is the
default here. So the sync's Starter pack step, which is where a mover's reach changes, is wrapped:
what each live automation reached is read before the packs are written and again after, and an
automation whose reach after does not cover its reach before is paused with the existing reason
`owner_lost_reach`, through the same store write a person's stop uses. See
`A_MOVE_PAUSES_WHAT_IT_WOULD_NARROW`.

**"Exceeds their reach" is not asked by a second implementation.** `lost_reach` builds the
automation's reach after the move with `agent_automations.automation_reach`, which is
`brain.ops.automation.flow_reach`, and then asks `EntitlementSet.intersect` with `now` what of the
reach before survives it. Whatever the intersection cannot hold is lost. No set arithmetic is
written here, and the call is pinned in `tests/invariants/test_single_implementation.py` as a new
site that passes the instant.

**Resumed only by confirmation, and by the authority the product already requires.** The paused
automation is listed on its owner's Automations page and, through the schedule screen's grant, on
the page of whoever holds authority over it, with a sentence saying the reach changed. It starts
again by the existing confirmed resume, which `automation_schedule.may_start` gives to a person
with the automation authority other than the one it runs as
(`agent_automations.may_change_schedule`, M39.6.2.2: an automation never approves its own
schedule). So the owner cannot restart their own paused automation by pressing a button, and **the
confirmation the lifecycle rule asks of "the delegator" is given by their administrator, not by
them.** That follows the decided schedule rule rather than item 216, and is reported as a question
rather than settled here.

**Rejected: a new pause reason and a new table for reconfirmations.** `owner_lost_reach` is
already a member of the closed vocabulary the database holds as a constraint
(`tables.automation_run.PAUSE_REASONS`), so a new reason would be a migration for a word, and the
schedule row, the ledger entry the trigger appends and the sentence on the page all exist for it.
A table of pending reconfirmations would store a second copy of "this automation has no next run
and was paused for a reach change", which is what `agent.automation_schedule` already says.

**Rejected: pausing only when the owner can no longer read what the task reads.** That is what
`automation_run.admitted_run` already does when a run starts, and it misses the case this exists
for: an owner who moves from one department to another still holds the capability, in a different
scope, so the run goes ahead and reports the new department's figures under last week's name.

**It watches every live automation, not only those of people the roster says moved.** The pack
step retires and gives packs by comparing a roster with what is held, and a reach also changes
when an administrator retires a pack in the same window. Comparing the reach before the step with
the reach after it is the question being asked; a list of movers would be a second, narrower way
of asking it, and would miss every route into a changed reach but the roster's.

**Behind a switch, and the switch gates the door and never traps what it opened.** The watch and
the pause are skipped while `mover_pauses_automations` is off. A listing and a resume never ask
it. See `brain.ops.features_declared.mover_pauses_automations`.

**A failure here never undoes the staff list.** The roster, the heads' reach and the packs are
committed before this runs, in transactions of their own, so a failure is logged by its type and
the automations are left running as they were, which is today's behaviour.

Task ids: M26.2.3
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import one_agent, record_of
from brain.agents.model import AgentRecord
from brain.console.agent_automations import automation_reach, pause
from brain.core.entitlement import EntitlementSet
from brain.core.scope_sql import scope_narrows
from brain.gate.admission import admit
from brain.gate.entitlement_store import StoredEntitlements
from brain.identity.principal_store import StoredPrincipals
from brain.ops.automation_owner import AUTOMATION_ASSURANCE, AUTOMATION_CHANNEL
from brain.ops.automation_run import PausedBecause
from brain.ops.automation_run_store import Listed, StoredAutomationSchedules
from brain.ops.features import is_on
from brain.ops.features_declared.mover_pauses_automations import MOVER_PAUSES_AUTOMATIONS

log = structlog.get_logger()

#: Why a move pauses an automation instead of letting it run at a smaller reach.
A_MOVE_PAUSES_WHAT_IT_WOULD_NARROW: Final = (
    "An automation runs as its owner at the owner's reach now, narrowed by its agent. When the "
    "staff sync moves the owner and the automation would reach less than it did, running it "
    "anyway is narrowing it without anybody having said so, so it is paused and a person with "
    "authority over it confirms it at the new reach before it runs again."
)

#: Why the question is asked of the reach before and after, and not of a list of movers.
THE_QUESTION_IS_WHAT_THE_AUTOMATION_REACHED_AND_REACHES: Final = (
    "Whether an automation lost reach is a fact about its reach before the pack step and its reach "
    "after, whatever changed the owner's grants in between. A roster's list of movers is one way "
    "a reach changes and not the question."
)

#: Why a failure to watch or to pause is logged and swallowed.
A_FAILURE_HERE_NEVER_UNDOES_THE_STAFF_LIST: Final = (
    "The roster, the heads' reach and the packs are committed before this runs, each in a "
    "transaction of its own. A failure to read or to pause is logged by its type and leaves the "
    "automations running as they were, which is what happens while the switch is off."
)

#: The ledger entry's reach digest for a write the sync makes. The sync holds no reach of its own;
#: the all-zero digest is the one the install checks use for the same write.
THE_SYNC_HOLDS_NO_REACH_OF_ITS_OWN: Final = "0" * 32

#: What the run is called in the ledger. The roster's own actor is the one its grants name.
ACTOR_PREFIX: Final = "roster."


def run_reach(owner: EntitlementSet, agent: AgentRecord) -> EntitlementSet:
    """What an automation of this owner, on this agent, reaches. `automation_run.admitted_run`'s
    reach, restated as a function so the question before and after is asked the same way.

    No arithmetic of its own: `automation_reach` is `flow_reach`, and the admission is the
    channel and assurance an automation is held to, so an owner who holds approve does not lend it.
    """
    return automation_reach(admit(owner, AUTOMATION_CHANNEL, AUTOMATION_ASSURANCE), agent)


def lost_reach(before: EntitlementSet, after: EntitlementSet, *, now: datetime) -> bool:
    """Whether the reach `after` fails to cover something the reach `before` had.

    Both are automation reaches (`run_reach`). What of `before` survives `after` is
    `EntitlementSet.intersect`, handed the instant, and a capability the survivor holds in a scope
    that does not contain the old one, or does not hold at all, is lost. Gaining reach alone is
    not a loss: an automation whose owner was promoted is left running.
    """
    survivor = after.intersect(before, now)
    for grant in before.grants:
        kept = survivor.scope_for(grant.capability, now)
        if kept is None or not scope_narrows(grant.scope, kept):
            return True
    return False


@dataclass(frozen=True)
class Watched:
    """One live automation and what it reached before the pack step."""

    listed: Listed
    agent: AgentRecord
    before: EntitlementSet


async def movers_pause_automations(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether a move pauses the mover's automations on this install. Off until turned on.

    Asked before the watch and the pause, and never before a listing or a resume: see
    `brain.ops.features.A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED`.
    """
    async with sessions() as session:
        return await is_on(session, MOVER_PAUSES_AUTOMATIONS)


async def _agents(
    sessions: async_sessionmaker[AsyncSession], agent_ids: Sequence[str]
) -> Mapping[str, AgentRecord]:
    found: dict[str, AgentRecord] = {}
    async with sessions() as session, session.begin():
        for agent_id in sorted(set(agent_ids)):
            row = (await session.execute(one_agent(agent_id))).scalar_one_or_none()
            record = None if row is None else record_of(row)
            if record is not None:
                found[agent_id] = record
    return found


async def watch(
    sessions: async_sessionmaker[AsyncSession], *, now: datetime
) -> tuple[Watched, ...]:
    """Every scheduled automation on an agent that exists, with the reach its owner has now.

    A leaver's is watched too, and left alone by `pause_what_lost_reach`, which asks again whether
    the owner is still here at the moment it writes. A removed automation is watched too and cannot
    be paused: `moving`, the write the console's own stop uses, refuses a removed automation
    whatever it is shown, so a filter here would be a second copy of that guard that no test could
    tell from its absence.

    Empty while the switch is off, and empty (with a log line naming the type) when anything here
    cannot be read: a watch that fails must not stop the pack step it only observes.
    """
    try:
        if not await movers_pause_automations(sessions):
            return ()
        every = [
            one
            for one in await StoredAutomationSchedules(sessions).every()
            if one.automation.next_run_at is not None
        ]
        agents = await _agents(sessions, [one.automation.agent_id for one in every])
        loader = StoredEntitlements(sessions)
        owners: dict[str, EntitlementSet] = {}
        watched: list[Watched] = []
        for one in every:
            agent = agents.get(one.automation.agent_id)
            if agent is None:
                continue
            owner_id = one.automation.runs_as.id
            if owner_id not in owners:
                owners[owner_id] = await loader.load(owner_id, now)
            watched.append(
                Watched(listed=one, agent=agent, before=run_reach(owners[owner_id], agent))
            )
        return tuple(watched)
    except Exception as exc:
        # Broad on purpose, for `A_FAILURE_HERE_NEVER_UNDOES_THE_STAFF_LIST`'s reason, which is
        # the heads' reach's: the roster is committed and this only observes.
        log.warning("mover_automations.watch_unread", error=type(exc).__name__)
        return ()


async def pause_what_lost_reach(
    sessions: async_sessionmaker[AsyncSession],
    watched: Sequence[Watched],
    *,
    source: str,
    trace_id: str,
    now: datetime,
) -> tuple[str, ...]:
    """Pause each watched automation whose reach after the pack step does not cover its reach
    before, and say which. The ids are for the install's own log and the check; no person's
    reach is described.

    Each pause is `agent_automations.pause` written through the console's own
    `StoredAutomationSchedules.change`, which moves the next run only where it is still the one
    read and appends the schedule row whose trigger puts the ledger entry. An automation a person
    stopped, or that a run paused, between the read and the write is left as it is.
    """
    if not watched:
        return ()
    try:
        loader = StoredEntitlements(sessions)
        people = StoredPrincipals(sessions)
        store = StoredAutomationSchedules(sessions)
        now_held: dict[str, EntitlementSet] = {}
        paused: list[str] = []
        for one in watched:
            owner_id = one.listed.automation.runs_as.id
            if await people.live_principal(owner_id) is None:
                # A leaver's automation is awaiting an owner and the runner pauses it as
                # `owner_gone` when it is due. A reach lost to leaving is not a move.
                continue
            if owner_id not in now_held:
                now_held[owner_id] = await loader.load(owner_id, now)
            if not lost_reach(one.before, run_reach(now_held[owner_id], one.agent), now=now):
                continue
            written = await store.change(
                pause(one.listed.automation, guards=one.listed.guards),
                reason=PausedBecause.OWNER_LOST_REACH.value,
                actor=f"{ACTOR_PREFIX}{source}",
                ent_hash=THE_SYNC_HOLDS_NO_REACH_OF_ITS_OWN,
                trace_id=trace_id,
                at=now,
            )
            if written:
                paused.append(one.listed.automation.automation_id)
        return tuple(sorted(paused))
    except Exception as exc:
        # Broad on purpose, as `watch`'s is.
        log.warning("mover_automations.pause_unwritten", error=type(exc).__name__)
        return ()
