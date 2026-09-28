"""The person's own conversations in PostgreSQL: opened, filed, listed, read back and corrected.

`brain.tables.chat` and `0005` made a conversation the one table here whose row-level security
restricts by person, and nothing read or wrote it: `brain.chat.threads` said so in its own
docstring. This is the store, and it holds no policy. What an exchange is filed as is
`brain.chat.filing`'s; what may be shown again is `brain.chat.threads.may_show`'s; this module
moves rows.

**Every transaction names its person first, and nothing here takes a person from a request
body.** `app.principal_id` is set with `set_config(..., true)`, which lasts for the transaction
and no longer, before any statement touches `chat`, so the policy is what decides whose rows a
statement reaches. Every statement also says `principal_id = :person` itself, which is the index
the listing is served from and a second statement of the rule the policy already enforces, never
a replacement for it. See `A_CONVERSATION_IS_READ_AS_ITS_PERSON`.

**A conversation that is not the person's and one that does not exist are the same None.** The
policy hides the first, so the store cannot tell them apart and a caller cannot either, which is
DENIED and ABSENT indistinguishable arriving from the database rather than being arranged by a
route.

**The search reads what the person typed and nothing an answer said (M9.1.3).** A match on an
answer's words would say what a withheld answer contained: "did any of my conversations say
90,000" answered yes about an answer the reader may no longer see. The title is the first
question, so the title and the person's own questions are the whole of what is searched. See
`A_SEARCH_READS_ONLY_WHAT_THE_PERSON_TYPED`.

**No count leaves here.** A listing is bounded and says whether there was more, never how much
more, for `brain.api_routes.A_TOTAL_IS_A_HIDDEN_ITEM_COUNT`'s reason, even though every row is
the reader's own: the habit is cheaper to keep than to argue about per screen.

**Messages are ordered by the database's clock at the moment each is written.** A question and
its answer are filed in one transaction, and `now()` is the transaction's start, so both would
carry the same instant and the order a thread reads in would be the order of their random ids.
`clock_timestamp()` moves within the transaction.

Task ids: M9.1.1, M9.1.2, M9.1.3, M9.2.4
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from sqlalchemy import Select, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.chat.filing import (
    continues,
    earlier_questions,
    refs_column,
    refs_of,
    shown_text,
    title_of,
)
from brain.chat.threads import Thread, ThreadMessage, refs_as_json, refs_from_json
from brain.chat.turns import Correction, RecordRef, Turn, TurnKind
from brain.core.errors import Absent
from brain.gate.answer import Answered
from brain.gate.context import Channel
from brain.knowledge.search import PRINCIPAL_SETTING
from brain.tables.chat import ConversationRow, CorrectionRow, MessageRole, MessageRow

# ------------------------------------------------------------------ written-down reasons
#: Why every transaction sets the person before it reads or writes.
A_CONVERSATION_IS_READ_AS_ITS_PERSON: Final = (
    "chat.conversation's policy admits a row only to a session naming its owner in "
    "app.principal_id, and an unset setting admits nothing. So every transaction here sets it "
    "first, from the person the route authenticated and never from a body, and a conversation "
    "somebody else owns is absent in exactly the way one that does not exist is."
)

#: Why the search matches questions and titles and never an answer.
A_SEARCH_READS_ONLY_WHAT_THE_PERSON_TYPED: Final = (
    "A match on an answer's words would tell the reader what an answer contained, including an "
    "answer they may no longer be shown, so a search is an oracle over withheld text. The title "
    "is the first question, and the person's own questions are words they typed, so those are "
    "the whole of what a search reads."
)

#: How many of a thread's messages one read returns, newest kept. A resource bound: a thread
#: longer than this shows its latest messages and says there were earlier ones.
MAX_MESSAGES_READ: Final = 200

#: The most conversations one listing returns.
MAX_LISTED: Final = 100

#: What a search term's wildcards are escaped with, written as a code point so that no editor
#: or heredoc can collapse it.
LIKE_ESCAPE: Final = chr(92)


@dataclass(frozen=True)
class Filed:
    """One stored message: what a thread is built from, and what a correction names."""

    message_id: str
    shown: ThreadMessage
    agent_id: str = ""
    ent_hash: str = ""


@dataclass(frozen=True)
class Kept:
    """One of the person's conversations as stored, oldest message first."""

    conversation_id: str
    owner_id: str
    title: str
    last_at: datetime
    messages: tuple[Filed, ...] = ()
    #: The kind of wrong the person said, by the answer's message id.
    corrected: Mapping[str, str] = field(default_factory=dict)
    #: There were earlier messages than `MAX_MESSAGES_READ` returned. Says there were, never how
    #: many.
    earlier: bool = False

    def thread(self) -> Thread | None:
        """As `brain.chat.threads.Thread`, or None while nothing has been filed in it."""
        if not self.messages:
            return None
        return Thread(
            thread_id=self.conversation_id,
            owner_id=self.owner_id,
            title=self.title,
            messages=tuple(one.shown for one in self.messages),
        )


@dataclass(frozen=True)
class Listed:
    """One conversation in the person's list: what they asked first and when it was last used."""

    conversation_id: str
    title: str
    started_at: datetime
    last_at: datetime


@dataclass(frozen=True)
class Exchange:
    """A question and what the asker was shown, as `brain.chat.filing` decided to file them."""

    channel: Channel
    question: str
    answer: str
    #: What the answer drew on, or None when that cannot be said.
    refs: tuple[RecordRef, ...] | None
    agent_id: str = ""
    ent_hash: str = ""


def _as_person(principal_id: str) -> Select[tuple[Any]]:
    """The statement naming this transaction's person to row-level security."""
    return select(func.set_config(PRINCIPAL_SETTING, principal_id, True))


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _pattern(term: str) -> str:
    """`term` as a case-insensitive substring pattern, with its own wildcards made literal."""
    escaped = "".join(LIKE_ESCAPE + one if one in "%_" + LIKE_ESCAPE else one for one in term)
    return f"%{escaped}%"


def _message(row: MessageRow) -> Filed | None:
    """A row as a message, or None for one whose role or channel no code could have written."""
    try:
        role, channel = MessageRole(row.role), Channel(row.channel)
    except ValueError:
        return None
    return Filed(
        message_id=str(row.id),
        shown=ThreadMessage(
            role=role,
            at=row.created_at,
            channel=channel,
            body=row.body,
            refs=refs_from_json(row.refs),
        ),
        agent_id=row.agent_id,
        ent_hash=row.ent_hash,
    )


