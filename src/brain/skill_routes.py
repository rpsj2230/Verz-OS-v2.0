"""The Skills screen over HTTP: the library, the queue, and the three writes that make a skill run.

SCREEN 6 of `docs/screens.html` is the design of record: a library of skills with their source,
version, reviewer and state, a review pane with Approve and Reject, and what each skill asks for.
Until `0056` nothing stored an imported skill, so this router served only which agents were pinned
to which bytes and said on every answer that a skill could not be added, approved or assigned. It
now serves the library `brain.ops.skill_store` keeps, and three writes, each of them a decision
`brain.console.skill_library` makes and this module only orders.

**Adding a skill is an administrator's write, and it lands in the review queue.** `POST /skills`
takes a package, a pasted or uploaded `SKILL.md` or a zip holding one, asks
`brain.console.skill_library.may_add` before anything is read, parses it with `read_package`, which
runs nothing, and writes it undecided. Its ledger entry is `0056`'s trigger. See
`AN_IMPORT_IS_A_SUBMISSION_AND_NEVER_AN_APPROVAL`.

**Approving is a second person, and the first is refused whatever they hold.**
`POST /skills/{digest}/review` asks `may_review`, then `decided`, which refuses the importer before
it asks anything else, and the table refuses the same row again. See
`brain.console.skill_library.NOBODY_DECIDES_ABOUT_A_SKILL_THEY_ADDED`.

**What a skill is trusted to reach is on the answer, computed from the registry.** Every library
row carries the tools the `SKILL.md` names, the capability each registered tool requires and the
tools nothing registers, from `brain.console.skill_library.trusted_reach` over the registry
`brain.app` built. An assignment answers with what the skill reaches through that agent for the
person who assigned it, which is `reach_through` at `E_run(caller, agent)`. Nothing here intersects
anything. See `A_SKILL_REACHES_WHAT_ITS_TOOLS_REACH_AND_THE_SCREEN_SAYS_WHICH`.

**Assigning goes through `attach_skill` and writes only the agent's skills.**
`POST /skills/{digest}/assignments` asks for the skill authority in a scope admitting the agent and
for the agent in the caller's audience, and refuses both alike. `brain.console.skill_library.
assignment` then runs `register_skill`, whose `attach_skill` and `pin_skill` refuse a skill that is
not approved by a named person and unchanged since, and writes the `skills` path of the install
with the authority compared before and after. The store writes the install only if nobody changed
it since it was read. The agent's ceiling does not move, so what any caller reaches through it can
only be narrowed by what the skill names. See
`brain.console.skill_library.A_SKILL_NEVER_WIDENS_AN_AGENT_PAST_ITS_CALLER`.

**Every refusal to a caller who may not act is the screen's one sentence**, identical for a skill
or an agent that does not exist, which is `brain.govern_routes._not_answerable`'s construction. A
caller who may act and is refused is told why in words, which is `brain.prompt_routes`'
construction, because they hold the authority and are looking at the thing: the importer reviewing
their own skill, a package that does not parse, an agent changed since they opened it.

**The catalogue of pins is still assembled agent by agent, from the agents this reader may already
see.** That is `brain.console.govern_estate.
AN_ESTATE_LISTING_IS_ASSEMBLED_FROM_WHAT_THE_READER_CAN_ALREADY_SEE`, and it is now also where the
list of agents a skill can be assigned to comes from, so a reader is never offered an agent the
roster would not list.

**Whether the screen opens is `brain.console.reads.permitted` and never a bare capability check**,
and the question is asked before a session is reached for, so a caller with no grant cannot tell a
deployment with a database from one without.

Rejected: a route answering one skill by name for reading. A deep link is resolved against the page,
for `brain.govern_routes.A_DEEP_LINK_RESOLVED_AGAINST_THE_PAGE_CANNOT_BE_AN_ORACLE`'s reason. The
writes take a digest in the path, and each asks its authority before the digest is looked up, so a
caller who may not act cannot use one to ask what exists.

Rejected: an assignment that takes a name and a digest from the browser. The digest names a stored
skill and the store's copy is what is pinned, so a typed digest that matches nothing pins nothing,
and one that matches pins the bytes a named second person approved. That was
`AN_ASSIGNMENT_BUILT_ON_A_DIGEST_SOMEBODY_TYPED_IS_AN_APPROVAL_THEY_GRANTED_THEMSELVES` before a
library existed, and it is answered by the library rather than argued away.

**What has never run.** This repository has no PostgreSQL, so the statements have not been executed
against one here; `tests/unit/test_skill_store.py` runs them against a scratch server where one
exists and skips otherwise.

Task ids: M42.6.4
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Final, Literal, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import (
    _tool_registry,
    every_agent,
    manifest_of,
    record_of,
    viewer_of,
)
from brain.agents.model import AgentRecord, visible_agent_ids
from brain.agents.template import (
    FieldOwner,
    SignedManifest,
    TemplateError,
    TemplateInstance,
    materialise,
)
from brain.api import API_PREFIX, COMMON_RESPONSES, Page
from brain.api_routes import Asked, Asking
from brain.audit.ledger import AuditChain
from brain.audit.record import AuditRecorder
from brain.console.agent_tabs import AgentTabError, Review, review_state
from brain.console.govern import Placed
from brain.console.govern_estate import skill_queue
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.skill_library import (
    SKILL_AUTHORITY,
    Assignment,
    LibrarySkill,
    SkillLibraryError,
    SkillReach,
    ToolReach,
    added,
    another_spelling,
    assignment,
    decided,
    may_add,
    may_assign,
    may_read_library,
    may_review,
    queue_entries,
    reach_through,
    read_package,
    trusted_reach,
)
from brain.console.workspace import WorkspaceError
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.ops.skill_store import MAX_LIBRARY, StoredSkills
from brain.prompt_routes import agent_scope_row, every_agent_with_install, installed
from brain.routing_routes import sessions_of
from brain.tables.agent import AgentRow
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
from brain.tools.review import QueueEntry
from brain.tools.skills import DIGEST_RE, SkillPin

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons
#: Why adding a skill is a submission.
AN_IMPORT_IS_A_SUBMISSION_AND_NEVER_AN_APPROVAL: Final = (
    "Adding a skill writes it in the imported state, with no reviewer and no approved digest, "
    "and there is no field on the request that could carry either. It is listed in the review "
    "queue from that moment, it cannot be attached to any agent, and brain.tools.skills.body_of "
    "refuses its instructions to an agent until somebody other than the person who added it has "
    "approved the exact bytes that were added."
)

#: Why reach is listed per tool, and why an unregistered tool is named.
A_SKILL_REACHES_WHAT_ITS_TOOLS_REACH_AND_THE_SCREEN_SAYS_WHICH: Final = (
    "A skill declares no reach of its own, so what it is trusted to reach is the union of what "
    "the registered tools it names require, read off the registry this process built. A tool it "
    "names that nothing registers reaches nothing and is listed by name, so a reviewer sees a "
    "misconfigured skill rather than an empty list that reads as a harmless one. Through an agent "
    "it is narrower again: the tools the catalogue admits at E_run(caller, agent)."
)

#: Why a difference between two pins is a statement about this page.
A_DIFFERENCE_BETWEEN_PINS_IS_ABOUT_THIS_PAGE_AND_NEVER_THE_ESTATE: Final = (
    "versions_differ is computed over the pins on the row, which are the pins of agents this "
    "reader's audience covers. An agent they cannot see may pin other bytes of the same "
    "skill, and the flag stays false. That is the narrow direction and the only honest one: "
    "a flag computed over every agent would be true for a reason the reader cannot find on "
    "the page, which is a count of what they were not shown wearing a boolean."
)


# ----------------------------------------------------------------- the screen
#: The screen whose grant decides whether this listing opens at all.
#:
#: A key rather than a capability written out, which is `brain.console.agent_tabs.SKILL_SCREEN`'s
#: construction and the same key: the tab and this screen are one grant, so a rename moves both.
SKILLS_SCREEN: Final = "skills"


# ------------------------------------------------------------------ the bounds
#: The most agents one catalogue answer is assembled from. A resource bound and not a
#: permission one: it is applied to the load, the audience filter runs over what came back,
#: and `truncated` says the load came back full without saying what was in the rest of it.
MAX_AGENTS_CONSIDERED: Final = 500

#: What a caller gets when they do not say.
DEFAULT_AGENTS_CONSIDERED: Final = 200

#: The longest package a request may carry, in characters, which is the largest package in base64
#: with room for the encoding. `brain.console.skill_library.MAX_PACKAGE_BYTES` refuses the bytes.
MAX_PACKAGE_CHARS: Final = 360_000

#: A digest in a path, as `brain.tools.skills.DIGEST_RE` spells one.
DIGEST_PATTERN: Final = DIGEST_RE.pattern


# ------------------------------------------------------------------- the shapes
class SkillPinView(BaseModel):
    """One agent, and the bytes of this skill it is configured to run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    digest: str


