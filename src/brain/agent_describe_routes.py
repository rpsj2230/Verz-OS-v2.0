"""Describe an agent in your own words and be handed a saved draft with suggestions (M20.5.3).

The builder already had every part of this and no way to use them in the order a person thinks in.
A person who wants an agent starts a draft, finds the Write step, finds the co-author on it and
asks. This is the same three acts in one: `agent_builder_routes.start_agent_draft` makes the draft,
`agent_coauthor_routes.suggest_changes` asks the model, and the answer comes back with the draft's
id, so the person lands on a draft of their own that already holds what they described, as
suggestions beside what the draft holds now. **Nothing here is a second co-author.** The words, the
paths it may write, the untrusted reply and the take-by-name rule are the domain's, called through
the two routes so a refusal a person reads is the one they would have read from the Write step.

**The draft is saved before the model is asked, and the suggestions are not applied.** Two
alternatives were rejected. Making the draft only when the model has answered would leave a person
who described their agent and had the call fail with nothing and nothing to retry from, where now
they have a blank draft in their list and the Write step's own ask. Writing the model's answer
into the draft as the draft's first revision would make a model's words an agent's without the act
`brain.builder.coauthor.THE_COAUTHOR_PROPOSES_AND_A_PERSON_DECIDES` exists to require: the person
described what they wanted, they did not read what came back. So the draft holds revision one, the
answer is a proposal against it, and taking it is the existing take, by name. Whether describing
should itself count as taking is a question for the owner and is on the Needs you page.

**Nothing that reaches is drafted, and the answer says so.** The co-author writes words and never
reach, so the tools an agent may call, what it may read, the knowledge it draws on and how closely
it is watched are not in the proposal, and neither are its channels, which are chosen at publish.
`NOT_DRAFTED` names each in words so that a person does not read a short proposal as a finished
agent. **Within the person's ceiling is therefore true by construction**: the draft that results
reaches nothing until its author names something, and what it names is held to what they hold by
the publish gate (M20.1.5), not by anything in this module.

**No model, no draft.** A process with no model, and a person who may not build, are refused
before the draft is made, so a describe that cannot be answered leaves nothing behind.

Task ids: M20.5.3
"""

from __future__ import annotations

import json
from typing import Any, Final

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.agent_builder_routes import (
    _TOLD,
    REFUSED,
    UNAVAILABLE,
    DraftStartAsked,
    _may_build,
    _no_draft_here,
    _not_changed,
    describing_is_on,
    start_agent_draft,
)
from brain.agent_coauthor_routes import (
    NO_MODEL_HERE,
    SuggestionAsked,
    SuggestionView,
    calls_of,
    suggest_changes,
)
from brain.api import API_PREFIX
from brain.api_routes import Asked
from brain.builder.coauthor import ASK_CHARS, checked_ask
from brain.builder.compose import BuilderError

# ------------------------------------------------------------------ written-down reasons
#: Why the answer lists what was not drafted.
A_SHORT_PROPOSAL_IS_NOT_A_FINISHED_AGENT: Final = (
    "The product writes an agent's words and never what it may reach, so a proposal is never the "
    "whole of an agent, and an answer that did not say so would read as one."
)

#: What a described draft does not hold, said in the words the Write step uses.
NOT_DRAFTED: Final[tuple[str, ...]] = (
    "The tools it may use and the permissions it holds: add them in the Write step. What it may "
    "reach is never suggested, and it can reach nothing you do not.",
    "The knowledge it draws on: set it on the agent's own page once it is published.",
    "The channels it answers on: you choose them when you publish.",
    "How closely it is watched: every agent starts at Shadow.",
)

DESCRIBE_PATH: Final = "/agent-drafts/describe"

#: What the co-author is asked, around the person's words.
INSTRUCTION: Final = (
    "Draft a new agent from this description. Propose its name, a one-line summary, its "
    "instructions, the skills it should follow and the connectors it needs.\n\nDescription:\n"
)

#: The longest description a person may give, so that the request around it still fits.
DESCRIPTION_CHARS: Final = ASK_CHARS - len(INSTRUCTION)

router = APIRouter(prefix=API_PREFIX, tags=["agents"])


class DescribeAsked(BaseModel):
    """What the person wants the agent to be, in their own words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str = Field(min_length=1, max_length=DESCRIPTION_CHARS)


class DescribedView(BaseModel):
    """The draft that was started, and what the model suggested for it, if it answered."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    draft_id: str
    agent_id: str
    #: The draft's revision, which taking a suggestion names.
    revision: int
    #: The suggestions as the Write step draws them, taken through its own route, or null when the
    #: model could not be asked or its answer could not be read.
    suggestion: SuggestionView | None
    #: Why there is no suggestion, in words, when there is none.
    told: str | None = None
    not_drafted: list[str] = Field(default_factory=lambda: list(NOT_DRAFTED))


def _said(answer: Any) -> dict[str, Any]:
    """A route's JSON body as a mapping."""
    body = json.loads(bytes(answer.body))
    return body if isinstance(body, dict) else {}


@router.post(DESCRIBE_PATH, status_code=201, response_model=DescribedView, responses=_TOLD)
async def describe_an_agent(request: Request, body: DescribeAsked, asked: Asked) -> JSONResponse:
    """Start a draft of the caller's own and ask the co-author for what they described.

    Refused before anything is made for a caller who may not build, with the switch off (as the one
    404 a draft that is not there gets), for a request that is blank or too long and on a process
    with no model. Otherwise the draft exists when this answers, and so does the proposal unless the
    model could not answer, in which case `told` says why and the draft can be asked again from the
    Write step.
    """
    await _may_build(request, asked)
    if not await describing_is_on(request):
        raise _no_draft_here(asked, "describe is off")
    try:
        # The person's own words are checked on their own: the instruction around them is never
        # blank, so a request of nothing but spaces would otherwise pass as a question.
        checked_ask(body.description)
        ask = checked_ask(INSTRUCTION + body.description.strip())
    except BuilderError as refused:
        return _not_changed(REFUSED, str(refused))
    if calls_of(request) is None:
        return _not_changed(UNAVAILABLE, NO_MODEL_HERE)
    started = _said(await start_agent_draft(request, DraftStartAsked(), asked))
    draft_id, agent_id = str(started["draft_id"]), str(started["agent_id"])
    revision = int(started["revision"])
    answered = await suggest_changes(
        request, draft_id, SuggestionAsked(revision=revision, ask=ask), asked
    )
    said = _said(answered)
    view = (
        DescribedView(
            draft_id=draft_id,
            agent_id=agent_id,
            revision=revision,
            suggestion=SuggestionView.model_validate(said),
        )
        if answered.status_code == 200
        else DescribedView(
            draft_id=draft_id,
            agent_id=agent_id,
            revision=revision,
            suggestion=None,
            told=str(said.get("sentence", "")) or None,
        )
    )
    return JSONResponse(status_code=201, content=view.model_dump(mode="json"))
