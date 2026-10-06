"""New agent and Edit as a draft: the builder's form, a draft saved as revisions, checked,
rehearsed and published, and a second person for a publish that reaches further.

`brain.builder` held every rule a builder needs (the form cut from the manifest schema, revisions
that are never edited, the publish gate that demotes a widening) and no route called any of them,
so the console could switch an agent off and could not make one. This module orders the questions
and writes through `brain.builder.draft_store`; every decision is `brain.builder.agent_drafts`' or
older, and every refusal a person reads is one of the sentences named below.

**Who may build is one capability, and failing it looks like absence.**
`brain.agents.creation.AGENT_INSTALL_CAPABILITY` decides that a ceiling exists at all, which is what
a draft does, and it is an `admin:` verb, so `brain.gate.admission` admits it only with a second
factor. A caller without it, a draft that does not exist and a draft that is somebody else's are one
404 with `Absent`'s one body: a draft is its author's own, by
`brain.builder.drafts.A_DRAFT_SOMEBODY_ELSE_OWNS_IS_A_DRAFT_THAT_DOES_NOT_EXIST`, and the one other
person who may open it is somebody who could approve it while it waits. An edit asks three questions
of the agent in `brain.agent_lifecycle_routes`' order: the capability, the agent's audience, and the
capability over the agent's row.

**Every step is its own act, and each is on the ledger.** Starting a draft, each save, a passing
check, a request, an approval, a sending back and a publish are rows `0149`'s triggers record as
`publish` entries about the agent. A publish needs a passing check of the same revision, so what is
published is what was checked. See `WHAT_IS_PUBLISHED_IS_WHAT_WAS_CHECKED`.

**A publish that reaches no further than before goes out on the author's word, and a wider one waits
for a second person** who is not its author and whose own reach covers everything the agent may
reach (`brain.builder.agent_drafts.NOBODY_PUBLISHES_A_WIDENING_THEY_AUTHORED_ALONE`). The waiting
publish is listed to exactly the people who could approve it, filtered and never counted, which is
`brain.console.scoped_authority.approvable`'s rule. **An agent is a lens and never a principal**:
nothing here computes a reach, and the rehearsal's reach is `brain.agents.install.rehearse`'s, which
calls `EntitlementSet.intersect` as the real gate does.

**What stops a publish, which rung it lands on and how many people it needs are
`brain.builder.publish.decide`'s one answer** (M20.4.1, M20.4.4), asked once by the check and again
when anything is written, so an approval by somebody who did not run the author's check is held to
the same gate. The checks are the system's own: the draft is filled in, nothing starts above Shadow,
the agent has not moved, and the install's permission canaries last passed. An author's own test
could never block (`A_TEST_THE_AUTHOR_WROTE_IS_A_TEST_THE_AUTHOR_CAN_REWRITE` in
`brain.builder.publish`), and none is run, because no model answers for an agent yet (M20.3.1).
The router collision (M20.4.5) is not asked: nothing on this install stores an agent's binding to
a route, so there is nothing for a draft to collide with; see `needs-rupash` on what a route is.

**A rehearsal says what it cannot do.** It runs the draft through the real gate as the person
asking, at Shadow, and reports whether a run would start for them, which tools it would reach for
them and the test questions it would ask. It does not ask the questions: no model answers for an
agent yet, so there is no answer to show or judge, and it says so in `A_REHEARSAL_RUNS_NO_MODEL_YET`
rather than drawing a result. It returns no rows, because nothing it does reads one.

**Publishing needs this install's template signing key**, like installing and duplicating, which
the application reads at start from its write-once vault slot (`brain.ops.template_key`,
`brain.agent_lifecycle_routes.INSTALLING_NEEDS_THE_KEY_THIS_INSTALL_VERIFIES_WITH`). So a process
without one says publishing is unavailable here, before a request or an approval is recorded, and a
draft can be written, saved, checked and rehearsed meanwhile.

**A new module rather than `brain.agent_lifecycle_routes`**, because that router moves an agent that
exists and this one makes and changes one; they share its three questions and its 409 body.

Task ids: M27.11.6, M27.15.31, M20.1.4, M20.4.6, M13.7.4, M20.4.1, M20.4.4
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.agent_lifecycle_routes import (
    NO_CHANNEL_ANSWERS_NOWHERE,
    NO_SIGNING_KEY_HERE,
    ChannelChoiceView,
    FoundAgent,
    channel_choices,
    connectors_of,
    holds,
    template_key_of,
    visible,
)
from brain.agent_routes import TEMPLATE_SCREEN, _tool_registry
from brain.agents.authoring import LiteralKind, scan
from brain.agents.catalogue import CATALOGUE
from brain.agents.creation import (
    AGENT_INSTALL_CAPABILITY,
    install_draft,
    mint_agent_id,
    new_audience,
)
from brain.agents.install import Installation, MissingKind, rehearse
from brain.agents.install_store import prepared
from brain.agents.lifecycle import ARCHIVE_IS_TERMINAL
from brain.agents.model import AgentAudience, AgentState, EnabledChannels
from brain.agents.template import SignedManifest, TemplateManifest, materialise, publish
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.automation_schedule_routes import NotChangedView
from brain.builder.agent_drafts import (
    NOT_THE_AUTHOR,
    STARTING_RUNG,
    Act,
    AgentDraft,
    approval_refusal,
    at_rung,
    becomes,
    blank_seed,
    carrier,
    ceiling_of,
    for_agent,
    manifest_of,
    name_of,
    next_version,
    plain,
    publish_decision,
    published,
    raised_rungs,
    republished,
    rung_of,
    second_people_needed,
    seed,
    state_of,
    system_check,
    widenings,
)
from brain.builder.compose import BuilderError
from brain.builder.draft_store import AgentDraftStore, Attribution, StoredAgentDrafts
from brain.builder.draft_words import DraftAct, DraftKind, DraftState
from brain.builder.drafts import (
    FIRST_REVISION,
    FIRST_VERSION,
    ManifestDraft,
    Revision,
    body_text,
    validity,
)
from brain.builder.form import form_document
from brain.builder.procedure import read_drawing, skill_markdown
from brain.builder.publish import Check, PublishDecision, blocking_failures
from brain.console.govern import _in_reach
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Absent, Failed
from brain.gate.injection import AutonomyTier
from brain.gate.screening import NOTHING_MATCHED
from brain.routing_routes import sessions_of
from brain.tools.registry import ToolRegistry

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the rehearsal says what it did not do.
A_REHEARSAL_RUNS_NO_MODEL_YET: Final = (
    "Rehearsing ran this draft through the real permission checks as you, at Shadow, and nothing "
    "was carried out. It did not ask the test questions: no model answers for an agent yet, so "
    "there is no answer to show or to judge. It read no records."
)

#: Why a publish needs a passing check of the same revision.
WHAT_IS_PUBLISHED_IS_WHAT_WAS_CHECKED: Final = (
    "A publish names a revision and needs a passing check of that same revision, so a save made "
    "after the check is checked again before it can be published."
)

# ------------------------------------------------------------------------------ the figures
#: The addresses, under `API_PREFIX`. `console/src/pages/agents/agentDraftsQuery.ts` names them.
FORM_PATH: Final = "/builder/form"
DRAFTS_PATH: Final = "/agent-drafts"
DRAFT_PATH: Final = "/agent-drafts/{draft_id}"
SAVE_PATH: Final = "/agent-drafts/{draft_id}/revisions"
CHECK_PATH: Final = "/agent-drafts/{draft_id}/check"
REHEARSE_PATH: Final = "/agent-drafts/{draft_id}/rehearse"
PROCEDURE_PATH: Final = "/agent-drafts/{draft_id}/procedure"
PUBLISH_PATH: Final = "/agent-drafts/{draft_id}/publish"
APPROVE_PATH: Final = "/agent-drafts/{draft_id}/approve"
DECLINE_PATH: Final = "/agent-drafts/{draft_id}/decline"
EDIT_PATH: Final = "/agents/{agent_id}/drafts"
PUBLICATIONS_PATH: Final = "/agents/{agent_id}/publications"

#: How many hex characters of randomness follow a minted id's stem, as an install mints one.
ID_SUFFIX_BYTES: Final = 3

#: The words a 409 carries, `brain.agent_lifecycle_routes`' three.
MOVED: Final = "moved"
REFUSED: Final = "refused"
UNAVAILABLE: Final = "unavailable"

#: What a person reads, each once.
SAVED_SINCE: Final = (
    "This draft was saved again after you opened it, so nothing was saved. Open it again and make "
    "your change there."
)
NOT_THE_LATEST: Final = (
    "That is not the latest save of this draft, so nothing was done. Open it again to see what is "
    "there now."
)
ALREADY_PUBLISHED: Final = (
    "This draft is published, so nothing was changed. To change the agent again, start a new draft "
    "from its page."
)
CHECK_FIRST: Final = "Nothing was published: check this draft first. " + (
    WHAT_IS_PUBLISHED_IS_WHAT_WAS_CHECKED
)
ALREADY_WAITING: Final = "This draft is already waiting for a second person to approve it."
NOT_WAITING: Final = "This draft is not waiting for anybody's approval, so nothing was changed."
AGENT_MOVED: Final = (
    "The agent changed after this draft was started, so nothing was published. Start a new draft "
    "from the agent as it is now."
)
NO_INSTALL_TO_START_FROM: Final = (
    "This agent was not made from a published version, so there is nothing to start a draft from."
)
NO_DEPARTMENT: Final = "Nothing was published: you sit in no department, so choose only you."
OUTSIDE_YOUR_AUTHORITY: Final = (
    "Nothing was published: your authority to make agents does not reach an agent seen by that "
    "audience. Choose the other one."
)
PRESS_AGAIN: Final = "Nothing was published: the agent was written by another press. Look again."
WAITS_FOR_A_SECOND_PERSON: Final = (
    "It reaches further than before, so it waits for a second person to approve it. They must not "
    "be you, and their own access must cover everything it may reach. It starts at Shadow either "
    "way."
)
PUBLISHED_NEW: Final = (
    "The new agent starts switched off and at Shadow on every action: it answers nobody until "
    "somebody switches it on, and it acts on nothing without a person until a rung is raised "
    "with evidence."
)
PUBLISHED_EDIT: Final = (
    "The agent now works as this draft says. Whether it is switched on has not changed, unless "
    "something it needs is missing here, in which case it was switched off."
)
SENT_BACK: Final = "Sent back to its author. Nothing was published."
#: What a check that passed is called, for the three the system makes of every draft.
COMPLETE: Final = "The draft is filled in."
MADE_HERE: Final = "The draft makes an agent on this install."
STARTS_AT_SHADOW: Final = "Every action starts at Shadow."
NOT_MOVED: Final = "The agent is as this draft started from it."
CANARIES_GREEN: Final = "The permission canaries passed on their latest run."
CANARIES_RED: Final = (
    "Nothing can be published while the permission checks this install runs on itself are "
    "failing. Ask an administrator to look at Quality and canaries, then check this draft again."
)
RUNG_PROBLEM: Final = (
    "Supervision, approval settings: every action starts at Shadow, and a rung is raised from "
    "evidence of the agent's own runs rather than from a draft. Set {targets} to Shadow."
)

#: The name a draft whose document names nothing is listed under.
UNNAMED: Final = "Unnamed agent"

#: What each kind of missing thing reads as.
MISSING_WORDS: Final[Mapping[MissingKind, str]] = {
    MissingKind.FIELD: "{name} is empty.",
    MissingKind.PLACEHOLDER: (
        "The question {name} has no answer here. Write the answer into the instructions and "
        "remove the question."
    ),
    MissingKind.CONNECTOR: "The {name} connector is not connected on this install yet.",
    MissingKind.TOOL: "Nothing on this install provides the tool {name} yet.",
}

#: The leak scan's kinds a check shows: the shaped ones, never a whole paragraph or a bare name.
SHAPED: Final[frozenset[LiteralKind]] = frozenset(
    {LiteralKind.EMAIL, LiteralKind.URL, LiteralKind.MONEY, LiteralKind.PHONE, LiteralKind.CODE}
)


# ------------------------------------------------------------------------ the shapes
class BuilderFormSection(BaseModel):
    """One section of the form: its name, its heading, its schema and its words (a uiSchema)."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    section: str
    title: str
    form: dict[str, Any] = Field(alias="schema")
    ui: dict[str, Any]


