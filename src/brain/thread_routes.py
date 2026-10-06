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

**A person exports their own conversation, as they are shown it now, and the export is recorded
(M33.3.1.3).** `POST /threads/{id}/export` reopens the thread exactly as `GET /threads/{id}` does,
at the reach held now, and hands what it shows to `brain.member_activity.export_my_history`, which
builds the export from the person's own turns and the `ExportAudit` row filing it as a subject
access request in their own name. The row lands in `ops.data_export` (`0207`) before the document
is handed back, so there is no export without its record, and the ledger's `publish` entry follows
from `0053`'s trigger. What is exported is never more than the page shows: a reference the person
can no longer read is not re-read for the file. See `AN_EXPORT_IS_THE_THREAD_AS_IT_IS_SHOWN_NOW`.

Task ids: M9.1.1, M9.1.2, M9.1.3, M9.2.4, M12.3.6, M33.3.1.3
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Annotated, Final

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import trace_of_request
from brain.chat.remember import threads_of
from brain.chat.thread_store import CONSOLE_SURFACE, StoredThreads, surfaces
from brain.chat.threads import Thread
from brain.chat.turns import CorrectionKind, Turn, TurnKind
from brain.core.errors import Absent, Failed
from brain.knowledge.document_tools import DocumentRead, reader
from brain.knowledge.item import ITEM_ID_PATTERN
from brain.knowledge.row_store import SessionRowSource
from brain.member_activity import (
    ContinuedThread,
    continue_thread,
    export_my_history,
    recent_threads,
)
from brain.ops.data_export_store import StoredExports
from brain.routing_routes import sessions_of
from brain.tables.chat import MessageRole
from brain.tables.data_export import ExportDataSet

#: Why no route here takes a person.
A_HISTORY_IS_ONLY_EVER_THE_CALLERS: Final = (
    "A thread's title is its first question and its messages are one person's answers at their "
    "own reach, so a history is one person's or it is nothing. No route takes a person: each "
    "answers for the signed-in caller, whom the store names to row-level security first, so "
    "somebody else's history has no address."
)

#: Why a person's export is the thread as the page shows it now, and never a wider read.
AN_EXPORT_IS_THE_THREAD_AS_IT_IS_SHOWN_NOW: Final = (
    "A person's export is built from the same reopening the thread page uses, at the reach they "
    "hold now, so it carries exactly the words the page would show and never a reference they "
    "can no longer read. Its record is written before the file is handed over, filed as a "
    "subject access request in their own name, so a copy of a conversation never leaves "
    "without the row saying who took it."
)

THREADS_PATH: Final = "/threads"
THREAD_SEARCH_PATH: Final = "/threads/search"
THREAD_PATH: Final = "/threads/{thread_id}"
CORRECTIONS_PATH: Final = "/threads/{thread_id}/corrections"
EXPORT_PATH: Final = "/threads/{thread_id}/export"

#: The file a person's export downloads as, named by the thread.
EXPORT_NAME: Final = "conversation-{}.json"

#: What the person is told when their export is handed over.
EXPORT_TAKEN: Final = (
    "Your conversation is saved as a file. A record that you exported it is kept in your name."
)
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
    """A person saying the latest answer in their thread was wrong, and how. No words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: CorrectionKind


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


async def _reopened(request: Request, asked: Asked, thread_id: str) -> ContinuedThread:
    """One of the caller's threads, reopened at the reach held now, or the one 404."""
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
    return continued


@router.get(THREAD_PATH, response_model=ThreadView, responses=COMMON_RESPONSES)
async def my_thread(
    request: Request,
    asked: Asked,
    thread_id: Annotated[str, Path(pattern=THREAD_ID_PATTERN)],
) -> ThreadView:
    """One of the caller's threads, reopened at the reach held now, or one 404 for any other."""
    continued = await _reopened(request, asked, thread_id)
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
        asked.caller.principal.id, thread_id, correction.kind, now=asked.now
    )
    if kept is None:
        raise Absent(f"thread {thread_id!r} is not answerable for this caller")
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


class ExportedTurnView(BaseModel):
    """One turn as it leaves: what kind, when, and the words the page showed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    at: datetime
    text: str


class ConversationExportView(BaseModel):
    """A person's own conversation as the file holds it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    export_id: str
    conversation_id: str
    exported_at: datetime
    turns: list[ExportedTurnView]


class ConversationTakenView(BaseModel):
    """The file once, its name, and what the person is told: `data_transfer_routes`' shape.

    The document is a string rather than the object so that the bytes the browser saves are the
    bytes whose digest the record holds; a console that parsed and re-serialised it would save a
    file the record does not describe.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str
    document: str
    told: str


#: Which turn each shown message is. A system note is nobody's turn and is not exported.
TURN_OF_ROLE: Final = {MessageRole.USER: TurnKind.QUESTION, MessageRole.ASSISTANT: TurnKind.ANSWER}


def turns_shown(continued: ContinuedThread, principal_id: str) -> tuple[Turn, ...]:
    """The reopened thread's messages as turns, in order, with the words the page shows."""
    return tuple(
        Turn(kind=kind, at=one.at, principal_id=principal_id, text=one.body)
        for one in continued.shown
        if (kind := TURN_OF_ROLE.get(one.role)) is not None
    )


@router.post(EXPORT_PATH, response_model=ConversationTakenView, responses=COMMON_RESPONSES)
async def export_my_thread(
    request: Request,
    asked: Asked,
    thread_id: Annotated[str, Path(pattern=THREAD_ID_PATTERN)],
) -> JSONResponse:
    """The caller's own conversation as a file, recorded before it is handed over (M33.3.1.3).

    See `AN_EXPORT_IS_THE_THREAD_AS_IT_IS_SHOWN_NOW`.
    """
    principal_id = asked.caller.principal.id
    continued = await _reopened(request, asked, thread_id)
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    export_id = uuid.uuid4().hex
    taken, audit = export_my_history(
        turns_shown(continued, principal_id),
        principal_id=principal_id,
        conversation_id=continued.thread_id,
        at=asked.now,
        export_id=export_id,
        reason_reference=f"thread/{continued.thread_id}",
    )
    body = ConversationExportView(
        export_id=export_id,
        conversation_id=taken.conversation_id,
        exported_at=taken.at,
        turns=[
            ExportedTurnView(kind=one.kind.value, at=one.at, text=one.text) for one in taken.turns
        ],
    )
    document = body.model_dump_json()
    await StoredExports(sessions).record_report(
        data_set=ExportDataSet.CONVERSATION,
        actor=audit.requested_by,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
        reason=audit.reason,
        reason_reference=audit.reason_reference,
        at=audit.at,
        entries=audit.items,
        document_digest=hashlib.sha256(document.encode("utf-8")).hexdigest(),
    )
    taken_view = ConversationTakenView(
        filename=EXPORT_NAME.format(continued.thread_id), document=document, told=EXPORT_TAKEN
    )
    return JSONResponse(
        status_code=200,
        content=taken_view.model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )
