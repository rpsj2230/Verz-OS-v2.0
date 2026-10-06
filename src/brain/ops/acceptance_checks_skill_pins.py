"""The install acceptance checks for what an agent runs with: its skill's version, its model, and
what three personas are told and offered.

Three leaves that were built and wired with nothing on an install saying they still work.
**M12.2.7**, version locking per agent: `brain.tools.skills.resolve_pin` refuses any version but the
pinned one, and the run reads its skills through `brain.escalation_routes.offered_skills`, but the
only install check over pins (`brain.ops.acceptance_checks_skills`) read them off the Skills screen
and never asked what a run is handed. **M5.7.3**, the pinned model: `PUT /agents/{id}/model-pin`
and the executor's walk were proved by unit tests over fakes. **M28.2.1 and M28.2.3**, the
permission canaries: the scheduled run (`brain.ops.canary_run`) compares every reach the install
holds, and on an install with no question shape in `gate.fast_path_rule` it compares no refusal at
all, which is a green run that asked nothing.

**Each check is the product's own functions, and the names it writes are the run's.** The skill
is added, approved, edited and assigned through the Skills screen's sequence
(`acceptance_checks_skills`), the pin is written by the route function itself, the question is
asked through `/answer`'s own `answered_for`, and the canaries are asked by the scheduled run's
own `ask_every_reach`. Everything is inside the check's rolled-back transaction.

**The model check answers from stand-ins in the process, and asks no real provider.** Which step a
walk tries first is the property, and a stand-in answering in the documented chat completions
shape is the product's own transport and adapter after the socket, as
`brain.ops.acceptance_routing.A_FAILURE_SHAPE_IS_ANSWERED_IN_THE_PROCESS` argues. An install
keeping text on its own hardware plans no stand-in, so there the check says it was not run.

**The personas are synthetic and live for the check alone.** `brain.ops.canary_run` refuses to
plant a canary account in a client's directory (`A_CANARY_IS_A_REACH_AND_NEVER_AN_ACCOUNT`), and a
reserved person in a reserved department inside a transaction that is rolled back is not one: the
check asks as the asker holding nothing, a buyer granted the price list in acceptance_a and an
outsider in acceptance_b, loaded through the one resolver. See
`THREE_PERSONAS_ARE_A_REACH_EACH_AND_LEAVE_NOTHING`.

**Not here: M12.2.8**, progressive disclosure. A model is shown a skill's card only through
`ModelLane.agent.pins`, and `/answer` hands every agent's run `pins=()`
(`brain.api_routes.model_lane_for` says so in its own words); nothing hands a model a skill's body
on demand, and `brain.tools.run_skill.SkillScriptTool` is registered nowhere. There is no run on
an install that shows a card or a body, so there is nothing for a check to ask.

Task ids: M12.2.7, M5.7.3, M28.2.1, M28.2.3, M13.2.5
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.agents.model import AgentRecord
    from brain.core.entitlement import EntitlementSet

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 422

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the canary check's personas are not the accounts `canary_run` refuses.
THREE_PERSONAS_ARE_A_REACH_EACH_AND_LEAVE_NOTHING: Final = (
    "The canaries never plant an account in a client's directory. The check's personas are "
    "reserved people in reserved departments, made inside a transaction that is rolled back, and "
    "loaded through the one resolver beside the asker the directory does not hold, so the run "
    "compares three reaches and leaves nobody behind."
)

#: Why the pinned model is a Complex step while the agent asks at its default level.
A_PIN_IS_TRIED_FIRST_IN_WHICHEVER_LEVEL_HOLDS_IT: Final = (
    "The executor tries the step serving the pinned pair in whichever level holds it, before the "
    "agent's own level. The pin's step is Complex and the agent's level is the default, so an "
    "answer from the pinned step can only have come from the pin, and a pinned step that cannot "
    "connect shows the level's own step answering behind it."
)

# ------------------------------------------------------------------------ the figures
#: What the pinned stand-in step is called. Any name the stand-in does not treat as a failure
#: answers, and this one says what it is on the attempt rows.
PINNED_MODEL: Final = "pinned-answers"


# ------------------------------------------------------------------------ the helpers
def _app_over(h: Harness) -> FastAPI:
    """What the escalation route reads an agent's skills from: the sessions and the registry."""
    from fastapi import FastAPI

    from brain.knowledge.row_store import SessionRowSource
    from brain.tools.startup import build_registry

    app = FastAPI()
    app.state.db_sessions = h.sessions
    app.state.tools = build_registry(
        source=h.settings.tool_source, records=SessionRowSource(h.sessions)
    )
    return app