class BuilderFormView(BaseModel):
    """`brain.builder.form.form_document`, read by `console/src/components/manifestSections.ts`."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    version: str = Field(alias="schema")
    sections: list[BuilderFormSection]


class DraftActView(BaseModel):
    """One act on one revision, as the draft's page lists it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int
    act: str
    at: datetime


class AgentDraftSummary(BaseModel):
    """One draft on the drafts list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    draft_id: str
    agent_id: str
    name: str
    kind: str
    state: str
    revision: int
    saved_at: datetime | None = None


class AgentDraftsPage(BaseModel):
    """This reader's drafts, and the publishes waiting for them. Two lists and no totals."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[AgentDraftSummary]
    waiting_for_you: list[AgentDraftSummary]


class AgentDraftView(BaseModel):
    """One draft, for its author or for a person who could approve it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    draft_id: str
    agent_id: str
    name: str
    kind: str
    state: str
    #: The latest revision's number, which a save names as its base.
    revision: int
    document: dict[str, Any]
    #: What the manifest model refuses about the latest revision, in plain words.
    problems: list[str]
    saved_at: datetime | None = None
    acts: list[DraftActView]
    #: The reader wrote it and it is not published, so it can be saved, checked and published.
    yours: bool
    #: The reader could approve it now.
    waiting_on_you: bool
    #: For a draft waiting on this reader: what it reaches that the agent did not.
    widened: list[str]
    #: The tools a procedure drawn for it may call, by the names a skill calls them.
    drawable_tools: list[str]
    #: Why publishing is unavailable on this install, when it is.
    publish_unavailable: str | None = None
    #: For a new agent: the channels it may be switched on for, offered unticked (M13.7.4).
    channels: list[ChannelChoiceView] = Field(default_factory=channel_choices)
    #: `brain.agent_lifecycle_routes.NO_CHANNEL_ANSWERS_NOWHERE`.
    channels_note: str = NO_CHANNEL_ANSWERS_NOWHERE


class DraftStartAsked(BaseModel):
    """Start a new agent's draft from nothing, or from a template the gallery offers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str | None = Field(default=None, min_length=2, max_length=60)


