"""One agent's artifacts, as its page's Artifacts section reads them, fetches them and retires them.

`brain.console.agent_output` decided what an artifact is, who may know one exists, how its window is
chosen, how it is superseded or archived and what its count and storage are shown against, and
`brain.ops.artifact_store` keeps the bytes and the record. The only route over any of it was the
estate-wide Artifacts screen, which lists and never fetches. This is the agent's own section, and
it decides nothing those modules had not.

**The list is the Artifacts tab's read, and everything in it is `visible_artifacts`'s answer.** A
reader without the tab's read is answered as an agent that does not exist, as the Memory section
is. The filters (type, the person it was produced for, a date range) are arguments to
`visible_artifacts` rather than a pass over its result, which is that function's own argument
about disclosure, and the people offered in the filter are the ones the reader already sees.

**A download asks `may_download` of the requester as they are now, and nothing else.** Not the tab
read: the person an artifact was produced for may fetch it without the screen, and an
administrator who holds the screen may not fetch a file whose content they could not have read.
Refused and missing are one 404. See `A_DOWNLOAD_IS_DECIDED_BY_THE_FILE_AND_NOT_BY_THE_SCREEN`.

**Superseding and archiving are the agent's steward's and the person it was produced for, and only
of an artifact the reader may see.** Anybody else shown it is told which two may; an artifact
they may not see is the missing one. Nothing deletes. See
`THE_STEWARD_AND_THE_PERSON_IT_WAS_PRODUCED_FOR_MAY_RETIRE_IT`.

**The latest of a kind for a client is asked at the run's reach**, `E_run(reader, agent)`, because
it is what an agent asks in the middle of a run and its answer goes into what the run reads
(`brain.ops.artifact_store.StoredArtifacts.latest_for`).

**Provenance is narrowed to the reader** by `provenance_for`, over the sources `sources_at` says
this reader may be told of and the documents their own read of the library returns
(`brain.agent_capability_routes.reader_items`). Nothing here counts what it withheld.

Task ids: M39.5.1.5, M39.5.2.1, M39.5.2.2, M39.5.2.3, M39.5.2.4, M39.5.2.5, M39.8.5
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from brain.agent_capability_routes import reader_items
from brain.agent_routes import (
    _no_agent_here,
    _require_session_factory,
    _tool_registry,
    _visible_record,
)
from brain.agents.model import AgentRecord
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking, sources_at
from brain.artifact_routes import KEPT_WITHOUT_A_CLOCK
from brain.attribution import trace_of_request
from brain.console.agent_output import (
    AN_ARTIFACT_MAY_NOT_OUTLIVE_THE_THING_IT_WAS_BUILT_FROM,
    ARTIFACTS_SCREEN,
    Artifact,
    ArtifactError,
    ArtifactKind,
    ArtifactState,
    basis_over,
    may_download,
    may_see,
    provenance_for,
    storage_summary,
    visible_artifacts,
)
from brain.console.reach_view import run_reach
from brain.console.reads import permitted
from brain.console.workspace import Tab, tab
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Degraded
from brain.knowledge.lifecycle_store import names_of
from brain.ops.artifact_store import StoredArtifacts
from brain.ops.retention import horizon_for
from brain.ops.storage import StorageError
from brain.tables.artifact import ARTIFACT_ID_PATTERN
from brain.tables.resolution import ENTITY_ID_CHARS

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why a download is not the tab's read.
A_DOWNLOAD_IS_DECIDED_BY_THE_FILE_AND_NOT_BY_THE_SCREEN: Final = (
    "Whether somebody may fetch an artifact is a question about the file: whether it was "
    "produced for them or a grant covers it, and whether they still hold everything its content "
    "drew on. Holding the screen answers neither, so a download asks may_download alone, and a "
    "refusal and a file that does not exist are one answer."
)

#: Who may supersede or archive one agent's artifact from its page.
THE_STEWARD_AND_THE_PERSON_IT_WAS_PRODUCED_FOR_MAY_RETIRE_IT: Final = (
    "An artifact is superseded or archived by the person who answers for the agent that made it, "
    "or by the person it was produced for, and only when they may see it. Anybody else shown it "
    "is told which two may. Nothing removes it: the row that was sent to somebody stays."
)

#: The sentence a reader shown an artifact they may not retire is told.
RETIRING_AN_ARTIFACT_NEEDS_THE_STEWARD_OR_ITS_PERSON: Final = (
    "Superseding or archiving this artifact needs the agent's steward, or the person it was "
    "produced for."
)

#: What a change the domain refuses is told, in words that name nothing.
THAT_CHANGE_IS_NOT_ONE_THIS_ARTIFACT_CAN_TAKE: Final = (
    "This artifact cannot take that change: it may already be superseded or archived, or the "
    "replacement named is not another artifact of this agent."
)

#: What the section says while this process keeps no record of artifacts.
NOTHING_HERE_RECORDS_THIS_AGENTS_ARTIFACTS: Final = (
    "This process has no database attached, so it cannot read what this agent produced. It is "
    "not that nothing was produced: it is that nothing here could look."
)

#: What a download is told while the object store is not connected or holds another file.
THE_FILE_CANNOT_BE_FETCHED_NOW: Final = (
    "The file cannot be fetched from the object store right now. Nothing about it has changed."
)

# ------------------------------------------------------------------------ the figures
ARTIFACTS_PATH: Final = "/agents/{agent_id}/artifacts"
LATEST_PATH: Final = "/agents/{agent_id}/artifacts/latest"
DOWNLOAD_PATH: Final = "/agents/{agent_id}/artifacts/{artifact_id}/download"
ARCHIVE_PATH: Final = "/agents/{agent_id}/artifacts/{artifact_id}/archive"
SUPERSEDE_PATH: Final = "/agents/{agent_id}/artifacts/{artifact_id}/supersede"

#: What a downloaded file is called: its kind and its id, never a title.
FILE_EXTENSIONS: Final[dict[str, str]] = {
    "text/csv": "csv",
    "application/pdf": "pdf",
    "application/json": "json",
    "image/png": "png",
    "text/plain": "txt",
}

ArtifactId = Annotated[str, Path(min_length=32, max_length=32, pattern=ARTIFACT_ID_PATTERN)]


# ------------------------------------------------------------------------------ the views
class KnowledgeRefView(BaseModel):
    """One document an artifact drew on, that this reader may see."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    title: str


class ProvenanceView(BaseModel):
    """What fed an artifact, narrowed to this reader. No count of what was left out."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sources: list[str]
    knowledge_items: list[KnowledgeRefView]


class AgentArtifactView(BaseModel):
    """One artifact on the agent's page, with what this reader may do with it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    kind: str
    produced_for: str
    produced_for_name: str
    produced_at: datetime
    state: str
    superseded_by: str
    run_id: str
    agent_version: str
    kept_as: str
    kept_until: datetime | None
    kept_because: str
    bytes_stored: int
    client_id: str
    provenance: ProvenanceView
    #: Whether this reader may fetch the file now.
    downloadable: bool
    #: Whether this reader may supersede or archive it here.
    changeable: bool


class PersonView(BaseModel):
    """Somebody an artifact the reader sees was produced for, for the filter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    name: str


class ArtifactSummaryView(BaseModel):
    """Count and storage of what the reader may see, and the soonest a window closes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    basis: str
    count: int
    bytes_stored: int
    oldest_at: datetime | None
    expires_soonest_at: datetime | None


class AgentArtifactsView(BaseModel):
    """The Artifacts section: the list, its summary, the filter's choices and the rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    artifacts: list[AgentArtifactView]
    summary: ArtifactSummaryView | None
    kinds: list[str]
    people: list[PersonView]
    kept_rule: str
    #: Set, with an empty list, when nothing on this process records artifacts.
    unread: str = ""


class SupersedeAsked(BaseModel):
    """The artifact that replaces this one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    by: str = Field(min_length=32, max_length=32, pattern=ARTIFACT_ID_PATTERN)


class ArtifactChangedView(BaseModel):
    """What a change did: the artifact as it reads now."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    state: str
    superseded_by: str


# ------------------------------------------------------------------------- the decisions
def store_of(request: Request) -> StoredArtifacts | None:
    """The artifact store `brain.app` attached, or None on a process with no database."""
    found = getattr(request.app.state, "artifacts", None)
    return found if isinstance(found, StoredArtifacts) else None


def may_read_artifacts_at(reach: EntitlementSet, now: datetime) -> bool:
    """The Artifacts tab's own read, which is what the strip shows the section by."""
    return permitted(tab(Tab.ARTIFACTS).read, reach, now)


def may_read_artifacts(asked: Asking) -> bool:
    """`may_read_artifacts_at` for a signed-in request."""
    return may_read_artifacts_at(asked.reach, asked.now)


def may_retire(one: Artifact, record: AgentRecord, reader_id: str) -> bool:
    """Whether this reader answers for the agent or is the person the artifact was made for."""
    return reader_id in (record.audience.owner_id, one.caller_id)


def kept_words(one: Artifact) -> tuple[datetime | None, str]:
    """When an artifact stops being kept, and the words beside it, as the estate screen says."""
    horizon = horizon_for(one.data_class)
    until = one.expiry()
    if until is None:
        return None, KEPT_WITHOUT_A_CLOCK.get(horizon.lifetime, horizon.lifetime.value)
    return until, f"kept {horizon.days} days from when it was produced"


def item_view(
    one: Artifact,
    *,
    record: AgentRecord,
    asked: Asking,
    names: dict[str, str],
    sources: Sequence[str],
    titles: dict[str, str],
) -> AgentArtifactView:
    """One artifact as this reader is shown it."""
    until, because = kept_words(one)
    shown = provenance_for(one, visible_sources=sources, visible_items=titles)
    reader_id = asked.caller.principal.id
    return AgentArtifactView(
        artifact_id=one.artifact_id,
        kind=one.kind.value,
        produced_for=one.caller_id,
        produced_for_name=names.get(one.caller_id, ""),
        produced_at=one.at,
        state=one.state.value,
        superseded_by=one.superseded_by,
        run_id=one.run_id,
        agent_version=one.agent_version,
        kept_as=one.data_class.value,
        kept_until=until,
        kept_because=because,
        bytes_stored=one.bytes_stored,
        client_id=one.client_id,
        provenance=ProvenanceView(
            sources=list(shown.sources),
            knowledge_items=[
                KnowledgeRefView(item_id=item, title=titles[item]) for item in shown.knowledge_items
            ],
        ),
        downloadable=may_download(one, asked.reach, asked.now),
        changeable=may_retire(one, record, reader_id) and one.state is not ArtifactState.ARCHIVED,
    )


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(ARTIFACTS_PATH, response_model=AgentArtifactsView, responses=COMMON_RESPONSES)
async def agent_artifacts(
    request: Request,
    agent_id: str,
    asked: Asked,
    kind: Annotated[ArtifactKind | None, Query()] = None,
    produced_for: Annotated[str, Query(max_length=128)] = "",
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
) -> AgentArtifactsView:
    """What this agent produced, as this reader may see it, filtered, newest first."""
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        if not may_read_artifacts(asked):
            log.info("agent artifacts not answerable", principal=asked.caller.principal.id)
            raise _no_agent_here()
    kinds = [one.value for one in ArtifactKind]
    store = store_of(request)
    if store is None:
        return AgentArtifactsView(
            agent_id=agent_id,
            artifacts=[],
            summary=None,
            kinds=kinds,
            people=[],
            kept_rule=AN_ARTIFACT_MAY_NOT_OUTLIVE_THE_THING_IT_WAS_BUILT_FROM,
            unread=NOTHING_HERE_RECORDS_THIS_AGENTS_ARTIFACTS,
        )
    entries = await store.of_agent(agent_id)
    every = visible_artifacts(entries, asked.reach, asked.now, agent_id=agent_id)
    shown = visible_artifacts(
        entries,
        asked.reach,
        asked.now,
        agent_id=agent_id,
        kinds=() if kind is None else (kind,),
        caller_id=produced_for,
        since=since,
        until=until,
    )
    summary = storage_summary(
        agent_id,
        entries,
        asked.reach,
        basis=basis_over(ARTIFACTS_SCREEN, asked.reach, asked.now),
        now=asked.now,
    )
    registry = _tool_registry(request)
    sources = () if registry is None else sources_at(registry, asked.reach, asked.now)
    drew_on_items = any(one.provenance.knowledge_items for one in shown)
    titles: dict[str, str] = {}
    if drew_on_items:
        items, _ = await reader_items(factory, asked.reach, asked.now)
        titles = {item.item_id: item.title for item in items}
    async with factory() as session:
        names = await names_of(session, (one.caller_id for one in every))
    return AgentArtifactsView(
        agent_id=agent_id,
        artifacts=[
            item_view(one, record=record, asked=asked, names=names, sources=sources, titles=titles)
            for one in shown
        ],
        summary=ArtifactSummaryView(
            basis=summary.basis.value,
            count=summary.count,
            bytes_stored=summary.bytes_stored,
            oldest_at=summary.oldest_at,
            expires_soonest_at=summary.expires_soonest_at,
        ),
        kinds=kinds,
        people=[
            PersonView(principal_id=who, name=names.get(who, ""))
            for who in sorted({one.caller_id for one in every})
        ],
        kept_rule=AN_ARTIFACT_MAY_NOT_OUTLIVE_THE_THING_IT_WAS_BUILT_FROM,
    )


