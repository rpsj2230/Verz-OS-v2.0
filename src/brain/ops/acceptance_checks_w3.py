"""Install acceptance check for the wave-three milestone: an agent installed from a template,
answering with knowledge and memory.

The milestone leaf says what must be live once wave three is done, and every clause of it is
load-bearing: **an agent installed from a template, a person asking through it, the answer built
from the person's own department's document, and the person's own memory shown to the model as a
hint beside the question.** Each part has its own check (`acceptance_checks_templates` installs
every built-in template, `acceptance_checks_agent_reach` narrows a person through an agent,
`acceptance_checks_memory` forms and recalls a memory), and the milestone asks whether they
compose. This check drives them together, in one transaction, as a person meets them.

**The agent is the catalogue's knowledge agent, installed from the gallery.** `internal_helpdesk`
is the template whose own description reads policy documents and holds no capability naming a
person, so the knowledge clause and the memory clause meet in it. It is installed by an
administrator of the first reserved department over a copy of the shipped manifest signed with a
key made for the check, because the worker holds no template signing key
(`acceptance_checks_templates.THE_WORKER_HOLDS_NO_SIGNING_KEY`), then enabled with the lifecycle
button, and nothing is installed or enabled for anybody else.

**The model is a stand-in that keeps its prompt, and the sentence says so.** Whether a model is
shown a document and a memory is a fact about the prompt the install builds, and a provider adds a
cost and a vendor's words to it (`acceptance_checks_memory.A_MODEL_THAT_KEEPS_ITS_PROMPT_STANDS_IN_
FOR_THE_PROVIDER`). So the answer is composed by the stand-in and everything before it is the
install's own: the roster, the agent's ceiling, the passage search, the recall and the prompt. A
real question put to a real model is the owner's, and the milestone's task stays held on it.

**The agent is a lens in both directions here too.** A person of the other reserved department
naming the agent is outside its audience and is answered as for no agent, so the document is not
told and no memory of anybody's reaches them; a colleague beside the asker in the same department
is answered from the document and is sent none of the asker's memory.

Task ids: M38.5.1, M38.2.2.4
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_memory import (
    PAIRED_QUESTION,
    REPLY,
    KeptPrompts,
    ask,
    memory_app,
    people,
)
from brain.ops.acceptance_checks_templates import (
    _administrator,
    _asking,
    _copy,
    _gallery,
    _install,
    _request,
)
from brain.ops.acceptance_models import asked
from brain.ops.acceptance_routing import roster_over
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.models.driver import DriverMessage, DriverResponse

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 620

A, B = RESERVED_DEPARTMENTS

#: The catalogue's knowledge agent: reads policy documents, names no person.
KNOWLEDGE_AGENT: Final = "internal_helpdesk"


@dataclass
class _Agentic(KeptPrompts):
    """The stand-in of `acceptance_checks_memory`, answering an agent's run as a model would: it
    asks for the document search once with the question it was asked, then answers in words that
    quote nothing it was shown. Every prompt it is sent is kept."""

    question: str = ""
    asked_for: int = 0

    async def complete(self, messages: Sequence[DriverMessage], **kwargs: Any) -> DriverResponse:
        from brain.knowledge.document_tools import SEARCH_DOCUMENTS
        from brain.models.driver import DriverResponse, TokenUsage

        self.sent.append(tuple(messages))
        self.categories.append(tuple(one.value for one in kwargs.get("categories", ())))
        self.caps.append(kwargs.get("max_output_tokens"))
        kwargs["meter"].attempted()
        if self.asked_for == 0:
            self.asked_for += 1
            reply = json.dumps({"tool": SEARCH_DOCUMENTS, "arguments": {"question": self.question}})
        else:
            reply = json.dumps({"answer": REPLY})
        response = DriverResponse(
            deployment_id="acceptance_stand_in",
            model="acceptance_stand_in",
            text=reply,
            usage=TokenUsage(input_tokens=0, output_tokens=0),
            finish_reason="stop",
        )
        kwargs["meter"].answered(
            response, provider="acceptance_stand_in", agent_version=kwargs.get("agent_version")
        )
        return response


async def _selected(h: Harness, n: int) -> str | None:
    """The agent the install's request row says answered the question asked as number `n`."""
    from sqlalchemy import text

    from brain.ops.acceptance_models import trace_of

    found = await h.execute(
        text("SELECT selected_agent FROM obs.request_telemetry WHERE trace_id = :trace").bindparams(
            trace=trace_of(h, n)
        )
    )
    row = found.first()
    return None if row is None or row[0] is None else str(row[0])


