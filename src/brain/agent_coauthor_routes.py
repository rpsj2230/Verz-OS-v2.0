"""The co-author, over HTTP: ask for changes to a draft, and take the ones you choose.

`brain.builder.coauthor` has held `propose` and `accept` since M20.1.3, whole, tested and reached
by nothing, so the builder's one AI-assisted step had no way to be used. This module orders the
questions and is the executor's caller, and adds no rule of its own about what a model may change:
every refusal a person reads is the domain's sentence or one of the few named below.

**A proposal is data, and applying any part of it is a separate act by the draft's author.**
Asking (`POST .../suggestions`) calls a model and writes nothing; taking (`POST
.../suggestions/take`) is the author's own act, naming every change they take, and writes one
revision through the same save a typed edit goes through. What is not named is rejected, and
rejecting writes nothing, so there is no route for it: a page that drops the proposal has rejected
it. See `brain.builder.coauthor.THE_COAUTHOR_PROPOSES_AND_A_PERSON_DECIDES`.

**Nothing is stored between the two, and what comes back is judged again.** The proposal travels
in the response and is rebuilt from the request, and `Hunk` refuses a change to a path the
co-author may not write (the reach and the sealed paths) however the request came by it, `accept`
refuses a change whose before is not what the draft holds, and a proposal made against a revision
the draft has moved past is refused rather than rebased. So a proposal edited on its way back
changes nothing it was not shown. See `A_PROPOSAL_IS_MADE_AGAINST_ONE_REVISION`.

**Who may ask is the draft's author, and failing it looks like absence.** The builder's
capability, then the draft being theirs, are `brain.agent_builder_routes._own`'s, so somebody
else's draft, a draft that does not exist and a caller who may not build are one 404, and none of
them costs a model call. **An agent is a lens and never a principal**: the co-author writes words
into a draft, never reach, and the draft is published through the gate that decides what an agent
may reach.

**The call is an ordinary model call, and it is recorded as one.** The messages are
`brain.builder.coauthor.coauthor_messages`, the executor chooses the rung, and the call is metered
and its row and cost recorded as a provider check's are, so the spend page shows it. The prompt
carries the author's draft and nothing else of the install, and the data category it is recorded
under is `AGENT_DRAFT`, which says what left for the provider: text somebody typed into a draft,
and no company record. A process with no model, and a ladder that cannot answer, say so in words
and change nothing.

Task ids: M20.1.3
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final, Protocol

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.agent_builder_routes import (
    _TOLD,
    ALREADY_PUBLISHED,
    MOVED,
    NOT_THE_LATEST,
    REFUSED,
    SAVED_SINCE,
    UNAVAILABLE,
    DraftSavedView,
    _by,
    _latest,
    _not_changed,
    _own,
    _trace_id,
)
from brain.api import API_PREFIX
from brain.api_routes import Asked
from brain.builder.agent_drafts import AgentDraft, plain, published, state_of
from brain.builder.coauthor import (
    ASK_CHARS,
    REPLY_TOKENS,
    Hunk,
    Proposal,
    StaleProposalError,
    UnreadableReplyError,
    accept,
    checked_ask,
    coauthor_messages,
    read_reply,
)
from brain.builder.compose import BuilderError
from brain.builder.drafts import FIRST_REVISION, MemoryDraftStore, validity
from brain.builder.form import FIELD_WORDS, SECTION_TITLES
from brain.core.lane import Lane
from brain.gate.finish import Finished, ModelCallOutcome, Origin, RequestRecorder, finish
from brain.models.disclosure import DataCategory
from brain.models.driver import DriverMessage, DriverResponse, ProviderUnavailable
from brain.models.metering import Meter
from brain.models.routing import NoCompliantRoute, Tier
from brain.ops.model_service import ModelService
from brain.ops.telemetry_store import TelemetryRecorder
from brain.ops.usage_store import UsageRecorder

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why asking is the author's and taking is a separate act.
A_SUGGESTION_IS_NOT_A_CHANGE_UNTIL_ITS_AUTHOR_TAKES_IT: Final = (
    "Asking the co-author calls a model and writes nothing. A change reaches the draft only when "
    "its author takes it by name, as a save, so a model's suggestion cannot become part of an "
    "agent that somebody then publishes without anybody having chosen it."
)

# ------------------------------------------------------------------------------ the figures
#: The addresses, under `API_PREFIX`. `console/src/pages/agents/agentDraftsQuery.ts` names them.
SUGGEST_PATH: Final = "/agent-drafts/{draft_id}/suggestions"
TAKE_PATH: Final = "/agent-drafts/{draft_id}/suggestions/take"

#: What a person is told when nothing can answer.
NO_MODEL_HERE: Final = (
    "No model is set up on this install yet, so the co-author has nothing to ask. Nothing was "
    "changed, and you can go on writing the draft yourself."
)
NO_ANSWER_NOW: Final = (
    "The co-author could not be reached just now, so nothing was suggested and nothing was "
    "changed. Try again in a moment."
)
NOTHING_TO_SUGGEST: Final = "The co-author had nothing to suggest for that. Try asking another way."

#: The model the co-author's call asks for: the main tier, which is what a draft's prose needs.
COAUTHOR_TIER: Final = Tier.MAIN

router = APIRouter(prefix=API_PREFIX, tags=["agents"])


# ------------------------------------------------------------------------------ the shapes
class SuggestionAsked(BaseModel):
    """The revision the page drew, and what the author asks the co-author to change in it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=FIRST_REVISION)
    ask: str = Field(min_length=1, max_length=ASK_CHARS)


class HunkView(BaseModel):
    """One change: a manifest path, where the form shows it, and its value before and after."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    #: The form's own words for where it is: the section, then the field.
    where: str
    #: The draft's value now, as JSON text, or null when the draft holds nothing there.
    before: str | None
    #: What the co-author proposes, as JSON text.
    after: str


class DroppedView(BaseModel):
    """A change in the reply that is not proposed, and what to do about it, in words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    message: str


class SuggestionView(BaseModel):
    """What the co-author proposes for one revision. Nothing here has been applied."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int
    #: The digest of the revision's body, which taking must send back.
    base_digest: str
    hunks: list[HunkView]
    dropped: list[DroppedView]
    #: `A_SUGGESTION_IS_NOT_A_CHANGE_UNTIL_ITS_AUTHOR_TAKES_IT`, said on the page.
    note: str = A_SUGGESTION_IS_NOT_A_CHANGE_UNTIL_ITS_AUTHOR_TAKES_IT


class HunkSent(BaseModel):
    """A change as the page sends it back, to be judged again."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1, max_length=200)
    before: str | None = Field(default=None, max_length=100_000)
    after: str = Field(max_length=100_000)


class SuggestionTaken(BaseModel):
    """The proposal as it was drawn, and the paths the author takes. The rest are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=0)
    base_digest: str = Field(min_length=1, max_length=64)
    hunks: list[HunkSent] = Field(max_length=64)
    take: list[str] = Field(min_length=1, max_length=64)


# ------------------------------------------------------------------------------ the model
class CoauthorCalls(Protocol):
    """What these routes need of `brain.models.calls.ModelCalls.complete`, narrowed."""

    async def complete(
        self,
        messages: tuple[DriverMessage, ...],
        *,
        lane: Lane,
        meter: Meter,
        trace_id: str,
        tier: Tier | None = None,
        max_output_tokens: int | None = None,
        categories: tuple[DataCategory, ...] = (),
    ) -> DriverResponse: ...


def calls_of(request: Request) -> CoauthorCalls | None:
    """`app.state.coauthor_calls` when a test put one there, the executor otherwise, or None.

    None on a process with no model service, which the route says in words and never as a failure:
    an install that has not set up a provider is an install whose co-author has nothing to ask.
    """
    found: CoauthorCalls | None = getattr(request.app.state, "coauthor_calls", None)
    if found is not None:
        return found
    service = getattr(request.app.state, "models", None)
    return service.calls if isinstance(service, ModelService) else None


async def _spent(
    request: Request, asked: Any, meter: Meter, *, answered: bool, completed_at: datetime
) -> None:
    """Record the call as a provider check is recorded: its ledger row and its cost, and no more."""
    recorders: tuple[RequestRecorder, ...] = tuple(
        one
        for one in getattr(request.app.state, "request_recorders", ())
        if isinstance(one, TelemetryRecorder | UsageRecorder)
    )
    if not recorders or meter.usage() is None:
        return
    await finish(
        recorders,
        Finished(
            origin=Origin(
                trace_id=_trace_id(), principal=asked.caller.principal, channel=asked.channel
            ),
            at=asked.now,
            outcome=ModelCallOutcome(answered=answered),
            completed_at=completed_at,
            entitlement_hash=asked.reach.ent_hash(),
            lane=Lane.ANSWER,
            tool_calls=0,
            model_usage=meter.usage(),
        ),
    )


def _where(path: str) -> str:
    """Where the form shows this path, in the form's own words."""
    from brain.builder.compose import SECTION_OF_PATH

    section = SECTION_OF_PATH.get(path)
    words = FIELD_WORDS.get(path)
    if section is None:
        return path
    heading = SECTION_TITLES[section]
    if words is None or words.title.casefold() == heading.casefold():
        return heading
    return f"{heading}, {words.title[:1].lower()}{words.title[1:]}"


def _view(proposal: Proposal) -> SuggestionView:
    return SuggestionView(
        revision=proposal.base_revision,
        base_digest=proposal.base_digest,
        hunks=[
            HunkView(path=one.path, where=_where(one.path), before=one.before, after=one.after)
            for one in proposal.hunks
        ],
        dropped=[DroppedView(path=one.path, message=one.message) for one in proposal.dropped],
    )


