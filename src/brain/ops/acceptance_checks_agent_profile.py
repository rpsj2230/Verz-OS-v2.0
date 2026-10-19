"""Install acceptance checks for what an agent's Profile offers beside its tools.

The Profile lists who else can find an agent, whether it learns, which of its skills no run uses,
and what it says about computer use. Each of those is a sentence or a switch the code decides, so
each check calls the route the console page calls, as the reader that page serves, over the
check's own transaction, and reads the answer back from where it is kept. **Every row written is
in the transaction the run rolls back, for reserved people of acceptance_a and acceptance_b, and
nothing reaches a person.**

**The offers check proves four refusals beside the success.** With the switch off an administrator
is refused in words and no row is written; with it on a department and a person are offered, the
roster finds the agent for both and for nobody else, and the agent's own steward, who holds no
authority, is told who it is offered to and may not change it; a member who answers for nothing is
sent the same body before and after, so an offered agent and an unoffered one read identically; and
a personal agent takes no offer. A withdrawn offer stops finding the agent and leaves its row.

**The learning check holds the switch to the route and the route to the row.** The authority over
the agent reads it on, pauses it with a reason, reads it paused and resumes it, and the agent's
steward without that authority is refused as an agent that does not exist. What a pause does to
what forms is `brain.ops.acceptance_checks_signals`' and is not asked again here.

**Computer use is asked of the capability detail and of the import machinery.** The detail says it
is not offered while no isolated desktop runner module is part of the product, and a check that
only read the sentence would pass the day somebody added the module and forgot the sentence, so
it asks the machinery as well.

Not claimed here: M27.11.12's channels and sources, whose install checks are
`brain.ops.acceptance_checks_agent_channels` and the connector checks that name M39.2.1. What is
claimed is the skill sentence, that a pinned skill nothing in the library backs is said to change no
run and one the library approved is not.

Task ids: M27.11.12, M27.11.13, M27.11.14, M27.15.32
"""

from __future__ import annotations

import importlib.util
import json
from typing import Any, Final, Literal

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_agent_console import (
    _asking,
    _console,
    _readers,
    _request,
    a_department_administrator,
)
from brain.ops.acceptance_run import Harness
from brain.ops.acceptance_workspace import installed_agent

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2340

A, B = RESERVED_DEPARTMENTS

NOT_REFUSED_WITH_THE_SWITCH_OFF: Final = "an offer was accepted while the switch was off"
WROTE_WITH_THE_SWITCH_OFF: Final = "an offer written while the switch was off left a row"
NOT_OFFERED: Final = "an administrator could not offer an agent to a department and a person"
NOT_FOUND_AFTER_AN_OFFER: Final = "an agent offered to a department was not found by its members"
FOUND_WITHOUT_AN_OFFER: Final = "an agent was found by somebody it was not offered to"
STEWARD_NOT_TOLD: Final = "an agent's steward was not told who it is offered to"
STEWARD_MAY_CHANGE_IT: Final = (
    "an agent's steward, who holds no authority, changed who it is offered to"
)
MEMBER_TOLD_WHO: Final = "a member who answers for the agent was told who it is offered to"
MEMBER_TOLD_APART: Final = "a member read an offered agent differently from one offered to nobody"
PERSONAL_TAKES_AN_OFFER: Final = "a personal agent was offered to somebody"
STILL_FOUND_AFTER_WITHDRAWN: Final = "a withdrawn offer still found the agent"
WITHDRAWAL_LEFT_NO_ROW: Final = "a withdrawn offer left no row saying who withdrew it"

NOT_READ_ON: Final = "an agent's learning was not read as on for the person who may switch it"
NOT_PAUSED: Final = "an agent's learning was not paused by the person who may switch it"
NOT_RESUMED: Final = "an agent's learning was not resumed by the person who paused it"
PAUSE_NOT_KEPT: Final = "a pause was not kept in the row learning reads"
STEWARD_SWITCHED_IT: Final = "an agent's steward, who holds no authority, switched its learning"