class SkillRow(BaseModel):
    """One skill the reader's agents run, and which of them run it.

    `versions_differ` is the one derived field and it is a fact about this row; see
    `A_DIFFERENCE_BETWEEN_PINS_IS_ABOUT_THIS_PAGE_AND_NEVER_THE_ESTATE`. Review state lives on the
    library row for the bytes, never here: a pin is a configuration, and a state read off one
    would say a skill was approved because an agent was configured with it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    pinned_by: tuple[SkillPinView, ...]
    #: The agents on this row are not all pinned to the same bytes of this skill.
    versions_differ: bool


class QueueEntryView(BaseModel):
    """One skill waiting for a reviewer, as the queue lists it.

    The name, the bytes, how long it has waited and which fields changed, which is what
    `brain.tools.review.QueueEntry` says a reviewer needs to decide. There is no body and no
    reviewer: the body is on the library row, where the decision is made, for a reader who may
    make it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    digest: str
    waiting_since: datetime
    #: Field names, never values, and empty for a first submission. `diff_skills`' own answer.
    changed: tuple[str, ...]
    stale: bool


class SkillQueueView(BaseModel):
    """What is waiting to be read, and the summary of exactly that.

    See `brain.console.govern_estate.A_SUMMARY_OVER_A_WIDER_LIST_THAN_THE_LISTING_IS_A_SUBTRACTION`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[QueueEntryView, ...]
    waiting: int
    edits: int
    stale: int


class ToolReachView(BaseModel):
    """One tool a skill names, and what the registered tool requires, or null when none is."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    capability: str | None


class LibrarySkillView(BaseModel):
    """One skill in the library: SCREEN 6's library row and its review pane in one shape.

    `review` is `brain.console.agent_tabs.review_state`, so a row whose bytes moved after approval
    reads `changed` rather than `approved`. `body` is present only for a reader who may add or
    review skills, because it is what a reviewer reads and a listing is not a place to hand
    instructions to anybody else. `reviewable` and `assignable` decide whether a button is drawn
    and nothing more: each write asks every question again.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    digest: str
    name: str
    version: str
    description: str
    source: str
    source_location: str
    submitted_by: str
    submitted_at: datetime
    review: str
    reviewer: str | None
    reviewed_at: datetime | None
    #: See `A_SKILL_REACHES_WHAT_ITS_TOOLS_REACH_AND_THE_SCREEN_SAYS_WHICH`.
    tools: tuple[ToolReachView, ...]
    capabilities: tuple[str, ...]
    unregistered_tools: tuple[str, ...]
    body: str | None
    reviewable: bool
    assignable: bool


class AgentChoiceView(BaseModel):
    """An agent this reader may assign a skill to: in their audience and in their authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str


class SkillsPage(Page[SkillRow]):
    """The skills the reader's agents run, the library, the queue, and what this reader may do.

    `total` is inherited and never populated, for the reason every listing in this application
    gives. `may_add` and `agents` decide what the page offers and nothing else.
    """

    #: The agent load came back full, so there are more agents than this answer was assembled from.
    truncated: bool = False
    queue: SkillQueueView
    library: tuple[LibrarySkillView, ...] = ()
    #: The library load came back full. Never how many more.
    library_truncated: bool = False
    #: The agents this reader may assign an approved skill to.
    agents: tuple[AgentChoiceView, ...] = ()
    may_add: bool = False
    #: No tool registry was built on this process, so no tool a skill names can be resolved and
    #: every tool is listed as unregistered.
    registry_is_absent: bool = False