class DraftSaveAsked(BaseModel):
    """A whole manifest document, and the revision it was edited from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document: dict[str, Any]
    base: int = Field(ge=0)


class DraftRevisionAsked(BaseModel):
    """The revision the page drew, which the act is about."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=FIRST_REVISION)


class DraftPublishAsked(BaseModel):
    """The revision checked, and for a new agent who sees it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int = Field(ge=FIRST_REVISION)
    #: False: the author alone. True: the author's own department.
    for_department: bool = False
    #: For a new agent: the channels it answers on, as the author ticked them (M13.7.4). None
    #: ticked answers nowhere. An edit keeps the agent's own, as it keeps its audience.
    channels: EnabledChannels = ()


class DraftSavedView(BaseModel):
    """What a save made: the revision that now stands and what the model refuses about it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int
    state: str
    problems: list[str]


class CompanyDetailView(BaseModel):
    """One shaped literal the leak scan found, and where."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    text: str
    places: list[str]


class DraftCheckView(BaseModel):
    """A check of one revision, in plain words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int
    passed: bool
    #: What stops a publish.
    problems: list[str]
    #: What the agent will be missing on this install. It is published switched off until then.
    missing: list[str]
    #: Addresses, figures and codes a template made from this agent would carry.
    company_details: list[CompanyDetailView]
    #: What it reaches that the agent did not, in the manifest's own words.
    widened: list[str]
    second_person_needed: bool
    #: The rung a publish of this revision would land on, decided by the publish gate: Shadow when
    #: it widens, otherwise the rung the agent is on.
    rung_after: str = "shadow"
    publish_unavailable: str | None = None


class DraftRehearsalView(BaseModel):
    """What rehearsing found for the person asking, and what it did not do. Never a row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: int
    #: Whether a run through this draft would start for you at all.
    starts_for_you: bool
    #: The tools a run would reach for you, by name.
    reaches_for_you: list[str]
    #: The rung it rehearsed at, which is Shadow.
    rung: str
    #: The test questions it would ask, which are the author's own text.
    questions: list[str]
    #: `A_REHEARSAL_RUNS_NO_MODEL_YET`.
    not_done: str


class ProcedureAsked(BaseModel):
    """A procedure drawn on the canvas, and what the skill it becomes is called."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    drawing: dict[str, Any]
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=400)


class ProcedureView(BaseModel):
    """The SKILL.md a drawing is, written by `brain.builder.procedure.skill_markdown`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    skill: str


class DraftPublishView(BaseModel):
    """What a publish did: published, sent back, or waiting for a second person."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: str
    agent_id: str
    sentence: str
    widened: list[str]
    #: The rung the agent went on at, which the publish gate decided.
    rung: str = "shadow"


# ------------------------------------------------------------------------ the store
async def canaries_red(request: Request) -> bool:
    """Whether the install's permission canaries last failed (M20.4.1).

    `app.state.canaries_red` when a test put one there, the newest finished run of the `canary_run`
    control otherwise, and no on a process with no database, which has no run to have failed. See
    `brain.builder.publication_store.A_RED_CANARY_RUN_STOPS_A_PUBLISH_AND_NO_RUN_DOES_NOT`.
    """
    from brain.builder.publication_store import canaries_are_red

    found = getattr(request.app.state, "canaries_red", None)
    if found is not None:
        return bool(await found())
    sessions = sessions_of(request)
    return False if sessions is None else await canaries_are_red(sessions)


def drafts_of(request: Request) -> AgentDraftStore:
    """`app.state.agent_drafts` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "agent_drafts", None)
    if isinstance(found, AgentDraftStore):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredAgentDrafts(factory)


# ------------------------------------------------------------------------ the decisions
def _no_draft_here(asked: Asking, reason: str) -> Absent:
    """The one refusal about a draft or an agent. The reason reaches a log and never a response."""
    log.info("agent draft not answerable", reason=reason, principal=asked.caller.principal.id)
    return Absent("no draft is answerable for this caller")


def _not_changed(outcome: str, sentence: str) -> JSONResponse:
    body = NotChangedView(outcome=outcome, sentence=sentence)
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _by(asked: Asking) -> Attribution:
    return Attribution(
        actor_id=asked.caller.principal.id, ent_hash=asked.reach.ent_hash(), trace_id=_trace_id()
    )


def _builds(asked: Asking) -> None:
    """The capability from the reach alone, before anything is read."""
    if asked.reach.scope_for(AGENT_INSTALL_CAPABILITY, asked.now) is None:
        raise _no_draft_here(asked, "capability")


def _tools(request: Request) -> ToolRegistry:
    tools = _tool_registry(request)
    if tools is None:
        raise Failed("no tool registry on this process")
    return tools


def _row(agent_id: str, audience: AgentAudience) -> dict[str, str]:
    row = {"agent_id": agent_id}
    if audience.department:
        row["department"] = audience.department
    return row


def _reaches(asked: Asking, agent_id: str, audience: AgentAudience) -> bool:
    """Whether this caller's authority to make agents reaches an agent with this audience."""
    return _in_reach(asked.reach, AGENT_INSTALL_CAPABILITY, _row(agent_id, audience), asked.now)


