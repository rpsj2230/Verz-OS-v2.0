"""The install acceptance check for an agent's run reading what it is assigned: skills and level.

`brain.api_routes.agent_run_of` builds the selected agent's run on every question, with the skill
pins the Skills screen reads from its install and the library they name, and the model step shows
the model one card per approved pinned skill, a name, a description and a version, and never a
body. Until 2026-10-06 `/answer` handed every run no pins, so an assigned skill changed nothing an
answer did (`brain.api_routes.AN_AGENT_RUNS_THE_SKILLS_IT_IS_ASSIGNED`).

**What the model is sent is read where the model receives it.** The model is a stand-in answering
in the process (`brain.ops.acceptance_routing.StandIns`), and this check keeps the body of every
request it is sent. The assigned skill's card must be in the request asked through the agent, its
body must not, a skill the library approved and nobody assigned must not appear, and a question
asked with no agent picked carries no card at all. Rejected: reading `skill_uses` off the ledger,
which records that cards were offered and not that the model was shown them.

**The level is the agent's.** The one stand-in step sits at the agent's level, and the request row
says the question was routed to that level because the agent pins it, which is
`brain.ops.acceptance_routing`'s M5.6.3 reading, asked here of an agent carrying a skill.

Not claimed: M12.2.8's second half, a skill's body handed to the model on demand. The answer lane
asks a model with no tool catalogue, so nothing can ask for a body; that waits for the run's tool
loop (M13.7.2).

Task ids: M27.12.1
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from brain.models.routing import Tier
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS
from brain.ops.acceptance_routing import StandIns
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    import httpx

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 406

#: The agent's level, one the install's default for an unpinned question is not.
AGENT_LEVEL: Final = Tier.HEAVY

NOT_ANSWERED: Final = "a question asked through an agent with an assigned skill was not answered"
NO_CARD: Final = "an agent's run did not show the model the skill it is assigned"
BODY_SENT: Final = "an agent's run sent the model a skill's body before it was asked for"
UNASSIGNED_SENT: Final = "an agent's run showed the model a skill it is not assigned"
CARD_WITHOUT_AN_AGENT: Final = "a question with no agent picked showed the model an agent's skill"
NOT_ITS_LEVEL: Final = "an agent's question was not routed to the level the agent pins"


@dataclass
class _Kept(StandIns):
    """The stand-in, keeping the body of every request it is sent."""

    bodies: list[str] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(request.content.decode("utf-8"))
        return super().__call__(request)

    def sent(self) -> str:
        """Every message of the last request, as the model would read them."""
        if not self.bodies:
            return ""
        messages = json.loads(self.bodies[-1]).get("messages", [])
        return "\n".join(str(one.get("content", "")) for one in messages)


@check(
    leaves=("M27.12.1",),
    sentence=(
        "A member of acceptance_a asks through an agent assigned an approved skill: the model is "
        "shown that skill's name and description and not its body, and no skill the agent is not "
        "assigned; with no agent picked it is shown none; and the question is routed to the level "
        "the agent pins."
    ),
)
async def an_agents_run_reads_its_assigned_skills_and_its_level(h: Harness) -> None:
    from brain.console.skill_library import added, decided, read_package
    from brain.models.routing import TierBasis
    from brain.ops.acceptance_checks_skills import (
        _administrator,
        _an_agent,
        _assign,
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
    from brain.ops.skill_store import StoredSkills

    reader, paired = await a_reader_with_a_document(h)
    await constrained(h, ())
    admin = await _administrator(h, "skills")
    reach = await h.reach(admin)
    store = StoredSkills(h.sessions)
    skills = []
    for word in ("assigned", "unassigned"):
        made = added(read_package("SKILL.md", _skill_md(_named(h, word))), by=admin, at=h.now)
        await _store(h, made, reach)
        if not await store.decide(
            decided(made, reviewer=admin, approve=True, at=h.now),
            ent_hash=reach.ent_hash(),
            trace_id=h.trace_id,
        ):
            raise CheckFailedError(NOT_ANSWERED)
        skills.append(made)
    assigned, unassigned = skills
    agent = await _an_agent(h, admin, tier=AGENT_LEVEL, capabilities=KNOWLEDGE_READS)
    await _assign(h, assigned.digest, agent, reach)

    responder = _Kept()
    models = await models_for(h, standing=stand_in_drivers(h, responder))
    askable(await models.calls.planned(), STAND_IN)
    # A step at the agent's level and one at the install's default, so a run that ignored the
    # agent's level would still be answered and the request row would say where it went.
    await pinned(h, (step(ANSWERS, tier=AGENT_LEVEL), step(ANSWERS)))
    app = await asking_app(h, models)
    app.state.agent_roster = roster_over(h)

    if not answered(await asking(h, app, reader, paired.question, 1, agent=agent)):
        raise CheckFailedError(NOT_ANSWERED)
    sent = responder.sent()
    card = assigned.imported.skill
    if card.name not in sent or card.description not in sent:
        raise CheckFailedError(NO_CARD)
    if card.body.strip() in sent:
        raise CheckFailedError(BODY_SENT)
    if unassigned.imported.skill.name in sent:
        raise CheckFailedError(UNASSIGNED_SENT)
    row = await request_of(h, trace_of(h, 1))
    if (
        row.get("routed_tier") != AGENT_LEVEL.value
        or row.get("tier_basis") != TierBasis.PINNED.value
        or row.get("selected_agent") != agent
    ):
        raise CheckFailedError(NOT_ITS_LEVEL)

    if not answered(await asking(h, app, reader, paired.question, 2)):
        raise CheckFailedError(NOT_ANSWERED)
    if card.name in responder.sent():
        raise CheckFailedError(CARD_WITHOUT_AN_AGENT)