class SkillPackageAsked(BaseModel):
    """A package: its file name, and its bytes as text or as base64. Nothing that could say who."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    file_name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=MAX_PACKAGE_CHARS)
    encoding: Literal["text", "base64"]


class ReviewAsked(BaseModel):
    """The decision. Nothing that could name the reviewer, who is the caller."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Literal["approve", "reject"]


class AssignAsked(BaseModel):
    """Which agent. The skill is the one in the path, as the library holds it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str = Field(min_length=1, max_length=128)


class AssignedView(BaseModel):
    """What was assigned, what it replaced, and what it reaches through this agent for you."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    skill_name: str
    digest: str
    replaced_digest: str | None
    #: `brain.console.skill_library.reach_through`: tool names, and never more than the caller
    #: reaches through this agent without the skill.
    reach: tuple[str, ...]
    effective_hash: str


# ------------------------------------------------------------------------ the stores
@runtime_checkable
class SkillLibrary(Protocol):
    """What these routes need of the library. `brain.ops.skill_store.StoredSkills` implements it."""

    async def library(self, limit: int = MAX_LIBRARY) -> tuple[LibrarySkill, ...]: ...

    async def skill(self, digest: str) -> LibrarySkill | None: ...

    async def add(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> bool: ...

    async def decide(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> bool: ...

    async def assign(
        self, made: Assignment, *, expected_hash: str, ent_hash: str, trace_id: str
    ) -> bool: ...


@dataclass(frozen=True)
class FoundAgent:
    """One stored agent, its install when it has one that constructs, and the install's hash."""

    record: AgentRecord
    install: tuple[SignedManifest, TemplateInstance] | None
    effective_hash: str | None


@runtime_checkable
class AgentInstalls(Protocol):
    """One agent and its install, read the way `brain.prompt_routes` reads one."""

    async def agent(self, agent_id: str) -> FoundAgent | None: ...


class StoredAgentInstalls:
    """`AgentInstalls` over `agent.agent` and its install rows."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def agent(self, agent_id: str) -> FoundAgent | None:
        async with self._sessions() as session:
            found = (
                await session.execute(every_agent_with_install().where(AgentRow.id == agent_id))
            ).one_or_none()
        if found is None:
            return None
        agent_row, instance_row, version_row = found
        record = record_of(agent_row)
        if record is None:
            return None
        return FoundAgent(
            record=record,
            install=installed(instance_row, version_row),
            effective_hash=None if instance_row is None else instance_row.effective_hash,
        )


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    """The factory, or a process-level fault identical for every caller.

    A `Failed` rather than an `Absent`, on `brain.routing_routes`' argument: an instance with no
    pool is broken rather than empty, and only a caller who already holds this screen's grant
    reaches this line.
    """
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def library_of(request: Request) -> SkillLibrary:
    """`app.state.skill_library` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "skill_library", None)
    if isinstance(found, SkillLibrary):
        return found
    return StoredSkills(_require_sessions(request))


def agent_installs_of(request: Request) -> AgentInstalls:
    """`app.state.agent_installs` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "agent_installs", None)
    if isinstance(found, AgentInstalls):
        return found
    return StoredAgentInstalls(_require_sessions(request))


# ---------------------------------------------------------------- the statements
def installs_of(agent_ids: Sequence[str]) -> Select[tuple[TemplateInstanceRow, TemplateVersionRow]]:
    """Every named agent's install and the version it is pinned to, joined on the pin's pair.

    Joined on both halves of the pin, template and version, because `agent.template_version`'s
    key is the pair. Ordered by instance id, so two readings of an unchanged install are one page.
    """
    return (
        select(TemplateInstanceRow, TemplateVersionRow)
        .join(
            TemplateVersionRow,
            and_(
                TemplateVersionRow.template_id == TemplateInstanceRow.template_id,
                TemplateVersionRow.version == TemplateInstanceRow.template_version,
            ),
        )
        .where(TemplateInstanceRow.id.in_(agent_ids))
        .order_by(TemplateInstanceRow.id)
    )


def bounded_agents(limit: int) -> Select[tuple[AgentRow]]:
    """Every stored agent, bounded. Filtered by audience afterwards, in Python.

    `brain.agent_routes.every_agent` is the statement and the bound is applied here, which is
    that module's `A_ROSTER_IS_FILTERED_BEFORE_IT_IS_BOUNDED` with the bound moved to the load.
    """
    return every_agent().limit(limit)


# ------------------------------------------------------------------ rows to pins
def pins_of(
    instance_row: TemplateInstanceRow, version_row: TemplateVersionRow, record: AgentRecord
) -> tuple[SkillPin, ...]:
    """The skills one agent is pinned to, or nothing when its install does not construct.

    `brain.agent_routes.install_of`'s refusal, for its reason: `materialise` checks the pin, the
    overlay and the seal, and none of those failures may become a status. The pins are
    `materialise`'s rather than the document's `skills` key, because an overlay may set that path,
    and assigning a skill from this screen is exactly an overlay setting it.
    """
    try:
        signed = SignedManifest(
            manifest=manifest_of(version_row.document),
            content_digest=version_row.content_digest,
            signature=version_row.signature,
            signed_by=version_row.signed_by,
            signed_at=version_row.signed_at,
        )
        instance = TemplateInstance(
            instance_id=instance_row.id,
            template_id=instance_row.template_id,
            template_version=instance_row.template_version,
            content_digest=instance_row.content_digest,
            overlay=instance_row.overlay,
            overlay_owners={
                path: FieldOwner.model_validate(owner)
                for path, owner in instance_row.field_owners.items()
            },
            created_by=instance_row.created_by,
        )
        effective = materialise(signed, instance, audience=record.audience)
    except (KeyError, ValueError, TemplateError) as exc:
        log.warning(
            "agent install does not construct", agent=record.agent_id, error=type(exc).__name__
        )
        return ()
    return effective.skill_pins


# ---------------------------------------------------------------- the projections
def catalogue(pins: Iterable[SkillPin]) -> tuple[SkillRow, ...]:
    """Every skill these pins name, in name order, with the agents pinned to each.

    Grouped by name rather than by name and digest, because a skill whose agents run different
    bytes is one skill with a disagreement on it. See
    `A_DIFFERENCE_BETWEEN_PINS_IS_ABOUT_THIS_PAGE_AND_NEVER_THE_ESTATE`.
    """
    held: dict[str, list[SkillPin]] = {}
    for pin in pins:
        held.setdefault(pin.skill_name, []).append(pin)
    return tuple(
        SkillRow(
            name=name,
            pinned_by=tuple(
                SkillPinView(agent_id=pin.agent_id, digest=pin.digest)
                for pin in sorted(held[name], key=lambda one: (one.agent_id, one.digest))
            ),
            versions_differ=len({pin.digest for pin in held[name]}) > 1,
        )
        for name in sorted(held)
    )


def submitted(library: Sequence[LibrarySkill], now: datetime) -> tuple[Placed[QueueEntry], ...]:
    """Every skill in the library waiting for a reviewer, placed where the queue narrows it.

    It was empty until `0056`, because nothing stored a submission, and it was a function so that
    the day a store existed this would be the one line that changed. It is:
    `brain.console.skill_library.queue_entries` over what the store holds.
    """
    return queue_entries(library, now)


def entry_view(entry: QueueEntry, now: datetime) -> QueueEntryView:
    """One queue entry, copied field by field, with staleness asked of the entry."""
    return QueueEntryView(
        name=entry.skill.skill.name,
        digest=entry.skill.skill.digest(),
        waiting_since=entry.waiting_since,
        changed=tuple(entry.changed),
        stale=entry.is_stale(now),
    )


def queue_view(
    entries: Sequence[Placed[QueueEntry]], reach: EntitlementSet, now: datetime
) -> SkillQueueView:
    """The queue this reader may see, and the summary of exactly that list.

    `brain.console.govern_estate.skill_queue` is the whole decision and it is not restated here.
    """
    narrowed = skill_queue(entries, reach, now)
    return SkillQueueView(
        entries=tuple(entry_view(one, now) for one in narrowed.entries),
        waiting=narrowed.summary.waiting,
        edits=narrowed.summary.edits,
        stale=narrowed.summary.stale,
    )


def library_view(
    one: LibrarySkill,
    reach: SkillReach,
    *,
    caller_id: str,
    discloses_body: bool,
    reviews: bool,
    assigns: bool,
) -> LibrarySkillView:
    """One library row, with the reach the registry gives it and what this reader is offered."""
    imported = one.imported
    state = review_state(imported)
    return LibrarySkillView(
        digest=one.digest,
        name=imported.skill.name,
        version=imported.skill.version,
        description=imported.skill.description,
        source=imported.source.kind.value,
        source_location=imported.source.location,
        submitted_by=one.submitted_by,
        submitted_at=one.submitted_at,
        review=state.value,
        reviewer=imported.reviewer or None,
        reviewed_at=imported.reviewed_at,
        tools=tuple(
            ToolReachView(name=tool.name, capability=tool.capability) for tool in reach.tools
        ),
        capabilities=reach.capabilities,
        unregistered_tools=reach.unknown,
        body=imported.skill.body if discloses_body else None,
        reviewable=(
            reviews and state is Review.PENDING and one.submitted_by != caller_id and not one.moved
        ),
        assignable=assigns and state is Review.APPROVED,
    )


def _unresolved(skill_tools: Sequence[str]) -> SkillReach:
    """What a skill reaches on a process with no registry: every tool it names, unresolved."""
    return SkillReach(
        tools=tuple(ToolReach(name=name, capability=None) for name in skill_tools),
        capabilities=(),
        unknown=tuple(skill_tools),
    )


# ------------------------------------------------------------------- the wiring
def _not_answerable() -> Absent:
    """The one refusal this router makes to a caller who may not act.

    Names the screen and never the row, the capability or the caller, which is
    `brain.govern_routes._not_answerable`'s construction.
    """
    return Absent(f"the {SKILLS_SCREEN} screen is not answerable for this caller")


def _refused_because(reason: str) -> Absent:
    """A refusal for a caller who may act, naming what to fix. `brain.prompt_routes`' shape."""
    return Absent(reason, public_message=reason)


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.session_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def visible_records(records: Sequence[AgentRecord], asked: Asking) -> tuple[AgentRecord, ...]:
    """The agents this caller's audience covers, in id order.

    `brain.agents.model.visible_agent_ids` is the answer and `brain.agent_routes.viewer_of`
    builds the viewer, so who may see an agent is decided once, by the module that owns it.
    """
    visible = visible_agent_ids(records, viewer_of(asked))
    return tuple(sorted((one for one in records if one.agent_id in visible), key=_by_id))


def _by_id(record: AgentRecord) -> str:
    return record.agent_id


router = APIRouter(prefix=API_PREFIX, tags=["skills"])


@router.get("/skills", response_model=SkillsPage, responses=COMMON_RESPONSES)
async def skills(
    request: Request,
    asked: Asked,
    limit: Annotated[int, Query(ge=1, le=MAX_AGENTS_CONSIDERED)] = DEFAULT_AGENTS_CONSIDERED,
) -> SkillsPage:
    """The skills the reader's agents run, the library and its queue, and what the reader may do.

    The screen's question first and the database second, and the order is the property: a caller
    holding no grant is refused identically on an instance with a database and on one without.

    The agents are loaded bounded and filtered by audience; their installs are read for exactly
    those agents. The library is read only for a reader it may be listed to, and the queue is
    narrowed again by `skill_queue`, so the two agree by being one question.
    """
    if not permitted(screen(SKILLS_SCREEN).read, asked.reach, asked.now):
        log.info("skills screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()

    factory = _require_sessions(request)
    async with factory() as session:
        rows = (await session.execute(bounded_agents(limit))).scalars().all()
        records = [record for record in (record_of(row) for row in rows) if record is not None]
        mine = visible_records(records, asked)
        pairs = (await session.execute(installs_of([one.agent_id for one in mine]))).all()

    by_id = {one.agent_id: one for one in mine}
    pins: list[SkillPin] = []
    for instance_row, version_row in pairs:
        record = by_id.get(instance_row.id)
        if record is None:
            # An install whose agent is outside this reader's audience, which the statement
            # above did not ask for. Dropped rather than trusted.
            continue
        pins.extend(pins_of(instance_row, version_row, record))

    readable = may_read_library(asked.reach, asked.now)
    library = await library_of(request).library(MAX_LIBRARY) if readable else ()
    registry = _tool_registry(request)
    reviews = may_review(asked.reach, asked.now)
    choices = tuple(
        AgentChoiceView(agent_id=one.agent_id, display_name=one.display_name)
        for one in mine
        if readable and may_assign(asked.reach, agent_scope_row(one), asked.now)
    )
    discloses = reviews or may_add(asked.reach, asked.now)
    return SkillsPage(
        items=list(catalogue(pins)),
        next_cursor=None,
        truncated=len(rows) >= limit,
        queue=queue_view(submitted(library, asked.now), asked.reach, asked.now),
        library=tuple(
            library_view(
                one,
                _unresolved(one.imported.skill.tools)
                if registry is None
                else trusted_reach(one.imported.skill, registry),
                caller_id=asked.caller.principal.id,
                discloses_body=discloses,
                reviews=reviews,
                assigns=bool(choices),
            )
            for one in library
        ),
        library_truncated=len(library) >= MAX_LIBRARY,
        agents=choices,
        may_add=may_add(asked.reach, asked.now),
        registry_is_absent=registry is None,
    )


def _package_bytes(body: SkillPackageAsked) -> bytes:
    if body.encoding == "text":
        return body.content.encode("utf-8")
    try:
        return base64.b64decode(body.content, validate=True)
    except (binascii.Error, ValueError):
        raise _refused_because(
            "this skill was not added: the file could not be read; choose it again"
        ) from None


def _view_for(one: LibrarySkill, request: Request, asked: Asking) -> LibrarySkillView:
    registry = _tool_registry(request)
    return library_view(
        one,
        _unresolved(one.imported.skill.tools)
        if registry is None
        else trusted_reach(one.imported.skill, registry),
        caller_id=asked.caller.principal.id,
        discloses_body=True,
        reviews=may_review(asked.reach, asked.now),
        assigns=False,
    )


@router.post(
    "/skills", status_code=201, response_model=LibrarySkillView, responses=COMMON_RESPONSES
)
async def add_skill(request: Request, body: SkillPackageAsked, asked: Asked) -> JSONResponse:
    """Add one skill to the library, undecided, or say why it was not added.

    See `AN_IMPORT_IS_A_SUBMISSION_AND_NEVER_AN_APPROVAL`. The authority is asked before the
    package is read, so a caller who may not add learns nothing about what a package would do.
    """
    if not may_add(asked.reach, asked.now):
        log.info("skill not addable", principal=asked.caller.principal.id)
        raise _not_answerable()
    try:
        package = read_package(body.file_name, _package_bytes(body))
        one = added(package, by=asked.caller.principal.id, at=asked.now)
    except SkillLibraryError as refused:
        raise _refused_because(str(refused)) from None
    library = library_of(request)
    spelt = another_spelling(one.imported.skill, await library.library(MAX_LIBRARY))
    if spelt is not None:
        raise _refused_because(
            f"this skill was not added: the library already holds {spelt!r}, which is the same "
            "name spelt differently; name this one the same way if it is a new version of it"
        )
    written = await library.add(one, ent_hash=asked.reach.ent_hash(), trace_id=_trace_id())
    if not written:
        raise _refused_because(
            f"this skill was not added: this version of {one.name!r} is already in the library"
        )
    log.info("skill added", skill=one.name, principal=asked.caller.principal.id)
    return JSONResponse(
        status_code=201, content=_view_for(one, request, asked).model_dump(mode="json")
    )


Digest = Annotated[str, Path(pattern=DIGEST_PATTERN)]


@router.post("/skills/{digest}/review", response_model=LibrarySkillView, responses=COMMON_RESPONSES)
async def review_skill(
    request: Request, digest: Digest, body: ReviewAsked, asked: Asked
) -> LibrarySkillView:
    """Approve or reject one skill, as somebody who did not add it, once.

    The authority first, before the digest is looked up. Then `decided`, which refuses the importer
    before anything else about the skill is considered.
    """
    if not may_review(asked.reach, asked.now):
        log.info("skill not reviewable", principal=asked.caller.principal.id)
        raise _not_answerable()
    library = library_of(request)
    one = await library.skill(digest)
    if one is None:
        raise _refused_because("nothing was decided: no skill in the library has that digest")
    try:
        after = decided(
            one,
            reviewer=asked.caller.principal.id,
            approve=body.decision == "approve",
            at=asked.now,
        )
    except SkillLibraryError as refused:
        raise _refused_because(str(refused)) from None
    written = await library.decide(after, ent_hash=asked.reach.ent_hash(), trace_id=_trace_id())
    if not written:
        raise _refused_because(
            f"nothing was decided: somebody decided about {one.name!r} first; reload to see it"
        )
    log.info("skill decided", skill=one.name, principal=asked.caller.principal.id)
    return _view_for(after, request, asked)


@router.post(
    "/skills/{digest}/assignments",
    status_code=201,
    response_model=AssignedView,
    responses=COMMON_RESPONSES,
)
async def assign_skill(
    request: Request, digest: Digest, body: AssignAsked, asked: Asked
) -> JSONResponse:
    """Assign one approved skill to one agent through `attach_skill`, or say why not.

    The authority is asked of the reach alone first, then of the agent's row once the agent is
    read, and an agent outside the caller's audience or outside their authority is the same
    refusal as one that does not exist. Only then is the skill looked up.
    """
    if not permitted(screen(SKILLS_SCREEN).read, asked.reach, asked.now) or (
        asked.reach.scope_for(SKILL_AUTHORITY, asked.now) is None
    ):
        log.info("skill not assignable", principal=asked.caller.principal.id)
        raise _not_answerable()
    found = await agent_installs_of(request).agent(body.agent_id)
    if (
        found is None
        or body.agent_id not in visible_agent_ids((found.record,), viewer_of(asked))
        or not may_assign(asked.reach, agent_scope_row(found.record), asked.now)
    ):
        log.info("skill not assignable to this agent", principal=asked.caller.principal.id)
        raise _not_answerable()
    if found.install is None or found.effective_hash is None:
        raise _refused_because(
            "nothing was assigned: this agent has no install record that constructs, so there is "
            "no manifest to pin a skill in"
        )
    library = library_of(request)
    one = await library.skill(digest)
    if one is None:
        raise _refused_because("nothing was assigned: no skill in the library has that digest")
    now = asked.now
    recorder = AuditRecorder(
        AuditChain(),
        actor_id=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id() or "unassigned",
        clock=lambda: now,
    )
    signed, instance = found.install
    try:
        made = assignment(
            one,
            record=found.record,
            signed=signed,
            instance=instance,
            library=await library.library(MAX_LIBRARY),
            by=asked.reach,
            recorder=recorder,
            now=now,
        )
    except (SkillLibraryError, AgentTabError) as refused:
        raise _refused_because(str(refused)) from None
    except (TemplateError, WorkspaceError, ValueError):
        raise _refused_because(
            "nothing was assigned: the agent's install refused this skill"
        ) from None
    written = await library.assign(
        made,
        expected_hash=found.effective_hash,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    )
    if not written:
        raise _refused_because(
            "nothing was assigned: somebody changed this agent after you opened it; reload and "
            "assign again"
        )
    registry = _tool_registry(request)
    reach = (
        ()
        if registry is None
        else reach_through(one.imported.skill, registry, asked.reach, found.record, now)
    )
    log.info(
        "skill assigned", skill=one.name, agent=made.agent_id, principal=asked.caller.principal.id
    )
    view = AssignedView(
        agent_id=made.agent_id,
        skill_name=made.skill_name,
        digest=made.digest,
        replaced_digest=made.replaces_digest,
        reach=reach,
        effective_hash=made.effective_hash,
    )
    return JSONResponse(status_code=201, content=view.model_dump(mode="json"))