class ConversationStore:
    """`chat.conversation`, `chat.message` and `chat.correction`, read and written as one person.

    Built over the application's sessions, which run every transaction as `brain_app`, the role
    the policies bind.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def open(self, principal_id: str) -> str:
        """A new conversation for this person, with no title until its first question."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as_person(principal_id))
            made = await session.execute(
                insert(ConversationRow)
                .values(principal_id=principal_id)
                .returning(ConversationRow.id)
            )
            return str(made.scalar_one())

    async def kept(self, principal_id: str, conversation_id: str) -> Kept | None:
        """One of this person's live conversations, or None for any other id."""
        wanted = _uuid(conversation_id)
        if wanted is None:
            return None
        async with self._sessions() as session, session.begin():
            await session.execute(_as_person(principal_id))
            return await self._read(session, principal_id, wanted)

    async def latest(self, principal_id: str, now: datetime) -> Kept | None:
        """The thread this person was last active in, if a chat message now still continues it."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as_person(principal_id))
            found = (
                await session.execute(
                    select(ConversationRow.id, ConversationRow.updated_at)
                    .where(
                        ConversationRow.principal_id == principal_id,
                        ConversationRow.deleted_at.is_(None),
                        ConversationRow.title.is_not(None),
                    )
                    .order_by(ConversationRow.updated_at.desc(), ConversationRow.id)
                    .limit(1)
                )
            ).first()
            if found is None or not continues(found.updated_at, now):
                return None
            return await self._read(session, principal_id, found.id)

    async def file(self, principal_id: str, conversation_id: str, exchange: Exchange) -> bool:
        """File one question and its answer in this person's conversation, or False for any other.

        The conversation takes its first question as its title and is marked used now, which is
        what the listing orders by and what a chat's continuation window is measured from.
        """
        wanted = _uuid(conversation_id)
        if wanted is None:
            return False
        async with self._sessions() as session, session.begin():
            await session.execute(_as_person(principal_id))
            touched = await session.execute(
                update(ConversationRow)
                .where(
                    ConversationRow.id == wanted,
                    ConversationRow.principal_id == principal_id,
                    ConversationRow.deleted_at.is_(None),
                )
                .values(
                    title=func.coalesce(ConversationRow.title, title_of(exchange.question)),
                    updated_at=func.clock_timestamp(),
                )
                .returning(ConversationRow.id)
            )
            if touched.first() is None:
                return False
            await session.execute(
                insert(MessageRow).values(
                    conversation_id=wanted,
                    role=MessageRole.USER.value,
                    channel=exchange.channel.value,
                    body=exchange.question,
                    refs=[],
                    created_at=func.clock_timestamp(),
                )
            )
            await session.execute(
                insert(MessageRow).values(
                    conversation_id=wanted,
                    role=MessageRole.ASSISTANT.value,
                    channel=exchange.channel.value,
                    body=exchange.answer,
                    refs=refs_column(exchange.refs),
                    agent_id=exchange.agent_id,
                    ent_hash=exchange.ent_hash,
                    created_at=func.clock_timestamp(),
                )
            )
            return True

    async def listed(
        self, principal_id: str, *, search: str = "", limit: int = MAX_LISTED
    ) -> tuple[tuple[Listed, ...], bool]:
        """This person's conversations, most recently used first, and whether there were more.

        A conversation opened and never asked in has no title and is not listed. See
        `A_SEARCH_READS_ONLY_WHAT_THE_PERSON_TYPED` for what `search` reads.
        """
        bound = max(1, min(limit, MAX_LISTED))
        statement = select(
            ConversationRow.id,
            ConversationRow.title,
            ConversationRow.created_at,
            ConversationRow.updated_at,
        ).where(
            ConversationRow.principal_id == principal_id,
            ConversationRow.deleted_at.is_(None),
            ConversationRow.title.is_not(None),
        )
        term = search.strip()
        if term:
            pattern = _pattern(term)
            asked = exists().where(
                MessageRow.conversation_id == ConversationRow.id,
                MessageRow.role == MessageRole.USER.value,
                MessageRow.body.ilike(pattern, escape=LIKE_ESCAPE),
            )
            statement = statement.where(
                or_(ConversationRow.title.ilike(pattern, escape=LIKE_ESCAPE), asked)
            )
        statement = statement.order_by(
            ConversationRow.updated_at.desc(), ConversationRow.id
        ).limit(bound + 1)
        async with self._sessions() as session, session.begin():
            await session.execute(_as_person(principal_id))
            rows = (await session.execute(statement)).all()
        found = tuple(
            Listed(
                conversation_id=str(row.id),
                title=row.title or "",
                started_at=row.created_at,
                last_at=row.updated_at,
            )
            for row in rows[:bound]
        )
        return found, len(rows) > bound

    async def correct(
        self, principal_id: str, conversation_id: str, answer: Filed, correction: Correction
    ) -> bool:
        """Keep a correction of one answer in this person's conversation. False when not theirs.

        A second correction of the same answer is dropped, and still True: it is the same
        statement made again, and the person is told the same thing both times.
        """
        wanted = _uuid(conversation_id)
        message = _uuid(answer.message_id)
        if wanted is None or message is None:
            return False
        async with self._sessions() as session, session.begin():
            await session.execute(_as_person(principal_id))
            mine = (
                await session.execute(
                    select(MessageRow.id).where(
                        MessageRow.id == message,
                        MessageRow.conversation_id == wanted,
                        MessageRow.role == MessageRole.ASSISTANT.value,
                    )
                )
            ).first()
            if mine is None:
                return False
            await session.execute(
                insert(CorrectionRow)
                .values(
                    conversation_id=wanted,
                    message_id=message,
                    kind=correction.kind.value,
                    agent_id=correction.agent_id,
                    ent_hash=answer.ent_hash,
                    refs=refs_as_json(correction.refs),
                )
                .on_conflict_do_nothing(index_elements=[CorrectionRow.message_id])
            )
            return True

    async def _read(
        self, session: AsyncSession, principal_id: str, wanted: uuid.UUID
    ) -> Kept | None:
        conversation = (
            await session.execute(
                select(ConversationRow).where(
                    ConversationRow.id == wanted,
                    ConversationRow.principal_id == principal_id,
                    ConversationRow.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if conversation is None:
            return None
        newest = list(
            (
                await session.execute(
                    select(MessageRow)
                    .where(MessageRow.conversation_id == wanted)
                    .order_by(MessageRow.created_at.desc(), MessageRow.id.desc())
                    .limit(MAX_MESSAGES_READ + 1)
                )
            ).scalars()
        )
        corrected = {
            str(row.message_id): row.kind
            for row in (
                await session.execute(
                    select(CorrectionRow.message_id, CorrectionRow.kind).where(
                        CorrectionRow.conversation_id == wanted
                    )
                )
            ).all()
        }
        read = [one for one in map(_message, reversed(newest[:MAX_MESSAGES_READ])) if one]
        return Kept(
            conversation_id=str(conversation.id),
            owner_id=conversation.principal_id,
            title=conversation.title or "",
            last_at=conversation.updated_at,
            messages=tuple(read),
            corrected=corrected,
            earlier=len(newest) > MAX_MESSAGES_READ,
        )


def store_of(state: object) -> ConversationStore | None:
    """The store over this process's application sessions, or None on a process with none.

    Built per request from `app.state.db_sessions`, which `brain.app.lifespan` sets, so nothing
    new is wired at startup and a process with no database files nothing and fails nothing.
    """
    sessions = getattr(state, "db_sessions", None)
    return ConversationStore(sessions) if isinstance(sessions, async_sessionmaker) else None


def answers_through(kept: Kept, message_id: str) -> tuple[Turn, ...]:
    """The thread's answers up to and including this message, as turns, or none when it is absent.

    What `brain.chat.turns.record_correction` reads, so the correction attaches to this answer
    and copies its agent and its references off the turn rather than off anything supplied.
    """
    ids = [one.message_id for one in kept.messages]
    if message_id not in ids:
        return ()
    return tuple(
        Turn(
            kind=TurnKind.ANSWER,
            at=one.shown.at,
            principal_id=kept.owner_id,
            agent_id=one.agent_id,
            refs=one.shown.refs or (),
        )
        for one in kept.messages[: ids.index(message_id) + 1]
        if one.shown.role is MessageRole.ASSISTANT
    )


# ------------------------------------------------------------------ the answer path's half
@dataclass(frozen=True)
class Filing:
    """Where one answered question is filed, and the earlier questions it is asked with.

    Handed to `brain.api_routes.answered_for` by a caller that knows the answer is the asker's
    own: the web route when a conversation is named, and a chat for the asker's answer and never
    for a room's. That function files it, because it alone knows which agent answered and at
    which scope.
    """

    store: ConversationStore
    conversation_id: str
    #: The person's own earlier questions in this thread, oldest first. Empty where a room may
    #: read the answer: see `brain.chat_answer`.
    earlier: tuple[str, ...] = ()

    async def file(
        self,
        principal_id: str,
        channel: Channel,
        question: str,
        answered: Answered,
        *,
        agent_id: str,
        ent_hash: str,
    ) -> bool:
        """File the question and what the asker was shown. False when the thread is not theirs."""
        exchange = Exchange(
            channel=channel,
            question=question,
            answer=shown_text(answered),
            refs=refs_of(answered),
            agent_id=agent_id,
            ent_hash=ent_hash,
        )
        return await self.store.file(principal_id, self.conversation_id, exchange)


async def filing_named(
    state: object, principal_id: str, conversation_id: uuid.UUID | None
) -> Filing | None:
    """The web's filing for a question naming a conversation, or None when it names none.

    Raises `Absent` when a conversation is named and is not this person's, which is also what a
    conversation that does not exist is. A process with no database files nothing and answers
    anyway: the id cannot be one it opened, and refusing every question during an outage would
    take asking away to protect a transcript.
    """
    if conversation_id is None:
        return None
    store = store_of(state)
    if store is None:
        return None
    kept = await store.kept(principal_id, str(conversation_id))
    if kept is None:
        raise Absent("that conversation is not this caller's")
    return Filing(
        store=store,
        conversation_id=kept.conversation_id,
        earlier=earlier_questions(kept.thread()),
    )


async def filing_current(
    state: object, principal_id: str, now: datetime, *, with_context: bool
) -> Filing | None:
    """A chat's filing: the thread its person was last in, if recent, or a new one. See
    `brain.chat.filing.A_CHAT_CONTINUES_THE_THREAD_THE_PERSON_WAS_LAST_IN`.

    `with_context` False files the question without carrying earlier ones into it, for an
    answer a room may read.
    """
    store = store_of(state)
    if store is None:
        return None
    kept = await store.latest(principal_id, now)
    if kept is None:
        return Filing(store=store, conversation_id=await store.open(principal_id))
    earlier = earlier_questions(kept.thread()) if with_context else ()
    return Filing(store=store, conversation_id=kept.conversation_id, earlier=earlier)
