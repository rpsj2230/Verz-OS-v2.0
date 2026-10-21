"""Install acceptance check for a personal agent following its owner when they move (M26.2.2).

A person's own agent is theirs and not their department's, so when the staff list moves them it
should need no edit and should reach what they reach now: the new department's knowledge and none
of the old one's. `brain.identity.lifecycle` argues this from the types; this asks the install's
own schema, through the objects the nightly run really writes, in the order the leaf names. A
personal agent is made for a member of acceptance_a, the staff sync's Starter pack step moves them
to acceptance_b, and the check reads three things before and after.

**What the agent reaches is `E_run(caller, agent)`, asked of the one intersection.** The agent is
made with an unrestricted scope, as a personal agent has no department to be cut by, so what its
owner's runs search is whatever the owner's own reach says. Before the move the run's knowledge
scope admits acceptance_a and not acceptance_b; after it, the reverse. **The agent's audience record
is the same row**, which is the half the leaf's note could not say was verified: the move edits no
agent. **Who may see the agent does not change**: its owner does, and a colleague who stayed in the
old department never does, before or after.

Not asked: an answer made through the agent. That needs a model, and the reach it would be given is
this reach; `brain.ops.acceptance_checks_agent_reach` asks the answer for an agent.

Task ids: M26.2.2
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before the roll-ups that read it. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1810

A, B = RESERVED_DEPARTMENTS


@check(
    leaves=("M26.2.2",),
    sentence=(
        "A member's personal agent, after the staff sync moves its owner to another department, is "
        "the same record and is still seen by its owner alone, and a run through it searches the "
        "new department's knowledge and none of the old one's."
    ),
)
async def a_personal_agent_reaches_the_new_department_when_its_owner_moves(h: Harness) -> None:
    from brain.agent_lifecycle_routes import StoredAgentLifecycles
    from brain.agents.model import AgentAudience, AgentRecord, visible_to
    from brain.console.workspace_capabilities import run_reach
    from brain.core.department import DEPARTMENT_FIELD
    from brain.core.scope import Scope
    from brain.gate.roster import viewer_for
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.search import KNOWLEDGE_READ
    from brain.knowledge.visibility import Visibility
    from brain.ops.acceptance_checks import KNOWLEDGE_READS
    from brain.ops.acceptance_checks_accounts import _joined
    from brain.ops.acceptance_checks_joiner_mover_leaver import _give, _listed, _roster
    from brain.ops.acceptance_checks_skills import _an_agent

    await h.found_departments()
    owner, colleague = h.principal(A, "mover_owner"), h.principal(A, "mover_colleague")
    for who in (owner, colleague):
        await h.person(who, department=A)
        await _joined(h, who)
    agent = await _an_agent(
        h,
        owner,
        capabilities=KNOWLEDGE_READS,
        scope=Scope.unrestricted(),
        audience=AgentAudience(level=Visibility.PERSONAL, owner_id=owner),
    )
    lifecycles = StoredAgentLifecycles(h.sessions)

    async def record() -> AgentRecord:
        found = await lifecycles.agent(agent)
        if found is None:
            raise CheckFailedError("a personal agent the check made was not in the agent table")
        return found.record

    async def reaches(department: str) -> bool:
        held = await record()
        scope = run_reach(await h.reach(owner), held).scope_for(KNOWLEDGE_READ, h.now)
        return scope is not None and scope.matches({DEPARTMENT_FIELD: department})

    async def seen_by(who: str) -> bool:
        person = await StoredPrincipals(h.sessions).live_principal(who)
        if person is None:
            raise CheckFailedError("a reserved person was not live in the directory")
        return visible_to((await record()).audience, viewer_for(person))

    await _give(h, _roster(_listed(h, owner, A), _listed(h, colleague, A)))
    before = await record()
    if not await reaches(A) or await reaches(B):
        raise CheckFailedError("a personal agent did not reach its owner's own department first")
    if not await seen_by(owner) or await seen_by(colleague):
        raise CheckFailedError("a personal agent was seen by somebody besides its owner")

    await _give(h, _roster(_listed(h, owner, B), _listed(h, colleague, A)))
    if await reaches(A) or not await reaches(B):
        raise CheckFailedError(
            "a personal agent did not follow its owner to the new department's knowledge"
        )
    if await record() != before:
        raise CheckFailedError("a personal agent's record was changed by its owner moving")
    if not await seen_by(owner) or await seen_by(colleague):
        raise CheckFailedError("who may see a personal agent changed when its owner moved")
