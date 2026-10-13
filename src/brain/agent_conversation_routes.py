"""An agent's Conversations section: the reader's own threads it answered in.

`brain.console.agent_conversations` decides what the section lists and why it is the reader's own
threads, and `brain.chat.thread_store.StoredThreads.threads_with_agent` reads them under row-level
security in the reader's own name; this route decides only who may open the section.

**Anybody who may see the agent may open it, and nothing else is asked.** An agent the reader may
not see is the 404 an agent that does not exist gets (`brain.agent_routes._visible_record`); past
that the section lists only the reader's own threads, which are theirs whatever they hold, as
`brain.thread_routes` lists them on Ask with no grant at all. The workspace's Conversations tab is
not this section's gate: it is read under `read:question`, which governs reading other people's
questions, and gating a person's own threads on it would hide their own history from them for no
protective reason. That tab, and `read:question`, stay for anything that would ever show another
person's threads (needs-rupash 121, option B). See `A_PERSONS_OWN_THREADS_NEED_NO_GRANT`.

**Another agent in a thread is named only while the reader may still see it.** The agents that
answered are read from the roster and kept by `brain.agents.model.visible_agent_ids`, the same
audience rule the roster and `/answer` use, so a participant who has left the reader's audience is
absent rather than named.

**The steward and the administrators are also told that other people's conversations happened,
never what was said** (needs-rupash 121, option B). The agent's steward and a holder of the
lifecycle authority over its row are listed, for each other person's use of it, who, when and
whether it answered, declined or failed, from the run record, which holds no question and no
answer; nobody else is told, and a personal agent tells nobody but its owner anything, because what
a personal agent did is its owner's alone. See `oversees` and
`brain.console.agent_conversations.OTHERS_CONVERSATIONS_SAY_THAT_THEY_HAPPENED_AND_NOTHING_THEY_SAID`.

Task ids: M39.8.9, M39.11.1
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.agent_lifecycle_routes import holds
from brain.agent_routes import (
    _require_session_factory,
    _visible_record,
    every_agent,
    record_of,
    steward_names,
    viewer_of,
)
from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY
from brain.agents.model import AgentRecord, visible_agent_ids
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.chat.thread_store import StoredThreads
from brain.console.agent_conversations import AgentConversation, agent_conversations
from brain.knowledge.visibility import Visibility
from brain.ops.agent_run_store import StoredAgentRuns

CONVERSATIONS_PATH: Final = "/agents/{agent_id}/conversations"

#: Why the section asks nothing of the reader but that they may see the agent.
A_PERSONS_OWN_THREADS_NEED_NO_GRANT: Final = (
    "The section lists the reader's own threads and nobody else's, and a person's own history is "
    "theirs to read without a grant, as Ask lists it. read:question governs reading other people's "
    "questions; gating the section on it would hide a person's own conversations from them and "
    "protect nothing, so it stays for anything that would ever show somebody else's threads."
)


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


class OtherConversationView(BaseModel):
    """Another person's use of the agent: who, when and how it ended, and no word of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    person: str
    started_at: datetime
    ended_at: datetime
    #: `answered`, `declined` or `failed`.
    outcome: str


class ConversationsView(BaseModel):
    """The reader's threads with this agent, most recently used first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    items: list[ConversationView]
    #: Whether this reader is told of other people's conversations: the steward and a holder of the
    #: lifecycle authority over the agent. Their own authority, so it tells nothing of others.
    oversees: bool = False
    #: Other people's conversations with the agent, newest first, for a reader who oversees it.
    others: list[OtherConversationView] = []


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


def oversees(record: AgentRecord, asked: Asking) -> bool:
    """Whether this reader is told that other people's conversations happened.

    The steward, and a holder of the lifecycle authority over the agent's row. Never for a personal
    agent: its owner is the one person who used it and sees their own threads above.
    """
    if record.audience.level is Visibility.PERSONAL:
        return False
    return record.audience.owner_id == asked.caller.principal.id or holds(
        AGENT_LIFECYCLE_CAPABILITY, record, asked
    )


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(CONVERSATIONS_PATH, response_model=ConversationsView, responses=COMMON_RESPONSES)
async def agent_conversations_route(
    request: Request, agent_id: str, asked: Asked
) -> ConversationsView:
    """The reader's own threads this agent answered in, with who answered and how (M39.8.9)."""
    factory = _require_session_factory(request)
    async with factory() as session:
        record, _ = await _visible_record(session, agent_id, asked)
        rows = (await session.execute(every_agent())).scalars().all()
    records = [one for one in (record_of(row) for row in rows) if one is not None]
    visible = visible_agent_ids(records, viewer_of(asked))
    names = {one.agent_id: one.display_name for one in records if one.agent_id in visible}
    reader = asked.caller.principal.id
    threads = await StoredThreads(factory).threads_with_agent(reader, agent_id)
    listed = agent_conversations(
        threads, agent_id, principal_id=reader, reader=asked.reach, now=asked.now
    )
    told = oversees(record, asked)
    others: list[OtherConversationView] = []
    if told:
        ran = await StoredAgentRuns(factory).others_of(agent_id, reader_id=reader)
        async with factory() as session:
            who = await steward_names(session, sorted({one.principal_id for one in ran}))
        others = [
            OtherConversationView(
                person=who.get(one.principal_id, one.principal_id),
                started_at=one.started_at,
                ended_at=one.ended_at,
                outcome=one.outcome,
            )
            for one in ran
        ]
    return ConversationsView(
        agent_id=agent_id,
        items=[view_of(one, names) for one in listed],
        oversees=told,
        others=others,
    )
