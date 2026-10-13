"""The install acceptance check for a skill described in conversation and drafted by the model.

M12.4.14 asks that a person create a skill by describing it, that the system draft the skill with
its instructions, the knowledge it needs, the tools and some example tasks, and that the draft land
unreviewed and not executable, exactly like an import. The route that does it
(`brain.skill_routes.draft_skill`) is pressed here as the administrator the Skills screen serves,
over the check's transaction, with the install's own tool registry and the install's own executor
asking a stand-in model.

**The model is a stand-in answering in the process**, as every check that needs a reply is: the
reply is a JSON skill that names a tool this install registers, a tool nobody registered and a
department nobody holds, so what is read is the product's refusal to keep what the install does not
have, which a real provider could not be made to write on the day a deploy is checked. Not run on an
install keeping text on its own hardware, for `brain.ops.acceptance_routing.standing_by`'s reason.

**What lands is read back from the library's own store**, and not from the route's answer: the
version is undecided, its instructions are withheld from an agent, its examples parse and its
tools and needs are the ones the install holds. Assigning it to an agent is refused by the library
as it refuses any skill nobody approved. And a person who may not add skills is refused with the
model never asked, and a switch left off refuses with the model never asked either.

Task ids: M12.4.14
"""

from __future__ import annotations

import json
from typing import Any, Final, cast

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_routing import StandIns
from brain.ops.acceptance_run import Harness

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1010

# What the check says, one sentence for each way the property can fail.
NOT_DRAFTED: Final = "a described skill was not added to the library as a draft"
OFF_WAS_ASKED: Final = "a skill was drafted, or a model asked, while the switch was off"
OUTSIDER_WAS_ASKED: Final = "a person who may not add skills was answered, or a model asked"
EXECUTABLE: Final = "a drafted skill was executable, or readable by an agent, before a review"
NOT_THE_INSTALLS: Final = "a drafted skill kept a tool or a department the install does not hold"
NOT_SAID: Final = "what was left out of a draft was not said to the person"
NO_EXAMPLES: Final = "a drafted skill carried no example task a rehearsal could read"
ASSIGNED: Final = "a drafted skill nobody approved was assigned to an agent"
NOT_ITS_WORDS: Final = "the model was not sent the person's description and the install's tools"

#: A tool and a department the install holds nothing of, made unique to the run by the check.
INVENTED_TOOL: Final = "acceptance.send_everything"


class DraftingStandIn(StandIns):
    """The stand-in provider, answering the one call with a skill as JSON, and keeping the
    requests it was sent."""

    def __init__(self, reply: str) -> None:
        super().__init__()
        self.reply = reply
        self.bodies: list[str] = []

    def __call__(self, request: Any) -> Any:
        import httpx

        self.bodies.append(request.content.decode("utf-8", "replace"))
        response: httpx.Response = super().__call__(request)
        if response.status_code != 200:
            return response
        body = json.loads(response.content)
        body["choices"][0]["message"]["content"] = self.reply
        return httpx.Response(200, json=body)


def _body(answered: Any) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(bytes(answered.body)))


@check(
    leaves=("M12.4.14",),
    sentence=(
        "A skill an administrator of acceptance_a describes lands undecided and unreadable by any "
        "agent, with example tasks and only the tools and departments this install holds, what was "
        "left out said, and cannot be assigned before a review; a person who may not add skills, "
        "or a switch left off, asks no model."
    ),
)
async def a_skill_described_in_conversation_lands_as_an_unreviewed_draft(h: Harness) -> None:
    import structlog

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        await _drafted(h)


