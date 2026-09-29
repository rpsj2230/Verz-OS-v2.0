"""Adding knowledge from a link, and many files at once: the two routes beside the upload.

`brain.knowledge_routes` adds one document, read in the request (M7.6.3). These are its two
siblings, and each is a separate route rather than a flag on that one because each changes what
the request does, which is what a reader of the route needs to see at a glance.

**`POST /knowledge/links` adds a web page by its link, fetched once and kept as the company's own
document** (M7.1.2). It is not a connector: nothing is re-read, nothing else on the site is
indexed, and the page is from then on an item like an uploaded file, at the one department or the
personal level its adder chose, answered from by text search in that scope. The fetch is
`brain.tools.fetch.fetch`, whose address rule is applied to every hop of the redirect chain,
over the skill importer's own transport, `brain.ops.skill_fetch.HttpsFetcher`, reused rather than
copied, which connects to the address the rule checked and names itself a knowledge link;
the answer's bytes decide its type (`brain.knowledge.uploads.A_LINK_IS_TYPED_BY_WHAT_IT_ANSWERED`);
the scan, the parse and the store are the upload's own, and the page's address is its first line.
The address travels in the JSON body rather than the query string, for
`brain.api_routes.A_QUESTION_IN_A_URL_IS_A_QUESTION_IN_EVERY_LOG`: a share link carries a token.

**`POST /knowledge/uploads/queued` takes one file of a bulk upload and queues it for the worker**
(M7.1.5, M22.2.4). The body, headers and query are the single upload's, so the console sends each
file of a selection the same way; what differs is that the request stops at the door. See
`brain.knowledge.ingest_queue.THE_REQUEST_ADMITS_AND_THE_WORKER_READS`. A full queue is refused
with 429 and a `Retry-After`, before a byte of the body is read, which is the backpressure
`brain.knowledge.ingest.admit_to_queue` argues for. `GET /knowledge/uploads/queued/{ticket}` says
what became of one, to the person who sent it and to nobody else.

**An accepted file is given its place in the install's document-job budget, as BATCH** (M22.1.4,
M22.2.3). Once the file has a ticket it asks `brain.ops.capacity_ledger` as
`brain.knowledge.uploads.ingestion_request`, under the ticket, so the same file sent twice holds one
place. Inside BATCH's share it starts as soon as the worker reaches it; past the share nobody is
waiting on it, so it keeps its place rather than being refused, and the answer carries its position
and expected wait, which the Knowledge page shows. The worker turns the place into a slot when it
starts and gives it back when it ends (`brain.knowledge.ingest_queue.register_ingest_tasks`). The
share is counted against every document being read, the ones read in a request by a person waiting
among them, which is how one budget is shared by two classes with different shares. Where the
install has no cache, or it does not answer, the job queue's own counts decide the position (see
`brain.ops.capacity_ledger.AN_UNANSWERED_LEDGER_DECIDES_ON_WHAT_THE_CALLER_COUNTED`). A link is
read in the request, so it takes a slot as the single upload does.

**Both are audited as the person who added them, through `0115`'s trigger.** The link is stored by
`brain.knowledge_routes.store_upload`, which attributes the write to the request; a queued file is
written by the worker as its uploader, with the queueing request's trace. The ledger entry names
the item, its kind, level and department, and never a word of it.

**A scan refusal names its cause.** The 422 says which scanner refused and why, in
`brain.knowledge.ingest.SCAN_CAUSE_TEXT`'s words (M7.1.3). A place the person may not add to is a
404 with no reason, as the upload's is.

Task ids: M7.1.2, M7.1.3, M7.1.5, M22.2.4, M7.7.3, M22.1.4, M22.2.1, M22.2.3
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime
from typing import Annotated, Any, Final, Protocol
from urllib.parse import unquote

import structlog
from fastapi import APIRouter, Body, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, RequestProblemView
from brain.api_routes import Asked, Asking, capacity_ledger_of
from brain.attribution import trace_of_request
from brain.core.department import SLUG_RE
from brain.core.errors import Absent, Failed
from brain.knowledge.app_parse_budget import app_parse_budget_bytes
from brain.knowledge.chunk_store import ChunkStoreError
from brain.knowledge.ingest import (
    IngestRefused,
    ParseFailure,
    admit_upload,
    ceiling_for,
)
from brain.knowledge.ingest_queue import (
    INGEST_TASK,
    TOO_LARGE_TO_QUEUE,
    IngestJobError,
    Ticket,
    fits_a_slot,
    get_ticket,
    ingest_job,
    new_ticket,
    outcome_sentence,
    put_ticket,
)
from brain.knowledge.kinds import KindError, KnowledgeKind
from brain.knowledge.scanners import configured_scanner
from brain.knowledge.scanning import scan_for_parsing
from brain.knowledge.uploads import (
    FetchedPage,
    OfferedAsATable,
    ReadUpload,
    UploadNotOffered,
    admit_ingestion,
    assert_declared_length,
    assert_safe_filename,
    ingestion_request,
    offer_a_table_file,
    placement_for_upload,
    read_arriving,
    read_for_link,
    receive_page,
    store_original,
    text_path_type,
)
from brain.knowledge.visibility import KnowledgeVisibility, Visibility, VisibilityError
from brain.knowledge_routes import (
    _ONE_PARSE_AT_A_TIME,
    FOUND_BY_TEXT,
    FOUND_BY_TEXT_AND_MEANING,
    NAME_HEADER,
    OFFERED_AS_A_TABLE,
    UploadedView,
    give_back,
    live_departments,
    may_add,
    reads_knowledge,
    store_upload,
    take_reading_slot,
    too_busy,
)
from brain.ops.admission import CapacityState, QueuePlacement, Resource, decide
from brain.ops.capacity_ledger import CapacityLedger, Taken
from brain.ops.object_store import ObjectStore
from brain.ops.queue import Job
from brain.ops.skill_fetch import HttpsFetcher, SystemResolver
from brain.ops.tuning import configured_budgets
from brain.routing_routes import sessions_of
from brain.tools.fetch import Fetcher, Resolver

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["knowledge"])

LINKS_PATH: Final = "/knowledge/links"
QUEUED_PATH: Final = "/knowledge/uploads/queued"

#: The longest address accepted. Past any link a person pastes, short of a body in disguise.
MAX_URL_CHARS: Final = 2048

#: A ticket as it appears in a path: the forty hex characters `ingest_queue` names one by.
TICKET_PATTERN: Final = r"^[0-9a-f]{40}$"

#: What an install whose object store is not connected is told about queued uploads.
QUEUED_UPLOADS_NEED_THE_STORE: Final = (
    "Queued uploads keep each file in this install's object store until the worker reads it, and "
    "the store is not connected, so nothing was queued. Add documents one at a time instead"
)

#: What is said when the queue could not be asked or did not take the job.
THE_QUEUE_DID_NOT_ANSWER: Final = (
    "The queue that reads uploaded files did not answer, so nothing was queued. Send it again "
    "shortly"
)

REFUSALS: Final[dict[int | str, dict[str, Any]]] = {
    **COMMON_RESPONSES,
    422: {
        "model": ErrorBody,
        "description": "Not added, and why, in words: the message, and the one problem by field.",
    },
}

QUEUED_REFUSALS: Final[dict[int | str, dict[str, Any]]] = {
    **REFUSALS,
    503: {
        "model": ErrorBody,
        "description": "The queue or a source did not answer. Nothing was queued.",
    },
    429: {
        "model": ErrorBody,
        "description": "The queue is full. Nothing was read; send it again after Retry-After.",
    },
}


class LinkAsked(BaseModel):
    """A link to add, and where. The address is in the body, never in the query string."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str = Field(min_length=1, max_length=MAX_URL_CHARS)
    kind: KnowledgeKind
    level: Visibility
    department: str = Field(default="", max_length=60)


