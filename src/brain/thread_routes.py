"""A person's own threads: listed, searched and reopened, and never anybody else's.

`brain.member_activity.recent_threads` and `continue_thread` decided what a person's history is and
what of it may be shown again, and `brain.chat.thread_store` now keeps it. These three routes are
the addresses the web application reads them at, for the signed-in person alone.

**There is no parameter naming whose threads.** Every route answers for the caller, and the store
names the caller to row-level security before it reads, so a history that is not yours is not
addressable at all. See `A_HISTORY_IS_ONLY_EVER_THE_CALLERS`.

**A thread that is not yours and one that does not exist are one 404**, with the sentence an
unknown record gets, because a refusal would say the id exists.

**An answer is shown again at the reach held now.** `continue_thread` shows the person's own
questions always and an answer only when every record behind it is still theirs to read, and
leaves no mark where one was left out; see
`brain.chat.threads.AN_ANSWER_IS_SHOWN_AGAIN_ONLY_AT_THE_REACH_HELD_NOW`.

**The search reads the person's questions and nothing an answer said**; see
`brain.chat.thread_store.SEARCH_READS_ONLY_THE_ASKERS_OWN_QUESTIONS`.

**A person may say the latest answer in their thread was wrong**, choosing a kind from a closed
list and writing nothing, which is kept as a signal for learning (M9.2.4).

**A person attaches a document to their own thread, and an agent answering them reads it
(M12.3.6).** `POST /threads/attachments` names a document the caller may already read, which an
upload at their own level makes, and keeps it on their thread as a reference
(`brain.chat.thread_store.StoredThreads.attach`), opening a thread when the id named is not theirs.
A document the caller cannot read is one 404, the same as one that does not exist.
`chat.read_attachment` is how an agent reads it: see `brain.chat.attachments`.

Task ids: M9.1.1, M9.1.2, M9.1.3, M9.2.4, M12.3.6
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import trace_of_request
from brain.chat.remember import threads_of
from brain.chat.thread_store import CONSOLE_SURFACE, StoredThreads, surfaces
from brain.chat.threads import Thread
from brain.chat.turns import CorrectionKind
from brain.core.errors import Absent, Failed
from brain.knowledge.candidate_store import propose
from brain.knowledge.candidates import WORDS_CHARS
from brain.knowledge.document_tools import DocumentRead, reader
from brain.knowledge.item import ITEM_ID_PATTERN
from brain.knowledge.row_store import SessionRowSource
from brain.member_activity import continue_thread, recent_threads

#: Why no route here takes a person.
A_HISTORY_IS_ONLY_EVER_THE_CALLERS: Final = (
    "A thread's title is its first question and its messages are one person's answers at their "
    "own reach, so a history is one person's or it is nothing. No route takes a person: each "
    "answers for the signed-in caller, whom the store names to row-level security first, so "
    "somebody else's history has no address."
)

THREADS_PATH: Final = "/threads"
THREAD_SEARCH_PATH: Final = "/threads/search"
THREAD_PATH: Final = "/threads/{thread_id}"
CORRECTIONS_PATH: Final = "/threads/{thread_id}/corrections"
ATTACHMENTS_PATH: Final = "/threads/attachments"

#: The longest search a person may type, which is a few words and not a paragraph.
SEARCH_CHARS: Final = 200

#: A thread id as the tables hold one: a UUID's text.
THREAD_ID_PATTERN: Final = r"^[0-9a-fA-F-]{36}$"

router = APIRouter(prefix=API_PREFIX, tags=["threads"])


class ThreadSummaryView(BaseModel):
    """One thread in a list: its title, when it was last used and where. Nothing counted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    thread_id: str
    title: str
    last_at: datetime
    last_channel: str


class ThreadsView(BaseModel):
    """This person's threads, most recently used first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[ThreadSummaryView]


class ThreadMessageView(BaseModel):
    """One message shown again: who said it, when, where, and the words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: str
    at: datetime
    channel: str
    body: str


class CorrectionAsked(BaseModel):
    """A person saying the latest answer in their thread was wrong, and how; and, if they choose,
    what the right answer is (M16.6.5).

    The words never reach the correction, which has no field for them. They are held as a
    candidate about the document the answer cited, and change nothing until somebody who may
    replace that document approves them: `brain.knowledge.candidates`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: CorrectionKind
    right_answer: str | None = Field(default=None, max_length=WORDS_CHARS)


class CorrectionView(BaseModel):
    """What was kept: the kind, and when. Nothing about the answer or its records."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    at: datetime


class AttachAsked(BaseModel):
    """A document the caller may read, to keep on one of their threads, or on a new one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    thread_id: str | None = Field(default=None, pattern=THREAD_ID_PATTERN)
    attachment_id: str = Field(pattern=ITEM_ID_PATTERN)


class AttachedView(BaseModel):
    """Which thread the document is kept on, which is the one to continue with."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    thread_id: str
    attachment_id: str


