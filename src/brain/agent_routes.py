"""The agent roster and one agent's workspace over HTTP, and why they refuse alike.

`brain.console.workspace` builds a tab strip, a deep link and a composition diff, and the
console's agent page has asked `GET /api/v1/agents/{agent_id}/workspace` since M39.1.2.1 was
closed, answered by nothing, so every agent rendered the API's 404 sentence. The roster the
workspace's way back points at did not exist either. This module is both halves, and it adds
no rule of its own about who may see an agent or what they may read about one.

**Who may see an agent is its audience and nothing else.** `brain.agents.model.
visible_agent_ids` answers it for the roster and for the workspace alike, so an agent listed
is an agent that opens, and an agent that opens is an agent listed. Neither route asks for a
capability to know an agent exists: the audience is who may see and start it, and a roster
that also demanded `read:agent` would be a second answer to that question, stricter than the
picker a member already has, and the two would disagree about the same person on the same
day. What a capability decides is what a reader may read *about* an agent, and that is
`tab_strip`'s question. See `AUDIENCE_DECIDES_WHO_SEES_AN_AGENT_AND_NOTHING_ELSE_DOES`.

**An agent this caller may not see and an agent that does not exist are one 404 with one
body.** `_no_agent_here` is the only refusal either route makes about an agent, and it is
raised for a missing row, a row outside the audience and a row that does not construct. That
is `brain.agents.model.A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER` at the edge of the
process, and it is worth holding here as well as there because an address bar is a loop:
a caller who could tell "no such agent" from "not yours" would enumerate the company's agents
by trying slugs.

**The roster is a listing, and a listing is where a total leaks.** `brain.memory.review`
makes the argument for its own three listings: a page of rows wants a total at the top, and a
total beside a filtered list is the number of things the reader may not see. So `RosterPage`
never sets the `total` it inherits from `brain.api.Page`, an agent outside the audience is
absent rather than drawn greyed out, and the bound on the page is applied *after* the
audience filter. Bounding in SQL first would be the subtle version of the same leak: a full
page of rows of which three survive says there were others. See `A_ROSTER_IS_FILTERED_BEFORE_
IT_IS_BOUNDED`.

**The strip is `tab_strip` at the caller's own reach, never at the agent's.** A tab is an
administrative read about the agent, which a person holds or does not, and an agent's
ceiling never holds `read:agent`, so an intersection here would remove every tab for
everybody and look like caution. Nothing in this module intersects two entitlement sets;
`brain.console.workspace.intersections_in` is run over this source by its test.

**Only what this route holds is populated.** `tab_strip` shows a tab that is permitted *and*
has something in it, and says `populated` is handed in because what is in each tab is seven
questions of seven modules. This route answers one of them: it holds the agent's record and
its install, which is the Settings tab's content. The other six have no route serving their
read, so they are not populated, and they are absent from the strip rather than drawn over an
empty panel. See `ONLY_WHAT_THIS_ROUTE_HOLDS_IS_POPULATED`.

**The composition travels exactly when the Settings tab does.** `composition_rows` carries
the persona, which is prompt material, and says whether somebody may see it is the strip's
question. So the rows are sent when the strip holds Settings, and a reader without it gets an
empty list, which is also what an agent with no install gets. `set_by` is never sent, for
`A_COMPOSITION_ROW_SAYS_WHAT_AND_NEVER_WHO`.

**A row that does not construct is absent for everybody.** A record that fails its own
validators is refused as though it were not there, uniformly, whoever asks, and logged at a
level an operator reads. A 500 would be the obvious answer and it is an oracle in both
routes: one bad row would take the roster down for every person, and on the workspace a 500
for a broken agent beside a 404 for a missing one says which slugs exist. See
`A_ROW_THAT_DOES_NOT_CONSTRUCT_IS_ABSENT_FOR_EVERYBODY`.

**The viewer is the caller and their primary department, and that is a gap stated rather than
hidden.** `AgentViewer.departments` is a set because a person can sit in two departments, and
`brain.core.principal.Principal` carries one. There is no membership read on the request path
today, so a person in Sales and Web sees Web's department agents and not Sales'. It fails in
the narrow direction, which is the direction a gap is allowed to fail in. See
`THE_VIEWER_IS_THEIR_PRIMARY_DEPARTMENT_UNTIL_MEMBERSHIP_IS_READ`.

Rejected: a SQL predicate for the audience. It would be cheaper on a large estate, and it
would be a second implementation of `visible_to` written in another language, and a second
copy of a visibility rule is the copy that is subtly wrong in production. Agents are counted
in tens on an installation, so reading every row and filtering in Python costs nothing
measurable; the day that stops being true the fix is `audience_scope` compiled through
`brain.core.scope_sql`, which is the same predicate rather than a second one.

Rejected: verifying the template's signature on read. `brain.agents.template.install` does it
at the moment a manifest becomes configuration, and it needs the installation's signing key.
What a read needs is that the row is the body that was signed, and `SignedManifest` recomputes
the digest on construction without any key, so a document edited after signing still cannot
reach a response.

Rejected: a disabled or archived flag on a roster entry. `brain.agents.model.
runnable_agent_ids` records why a caller is told nothing about why an agent they used
yesterday is not chosen today, and a roster saying "disabled" beside a name is that sentence.

Task ids: M39.1.2.5
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.model import (
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    AgentViewer,
    visible_agent_ids,
)
from brain.agents.template import (
    MANIFEST_PATHS,
    FieldOwner,
    SignedManifest,
    TemplateError,
    TemplateInstance,
    TemplateManifest,
    materialise,
)
from brain.api import API_PREFIX, COMMON_RESPONSES, Page
from brain.api_routes import Asked, Asking
from brain.console.workspace import (
    Tab,
    WorkspaceTab,
    composition_rows,
    tab_strip,
)
from brain.core.entitlement import Capability
from brain.core.envelope import SideEffect
from brain.core.errors import Absent, Failed
from brain.core.scope import Scope
from brain.knowledge.visibility import Visibility
from brain.models.routing import Tier
from brain.routing_routes import sessions_of
from brain.tables.agent import AgentRow
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

log = structlog.get_logger()


# ------------------------------------------------------------ written-down reasons

#: Why neither route asks for a capability before saying an agent exists.
AUDIENCE_DECIDES_WHO_SEES_AN_AGENT_AND_NOTHING_ELSE_DOES: Final = (
    "An agent's audience is who may see and start it, and visible_agent_ids is the one "
    "answer to that question. A roster that also required a capability would be a second "
    "answer, stricter than the picker a member already has, and a person would find an agent "
    "in one place and not the other. A capability decides what a reader may read about an "
    "agent, which is the tab strip's question, and never whether the agent is there."
)

#: Why the roster's bound is applied to the filtered list and not to the query.
A_ROSTER_IS_FILTERED_BEFORE_IT_IS_BOUNDED: Final = (
    "A page bounded in SQL and then filtered by audience comes back short whenever the "
    "filter did anything, and a page of three under a limit of fifty says there were rows "
    "the reader was not shown. So every row is read, the audience filter runs first, and the "
    "bound is applied to what survived. truncated then says there are more agents this "
    "reader may see, and never how many they may not."
)

#: Why the strip is told one tab has something in it.
ONLY_WHAT_THIS_ROUTE_HOLDS_IS_POPULATED: Final = (
    "tab_strip shows a tab that is permitted and populated, and a heading over an empty panel "
    "is a count of hidden things spelled out. This route holds the agent's record and its "
    "install, which is what the Settings tab reads, and holds nothing any other tab reads. "
    "Marking the other six populated would draw six headings over nothing; marking Settings "
    "empty would withhold a tab whose content is already in the response."
)

#: Why a malformed row is refused as though it were missing.
A_ROW_THAT_DOES_NOT_CONSTRUCT_IS_ABSENT_FOR_EVERYBODY: Final = (
    "A stored agent that fails its own validators cannot have its audience evaluated, so "
    "there is no reader it could safely be shown to. Answering 500 would take the whole "
    "roster down for every person over one row, and on the workspace would distinguish a "
    "broken agent from a missing one, which says the slug exists. It is absent for everybody "
    "alike and it is logged, so the difference reaches an operator and never a response."
)

#: Why the viewer carries at most one department.
THE_VIEWER_IS_THEIR_PRIMARY_DEPARTMENT_UNTIL_MEMBERSHIP_IS_READ: Final = (
    "AgentViewer takes a set of departments because a person can sit in two, and the "
    "principal on a request carries one. Nothing on the request path reads membership, so "
    "the viewer is the caller and their primary department, and a person in a second "
    "department does not see that department's agents here. That is a gap and it fails "
    "narrow: nobody is shown an agent their audience does not cover."
)


# ------------------------------------------------------------------------ the bounds

#: The most agents one roster answer carries. A resource bound and not a permission one: it
#: is applied after the audience filter, so raising it discloses nothing, and an installation
#: with more agents than this is told so by `truncated`.
MAX_ROSTER_ENTRIES: Final = 500

#: The one tab whose content this route holds. See `ONLY_WHAT_THIS_ROUTE_HOLDS_IS_POPULATED`.
POPULATED_HERE: Final[frozenset[Tab]] = frozenset({Tab.SETTINGS})


# ------------------------------------------------------------------------ the shapes


class RosterEntry(BaseModel):
    """One agent this caller may see. Its id and its name, and nothing about its state.

    The id is the address of its workspace and the name is what a person looks for. No
    owner, no summary and no lifecycle word: each is a separate disclosure decision, and the
    roster's job is to be a list of doors.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str