COMPUTER_USE_OFFERED_WITH_NO_RUNNER: Final = (
    "computer use was offered while no desktop runner exists"
)
COMPUTER_USE_NOT_SAID: Final = "the capability detail did not say computer use is not offered"
A_RUNNER_EXISTS: Final = (
    "the product now has an isolated desktop runner module, so what the Profile says about "
    "computer use has to be asked again by a person"
)

SKILL_NOT_SAID: Final = "a pinned skill the library does not hold was not said to change no run"
APPROVED_SKILL_SAID_STOPPED: Final = "an approved assigned skill was said to change no run"


async def _body(answered: Any) -> dict[str, Any]:
    loaded = json.loads(bytes(answered.body))
    return dict(loaded)


async def _offers_of(h: Harness, agent_id: str) -> list[tuple[str, str, bool]]:
    """Every offer the table holds for one agent, with whether it was withdrawn, in order."""
    async with h.sessions() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT kind, value, removed_at IS NOT NULL FROM agent.audience_extra "
                    "WHERE agent_id = :agent ORDER BY kind, value"
                ),
                {"agent": agent_id},
            )
        ).all()
    return [(str(kind), str(value), bool(gone)) for kind, value, gone in rows]


# ------------------------------------------- 1. offered beyond its level (M27.11.13)
@check(
    leaves=("M27.11.13",),
    sentence=(
        "An agent's Profile tells its steward and its department's administrator who else it is "
        "offered to, an administrator offers it to a department and a person and withdraws one "
        "only once the switch is on, the roster then finds it for exactly them, a member who "
        "answers for nothing is sent the same body before and after, and a personal agent takes "
        "no offer."
    ),
)
async def an_agent_is_offered_to_more_than_its_level_from_its_profile(h: Harness) -> None:
    from brain.agent_audience_routes import (
        AudienceAsked,
        agent_audience,
        offer_agent,
        withdraw_agent,
    )
    from brain.agent_routes import agents
    from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
    from brain.agents.model import AgentAudience
    from brain.core.errors import BrainError
    from brain.core.scope import Scope
    from brain.knowledge.visibility import Visibility
    from brain.listing import ListAsked
    from brain.ops.acceptance_switch import switched
    from brain.ops.features_declared.agent_audience_extras import AGENT_AUDIENCE_EXTRAS

    await h.found_departments()
    steward, member = h.principal(A, "steward"), h.principal(A, "member")
    outsider, named = h.principal(B, "outsider"), h.principal(B, "named")
    for one, department in ((steward, A), (member, A), (outsider, B), (named, B)):
        await h.person(one, department=department, grants=_readers())
    admin = await a_department_administrator(h)
    agent = await installed_agent(
        h,
        steward,
        suffix="_offers",
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id=steward, department=A),
    )
    app = _console(h)
    mine = ListAsked(search=f"acceptance_{h.run}", limit=50)

    async def found_by(reader: str) -> bool:
        page = await agents(_request(app), await _asking(h, reader), mine)
        return agent in {one.agent_id for one in page.items}

    async def offer(
        who: str,
        kind: Literal["department", "person"],
        value: str,
        *,
        withdraw: bool = False,
        on: str = agent,
    ) -> Any:
        move = withdraw_agent if withdraw else offer_agent
        return await move(
            _request(app),
            on,
            AudienceAsked(kind=kind, value=value),
            await _asking(h, who, strong=True),
        )

    # With the switch off, an administrator is refused in words and nothing is written.
    await switched(h, AGENT_AUDIENCE_EXTRAS, on=False)
    refused = await offer(admin, "department", B)
    if getattr(refused, "status_code", 200) != 409:
        raise CheckFailedError(NOT_REFUSED_WITH_THE_SWITCH_OFF)
    if await _offers_of(h, agent):
        raise CheckFailedError(WROTE_WITH_THE_SWITCH_OFF)

    await switched(h, AGENT_AUDIENCE_EXTRAS, on=True)
    before = (await agent_audience(_request(app), agent, await _asking(h, member))).model_dump()
    if await found_by(outsider) or await found_by(named):
        raise CheckFailedError(FOUND_WITHOUT_AN_OFFER)
    for done in (await offer(admin, "department", B), await offer(admin, "person", member)):
        if getattr(done, "status_code", 200) == 409:
            raise CheckFailedError(NOT_OFFERED)
    if not (await found_by(outsider) and await found_by(named)):
        raise CheckFailedError(NOT_FOUND_AFTER_AN_OFFER)

    # The steward holds no authority: told who, and refused a change as an agent that is not there.
    told = await agent_audience(_request(app), agent, await _asking(h, steward))
    if (told.departments, told.people) != ([B], [member]) or told.may_change:
        raise CheckFailedError(STEWARD_NOT_TOLD)
    try:
        await offer(steward, "person", named)
    except BrainError:
        pass
    else:
        raise CheckFailedError(STEWARD_MAY_CHANGE_IT)

    # A member answering for nothing is told no name, and reads the same body as before.
    after = (await agent_audience(_request(app), agent, await _asking(h, member))).model_dump()
    if after["departments"] or after["people"] or after["names_shown"]:
        raise CheckFailedError(MEMBER_TOLD_WHO)
    if after != before:
        raise CheckFailedError(MEMBER_TOLD_APART)

    # A personal agent takes no offer, whatever the switch says. Only somebody who holds the
    # authority over every row and owns the agent can ask, since nobody else may even open it, so
    # the refusal is the route's own sentence and not the answer an agent that is not there gets.
    chief = h.principal(A, "chief")
    await h.person(
        chief,
        department=A,
        grants=((AGENT_LIFECYCLE_CAPABILITY.value, Scope.unrestricted()),),
    )
    own = await installed_agent(h, chief, suffix="_own", personal=True)
    taken = await offer(chief, "person", named, on=own)
    if getattr(taken, "status_code", 200) != 409 or await _offers_of(h, own):
        raise CheckFailedError(PERSONAL_TAKES_AN_OFFER)

    # Withdrawn: the agent is no longer found by that department, and the row says who withdrew it.
    gone = await offer(admin, "department", B, withdraw=True)
    if getattr(gone, "status_code", 200) == 409:
        raise CheckFailedError(STILL_FOUND_AFTER_WITHDRAWN)
    if await found_by(outsider):
        raise CheckFailedError(STILL_FOUND_AFTER_WITHDRAWN)
    rows = await _offers_of(h, agent)
    if (("department", B, True) not in rows) or (("person", member, False) not in rows):
        raise CheckFailedError(WITHDRAWAL_LEFT_NO_ROW)