# ------------------------------------------------------------------------------ the routes
@router.post(SUGGEST_PATH, response_model=SuggestionView, responses=_TOLD)
async def suggest_changes(
    request: Request, draft_id: str, body: SuggestionAsked, asked: Asked
) -> JSONResponse:
    """Ask the co-author for changes to the latest revision of the author's own draft.

    Writes nothing to the draft. Refused, before any model is called, for somebody else's draft,
    for a draft already published, for a revision that is not the latest and for a blank request.
    """
    _, draft = await _own(request, draft_id, asked)
    if published(draft):
        return _not_changed(REFUSED, ALREADY_PUBLISHED)
    latest = _latest(draft)
    if latest.number != body.revision:
        return _not_changed(MOVED, NOT_THE_LATEST)
    try:
        ask = checked_ask(body.ask)
    except BuilderError as refused:
        return _not_changed(REFUSED, str(refused))
    calls = calls_of(request)
    if calls is None:
        return _not_changed(UNAVAILABLE, NO_MODEL_HERE)
    meter = Meter()
    try:
        response = await calls.complete(
            coauthor_messages(latest.document(), ask),
            tier=COAUTHOR_TIER,
            lane=Lane.ANSWER,
            meter=meter,
            trace_id=_trace_id(),
            max_output_tokens=REPLY_TOKENS,
            categories=(DataCategory.AGENT_DRAFT,),
        )
    except (ProviderUnavailable, NoCompliantRoute):
        await _spent(request, asked, meter, answered=False, completed_at=datetime.now(UTC))
        return _not_changed(UNAVAILABLE, NO_ANSWER_NOW)
    await _spent(request, asked, meter, answered=True, completed_at=datetime.now(UTC))
    try:
        proposal = read_reply(response.text, draft_id=draft.draft_id, base=latest)
    except UnreadableReplyError as unreadable:
        return _not_changed(REFUSED, str(unreadable))
    log.info(
        "co-author asked",
        draft=draft.draft_id,
        by=asked.caller.principal.id,
        proposed=len(proposal.hunks),
        dropped=len(proposal.dropped),
    )
    view = _view(proposal)
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))


def _remembered(draft: AgentDraft) -> MemoryDraftStore:
    """The draft's history in the store `brain.builder.coauthor.accept` reads and appends to.

    A copy for the length of one call: the domain function is the one place the rules for taking a
    proposal live, and it is written against that store, so this hands it one holding exactly what
    the real store holds. What it appends is read back and written to the real one.
    """
    memory = MemoryDraftStore()
    memory.add(draft.draft)
    for revision in draft.revisions:
        memory.append(revision)
    return memory


@router.post(TAKE_PATH, response_model=DraftSavedView, responses=_TOLD)
async def take_suggestions(
    request: Request, draft_id: str, body: SuggestionTaken, asked: Asked
) -> JSONResponse:
    """Apply the named changes of a proposal to the author's own draft, as the next revision.

    The proposal is rebuilt from the request and judged again: a change to a path the co-author may
    not write cannot be rebuilt at all, a change whose before is not what the draft holds is
    refused, and a proposal made against a revision the draft has moved past is refused. What is
    not named is rejected and writes nothing.
    """
    store, draft = await _own(request, draft_id, asked)
    if published(draft):
        return _not_changed(REFUSED, ALREADY_PUBLISHED)
    latest = _latest(draft)
    try:
        proposal = Proposal(
            draft_id=draft.draft_id,
            base_revision=body.revision,
            base_digest=body.base_digest,
            hunks=tuple(
                Hunk(path=one.path, before=one.before, after=one.after) for one in body.hunks
            ),
        )
        taken = accept(
            _remembered(draft),
            proposal,
            body.take,
            by=asked.caller.principal.id,
            at=asked.now,
        )
    except StaleProposalError as stale:
        return _not_changed(MOVED, str(stale))
    except BuilderError as refused:
        return _not_changed(REFUSED, str(refused))
    saved = taken.saved.revision
    revisions = draft.revisions
    if saved.number > latest.number:
        if not await store.append(saved, by=_by(asked)):
            return _not_changed(MOVED, SAVED_SINCE)
        revisions = (*revisions, saved)
    after = AgentDraft(
        draft=draft.draft,
        agent_id=draft.agent_id,
        kind=draft.kind,
        base_hash=draft.base_hash,
        revisions=revisions,
        acts=draft.acts,
    )
    log.info(
        "co-author changes taken",
        draft=draft.draft_id,
        by=asked.caller.principal.id,
        taken=len(taken.resolution.accepted),
        rejected=len(taken.resolution.rejected),
    )
    view = DraftSavedView(
        revision=saved.number,
        state=state_of(after).value,
        problems=[plain(one) for one in validity(saved).problems],
    )
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))