class RosterPage(Page[RosterEntry]):
    """Every agent this caller's audience covers, by name.

    `total` is inherited and never populated, and `next_cursor` is always null: the page is
    bounded by `MAX_ROSTER_ENTRIES` rather than paged. See
    `A_ROSTER_IS_FILTERED_BEFORE_IT_IS_BOUNDED`.
    """

    #: There are more agents this caller may see than this answer carries. Never how many.
    truncated: bool = False


class AgentHeaderView(BaseModel):
    """Who an agent is, under the wire names `console/src/pages/agentQuery.ts` reads.

    `owner_id` is `AgentAudience.owner_id`, the current steward, and never `created_by`:
    `brain.agents.model` says the steward is who answers for an agent now, "the question
    everybody else asks", and everybody here is somebody the audience already covers.

    The summary and the lineage come from the install and are null when the agent has none
    that constructs. Both halves of the lineage are set together or neither is.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str
    owner_id: str
    summary: str | None = None
    template_id: str | None = None
    template_version: int | None = None


class TabView(BaseModel):
    """One tab of the strip: its key, its label and its purpose sentence.

    Deliberately not `WorkspaceTab` serialised whole. That type carries `read`, which names
    the capability each tab requires, and the list of grants a screen needs is a permission
    map handed to whoever is looking.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tab: str
    label: str
    purpose: str


