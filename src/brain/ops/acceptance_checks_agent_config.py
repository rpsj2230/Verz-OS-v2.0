"""Install checks for what is attached to an agent from its page: a group chat, and an automation
that fails.

An agent's page lists the group chats the bot is in on the surfaces the agent answers on and the
steward installs the agent into one (`brain.agent_group_routes`). The unit tests run over a stub
store. What they cannot show is that, on an install, over the product's own tables and routes, an
agent that answers on a surface declaring group installation is offered the rooms the vendor said
the bot is in, installs into one, leaves the room unoffered to anything else, is refused a room
already taken and a surface that has no groups, and is taken out again, and that somebody who may
not switch the agent's channels is answered as the agent that does not exist.

**The room is the check's own, and nothing is sent to it.** A room exists here exactly when the
vendor said the bot joined it (`StoredGroupInstalls.note`, the call the events route makes from a
signed request). The check notes one of a name nothing else holds, in its rolled-back transaction,
so no real room can be installed into and no message is sent to any.

**The surface is asked of the product's declarations and not named here.** The check takes the
first surface whose adapter declares `Feature.GROUP_INSTALL`, and a surface that does not for the
refusal, so a surface gaining or losing the feature moves the check with it; an install shipping
no surface of either kind says so by not being run.

**A failing automation is paused and its steward is told, over a failure the check makes up.**
`brain.ops.automation_run.afterwards` decides what one failed run brings an automation to, and
`brain.ops.automation_run_store.run_one` writes what it decides. A run only fails when the task it
performs raises, and the one task this install can run does not, so no honest install produces the
failure; the check hands the decision the count of failures before this one, exactly as `run_one`
does, and then writes the pause as `run_one` writes it, as the runner, in the worker's role. What
is proved is the product's own decision and its own record: one failure short of the threshold
pauses nothing, the failure that reaches it pauses with the reason `failed_repeatedly` and a
notice addressed to the agent's steward, and the web process's own read finds that pause for that
steward and composes the one sentence they are told. **Nothing is sent**: the steward is a
reserved person with no chat, so the check composes the sentence and tells nobody. M39.6.2.3
therefore stays in `docs/proof-sweep-holds.json` until a real failing run is shown on an install,
and whether a pause also stops the agent's questions is the owner's item 172, which this check
neither decides nor depends on.

Task ids: M39.2.4.4, M39.6.2.3
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_agent_console import _asking, _console, _readers, _request
from brain.ops.acceptance_run import Harness
from brain.ops.acceptance_workspace import installed_agent

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 892

A, B = RESERVED_DEPARTMENTS

NO_SURFACE_WITH_GROUPS: Final = (
    "no surface this install ships declares group installation, so there is no group chat an "
    "agent could be installed into"
)
NO_SURFACE_WITHOUT_GROUPS: Final = (
    "every surface this install ships declares group installation, so there is none to be "
    "refused one"
)
THE_ROOM_WAS_NOT_OFFERED: Final = (
    "a room the bot was noted in was not offered to an agent answering on its surface"
)
THE_INSTALL_WAS_NOT_MADE: Final = "an agent's steward could not install it into an offered room"
THE_ROOM_WAS_STILL_OFFERED: Final = "a room with an agent installed was still offered"
A_ROOM_TOOK_A_SECOND_AGENT: Final = "a room that already had an agent took a second"
A_SURFACE_WITHOUT_GROUPS_TOOK_ONE: Final = "an agent was installed on a surface with no groups"
A_COLLEAGUE_INSTALLED: Final = "somebody who may not switch the agent's channels installed it"
THE_REMOVAL_DID_NOT_FREE_THE_ROOM: Final = "an agent taken out of a room did not free the room"


def _surfaces() -> tuple[Any, Any]:
    """The first channel whose surface declares group installation, and one that does not."""
    from brain.agent_routes import declared_channels
    from brain.channels.adapter import Feature

    declared = declared_channels()
    with_groups = [one.channel for one in declared if one.supports(Feature.GROUP_INSTALL)]
    without = [one.channel for one in declared if not one.supports(Feature.GROUP_INSTALL)]
    if not with_groups:
        raise CheckNotRunError(NO_SURFACE_WITH_GROUPS)
    if not without:
        raise CheckNotRunError(NO_SURFACE_WITHOUT_GROUPS)
    return with_groups[0], without[0]


async def _answering_on(h: Harness, steward: str, agent_id: str, *channels: str) -> None:
    """The agent switched on these surfaces through the lifecycle route, as its steward does."""
    from brain.agent_lifecycle_routes import ChannelsAsked, change_agent_channels
    from brain.gate.context import Channel

    now = [Channel.CONSOLE.value]
    done = await change_agent_channels(
        _request(_console(h)),
        agent_id,
        ChannelsAsked(channels=[*now, *channels], expected=now),
        await _asking(h, steward, strong=True),
    )
    if done.status_code != 200:
        raise CheckFailedError("an agent's steward could not switch on a surface that carries it")


def _told(answer: Any) -> dict[str, Any]:
    return dict(json.loads(bytes(answer.body)))


@check(
    leaves=("M39.2.4.4",),
    sentence=(
        "An agent answering on a surface that declares group installation is offered the group "
        "chat the bot was noted in, its steward installs it there and the room is no longer "
        "offered; a second agent is refused that room, a surface with no groups is refused, a "
        "colleague who may not switch its channels is answered as it does not exist, and the "
        "steward takes the agent out and frees the room."
    ),
)
async def an_agent_is_installed_into_a_group_chat_and_taken_out_again(h: Harness) -> None:
    from brain.agent_group_routes import (
        InstallAsked,
        RemovalAsked,
        agent_groups,
        install_agent_in_group,
        remove_agent_from_group,
    )
    from brain.channels.adapter import RoomChange
    from brain.core.errors import Absent
    from brain.ops.acceptance_checks_governance import _traced
    from brain.ops.group_install_store import StoredGroupInstalls

    groups, plain = _surfaces()
    _traced(h)
    await h.found_departments()
    steward, colleague = h.principal(A, "steward"), h.principal(A, "colleague")
    await h.person(steward, department=A, grants=_readers())
    await h.person(colleague, department=A, grants=_readers())
    first = await installed_agent(h, steward, suffix="_first")
    second = await installed_agent(h, steward, suffix="_second")
    # The first agent answers on the surface with no groups as well, so that a refusal there can
    # only be the surface's and never the agent's not answering on it.
    await _answering_on(h, steward, first, groups.value, plain.value)
    await _answering_on(h, steward, second, groups.value)

    room = f"acceptance_{h.run}_{h.word().lower()}"
    # A room the bot is noted in on the surface with no groups too, so that the refusal there can
    # only be that surface's: the store would refuse a room it has not been told of for any reason.
    elsewhere = f"{room}_elsewhere"
    store = StoredGroupInstalls(h.sessions)
    await store.note(
        groups, RoomChange(conversation_id=room, name=f"Acceptance {room}", joined=True), h.now
    )
    await store.note(
        plain, RoomChange(conversation_id=elsewhere, name=f"Acceptance {room}", joined=True), h.now
    )
    request = _request(_console(h))

    async def rooms_offered(agent_id: str) -> set[str]:
        page = await agent_groups(request, agent_id, await _asking(h, steward, strong=True))
        return {one.room_ref for one in page.rooms}

    async def installing(agent_id: str, who: str, channel: Any, ref: str) -> Any:
        return await install_agent_in_group(
            request,
            agent_id,
            InstallAsked(channel=channel, room_ref=ref),
            await _asking(h, who, strong=True),
        )

    if room not in await rooms_offered(first):
        raise CheckFailedError(THE_ROOM_WAS_NOT_OFFERED)

    try:
        await installing(first, colleague, groups, room)
    except Absent:
        pass
    else:
        raise CheckFailedError(A_COLLEAGUE_INSTALLED)

    made = await installing(first, steward, groups, room)
    installed = [one for one in _told(made).get("installs", []) if one["room_ref"] == room]
    if made.status_code != 201 or len(installed) != 1 or not installed[0]["present"]:
        raise CheckFailedError(THE_INSTALL_WAS_NOT_MADE)
    if room in await rooms_offered(first) or room in await rooms_offered(second):
        raise CheckFailedError(THE_ROOM_WAS_STILL_OFFERED)
    if (await installing(second, steward, groups, room)).status_code == 201:
        raise CheckFailedError(A_ROOM_TOOK_A_SECOND_AGENT)
    if (await installing(first, steward, plain, elsewhere)).status_code == 201:
        raise CheckFailedError(A_SURFACE_WITHOUT_GROUPS_TOOK_ONE)

    freed = await remove_agent_from_group(
        request,
        first,
        RemovalAsked(install_id=installed[0]["id"]),
        await _asking(h, steward, strong=True),
    )
    if freed.status_code != 200 or room not in await rooms_offered(second):
        raise CheckFailedError(THE_REMOVAL_DID_NOT_FREE_THE_ROOM)


# -------------------------------------------------- a failing automation, paused and told
A_FAILURE_SHORT_OF_THE_THRESHOLD_PAUSED: Final = (
    "an automation was paused by a failure short of the threshold"
)
THE_THRESHOLD_DID_NOT_PAUSE: Final = (
    "the failure that reached the threshold did not pause the automation for failing repeatedly"
)
THE_NOTICE_WAS_NOT_ADDRESSED_TO_THE_STEWARD: Final = (
    "the notice a pause for failing builds was not addressed to the agent's steward"
)
THE_PAUSE_WAS_NOT_RECORDED: Final = (
    "a pause for failing was not recorded against the automation, or left it scheduled"
)
THE_STEWARD_WAS_NOT_FOUND: Final = (
    "the read the steward is told from did not find the pause for the agent's own steward"
)
THE_SENTENCE_NAMED_THE_FAILURE: Final = (
    "the sentence the steward is told did not say how many failures paused it, or named why"
)


@check(
    leaves=("M39.6.2.3",),
    sentence=(
        "A failure one short of the threshold pauses no automation; the failure that reaches it "
        "pauses it for failing repeatedly with a notice for the agent's steward, the runner "
        "records the pause, and the web process finds it for that steward and composes the "
        "sentence they are told, which says how many runs failed and not why."
    ),
)
async def a_failing_automation_is_paused_and_its_steward_is_told(h: Harness) -> None:
    from brain.automation_paused_told import paused_between, paused_text
    from brain.console.agent_automations import FAILURES_BEFORE_PAUSE, Automation
    from brain.console.automation_gallery import (
        AUTOMATION_AUTHORITY,
        install,
        new_automation_id,
        preview,
        template_by_id,
    )
    from brain.console.questions_view import QUESTION_AUTHORITY
    from brain.console.workspace import Tab, tab
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.acceptance_workspace import (
        _everywhere,
        _planes,
        stored_agent,
        worker_sessions,
    )
    from brain.ops.agent_automation_store import StoredAgentAutomations
    from brain.ops.automation_owner_store import PRINCIPAL_SETTING
    from brain.ops.automation_run import RUNNER_ACTOR, PausedBecause, RunOutcome, afterwards
    from brain.ops.automation_run_store import (
        StoredAutomationSchedules,
        _set_config,
        schedule_change,
    )

    await h.found_departments()
    steward = h.principal(A, "steward")
    await h.person(
        steward,
        department=A,
        grants=_everywhere(
            AUTOMATION_AUTHORITY.value,
            tab(Tab.AUTOMATIONS).read.requires.value,
            QUESTION_AUTHORITY.value,
            *_planes(),
        ),
    )
    agent_id = await installed_agent(h, steward, capabilities=(QUESTION_AUTHORITY.value,))
    record = await stored_agent(h, agent_id)
    person = await StoredPrincipals(h.sessions).live_principal(steward)
    template = template_by_id("unanswered_questions")
    if person is None or template is None:
        raise CheckFailedError("the check's steward or the gallery's template did not read back")
    reach = await h.reach(steward)
    shown = preview(template, record, installer=person, installer_reach=reach)
    installation = install(
        shown, confirmation=shown.confirmation, automation_id=new_automation_id()
    )
    done = await StoredAgentAutomations(h.sessions).install(
        installation, ent_hash=reach.ent_hash(), trace_id=h.trace_id
    )
    if not done.created:
        raise CheckFailedError("installing an automation from the gallery wrote nothing")
    [held] = await StoredAutomationSchedules(h.sessions).listed(agent_id)
    automation = Automation(
        automation_id=done.automation_id,
        agent_id=agent_id,
        name=held.automation.name,
        runs_as=person,
        task=held.automation.task,
        next_run_at=h.now,
    )

    def after(failures_before: int) -> Any:
        return afterwards(
            automation,
            outcome=RunOutcome.FAILED,
            refused_because=None,
            failures_before=failures_before,
            cadence=held.cadence or template.cadence,
            owner_id=steward,
            guards=held.guards,
            at=h.now,
        )

    if after(FAILURES_BEFORE_PAUSE - 2).paused_because is not None:
        raise CheckFailedError(A_FAILURE_SHORT_OF_THE_THRESHOLD_PAUSED)
    reached = after(FAILURES_BEFORE_PAUSE - 1)
    if reached.paused_because is not PausedBecause.FAILED_REPEATEDLY or reached.next_run_at:
        raise CheckFailedError(THE_THRESHOLD_DID_NOT_PAUSE)
    if reached.notice is None or reached.notice.owner_id != steward:
        raise CheckFailedError(THE_NOTICE_WAS_NOT_ADDRESSED_TO_THE_STEWARD)

    # What `run_one` writes next, as the runner, in the worker's role.
    sessions = worker_sessions(h)
    async with sessions() as session, session.begin():
        await session.execute(_set_config(PRINCIPAL_SETTING, RUNNER_ACTOR))
        await session.execute(
            schedule_change(
                automation_id=automation.automation_id,
                agent_id=agent_id,
                next_run_at=None,
                reason=reached.paused_because.value,
                changed_by=RUNNER_ACTOR,
                at=h.now,
            )
        )
    [paused] = await StoredAutomationSchedules(h.sessions).listed(agent_id)
    if not paused.automation.paused:
        raise CheckFailedError(THE_PAUSE_WAS_NOT_RECORDED)

    found = [
        one
        for one in await paused_between(
            sessions, after=h.now - timedelta(hours=1), until=h.now + timedelta(hours=1)
        )
        if one.automation_id == automation.automation_id
    ]
    if [one.steward_id for one in found] != [steward]:
        raise CheckFailedError(THE_STEWARD_WAS_NOT_FOUND)
    sentence = paused_text(found[0])
    if f"{FAILURES_BEFORE_PAUSE} consecutive failed runs" not in sentence or "because" in sentence:
        raise CheckFailedError(THE_SENTENCE_NAMED_THE_FAILURE)