async def _drafted(h: Harness) -> None:
    from brain.core.errors import Absent
    from brain.models.routing import DEFAULT_TIER
    from brain.ops.acceptance_checks_skill_reuse import switched
    from brain.ops.acceptance_checks_skills import _administrator, _changes
    from brain.ops.acceptance_models import STAND_IN, askable, models_for, pinned
    from brain.ops.acceptance_routing import ANSWERS, constrained, stand_in_drivers, step
    from brain.ops.acceptance_skill_console import _asking, _console, _request
    from brain.ops.acceptance_workspace import LOCAL_TOOL, installed_agent
    from brain.ops.features import SKILL_DRAFTING
    from brain.ops.skill_store import StoredSkills
    from brain.skill_draft_routes import SkillDescribed, draft_skill
    from brain.skill_routes import AssignAsked, assign_skill
    from brain.tools.skill_examples import examples_of
    from brain.tools.skills import SkillError, SkillState, body_of

    await h.found_departments()
    await constrained(h, ())
    name = f"acceptance_{h.run}_drafted"
    nowhere = f"acceptance_{h.run}_nowhere"
    reply = json.dumps(
        {
            "name": name.replace("_", "-"),
            "description": "Use when an acceptance check asks for the price of something",
            "instructions": "Read the price list.\nSay what it holds for the thing asked about.",
            "tools": [LOCAL_TOOL, INVENTED_TOOL],
            "knowledge": [A, nowhere],
            "examples": [
                {"task": "What does the price list say about hosting", "tools": [LOCAL_TOOL]},
                {"task": "Send everybody the price list", "tools": [INVENTED_TOOL]},
            ],
        }
    )
    responder = DraftingStandIn(reply)
    models = await models_for(h, standing=stand_in_drivers(h, responder))
    askable(await models.calls.planned(), STAND_IN)
    await pinned(h, (step(ANSWERS, tier=DEFAULT_TIER),))

    admin = await _administrator(h, "drafter")
    outsider = h.principal(A, "outsider")
    await h.person(outsider, department=A)
    app = _console(h)
    app.state.models = models
    description = f"Tell a person what the price list holds {h.word()}"
    ask = SkillDescribed(description=description)

    async def refused(who: str) -> bool:
        try:
            await draft_skill(_request(app), ask, await _asking(h, who))
        except Absent:
            return True
        return False

    # Off, as an install ships it: nothing is drafted and no model is asked.
    if not await refused(admin) or responder.bodies:
        raise CheckFailedError(OFF_WAS_ASKED)
    await switched(h, SKILL_DRAFTING, on=True)
    if not await refused(outsider) or responder.bodies:
        raise CheckFailedError(OUTSIDER_WAS_ASKED)

    answered = _body(await draft_skill(_request(app), ask, await _asking(h, admin)))
    skill = answered.get("skill", {})
    if not skill.get("digest") or skill.get("review") != "pending":
        raise CheckFailedError(NOT_DRAFTED)
    sent = " ".join(responder.bodies)
    if description not in sent or LOCAL_TOOL not in sent:
        raise CheckFailedError(NOT_ITS_WORDS)

    kept = await StoredSkills(h.sessions).skill(str(skill["digest"]))
    if kept is None or kept.imported.state is not SkillState.IMPORTED:
        raise CheckFailedError(NOT_DRAFTED)
    if kept.imported.is_executable():
        raise CheckFailedError(EXECUTABLE)
    try:
        body_of(kept.imported)
    except SkillError:
        pass
    else:
        raise CheckFailedError(EXECUTABLE)
    drafted = kept.imported.skill
    if drafted.tools != (LOCAL_TOOL,) or drafted.knowledge != (A,):
        raise CheckFailedError(NOT_THE_INSTALLS)
    left_out = {str(one.get("what")) for one in answered.get("findings", [])}
    if left_out != {INVENTED_TOOL, nowhere}:
        raise CheckFailedError(NOT_SAID)
    if len(examples_of(drafted)) != 2:
        raise CheckFailedError(NO_EXAMPLES)
    said = [(actor, d.get("change")) for actor, d in await _changes(h, f"skill:{drafted.name}")]
    if said != [(admin, "imported")]:
        raise CheckFailedError(NOT_DRAFTED)

    agent = await installed_agent(h, admin, allowed_tools=(LOCAL_TOOL,), suffix="_drafting")
    try:
        await assign_skill(
            _request(app),
            str(skill["digest"]),
            AssignAsked(agent_id=agent),
            await _asking(h, admin),
        )
    except Absent:
        return
    raise CheckFailedError(ASSIGNED)