class QueuedView(BaseModel):
    """One queued file: its ticket, its name as its sender gave it, and what became of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket: str
    name: str
    state: str
    #: The sentence the console shows, including the cause when it was not added, and the place
    #: and expected wait when it was just queued behind others.
    said: str
    item_id: str | None
    passages: int
    #: Where it stands among the work waiting for a slot to read documents, when it was queued
    #: past BATCH's share. Null when it starts as soon as the worker reaches it, and on every
    #: later look: a place is true when it is given and nobody keeps it current.
    position: int | None = None
    #: The expected wait before it starts, in seconds, beside `position`. An estimate from
    #: Little's law that assumes no new arrivals, so a floor rather than a promise.
    expected_wait_seconds: float | None = None


def _refused(
    field: str,
    code: str,
    message: str,
    *,
    status: int = 422,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """A refusal whose message is the reason, so the page shows the reason and not a status."""
    told = ErrorBody(
        message=message, problems=[RequestProblemView(field=field, code=code, message=message)]
    )
    return JSONResponse(status_code=status, content=told.model_dump(mode="json"), headers=headers)


def _sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return sessions


async def _placement(
    request: Request, asked: Asking, level: Visibility, department: str
) -> KnowledgeVisibility | JSONResponse:
    """Where this person may add, as the upload route decides it, or the refusal to send."""
    if department and not SLUG_RE.match(department):
        return _refused("department", "not_a_department", "that is not a department's name")
    registry = await live_departments(_sessions(request))
    try:
        return placement_for_upload(
            level,
            department=department,
            owner_id=asked.caller.principal.id,
            may_add=may_add(asked.reach, registry, asked.now),
            reads_knowledge=reads_knowledge(asked.reach, asked.now),
        )
    except UploadNotOffered as exc:
        raise Absent(str(exc)) from exc
    except VisibilityError as exc:
        return _refused("level", "level_refused", str(exc))


# ------------------------------------------------------------------ the link (M7.1.2)
#: What a site's log sees as the client of a knowledge link. Names the product and nothing else.
LINK_USER_AGENT: Final = "company-brain-knowledge-link/1"


def make_fetcher() -> Fetcher:
    """The transport a link is fetched over. A function so a test can hand over recorded pages.

    The skill importer's pinned transport, not a second one: its one overridden method is the one
    that would look the name up again, and a second copy of it is a second place for DNS
    rebinding to come back in.
    """
    return HttpsFetcher(user_agent=LINK_USER_AGENT)


def make_resolver() -> Resolver:
    """The resolver the address rule asks. A function so a test never asks the network."""
    return SystemResolver()


def _read_link(
    page: FetchedPage, *, kind: KnowledgeKind, placement: KnowledgeVisibility, asked: Asking
) -> ReadUpload | ParseFailure:
    # The upload route's lock, not a second one: the parse budget sizes one parse per process, and
    # a lock of this route's own would let a link and an upload each spend all of it at once.
    with _ONE_PARSE_AT_A_TIME:
        return read_for_link(
            page,
            kind=kind,
            placement=placement,
            owner_id=asked.caller.principal.id,
            taken_on=asked.now.date(),
            # Read in the application container, so against its budget: see
            # `brain.knowledge.app_parse_budget`.
            budget_bytes=app_parse_budget_bytes(),
        )


@router.post(LINKS_PATH, status_code=201, response_model=UploadedView, responses=REFUSALS)
async def add_link(
    request: Request, asked: Asked, link: Annotated[LinkAsked, Body()]
) -> UploadedView | JSONResponse:
    """Add the page a link answers with, once, at the level and department asked for."""
    placement = await _placement(request, asked, link.level, link.department)
    if isinstance(placement, JSONResponse):
        return placement
    try:
        page = await asyncio.to_thread(
            receive_page, link.url, fetcher=make_fetcher(), resolver=make_resolver()
        )
    except OfferedAsATable as exc:
        return _refused("url", OFFERED_AS_A_TABLE, str(exc))
    except (IngestRefused, KindError) as exc:
        return _refused("url", "not_added", str(exc))
    # Read in the request, so a slot as the single upload takes one, after the fetch for its
    # reason: `brain.knowledge_routes.THE_PARSE_HOLDS_A_SLOT_OF_THE_BUDGET`.
    ledger, taken = await take_reading_slot(request, now=asked.now)
    if not taken.admitted:
        return too_busy(taken.decision, field="url")
    try:
        read = await asyncio.to_thread(
            _read_link, page, kind=link.kind, placement=placement, asked=asked
        )
    except OfferedAsATable as exc:
        return _refused("url", OFFERED_AS_A_TABLE, str(exc))
    except (IngestRefused, KindError) as exc:
        return _refused("url", "not_added", str(exc))
    finally:
        await give_back(ledger, taken)
    if isinstance(read, ParseFailure):
        return _refused("url", read.cause.value, read.message())
    try:
        job, queued = await store_upload(request, read, asked=asked)
    except ChunkStoreError as exc:
        return _refused("url", "not_stored", str(exc))
    log.info(
        "knowledge.link_added",
        principal=asked.caller.principal.id,
        item=read.item.item_id,
        kind=link.kind.value,
        level=placement.level.value,
    )
    assert read.item.kind is not None  # set by `read_for_link`, which requires one
    return UploadedView(
        item_id=read.item.item_id,
        title=read.item.title,
        kind=read.item.kind.value,
        level=placement.level.value,
        department=placement.department or None,
        passages=len(read.blocks),
        found_by=FOUND_BY_TEXT_AND_MEANING if job is not None and queued else FOUND_BY_TEXT,
    )


# ------------------------------------------------------------------ the queue (M7.1.5, M22.2.4)
class IntakeQueue(Protocol):
    """What a queued upload asks of the job queue: how full it is, and to take one job."""

    async def counts(self) -> tuple[int, int]: ...

    async def enqueue(self, job: Job) -> None: ...


class DriverQueue:
    """`IntakeQueue` over the queue driver, opened for each question as the upload route opens it.

    Opened per call rather than held, for `brain.knowledge_routes.store_upload`'s reason: the web
    process holds no queue of its own for the others.
    """

    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def _app(self) -> Any:
        from brain.ops.queue import queue_app
        from brain.ops.worker import register_tasks

        app = queue_app(self._url, pool_max=1)
        register_tasks(app, database_url=self._url)
        return app

    async def counts(self) -> tuple[int, int]:
        from brain.ops.queue import outstanding_jobs

        app = self._app()
        async with app.open_async():
            return await outstanding_jobs(app, (INGEST_TASK,))

    async def enqueue(self, job: Job) -> None:
        from brain.ops.queue import enqueue_job

        app = self._app()
        async with app.open_async():
            await enqueue_job(app, job)


def queue_for(request: Request) -> IntakeQueue:
    """The job queue this process enqueues onto. A function so a test can stand one in."""
    settings = getattr(request.app.state, "settings", None)
    return DriverQueue(str(getattr(settings, "database_url", "") or ""))


def store_of(request: Request) -> ObjectStore | None:
    """This process's object store, as the lifespan built it, or None where nothing did."""
    store = getattr(request.app.state, "object_store", None)
    return store if isinstance(store, ObjectStore) else None


