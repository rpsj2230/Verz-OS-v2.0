"""Adding a document to the knowledge layer from the console: what may be added, and the upload.

Until this module the Knowledge page said "Upload" was a write nothing on the server offered, and
it was right: `brain.knowledge.uploads` held the door's decisions and said in its own docstring
that the four lines calling them did not exist. These two routes are those lines, and the text
path they call reads plain text, Markdown, PDF and Word inside the application (M7.6.3), so a
document added here is answered from on an install with no worker, no object store and no
embedding server.

**`GET /knowledge/uploads/options` says what this person may add and where.** The kinds they may
choose, the departments they may add to, whether their own level is offered, and the types and
sizes the door takes. The departments are the live registry reduced by their `admin:knowledge`
grant through `brain.knowledge.search.reach_for`, so it names only departments they already hold
that capability over, and a person holding none is answered as absent, in the words every refusal
of that kind uses.

**`POST /knowledge/uploads` takes the file as the request body, raw.** The file's name travels in
`x-upload-name`, percent-encoded, and the kind, the level and the department in the query string,
which carries nothing but words from closed lists and a department slug. A filename is where a
client's name appears, and `brain.api_routes.A_QUESTION_IN_A_URL_IS_A_QUESTION_IN_EVERY_LOG`
applies to it: a URL is written into every access log in front of the application. A multipart
body was rejected because it needs a parser this product does not otherwise depend on, and a JSON
body carrying the file as base64 because the door's running ceiling could not then be applied as
the bytes arrive, which is the check `brain.knowledge.uploads` argues for.

**Every refusal the uploader can act on is a 422 naming what to do.** The door's size and type
refusals, the scan's, a parse failure's cause (M7.2.5), the kind's rules and the level's all say
why, because the person told is the person who chose the file and the place, and naming why
discloses nothing they did not bring. A place they may not add to, and a department that does not
exist, are one 404 with no reason, so the route is not a way to ask which departments exist.

**The document is written as its uploader, published at the level it was placed.** It is stored
through `brain.knowledge.chunk_store.ingest_document`, which writes the item and its chunks under
the owner's store reach and commits before it queues any embedding. On an install that declares
no embedding revision there is nothing to queue, and the document is found by text search from
the moment the response is sent, which is the whole of M7.6.3's promise. See
`A_DOCUMENT_IS_SEARCHABLE_WHEN_THE_RESPONSE_SAYS_IT_WAS_ADDED`.

**Every upload is audited as the person who made it.** `0115`'s trigger on `know.item` appends a
`setting` entry naming the item, its kind, its level and its department, and the store runs this
request's attribution first in the transaction it writes in, so the Audit screen shows who added
what, where, at what reach, and never the title or a word of the text. See
`AN_UPLOAD_IS_AUDITED_AS_THE_PERSON_WHO_MADE_IT`.

**One parse at a time in this process.** `brain.knowledge.parse_budget` sizes a parse as the only
one running, so the text path takes a lock around it rather than letting two uploads each spend
the whole budget. A second upload waits for the first.

Task ids: M7.1.1, M7.6.3, M7.2.5, M7.4.3, M7.6.1
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from typing import Annotated, Any, Final
from urllib.parse import unquote

import structlog
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, RequestProblemView
from brain.api_routes import Asked, Asking
from brain.attribution import of_request
from brain.core.department import SLUG_RE
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.knowledge.chunk_store import ChunkStoreError, ingest_document
from brain.knowledge.chunking import Block
from brain.knowledge.document_tools import departments_query
from brain.knowledge.embed_policy import embedding_revision
from brain.knowledge.ingest import (
    TYPE_LIMITS,
    IngestRefused,
    MediaType,
    ParseFailure,
    admit_upload,
    ceiling_for,
)
from brain.knowledge.item import KnowledgeItem
from brain.knowledge.kinds import KIND_LABELS, KindError, KnowledgeKind, uploadable_kinds
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD, Reach, SearchError, reach_for
from brain.knowledge.text_path import STRUCTURAL_CHECK, TEXT_PATH_TYPES
from brain.knowledge.uploads import (
    ReadUpload,
    ReceivedUpload,
    UploadNotOffered,
    assert_declared_length,
    assert_safe_filename,
    placement_for_upload,
    read_arriving,
    read_for_text_path,
    text_path_type,
)
from brain.knowledge.visibility import KnowledgeVisibility, Visibility, VisibilityError
from brain.ops.queue import Job
from brain.routing_routes import sessions_of

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["knowledge"])

UPLOADS_PATH: Final = "/knowledge/uploads"
UPLOAD_OPTIONS_PATH: Final = "/knowledge/uploads/options"

#: The header the file's name travels in, percent-encoded UTF-8. See the module docstring.
NAME_HEADER: Final = "x-upload-name"

#: What a document is found by once added. Words rather than a flag, so the page says them.
FOUND_BY_TEXT: Final = "text search"
FOUND_BY_TEXT_AND_MEANING: Final = "text search, and by meaning once it is embedded"

#: The extensions the console offers for each type this path reads, in the order it lists them.
EXTENSIONS: Final[dict[MediaType, tuple[str, ...]]] = {
    MediaType.MARKDOWN: (".md", ".markdown"),
    MediaType.PLAIN: (".txt",),
    MediaType.PDF: (".pdf",),
    MediaType.DOCX: (".docx",),
}

#: Why the response is sent only once the rows are committed.
A_DOCUMENT_IS_SEARCHABLE_WHEN_THE_RESPONSE_SAYS_IT_WAS_ADDED: Final = (
    "ingest_document commits the item and its chunks before it returns, and the text search a "
    "question runs reads the committed rows, so a person told the document was added can ask "
    "about it at once. The embedding job, where an install has one, is queued after the commit; "
    "a queue that refuses it leaves the document found by text search and not yet by meaning, "
    "which the response says rather than failing an upload that was stored."
)

#: Why an upload's write carries the request's attribution.
AN_UPLOAD_IS_AUDITED_AS_THE_PERSON_WHO_MADE_IT: Final = (
    "Every write of know.item appends a ledger entry through 0115's trigger, and a trigger cannot "
    "know who is writing: it reads the actor, the reach digest and the trace from the transaction. "
    "So the store runs brain.attribution.of_request for this request first in the transaction it "
    "writes in, and the Audit screen shows the upload as the person who made it, at their reach, "
    "in the request that made it, naming the item, its kind and its department and never a word "
    "of what it says."
)

#: The parse lock. See the module docstring on one parse at a time. A thread lock, taken inside
#: the worker thread the parse runs in, so the event loop never waits on it and no loop owns it.
_ONE_PARSE_AT_A_TIME: Final = threading.Lock()


class KindOption(BaseModel):
    """One kind this person may choose, as stored and as read."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str
    label: str


