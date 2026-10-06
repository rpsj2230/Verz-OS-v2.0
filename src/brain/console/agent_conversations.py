"""An agent's Conversations section: the reader's own threads it answered in, and how each ended.

M39.8.9 asks for the threads the reader may see, filterable to the threads the reader took part
in, each with its participants, relative time, a preview and the run state including failed.

**The threads the reader may see are the reader's own, and that is `brain.chat.thread_store`'s
rule, not this module's.** A thread there has one human: row-level security shows a person their
own conversations only (`AN_ID_THAT_IS_NOT_YOURS_STARTS_A_NEW_THREAD`), a web thread is one
person's, and a chat thread is named for the channel, the person and the vendor's conversation, so
"two people in one room never share one" (`A_CHAT_S_THREAD_IS_NAMED_BY_ITS_CONVERSATION`). Every
thread a reader may see is therefore one they wrote every question in, and "threads the reader took
part in" is exactly the reader's own threads with this agent. The list is the leaf's wording met,
not narrowed, and **it draws no "related to me" filter**, because a filter that can never change
the list is a control that does nothing. Whether owners and administrators should also see that
other people's conversations happened, never their words, is needs-rupash 121; that answer can
only add to this.

**The participants are the reader and the agents that answered in the thread**, this agent first.
Another agent is named only while the reader may still see it, by the route: an agent that has
left the reader's audience since is absent rather than drawn as a name they may no longer find.

**The preview is the thread's own title**, which is the reader's first question
(`brain.chat.thread_store._title`), and nothing an answer said: an answer is shown again only at
the reach held now (`brain.chat.threads`), and a list is not the place to re-check it.

**The run state is this agent's latest answer in the thread**, as `0192` records it: answered,
declined, degraded, or failed. A failed run keeps its question and a turn with nothing in it
(`brain.chat.thread_store.FAILED_RUN_SHOWS_NOTHING`), so a failed row says failed and shows no
model output. An answer written before `0192` has no recorded state and says so rather than
guessing.

**Anybody who may see the agent is listed their own threads with it, and nothing else is asked of
them.** Their own history is theirs without a grant, as Ask lists it; `read:question`, which the
workspace's Conversations tab is read under, governs other people's questions and stays for option
B. See `brain.agent_conversation_routes.A_PERSONS_OWN_THREADS_NEED_NO_GRANT`.

Built on `brain.member_activity.recent_threads`, which decides which of a person's threads are
listed and in what order, so this section and the Ask page's list cannot disagree about that.

Task ids: M39.8.9
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.chat.threads import Thread
from brain.core.entitlement import EntitlementSet
from brain.gate.context import Channel
from brain.member_activity import RECENT_THREADS, recent_threads
from brain.tables.chat import MessageRole, RunState

#: Why the section draws no "took part in" filter. See the module docstring.
EVERY_THREAD_A_READER_SEES_IS_ONE_THEY_TOOK_PART_IN: Final = (
    "A thread has one human, its owner, and a reader sees only their own, so every thread listed "
    "is one the reader wrote every question in. A filter to the threads they took part in would "
    "never change the list, and a control that never changes anything is not drawn."
)


@dataclass(frozen=True)
class AgentConversation:
    """One of the reader's threads an agent answered in, as the section lists it."""

    thread_id: str
    #: The reader's first question in the thread. See the module docstring.
    title: str
    last_at: datetime
    last_channel: Channel
    #: Every agent that answered in the thread, this one first, the rest in the order they
    #: first answered. The reader is the other participant and is not repeated here.
    agents: tuple[str, ...]
    #: How this agent's latest run in the thread ended, or None when it was not recorded.
    state: RunState | None


def answered_by(thread: Thread, agent_id: str) -> bool:
    """Whether this agent gave any answer in the thread."""
    return any(
        one.role is MessageRole.ASSISTANT and one.agent_id == agent_id for one in thread.messages
    )


def agents_in(thread: Thread, agent_id: str) -> tuple[str, ...]:
    """The agents that answered in the thread, this one first and each once."""
    seen: dict[str, None] = {agent_id: None}
    for one in thread.messages:
        if one.role is MessageRole.ASSISTANT and one.agent_id:
            seen.setdefault(one.agent_id, None)
    return tuple(seen)


def latest_state(thread: Thread, agent_id: str) -> RunState | None:
    """How this agent's latest answer in the thread ended, or None when nothing recorded it."""
    answers = [
        one
        for one in thread.messages
        if one.role is MessageRole.ASSISTANT and one.agent_id == agent_id
    ]
    return answers[-1].run_state if answers else None


def agent_conversations(
    threads: Iterable[Thread],
    agent_id: str,
    *,
    principal_id: str,
    reader: EntitlementSet,
    now: datetime,
    limit: int = RECENT_THREADS,
) -> tuple[AgentConversation, ...]:
    """The reader's threads this agent answered in, most recently used first.

    `recent_threads` decides which are listed and in what order: the reader's own, live, not on a
    surface other people read, and nothing for a reader whose principal has expired. This adds
    which agents answered and how this agent's latest run ended.
    """
    mine = {one.thread_id: one for one in threads if answered_by(one, agent_id)}
    listed = recent_threads(
        mine.values(),
        principal_id=principal_id,
        reader=reader,
        audience_is_one_person=True,
        now=now,
        limit=limit,
    )
    return tuple(
        AgentConversation(
            thread_id=one.thread_id,
            title=one.title,
            last_at=one.last_at,
            last_channel=one.last_channel,
            agents=agents_in(mine[one.thread_id], agent_id),
            state=latest_state(mine[one.thread_id], agent_id),
        )
        for one in listed
    )