def _queued_view(ticket: Ticket, place: QueuePlacement | None = None) -> QueuedView:
    return QueuedView(
        ticket=ticket.ticket,
        name=ticket.filename,
        state=ticket.state.value,
        said=outcome_sentence(ticket, place=place),
        item_id=ticket.item_id or None,
        passages=ticket.passages,
        position=None if place is None else place.position,
        expected_wait_seconds=None if place is None else place.expected_wait_seconds,
    )


async def take_a_place(
    request: Request, *, ticket: str, running: int, waiting: int, now: datetime
) -> tuple[CapacityLedger | None, Taken]:
    """The queued file's place in the document-job budget, as BATCH, held under its ticket.

    `running` and `waiting` are the job queue's own counts, which decide where there is no cache
    to ask and where the cache does not answer; see the module docstring.
    """
    asked_for = ingestion_request(trace_of_request())
    budgets = configured_budgets()
    key = asked_for.budget_key
    counted = CapacityState(used={key: running}, queued={key: waiting})
    ledger = capacity_ledger_of(request.app.state)
    if ledger is None:
        return None, Taken(decision=decide(asked_for, budgets, counted, now=now))
    return ledger, await asyncio.to_thread(
        ledger.admit, asked_for, budgets, now=now, member=ticket, fallback=counted
    )