# ------------------------------------------------ 2. the learning switch (M27.11.14)
@check(
    leaves=("M27.11.14",),
    sentence=(
        "The person who holds the lifecycle authority over an agent reads its learning on, "
        "pauses it with a reason, reads it paused in the row learning asks, and resumes it, and "
        "the agent's steward without that authority is refused as an agent that does not exist."
    ),
)
async def an_agents_learning_is_paused_and_resumed_from_its_profile(h: Harness) -> None:
    from brain.agent_lifecycle_routes import (
        LearningSwitchAsked,
        agent_learning,
        switch_agent_learning,
    )
    from brain.core.errors import BrainError
    from brain.ops.learning_signal_store import StoredLearningPauses

    await h.found_departments()
    steward = h.principal(A, "steward")
    await h.person(steward, department=A, grants=_readers())
    admin = await a_department_administrator(h)
    agent = await installed_agent(h, steward, suffix="_learns")
    app = _console(h)

    async def reads(who: str) -> bool:
        return bool(
            (await agent_learning(_request(app), agent, await _asking(h, who, strong=True))).paused
        )

    async def moves(paused: bool, reason: str) -> Any:
        return await switch_agent_learning(
            _request(app),
            agent,
            LearningSwitchAsked(paused=paused, reason=reason),
            await _asking(h, admin, strong=True),
        )

    if await reads(admin):
        raise CheckFailedError(NOT_READ_ON)
    if not (await moves(True, "an install acceptance check")).paused:
        raise CheckFailedError(NOT_PAUSED)
    if not await reads(admin):
        raise CheckFailedError(NOT_PAUSED)
    if agent not in await StoredLearningPauses(h.sessions).paused((agent,)):
        raise CheckFailedError(PAUSE_NOT_KEPT)
    try:
        await reads(steward)
    except BrainError:
        pass
    else:
        raise CheckFailedError(STEWARD_SWITCHED_IT)
    if (await moves(False, "the check is over")).paused or await reads(admin):
        raise CheckFailedError(NOT_RESUMED)


