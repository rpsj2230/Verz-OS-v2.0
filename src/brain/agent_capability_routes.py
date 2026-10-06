"""What one agent is built from and who can use it, in the detail its Profile draws, and a preview.

`brain.console.workspace_capabilities` and `brain.console.agent_tabs` decided, a fortnight before
anything could ask them, how an agent's capability block reads for one reader: a connector row with
the fields it projects and the health the Connectors page probed; a skill chip with its version,
source and review state, the approved library skills that could be attached and the ones that can
only be sent to review; how often each attached skill ran; the knowledge an agent draws on as a
predicate, with how many of the reader's own documents it matches and how fresh they are. And
`brain.console.reach_view` decided the availability block and a worked preview of one person's run.
None of it had a route. This module is the route, and it adds no rule of its own about what a
reader may be told: every block is the domain function's answer, called as its docstring says.

**One read for the Profile's detail, separate from the workspace read.** The workspace answers the
header and the view switch for every visitor and is asked on every view; this is asked only when
the Profile is drawn, and it reads the library, the Connectors page's health and the reader's own
documents, which are three reads nobody opening the Dashboard should pay for. Rejected: widening
`WorkspaceView`, which put those reads on every page load of every agent.

**Each block is gated where the workspace gates its sibling, so the two cannot disagree.**
Connectors are narrowed by `brain.api_routes.reachable_sources`, as the workspace's strip is.
Skills travel with the Settings tab and the Skills screen's read, as the workspace's chips do, and
the library's offers only to a reader the library is listed to. The knowledge slice is the
Knowledge tab's read (`read:document` on the existence plane) and is computed over documents this
reader may already see, so a count of the slice is never a count of anything hidden. The
availability block is the audience's, which is who may open the agent at all. See
`EVERY_BLOCK_IS_GATED_WHERE_ITS_WORKSPACE_SIBLING_IS`.

**A preview is the run the gate would make for that person, never an estimate.** `run_preview`
calls `brain.gate.invoke.invoke`, and the entitlement it is handed is `E_run(person, agent)`, taken
through `brain.console.workspace_capabilities.run_reach`, the console's one route into the one
intersection. `reach_view.run_preview` hands `invoke` whatever it is given and `invoke` narrows
nothing, so passing the person's own entitlement would preview a run wider than the agent's
ceiling on every capability the tool registry does not re-check. See
`A_PREVIEW_IS_THE_RUN_REACH_AND_NEVER_THE_PERSONS_OWN`. Who may ask is `PREVIEW_DISCLOSURE`, the
People screen's read, because previewing a person's run is reading what that person holds; a
reader without it is answered as an agent that does not exist.

**What is still absent, and why.** A connector's attach and detach, and a channel's enablement,
write the agent's install and need a ledger row nothing yet appends (the next package). The items
an agent retrieved most and never touched (M39.2.3.5) need a per-item retrieval record, and nothing
on an install writes one: `brain.knowledge.quality.RetrievalEvent` carries no item by design.

Task ids: M39.2.1.1, M39.2.1.3, M39.2.1.4, M39.2.1.5, M39.2.2.1, M39.2.2.2, M39.2.2.3
Task ids: M39.2.2.4, M39.2.2.5, M39.2.3.1, M39.2.3.2, M39.2.3.3, M39.2.3.4
Task ids: M39.3.1.1, M39.3.1.2, M39.3.1.3, M39.3.1.4
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import (
    HEADLINE_RANGE,
    POPULATED_HERE,
    Install,
    _no_agent_here,
    _require_session_factory,
    _tool_registry,
    _visible_record,
    holds_settings,
    install_for,
    install_of,
    leash_of,
    product_field_policy,
    steward_names,
    viewer_of,
)
from brain.agents.attachments import narrowed
from brain.agents.model import AgentRecord, AgentViewer
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, sources_at
from brain.connector_routes import manifest_or_none, records_of, sync_records_of
from brain.console.agent_tabs import (
    SKILL_SCREEN,
    Control,
    SkillInvocation,
    chip_for,
    offer_for,
    skill_usage,
    slice_health,
    usage_basis,
)
from brain.console.connector_trust import attempt_as_health
from brain.console.reach_view import (
    PREVIEW_DISCLOSURE,
    PREVIEW_RETURNS_NOTHING,
    availability_block,
    run_preview,
)
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.skill_library import LibrarySkill, may_assign, may_read_library
from brain.console.workspace import Basis, Tab, tab, tab_strip, window
from brain.console.workspace_capabilities import (
    CapabilitiesError,
    KnowledgeScope,
    connector_rows,
    projected_for,
    run_reach,
)
from brain.core.entitlement import EntitlementSet
from brain.gate.badge_store import NO_BODY_READ
from brain.gate.entitlement_store import StoredEntitlements
from brain.gate.screening import NOTHING_MATCHED
from brain.knowledge.item import KnowledgeItem
from brain.knowledge.lifecycle import StoredItem, authority_for
from brain.knowledge.lifecycle_store import MAX_ITEMS, as_person, live_items
from brain.knowledge_routes import live_departments
from brain.ops.attachment_store import changes_in
from brain.ops.connector_store import Connection
from brain.ops.skill_store import MAX_LIBRARY
from brain.prompt_routes import agent_scope_row
from brain.skill_routes import library_of
from brain.tables.skill_invocation import SkillInvocationRow
from brain.tools.registry import ToolRegistry

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why no block here is gated by a rule of this module's own.
EVERY_BLOCK_IS_GATED_WHERE_ITS_WORKSPACE_SIBLING_IS: Final = (
    "The workspace already decided who is told an agent's connectors, skills and configuration. "
    "Each block here asks the same question of the same function, so a reader shown a connector "
    "in the header's strip is shown its detail here, and a reader refused one is refused both."
)

#: Why the preview is run at the run reach.
A_PREVIEW_IS_THE_RUN_REACH_AND_NEVER_THE_PERSONS_OWN: Final = (
    "A run of an agent reaches what its caller holds narrowed by the agent's ceiling, and invoke "
    "narrows nothing itself. So the preview hands it E_run(person, agent) from run_reach, and a "
    "preview can never show a tool the agent's ceiling would not have let the run reach."
)

# ------------------------------------------------------------------------ the figures
CAPABILITIES_PATH: Final = "/agents/{agent_id}/capabilities"
PREVIEW_PATH: Final = "/agents/{agent_id}/preview"

#: The most library skills offered beside an agent's own. The library's own bound, so an offer
#: list is never a second, longer read of it.
MAX_OFFERS: Final = MAX_LIBRARY

#: The most of the reader's documents one slice is computed over, which is the documents list's
#: own bound, so the slice and that list agree.
MAX_SLICE_ITEMS: Final = MAX_ITEMS


# ------------------------------------------------------------------------------ the views
class AvailabilityView(BaseModel):
    """Who may find and start this agent. Discovery, and never authority (M39.3.1.1, M39.3.1.3).

    `reach_view.AvailabilityBlock` whole: its level, the department at the department level, the
    steward, whether the reader is in the audience, and its `copy` as `words`, which is
    `brain.agents.model.AUDIENCE_IS_NOT_AUTHORITY` itself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: str
    department: str | None = None
    owner_id: str
    reader_is_included: bool
    #: What the block says under its heading: availability is discovery and never authority.
    words: str


class ConnectorDetailView(BaseModel):
    """One connector on the agent, as `ConnectorRow` carries it (M39.2.1.1, .3, .4, .5).

    `projects` are the fields this reader's run through the agent would see, and never a count
    of the rest. `health` and `checked_at` are the Connectors page's last attempt, copied, and
    null together for a source nobody has tried.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    presence: str
    projects: list[str] = []
    health: str | None = None
    checked_at: datetime | None = None


class SkillChipView(BaseModel):
    """One skill the agent is pinned to (M39.2.2.1, M39.2.2.4).

    `version`, `source` and `review` come from the library row with the pinned digest and are
    null for a skill the agent's template shipped, which has no library row. `runs` is how many
    requests used it in the headline's window, at `usage_basis`. `detachable` says the reader may
    take it off here, which the Skills page's detach route decides again when pressed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    digest: str
    version: str | None = None
    source: str | None = None
    review: str | None = None
    runs: int
    detachable: bool = False


class SkillOfferView(BaseModel):
    """One library skill this agent is not pinned to, and the one control offered beside it.

    `control` is `brain.console.agent_tabs.Control`: attach for an approved skill a reader who may
    assign is offered, review with the `route` to the skill's own page for anything unapproved,
    nothing otherwise. Never both (M39.2.2.2, M39.2.2.3).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str
    digest: str
    review: str
    control: str
    route: str = ""


class ClauseView(BaseModel):
    """One clause of the knowledge predicate: a field of a document's place, and a value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    op: str
    value: str