def _latest(draft: AgentDraft) -> Revision:
    latest = draft.latest
    if latest is None:
        # `start` writes the first revision in the transaction that writes the draft.
        raise Failed("a draft with no revision")
    return latest


def _whole(draft: AgentDraft, revision: Revision, publisher: str) -> TemplateManifest | None:
    manifest, _ = manifest_of(
        revision.document(), agent_id=draft.agent_id, version=FIRST_VERSION, publisher=publisher
    )
    return manifest


async def _becomes(
    request: Request,
    draft: AgentDraft,
    manifest: TemplateManifest,
    audience: AgentAudience,
    asked: Asking,
) -> Installation:
    return becomes(
        carrier(manifest, signed_by=draft.owner_id, at=asked.now),
        agent_id=draft.agent_id,
        created_by=draft.owner_id,
        audience=audience,
        registry=await connectors_of(request),
        tools=_tools(request),
        at=asked.now,
    )


async def _target(store: AgentDraftStore, draft: AgentDraft) -> FoundAgent | None:
    """The agent an edit changes, or None for a new agent."""
    if draft.kind is DraftKind.NEW:
        return None
    return await store.agent(draft.agent_id)


async def _audience_asked(
    store: AgentDraftStore, draft: AgentDraft, found: FoundAgent | None, for_department: bool
) -> AgentAudience | str:
    """Who sees the agent: an edit keeps its own, and a new agent is its author's alone or their
    department's. A sentence when the author has no department to show it to."""
    if found is not None:
        return found.record.audience
    department = await store.department_of(draft.owner_id) if for_department else None
    if for_department and not department:
        return NO_DEPARTMENT
    return new_audience(draft.owner_id, department)


def _requested(draft: AgentDraft) -> Act | None:
    """The request on the latest revision, when the draft is waiting."""
    latest = draft.latest
    if latest is None or state_of(draft) is not DraftState.WAITING:
        return None
    return draft.act_named(latest.number, DraftAct.REQUESTED)


async def _approvable(
    request: Request, store: AgentDraftStore, draft: AgentDraft, asked: Asking
) -> tuple[Installation, AgentAudience, FoundAgent | None, tuple[str, ...]] | None:
    """What approving this draft would publish, for a caller who could approve it, or None.

    None for the author, for a draft not waiting, and for a caller whose own reach does not cover
    the agent's whole ceiling or whose authority does not reach its row. The approvals a person is
    offered are filtered before they are shown and never counted, so every one of those is the
    same None.
    """
    requested = _requested(draft)
    if requested is None or draft.owner_id == asked.caller.principal.id:
        return None
    manifest = _whole(draft, _latest(draft), asked.caller.principal.id)
    found = await _target(store, draft)
    if manifest is None or (draft.kind is DraftKind.EDIT and found is None):
        return None
    audience = await _audience_asked(store, draft, found, requested.for_department)
    if isinstance(audience, str) or not _reaches(asked, draft.agent_id, audience):
        return None
    try:
        settled = await _becomes(request, draft, manifest, audience, asked)
    except BuilderError:
        return None
    if approval_refusal(
        author_id=draft.owner_id,
        approver_id=asked.caller.principal.id,
        ceiling=ceiling_of(settled.record),
        approver_reach=asked.reach,
        now=asked.now,
    ):
        return None
    before = None if found is None else found.record
    return settled, audience, found, widenings(before, settled.record, now=asked.now)


async def _openable(
    request: Request, draft_id: str, asked: Asking
) -> tuple[AgentDraftStore, AgentDraft, tuple[str, ...] | None]:
    """A draft this caller may open, and for a draft waiting on them what it widens.

    Their own, or one waiting that they could approve. Everything else is the one 404.
    """
    _builds(asked)
    store = drafts_of(request)
    draft = await store.draft(draft_id)
    if draft is None:
        raise _no_draft_here(asked, "draft")
    if draft.owner_id == asked.caller.principal.id:
        return store, draft, None
    approvable = await _approvable(request, store, draft, asked)
    if approvable is None:
        raise _no_draft_here(asked, "owner")
    return store, draft, approvable[3]


async def _own(
    request: Request, draft_id: str, asked: Asking
) -> tuple[AgentDraftStore, AgentDraft]:
    """A draft this caller wrote. Anybody else's is the one 404."""
    _builds(asked)
    store = drafts_of(request)
    draft = await store.draft(draft_id)
    if draft is None or draft.owner_id != asked.caller.principal.id:
        raise _no_draft_here(asked, "owner")
    return store, draft


def _summary(draft: AgentDraft) -> AgentDraftSummary:
    latest = draft.latest
    document = {} if latest is None else latest.document()
    return AgentDraftSummary(
        draft_id=draft.draft_id,
        agent_id=draft.agent_id,
        name=name_of(document) or UNNAMED,
        kind=draft.kind.value,
        state=state_of(draft).value,
        revision=0 if latest is None else latest.number,
        saved_at=None if latest is None else latest.saved_at,
    )


async def _drawable(request: Request, draft: AgentDraft, asked: Asking) -> list[str]:
    """The tools a procedure drawn for this draft may call: the registered tools its allowed tools
    bind to on this install, which are the names a skill calls. None while it binds nothing."""
    manifest = _whole(draft, _latest(draft), draft.owner_id)
    if manifest is None:
        return []
    try:
        made = await _becomes(request, draft, manifest, new_audience(draft.owner_id, None), asked)
    except BuilderError:
        return []
    return sorted(made.record.authority.allowed_tools)


def _view(
    draft: AgentDraft,
    asked: Asking,
    *,
    widened: Sequence[str] | None,
    key: str | None,
    drawable: Sequence[str],
) -> AgentDraftView:
    latest = _latest(draft)
    document = latest.document()
    return AgentDraftView(
        draft_id=draft.draft_id,
        agent_id=draft.agent_id,
        name=name_of(document) or UNNAMED,
        kind=draft.kind.value,
        state=state_of(draft).value,
        revision=latest.number,
        document=document,
        problems=[plain(one) for one in validity(latest).problems],
        saved_at=latest.saved_at,
        acts=[
            DraftActView(revision=one.revision, act=one.act.value, at=one.at) for one in draft.acts
        ],
        yours=draft.owner_id == asked.caller.principal.id and not published(draft),
        waiting_on_you=widened is not None,
        widened=list(widened or ()),
        drawable_tools=list(drawable),
        publish_unavailable=NO_SIGNING_KEY_HERE if key is None else None,
    )


