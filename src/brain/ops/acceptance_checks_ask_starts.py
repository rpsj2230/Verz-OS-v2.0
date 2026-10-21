"""Install acceptance checks for how a member starts on Ask (M40.7.5, M40.7.2, M40.7.8).

Three checks, one for each way a question is started other than by typing it at the default agent:
a task, a skill to try, an agent's starters. Each is asked through `/answer`'s own function or the
starters route, as a member of acceptance_a, with the refusal asked beside the answer.

**A task with no agent named** is matched to the agent whose purpose it shares words with. The check
asks the same question with task routing switched off, and the request row says the default agent
answered; switched on, the row says the agent whose instruction the question shares two words with,
and a second agent the member may not call, which fits it equally well, is never the one. **A skill
to try** is shown to the model for that question only: with trying switched off or with a digest
nobody approved the card is absent, with an approved one it is present, and the agent has gained no
assignment afterwards. **Starters** are read through the route: the example task of a skill assigned
to the agent is offered to a member who may run the agent, nothing is offered to one who may not
(the one refusal), and nothing is offered while the switch is off.

The switches are set on the check's application state, where the routes look first, so these never
turn a real switch on or off on the install they run against.

Every name the checks write is the run's, written by reserved principals of acceptance_a, and all of
it rolls back with the check.

Task ids: M40.7.5, M40.7.2, M40.7.8
"""

from __future__ import annotations

from typing import Any, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS
from brain.ops.acceptance_checks_skill_runs import _Kept
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1960

A, B = RESERVED_DEPARTMENTS

#: The example the starters check's skill carries, and the tool list it says it needs (none).
EXAMPLE_TASK: Final = "Which acceptance check is waiting for review?"


@check(
    leaves=("M40.7.5",),
    sentence=(
        "A member of acceptance_a starts a task with no agent named: with task routing off the "
        "default agent answers; with it on the agent whose purpose the task shares words with "
        "answers, at the member's own reach, and an agent the member may not call is never the one."
    ),
)
async def a_task_with_no_agent_goes_to_the_agent_it_matches(
    h: Harness,
) -> None:
    from brain.agents.model import AgentAudience
    from brain.api_routes import DEFAULT_AGENT
    from brain.knowledge.visibility import Visibility
    from brain.ops.acceptance_checks_skills import _administrator, _an_agent
    from brain.ops.acceptance_models import (
        STAND_IN,
        a_reader_with_a_document,
        askable,
        asking_app,
        models_for,
        pinned,
        trace_of,
    )
    from brain.ops.acceptance_routing import (
        ANSWERS,
        answered,
        asking,
        constrained,
        request_of,
        roster_over,
        stand_in_drivers,
        step,
    )

    reader, paired = await a_reader_with_a_document(h)
    await constrained(h, ())
    admin = await _administrator(h, "task_routing")
    purpose = f"Answers what {paired.key} is paired with."
    agent = await _an_agent(h, admin, capabilities=KNOWLEDGE_READS, persona=purpose)
    hidden = await _an_agent(
        h,
        admin,
        capabilities=KNOWLEDGE_READS,
        persona=purpose,
        named="_hidden",
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id=admin, department=B),
    )
    responder = _Kept()
    models = await models_for(h, standing=stand_in_drivers(h, responder))
    askable(await models.calls.planned(), STAND_IN)
    await pinned(h, (step(ANSWERS),))
    app = await asking_app(h, models)
    app.state.agent_roster = roster_over(h)
    task = paired.question

    async def routed_to(n: int) -> str:
        if not answered(await asking(h, app, reader, task, n)):
            raise CheckFailedError("a task started with no agent named was not answered")
        return str((await request_of(h, trace_of(h, n))).get("selected_agent", ""))

    app.state.task_routing_on = False
    if await routed_to(1) != DEFAULT_AGENT:
        raise CheckFailedError("a task was routed to an agent with task routing switched off")
    app.state.task_routing_on = True
    chosen = await routed_to(2)
    if chosen == hidden:
        raise CheckFailedError("a task was routed to an agent the member may not call")
    if chosen != agent:
        raise CheckFailedError("a task was not routed to the agent whose purpose it matches")