# --------------------------------------- 3. computer use is not offered (M27.15.32)
@check(
    leaves=("M27.15.32",),
    sentence=(
        "An agent's capability detail says computer use is not offered, and does so for as long "
        "as the product holds no isolated desktop runner, which the import machinery is asked "
        "and not a constant."
    ),
)
async def computer_use_is_not_offered_until_a_desktop_runner_exists(h: Harness) -> None:
    from brain.agent_capability_routes import agent_capabilities
    from brain.console.agent_behaviour import DESKTOP_RUNNER_MODULE

    try:
        runner = importlib.util.find_spec(DESKTOP_RUNNER_MODULE) is not None
    except (ImportError, ValueError):
        runner = False
    if runner:
        raise CheckNotRunError(A_RUNNER_EXISTS)
    await h.found_departments()
    steward = h.principal(A, "steward")
    await h.person(steward, department=A, grants=_readers())
    agent = await installed_agent(h, steward, suffix="_computer")
    view = await agent_capabilities(_request(_console(h)), agent, await _asking(h, steward))
    if view.computer_use.offered:
        raise CheckFailedError(COMPUTER_USE_OFFERED_WITH_NO_RUNNER)
    if not view.computer_use.sentence.startswith("Not offered"):
        raise CheckFailedError(COMPUTER_USE_NOT_SAID)


# ------------------------------------------------ 4. a skill no run uses (M27.11.12)
@check(
    leaves=("M27.11.12",),
    sentence=(
        "An agent's capability detail says a pinned skill the library holds no row for changes no "
        "run, and says nothing of one the library approved and the agent is assigned."
    ),
)
async def a_pinned_skill_no_run_could_use_is_said_so_on_the_profile(h: Harness) -> None:
    from brain.agent_capability_routes import agent_capabilities
    from brain.console.screens import screen
    from brain.console.skill_library import added, decided, read_package
    from brain.ops.acceptance_checks_skills import (
        _administrator,
        _an_agent,
        _assign,
        _named,
        _skill_md,
        _store,
    )
    from brain.ops.skill_store import StoredSkills

    await h.found_departments()
    admin = await _administrator(h, "profile_skills")
    reach = await h.reach(admin)
    made = added(read_package("SKILL.md", _skill_md(_named(h, "profiled"))), by=admin, at=h.now)
    await _store(h, made, reach)
    if not await StoredSkills(h.sessions).decide(
        decided(made, reviewer=admin, approve=True, at=h.now),
        ent_hash=reach.ent_hash(),
        trace_id=h.trace_id,
    ):
        raise CheckFailedError(SKILL_NOT_SAID)
    reader = h.principal(A, "profile_reader")
    await h.person(reader, department=A, grants=_readers(screen("skills").read.requires.value))
    assigned = await _an_agent(h, admin, named="_assigned")
    await _assign(h, made.digest, assigned, reach)
    unbacked = await installed_agent(
        h, admin, suffix="_unbacked", skills=((_named(h, "missing"), "f" * 64),)
    )
    app = _console(h)

    async def chips(agent_id: str) -> list[Any]:
        view = await agent_capabilities(_request(app), agent_id, await _asking(h, reader))
        return list(view.skills)

    backed = await chips(assigned)
    if not backed or any(one.not_used_because is not None for one in backed):
        raise CheckFailedError(APPROVED_SKILL_SAID_STOPPED)
    missing = await chips(unbacked)
    if not missing or any(one.not_used_because is None for one in missing):
        raise CheckFailedError(SKILL_NOT_SAID)