async def _record(h: Harness, agent_id: str) -> AgentRecord:
    """The agent as `/answer`'s roster reads it on a question."""
    from brain.ops.acceptance_routing import roster_over

    found = {one.agent_id: one for one in (await roster_over(h)()).records}.get(agent_id)
    if found is None:
        raise CheckFailedError("the check's agent did not read back from the roster")
    return found


async def _run_skills(h: Harness, app: FastAPI, agent_id: str, caller: EntitlementSet) -> list[str]:
    """The digests of the skills a run of this agent is handed, by the route's own reading."""
    from brain.escalation_routes import offered_skills
    from brain.ops.acceptance_threads import _request

    offered = await offered_skills(
        _request(app), await _record(h, agent_id), caller=caller, now=h.now
    )
    return [one.skill.digest() for one in offered]


# ------------------------------------------------------- M12.2.7: version locking per agent
@check(
    leaves=("M12.2.7",),
    sentence=(
        "A skill approved and assigned to two agents of acceptance_a is edited, and the edit "
        "approved and assigned to one of them: a run of each is handed exactly the version its "
        "own agent is pinned to, the other agent's run keeps the first version, and neither run "
        "follows the edit by itself."
    ),
)
async def each_agent_runs_the_skill_version_it_is_pinned_to(h: Harness) -> None:
    from brain.console.skill_library import added, decided, edited, read_package
    from brain.ops.acceptance_checks_skills import (
        BODY,
        _administrator,
        _an_agent,
        _assign,
        _named,
        _pins,
        _skill_md,
        _store,
    )
    from brain.ops.skill_store import StoredSkills

    await h.found_departments()
    admin = await _administrator(h, "skills")
    editor = await _administrator(h, "editor", reviews=False)
    admin_reach, editor_reach = await h.reach(admin), await h.reach(editor)
    store = StoredSkills(h.sessions)
    name = _named(h, "locked")
    first = added(read_package("SKILL.md", _skill_md(name)), by=admin, at=h.now)
    await _store(h, first, admin_reach)
    if not await store.decide(
        decided(first, reviewer=admin, approve=True, at=h.now),
        ent_hash=admin_reach.ent_hash(),
        trace_id=h.trace_id,
    ):
        raise CheckFailedError("an administrator could not approve a skill they imported")
    kept, moved = (
        await _an_agent(h, admin, named="_kept"),
        await _an_agent(h, admin, named="_moved"),
    )
    for agent_id in (kept, moved):
        await _assign(h, first.digest, agent_id, admin_reach)

    approved = await store.skill(first.digest)
    if approved is None:
        raise CheckFailedError("an approved skill did not read back")
    second = edited(
        approved,
        _skill_md(
            name,
            description="Use when an acceptance check asks for the edited version",
            version="1.1.0",
            body=(BODY[0], "Answer it from the edited acceptance check."),
        ).decode("utf-8"),
        by=editor,
        at=h.now,
        library=await store.library(),
    )
    await _store(h, second, editor_reach)
    new = {one.digest: one for one in await store.library()}.get(second.digest)
    if new is None or not await store.decide(
        decided(new, reviewer=admin, approve=True, at=h.now),
        ent_hash=admin_reach.ent_hash(),
        trace_id=h.trace_id,
    ):
        raise CheckFailedError("an edit by somebody else could not be approved by a reviewer")

    app = _app_over(h)
    # Both versions approved, neither agent moved: each run is handed the version it was pinned to.
    for agent_id in (kept, moved):
        if await _run_skills(h, app, agent_id, admin_reach) != [first.digest]:
            raise CheckFailedError("a run followed an approved edit its agent was not pinned to")
    await _assign(h, second.digest, moved, admin_reach)
    if await _pins(h, moved) != {name: second.digest} or await _pins(h, kept) != {
        name: first.digest
    }:
        raise CheckFailedError("reassigning one agent moved a pin it should not have")
    if await _run_skills(h, app, moved, admin_reach) != [second.digest]:
        raise CheckFailedError("a run was not handed the version its agent was moved to")
    if await _run_skills(h, app, kept, admin_reach) != [first.digest]:
        raise CheckFailedError("moving one agent's pin moved another agent's run")


