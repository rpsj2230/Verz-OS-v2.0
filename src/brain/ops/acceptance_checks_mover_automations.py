"""The install acceptance check for what a move does to the automations a person owns.

`brain.ops.mover_automations` reads what each live automation reaches before the staff sync's
Starter pack step and again after it, and pauses the ones that would reach less. **This check does
the same three things with the functions the run calls**, against the install's own schema: it gives
two people the pack over their department, installs an automation of each on one agent, moves one of
them to the other department with the same pack step, and asks what the run's pause does. The
person who stayed is the positive half: a check that paused every automation would pass the mover's
half on its own.

**The switch is turned on inside the check's transaction and rolled back with it.** The capability
ships off, so an install that has not agreed to it is not touched by this check any more than by the
run; the check turns it on for its own reserved people to ask whether the capability works, not
whether this install has chosen it.

**An install with no Starter pack says so**, as `acceptance_checks_joiner_mover_leaver` does, since
the pack is what changes a mover's reach on a real install.

Rejected: calling the whole scheduled run, which reads a directory with a credential and would send
a real request to the install's staff source from a check. The two functions around the pack step
are the new behaviour; the pack step is the one the other checks already drive.

Task ids: M26.2.3
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from sqlalchemy import insert, select, text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import SET_UP_REACH, Harness
from brain.tables.audit import attributed_to

#: Where this module's checks stand on the Install page, just after the joiner, mover and leaver
#: checks it reuses the pack step of. See `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_
#: ITSELF`.
CHECK_ORDER: Final = 1801

A, B = RESERVED_DEPARTMENTS

#: Said when no template names a task this install can run.
NO_TASK_TO_AUTOMATE: Final = (
    "no automation template names a task this install can run, so an automation of a person's "
    "cannot be installed to ask what a move does to it"
)


#: Said when the install has no Starter pack to give. Written out here rather than imported from
#: the joiner check, because a reason a check raises has to be a literal in its own module.
NO_STARTER_PACK_TO_GIVE: Final = (
    "this install has no live Starter pack the staff sync can give, which the application writes "
    "on its first start and an administrator may have retired, so what a joiner is given cannot "
    "be asked here"
)


@check(
    leaves=("M26.2.3",),
    sentence=(
        "When the staff sync's Starter pack step moves a person to another department, the "
        "automation they own that would reach less is paused with a reason the Automations page "
        "reads and a schedule row written by the roster, and it is listed with no next run; the "
        "automation of a person who did not move keeps its next run."
    ),
)
async def a_mover_s_automation_is_paused_and_a_stayer_s_is_not(h: Harness) -> None:
    from brain.console.automation_gallery import BUILT_IN
    from brain.ops.acceptance_checks_accounts import _joined
    from brain.ops.acceptance_checks_agent_reach import _agent
    from brain.ops.acceptance_checks_joiner_mover_leaver import (
        _give,
        _listed,
        _roster,
    )
    from brain.ops.automation_owner_store import PRINCIPAL_SETTING
    from brain.ops.automation_run import PausedBecause, task_declaration
    from brain.ops.automation_run_store import StoredAutomationSchedules
    from brain.ops.features import switch
    from brain.ops.features_declared.mover_pauses_automations import MOVER_PAUSES_AUTOMATIONS
    from brain.ops.mover_automations import pause_what_lost_reach, watch
    from brain.ops.starter_pack_store import the_starter_pack
    from brain.tables.agent_automation import AgentAutomationRow

    runnable = [
        one
        for one in BUILT_IN
        if (task := task_declaration(one.task)) is not None and task.reads is not None
    ]
    if not runnable:
        raise CheckNotRunError(NO_TASK_TO_AUTOMATE)
    template = runnable[0]
    if (await h.execute(the_starter_pack())).first() is None:
        raise CheckNotRunError(NO_STARTER_PACK_TO_GIVE)

    await h.found_departments()
    mover, stayer = h.principal(A, "mover"), h.principal(A, "stayer")
    for pid in (mover, stayer):
        await h.person(pid, department=A)
        await _joined(h, pid)
    agent_id = await _agent(h, mover, "movers", ("read:knowledge",))
    due = h.now + timedelta(days=1)
    ids = {pid: f"acceptance-{h.run}-{index}" for index, pid in enumerate((mover, stayer))}
    for pid, automation_id in ids.items():
        await h.execute(
            *h.attributed(pid),
            text("SELECT set_config(:name, :value, true)").bindparams(
                name=PRINCIPAL_SETTING, value=pid
            ),
            insert(AgentAutomationRow).values(
                automation_id=automation_id,
                agent_id=agent_id,
                name=template.name,
                runs_as_id=pid,
                task=template.task,
                next_run_at=due,
                guards=template.guards,
                template_id=template.template_id,
                template_version=template.version,
                installed_by=pid,
            ),
        )

    await _give(h, _roster(_listed(h, mover, A), _listed(h, stayer, A)))
    async with h.sessions() as session:
        for statement in attributed_to(
            actor_id=h.actor, ent_hash=SET_UP_REACH, trace_id=h.trace_id
        ):
            await session.execute(statement)
        await switch(session, MOVER_PAUSES_AUTOMATIONS, on=True, by=h.actor)
        await session.commit()

    watched = await watch(h.sessions, now=h.now)
    if not {ids[mover], ids[stayer]} <= {one.listed.automation.automation_id for one in watched}:
        raise CheckFailedError("the pack step's watch did not see an automation of a live person")

    # The next night: the list moves one of them. Nothing else changes between the two reads.
    await _give(h, _roster(_listed(h, mover, B), _listed(h, stayer, A)))
    paused = await pause_what_lost_reach(
        h.sessions, watched, source="acceptance", trace_id=h.trace_id, now=h.now
    )
    if ids[mover] not in paused:
        raise CheckFailedError("an automation whose owner moved to another department kept running")
    if ids[stayer] in paused:
        raise CheckFailedError("an automation whose owner did not move was paused")

    async def next_run(automation_id: str) -> object:
        found = await h.execute(
            select(AgentAutomationRow.next_run_at).where(
                AgentAutomationRow.automation_id == automation_id
            )
        )
        return found.scalar_one()

    if await next_run(ids[mover]) is not None:
        raise CheckFailedError("a paused automation still had a next run")
    if await next_run(ids[stayer]) != due:
        raise CheckFailedError("the automation of a person who did not move lost its next run")
    detail = await StoredAutomationSchedules(h.sessions).one(ids[mover])
    if detail is None or detail.listed.stopped_because != PausedBecause.OWNER_LOST_REACH.value:
        raise CheckFailedError("a paused mover's automation was not listed with its reason")
    if not detail.schedule or not detail.schedule[-1].changed_by.startswith("roster."):
        raise CheckFailedError("the pause was not recorded as the roster's, with a schedule row")