@check(
    leaves=("M40.7.2",),
    sentence=(
        "A member of acceptance_a tries an approved skill: it is shown to the model for that "
        "question when trying is switched on and not when it is off, never when nobody approved "
        "it, and the agent has gained no assignment afterwards."
    ),
)
async def a_member_tries_an_approved_skill_for_one_question(
    h: Harness,
) -> None:
    from brain.console.skill_library import added, decided, read_package
    from brain.ops.acceptance_checks_skills import (
        _administrator,
        _an_agent,
        _named,
        _pins,
        _skill_md,
        _store,
    )
    from brain.ops.acceptance_models import (
        STAND_IN,
        a_reader_with_a_document,
        askable,
        asking_app,
        models_for,
        pinned,
    )
    from brain.ops.acceptance_routing import (
        ANSWERS,
        answered,
        asking,
        constrained,
        roster_over,
        stand_in_drivers,
        step,
    )
    from brain.ops.skill_store import StoredSkills

    reader, paired = await a_reader_with_a_document(h)
    await constrained(h, ())
    admin = await _administrator(h, "try_a_skill")
    reach = await h.reach(admin)
    store = StoredSkills(h.sessions)
    made = []
    for word in ("approved", "undecided"):
        one = added(read_package("SKILL.md", _skill_md(_named(h, word))), by=admin, at=h.now)
        await _store(h, one, reach)
        made.append(one)
    approved, undecided = made
    if not await store.decide(
        decided(approved, reviewer=admin, approve=True, at=h.now),
        ent_hash=reach.ent_hash(),
        trace_id=h.trace_id,
    ):
        raise CheckFailedError("an approval of a skill named for this run was refused")
    agent = await _an_agent(h, admin, capabilities=KNOWLEDGE_READS)
    responder = _Kept()
    models = await models_for(h, standing=stand_in_drivers(h, responder))
    askable(await models.calls.planned(), STAND_IN)
    await pinned(h, (step(ANSWERS),))
    app = await asking_app(h, models)
    app.state.agent_roster = roster_over(h)
    name = approved.imported.skill.name

    async def shown(n: int, digest: str | None, *, on: bool) -> bool:
        app.state.trying_a_skill_on = on
        if not answered(
            await asking(h, app, reader, paired.question, n, agent=agent, try_skill=digest)
        ):
            raise CheckFailedError("a question carrying a skill to try was not answered")
        return name in responder.sent()

    if await shown(1, approved.digest, on=False):
        raise CheckFailedError("a skill was tried with trying switched off")
    if not await shown(2, approved.digest, on=True):
        raise CheckFailedError("an approved skill was not shown to the model when it was tried")
    if await shown(3, None, on=True):
        raise CheckFailedError("a skill tried for one question was shown to the next")
    if await shown(4, undecided.digest, on=True) or undecided.imported.skill.name in (
        responder.sent()
    ):
        raise CheckFailedError("a skill nobody approved was tried")
    if await _pins(h, agent):
        raise CheckFailedError("trying a skill assigned it to the agent")


@check(
    leaves=("M40.7.8",),
    sentence=(
        "A member of acceptance_a who may run an agent is offered the example task of a skill "
        "assigned to it; a member who may not run it is refused in the page's one sentence; and "
        "with the switch off the list is empty."
    ),
)
async def an_agent_opened_offers_the_examples_of_its_skills(
    h: Harness,
) -> None:
    from fastapi import FastAPI
    from starlette.requests import Request

    from brain.console.skill_library import added, decided, read_package
    from brain.core.errors import Absent
    from brain.core.scope import Scope
    from brain.knowledge.row_store import SessionRowSource
    from brain.member.shell import member_capability
    from brain.member_starter_routes import agent_starters
    from brain.ops.acceptance_checks_skills import (
        _administrator,
        _an_agent,
        _assign,
        _named,
        _skill_md,
        _store,
    )
    from brain.ops.acceptance_skill_console import _asking
    from brain.ops.skill_store import StoredSkills
    from brain.tools.startup import build_registry

    await h.found_departments()
    member, outsider = (h.principal(A, "starter"), h.principal(B, "starter_out"))
    held = (
        (member_capability("home").value, Scope.unrestricted()),
        ("read:member.content", Scope.unrestricted()),
    )
    await h.person(member, department=A, grants=held)
    await h.person(outsider, department=B, grants=held)
    admin = await _administrator(h, "starters")
    reach = await h.reach(admin)
    one = added(
        read_package(
            "SKILL.md",
            _skill_md(
                _named(h, "starters"),
                body=("Read the question.", "## Examples", f"- {EXAMPLE_TASK} => none"),
            ),
        ),
        by=admin,
        at=h.now,
    )
    await _store(h, one, reach)
    if not await StoredSkills(h.sessions).decide(
        decided(one, reviewer=admin, approve=True, at=h.now),
        ent_hash=reach.ent_hash(),
        trace_id=h.trace_id,
    ):
        raise CheckFailedError("an approval of a skill named for this run was refused")
    agent = await _an_agent(h, admin)
    await _assign(h, one.digest, agent, reach)

    app = FastAPI()
    app.state.db_sessions = h.sessions
    app.state.tools = build_registry(
        source=h.settings.tool_source, records=SessionRowSource(h.sessions)
    )
    request = Request({"type": "http", "app": app, "headers": [], "method": "GET"})

    async def prompts(who: str, *, on: bool) -> Any:
        app.state.agent_starter_prompts_on = on
        return await agent_starters(request, agent, await _asking(h, who))

    offered = await prompts(member, on=True)
    if list(offered.prompts) != [EXAMPLE_TASK]:
        raise CheckFailedError("a member who may run an agent was not offered its skill's example")
    if (await prompts(member, on=False)).prompts:
        raise CheckFailedError("starters were offered with the switch off")
    try:
        await prompts(outsider, on=True)
    except Absent:
        return
    raise CheckFailedError("a member who may not run an agent was told what to ask it")
