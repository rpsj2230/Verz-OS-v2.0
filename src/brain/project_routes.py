"""A person's own projects: made, listed, renamed, put away and filled with threads and files.

Seven routes for the person asking, none taking a parameter that names whose projects, each gated on
the member grant (`brain.member.shell`). `agent.project` and `agent.project_item` (`0233`) are read
and written as the person alone, so a project that is not yours is not addressable: asking for it is
the one 404 an unknown project gets.

**The switch gates the door and never traps what it opened.** `personal_projects` ships off. Off, a
project cannot be made and nothing can be added to one, in a sentence; listing, reading, renaming,
putting away and taking something out are never behind it, so a person can always see and tidy what
they made (`brain.ops.features.A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED`).

**Adding is checked at the reach held now, once, and reading is checked again every turn.** A thread
is added only when it is one of the caller's own; a file only when the caller may read it at their
own reach this moment, and either failing is the one 404. That check is a courtesy to the person.
What decides whether a run reads a file is not made here: it is the document reader at the run's
reach, every turn (`brain.project_context`), so a file the person can no longer read stays on the
list, is not read, and nothing says so.

**Putting away is not deleting.** An archived project is no longer listed and stops being read; the
grants give nobody a delete of a project, and the items stay with it.

Task ids: M40.7.7
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Final, Literal

import structlog
from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody
from brain.api_routes import Asked
from brain.chat.remember import threads_of
from brain.console.reads import permitted
from brain.core.errors import Absent, Failed
from brain.knowledge.document_tools import DocumentRead, reader
from brain.knowledge.item import ITEM_ID_PATTERN
from brain.knowledge.row_store import SessionRowSource
from brain.member.shell import member_screen
from brain.member_projects import (
    NAME_NEEDED,
    NOT_AVAILABLE,
    TOO_MANY_ITEMS,
    TOO_MANY_PROJECTS,
    Project,
    ProjectItem,
    clean_name,
)
from brain.mine_routes import MEMBER_HOME
from brain.ops.project_store import ProjectFullError, StoredProjects
from brain.project_context import projects_are_on
from brain.routing_routes import sessions_of

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["member"])

PROJECTS_PATH: Final = "/me/projects"
PROJECT_PATH: Final = "/me/projects/{project_id}"
RENAME_PATH: Final = "/me/projects/{project_id}/rename"
ARCHIVE_PATH: Final = "/me/projects/{project_id}/archive"
ADD_ITEM_PATH: Final = "/me/projects/{project_id}/items"
REMOVE_ITEM_PATH: Final = "/me/projects/{project_id}/items/remove"

#: A project id as the table holds one: a UUID's text.
PROJECT_ID_PATTERN: Final = r"^[0-9a-fA-F-]{36}$"
ProjectId = Annotated[str, Path(pattern=PROJECT_ID_PATTERN)]

PROJECT_RESPONSES: Final = {
    **COMMON_RESPONSES,
    409: {"model": ErrorBody, "description": "That cannot be kept now, and why, in words."},
    422: {"model": ErrorBody, "description": "That cannot be kept, and why, in words."},
}


def _not_answerable() -> Absent:
    return Absent("that project is not answerable for this caller")


def _guard(asked: Asked) -> None:
    if not permitted(member_screen(MEMBER_HOME).read, asked.reach, asked.now):
        log.info("own projects not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()


def _store(request: Request) -> StoredProjects:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredProjects(factory)


def _told(status: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content=ErrorBody(message=message).model_dump(mode="json")
    )


class NameAsked(BaseModel):
    """A project's name, as the person typed it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=400)


class ItemAsked(BaseModel):
    """One thread or one file, by id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["file", "thread"]
    ref: str = Field(min_length=1, max_length=128, pattern=r"^\S+$")


class ProjectView(BaseModel):
    """One project in a list: its id, its name and when it was made. Nothing counted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    name: str
    created_at: datetime


class ProjectsView(BaseModel):
    """This person's active projects, newest first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    projects: list[ProjectView]
    #: Whether making a project and filling one is switched on, so the page can say so.
    switched_on: bool


class ProjectItemView(BaseModel):
    """One thing in a project: its kind, its id and, for one of the person's threads, its title."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    ref: str
    title: str
    added_at: datetime


class ProjectDetailView(BaseModel):
    """One project and everything it lists, including what the person can no longer read."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    name: str
    created_at: datetime
    items: list[ProjectItemView]
    switched_on: bool


class ProjectChanged(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str


def _view(one: Project) -> ProjectView:
    return ProjectView(project_id=one.project_id, name=one.name, created_at=one.created_at)


async def _on(request: Request) -> bool:
    return await projects_are_on(sessions_of(request))


@router.get(PROJECTS_PATH, response_model=ProjectsView, responses=COMMON_RESPONSES)
async def my_projects(request: Request, asked: Asked) -> ProjectsView:
    """The caller's active projects (M40.7.7). Never behind the switch."""
    _guard(asked)
    found = await _store(request).projects(asked.caller.principal.id)
    return ProjectsView(projects=[_view(one) for one in found], switched_on=await _on(request))