@router.get(LATEST_PATH, response_model=AgentArtifactView, responses=COMMON_RESPONSES)
async def latest_agent_artifact(
    request: Request,
    agent_id: str,
    asked: Asked,
    kind: Annotated[ArtifactKind, Query()],
    client: Annotated[str, Query(min_length=1, max_length=ENTITY_ID_CHARS)],
) -> AgentArtifactView:
    """The newest current artifact of a kind for a client, at this agent's run reach, or 404."""
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
    store = store_of(request)
    if store is None:
        raise _no_agent_here()
    found = await store.latest_for(client, kind, run_reach(asked.reach, record), asked.now)
    if found is None:
        raise _no_agent_here()
    async with factory() as session:
        names = await names_of(session, (found.caller_id,))
    return item_view(found, record=record, asked=asked, names=names, sources=(), titles={})


async def _visible_artifact(
    request: Request, agent_id: str, artifact_id: str, asked: Asking
) -> tuple[AgentRecord, StoredArtifacts, Artifact]:
    """The agent's artifact, when this reader may know it exists, or the missing agent's 404."""
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
    store = store_of(request)
    kept = None if store is None else await store.one(artifact_id)
    if (
        store is None
        or kept is None
        or kept.artifact.agent_id != agent_id
        or not may_see(kept.artifact, asked.reach, asked.now)
    ):
        log.info("agent artifact not answerable", principal=asked.caller.principal.id)
        raise _no_agent_here()
    return record, store, kept.artifact


@router.get(DOWNLOAD_PATH, responses=COMMON_RESPONSES, response_class=Response)
async def download_agent_artifact(
    request: Request, agent_id: str, artifact_id: ArtifactId, asked: Asked
) -> Response:
    """The file, when `may_download` admits this requester now. See the reason on downloads."""
    factory = _require_session_factory(request)
    async with factory() as session:
        await _visible_record(session, agent_id, asked)
    store = store_of(request)
    kept = None if store is None else await store.one(artifact_id)
    if (
        store is None
        or kept is None
        or kept.artifact.agent_id != agent_id
        or not may_download(kept.artifact, asked.reach, asked.now)
    ):
        log.info("agent artifact download not answerable", principal=asked.caller.principal.id)
        raise _no_agent_here()
    try:
        body = await store.bytes_of(kept)
    except StorageError as exc:
        raise Degraded(str(exc), public_message=THE_FILE_CANNOT_BE_FETCHED_NOW) from exc
    extension = FILE_EXTENSIONS.get(kept.content_type.split(";")[0].strip(), "bin")
    name = f"{kept.artifact.kind.value}-{kept.artifact.artifact_id}.{extension}"
    return Response(
        content=body,
        media_type=kept.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )


def _refused() -> JSONResponse:
    return JSONResponse(
        status_code=403, content={"message": RETIRING_AN_ARTIFACT_NEEDS_THE_STEWARD_OR_ITS_PERSON}
    )


def _not_that_change() -> JSONResponse:
    return JSONResponse(
        status_code=409, content={"message": THAT_CHANGE_IS_NOT_ONE_THIS_ARTIFACT_CAN_TAKE}
    )


def _changed(one: Artifact) -> ArtifactChangedView:
    return ArtifactChangedView(
        artifact_id=one.artifact_id, state=one.state.value, superseded_by=one.superseded_by
    )


@router.post(ARCHIVE_PATH, response_model=ArtifactChangedView, responses=COMMON_RESPONSES)
async def archive_agent_artifact(
    request: Request, agent_id: str, artifact_id: ArtifactId, asked: Asked
) -> JSONResponse | ArtifactChangedView:
    """Archive one artifact: a row saying so, and the artifact kept. See the reason on retiring."""
    record, store, one = await _visible_artifact(request, agent_id, artifact_id, asked)
    if not may_retire(one, record, asked.caller.principal.id):
        return _refused()
    try:
        changed = await store.change(
            artifact_id,
            to=ArtifactState.ARCHIVED,
            by=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=trace_of_request(),
        )
    except ArtifactError:
        return _not_that_change()
    return _changed(changed)


@router.post(SUPERSEDE_PATH, response_model=ArtifactChangedView, responses=COMMON_RESPONSES)
async def supersede_agent_artifact(
    request: Request,
    agent_id: str,
    artifact_id: ArtifactId,
    body: SupersedeAsked,
    asked: Asked,
) -> JSONResponse | ArtifactChangedView:
    """Mark one artifact replaced by a newer one the reader may also see."""
    record, store, one = await _visible_artifact(request, agent_id, artifact_id, asked)
    if not may_retire(one, record, asked.caller.principal.id):
        return _refused()
    successor = await store.one(body.by)
    if successor is None or not may_see(successor.artifact, asked.reach, asked.now):
        return _not_that_change()
    try:
        changed = await store.change(
            artifact_id,
            to=ArtifactState.SUPERSEDED,
            superseded_by=body.by,
            by=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=trace_of_request(),
        )
    except ArtifactError:
        return _not_that_change()
    return _changed(changed)
