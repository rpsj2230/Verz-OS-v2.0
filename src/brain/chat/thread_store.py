"""Where a person's threads are kept, and the one place a question and its answer are written down.

`brain.tables.chat` made the storage decision and `brain.chat.threads` and
`brain.member_activity` made every reading decision: what a thread is, what may be shown again and
at whose reach, what a follow-up may draw on. Nothing wrote a row, so no install had a history and
every one of those decisions ran over nothing. This module is the writer and the loader, and it
decides nothing the other two already decide.

**A thread is written where the question was answered, by whoever answered it.** The answer route
and every chat channel answer through `brain.api_routes.answered_for`, and each calls `remember`
with what it answered, so a question asked in Lark and one asked on Ask land in the same tables
with the channel on the message. See
`brain.chat.threads.A_THREAD_IS_THE_PERSONS_AND_THE_CHANNEL_IS_WHERE_ONE_MESSAGE_WAS_TYPED`.

**A chat conversation is a thread by its own name, with no column to hold the name.** A web
question continues a thread by its id, which the page holds. A chat message cannot carry one, so a
chat channel's thread id is derived from the channel, the person and the vendor's conversation, as
a name-based UUID: the same person in the same chat continues the same thread, two people in one
room never share one, and the web can continue a thread begun in a chat because it is listed with
the rest. Rejected: stitching threads together by person and time, which `brain.tables.chat` calls
a join that guesses. See `A_CHAT_S_THREAD_IS_NAMED_BY_ITS_CONVERSATION`.

**An id nobody here owns starts a new thread rather than saying so.** Row-level security shows a
person their own conversations only, so an id that is somebody else's, retired or invented reads
as absent, and the answer is recorded under a fresh thread. A refusal naming the id would tell
whoever typed it that it exists. See `AN_ID_THAT_IS_NOT_YOURS_STARTS_A_NEW_THREAD`.

**A referred question is written nowhere.** A question the sensitive-topic interception routed to
a named person is recorded by that path without its words (M24.2.2), and a transcript row here
would be the copy it exists not to keep.

**An answer whose references were not recorded is kept unreadable.** A cached answer carries its
words and not what they drew on, and an answer stored with an empty reference list would be shown
again after any grant behind it was revoked. So it is stored with a reference list
`brain.chat.threads.refs_from_json` refuses, which shows the question and never the answer again,
failing closed. See `AN_ANSWER_WHOSE_SOURCES_ARE_UNKNOWN_IS_NEVER_SHOWN_AGAIN`.

**Search reads the person's own questions and nothing an answer said.** The words of an answer
may be ones the reader no longer reaches, and a search that matched them would say they are still
there. A question is the person's own words, which `brain.chat.threads.may_show` always shows.
See `SEARCH_READS_ONLY_THE_ASKERS_OWN_QUESTIONS`.

**A correction is a note in the thread and a signal, never a fact.** `correct` keeps the kind of
wrong and the answer's references, and `corrections` hands the learning signal one observation per
note. See `A_CORRECTION_IS_A_SIGNAL_AND_NEVER_A_FACT`.

Task ids: M9.1.1, M9.1.2, M9.1.3, M9.2.4
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.channels.adapter import ChannelCapabilities
from brain.chat.threads import Thread, ThreadMessage, as_turns, refs_as_json, refs_from_json
from brain.chat.turns import Correction, CorrectionKind, RecordRef, record_correction
from brain.core.field_policy import Classification
from brain.gate.context import Channel
from brain.memory.signals import Observation, Signal
from brain.tables.chat import TITLE_CHARS, ConversationRow, MessageRole, MessageRow

# ------------------------------------------------------------------ written-down reasons
#: Why a chat channel's thread id is derived rather than stored.
A_CHAT_S_THREAD_IS_NAMED_BY_ITS_CONVERSATION: Final = (
    "A chat message cannot carry a thread id, and chat.conversation has no column for a "
    "vendor's conversation. So a chat's thread id is a name-based UUID of the channel, the "
    "person and the vendor's conversation: one person in one chat continues one thread, two "
    "people in one room never share one, and the web continues it because it is listed with the "
    "person's other threads. Stitching threads by person and time would be a join that guesses."
)

#: Why an id that is not the caller's is answered with a new thread.
AN_ID_THAT_IS_NOT_YOURS_STARTS_A_NEW_THREAD: Final = (
    "Row-level security shows a person their own live conversations only, so an id that is "
    "somebody else's, retired or invented reads alike as absent. The exchange is recorded under "
    "a fresh thread and nothing is said about the id, because a refusal naming it would tell "
    "whoever typed it that it exists."
)

#: Why an answer with unrecorded references is stored so it is never shown again.
AN_ANSWER_WHOSE_SOURCES_ARE_UNKNOWN_IS_NEVER_SHOWN_AGAIN: Final = (
    "An answer served from the cache carries its words and not what they drew on. Stored with "
    "an empty reference list it would be shown again after a grant behind it was revoked, so it "
    "is stored with a list the thread reader refuses, which keeps the question and never shows "
    "the answer again."
)

#: Why the search matches questions and never answers.
SEARCH_READS_ONLY_THE_ASKERS_OWN_QUESTIONS: Final = (
    "An answer's words may be ones the reader no longer reaches, and a search matching them "
    "would say they are still there. A question is the person's own words, always shown back to "
    "them, so the search reads questions and titles, which are questions, and nothing else."
)

#: Why the console is a surface of the highest ceiling here.
THE_CONSOLE_CARRIES_WHAT_ITS_READER_MAY_READ: Final = (
    "The web application renders an answer to the person signed in, at the reach admission "
    "gave the console, and no adapter declares it because nothing is sent through a vendor. A "
    "stored answer is re-checked against that reach before it is shown again, so the surface "
    "itself narrows nothing further and is declared at the highest classification."
)

#: Why a correction keeps a kind and never what the person said the answer should have been.
A_CORRECTION_IS_A_SIGNAL_AND_NEVER_A_FACT: Final = (
    "A person marking an answer wrong is kept as a note in their thread naming the kind of "
    "wrong, with the references the answer drew on so somebody can look at the same records, "
    "and read by the learning signal as a contradiction. Nothing the person says the right "
    "answer is gets kept, because a chat box that could write facts would be a write path into "
    "the company's knowledge with no review, no scope and no provenance."
)

# ------------------------------------------------------------------------ the figures
#: The namespace a chat conversation's thread id is named in. A fixed product constant, the same
#: on every install, so a person's chat thread keeps its id across a restart.
THREAD_NAMESPACE: Final = uuid.UUID("3f1d6c9e-5b4a-4e8f-9a2d-7c6b5e4d3a21")

#: What is stored as the references of an answer whose references were not recorded. Not the
#: shape `refs_from_json` reads, on purpose: see
#: `AN_ANSWER_WHOSE_SOURCES_ARE_UNKNOWN_IS_NEVER_SHOWN_AGAIN`.
UNREADABLE_REFS: Final[tuple[Mapping[str, str], ...]] = ({"unrecorded": "references"},)

#: How far apart the question and its answer are stamped, so they read back in order.
ANSWER_AFTER_QUESTION: Final = timedelta(microseconds=1)

#: The messages a search reads: the person's own questions, and nothing an answer said. See
#: `SEARCH_READS_ONLY_THE_ASKERS_OWN_QUESTIONS`.
SEARCHED_ROLES: Final[tuple[str, ...]] = (MessageRole.USER.value,)

#: What a correction's note begins with, followed by its kind's word.
CORRECTION_PREFIX: Final = "correction:"

#: The most threads a list or a search returns, and the most words a search takes.
MOST_THREADS: Final = 50
MOST_SEARCH_WORDS: Final = 8

#: The console as a surface a stored answer is shown on. See
#: `THE_CONSOLE_CARRIES_WHAT_ITS_READER_MAY_READ`.
CONSOLE_SURFACE: Final = ChannelCapabilities(
    channel=Channel.CONSOLE,
    max_classification=Classification.RESTRICTED,
    can_carry_label=True,
)

_SET_PRINCIPAL: Final = sa.text("SELECT set_config('app.principal_id', :principal, true)")


def chat_thread_id(channel: Channel, principal_id: str, conversation: str) -> str:
    """The thread one person's messages in one chat conversation continue. See the constant."""
    return str(uuid.uuid5(THREAD_NAMESPACE, f"{channel.value}|{principal_id}|{conversation}"))


