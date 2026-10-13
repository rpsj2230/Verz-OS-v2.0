"""One search box over the console, answered by each module's own list route (M27.10.5).

**Each module decides what it shows, and this module asks them and adds nothing.** A global search
that kept an index of its own would be a second copy of what every list route already decides about
who may be told a thing exists, and the copy is the one that leaks: a person, an agent or a source
named in an index the reader's reach never narrowed. So the search is the modules' own reads, called
in process as the reader, each with `ListAsked(search=q)` and a small bound: People's directory, the
agent roster, the template gallery, the skills the reader's agents run, the source list, and the
menu's own pages. What a module would not list to this reader it does not list here.

**No match and not permitted are one answer.** A module that refuses the reader (a reader without
its screen, an agent outside the audience) and a module with nothing that matches both leave no
group at all, so the answer cannot say a module has what the reader may not see. A module that
faults is logged and left out for the same reason: a search that says "People is broken" to somebody
who may not open People has said People exists.

**No count anywhere, and no cursor.** Each group is the first few hits and nothing says how many
more there are, which is the same rule every listing here keeps. The query is bounded below (one
character matches the alphabet) and above.

Rejected: a search index table. It needs a migration, a writer for every module and a second set of
narrowing rules, and it would be right on the day it was written.

Task ids: M27.10.5
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.console.department_console import console_for
from brain.core.errors import BrainError
from brain.listing import ListAsked

log = structlog.get_logger()

#: Where the search is asked.
SEARCH_PATH: Final = "/console/search"

#: The shortest and longest query asked, and the most hits one module shows.
MIN_CHARS: Final = 2
MAX_CHARS: Final = 80
HITS_PER_MODULE: Final = 5


class SearchHitView(BaseModel):
    """One thing a module listed for the query: what to call it, a line under it and where it is."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    sub: str | None = None
    to: str


class SearchGroupView(BaseModel):
    """One module's hits. Present only when there is at least one, so a group says what it has."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    heading: str
    hits: list[SearchHitView]


class SearchResultsView(BaseModel):
    """What the modules listed for a query, in the order the menu keeps. No count and no cursor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    q: str
    groups: list[SearchGroupView]


#: One module the search asks: its key and heading, and how to ask it and read an answer.
Module = tuple[str, str, Callable[[Request, Asking, ListAsked], Awaitable[list[SearchHitView]]]]


async def _people(request: Request, asked: Asking, listed: ListAsked) -> list[SearchHitView]:
    from brain.directory_routes import directory

    page = await directory(request, asked, listed)
    return [
        SearchHitView(
            label=one.display_name, sub=one.department_name, to=f"/people/{one.principal_id}"
        )
        for one in page.items
    ]


async def _agents(request: Request, asked: Asking, listed: ListAsked) -> list[SearchHitView]:
    from brain.agent_routes import agents

    page = await agents(request, asked, listed)
    return [
        SearchHitView(label=one.display_name, sub=one.department, to=f"/agents/{one.agent_id}")
        for one in page.items
    ]


async def _templates(request: Request, asked: Asking, listed: ListAsked) -> list[SearchHitView]:
    from brain.agent_routes import agent_templates

    page = await agent_templates(request, asked, listed)
    return [
        SearchHitView(
            label=one.display_name, sub=one.summary, to=f"/agent-templates/{one.template_id}"
        )
        for one in page.items
    ]


async def _skills(request: Request, asked: Asking, listed: ListAsked) -> list[SearchHitView]:
    from brain.skill_routes import skills

    page = await skills(request, asked, listed)
    return [SearchHitView(label=one.name, to=f"/skills/{one.name}") for one in page.items]


async def _sources(request: Request, asked: Asking, listed: ListAsked) -> list[SearchHitView]:
    from brain.connector_routes import connector_sources

    page = await connector_sources(request, asked, listed)
    return [
        SearchHitView(label=one.label, sub=one.department, to=f"/connectors/{one.name}")
        for one in page.items
    ]


#: The modules the search asks, in the order their groups are listed. Pages come last, below.
MODULES: Final[tuple[Module, ...]] = (
    ("people", "People", _people),
    ("agents", "Agents", _agents),
    ("agent_templates", "Agent templates", _templates),
    ("skills", "Skills", _skills),
    ("connectors", "Connectors", _sources),
)


def pages_matching(asked: Asking, q: str) -> list[SearchHitView]:
    """The menu's own pages whose name has the query in it, for the console this reader is given."""
    wanted = q.casefold()
    found: list[SearchHitView] = []
    for section in console_for(asked.reach, asked.now).sections:
        for entry in section.entries:
            for page in entry.pages:
                if wanted in page.label.casefold() or wanted in entry.label.casefold():
                    found.append(SearchHitView(label=page.label, sub=entry.label, to=page.to))
    return found[:HITS_PER_MODULE]


async def search(request: Request, asked: Asking, q: str) -> SearchResultsView:
    """Every module's hits for `q`, as this reader would be listed them, and nothing else."""
    listed = ListAsked(search=q, limit=HITS_PER_MODULE)
    groups: list[SearchGroupView] = []
    for key, heading, ask in MODULES:
        try:
            hits = await ask(request, asked, listed)
        except BrainError:
            continue
        except Exception as fault:
            log.warning("console search module faulted", module=key, error=type(fault).__name__)
            continue
        if hits:
            groups.append(SearchGroupView(key=key, heading=heading, hits=hits[:HITS_PER_MODULE]))
    pages = pages_matching(asked, q)
    if pages:
        groups.append(SearchGroupView(key="pages", heading="Pages", hits=pages))
    return SearchResultsView(q=q, groups=groups)


router = APIRouter(prefix=API_PREFIX, tags=["console"])


@router.get(SEARCH_PATH, response_model=SearchResultsView, responses=COMMON_RESPONSES)
async def console_search(
    request: Request,
    asked: Asked,
    q: Annotated[str, Query(min_length=MIN_CHARS, max_length=MAX_CHARS)],
) -> SearchResultsView:
    """The modules' own lists, asked for one query as the person asking (M27.10.5)."""
    return await search(request, asked, q.strip())