class ThreadView(BaseModel):
    """One thread reopened on the web, with what may be shown of it now."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    thread_id: str
    title: str
    messages: list[ThreadMessageView]


def _store(request: Request) -> StoredThreads:
    store = threads_of(request.app.state)
    if store is None:
        # The same for every caller: a process with no database keeps no history.
        raise Failed("no database on this process")
    return store


def _listed(threads: tuple[Thread, ...], asked: Asked) -> ThreadsView:
    recent = recent_threads(
        threads,
        principal_id=asked.caller.principal.id,
        reader=asked.reach,
        audience_is_one_person=True,
        now=asked.now,
    )
    return ThreadsView(
        items=[
            ThreadSummaryView(
                thread_id=one.thread_id,
                title=one.title,
                last_at=one.last_at,
                last_channel=one.last_channel.value,
            )
            for one in recent
        ]
    )


@router.get(THREADS_PATH, response_model=ThreadsView, responses=COMMON_RESPONSES)
async def my_threads(request: Request, asked: Asked) -> ThreadsView:
    """The caller's most recently used threads, wherever each was asked (M9.1.1, M9.1.2)."""
    threads = await _store(request).threads(asked.caller.principal.id)
    return _listed(threads, asked)


@router.get(THREAD_SEARCH_PATH, response_model=ThreadsView, responses=COMMON_RESPONSES)
async def search_my_threads(
    request: Request,
    asked: Asked,
    q: Annotated[str, Query(min_length=1, max_length=SEARCH_CHARS)],
) -> ThreadsView:
    """The caller's threads whose questions hold every word asked, and nobody else's (M9.1.3)."""
    threads = await _store(request).search(asked.caller.principal.id, q)
    return _listed(threads, asked)


@router.get(THREAD_PATH, response_model=ThreadView, responses=COMMON_RESPONSES)
async def my_thread(
    request: Request,
    asked: Asked,
    thread_id: Annotated[str, Path(pattern=THREAD_ID_PATTERN)],
) -> ThreadView:
    """One of the caller's threads, reopened at the reach held now, or one 404 for any other."""
    principal_id = asked.caller.principal.id
    found = await _store(request).thread(principal_id, thread_id)
    continued = continue_thread(
        () if found is None else (found,),
        thread_id,
        principal_id=principal_id,
        reader=asked.reach,
        reading=CONSOLE_SURFACE,
        surfaces=surfaces(),
        audience_is_one_person=True,
        now=asked.now,
    )
    if continued is None:
        raise Absent(f"thread {thread_id!r} is not answerable for this caller")
    return ThreadView(
        thread_id=continued.thread_id,
        title=continued.title,
        messages=[
            ThreadMessageView(
                role=one.role.value, at=one.at, channel=one.channel.value, body=one.body
            )
            for one in continued.shown
        ],
    )


@router.post(
    CORRECTIONS_PATH, status_code=201, response_model=CorrectionView, responses=COMMON_RESPONSES
)
async def correct_my_thread(
    request: Request,
    asked: Asked,
    thread_id: Annotated[str, Path(pattern=THREAD_ID_PATTERN)],
    correction: CorrectionAsked,
) -> CorrectionView:
    """Mark the latest answer in one of the caller's threads as wrong (M9.2.4).

    Kept as a signal and never as a fact: see
    `brain.chat.thread_store.A_CORRECTION_IS_A_SIGNAL_AND_NEVER_A_FACT`. A thread that is not the
    caller's, does not exist or holds no answer is one 404.
    """
    kept = await _store(request).correct(
        asked.caller.principal.id,
        thread_id,
        correction.kind,
        now=asked.now,
        trace_id=trace_of_request(),
    )
    if kept is None:
        raise Absent(f"thread {thread_id!r} is not answerable for this caller")
    if correction.right_answer and correction.right_answer.strip():
        # Held as a candidate about the document the answer cited, in the person's own name, and
        # told to nobody here: whether a candidate formed says which documents the answer cited
        # are still theirs to read, which the correction's own reply does not say either.
        sessions = request.app.state.db_sessions
        await propose(
            sessions,
            SessionRowSource(sessions),
            correction=kept,
            thread_id=thread_id,
            words=correction.right_answer,
            reach=asked.reach,
            now=asked.now,
            trace_id=trace_of_request() or f"correction.{thread_id}",
        )
    return CorrectionView(kind=kept.kind.value, at=kept.at)


@router.post(
    ATTACHMENTS_PATH, status_code=201, response_model=AttachedView, responses=COMMON_RESPONSES
)
async def attach_to_my_thread(
    request: Request, asked: Asked, attaching: AttachAsked
) -> AttachedView:
    """Keep a document the caller may read on one of their threads (M12.3.6).

    Asked of the document reader at the caller's reach first, so a document they cannot read is
    the same 404 as one that does not exist. See `brain.chat.attachments`.
    """
    store = _store(request)
    readable = await reader(SessionRowSource(request.app.state.db_sessions))(
        DocumentRead(document_id=attaching.attachment_id, limit=1),
        entitlement=asked.reach,
        now=asked.now,
    )
    if not readable.records:
        raise Absent("that document is not one this caller may read")
    thread_id = await store.attach(
        asked.caller.principal.id,
        thread_id=attaching.thread_id,
        attachment_id=attaching.attachment_id,
        now=asked.now,
    )
    return AttachedView(thread_id=thread_id, attachment_id=attaching.attachment_id)
