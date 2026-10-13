"""The install acceptance check for reusing one approved skill across agents.

M12.4.10 asks that one library skill be given to two agents and change what both runs do, that an
assignment whose tool or knowledge needs exceed the agent is refused saying what is missing, and
that taking it off one agent leaves it on the other with the detachment kept. Each half has an
install check of its own (the card shown in a run, the body on demand, the script through the
sandbox); what no check showed was the reuse itself, which is the library's skill reaching two
agents as one item and leaving one of them without touching the other.

**The routes are the ones the Skills screen presses.** `assign_skill` and `detach_skill`, as the
administrator the page serves, over the check's transaction, with the install's own tool registry,
so the refusal is read from the route's answer and not from the function under it. The switch the
refusal sits behind (`brain.ops.features.SKILL_NEEDS`) is turned on inside the transaction and
rolled back with it. Rejected: asking `assignment` directly, which would pass with the route never
reading the switch, the defect a switch nothing reads is.

**What a run does is read where the model receives it.** The stand-in model keeps the body of every
request it is sent, as `brain.ops.acceptance_checks_skill_runs` does, and the skill's name and
description must be in the request of a question asked through each agent that holds it, and absent
from the request of the agent it was taken off. Rejected: counting the assignment rows, which say a
skill was written to an agent and not that its run was changed.

**The skill declares the knowledge it needs as a department.** The reserved department is one
the two agents cover and the third agent's scope does not, so the refusal for knowledge is the
route's own and not a stand-in for it. The tool refusal is a second skill naming the install's own
price list tool and an agent with no tools.

Not claimed here: the body only on demand (M12.2.8) and the script only through the sandbox (M12.2.9
and M12.4.11), which `brain.ops.acceptance_checks_skill_tools` proves on the same library and which
name M12.4.10 beside this check.

Task ids: M12.3.3, M12.4.10
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1000

# What the check says, one sentence for each way the property can fail.
NOT_ANSWERED: Final = "a question asked through an agent holding the reused skill was not answered"
NOT_ASSIGNED: Final = "an approved skill was not assigned to an agent that can serve it"
NEEDS_NOT_REFUSED: Final = "a skill was assigned to an agent that cannot serve what it needs"
NEEDS_NOT_SAID: Final = "a refusal did not say which tool or knowledge the agent lacks"
SWITCH_NOT_READ: Final = "the needs rule was applied with its switch off or ignored when on"
NO_CARD: Final = "an agent given the reused skill was not shown it in its run"
CARD_AFTER_DETACH: Final = "an agent the skill was taken off was still shown it in its run"
OTHER_AGENT_LOST_IT: Final = "taking the skill off one agent took it off the other"
NO_HISTORY: Final = "a detachment was not kept as a row and a ledger entry beside the assignment"


async def switched(h: Harness, feature: Any, *, on: bool) -> None:
    """A feature's switch, set in the check's transaction with the attribution every settings
    write carries, and rolled back with the rest of the check."""
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.features import switch
    from brain.tables.audit import attributed_to

    async with h.sessions() as session:
        for statement in attributed_to(
            actor_id=h.actor, ent_hash=SET_UP_REACH, trace_id=h.trace_id
        ):
            await session.execute(statement)
        await switch(session, feature, on=on, by=h.actor)
        await session.commit()


async def _needs_switched(h: Harness, *, on: bool) -> None:
    """The needs rule's switch. See `switched`."""
    from brain.ops.features import SKILL_NEEDS

    await switched(h, SKILL_NEEDS, on=on)


async def _refusal_of(call: Any) -> str | None:
    """What a route refused with, in its own words, or None when it answered."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent as refused:
        return str(refused.public_message)
    return None


@check(
    leaves=("M12.3.3", "M12.4.10"),
    sentence=(
        "One approved skill needing a department's knowledge is assigned to two agents of "
        "acceptance_a and both are shown it in their runs; an agent whose scope is another "
        "department's and an agent with none of the tools another skill names are each refused "
        "with what they lack, and nothing is assigned; taken off one agent it is gone from that "
        "agent's run, kept as a detachment, and still on the other."
    ),
)
async def a_skill_is_reused_by_two_agents_and_refused_where_unservable(
    h: Harness,
) -> None:
    import structlog
    from sqlalchemy import func, select

    from brain.audit.ledger import AuditAction
    from brain.console.skill_library import added, decided, read_package
    from brain.ops.acceptance_checks_skill_runs import _Kept
    from brain.ops.acceptance_checks_skills import (
        _administrator,
        _changes,
        _named,
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
    from brain.ops.acceptance_skill_console import _asking, _console, _request
    from brain.ops.acceptance_workspace import LOCAL_READ, LOCAL_TOOL, installed_agent
    from brain.ops.skill_store import StoredSkills
    from brain.skill_routes import AssignAsked, assign_skill, detach_skill, skill_library
    from brain.tables.skill import SkillAssignmentRow, SkillDetachmentRow

    reader, paired = await a_reader_with_a_document(h)
    await constrained(h, ())
    admin = await _administrator(h, "reuse")
    await h.grant(admin, LOCAL_READ, Scope.unrestricted())
    reach = await h.reach(admin)
    store = StoredSkills(h.sessions)

    async def approved(word: str, *lines: str) -> Any:
        made = added(
            read_package(
                "SKILL.md",
                _skill_md(
                    _named(h, word),
                    description=f"Use when an acceptance check reuses the {word} skill",
                    extra=lines,
                ),
            ),
            by=admin,
            at=h.now,
        )
        await _store(h, made, reach)
        if not await store.decide(
            decided(made, reviewer=admin, approve=True, at=h.now),
            ent_hash=reach.ent_hash(),
            trace_id=h.trace_id,
        ):
            raise CheckFailedError(NOT_ASSIGNED)
        return made

    reused = await approved("reused", f"knowledge: [{A}]")
    tooling = await approved("tooling", f"tools: [{LOCAL_TOOL}]")

    held = (LOCAL_READ, *KNOWLEDGE_READS)
    first = await installed_agent(
        h, admin, capabilities=held, allowed_tools=(LOCAL_TOOL,), suffix="_first"
    )
    second = await installed_agent(
        h, admin, capabilities=held, allowed_tools=(LOCAL_TOOL,), suffix="_second"
    )
    bare = await installed_agent(h, admin, suffix="_bare")
    elsewhere = await installed_agent(
        h, admin, scope=Scope.department(B), suffix="_elsewhere", allowed_tools=(LOCAL_TOOL,)
    )
    app = _console(h)

    async def assign(digest: str, agent: str) -> Any:
        return await assign_skill(
            _request(app), digest, AssignAsked(agent_id=agent), await _asking(h, admin)
        )

    async def counted(table: Any, agent: str, digest: str) -> int:
        async with h.sessions() as session:
            counting = (
                select(func.count())
                .select_from(table)
                .where(table.agent_id == agent, table.digest == digest)
            )
            return int((await session.execute(counting)).scalar_one())

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        # The rule is off as an install ships it: the same assignment is made, and said to reach
        # nothing, which is the screen's way of showing a skill an agent cannot fully use.
        if await _refusal_of(assign(tooling.digest, bare)) is not None:
            raise CheckFailedError(SWITCH_NOT_READ)
        await detach_skill(
            _request(app), tooling.digest, AssignAsked(agent_id=bare), await _asking(h, admin)
        )

        await _needs_switched(h, on=True)
        for digest, agent in ((reused.digest, first), (reused.digest, second)):
            if (await _refusal_of(assign(digest, agent))) is not None:
                raise CheckFailedError(NOT_ASSIGNED)

        said = await _refusal_of(assign(tooling.digest, bare))
        if said is None:
            raise CheckFailedError(NEEDS_NOT_REFUSED)
        if LOCAL_TOOL not in said or "nothing was assigned" not in said:
            raise CheckFailedError(NEEDS_NOT_SAID)
        said = await _refusal_of(assign(reused.digest, elsewhere))
        if said is None:
            raise CheckFailedError(NEEDS_NOT_REFUSED)
        if A not in said or "nothing was assigned" not in said:
            raise CheckFailedError(NEEDS_NOT_SAID)
        if await counted(SkillAssignmentRow, bare, tooling.digest) != 1:
            # One row is the first assignment, made while the rule was off; a second would be the
            # refusal written anyway.
            raise CheckFailedError(NEEDS_NOT_REFUSED)
        if await counted(SkillAssignmentRow, elsewhere, reused.digest) != 0:
            raise CheckFailedError(NEEDS_NOT_REFUSED)

        # What each run is shown, read where the model receives it.
        responder = _Kept()
        models = await models_for(h, standing=stand_in_drivers(h, responder))
        askable(await models.calls.planned(), STAND_IN)
        await pinned(h, (step(ANSWERS),))
        asked_app: FastAPI = await asking_app(h, models)
        asked_app.state.agent_roster = roster_over(h)
        card = reused.imported.skill

        async def shown_to(agent: str, n: int) -> bool:
            if not answered(await asking(h, asked_app, reader, paired.question, n, agent=agent)):
                raise CheckFailedError(NOT_ANSWERED)
            sent = responder.sent()
            return card.name in sent and card.description in sent

        if not await shown_to(first, 1) or not await shown_to(second, 2):
            raise CheckFailedError(NO_CARD)

        await detach_skill(
            _request(app), reused.digest, AssignAsked(agent_id=first), await _asking(h, admin)
        )
        if await shown_to(first, 3):
            raise CheckFailedError(CARD_AFTER_DETACH)
        if not await shown_to(second, 4):
            raise CheckFailedError(OTHER_AGENT_LOST_IT)
        library = await skill_library(
            _request(app), await _asking(h, admin), _list_for(reused.name)
        )
        running = {one.digest: one.agents_running for one in library.items}
        if running.get(reused.digest) != 1:
            raise CheckFailedError(OTHER_AGENT_LOST_IT)

    if await counted(SkillDetachmentRow, first, reused.digest) != 1:
        raise CheckFailedError(NO_HISTORY)
    if await counted(SkillAssignmentRow, first, reused.digest) != 1:
        raise CheckFailedError(NO_HISTORY)
    attached = await _changes(h, f"agent:{first}", action=AuditAction.COMPOSE_CHANGE.value)
    if [d.get("direction") for _, d in attached] != ["attached", "detached"]:
        raise CheckFailedError(NO_HISTORY)
    other = await _changes(h, f"agent:{second}", action=AuditAction.COMPOSE_CHANGE.value)
    if [d.get("direction") for _, d in other] != ["attached"]:
        raise CheckFailedError(OTHER_AGENT_LOST_IT)


def _list_for(name: str) -> Any:
    """The library's list narrowed to one skill by name, as the screen's search does."""
    from brain.api_routes import FILTER_SEPARATOR
    from brain.listing import ListAsked

    return ListAsked(filters=(f"name{FILTER_SEPARATOR}{name}",))