class CompositionRowView(BaseModel):
    """One composition path, the template's value beside this agent's.

    Exactly `CompositionRow.wire()`, so the names are that type's rather than a second copy.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    part: str
    path: str
    template: str
    instance: str
    source: str


class WorkspaceView(BaseModel):
    """One agent's workspace, as this caller may read it. Three fields and none a count."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent: AgentHeaderView
    tabs: list[TabView]
    composition: list[CompositionRowView]


# ------------------------------------------------------------------ rows to records


def record_of(row: AgentRow) -> AgentRecord | None:
    """The stored agent as the domain type, or None when it does not construct.

    Every validator in `brain.agents.model` runs, including the tool ceiling's, because the
    audience cannot be trusted off a row the record refuses. See
    `A_ROW_THAT_DOES_NOT_CONSTRUCT_IS_ABSENT_FOR_EVERYBODY`.
    """
    try:
        return AgentRecord(
            agent_id=row.id,
            display_name=row.display_name,
            persona=row.persona,
            tier=Tier(row.tier),
            audience=AgentAudience(
                level=Visibility(row.visibility),
                owner_id=row.owner_id,
                department=row.department or "",
            ),
            authority=AgentAuthority(
                scope=Scope.model_validate(row.scope),
                capabilities=tuple(Capability(value=one) for one in row.capabilities),
                allowed_tools=frozenset(row.allowed_tools),
                required_tools=frozenset(row.required_tools),
                max_side_effect=SideEffect(row.max_side_effect),
            ),
            created_by=row.created_by,
            disabled_at=row.disabled_at,
            archived_at=row.archived_at,
        )
    except ValueError as exc:
        # `ValidationError` is a `ValueError`, and so is an enum given a word it does not
        # hold and the ceiling's own refusal of a required tool outside the allowed set.
        log.warning("agent row does not construct", agent=row.id, error=type(exc).__name__)
        return None