class KnowledgeSliceView(BaseModel):
    """What the agent draws on, as a predicate, and how this reader's share of it stands.

    `clauses` are the predicate (M39.2.3.1): an empty list means the agent narrows nothing of its
    own. `matched` is how many of the documents this reader may see the predicate reaches
    (M39.2.3.3); `verified`, `stale` and `unverified` split it by the badge each carries
    (M39.2.3.4). Every figure counts what the reader was shown, so none is a count of anything
    hidden. `at_least` says the reader's documents were read to their bound.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    clauses: list[ClauseView]
    matched: int
    verified: int
    stale: int
    unverified: int
    at_least: bool = False


class AgentCapabilitiesView(BaseModel):
    """An agent's capabilities and availability, as this reader may be told them.

    No field is a count of what was withheld. `skills` and `offers` are empty for a reader the
    workspace would send no skills; `knowledge` is null for a reader without the Knowledge tab's
    read, or for an agent whose records are not described by where documents sit.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    availability: AvailabilityView
    connectors: list[ConnectorDetailView] = []
    skills: list[SkillChipView] = []
    #: The pinned skills with no run in the window, which is the list somebody prunes from.
    unused_skills: list[str] = []
    #: Whose runs the skill figures count: `own` or `everyone`.
    usage_basis: str
    #: Whether this reader may attach and detach skills on this agent here.
    skills_editable: bool = False
    offers: list[SkillOfferView] = []
    knowledge: KnowledgeSliceView | None = None


class PreviewAsked(BaseModel):
    """Whose run to preview: a person's principal id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    person_id: Annotated[str, Field(min_length=1, max_length=200)]


class PreviewToolView(BaseModel):
    """One tool the previewed run would be handed, by name, with the registry's description."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str | None = None