def _signed(
    revision: Revision,
    *,
    agent_id: str,
    version: int,
    publisher: str,
    key: str,
    at: datetime,
    rung: AutonomyTier,
) -> SignedManifest:
    """The version a publish keeps, signed with this install's key, at the rung the gate decided."""
    manifest, problems = manifest_of(
        revision.document(), agent_id=agent_id, version=version, publisher=publisher
    )
    if manifest is None:
        raise BuilderError("; ".join(plain(one) for one in problems))
    return publish(at_rung(manifest, rung), key=key, signed_by=publisher, at=at)


async def _publish(
    request: Request,
    store: AgentDraftStore,
    draft: AgentDraft,
    audience: AgentAudience,
    found: FoundAgent | None,
    acts: Sequence[Act],
    asked: Asking,
    key: str,
    decision: PublishDecision,
) -> JSONResponse:
    """Write the agent the latest revision makes, with the acts that say so, or say why not.

    At the rung `decision` landed on, which is the publish gate's and not this function's."""
    revision = _latest(draft)
    publisher = asked.caller.principal.id
    tools = _tools(request)
    registry = await connectors_of(request)
    if found is None:
        signed = _signed(
            revision,
            agent_id=draft.agent_id,
            version=FIRST_VERSION,
            publisher=publisher,
            key=key,
            at=asked.now,
            rung=decision.rung,
        )
        # The channels the publishing act carries, which are what the author ticked.
        channels = next((one.channels for one in acts if one.act is DraftAct.PUBLISHED), ())
        made: Installation = prepared(
            install_draft(
                signed, agent_id=draft.agent_id, maker_id=draft.owner_id, display_name=None
            ),
            key=key,
            audience=audience,
            registry=registry,
            tools=tools,
            at=asked.now,
            channels=channels,
        )
        if not await store.publish_new(draft.draft_id, acts, signed, made, by=_by(asked)):
            return _not_changed(MOVED, PRESS_AGAIN)
        sentence = PUBLISHED_NEW
    else:
        if found.effective_hash != draft.base_hash or found.record.state is AgentState.ARCHIVED:
            return _not_changed(MOVED, AGENT_MOVED)
        signed = _signed(
            revision,
            agent_id=draft.agent_id,
            version=next_version(await store.versions_of(draft.agent_id)),
            publisher=publisher,
            key=key,
            at=asked.now,
            rung=decision.rung,
        )
        settled = republished(
            signed,
            key=key,
            agent_id=draft.agent_id,
            created_by=found.record.created_by,
            audience=audience,
            registry=registry,
            tools=tools,
            at=asked.now,
        )
        disabled_at = found.record.disabled_at
        if disabled_at is None and not settled.completeness.is_ready:
            disabled_at = asked.now
        written = await store.publish_edit(
            draft.draft_id,
            acts,
            signed,
            settled,
            base_hash=draft.base_hash or "",
            disabled_at=disabled_at,
            by=_by(asked),
        )
        if not written:
            return _not_changed(MOVED, AGENT_MOVED)
        sentence = PUBLISHED_EDIT
    log.info("agent draft published", draft=draft.draft_id, agent=draft.agent_id, by=publisher)
    body = DraftPublishView(
        state=DraftState.PUBLISHED.value,
        agent_id=draft.agent_id,
        sentence=sentence,
        widened=[],
        rung=decision.rung.name.lower(),
    )
    return JSONResponse(status_code=201, content=body.model_dump(mode="json"))


def _missing_words(settled: Installation) -> list[str]:
    return [MISSING_WORDS[one.kind].format(name=one.name) for one in settled.completeness.missing]


def _company_details(draft: AgentDraft) -> list[CompanyDetailView]:
    """The shaped literals `brain.agents.authoring.scan` finds, over the flat document."""
    manifest = _whole(draft, _latest(draft), draft.owner_id)
    if manifest is None:
        return []
    report = scan(manifest.document())
    return [
        CompanyDetailView(kind=one.kind.value, text=one.text, places=list(one.locations))
        for one in report.items
        if one.kind in SHAPED
    ]


router = APIRouter(prefix=API_PREFIX, tags=["agents"])

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": NotChangedView, "description": "Nothing was changed, and why."},
}


@router.get(FORM_PATH, response_model=BuilderFormView, responses=COMMON_RESPONSES)
async def builder_form(asked: Asked) -> JSONResponse:
    """The form a draft is written in, one JSON Schema per section, cut from the manifest's own."""
    _builds(asked)
    return JSONResponse(status_code=200, content=form_document())


@router.get(DRAFTS_PATH, response_model=AgentDraftsPage, responses=COMMON_RESPONSES)
async def agent_drafts(request: Request, asked: Asked) -> AgentDraftsPage:
    """This reader's drafts, newest first, and the publishes waiting for them to approve."""
    _builds(asked)
    store = drafts_of(request)
    mine = await store.drafts_owned_by(asked.caller.principal.id)
    waiting = [
        one
        for one in await store.waiting()
        if await _approvable(request, store, one, asked) is not None
    ]
    return AgentDraftsPage(
        items=[_summary(one) for one in mine],
        waiting_for_you=[_summary(one) for one in waiting],
    )


async def _start(
    request: Request,
    store: AgentDraftStore,
    asked: Asking,
    *,
    agent_id: str,
    kind: DraftKind,
    base_hash: str | None,
    document: Mapping[str, Any],
    key: str | None,
) -> JSONResponse:
    """Write a new draft and its first revision, which is the document it starts from."""
    draft_id = str(uuid.uuid4())
    me = asked.caller.principal.id
    draft = AgentDraft(
        draft=ManifestDraft(draft_id=draft_id, owner_id=me, created_at=asked.now),
        agent_id=agent_id,
        kind=kind,
        base_hash=base_hash,
    )
    first = Revision(
        draft_id=draft_id,
        number=FIRST_REVISION,
        body=body_text(for_agent(document, agent_id)),
        saved_by=me,
        saved_at=asked.now,
    )
    await store.start(draft, first, by=_by(asked))
    started = AgentDraft(
        draft=draft.draft, agent_id=agent_id, kind=kind, base_hash=base_hash, revisions=(first,)
    )
    log.info("agent draft started", draft=draft_id, agent=agent_id, kind=kind.value, by=me)
    view = _view(
        started, asked, widened=None, key=key, drawable=await _drawable(request, started, asked)
    )
    return JSONResponse(status_code=201, content=view.model_dump(mode="json"))


@router.post(DRAFTS_PATH, status_code=201, response_model=AgentDraftView, responses=_TOLD)
async def start_agent_draft(request: Request, body: DraftStartAsked, asked: Asked) -> JSONResponse:
    """A new agent's draft, from nothing or from a template, under an id minted now.

    A template is one the gallery offers this reader: a built-in one, or the newest published
    version of one, read behind the gallery's own grant. The draft is a copy: it starts from the
    template's words, and publishing it makes an agent of its own lineage.
    """
    _builds(asked)
    store = drafts_of(request)
    if body.template_id is None:
        agent_id = mint_agent_id("", suffix=secrets.token_hex(ID_SUFFIX_BYTES))
        document = blank_seed(agent_id)
    else:
        if not permitted(screen(TEMPLATE_SCREEN).read, asked.reach, asked.now):
            raise _no_draft_here(asked, "gallery")
        template = await store.newest_published(body.template_id) or next(
            (one for one in CATALOGUE if one.identity.template_id == body.template_id), None
        )
        if template is None:
            sentence = "No template by that name is offered to start from."
            raise Absent(sentence, public_message=sentence)
        name = template.identity.display_name
        agent_id = mint_agent_id(name, suffix=secrets.token_hex(ID_SUFFIX_BYTES))
        document = seed(template, agent_id)
    return await _start(
        request,
        store,
        asked,
        agent_id=agent_id,
        kind=DraftKind.NEW,
        base_hash=None,
        document=document,
        key=template_key_of(request),
    )


@router.post(EDIT_PATH, status_code=201, response_model=AgentDraftView, responses=_TOLD)
async def edit_agent_as_draft(request: Request, agent_id: str, asked: Asked) -> JSONResponse:
    """A draft of an agent as it is now, which publishing replaces it with.

    Asked of the capability, the audience and the capability over the agent's row, in
    `brain.agent_lifecycle_routes`' order, with one 404 for all three. An archived agent is refused
    in the domain's own words, and an agent with no install has nothing to start from.
    """
    _builds(asked)
    store = drafts_of(request)
    found = await store.agent(agent_id)
    if found is None or not visible(found.record, asked):
        raise _no_draft_here(asked, "agent")
    if not holds(AGENT_INSTALL_CAPABILITY, found.record, asked):
        raise _no_draft_here(asked, "scope")
    if found.record.state is AgentState.ARCHIVED:
        return _not_changed(REFUSED, ARCHIVE_IS_TERMINAL)
    if found.install is None or found.effective_hash is None:
        return _not_changed(REFUSED, NO_INSTALL_TO_START_FROM)
    signed, instance = found.install
    effective = materialise(signed, instance, audience=found.record.audience)
    return await _start(
        request,
        store,
        asked,
        agent_id=agent_id,
        kind=DraftKind.EDIT,
        base_hash=found.effective_hash,
        document=seed(effective.manifest, agent_id),
        key=template_key_of(request),
    )


class PublicationView(BaseModel):
    """One publish of an agent: who, when, which paths moved, the rung and who approved it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    published_by: str
    published_at: datetime
    #: The manifest paths that changed against the version before, names only.
    paths: list[str]
    rung: str
    approvers: list[str]


class PublicationsView(BaseModel):
    """An agent's publish history, oldest first (M20.4.6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    publications: list[PublicationView]


@router.get(PUBLICATIONS_PATH, response_model=PublicationsView, responses=COMMON_RESPONSES)
async def agent_publications(request: Request, agent_id: str, asked: Asked) -> PublicationsView:
    """Every publish of one agent, computed from its stored versions (M20.4.6).

    Asked as Edit as a draft asks: the capability, the agent's audience, then the capability over
    its row, one 404 for all three. The record is `brain.builder.publish.publication_history`
    over what `agent.template_version` keeps; nothing is written to serve it. See
    `brain.builder.publish.THE_PUBLISH_RECORD_IS_READ_FROM_THE_VERSIONS`.
    """
    from brain.builder.publication_store import StoredPublications

    _builds(asked)
    found = await drafts_of(request).agent(agent_id)
    if found is None or not visible(found.record, asked):
        raise _no_draft_here(asked, "agent")
    if not holds(AGENT_INSTALL_CAPABILITY, found.record, asked):
        raise _no_draft_here(asked, "scope")
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    history = await StoredPublications(sessions).history(agent_id)
    return PublicationsView(
        agent_id=agent_id,
        publications=[
            PublicationView(
                published_by=one.actor_id,
                published_at=one.at,
                paths=list(one.paths),
                rung=one.rung.name.lower(),
                approvers=list(one.approvers),
            )
            for one in history
        ],
    )


@router.get(DRAFT_PATH, response_model=AgentDraftView, responses=COMMON_RESPONSES)
async def agent_draft(request: Request, draft_id: str, asked: Asked) -> AgentDraftView:
    """One draft, for its author, or for a person who could approve it while it waits."""
    _, draft, widened = await _openable(request, draft_id, asked)
    key = template_key_of(request)
    return _view(
        draft, asked, widened=widened, key=key, drawable=await _drawable(request, draft, asked)
    )


@router.post(SAVE_PATH, response_model=DraftSavedView, responses=_TOLD)
async def save_agent_draft(
    request: Request, draft_id: str, body: DraftSaveAsked, asked: Asked
) -> JSONResponse:
    """The document as the next revision, kept whole or not. See
    `brain.builder.drafts.AN_INCOMPLETE_DRAFT_IS_KEPT_AND_REPORTED_NOT_REFUSED`.

    Saving what is already the latest returns it, a save from an older revision is refused, and
    the document's address is set to the agent's own before it is kept.
    """
    store, draft = await _own(request, draft_id, asked)
    if published(draft):
        return _not_changed(REFUSED, ALREADY_PUBLISHED)
    latest = _latest(draft)
    try:
        text = body_text(for_agent(body.document, draft.agent_id))
    except BuilderError as refused:
        return _not_changed(REFUSED, str(refused))
    if text == latest.body:
        saved = latest
    elif body.base != latest.number:
        return _not_changed(MOVED, SAVED_SINCE)
    else:
        saved = Revision(
            draft_id=draft.draft_id,
            number=latest.number + 1,
            body=text,
            saved_by=asked.caller.principal.id,
            saved_at=asked.now,
        )
        if not await store.append(saved, by=_by(asked)):
            return _not_changed(MOVED, SAVED_SINCE)
    after = AgentDraft(
        draft=draft.draft,
        agent_id=draft.agent_id,
        kind=draft.kind,
        base_hash=draft.base_hash,
        revisions=(*draft.revisions, saved) if saved is not latest else draft.revisions,
        acts=draft.acts,
    )
    view = DraftSavedView(
        revision=saved.number,
        state=state_of(after).value,
        problems=[plain(one) for one in validity(saved).problems],
    )
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))


async def _check(
    request: Request, draft: AgentDraft, found: FoundAgent | None, asked: Asking
) -> tuple[DraftCheckView, Installation | None, PublishDecision | None]:
    """Everything the check says about the latest revision, what it would become, and the gate.

    What stops a publish is the publish gate's own answer (`brain.builder.publish.decide`) over
    checks of system origin, and the rung, the widenings and the second person the view carries are
    the same decision's. The decision is None when the draft does not make an agent yet, because a
    gate has nothing to compare then and the checks alone say why.
    """
    revision = _latest(draft)
    manifest, problems = manifest_of(
        revision.document(),
        agent_id=draft.agent_id,
        version=FIRST_VERSION,
        publisher=asked.caller.principal.id,
    )
    checks: list[Check] = [system_check(COMPLETE, plain(one), failed=True) for one in problems]
    settled: Installation | None = None
    if manifest is not None:
        raised = raised_rungs(manifest)
        checks.append(
            system_check(
                STARTS_AT_SHADOW,
                RUNG_PROBLEM.format(targets=", ".join(raised)),
                failed=bool(raised),
            )
        )
        audience = (
            found.record.audience if found is not None else new_audience(draft.owner_id, None)
        )
        made_failing = ""
        try:
            settled = await _becomes(request, draft, manifest, audience, asked)
        except BuilderError as refused:
            made_failing = str(refused)
        checks.append(system_check(MADE_HERE, made_failing, failed=bool(made_failing)))
    checks.append(
        system_check(
            NOT_MOVED,
            AGENT_MOVED,
            failed=draft.kind is DraftKind.EDIT
            and (
                found is None
                or found.effective_hash != draft.base_hash
                or found.record.state is AgentState.ARCHIVED
            ),
        )
    )
    checks.append(system_check(CANARIES_GREEN, CANARIES_RED, failed=await canaries_red(request)))
    decision: PublishDecision | None = None
    stops: tuple[str, ...] = blocking_failures(checks)
    widened: tuple[str, ...] = ()
    if settled is not None:
        decision = publish_decision(
            agent_id=draft.agent_id,
            before=None if found is None else found.record,
            after=settled.record,
            current_rung=rung_of(
                None if found is None or found.install is None else found.install[0]
            ),
            checks=checks,
            now=asked.now,
        )
        stops = decision.refusals
        widened = decision.widenings
    view = DraftCheckView(
        revision=revision.number,
        passed=not stops,
        problems=list(stops),
        missing=[] if settled is None else _missing_words(settled),
        company_details=_company_details(draft),
        widened=list(widened),
        second_person_needed=second_people_needed(widened) > 0,
        rung_after=(STARTING_RUNG if decision is None else decision.rung).name.lower(),
        publish_unavailable=NO_SIGNING_KEY_HERE if template_key_of(request) is None else None,
    )
    return view, settled, decision


@router.post(CHECK_PATH, response_model=DraftCheckView, responses=_TOLD)
async def check_agent_draft(
    request: Request, draft_id: str, body: DraftRevisionAsked, asked: Asked
) -> JSONResponse:
    """Whether the latest revision would publish, and every reason it would not, in plain words.

    A passing check is recorded against the revision, which is what a publish then needs.
    """
    store, draft = await _own(request, draft_id, asked)
    if _latest(draft).number != body.revision:
        return _not_changed(MOVED, NOT_THE_LATEST)
    view, _, _ = await _check(request, draft, await _target(store, draft), asked)
    if view.passed and not published(draft):
        await store.record(
            draft.draft_id,
            Act(
                revision=body.revision,
                act=DraftAct.CHECKED,
                actor_id=asked.caller.principal.id,
                at=asked.now,
                widened=bool(view.widened),
            ),
            by=_by(asked),
        )
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))


@router.post(REHEARSE_PATH, response_model=DraftRehearsalView, responses=_TOLD)
async def rehearse_agent_draft(
    request: Request, draft_id: str, body: DraftRevisionAsked, asked: Asked
) -> JSONResponse:
    """The latest revision rehearsed as the person asking, at Shadow, through the real gate.

    `brain.agents.install.rehearse` assembles the run `E(you) ∩ ceiling` would be and says whether
    it starts and what it reaches; nothing is carried out, nothing is recorded and no row is read.
    """
    store, draft = await _own(request, draft_id, asked)
    if _latest(draft).number != body.revision:
        return _not_changed(MOVED, NOT_THE_LATEST)
    view, settled, _ = await _check(request, draft, await _target(store, draft), asked)
    if settled is None:
        return _not_changed(REFUSED, " ".join(view.problems))
    manifest = settled.effective.manifest
    ran = rehearse(
        settled,
        registry=_tools(request),
        entitlement=asked.reach,
        assessment=NOTHING_MATCHED,
        now=asked.now,
    )
    result = DraftRehearsalView(
        revision=body.revision,
        starts_for_you=ran.started,
        reaches_for_you=list(ran.reachable),
        rung=STARTING_RUNG.name.lower(),
        questions=[one.question for one in manifest.golden_set],
        not_done=A_REHEARSAL_RUNS_NO_MODEL_YET,
    )
    return JSONResponse(status_code=200, content=result.model_dump(mode="json"))


@router.post(PROCEDURE_PATH, response_model=ProcedureView, responses=_TOLD)
async def draw_agent_procedure(
    request: Request, draft_id: str, body: ProcedureAsked, asked: Asked
) -> JSONResponse:
    """The SKILL.md a drawn procedure is, over the tools this draft allows. Nothing is kept."""
    _, draft = await _own(request, draft_id, asked)
    tools = await _drawable(request, draft, asked)
    try:
        procedure = read_drawing(body.drawing, drawable_tools=tools)
        skill = skill_markdown(procedure, name=body.name, description=body.description)
    except BuilderError as refused:
        return _not_changed(REFUSED, str(refused))
    return JSONResponse(status_code=200, content=ProcedureView(skill=skill).model_dump(mode="json"))