def manifest_of(document: Mapping[str, Any]) -> TemplateManifest:
    """A manifest from the flat document `TemplateManifest.document()` produced.

    The inverse of that method, walking the same `MANIFEST_PATHS` it walks, so a path is read
    back into exactly the section it was taken out of. Nothing here checks the round trip,
    because `SignedManifest` does: it recomputes the digest from the rebuilt body and refuses
    a mismatch, so a reconstruction that lost or moved a value cannot be signed-for.
    """
    nested: dict[str, Any] = {}
    for path in MANIFEST_PATHS:
        head, _, tail = path.partition(".")
        if tail:
            nested.setdefault(head, {})[tail] = document[path]
        else:
            nested[head] = document[path]
    return TemplateManifest.model_validate(nested)


@dataclass(frozen=True)
class Install:
    """What an agent was installed from, and the diff between the two."""

    template_id: str
    template_version: int
    summary: str
    composition: tuple[CompositionRowView, ...]


def install_of(
    instance_row: TemplateInstanceRow, version_row: TemplateVersionRow, record: AgentRecord
) -> Install | None:
    """The install behind one agent, or None when it does not construct.

    `materialise` checks the pin, the overlay and the seal, and `SignedManifest` checks the
    body against its digest, so this adds no check of its own. What it adds is the refusal to
    let any of those failures become a status: an install that does not construct is an agent
    with no lineage and no composition, for every reader alike.
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
        rows = composition_rows(signed, effective)
    except (KeyError, ValueError, TemplateError) as exc:
        # Not `WorkspaceError`. `composition_rows` raises it for an agent materialised from a
        # different template or version, and `materialise` has already refused exactly that
        # pin two lines up, so a catch for it here could not fire and no test could reach it.
        log.warning(
            "agent install does not construct", agent=record.agent_id, error=type(exc).__name__
        )
        return None
    return Install(
        template_id=instance.template_id,
        template_version=instance.template_version,
        summary=effective.manifest.identity.summary,
        composition=tuple(CompositionRowView(**row.wire()) for row in rows),
    )


# ------------------------------------------------------------------ the decisions


def viewer_of(asked: Asking) -> AgentViewer:
    """The caller, as an audience question is asked about them.

    See `THE_VIEWER_IS_THEIR_PRIMARY_DEPARTMENT_UNTIL_MEMBERSHIP_IS_READ`.
    """
    department = asked.caller.principal.primary_department
    return AgentViewer(
        principal_id=asked.caller.principal.id,
        departments=frozenset({department}) if department else frozenset(),
    )


def roster(records: Sequence[AgentRecord], viewer: AgentViewer) -> RosterPage:
    """The agents this viewer's audience covers, by name, bounded after filtering.

    Ordered by name and then by id, so two readings of an unchanged table are one list and
    the order says nothing about when an agent was created.
    """
    visible = visible_agent_ids(records, viewer)
    kept = sorted(
        (one for one in records if one.agent_id in visible),
        key=lambda one: (one.display_name, one.agent_id),
    )
    return RosterPage(
        items=[
            RosterEntry(agent_id=one.agent_id, display_name=one.display_name)
            for one in kept[:MAX_ROSTER_ENTRIES]
        ],
        next_cursor=None,
        truncated=len(kept) > MAX_ROSTER_ENTRIES,
    )


def tab_view(one: WorkspaceTab) -> TabView:
    """One tab under the console's names. The label is the key's own word, capitalised."""
    return TabView(tab=one.tab.value, label=one.tab.value.capitalize(), purpose=one.purpose)


def workspace(record: AgentRecord, install: Install | None, asked: Asking) -> WorkspaceView:
    """One visible agent's workspace at this caller's reach.

    Takes a record the audience has already admitted; `agent_workspace` is where that is
    decided, and nothing here could decide it, because nothing here is handed a viewer.
    """
    strip = tab_strip(asked.reach, populated=POPULATED_HERE, now=asked.now)
    may_read_settings = any(one.tab is Tab.SETTINGS for one in strip)
    return WorkspaceView(
        agent=AgentHeaderView(
            agent_id=record.agent_id,
            display_name=record.display_name,
            owner_id=record.audience.owner_id,
            summary=(install.summary or None) if install is not None else None,
            template_id=install.template_id if install is not None else None,
            template_version=install.template_version if install is not None else None,
        ),
        tabs=[tab_view(one) for one in strip],
        composition=list(install.composition) if install is not None and may_read_settings else [],
    )


# ------------------------------------------------------------------------- the wiring


def every_agent() -> Select[tuple[AgentRow]]:
    """Every stored agent. Filtered by audience afterwards, in Python, by the one predicate."""
    return select(AgentRow).order_by(AgentRow.id)


def one_agent(agent_id: str) -> Select[tuple[AgentRow]]:
    """One stored agent by its slug."""
    return select(AgentRow).where(AgentRow.id == agent_id)


def install_for(agent_id: str) -> Select[tuple[TemplateInstanceRow, TemplateVersionRow]]:
    """One agent's install and the version it is pinned to, joined on the pin's pair."""
    return (
        select(TemplateInstanceRow, TemplateVersionRow)
        .join(
            TemplateVersionRow,
            and_(
                TemplateVersionRow.template_id == TemplateInstanceRow.template_id,
                TemplateVersionRow.version == TemplateInstanceRow.template_version,
            ),
        )
        .where(TemplateInstanceRow.id == agent_id)
    )


def _no_agent_here() -> Absent:
    """The one refusal this router makes about an agent.

    Named so that a missing row, a row outside the audience and a row that does not construct
    are one refusal rather than three that agree today. `brain.app.handle_brain_error` sends
    `Absent.public_message`, and the string below reaches a log.
    """
    return Absent("no agent is answerable for this caller")


def _require_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """The session factory, or a process-level fault identical for every caller.

    A `Failed` rather than an `Absent`, for `brain.routing_routes`' reason: an instance with
    no pool is broken rather than empty. It is also the same answer for every caller and
    every slug, so it says nothing about which agents exist.
    """
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


async def _visible_record(session: AsyncSession, agent_id: str, asked: Asking) -> AgentRecord:
    row = (await session.execute(one_agent(agent_id))).scalar_one_or_none()
    record = record_of(row) if row is not None else None
    if record is None or agent_id not in visible_agent_ids((record,), viewer_of(asked)):
        # One refusal for three causes. See `_no_agent_here`.
        log.info("agent not answerable", principal=asked.caller.principal.id)
        raise _no_agent_here()
    return record


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get("/agents", response_model=RosterPage, responses=COMMON_RESPONSES)
async def agents(request: Request, asked: Asked) -> RosterPage:
    """Every agent this caller's audience covers.

    No capability is asked for, and that is the argument of this module rather than an
    omission. See `AUDIENCE_DECIDES_WHO_SEES_AN_AGENT_AND_NOTHING_ELSE_DOES`.
    """
    factory = _require_session_factory(request)
    async with factory() as session:
        rows = (await session.execute(every_agent())).scalars().all()
    records = [record for record in (record_of(row) for row in rows) if record is not None]
    return roster(records, viewer_of(asked))


@router.get(
    "/agents/{agent_id}/workspace", response_model=WorkspaceView, responses=COMMON_RESPONSES
)
async def agent_workspace(request: Request, agent_id: str, asked: Asked) -> WorkspaceView:
    """One agent's workspace, or the answer an agent that does not exist gets.

    The audience is decided before the install is read, so nothing about an agent this
    caller may not see is fetched on their behalf.
    """
    factory = _require_session_factory(request)
    async with factory() as session:
        record = await _visible_record(session, agent_id, asked)
        pair = (await session.execute(install_for(agent_id))).one_or_none()
    install = install_of(pair[0], pair[1], record) if pair is not None else None
    return workspace(record, install, asked)