@check(
    leaves=("M38.2.2.4",),
    sentence=(
        "The catalogue's knowledge agent is installed and enabled by an administrator of "
        "acceptance_a; a member asking through it is answered from their department's document, "
        "cited, with their memory sent to the model as a hint and not in the answer; a colleague "
        "is sent none of it, and a member of acceptance_b naming the agent is answered as for no "
        "agent. The model is a stand-in that keeps its prompt."
    ),
)
async def a_template_agent_answers_with_knowledge_and_memory(
    h: Harness,
) -> None:
    from brain.agent_lifecycle_routes import LifecycleStateAsked, enable_agent
    from brain.agents.catalogue import CATALOGUE
    from brain.agents.install_store import version_values
    from brain.agents.template import publish
    from brain.gate.model_lane import HINTS_HEADING
    from brain.ops.acceptance_checks_memory import a_document
    from brain.tables.template import TemplateVersionRow

    shipped = next(one for one in CATALOGUE if one.identity.template_id == KNOWLEDGE_AGENT)

    placed = await people(h)
    words = await a_document(h)
    administrator = await _administrator(h)
    from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
    from brain.core.scope import Scope

    await h.grant(administrator, AGENT_LIFECYCLE_CAPABILITY.value, Scope.department(A))

    key = secrets.token_hex(32)
    gallery = _gallery(h, key)
    signed = publish(
        _copy(shipped, f"acceptance_{h.run}_{KNOWLEDGE_AGENT}"),
        key=key,
        signed_by=administrator,
        at=h.now,
    )
    await h.execute(
        *h.attributed(administrator),
        insert(TemplateVersionRow).values(**version_values(signed)),
    )
    made = await _install(h, gallery, administrator, signed)
    agent_id = made["agent"]["agent_id"]
    await enable_agent(
        _request(gallery),
        agent_id,
        LifecycleStateAsked(expected_state="disabled"),
        await _asking(h, administrator),
    )

    stand_in = _Agentic(question=PAIRED_QUESTION.format(key=words.key))
    app = await memory_app(h, stand_in, recorded=True)
    app.state.agent_roster = roster_over(h)
    hint = h.word()
    await ask(h, app, placed.member, f"Remember that I want {hint} in every reply.", 1)
    # That question is answered in one turn; what follows is each question's own two.
    before = len(stand_in.sent)
    stand_in.asked_for = 0
    answered = await asked(
        h, app, placed.member, PAIRED_QUESTION.format(key=words.key), 2, agent=agent_id
    )
    turns = stand_in.sent[before:]
    if await _selected(h, 2) != agent_id:
        raise CheckFailedError(
            "the question was not answered by the agent installed from the template"
        )
    if answered.composed is None or len(turns) != 2:
        raise CheckFailedError("a question through the installed agent was not answered")
    told = "\n".join(message.content for sent in turns for message in sent[1:])
    if words.value not in told:
        raise CheckFailedError("the installed agent's model was not shown the document")
    if f"- I want {hint} in every reply" not in told or HINTS_HEADING not in told:
        raise CheckFailedError("the installed agent's model was not shown the asker's memory")
    if hint in turns[0][0].content:
        raise CheckFailedError("an asker's memory reached the prompt region every caller shares")
    documents = [] if answered.provenance is None else answered.provenance.documents
    if not documents:
        raise CheckFailedError("an answer through the installed agent did not cite its document")
    if hint in "\n".join(answered.frames):
        raise CheckFailedError("an answer through the installed agent carried the asker's memory")

    before = len(stand_in.sent)
    stand_in.asked_for = 0
    await asked(h, app, placed.colleague, PAIRED_QUESTION.format(key=words.key), 3, agent=agent_id)
    turns = stand_in.sent[before:]
    told = "\n".join(message.content for sent in turns for message in sent[1:])
    if len(turns) != 2 or words.value not in told or await _selected(h, 3) != agent_id:
        raise CheckFailedError("a colleague was not answered from the document through the agent")
    if hint in told:
        raise CheckFailedError("a colleague's model was shown somebody else's memory")

    before = len(stand_in.sent)
    stand_in.asked_for = 0
    await asked(h, app, placed.other, PAIRED_QUESTION.format(key=words.key), 4, agent=agent_id)
    if await _selected(h, 4) == agent_id:
        raise CheckFailedError("a member outside the agent's audience was answered by it")
    if any(
        words.value in message.content or hint in message.content
        for sent in stand_in.sent[before:]
        for message in sent
    ):
        raise CheckFailedError("an agent lent another department's member a document or a memory")
