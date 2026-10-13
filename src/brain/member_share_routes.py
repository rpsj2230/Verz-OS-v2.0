"""Handing an artifact to a colleague, and opening what was handed to you.

Five routes for the person asking, none taking a parameter that names whose page it is, each
gated on the member grant (`brain.member.shell`): **share** one artifact an agent made for you
with one colleague, **withdraw** it, **list what you have shared**, **list what was shared with
you**, and **open** it. `brain.member_library` decided all of it and had no caller.

**Sharing hands over what somebody has and grants nothing.** `share` asks `may_download` of the
sharer and then of the colleague, as the colleague's own grants stand now, and refuses in words when
either is no; `open_share` asks it again of the colleague at every read, so a colleague whose reach
narrowed after the share is shown nothing, and the row is never an input to the verdict. The
colleague's grants are read in a session of their own, because reading them tells the transaction
whose grants are being resolved, and the write that follows is the sharer's.

**A share nobody may open is not listed.** What shared-with-you shows is the shares whose verdict is
yes this moment; one that is no is absent, as an artifact that aged out is, so the list says nothing
about what the person is no longer admitted to. An unknown colleague and one with no access are the
one refusal.

**Opening is a read written down.** The file is fetched with `record_artifact_download` before it is
handed over, exactly as the agent's own artifact page does, so a shared file is no quieter than one
taken from where it was made.

Task ids: M40.3.3.3
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from brain.agent_artifact_routes import (
    FILE_EXTENSIONS,
    THE_FILE_CANNOT_BE_FETCHED_NOW,
    store_of,
)
from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, RequestProblemView
from brain.api_routes import Asked
from brain.artifact_routes import ArtifactView, artifact_source_of, artifact_view
from brain.attribution import trace_of_request
from brain.console.reads import permitted
from brain.core.errors import Absent, Degraded, Failed
from brain.knowledge_lifecycle_routes import entitlement_of
from brain.member.shell import member_screen
from brain.member_library import LibraryError, Share, open_share, produced_for_me, share
from brain.mine_routes import MEMBER_HOME
from brain.ops.member_share_store import StoredShares
from brain.ops.sensitive_read_store import record_artifact_download
from brain.ops.storage import StorageError
from brain.routing_routes import sessions_of
from brain.tables.artifact import ARTIFACT_ID_PATTERN

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["member"])

#: How many shares one answer carries. Past it the answer says there are more, never how many.
MOST_SHARES: Final = 100

SHARE_RESPONSES: Final = {
    **COMMON_RESPONSES,
    422: {"model": ErrorBody, "description": "That cannot be shared, and why, in words."},
}

ArtifactId = Annotated[str, Path(pattern=ARTIFACT_ID_PATTERN, max_length=128)]


def _not_answerable() -> Absent:
    return Absent("your shared artifacts are not answerable for this caller")


def _guard(asked: Asked) -> None:
    if not permitted(member_screen(MEMBER_HOME).read, asked.reach, asked.now):
        log.info("own shares not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()


def _shares(request: Request) -> StoredShares:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredShares(factory)


class ShareAsked(BaseModel):
    """Which colleague, by their person id. One, and never a list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    colleague: str = Field(min_length=1, max_length=128, pattern=r"^\S+$")


class ShareView(BaseModel):
    """One artifact this person handed to one colleague."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    shared_with: str
    shared_at: datetime


class SharesView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    shares: list[ShareView]
    more: bool = False


class SharedWithMeView(BaseModel):
    """One artifact a colleague handed to this person that they may open now."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact: ArtifactView
    shared_by: str
    shared_at: datetime


class SharedWithMePage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[SharedWithMeView]
    more: bool = False


class Unshared(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str


def _refused(message: str) -> JSONResponse:
    told = ErrorBody(
        message=message,
        problems=[RequestProblemView(field="colleague", code="not_shareable", message=message)],
    )
    return JSONResponse(status_code=422, content=told.model_dump(mode="json"))


def _view(one: Share) -> ShareView:
    return ShareView(artifact_id=one.artifact_id, shared_with=one.shared_with, shared_at=one.at)


@router.post(
    "/me/artifacts/{artifact_id}/share", response_model=ShareView, responses=SHARE_RESPONSES
)
async def share_my_artifact(
    request: Request, artifact_id: ArtifactId, body: ShareAsked, asked: Asked
) -> ShareView | JSONResponse:
    """Hand one artifact made for this person to one colleague who already reaches it."""
    _guard(asked)
    me = asked.caller.principal.id
    source = artifact_source_of(request)
    factory = sessions_of(request)
    if source is None or factory is None:
        raise _not_answerable()
    mine = produced_for_me(
        tuple(await source()), principal_id=me, reader=asked.reach, now=asked.now
    )
    found = next((one for one in mine if one.artifact_id == artifact_id), None)
    if found is None:
        log.info("own share not answerable", principal=me)
        raise _not_answerable()
    # The colleague's grants are read in a session of their own: reading them names them to the
    # transaction, and the write below is the sharer's.
    async with factory() as session:
        theirs = await entitlement_of(session, body.colleague, asked.now)
    try:
        made = share(found, sharer=asked.reach, colleague=theirs, now=asked.now)
    except LibraryError:
        return _refused("That colleague cannot open this, so it cannot be shared with them.")
    await _shares(request).record(made)
    log.info("own artifact shared", principal=me)
    return _view(made)


@router.post(
    "/me/artifacts/{artifact_id}/unshare", response_model=Unshared, responses=COMMON_RESPONSES
)
async def withdraw_my_share(
    request: Request, artifact_id: ArtifactId, body: ShareAsked, asked: Asked
) -> Unshared:
    """Take a share back. A share that was not there is the one refusal."""
    _guard(asked)
    taken = await _shares(request).withdraw(
        artifact_id, shared_by=asked.caller.principal.id, shared_with=body.colleague
    )
    if not taken:
        raise _not_answerable()
    return Unshared(artifact_id=artifact_id)


@router.get("/me/shares", response_model=SharesView, responses=COMMON_RESPONSES)
async def my_shares(request: Request, asked: Asked) -> SharesView:
    """What this person has handed to colleagues."""
    _guard(asked)
    sent = await _shares(request).sent_by(asked.caller.principal.id)
    return SharesView(
        shares=[_view(one) for one in sent[:MOST_SHARES]], more=len(sent) > MOST_SHARES
    )


@router.get("/me/shared", response_model=SharedWithMePage, responses=COMMON_RESPONSES)
async def shared_with_me(request: Request, asked: Asked) -> SharedWithMePage:
    """What colleagues handed this person that they may open now (M40.3.3.3)."""
    _guard(asked)
    source = artifact_source_of(request)
    if source is None:
        return SharedWithMePage(items=[])
    received = await _shares(request).received_by(asked.caller.principal.id)
    by_id = {one.artifact_id: one for one in await source()}
    items: list[SharedWithMeView] = []
    for one in received:
        artifact = by_id.get(one.artifact_id)
        if artifact is not None and open_share(one, artifact, recipient=asked.reach, now=asked.now):
            items.append(
                SharedWithMeView(
                    artifact=artifact_view(artifact), shared_by=one.shared_by, shared_at=one.at
                )
            )
    return SharedWithMePage(items=items[:MOST_SHARES], more=len(items) > MOST_SHARES)


@router.get(
    "/me/shared/{artifact_id}/download", responses=COMMON_RESPONSES, response_class=Response
)
async def open_shared_artifact(request: Request, artifact_id: ArtifactId, asked: Asked) -> Response:
    """The file, when the share is out to this person and they may open it now."""
    _guard(asked)
    me = asked.caller.principal.id
    store = store_of(request)
    factory = sessions_of(request)
    kept = None if store is None else await store.one(artifact_id)
    received = [
        one for one in await _shares(request).received_by(me) if one.artifact_id == artifact_id
    ]
    if (
        store is None
        or factory is None
        or kept is None
        or not received
        or not open_share(received[0], kept.artifact, recipient=asked.reach, now=asked.now)
    ):
        log.info("shared artifact not answerable", principal=me)
        raise _not_answerable()
    try:
        body = await store.bytes_of(kept)
    except StorageError as exc:
        raise Degraded(str(exc), public_message=THE_FILE_CANNOT_BE_FETCHED_NOW) from exc
    await record_artifact_download(
        factory,
        reader_id=me,
        artifact_id=kept.artifact.artifact_id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
    )
    extension = FILE_EXTENSIONS.get(kept.content_type.split(";")[0].strip(), "bin")
    name = f"{kept.artifact.kind.value}-{artifact_id}.{extension}"
    return Response(
        content=body,
        media_type=kept.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )
