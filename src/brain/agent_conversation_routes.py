"""An agent's Conversations section: the reader's own threads it answered in.

`brain.console.agent_conversations` decides what the section lists and why it is the reader's own
threads, and `brain.chat.thread_store.StoredThreads.threads_with_agent` reads them under row-level
security in the reader's own name; this route decides only who may open the section.

**The agent first, then the tab.** An agent the reader may not see is the 404 an agent that does not
exist gets (`brain.agent_routes._visible_record`), and a reader the Conversations tab is not open
to gets the same answer, because the tab strip already treats a tab the reader may not read and a
tab with nothing in it as one absence (`brain.console.workspace.tab_strip`). The tab's own read is
the rule, so this route adds none.

**Another agent in a thread is named only while the reader may still see it.** The agents that
answered are read from the roster and kept by `brain.agents.model.visible_agent_ids`, the same
audience rule the roster and `/answer` use, so a participant who has left the reader's audience is
absent rather than named.

Task ids: M39.8.9
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.agent_routes import (
    _no_agent_here,
    _require_session_factory,
    _visible_record,
    every_agent,
    record_of,
    viewer_of,
)
from brain.agents.model import visible_agent_ids
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.chat.thread_store import StoredThreads
from brain.console.agent_conversations import AgentConversation, agent_conversations
from brain.console.reads import permitted
from brain.console.workspace import Tab, tab

CONVERSATIONS_PATH: Final = "/agents/{agent_id}/conversations"


def may_read_conversations(asked: Asking) -> bool:
    """Whether the Conversations tab is open to this reader. The tab's own read, and no other."""
    return permitted(tab(Tab.CONVERSATIONS).read, asked.reach, asked.now)


class ParticipantView(BaseModel):
    """One agent that answered in the thread, by the name the reader knows it by."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str


class ConversationView(BaseModel):
    """One of the reader's threads with this agent, as the section lists it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    thread_id: str
    #: The reader's first question in the thread.
    title: str
    last_at: datetime
    last_channel: str
    #: The agents that answered, this one first. The reader is the other participant.
    agents: list[ParticipantView]
    #: How this agent's latest run in the thread ended, or None when it was not recorded.
    state: str | None


class ConversationsView(BaseModel):
    """The reader's threads with this agent, most recently used first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    items: list[ConversationView]


def view_of(one: AgentConversation, names: dict[str, str]) -> ConversationView:
    return ConversationView(
        thread_id=one.thread_id,
        title=one.title,
        last_at=one.last_at,
        last_channel=one.last_channel.value,
        agents=[
            ParticipantView(agent_id=agent, display_name=names[agent])
            for agent in one.agents
            if agent in names
        ],
        state=None if one.state is None else one.state.value,
    )


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(CONVERSATIONS_PATH, response_model=ConversationsView, responses=COMMON_RESPONSES)
async def agent_conversations_route(
    request: Request, agent_id: str, asked: Asked
) -> ConversationsView:
    """The reader's own threads this agent answered in, with who answered and how (M39.8.9)."""
    factory = _require_session_factory(request)
    async with factory() as session:
        await _visible_record(session, agent_id, asked)
        if not may_read_conversations(asked):
            raise _no_agent_here()
        rows = (await session.execute(every_agent())).scalars().all()
    records = [one for one in (record_of(row) for row in rows) if one is not None]
    visible = visible_agent_ids(records, viewer_of(asked))
    names = {one.agent_id: one.display_name for one in records if one.agent_id in visible}
    reader = asked.caller.principal.id
    threads = await StoredThreads(factory).threads_with_agent(reader, agent_id)
    listed = agent_conversations(
        threads, agent_id, principal_id=reader, reader=asked.reach, now=asked.now
    )
    return ConversationsView(agent_id=agent_id, items=[view_of(one, names) for one in listed])
