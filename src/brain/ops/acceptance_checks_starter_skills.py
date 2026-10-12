"""The install acceptance check for the starter skill library: furnished, rehearsed, approved,
assigned.

M12.4.7 asks that an install hold eight starter skills, each approved, assignable and rehearsed
against its example tasks. The skills are `brain.tools.starter_skills`; what an install shows is
that furnishing writes them as the library holds anything, that each one's examples are rehearsed
through an agent that holds the tools they expect and cleared, that a person other than first run
approves each through the route the Skills screen presses, and that each is then assigned to an
agent and shown in what that agent reaches.

**The switch is turned on inside the check's transaction, and the install's own is left as it
is.** `brain.ops.features.STARTER_SKILLS_SWITCH` ships off, so on an install that has not chosen
to furnish, the check furnishes inside its transaction and rolls it back. On one that has, the
skills are already held and the check uses them as they are, undecided or approved: a name the
library holds is never written again, which is the rule being relied on. An install whose library
holds a starter skill an administrator rejected or retired says so and is not run, because
approving it would be the check overruling the install's own people.

**The approval is the check's, made by a reserved administrator, and is held.** Nobody on the
install has read these words in the check's transaction, so what is shown is that the path works
and not that the library holds eight approved skills. `docs/proof-sweep-holds.json` holds M12.4.7
until a person has approved them on the install (needs-rupash 181).

**Every example is rehearsed through an agent holding what the examples expect**, with the website
check registered over the install's own transport as the application registers it. The rehearsal is
a rehearsal of reach and says no more (`brain.tools.skill_examples`).

Task ids: M12.4.7
"""

from __future__ import annotations

from typing import Any, Final, cast

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1020

# What the check says, one sentence for each way the property can fail.
NOT_FURNISHED: Final = "furnishing did not leave all eight starter skills in the library"
APPROVED_BY_THE_PRODUCT: Final = "a starter skill was furnished already approved by nobody"
NOT_REHEARSABLE: Final = "a starter skill's examples were not cleared by a rehearsal"
NOT_APPROVED: Final = "a starter skill whose examples were rehearsed could not be approved"
NOT_ASSIGNED: Final = "an approved starter skill was not assigned to an agent that holds its tools"
LEFT_BY_THE_INSTALL: Final = (
    "this install's library holds a starter skill its people rejected or retired, so the check "
    "does not approve it over them"
)

#: Every capability the eight skills' tools are read under.
CAPABILITIES: Final = (
    "read:knowledge",
    "read:search_site",
    "read:analytics_property",
    "read:ticket",
    "read:hubspot_company",
    "read:hubspot_deal",
    "read:price_list",
    "read:domain",
    "read:zone",
    "read:dns_record",
    "read:website_check",
)


def _body(answered: Any) -> dict[str, Any]:
    import json

    return cast(dict[str, Any], json.loads(bytes(answered.body)))


@check(
    leaves=("M12.4.7",),
    sentence=(
        "Furnished with the starter skills switched on, the library holds all eight waiting for "
        "review; each one's examples are rehearsed through an agent that holds its tools and "
        "cleared, a reserved administrator approves each through the Skills screen's route, and "
        "each is assigned to the agent and reaches the tools it names."
    ),
)
async def the_starter_skills_are_furnished_rehearsed_and_assigned(
    h: Harness,
) -> None:
    import structlog

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        await _furnished(h)


async def _furnished(h: Harness) -> None:
    from brain.console.skill_library import LibrarySkill
    from brain.core.errors import Absent
    from brain.firstrun import GRANTED_BY
    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.acceptance_checks_skills import _administrator
    from brain.ops.acceptance_skill_console import _asking, _console, _request
    from brain.ops.acceptance_switch import switched
    from brain.ops.acceptance_workspace import installed_agent
    from brain.ops.features import STARTER_SKILLS_SWITCH
    from brain.ops.skill_store import StoredSkills
    from brain.ops.starter_skill_store import furnish_skills_when_on
    from brain.ops.webhook_delivery import SystemResolver
    from brain.ops.website_probe import HttpsProber
    from brain.skill_routes import (
        AssignAsked,
        RehearseAsked,
        ReviewAsked,
        assign_skill,
        rehearse_skill,
        review_skill,
    )
    from brain.tools.skills import SkillState, version_key
    from brain.tools.starter_skills import STARTER_SKILLS
    from brain.tools.startup import build_registry
    from brain.tools.website_check import WebsiteCheckTool

    await h.found_departments()
    await switched(h, STARTER_SKILLS_SWITCH, on=True)
    await furnish_skills_when_on(h.sessions, actor=GRANTED_BY, trace_id=h.trace_id, now=h.now)
    store = StoredSkills(h.sessions)

    newest: dict[str, LibrarySkill] = {}
    for one in await store.library():
        held = newest.get(one.name)
        if held is None or version_key(one.imported.skill.version) > version_key(
            held.imported.skill.version
        ):
            newest[one.name] = one
    if any(one.name not in newest for one in STARTER_SKILLS):
        raise CheckFailedError(NOT_FURNISHED)
    skills = [newest[one.name] for one in STARTER_SKILLS]
    if any(one.imported.state is SkillState.REJECTED for one in skills):
        raise CheckNotRunError(LEFT_BY_THE_INSTALL)
    for one in skills:
        if one.imported.state is SkillState.APPROVED and one.imported.reviewer in ("", GRANTED_BY):
            raise CheckFailedError(APPROVED_BY_THE_PRODUCT)

    admin = await _administrator(h, "starters")
    for capability in CAPABILITIES:
        await h.grant(admin, capability, Scope.unrestricted())
    tools = sorted({name for one in skills for name in one.imported.skill.tools})
    # A capability on a connected source's entity holds only while the agent names that source.
    sources = tuple(sorted({name.partition(".")[0] for name in tools} - {"knowledge", "website"}))
    agent = await installed_agent(
        h,
        admin,
        capabilities=CAPABILITIES,
        allowed_tools=tuple(tools),
        connectors=sources,
        suffix="_starters",
    )
    app = _console(h)
    app.state.tools = build_registry(
        source=h.settings.tool_source,
        records=SessionRowSource(h.sessions),
        website=WebsiteCheckTool(resolver=SystemResolver(), prober=HttpsProber()),
    )

    for one in skills:
        rehearsed = _body(
            await rehearse_skill(
                _request(app), one.digest, RehearseAsked(agent_id=agent), await _asking(h, admin)
            )
        )
        if not rehearsed.get("passed"):
            raise CheckFailedError(NOT_REHEARSABLE)
        if one.imported.state is not SkillState.APPROVED:
            try:
                await review_skill(
                    _request(app),
                    one.digest,
                    ReviewAsked(decision="approve"),
                    await _asking(h, admin),
                )
            except Absent:
                raise CheckFailedError(NOT_APPROVED) from None
        try:
            await assign_skill(
                _request(app), one.digest, AssignAsked(agent_id=agent), await _asking(h, admin)
            )
        except Absent:
            raise CheckFailedError(NOT_ASSIGNED) from None

    from brain.skill_routes import StoredAgentInstalls, installs_of, pins_of

    found = await StoredAgentInstalls(h.sessions).agent(agent)
    if found is None:
        raise CheckFailedError(NOT_ASSIGNED)
    async with h.sessions() as session:
        pairs = (await session.execute(installs_of([agent]))).all()
    pinned = {
        pin.skill_name
        for instance_row, version_row in pairs
        for pin in pins_of(instance_row, version_row, found.record)
    }
    if pinned != {one.name for one in STARTER_SKILLS}:
        raise CheckFailedError(NOT_ASSIGNED)
