"""Where a link to one tab of one agent lands for the person following it, or the one 404.

`brain.console.workspace` has had the address of every tab (`deep_link`) and the answer to "where
does this land for this reader" (`resolve`) since M39.1.2.4 was written, and nothing reached
either: the console built its own addresses and decided its own landing from the workspace's
strip, and no alert carried a link at all. This route is `resolve` on the request path, so
anything that hands a person a link to an agent's tab (the paused-automation notice is the first,
`brain.automation_paused_told`) can be asked about by the same rule the page keeps.

**One answer for every failure, and it is the missing agent's.** `resolve` returns None for a
malformed link, an unknown tab, an agent outside the reader's audience, a tab they hold no grant
for and a tab with nothing in it, and this route answers every None with
`agent_routes._no_agent_here`, the 404 an agent that does not exist gets. A route that said
"forbidden" for one of the five and "not found" for another would turn the address bar into a
question about which agents exist. See
`workspace.A_DEEP_LINK_THAT_REFUSES_DIFFERENTLY_IS_AN_ORACLE`.

**The audience is the agent route's own question, asked of one row.** The link names one agent,
so the route reads that one row and asks `visible_agent_ids` about it, which is the function the
roster and the workspace ask; the tab is `tab_strip`'s, over what this install populates
(`agent_routes.POPULATED_HERE`), so a landing and the strip the page draws cannot disagree.
Rejected: parsing the link here and deciding the tab beside `resolve`, which would be a second
copy of the rule `resolve` exists to hold.

Task ids: M39.1.2.4
"""

from __future__ import annotations

from typing import Final

import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict

from brain.agent_routes import (
    POPULATED_HERE,
    _no_agent_here,
    _require_session_factory,
    one_agent,
    record_of,
    viewer_of,
)
from brain.agents.model import visible_agent_ids
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.console.workspace import DEEP_LINK_PREFIX, deep_link, resolve

log = structlog.get_logger()

#: Where a link is asked about. Its own prefix, so it can never be read as an agent's id.
LANDING_PATH: Final = "/agent-links/landing"

#: The longest link worth reading: the prefix, an agent id, a slash and a tab.
LINK_CHARS: Final = 256


class AgentLandingView(BaseModel):
    """Where a link lands: the agent, the tab and the tab's own address. Nothing about why not."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    tab: str
    address: str


def agent_named_by(link: str) -> str | None:
    """The agent id a well-formed link names, so the one row can be read, or None.

    Decides nothing: whatever this returns, `resolve` is asked about the whole link.
    """
    if not link.startswith(DEEP_LINK_PREFIX):
        return None
    head, _, _ = link[len(DEEP_LINK_PREFIX) :].partition("/")
    return head or None


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(LANDING_PATH, response_model=AgentLandingView, responses=COMMON_RESPONSES)
async def agent_landing(
    request: Request,
    asked: Asked,
    link: str = Query(min_length=1, max_length=LINK_CHARS),
) -> AgentLandingView:
    """Where this link lands for this reader, or the missing agent's 404 (M39.1.2.4)."""
    named = agent_named_by(link)
    visible: frozenset[str] = frozenset()
    if named is not None:
        factory = _require_session_factory(request)
        async with factory() as session:
            row = (await session.execute(one_agent(named))).scalar_one_or_none()
        record = None if row is None else record_of(row)
        if record is not None:
            visible = visible_agent_ids((record,), viewer_of(asked))
    landing = resolve(
        link, asked.reach, visible_agents=visible, populated=POPULATED_HERE, now=asked.now
    )
    if landing is None:
        log.info("agent link not answerable", principal=asked.caller.principal.id)
        raise _no_agent_here()
    return AgentLandingView(
        agent_id=landing.agent_id,
        tab=landing.tab.tab.value,
        address=deep_link(landing.agent_id, landing.tab.tab),
    )
