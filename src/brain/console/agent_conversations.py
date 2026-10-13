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

**The owner and the administrators are also told that other people's conversations happened, never
what was said** (needs-rupash 121, option B, decided 2026-10-13). Each is a person, a time and
whether the agent answered, declined or failed, read from the run record
(`ops.agent_run`: counts and names from closed lists, no question and no answer), and never from a
thread, which only its own person can read. A person's words were answered at that person's reach,
which may be wider than the viewer's, so showing them would be reading through the Brain what the
viewer could not read themselves. See
`OTHERS_CONVERSATIONS_SAY_THAT_THEY_HAPPENED_AND_NOTHING_THEY_SAID`.
Who may be told is the steward and a holder of the lifecycle authority over the agent's row, and a
personal agent has no such reader at all, because what a personal agent did is its owner's alone.

Built on `brain.member_activity.recent_threads`, which decides which of a person's threads are
listed and in what order, so this section and the Ask page's list cannot disagree about that.

Task ids: M39.8.9, M39.11.1
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.chat.threads import Thread
from brain.core.entitlement import EntitlementSet
from brain.gate.context import Channel
from brain.gate.stop import StopReason
from brain.member_activity import RECENT_THREADS, recent_threads
from brain.tables.chat import MessageRole, RunState

#: Why the section draws no "took part in" filter. See the module docstring.
EVERY_THREAD_A_READER_SEES_IS_ONE_THEY_TOOK_PART_IN: Final = (
    "A thread has one human, its owner, and a reader sees only their own, so every thread listed "
    "is one the reader wrote every question in. A filter to the threads they took part in would "
    "never change the list, and a control that never changes anything is not drawn."
)


#: Why another person's conversation is a person, a time and an outcome, and nothing else.
OTHERS_CONVERSATIONS_SAY_THAT_THEY_HAPPENED_AND_NOTHING_THEY_SAID: Final = (
    "The agent's owner and its administrators are told who asked it, when, and whether it "
    "answered, declined or failed. They are never told the question or the answer, because the "
    "answer was built from what the asker may see, which may be more than the viewer may. The "
    "rows are read from the run record, which holds no words, and never from a thread."
)

#: The words a run's outcome is told in, and the only three.
OUTCOME_WORDS: Final = ("answered", "declined", "failed")


@dataclass(frozen=True)
class OtherConversation:
    """Another person's use of this agent: who, when it started and ended, and how it ended."""

    principal_id: str
    started_at: datetime
    ended_at: datetime
    #: One of `OUTCOME_WORDS`.
    outcome: str


def outcome_of(stop_reason: str) -> str:
    """How a run's stop reason reads to a person: it answered, it declined, or it failed.

    Every bound a run can reach and a refusal or a fault is a failure to the person who watches an
    agent for failing; the model declining on content is its own word.
    """
    if stop_reason == StopReason.ANSWERED.value:
        return OUTCOME_WORDS[0]
    if stop_reason == StopReason.DECLINED.value:
        return OUTCOME_WORDS[1]
    return OUTCOME_WORDS[2]


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