def parsed_thread_id(value: str | None) -> uuid.UUID | None:
    """A thread id as the tables hold it, or None for anything that is not one."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class Exchange:
    """One question and what it was answered with, as a person saw them.

    `refs` is what the answer drew on, or None when that was not recorded, which is stored so the
    answer is never shown again; see `AN_ANSWER_WHOSE_SOURCES_ARE_UNKNOWN_IS_NEVER_SHOWN_AGAIN`.
    """

    question: str
    answer: str
    refs: tuple[RecordRef, ...] | None


def _title(question: str) -> str:
    """A thread's title: its first question, on one line, cut to the column."""
    one_line = " ".join(question.split())
    return one_line[:TITLE_CHARS]


class StoredThreads:
    """`chat.conversation` and `chat.message`, as the application role, one person at a time.

    Every statement runs after `app.principal_id` names the person, in the same transaction, so
    the row-level security `0005` and `0045` put on both tables decides what exists.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(
        self,
        principal_id: str,
        *,
        thread_id: str | None,
        channel: Channel,
        exchange: Exchange,
        now: datetime,
    ) -> str:
        """Write one exchange to the named thread when it is this person's, or to a new one.

        The id the exchange was written under, which is the one to continue with. See
        `AN_ID_THAT_IS_NOT_YOURS_STARTS_A_NEW_THREAD`.
        """
        wanted = parsed_thread_id(thread_id)
        async with self._sessions() as session, session.begin():
            await session.execute(_SET_PRINCIPAL, {"principal": principal_id})
            held = await self._own(session, wanted)
            if held is None:
                held = await self._opened(session, principal_id, wanted, exchange.question)
            refs = list(UNREADABLE_REFS) if exchange.refs is None else refs_as_json(exchange.refs)
            await session.execute(
                sa.insert(MessageRow),
                [
                    {
                        "conversation_id": held,
                        "role": MessageRole.USER.value,
                        "channel": channel.value,
                        "body": exchange.question,
                        "refs": [],
                        "created_at": now,
                    },
                    {
                        "conversation_id": held,
                        "role": MessageRole.ASSISTANT.value,
                        "channel": channel.value,
                        "body": exchange.answer,
                        "refs": refs,
                        "created_at": now + ANSWER_AFTER_QUESTION,
                    },
                ],
            )
        return str(held)

    async def _own(self, session: AsyncSession, wanted: uuid.UUID | None) -> uuid.UUID | None:
        if wanted is None:
            return None
        found = await session.execute(
            sa.select(ConversationRow.id).where(ConversationRow.id == wanted)
        )
        return found.scalar_one_or_none()

    async def _opened(
        self, session: AsyncSession, principal_id: str, wanted: uuid.UUID | None, question: str
    ) -> uuid.UUID:
        """A new conversation, under the id asked for when nobody holds it, else a fresh one."""
        for candidate in (wanted, uuid.uuid4()):
            if candidate is None:
                continue
            made = await session.execute(
                pg_insert(ConversationRow)
                .values(id=candidate, principal_id=principal_id, title=_title(question))
                .on_conflict_do_nothing(index_elements=[ConversationRow.id])
                .returning(ConversationRow.id)
            )
            opened = made.scalar_one_or_none()
            if opened is not None:
                return opened
        msg = "a fresh thread id was already taken, which a random UUID does not do"
        raise RuntimeError(msg)

    async def correct(
        self, principal_id: str, thread_id: str, kind: CorrectionKind, *, now: datetime
    ) -> Correction | None:
        """Mark the latest answer in one of this person's threads as wrong (M9.2.4).

        None for a thread that is not theirs, does not exist or holds no answer, alike. The
        correction is `brain.chat.turns.record_correction`'s, which takes the answer's instant,
        agent and references off the answer itself, and it is kept as a system note in the
        thread naming its kind and nothing the person said about it. See
        `A_CORRECTION_IS_A_SIGNAL_AND_NEVER_A_FACT`.
        """
        found = await self.thread(principal_id, thread_id)
        if found is None:
            return None
        try:
            correction = record_correction(as_turns(found), kind, principal_id=principal_id, at=now)
        except ValueError:
            return None
        wanted = parsed_thread_id(found.thread_id)
        async with self._sessions() as session, session.begin():
            await session.execute(_SET_PRINCIPAL, {"principal": principal_id})
            await session.execute(
                sa.insert(MessageRow).values(
                    conversation_id=wanted,
                    role=MessageRole.SYSTEM.value,
                    channel=Channel.CONSOLE.value,
                    body=f"{CORRECTION_PREFIX}{kind.value}",
                    refs=refs_as_json(correction.refs),
                    created_at=now,
                )
            )
        return correction

    async def corrections(self, principal_id: str) -> tuple[Observation, ...]:
        """This person's corrections, as the learning signal reads them (M9.2.4, M16.2.3).

        One `brain.memory.signals.Observation` per correction, naming the conversation and the
        message and never the words, which is that module's
        `A_SIGNAL_LOG_MUST_NOT_BECOME_A_SECOND_TRANSCRIPT`.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(_SET_PRINCIPAL, {"principal": principal_id})
            rows = (
                await session.execute(
                    sa.select(MessageRow.id, MessageRow.conversation_id, MessageRow.created_at)
                    .join(ConversationRow, ConversationRow.id == MessageRow.conversation_id)
                    .where(
                        ConversationRow.principal_id == principal_id,
                        MessageRow.role == MessageRole.SYSTEM.value,
                        MessageRow.body.startswith(CORRECTION_PREFIX, autoescape=True),
                    )
                    .order_by(MessageRow.created_at, MessageRow.id)
                )
            ).all()
        return tuple(
            Observation(
                signal=Signal.CONTRADICTED,
                conversation_id=str(conversation),
                message_id=str(message),
                principal_id=principal_id,
                at=at,
            )
            for message, conversation, at in rows
        )

    async def threads(self, principal_id: str, *, limit: int = MOST_THREADS) -> tuple[Thread, ...]:
        """This person's most recently used threads, each with its messages in order."""
        async with self._sessions() as session, session.begin():
            await session.execute(_SET_PRINCIPAL, {"principal": principal_id})
            latest = (
                sa.select(
                    MessageRow.conversation_id, sa.func.max(MessageRow.created_at).label("at")
                )
                .group_by(MessageRow.conversation_id)
                .subquery()
            )
            ids = (
                (
                    await session.execute(
                        sa.select(ConversationRow.id)
                        .join(latest, latest.c.conversation_id == ConversationRow.id)
                        .where(ConversationRow.principal_id == principal_id)
                        .order_by(latest.c.at.desc(), ConversationRow.id)
                        .limit(max(1, min(limit, MOST_THREADS)))
                    )
                )
                .scalars()
                .all()
            )
            return await self._loaded(session, principal_id, list(ids))

    async def thread(self, principal_id: str, thread_id: str) -> Thread | None:
        """One of this person's threads, or None for one that is not theirs or does not exist."""
        wanted = parsed_thread_id(thread_id)
        if wanted is None:
            return None
        async with self._sessions() as session, session.begin():
            await session.execute(_SET_PRINCIPAL, {"principal": principal_id})
            found = await self._loaded(session, principal_id, [wanted])
        return found[0] if found else None

    async def search(
        self, principal_id: str, words: str, *, limit: int = MOST_THREADS
    ) -> tuple[Thread, ...]:
        """This person's threads whose title or questions hold every word asked (M9.1.3).

        See `SEARCH_READS_ONLY_THE_ASKERS_OWN_QUESTIONS`. Matched with `strpos` over lowered
        text, so a word is bound as a value and a percent sign in it means a percent sign.
        """
        terms = [one.lower() for one in words.split()][:MOST_SEARCH_WORDS]
        if not terms:
            return ()
        asked = MessageRow.role.in_(SEARCHED_ROLES)
        conditions = [
            sa.or_(
                sa.func.strpos(sa.func.lower(sa.func.coalesce(ConversationRow.title, "")), term)
                > 0,
                sa.exists(
                    sa.select(MessageRow.id).where(
                        MessageRow.conversation_id == ConversationRow.id,
                        asked,
                        sa.func.strpos(sa.func.lower(MessageRow.body), term) > 0,
                    )
                ),
            )
            for term in terms
        ]
        async with self._sessions() as session, session.begin():
            await session.execute(_SET_PRINCIPAL, {"principal": principal_id})
            ids = (
                (
                    await session.execute(
                        sa.select(ConversationRow.id)
                        .where(ConversationRow.principal_id == principal_id, *conditions)
                        .order_by(ConversationRow.created_at.desc(), ConversationRow.id)
                        .limit(max(1, min(limit, MOST_THREADS)))
                    )
                )
                .scalars()
                .all()
            )
            return await self._loaded(session, principal_id, list(ids))

    async def _loaded(
        self, session: AsyncSession, principal_id: str, ids: Sequence[uuid.UUID]
    ) -> tuple[Thread, ...]:
        """The threads named, in the order named, with their messages in the order written."""
        if not ids:
            return ()
        conversations = {
            row.id: row
            for row in (
                await session.execute(
                    sa.select(ConversationRow).where(
                        ConversationRow.id.in_(list(ids)),
                        ConversationRow.principal_id == principal_id,
                    )
                )
            ).scalars()
        }
        messages: dict[uuid.UUID, list[ThreadMessage]] = {one: [] for one in conversations}
        rows = (
            await session.execute(
                sa.select(MessageRow)
                .where(MessageRow.conversation_id.in_(list(conversations)))
                .order_by(MessageRow.conversation_id, MessageRow.created_at, MessageRow.id)
            )
        ).scalars()
        for row in rows:
            messages[row.conversation_id].append(_message_of(row))
        return tuple(
            Thread(
                thread_id=str(one),
                owner_id=conversations[one].principal_id,
                title=conversations[one].title or "",
                messages=tuple(messages[one]),
                retired=conversations[one].deleted_at is not None,
            )
            for one in ids
            if one in conversations
        )


def _message_of(row: MessageRow) -> ThreadMessage:
    """One stored row as the thread reader reads it."""
    try:
        channel = Channel(row.channel)
    except ValueError:
        # A channel this build does not know. The API has no declared surface, so an answer
        # read back as the API's is never shown again, which is the direction to fail in.
        channel = Channel.API
    raw: Any = row.refs
    return ThreadMessage(
        role=MessageRole(row.role),
        at=row.created_at,
        channel=channel,
        body=row.body,
        refs=refs_from_json(raw),
    )


def surfaces() -> Mapping[Channel, ChannelCapabilities]:
    """Every surface's declared capabilities: each adapter's, and the console."""
    from brain.channels.adapter import channel_adapters

    declared = {
        one.channel: one for one in (factory().capabilities() for factory in channel_adapters())
    }
    declared[Channel.CONSOLE] = CONSOLE_SURFACE
    return declared