# -------------------------------------------- M13.2.5: the install hash keys the answer cache
async def _roster_hash(h: Harness, principal_id: str, agent_id: str) -> str:
    """The configuration hash `/answer` keys this agent's answers on, from the roster it reads."""
    from brain.api_routes import Answering, roster_of
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_routing import roster_over
    from brain.tools.startup import build_registry

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    roster = await roster_of(
        SimpleNamespace(agent_roster=roster_over(h)),
        Answering(
            principal=person,
            reach=admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.AUTHENTICATED),
            channel=Channel.CONSOLE,
            now=h.now,
        ),
        build_registry(source=h.settings.tool_source, records=SessionRowSource(h.sessions)),
    )
    setup = roster.agents.get(agent_id)
    if setup is None:
        raise CheckFailedError("the check's agent was not in the roster its owner is answered from")
    return setup.config_hash


@check(
    leaves=("M13.2.5",),
    sentence=(
        "An agent of acceptance_a is read from the roster `/answer` selects from, a skill is "
        "approved and assigned to it, and the roster is read again: the hash the answer cache "
        "is keyed on has not moved when the skill was only approved and has moved once it was "
        "assigned, and the key built from the two hashes differs."
    ),
)
async def an_assigned_skill_moves_the_key_an_answer_is_cached_under(h: Harness) -> None:
    from brain.console.skill_library import added, decided, read_package
    from brain.gate.cache_key import key_for
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
    admin = await _administrator(h, "keyed")
    reach = await h.reach(admin)
    agent = await _an_agent(h, admin, named="_keyed")
    before = await _roster_hash(h, admin, agent)
    first = added(read_package("SKILL.md", _skill_md(_named(h, "keyed"))), by=admin, at=h.now)
    await _store(h, first, reach)
    if not await StoredSkills(h.sessions).decide(
        decided(first, reviewer=admin, approve=True, at=h.now),
        ent_hash=reach.ent_hash(),
        trace_id=h.trace_id,
    ):
        raise CheckFailedError("an administrator could not approve a skill they imported")
    if await _roster_hash(h, admin, agent) != before:
        raise CheckFailedError("approving a skill moved the key of an agent it was not assigned to")
    await _assign(h, first.digest, agent, reach)
    after = await _roster_hash(h, admin, agent)
    if after == before:
        raise CheckFailedError(
            "assigning a skill left the key an answer is cached under where it was"
        )
    ent_hash = reach.ent_hash()
    if key_for("the check's question", ent_hash, before, 1, {}) == key_for(
        "the check's question", ent_hash, after, 1, {}
    ):
        raise CheckFailedError("two hashes that differ built one cache key")


# ------------------------------------------------------------ M5.7.3: an agent's model pin
@check(
    leaves=("M5.7.3",),
    sentence=(
        "An agent of acceptance_a answers at its default level from a stand-in step; an "
        "administrator pins a Complex step's provider and model through the pin route, and the "
        "next answer comes from it first; pinned to a step that cannot connect, the level's own "
        "step answers behind it; a pin no step serves, or by a reader, is refused."
    ),
)
async def an_agent_s_pinned_model_is_tried_first_with_its_level_behind(h: Harness) -> None:
    from brain.agent_model_routes import PinAsked, PinView, pin_model
    from brain.core.errors import Absent
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals
    from brain.models.evidence import OK
    from brain.models.routing import DEFAULT_TIER, Tier
    from brain.ops.acceptance_checks import KNOWLEDGE_READS
    from brain.ops.acceptance_checks_skills import _an_agent
    from brain.ops.acceptance_models import STAND_IN, STAND_IN_ADDRESS, pinned, trace_of
    from brain.ops.acceptance_routing import (
        ANSWERS,
        CONNECTION_ERROR,
        UNREACHABLE,
        answered,
        asking,
        request_of,
        roster_over,
        standing_by,
        step,
        walked,
    )
    from brain.ops.acceptance_threads import _request
    from brain.routing_routes import MATRIX_WRITE

    s = await standing_by(h)
    admin = h.principal(A, "models")
    await h.person(admin, department=A, grants=((MATRIX_WRITE.value, Scope.unrestricted()),))
    person = await StoredPrincipals(h.sessions).live_principal(admin)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    as_admin = SimpleNamespace(
        caller=SimpleNamespace(principal=person),
        reach=admit(await h.reach(admin), Channel.CONSOLE, Assurance.STRONG),
        now=h.now,
    )
    agent = await _an_agent(h, admin, capabilities=KNOWLEDGE_READS)
    await pinned(
        h,
        (
            step(ANSWERS, tier=DEFAULT_TIER),
            step(PINNED_MODEL, tier=Tier.HEAVY),
            step(UNREACHABLE, tier=Tier.HEAVY),
        ),
    )
    s.app.state.agent_roster = roster_over(h)
    request = _request(s.app)

    async def pin(model: str | None, by: Any = as_admin) -> Any:
        body = PinAsked(provider=None if model is None else STAND_IN, model=model)
        return await pin_model(request, agent, body, by)

    async def ask(n: int) -> list[tuple[str, str, str | None, str]]:
        through = await asking(h, s.app, s.reader, s.paired.question, n, agent=agent)
        if not answered(through):
            raise CheckFailedError("a question asked through an agent was not answered")
        row = await request_of(h, trace_of(h, n))
        if row.get("selected_agent") != agent:
            raise CheckFailedError("the question was not answered by the agent it was asked of")
        return await walked(h, trace_of(h, n))

    level = DEFAULT_TIER.value
    # By default the agent's level answers, and the pinned step is never asked.
    if await ask(1) != [(STAND_IN, ANSWERS, OK, level)]:
        raise CheckFailedError("an agent with no pin did not answer from its own level")

    # A pin no step serves, and a pin by somebody who may not route, are each refused.
    unserved = await pin("served-by-no-step")
    if isinstance(unserved, PinView) or getattr(unserved, "status_code", None) != 422:
        raise CheckFailedError("a pin naming a model no step serves was accepted")
    reader = await StoredPrincipals(h.sessions).live_principal(s.reader)
    if reader is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    try:
        await pin(
            PINNED_MODEL,
            SimpleNamespace(
                caller=SimpleNamespace(principal=reader), reach=await h.reach(s.reader), now=h.now
            ),
        )
    except Absent:
        pass
    else:
        raise CheckFailedError("a reader who may not route pinned an agent's model")

    # Pinned: the pinned step answers first, in the level that holds it.
    taken = await pin(PINNED_MODEL)
    if not isinstance(taken, PinView) or (taken.provider, taken.model) != (STAND_IN, PINNED_MODEL):
        raise CheckFailedError("an administrator's pin was not taken by the pin route")
    if await ask(2) != [(STAND_IN, PINNED_MODEL, OK, Tier.HEAVY.value)]:
        raise CheckFailedError("an agent's pinned model was not tried first")

    # Pinned to a step that cannot connect: the agent's level answers behind it.
    await pin(UNREACHABLE)
    if await ask(3) != [
        (STAND_IN, UNREACHABLE, CONNECTION_ERROR, Tier.HEAVY.value),
        (STAND_IN, ANSWERS, OK, level),
    ]:
        raise CheckFailedError("the agent's level did not answer behind a pin that failed")
    if s.responder.sent_to(STAND_IN_ADDRESS, PINNED_MODEL) != 1:
        raise CheckFailedError("the pinned model was asked other than when it was pinned")


# ---------------------------------------------- M28.2.1, M28.2.3: the permission canaries
@check(
    leaves=("M28.2.1", "M28.2.3"),
    sentence=(
        "The scheduled canary run's own functions, given a question of the check's own, ask as "
        "three personas, the asker holding nothing, a buyer granted the price list in "
        "acceptance_a and an outsider in acceptance_b: each is offered exactly the tools its "
        "grants admit, the buyer more than nobody, a price nothing holds gets one answer from all "
        "three, and the buyer alone is told a real price."
    ),
)
async def three_personas_are_told_one_absence_and_offered_their_own_tools(h: Harness) -> None:
    from sqlalchemy import insert

    from brain.api_routes import field_policies, row_readers
    from brain.connectors.projection import ProjectedRecord
    from brain.core.envelope import SideEffect
    from brain.gate.catalogue import AgentCeiling, project
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.gate.rule_store import load_rules
    from brain.knowledge.columns import PRICE_LIST
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.canary_run import (
        CANARY_AGENT,
        NOBODY,
        absent_question,
        ask_every_reach,
        distinct_reaches,
        minted_value,
        projection_check,
        said_to,
    )
    from brain.ops.connector_sync_store import record_upsert
    from brain.tables.fast_lane import FastPathRuleRow
    from brain.tools.startup import build_registry

    await h.found_departments()
    source = h.settings.tool_source
    rule = {
        "rule_id": f"acceptance_{h.run}_price",
        "template": "What is the sell price of {name}?",
        "slot": "name",
        "source": source,
        "entity": PRICE_LIST.entity,
        "match_field": "name",
        "answer_field": "sell_price",
    }
    await h.execute(*h.attributed(), insert(FastPathRuleRow).values(**rule, created_by=h.actor))
    item, price = h.word(), "417.00"
    row = ProjectedRecord(
        source=source,
        entity=PRICE_LIST.entity,
        source_id=f"acceptance-{h.word()}",
        last_seen_at=h.now,
        fields={"name": item, "sell_price": price},
    )
    async with h.sessions() as session, session.begin():
        await session.execute(record_upsert(row, {"name": item, "sell_price": price}))
    buyer, outsider = h.principal(A, "buyer"), h.principal(B, "outsider")
    reads = ("read:price_list", "read:price_list.name", "read:price_list.sell_price")
    await h.person(buyer, department=A, grants=tuple((one, Scope.unrestricted()) for one in reads))
    await h.person(outsider, department=B, grants=(("read:knowledge", Scope.department(B)),))

    # The three personas, through the one resolver and the run's own reckoning of distinct reaches.
    resolver = StoredEntitlements(h.sessions)
    nobody = await resolver.load(NOBODY, h.now)
    personas = distinct_reaches(
        [await resolver.load(one, h.now) for one in (buyer, outsider)], nobody=nobody
    )
    if [one.principal_id for one in personas] != [NOBODY, buyer, outsider]:
        raise CheckFailedError("the canaries did not ask as three personas, nobody first")
    registry = build_registry(source=source, records=SessionRowSource(h.sessions))
    definitions = registry.definitions()

    # M28.2.3: each persona's catalogue is exactly the tools its grants admit, and they differ.
    if any(projection_check(one, definitions, now=h.now) for one in personas):
        raise CheckFailedError("a persona was offered a tool its grants do not admit, or not one")
    ceiling = AgentCeiling(
        agent_id=CANARY_AGENT,
        allowed_tools=frozenset(one.name for one in definitions),
        max_side_effect=SideEffect.MONEY,
    )
    offered = [set(project(definitions, one, ceiling, now=h.now).names) for one in personas]
    price_tool = next(
        (one.name for one in definitions if (one.source, one.entity) == (source, "price_list")),
        None,
    )
    if offered[0] or price_tool is None or price_tool not in offered[1] - offered[2]:
        raise CheckFailedError("the personas' catalogues were not each their own")

    # M28.2.1: one question about a price nothing holds, asked as each persona, answers diffed.
    rules = await load_rules(h.sessions)
    run = await ask_every_reach(
        personas,
        definitions=definitions,
        rules=rules,
        readers=row_readers(registry),
        policies=field_policies(registry),
        now=h.now,
        value=minted_value(),
    )
    if rule["rule_id"] not in run.rules_asked:
        raise CheckFailedError("the canaries did not ask the question shape the install holds")
    if run.findings:
        raise CheckFailedError("the canaries told one persona's refusal apart from an absence")
    shape = next(one for one in rules if one.rule_id == rule["rule_id"])
    told = {
        one.principal_id: await said_to(
            absent_question(shape, item),
            one,
            rules=rules,
            readers=row_readers(registry),
            policies=field_policies(registry),
            now=h.now,
        )
        for one in personas
    }
    if price not in (told[buyer] or "") or any(
        price in (told[one] or "") for one in (NOBODY, outsider)
    ):
        raise CheckFailedError("the personas did not differ on a price one of them may read")