class PreviewView(BaseModel):
    """What one person's run of this agent would be handed, computed by the gate (M39.3.1.4).

    `tools` and `rung` are empty and null together when the run would not start, and `notice` is
    then `reach_view.PREVIEW_RETURNS_NOTHING` for every reason it could have been refused.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    person_id: str
    person_name: str | None = None
    tools: list[PreviewToolView] = []
    rung: str | None = None
    notice: str = ""


# ------------------------------------------------------------------------- the decisions
def availability_view(record: AgentRecord, viewer: AgentViewer) -> AvailabilityView:
    """`reach_view.availability_block`, sent whole."""
    block = availability_block(record, viewer)
    return AvailabilityView(
        level=block.level,
        department=block.department or None,
        owner_id=block.owner_id,
        reader_is_included=block.reader_is_included,
        words=block.copy,
    )


def projections_for(
    connections: Sequence[Connection], reach: EntitlementSet, now: datetime
) -> dict[str, tuple[str, ...]]:
    """The fields each connected source would show a run at `reach`, by source (M39.2.1.3).

    Over every entity the source's manifest projects, in its declared order, through
    `projected_for` and the product's field policy. A source whose settings build no manifest
    today projects nothing rather than failing the page.
    """
    policy = product_field_policy()
    found: dict[str, tuple[str, ...]] = {}
    for one in connections:
        manifest = manifest_or_none(one)
        if manifest is None:
            continue
        fields: list[str] = []
        for entity in manifest.projections:
            fields.extend(
                f"{entity.entity}.{name}" for name in projected_for(entity, reach, policy, now)
            )
        found[one.connector] = tuple(fields)
    return found


def connector_details(
    install: Install | None,
    record: AgentRecord,
    registry: ToolRegistry | None,
    reach: EntitlementSet,
    now: datetime,
    *,
    connections: Sequence[Connection] = (),
    health: Mapping[str, object] = {},
) -> list[ConnectorDetailView]:
    """The connector rows `agent_routes.reader_connector_rows` draws, with projections and health.

    The same three sets, decided by the same functions: the manifest's declared list, the sources
    behind the tools the ceiling allows, and `sources_at` for what this reader may be told of.
    """
    from brain.connectors.contract import ConnectorHealth

    if install is None or registry is None:
        return []
    visible = sources_at(registry, reach, now)
    allowed = record.authority.allowed_tools
    attached = {one.source for one in registry.definitions() if one.name in allowed and one.source}
    rows = connector_rows(
        declared=install.connectors,
        attached=attached,
        visible=visible,
        projections=projections_for(connections, run_reach(reach, record), now),
        health={
            name: probe for name, probe in health.items() if isinstance(probe, ConnectorHealth)
        },
    )
    return [
        ConnectorDetailView(
            source=one.source,
            presence=one.presence.value,
            projects=list(one.projects),
            health=None if one.health is None else one.health.value,
            checked_at=one.checked_at,
        )
        for one in rows
    ]


def invocations_of(
    agent_id: str, since: datetime, *, basis: Basis, caller_id: str
) -> Select[tuple[str, str, datetime]]:
    """The skill runs this agent made since an instant, the caller's alone on the narrower basis.

    `brain.console_stats_routes.skill_invocations` with the agent in place of the skill: the basis
    is in the WHERE clause, so nobody else's run reaches this process for a reader who may not
    read usage.
    """
    from brain.console.entity_stats import MAX_ACTIVITY_ROWS

    statement = select(
        SkillInvocationRow.principal_id,
        SkillInvocationRow.skill_name,
        SkillInvocationRow.used_at,
    ).where(SkillInvocationRow.agent_id == agent_id, SkillInvocationRow.used_at >= since)
    if basis is not Basis.EVERYONE:
        statement = statement.where(SkillInvocationRow.principal_id == caller_id)
    return statement.order_by(SkillInvocationRow.used_at.desc()).limit(MAX_ACTIVITY_ROWS)


def newest_by_name(library: Sequence[LibrarySkill]) -> dict[str, LibrarySkill]:
    """The newest version of each skill in the library, by name."""
    newest: dict[str, LibrarySkill] = {}
    for one in library:
        held = newest.get(one.name)
        if held is None or one.submitted_at > held.submitted_at:
            newest[one.name] = one
    return newest


def skill_blocks(
    install: Install | None,
    record: AgentRecord,
    *,
    library: Sequence[LibrarySkill],
    invocations: Sequence[SkillInvocation],
    reach: EntitlementSet,
    caller_id: str,
    basis: Basis,
    listed: bool,
    editable: bool,
    now: datetime,
) -> tuple[list[SkillChipView], list[str], list[SkillOfferView]]:
    """The agent's skill chips, the pinned ones nobody used, and the library's offers.

    Chips from the pins, joined to the library by digest (M39.2.2.1). Runs from `skill_usage`
    over the headline window (M39.2.2.4). Offers only when the library is listed to the reader,
    each `offer_for`'s one control, and an attach offered only to a reader who may assign here
    (M39.2.2.2, M39.2.2.3); the description convention is enforced where the assignment is made,
    by `agent_tabs.register_skill` (M39.2.2.5).
    """
    if install is None:
        return [], [], []
    by_digest = {one.digest: one for one in library}
    since, until = window(HEADLINE_RANGE, now)
    usage = skill_usage(
        record.agent_id,
        invocations,
        attached=[one.name for one in install.skills],
        caller_id=caller_id,
        basis=basis,
        since=since,
        until=until,
    )
    runs = {one.skill_name: one.invocations for one in usage.used}
    chips: list[SkillChipView] = []
    for pin in install.skills:
        row = by_digest.get(pin.digest)
        chip = None if row is None else chip_for(row.imported)
        chips.append(
            SkillChipView(
                name=pin.name,
                digest=pin.digest,
                version=None if chip is None else chip.version,
                source=None if chip is None else chip.source.value,
                review=None if chip is None else chip.review.value,
                runs=runs.get(pin.name, 0),
                detachable=editable and row is not None,
            )
        )
    offers: list[SkillOfferView] = []
    if listed:
        pinned = {one.name for one in install.skills}
        for name, one in sorted(newest_by_name(library).items()):
            if name in pinned:
                continue
            offer = offer_for(one.imported, reach, now)
            control = offer.control
            if control is Control.ATTACH and not editable:
                control = Control.NOTHING
            offers.append(
                SkillOfferView(
                    name=offer.chip.name,
                    version=offer.chip.version,
                    digest=one.digest,
                    review=offer.chip.review.value,
                    control=control.value,
                    route=offer.route,
                )
            )
        offers = offers[:MAX_OFFERS]
    return chips, list(usage.unused), offers


def knowledge_item_of(one: StoredItem) -> KnowledgeItem:
    """A stored document as the record a predicate and a badge read, with no body read."""
    return KnowledgeItem(
        item_id=one.item_id,
        content=NO_BODY_READ,
        title=one.title,
        visibility=one.visibility,
        owner_id=one.owner_id,
        state=one.state,
        verified_by=one.verified_by,
        verified_at=one.verified_at,
        review_by=one.review_by,
        supersedes=one.supersedes,
        kind=one.kind,
    )


def knowledge_scope_of(record: AgentRecord) -> KnowledgeScope | None:
    """The agent's knowledge predicate, or None when its scope is not about where documents sit.

    The scope the agent's records are narrowed by is the predicate its knowledge is narrowed by
    (`brain.agents.model.entitlement_ceiling` binds every capability to it), and
    `KnowledgeScope` refuses a clause on any field a document's place does not carry.
    """
    try:
        return KnowledgeScope(agent_id=record.agent_id, predicate=record.authority.scope)
    except CapabilitiesError:
        return None


async def reader_items(
    sessions: async_sessionmaker[AsyncSession], reach: EntitlementSet, now: datetime
) -> tuple[tuple[KnowledgeItem, ...], bool]:
    """The live documents this reach may see, as the documents list reads them, and whether the
    read came back full."""
    departments = await live_departments(sessions)
    authority = authority_for(reach, departments=departments, now=now)
    async with sessions() as session, session.begin():
        await as_person(session, authority)
        found = await live_items(session, limit=MAX_SLICE_ITEMS)
    seen = tuple(knowledge_item_of(one) for one in found if authority.may_see(one))
    return seen, len(found) >= MAX_SLICE_ITEMS


def knowledge_view(
    scope: KnowledgeScope, items: Sequence[KnowledgeItem], *, at_least: bool, now: datetime
) -> KnowledgeSliceView:
    """The predicate, and `slice_health` over the reader's own documents (M39.2.3.1, .3, .4)."""
    health = slice_health(scope, items, now=now)
    return KnowledgeSliceView(
        clauses=[
            ClauseView(field=one.field, op=one.op.value, value=str(one.value))
            for one in scope.predicate.clauses
        ],
        matched=health.matched,
        verified=health.verified,
        stale=health.stale,
        unverified=health.unverified,
        at_least=at_least,
    )


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(CAPABILITIES_PATH, response_model=AgentCapabilitiesView, responses=COMMON_RESPONSES)
async def agent_capabilities(
    request: Request, agent_id: str, asked: Asked
) -> AgentCapabilitiesView:
    """One agent's capability detail and availability, or the answer a missing agent gets.

    The audience admits the caller before anything else about the agent is read.
    """
    factory = _require_session_factory(request)
    registry = _tool_registry(request)
    caller_id = asked.caller.principal.id
    basis = usage_basis(asked.reach, asked.now)
    since, _ = window(HEADLINE_RANGE, asked.now)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        pair = (await session.execute(install_for(agent_id))).one_or_none()
        rows = (
            await session.execute(invocations_of(agent_id, since, basis=basis, caller_id=caller_id))
        ).all()
        # The tools it carries now, so a connector shows attached exactly when a run could use it.
        record = narrowed(record, await changes_in(session, (agent_id,)))
    install = install_of(pair[0], pair[1], record) if pair is not None else None
    strip = tab_strip(asked.reach, populated=POPULATED_HERE, now=asked.now)
    reads_skills = holds_settings(strip) and permitted(
        screen(SKILL_SCREEN).read, asked.reach, asked.now
    )

    connections = await _connections(request)
    health = await _health(request)
    connectors = connector_details(
        install,
        record,
        registry,
        asked.reach,
        asked.now,
        connections=connections,
        health=health,
    )

    chips: list[SkillChipView] = []
    unused: list[str] = []
    offers: list[SkillOfferView] = []
    editable = False
    if reads_skills:
        listed = may_read_library(asked.reach, asked.now)
        editable = listed and may_assign(asked.reach, agent_scope_row(record), asked.now)
        library = await library_of(request).library(MAX_LIBRARY) if listed else ()
        invocations = [
            SkillInvocation(agent_id=agent_id, skill_name=name, principal_id=who, at=at)
            for who, name, at in rows
        ]
        chips, unused, offers = skill_blocks(
            install,
            record,
            library=library,
            invocations=invocations,
            reach=asked.reach,
            caller_id=caller_id,
            basis=basis,
            listed=listed,
            editable=editable,
            now=asked.now,
        )

    knowledge: KnowledgeSliceView | None = None
    scope = knowledge_scope_of(record)
    if scope is not None and permitted(tab(Tab.KNOWLEDGE).read, asked.reach, asked.now):
        items, full = await reader_items(factory, asked.reach, asked.now)
        knowledge = knowledge_view(scope, items, at_least=full, now=asked.now)

    return AgentCapabilitiesView(
        agent_id=agent_id,
        availability=availability_view(record, viewer_of(asked)),
        connectors=connectors,
        skills=chips,
        unused_skills=unused if reads_skills else [],
        usage_basis=basis.value,
        skills_editable=editable,
        offers=offers,
        knowledge=knowledge,
    )


async def _connections(request: Request) -> tuple[Connection, ...]:
    records = records_of(request)
    return () if records is None else tuple(await records.connected())


async def _health(request: Request) -> dict[str, object]:
    synced = sync_records_of(request)
    if synced is None:
        return {}
    states = await synced.states()
    return {
        name: probe
        for name, probe in ((name, attempt_as_health(state)) for name, state in states.items())
        if probe is not None
    }


async def preview_of(
    sessions: async_sessionmaker[AsyncSession],
    *,
    record: AgentRecord,
    install: Install | None,
    registry: ToolRegistry,
    person_id: str,
    previewer: EntitlementSet,
    now: datetime,
) -> PreviewView | None:
    """One person's run of this agent as the gate would build it, or None for a previewer who
    may not ask. See `A_PREVIEW_IS_THE_RUN_REACH_AND_NEVER_THE_PERSONS_OWN`.

    The previewer is asked first, as `run_preview` asks, so nobody's grants are read on behalf of
    somebody who may not be told them.
    """
    if previewer.scope_for(PREVIEW_DISCLOSURE, now) is None:
        return None
    person = await StoredEntitlements(sessions).load(person_id, now)
    made = run_preview(
        record=record,
        subject_id=person_id,
        subject_entitlement=run_reach(person, record),
        previewer=previewer,
        registry=registry,
        leash=leash_of(install, registry),
        assessment=NOTHING_MATCHED,
        now=now,
    )
    if made is None:
        return None
    async with sessions() as session:
        names = await steward_names(session, [person_id])
    rung = made.rung()
    described = {one.name: one.description for one in registry.definitions()}
    return PreviewView(
        person_id=person_id,
        person_name=names.get(person_id),
        tools=[
            PreviewToolView(name=name, description=described.get(name) or None)
            for name in made.reaches()
        ],
        rung=None if rung is None else rung.name.lower(),
        notice=made.notice,
    )


@router.post(PREVIEW_PATH, response_model=PreviewView, responses=COMMON_RESPONSES)
async def preview_agent(
    request: Request, agent_id: str, body: PreviewAsked, asked: Asked
) -> PreviewView:
    """What one person's run of this agent would be handed. See the module docstring.

    A reader who may not preview is answered as an agent that does not exist, and a person who
    does not exist is a run that would return nothing, as a person who holds nothing is.
    """
    factory = _require_session_factory(request)
    registry = _tool_registry(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        pair = (await session.execute(install_for(agent_id))).one_or_none()
    install = install_of(pair[0], pair[1], record) if pair is not None else None
    if registry is None:
        return PreviewView(person_id=body.person_id, notice=PREVIEW_RETURNS_NOTHING)
    made = await preview_of(
        factory,
        record=record,
        install=install,
        registry=registry,
        person_id=body.person_id,
        previewer=asked.reach,
        now=asked.now,
    )
    if made is None:
        log.info("agent preview not answerable", principal=asked.caller.principal.id)
        raise _no_agent_here()
    return made