@router.post(QUEUED_PATH, status_code=202, response_model=QueuedView, responses=QUEUED_REFUSALS)
async def queue_upload(
    request: Request,
    asked: Asked,
    kind: Annotated[KnowledgeKind, Query()],
    level: Annotated[Visibility, Query()],
    department: Annotated[str, Query(max_length=60)] = "",
) -> QueuedView | JSONResponse:
    """Take one file of a bulk upload at the door, and queue it for the worker to read."""
    placement = await _placement(request, asked, level, department)
    if isinstance(placement, JSONResponse):
        return placement
    filename = unquote(request.headers.get(NAME_HEADER, ""))
    declared = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    try:
        # Before the store is asked: a spreadsheet belongs on Classification whether or not this
        # install keeps queued files, and saying so is the more useful of the two answers (M7.7.3).
        offer_a_table_file(filename, declared)
    except OfferedAsATable as exc:
        return _refused("file", OFFERED_AS_A_TABLE, str(exc))
    store = store_of(request)
    if store is None or store.backend is None:
        why = "" if store is None else f": {store.unconnected}"
        return _refused("file", "no_object_store", QUEUED_UPLOADS_NEED_THE_STORE + why)

    length = request.headers.get("content-length")
    queue = queue_for(request)
    try:
        assert_safe_filename(filename)
        media_type = text_path_type(declared)
        assert_declared_length(
            media_type=media_type,
            content_length=int(length) if length and length.isdigit() else None,
        )
    except IngestRefused as exc:
        return _refused("file", "not_added", str(exc))

    try:
        waiting, running = await queue.counts()
    except Exception as exc:
        # Broad on purpose: whatever stopped the queue answering, nothing has been read or kept,
        # and the sender is told to try again rather than handed a stack trace.
        log.warning("knowledge.queue_not_answering", error=type(exc).__name__)
        return _refused("file", "queue_unavailable", THE_QUEUE_DID_NOT_ANSWER, status=503)
    admission = admit_ingestion(
        trace_id=trace_of_request(),
        budgets=configured_budgets(),
        state=CapacityState(used={(Resource.DOCUMENT_JOBS, ""): running}),
        depth=waiting,
        now=asked.now,
    )
    if not admission.accepted:
        log.info("knowledge.queue_refused", **admission.log_record())
        wait = max(1, math.ceil(admission.retry_after_seconds))
        return _refused(
            "file", "queue_full", admission.reason, status=429, headers={"Retry-After": str(wait)}
        )

    try:
        body = await read_arriving(request.stream(), ceiling=ceiling_for(media_type))
        upload = admit_upload(filename=filename, declared_type=media_type.value, content=body)
        if not fits_a_slot(upload):
            return _refused("file", "too_large_to_queue", f"{filename!r}: {TOO_LARGE_TO_QUEUE}")
        scanned = await asyncio.to_thread(
            scan_for_parsing, upload, body, scanner=configured_scanner()
        )
    except IngestRefused as exc:
        return _refused("file", "not_added", str(exc))

    ticket = new_ticket(
        upload,
        placement=placement,
        kind=kind,
        owner_id=asked.caller.principal.id,
        trace_id=trace_of_request(),
        now=asked.now,
    )
    backend = store.backend
    ledger, taken = await take_a_place(
        request, ticket=ticket.ticket, running=running, waiting=waiting, now=asked.now
    )
    queued = False
    try:
        await asyncio.to_thread(store_original, scanned, backend=backend, prefix=store.prefix)
        await asyncio.to_thread(put_ticket, backend, ticket, prefix=store.prefix)
        try:
            await queue.enqueue(ingest_job(ticket.ticket))
        except Exception as exc:
            # After the original and the ticket are kept: sending the file again writes the same
            # two objects under the same names, so a retry costs a transfer and leaves nothing.
            log.warning("knowledge.queue_did_not_take", error=type(exc).__name__)
            return _refused("file", "queue_unavailable", THE_QUEUE_DID_NOT_ANSWER, status=503)
        queued = True
    finally:
        # A place held for a file that never reached the queue would stand in front of every
        # file after it until it lapsed.
        if not queued:
            await give_back(ledger, taken)
    log.info(
        "knowledge.queued",
        principal=asked.caller.principal.id,
        ticket=ticket.ticket,
        kind=kind.value,
        level=placement.level.value,
        starts_now=taken.admitted,
        degraded=taken.degraded,
    )
    return _queued_view(ticket, place=taken.decision.queue)


@router.get(QUEUED_PATH + "/{ticket}", response_model=QueuedView, responses=COMMON_RESPONSES)
async def queued_status(
    request: Request, asked: Asked, ticket: Annotated[str, Path(pattern=TICKET_PATTERN)]
) -> QueuedView:
    """What became of one queued file. Its sender's to ask; anybody else is answered as absent."""
    store = store_of(request)
    if store is None or store.backend is None:
        raise Absent("no queued upload by that ticket")
    try:
        found = await asyncio.to_thread(get_ticket, store.backend, ticket, prefix=store.prefix)
    except IngestJobError as exc:
        raise Absent("no queued upload by that ticket") from exc
    if found.owner_id != asked.caller.principal.id:
        raise Absent("no queued upload by that ticket")
    return _queued_view(found)