class TypeOption(BaseModel):
    """One type the door takes on this path: its extensions and the most it may weigh."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    media_type: str
    extensions: list[str]
    max_bytes: int


class UploadOptionsView(BaseModel):
    """What this person may add and where. Their own reach only; nothing about anybody else's."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kinds: list[KindOption]
    #: The departments they may add to, sorted. Never the registry, only its part they hold.
    departments: list[str]
    #: Whether their own level is offered, which needs a read of the knowledge layer.
    personal: bool
    types: list[TypeOption]
    #: What a document added now is found by on this install.
    found_by: str
    #: The name of what checks a file before it is read, so nobody mistakes it for an antivirus.
    checked_by: str


class UploadedView(BaseModel):
    """The document that was added, in the words and places the uploader chose."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    title: str
    kind: str
    level: str
    department: str | None
    #: How many passages the document was cut into. A count of the uploader's own document.
    passages: int
    found_by: str


UPLOAD_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    **COMMON_RESPONSES,
    422: {
        "model": ErrorBody,
        "description": "Not added, and why, in words: the message, and the one problem by field.",
    },
}


# ------------------------------------------------------------------ the reads
async def live_departments(sessions: async_sessionmaker[AsyncSession]) -> tuple[str, ...]:
    """Every live department's slug, as `document_tools` reads the registry for a reach."""
    async with sessions() as session:
        result = await session.execute(departments_query().statement)
        return tuple(str(slug) for slug in result.scalars().all())


def may_add(entitlement: EntitlementSet, registry: tuple[str, ...], now: datetime) -> Reach | None:
    """Where this person may add a document, or None. A grant `reach_for` refuses adds nothing."""
    try:
        return reach_for(entitlement, departments=registry, now=now, capability=KNOWLEDGE_UPLOAD)
    except SearchError:
        return None


def reads_knowledge(entitlement: EntitlementSet, now: datetime) -> bool:
    """Whether this person holds any read of the knowledge layer."""
    return entitlement.scope_for(KNOWLEDGE_READ, now) is not None


def _sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return sessions


def read_one_at_a_time(
    received: ReceivedUpload,
    *,
    kind: KnowledgeKind,
    placement: KnowledgeVisibility,
    owner_id: str,
) -> ReadUpload | ParseFailure:
    """`read_for_text_path` under the parse lock, in the thread it runs in."""
    with _ONE_PARSE_AT_A_TIME:
        return read_for_text_path(received, kind=kind, placement=placement, owner_id=owner_id)


def _refused(field: str, code: str, message: str) -> JSONResponse:
    """A 422 whose message is the reason, so the page shows the reason and not a status word."""
    told = ErrorBody(
        message=message, problems=[RequestProblemView(field=field, code=code, message=message)]
    )
    return JSONResponse(status_code=422, content=told.model_dump(mode="json"))


# ------------------------------------------------------------------ the store
async def store_upload(
    request: Request, read: ReadUpload, *, asked: Asking
) -> tuple[Job | None, bool]:
    """Write the item and its chunks as the uploader, then queue its embedding if there is one.

    Answers the job, or None on an install that embeds nothing, and whether the job reached the
    queue. See `A_DOCUMENT_IS_SEARCHABLE_WHEN_THE_RESPONSE_SAYS_IT_WAS_ADDED`. The write is
    attributed to the request, so the ledger entry `0115`'s trigger appends for the item names the
    uploader, their reach and the trace: `AN_UPLOAD_IS_AUDITED_AS_THE_PERSON_WHO_MADE_IT`.
    """
    queued: list[bool] = []

    async def enqueue(job: Job) -> object:
        # Imported here: only an install that declares an embedding revision reaches this, and
        # the web process has no queue of its own to hold open for the others.
        from brain.ops.queue import enqueue_job, queue_app
        from brain.ops.worker import register_tasks

        settings = getattr(request.app.state, "settings", None)
        url = str(getattr(settings, "database_url", "") or "")
        try:
            app = queue_app(url, pool_max=1)
            register_tasks(app, database_url=url)
            async with app.open_async():
                found = await enqueue_job(app, job)
        except Exception as exc:
            # Broad on purpose, and after the commit: the document is stored and searchable by
            # text, and a queue that refused is a fact to log and to say, not a failed upload.
            log.warning("knowledge.embed_not_queued", error=type(exc).__name__)
            queued.append(False)
            return None
        queued.append(True)
        return found

    job = await ingest_document(
        _sessions(request),
        read.item,
        enqueue=enqueue,
        now=asked.now,
        blocks=read.blocks,
        attributed=of_request(asked),
    )
    return job, all(queued) and bool(queued)


def _uploaded(item: KnowledgeItem, blocks: tuple[Block, ...], *, meaning: bool) -> UploadedView:
    assert item.kind is not None  # set by `read_for_text_path`, which requires one
    return UploadedView(
        item_id=item.item_id,
        title=item.title,
        kind=item.kind.value,
        level=item.visibility.level.value,
        department=item.visibility.department or None,
        passages=len(blocks),
        found_by=FOUND_BY_TEXT_AND_MEANING if meaning else FOUND_BY_TEXT,
    )


# ------------------------------------------------------------------ the routes
@router.get(UPLOAD_OPTIONS_PATH, response_model=UploadOptionsView, responses=COMMON_RESPONSES)
async def upload_options(request: Request, asked: Asked) -> UploadOptionsView:
    """What this person may add, and where. Absent when they may add nothing anywhere."""
    registry = await live_departments(_sessions(request))
    where = may_add(asked.reach, registry, asked.now)
    if where is None:
        raise Absent("adding knowledge is not offered to this caller")
    return UploadOptionsView(
        kinds=[KindOption(value=one.value, label=KIND_LABELS[one]) for one in uploadable_kinds()],
        departments=sorted(where.departments),
        personal=reads_knowledge(asked.reach, asked.now),
        types=[
            TypeOption(
                media_type=media_type.value,
                extensions=list(EXTENSIONS[media_type]),
                max_bytes=min(TYPE_LIMITS[media_type].max_bytes, ceiling_for(media_type)),
            )
            for media_type in EXTENSIONS
            if media_type in TEXT_PATH_TYPES
        ],
        found_by=FOUND_BY_TEXT if embedding_revision() is None else FOUND_BY_TEXT_AND_MEANING,
        checked_by=STRUCTURAL_CHECK,
    )


@router.post(
    UPLOADS_PATH,
    status_code=201,
    response_model=UploadedView,
    responses=UPLOAD_RESPONSES,
)
async def upload(
    request: Request,
    asked: Asked,
    kind: Annotated[KnowledgeKind, Query()],
    level: Annotated[Visibility, Query()],
    department: Annotated[str, Query(max_length=60)] = "",
) -> UploadedView | JSONResponse:
    """Add one document, read by the text path, at the level and department asked for."""
    if department and not SLUG_RE.match(department):
        return _refused("department", "not_a_department", "that is not a department's name")
    sessions = _sessions(request)
    registry = await live_departments(sessions)
    owner = asked.caller.principal.id
    try:
        placement = placement_for_upload(
            level,
            department=department,
            owner_id=owner,
            may_add=may_add(asked.reach, registry, asked.now),
            reads_knowledge=reads_knowledge(asked.reach, asked.now),
        )
    except UploadNotOffered as exc:
        raise Absent(str(exc)) from exc
    except VisibilityError as exc:
        return _refused("level", "level_refused", str(exc))

    filename = unquote(request.headers.get(NAME_HEADER, ""))
    declared = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    length = request.headers.get("content-length")
    try:
        assert_safe_filename(filename)
        media_type = text_path_type(declared)
        assert_declared_length(
            media_type=media_type,
            content_length=int(length) if length and length.isdigit() else None,
        )
        body = await read_arriving(request.stream(), ceiling=ceiling_for(media_type))
        received = ReceivedUpload(
            upload=admit_upload(filename=filename, declared_type=media_type.value, content=body),
            body=body,
        )
        read = await asyncio.to_thread(
            read_one_at_a_time, received, kind=kind, placement=placement, owner_id=owner
        )
    except (IngestRefused, KindError) as exc:
        return _refused("file", "not_added", str(exc))
    if isinstance(read, ParseFailure):
        # The cause and its remedy, from `CAUSE_TEXT`, and never the parser's own words (M7.2.5).
        return _refused("file", read.cause.value, read.message())

    try:
        job, queued = await store_upload(request, read, asked=asked)
    except ChunkStoreError as exc:
        return _refused("file", "not_stored", str(exc))
    log.info(
        "knowledge.uploaded",
        principal=owner,
        item=read.item.item_id,
        kind=kind.value,
        level=placement.level.value,
    )
    return _uploaded(read.item, read.blocks, meaning=job is not None and queued)