@router.post(PUBLISH_PATH, status_code=201, response_model=DraftPublishView, responses=_TOLD)
async def publish_agent_draft(
    request: Request, draft_id: str, body: DraftPublishAsked, asked: Asked
) -> JSONResponse:
    """Publish the checked latest revision, or ask a second person when it reaches further.

    Refused, before anything is written, when publishing is unavailable here, when the revision is
    not the latest or not checked, when the draft is already published or waiting, and when the
    author's authority does not reach the agent's audience.
    """
    store, draft = await _own(request, draft_id, asked)
    key = template_key_of(request)
    if key is None:
        return _not_changed(UNAVAILABLE, NO_SIGNING_KEY_HERE)
    latest = _latest(draft)
    if published(draft):
        return _not_changed(REFUSED, ALREADY_PUBLISHED)
    if latest.number != body.revision:
        return _not_changed(MOVED, NOT_THE_LATEST)
    state = state_of(draft)
    if state is DraftState.WAITING:
        return _not_changed(REFUSED, ALREADY_WAITING)
    if state is not DraftState.CHECKED:
        return _not_changed(REFUSED, CHECK_FIRST)
    found = await _target(store, draft)
    view, settled, decision = await _check(request, draft, found, asked)
    if not view.passed or settled is None or decision is None:
        return _not_changed(REFUSED, " ".join(view.problems))
    audience = await _audience_asked(store, draft, found, body.for_department)
    if isinstance(audience, str):
        return _not_changed(REFUSED, audience)
    if not _reaches(asked, draft.agent_id, audience):
        return _not_changed(REFUSED, OUTSIDE_YOUR_AUTHORITY)
    me = asked.caller.principal.id
    if second_people_needed(view.widened) > 0:
        asked_for = Act(
            revision=latest.number,
            act=DraftAct.REQUESTED,
            actor_id=me,
            at=asked.now,
            widened=True,
            for_department=body.for_department,
            channels=body.channels,
        )
        if not await store.record(draft.draft_id, asked_for, by=_by(asked)):
            return _not_changed(REFUSED, ALREADY_WAITING)
        log.info("agent draft waits for a second person", draft=draft.draft_id, by=me)
        waiting = DraftPublishView(
            state=DraftState.WAITING.value,
            agent_id=draft.agent_id,
            sentence=WAITS_FOR_A_SECOND_PERSON,
            widened=list(view.widened),
        )
        return JSONResponse(status_code=202, content=waiting.model_dump(mode="json"))
    done = Act(
        revision=latest.number,
        act=DraftAct.PUBLISHED,
        actor_id=me,
        at=asked.now,
        for_department=body.for_department,
        channels=body.channels,
    )
    return await _publish(request, store, draft, audience, found, (done,), asked, key, decision)


async def _decided(
    request: Request, draft_id: str, body: DraftRevisionAsked, asked: Asking
) -> tuple[AgentDraftStore, AgentDraft, AgentAudience, FoundAgent | None] | JSONResponse:
    """A waiting draft this caller may decide, or the answer saying why not.

    The author is told they wrote it; anybody who could not approve it is the one 404, because
    they could not have opened it either.
    """
    _builds(asked)
    store = drafts_of(request)
    draft = await store.draft(draft_id)
    if draft is None:
        raise _no_draft_here(asked, "draft")
    if draft.owner_id == asked.caller.principal.id:
        return _not_changed(REFUSED, NOT_THE_AUTHOR)
    approvable = await _approvable(request, store, draft, asked)
    if approvable is None:
        raise _no_draft_here(asked, "approver")
    if _latest(draft).number != body.revision:
        return _not_changed(MOVED, NOT_THE_LATEST)
    _, audience, found, _ = approvable
    return store, draft, audience, found


@router.post(APPROVE_PATH, status_code=201, response_model=DraftPublishView, responses=_TOLD)
async def approve_agent_draft(
    request: Request, draft_id: str, body: DraftRevisionAsked, asked: Asked
) -> JSONResponse:
    """Approve a waiting publish as the second person, which publishes it."""
    decided = await _decided(request, draft_id, body, asked)
    if isinstance(decided, JSONResponse):
        return decided
    store, draft, audience, found = decided
    key = template_key_of(request)
    if key is None:
        return _not_changed(UNAVAILABLE, NO_SIGNING_KEY_HERE)
    me = asked.caller.principal.id
    requested = _requested(draft)
    for_department = bool(requested and requested.for_department)
    acts = (
        Act(revision=body.revision, act=DraftAct.APPROVED, actor_id=me, at=asked.now, widened=True),
        Act(
            revision=body.revision,
            act=DraftAct.PUBLISHED,
            actor_id=me,
            at=asked.now,
            widened=True,
            for_department=for_department,
            # What the author ticked when they asked, which is what the approver was shown.
            channels=requested.channels if requested is not None else (),
        ),
    )
    # The gate is asked again at the moment of writing: an approval is a publish by somebody who
    # did not run the author's check, and what is written is what the gate says now.
    _, _, decision = await _check(request, draft, found, asked)
    if decision is None or not decision.may_publish:
        return _not_changed(REFUSED, " ".join(() if decision is None else decision.refusals))
    return await _publish(request, store, draft, audience, found, acts, asked, key, decision)


@router.post(DECLINE_PATH, response_model=DraftPublishView, responses=_TOLD)
async def decline_agent_draft(
    request: Request, draft_id: str, body: DraftRevisionAsked, asked: Asked
) -> JSONResponse:
    """Send a waiting publish back to its author. Nothing is published."""
    decided = await _decided(request, draft_id, body, asked)
    if isinstance(decided, JSONResponse):
        return decided
    store, draft, _, _ = decided
    act = Act(
        revision=body.revision,
        act=DraftAct.DECLINED,
        actor_id=asked.caller.principal.id,
        at=asked.now,
        widened=True,
    )
    if not await store.record(draft.draft_id, act, by=_by(asked)):
        return _not_changed(MOVED, NOT_WAITING)
    view = DraftPublishView(
        state=DraftState.DECLINED.value, agent_id=draft.agent_id, sentence=SENT_BACK, widened=[]
    )
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))