@router.post(
    PROJECTS_PATH, status_code=201, response_model=ProjectView, responses=PROJECT_RESPONSES
)
async def make_my_project(
    request: Request, body: NameAsked, asked: Asked
) -> ProjectView | JSONResponse:
    """Make a project of the caller's own, when the switch is on."""
    _guard(asked)
    if not await _on(request):
        return _told(409, NOT_AVAILABLE)
    name = clean_name(body.name)
    if name is None:
        return _told(422, NAME_NEEDED)
    try:
        made = await _store(request).create(asked.caller.principal.id, name)
    except ProjectFullError:
        return _told(422, TOO_MANY_PROJECTS)
    log.info("own project made", principal=asked.caller.principal.id)
    return _view(made)


@router.get(PROJECT_PATH, response_model=ProjectDetailView, responses=COMMON_RESPONSES)
async def my_project(request: Request, project_id: ProjectId, asked: Asked) -> ProjectDetailView:
    """One of the caller's projects with everything it lists, or the one 404. Never switched."""
    _guard(asked)
    me = asked.caller.principal.id
    found = await _store(request).one(me, project_id)
    if found is None or found[0].archived:
        raise _not_answerable()
    project, items = found
    threads = threads_of(request.app.state)
    shown: list[ProjectItemView] = []
    for one in items:
        title = ""
        if one.kind == "thread" and threads is not None:
            held = await threads.thread(me, one.ref)
            title = "" if held is None else held.title
        shown.append(_item(one, title))
    return ProjectDetailView(
        project_id=project.project_id,
        name=project.name,
        created_at=project.created_at,
        items=shown,
        switched_on=await _on(request),
    )


def _item(one: ProjectItem, title: str) -> ProjectItemView:
    return ProjectItemView(kind=one.kind, ref=one.ref, title=title, added_at=one.added_at)


@router.post(RENAME_PATH, response_model=ProjectChanged, responses=PROJECT_RESPONSES)
async def rename_my_project(
    request: Request, project_id: ProjectId, body: NameAsked, asked: Asked
) -> ProjectChanged | JSONResponse:
    """Change a project's name. Never behind the switch."""
    _guard(asked)
    name = clean_name(body.name)
    if name is None:
        return _told(422, NAME_NEEDED)
    if not await _store(request).rename(asked.caller.principal.id, project_id, name):
        raise _not_answerable()
    return ProjectChanged(project_id=project_id)


@router.post(ARCHIVE_PATH, response_model=ProjectChanged, responses=COMMON_RESPONSES)
async def put_my_project_away(
    request: Request, project_id: ProjectId, asked: Asked
) -> ProjectChanged:
    """Put a project away: it is no longer listed and no run reads it. Never behind the switch."""
    _guard(asked)
    if not await _store(request).archive(asked.caller.principal.id, project_id, asked.now):
        raise _not_answerable()
    return ProjectChanged(project_id=project_id)


@router.post(
    ADD_ITEM_PATH, status_code=201, response_model=ProjectChanged, responses=PROJECT_RESPONSES
)
async def add_to_my_project(
    request: Request, project_id: ProjectId, body: ItemAsked, asked: Asked
) -> ProjectChanged | JSONResponse:
    """List one of the caller's threads, or a file they may read, in one of their projects."""
    _guard(asked)
    me = asked.caller.principal.id
    if not await _on(request):
        return _told(409, NOT_AVAILABLE)
    if body.kind == "thread":
        threads = threads_of(request.app.state)
        if threads is None or await threads.thread(me, body.ref) is None:
            raise _not_answerable()
    else:
        sessions = sessions_of(request)
        if sessions is None:
            raise Failed("no database on this process")
        if not _is_item_id(body.ref):
            raise _not_answerable()
        readable = await reader(SessionRowSource(sessions))(
            DocumentRead(document_id=body.ref, limit=1), entitlement=asked.reach, now=asked.now
        )
        if not readable.records:
            raise _not_answerable()
    try:
        kept = await _store(request).add(me, project_id, body.kind, body.ref)
    except ProjectFullError:
        return _told(422, TOO_MANY_ITEMS)
    if not kept:
        raise _not_answerable()
    return ProjectChanged(project_id=project_id)


def _is_item_id(ref: str) -> bool:
    return re.fullmatch(ITEM_ID_PATTERN, ref) is not None


@router.post(REMOVE_ITEM_PATH, response_model=ProjectChanged, responses=COMMON_RESPONSES)
async def take_out_of_my_project(
    request: Request, project_id: ProjectId, body: ItemAsked, asked: Asked
) -> ProjectChanged:
    """Take one thing out of a project. Never behind the switch."""
    _guard(asked)
    if not await _store(request).remove(asked.caller.principal.id, project_id, body.kind, body.ref):
        raise _not_answerable()
    return ProjectChanged(project_id=project_id)
