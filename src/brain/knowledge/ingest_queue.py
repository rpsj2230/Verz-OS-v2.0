"""Many files at once: admitted at the door, read in the worker, so a parse never runs beside Ask.

A single document added from the console is read inside the request (M7.6.3), which is right for
one file and wrong for fifty: fifty parses in the web process are fifty parses on the CPU and the
connection pool that answer questions. M7.1.5 asks for an ingestion queue with backpressure and
M22.2.4 for ingestion throttled so a bulk parse cannot slow the chat, and this module is both:
the door stays in the request, and the reading moves to the worker.

**The request admits and the worker reads, and that split is the throttle.** The request does what
must be answered to the person sending the file and nothing more: the name, the type, the
declared length and the running ceiling, the sniff, the queue's own depth, the scan, and the
original written to the object store. The parse, the chunking, the write and the embedding job
all happen in a worker process with its own connections, on the `SYSTEM` class whose single slot
is housekeeping's, so a hundred files are read one at a time in a container that answers no
question. See `THE_REQUEST_ADMITS_AND_THE_WORKER_READS`.

**Backpressure is the queue's own count, refused at the door with a wait.** `brain.knowledge.
uploads.admit_ingestion` already decides it, and until now had no caller. It is asked with the
driver's counts of these tasks' waiting and running jobs, through `brain.ops.queue.
outstanding_jobs`, so the number that refuses is the number of rows the worker will fetch rather
than a counter kept beside them. A full queue refuses before a byte of the body is read.

**A job carries a ticket, and the ticket lives beside the original in the object store.** A
filename is the likeliest place a client's name appears, and the queue's table has no row-level
security and a retention of its own (`brain.ops.queue.Job`), so the job's one argument is the
ticket, a digest. The ticket names the file, its kind, where it goes, who sent it and the request
that did, and it sits in the bucket that already holds the whole of the original. See
`A_JOB_CARRIES_A_TICKET_AND_NOT_THE_FILE`.

**The uploader's grants are read when the job runs, not when it was queued.** `Job`'s own rule is
that entitlements revoked since the queueing must not be in the queue; so the worker resolves them
again, asks `placement_for_upload` again, and writes through `ingest_document` as the uploader,
which resolves their store reach a third time in the transaction it writes in. The ledger entry
`0115`'s trigger appends names the uploader, their reach at the moment of the write, and the trace
of the request that queued it. See `THE_GRANTS_ARE_READ_WHEN_THE_JOB_RUNS`.

**A queued file must fit one standard slot, and a larger one is refused at the door.** The job
runs in the general worker, whose slot is `MIB_PER_SLOT`, and its parse is bounded by that slot
(`parse_scanned`'s budget), so a job cannot spend more than its slot whatever reached it. The
container sized for a larger parse, `brain-parse-worker`, drains `system.whole_container` and
today registers no task and holds no vault token for the object store, so a job routed there
would be fetched by nothing that can run it. Rather than queue work nothing will read, a file
whose declared cost is over a standard slot (a PDF over about eight megabytes) is refused with
the remedy: add it one at a time, where it is read in the request. Wiring the parse worker is
the parse service's (K4, M7.2.6), and a second task on `SlotClass.WHOLE_CONTAINER` is then one
registration. See `A_QUEUED_FILE_FITS_ONE_STANDARD_SLOT`.

**The outcome is written onto the ticket.** Nobody is waiting on the request any more, so the
cause of a scan refusal or a parse failure (M7.2.5) has to be kept somewhere the uploader can ask
for it, and the ticket is the one record that names both the file and its owner. The console asks
`GET /knowledge/uploads/queued/{ticket}`, answered to the uploader alone.

**It needs the object store, and says so when there is none.** Nothing else on an install holds a
file between a request and a worker: a queue row may not, and the database has no table for bytes.
An install whose store is not connected is told that queued uploads need it, and the one-at-a-time
upload still works there.

Task ids: M7.1.5, M22.2.4
"""

from __future__ import annotations

import enum
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import TextClause
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.entitlement import EntitlementSet
from brain.gate.context import TrafficClass
from brain.gate.entitlement_store import RESOLVE, entitlements_from
from brain.knowledge.chunk_store import ChunkStoreError, ingest_document
from brain.knowledge.document_tools import departments_query
from brain.knowledge.ingest import (
    AdmittedUpload,
    IngestRefused,
    MediaType,
    ParseFailure,
    admit_upload,
)
from brain.knowledge.kinds import KindError, KnowledgeKind
from brain.knowledge.parse_budget import MIB, fits_parse_budget
from brain.knowledge.scanning import Scanner
from brain.knowledge.search import KNOWLEDGE_READ, KNOWLEDGE_UPLOAD, Reach, SearchError, reach_for
from brain.knowledge.search import session_settings as reach_settings
from brain.knowledge.uploads import (
    UPLOAD_ID_PREFIX,
    ReceivedUpload,
    UploadNotOffered,
    original_bucket,
    original_key,
    placement_for_upload,
    read_for_text_path,
    upload_item_id,
)
from brain.knowledge.visibility import KnowledgeVisibility, Visibility, VisibilityError
from brain.ops.queue import MIB_PER_SLOT, Job, Redrive
from brain.ops.storage import StorageBackend
from brain.tables.audit import attributed_to

# ------------------------------------------------------------------ written-down reasons
#: Why the request stops at the door and the worker does the reading.
THE_REQUEST_ADMITS_AND_THE_WORKER_READS: Final = (
    "The web process answers questions, and a parse is the most expensive thing done to a "
    "document: CPU for the reader, memory for the file, and connections for the write. A bulk "
    "upload read in the request would spend those beside every question asked meanwhile. So the "
    "request checks what the sender must be told at once, the door, the queue's depth and the "
    "scan, stores the original, and queues a job; the worker reads it on the SYSTEM class, one "
    "slot at a time, in a container with its own pool. The request path of a queued upload never "
    "calls a parser."
)

#: Why the job's one argument is a ticket.
A_JOB_CARRIES_A_TICKET_AND_NOT_THE_FILE: Final = (
    "A queue row has no row-level security and its own retention, and a filename is where a "
    "client's name appears, so a job names nothing but a digest. What the worker needs, the "
    "file's name, kind, place, owner and the request that queued it, is a ticket stored beside "
    "the original in the bucket that already holds the whole of the file."
)

#: Why only a file one standard slot can hold is queued.
A_QUEUED_FILE_FITS_ONE_STANDARD_SLOT: Final = (
    "The general worker reads queued files in a slot of MIB_PER_SLOT, and the parse there is "
    "bounded by that slot. The parse worker, sized for larger files, registers no task and holds "
    "no store credential yet, so a job queued for it would be fetched by nothing that runs it. A "
    "file whose declared parse cost is over one slot is refused at the door, naming the remedy, "
    "rather than accepted into a queue nothing drains."
)

#: Why the worker asks the uploader's grants again.
THE_GRANTS_ARE_READ_WHEN_THE_JOB_RUNS: Final = (
    "Entitlements granted when a file was queued and revoked before it was read must not still "
    "apply, which is brain.ops.queue.Job's rule. So the worker resolves the uploader's grants "
    "when the job runs, asks placement_for_upload again, and a file its uploader may no longer "
    "add there is not added, with the ticket saying so."
)

# ------------------------------------------------------------------ the figures
#: The task a queued file is read by, in the general worker.
INGEST_TASK: Final = "knowledge.ingest"

#: The class ingestion runs on: nobody is waiting, which is what `SYSTEM` means.
INGEST_TRAFFIC_CLASS: Final = TrafficClass.SYSTEM

#: What one standard slot may spend on a parse: the slot's own size, so a queued parse is bounded
#: by the slot it runs in and not by the parse worker's larger budget.
STANDARD_PARSE_BUDGET: Final = MIB_PER_SLOT * MIB

#: Where tickets live, under the install's prefix, in the bucket originals live in.
TICKET_PREFIX: Final = "knowledge/queued"

#: The length of a ticket: the digest part of the item id the file will be added as.
TICKET_CHARS: Final = 40

_HEX: Final = frozenset("0123456789abcdef")

#: The content type a ticket is stored under.
TICKET_TYPE: Final = "application/json"


class IngestJobError(Exception):
    """A queued job that cannot report its own outcome: no ticket, or no store to write one to."""


class TicketState(enum.StrEnum):
    """Where a queued file is. Three states, and a failed one says why in its own field."""

    QUEUED = "queued"
    ADDED = "added"
    NOT_ADDED = "not_added"


@dataclass(frozen=True)
class Ticket:
    """What the worker needs to read one queued file, and what became of it.

    References and choices, never content: the digest, the type the door proved, the name the
    uploader gave, the kind, the place and the owner, and the trace of the request that queued
    it so the ledger ties the worker's write to that request. `reason` is the sentence the
    uploader is told when it was not added, built from `CAUSE_TEXT`, `SCAN_CAUSE_TEXT` or a
    refusal's own words, and never from the file.
    """

    ticket: str
    digest: str
    media_type: MediaType
    size_bytes: int
    filename: str
    kind: KnowledgeKind
    level: Visibility
    department: str
    owner_id: str
    trace_id: str
    queued_at: datetime
    state: TicketState = TicketState.QUEUED
    item_id: str = ""
    passages: int = 0
    code: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if len(self.ticket) != TICKET_CHARS or not set(self.ticket) <= _HEX:
            msg = f"a ticket is {TICKET_CHARS} hex characters, and {self.ticket[:8]!r}... is not"
            raise IngestRefused(msg)

    def to_json(self) -> bytes:
        raw: dict[str, Any] = asdict(self)
        raw["queued_at"] = self.queued_at.isoformat()
        return json.dumps(raw, sort_keys=True).encode("utf-8")

    @classmethod
    def from_json(cls, raw: bytes) -> Ticket:
        """A stored ticket, or a refusal. Every field is read by name and checked by its type."""
        try:
            data = json.loads(raw.decode("utf-8"))
            return cls(
                ticket=str(data["ticket"]),
                digest=str(data["digest"]),
                media_type=MediaType(data["media_type"]),
                size_bytes=int(data["size_bytes"]),
                filename=str(data["filename"]),
                kind=KnowledgeKind(data["kind"]),
                level=Visibility(data["level"]),
                department=str(data["department"]),
                owner_id=str(data["owner_id"]),
                trace_id=str(data["trace_id"]),
                queued_at=datetime.fromisoformat(str(data["queued_at"])),
                state=TicketState(data["state"]),
                item_id=str(data["item_id"]),
                passages=int(data["passages"]),
                code=str(data["code"]),
                reason=str(data["reason"]),
            )
        except (UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
            msg = "a stored ticket could not be read as one"
            raise IngestJobError(msg) from exc

    def outcome(self, state: TicketState, *, code: str = "", reason: str = "") -> Ticket:
        return replace(self, state=state, code=code, reason=reason)


def ticket_for(upload: AdmittedUpload, placement: KnowledgeVisibility, owner_id: str) -> str:
    """The ticket: the digest part of the item id this file will be added as.

    So sending the same file to the same place twice is one ticket and one item, as it is one
    item for a single upload (`uploads.AN_UPLOAD_IS_NAMED_BY_WHAT_IT_IS_AND_WHERE_IT_WENT`).
    """
    return upload_item_id(upload, placement, owner_id).removeprefix(UPLOAD_ID_PREFIX)


def ticket_key(ticket: str, *, prefix: str = "") -> str:
    """Where a ticket is stored. Addressed by the ticket, which is a digest, never by the name."""
    key = f"{TICKET_PREFIX}/{ticket}.json"
    return f"{prefix}/{key}" if prefix else key


def new_ticket(
    upload: AdmittedUpload,
    *,
    placement: KnowledgeVisibility,
    kind: KnowledgeKind,
    owner_id: str,
    trace_id: str,
    now: datetime,
) -> Ticket:
    """The ticket for a file the door admitted and the scan cleared, before it is queued."""
    return Ticket(
        ticket=ticket_for(upload, placement, owner_id),
        digest=upload.digest,
        media_type=upload.media_type,
        size_bytes=upload.size_bytes,
        filename=upload.filename,
        kind=kind,
        level=placement.level,
        department=placement.department,
        owner_id=owner_id,
        trace_id=trace_id,
        queued_at=now,
    )


# ------------------------------------------------------------------ the slot and the job
#: What the sender of a file too large to queue is told.
TOO_LARGE_TO_QUEUE: Final = (
    "this file is larger than a queued upload may be, because the worker that reads queued files "
    "holds one ordinary document at a time. Add it with Add a document, which reads it straight "
    "away, or split it into smaller documents."
)


def fits_a_slot(upload: AdmittedUpload) -> bool:
    """Whether one standard slot can hold this file's parse; `A_QUEUED_FILE_FITS_ONE_STANDARD_SLOT`.

    `fits_parse_budget` asked with the slot's own size, so the answer is the one `parse_scanned`
    gives inside that slot.
    """
    return fits_parse_budget(upload, budget_bytes=STANDARD_PARSE_BUDGET)


def ingest_job(ticket: str) -> Job:
    """One queued file's job: its ticket and nothing else.

    `Redrive.SAFE`, because running it twice writes the same item under the same id and the same
    outcome onto the same ticket, which `ingest_document` treats as replacing it.
    """
    return Job(
        task=INGEST_TASK,
        traffic_class=INGEST_TRAFFIC_CLASS,
        args={"ticket": ticket},
        redrive=Redrive.SAFE,
    )


# ------------------------------------------------------------------ the store's two objects
def put_ticket(backend: StorageBackend, ticket: Ticket, *, prefix: str = "") -> None:
    """Write a ticket beside the originals, in the bucket `uploads.original_bucket` checks."""
    bucket = original_bucket()
    backend.put_object(
        bucket.name, ticket_key(ticket.ticket, prefix=prefix), ticket.to_json(), TICKET_TYPE
    )


def get_ticket(backend: StorageBackend, ticket: str, *, prefix: str = "") -> Ticket:
    """A stored ticket, or `IngestJobError` when there is none or it will not read as one."""
    bucket = original_bucket()
    try:
        raw = backend.get_object(bucket.name, ticket_key(ticket, prefix=prefix))
    except Exception as exc:
        # Broad on purpose: each backend names a missing object differently, and a job with no
        # ticket has nothing to report to and nowhere to report it.
        msg = f"ticket {ticket[:8]}... is not in the store ({type(exc).__name__})"
        raise IngestJobError(msg) from exc
    return Ticket.from_json(raw)


# ------------------------------------------------------------------ the uploader, now
@dataclass(frozen=True)
class Uploader:
    """The uploader's grants as the resolver answers now, and the departments that exist now."""

    entitlement: EntitlementSet
    registry: tuple[str, ...]


async def uploader_now(
    sessions: async_sessionmaker[AsyncSession], principal_id: str, *, now: datetime
) -> Uploader:
    """The uploader's grants at this moment. See `THE_GRANTS_ARE_READ_WHEN_THE_JOB_RUNS`.

    The resolver is told whose grants it reads before it reads them, as
    `brain.knowledge.chunk_store.reach_of` tells it, in a transaction of its own.
    """
    async with sessions() as session, session.begin():
        for setting in reach_settings(Reach(principal_id=principal_id)):
            await session.execute(setting)
        payload = (
            await session.execute(RESOLVE, {"principal_id": principal_id, "at": now})
        ).scalar_one()
        registry = (await session.execute(departments_query().statement)).scalars().all()
    return Uploader(
        entitlement=entitlements_from(payload), registry=tuple(str(one) for one in registry)
    )


def placement_now(ticket: Ticket, uploader: Uploader, *, now: datetime) -> KnowledgeVisibility:
    """Where the file goes if its uploader may still add it there; refused as the route refuses."""
    try:
        may_add: Reach | None = reach_for(
            uploader.entitlement,
            departments=uploader.registry,
            now=now,
            capability=KNOWLEDGE_UPLOAD,
        )
    except SearchError:
        may_add = None
    return placement_for_upload(
        ticket.level,
        department=ticket.department,
        owner_id=ticket.owner_id,
        may_add=may_add,
        reads_knowledge=uploader.entitlement.scope_for(KNOWLEDGE_READ, now) is not None,
    )


# ------------------------------------------------------------------ the job
#: What a worker hands the job to reach the store, the database, the queue and the clock.
Enqueue = Callable[[Job], Awaitable[object]]


@dataclass(frozen=True)
class IngestRun:
    """Everything one run of the job touches, handed in so a test can stand each one in."""

    backend: StorageBackend
    prefix: str
    sessions: async_sessionmaker[AsyncSession]
    enqueue: Enqueue
    now: datetime
    scanner: Scanner | None = None
    env: Mapping[str, str] | None = None


#: What the uploader is told when the original in the store is not the file that was queued.
NOT_THE_QUEUED_FILE: Final = (
    "the file kept for reading is missing or is not the file that was queued, so nothing was "
    "read. Upload it again."
)

#: What the uploader is told when adding it there is no longer theirs to do.
NO_LONGER_OFFERED: Final = (
    "adding knowledge there is no longer offered to you, so the file was not added."
)


async def run_ingest_job(ticket_id: str, run: IngestRun) -> Ticket:
    """Read one queued file and add it as its uploader, or record why not (M7.1.5, M22.2.4).

    The order is the single upload's, with the grants asked again first. Every outcome the
    uploader can act on is written onto the ticket and the job succeeds, because the job did what
    it was for: it decided. Only a job with no ticket, or a store it cannot write back to, fails,
    because it has nowhere to say anything; the queue records that failure for an operator.
    """
    ticket = get_ticket(run.backend, ticket_id, prefix=run.prefix)
    outcome = await _decide(ticket, run)
    put_ticket(run.backend, outcome, prefix=run.prefix)
    return outcome


async def _decide(ticket: Ticket, run: IngestRun) -> Ticket:
    if ticket.state is not TicketState.QUEUED:
        # A redrive after the outcome was written: the decision stands, and running it again
        # would only write the same one.
        return ticket
    bucket = original_bucket()
    try:
        body = run.backend.get_object(
            bucket.name,
            original_key(_admitted_shape(ticket), prefix=run.prefix),
        )
    except Exception:
        # Broad on purpose: each backend names a missing object in its own words. A store that
        # is down fails the write of this outcome too, and the job then fails for the queue to
        # record; an original that is gone is the sender's to be told.
        return ticket.outcome(TicketState.NOT_ADDED, code="not_added", reason=NOT_THE_QUEUED_FILE)
    try:
        upload = admit_upload(
            filename=ticket.filename, declared_type=ticket.media_type.value, content=body
        )
    except IngestRefused:
        return ticket.outcome(TicketState.NOT_ADDED, code="not_added", reason=NOT_THE_QUEUED_FILE)
    if upload.digest != ticket.digest:
        return ticket.outcome(TicketState.NOT_ADDED, code="not_added", reason=NOT_THE_QUEUED_FILE)

    uploader = await uploader_now(run.sessions, ticket.owner_id, now=run.now)
    try:
        placement = placement_now(ticket, uploader, now=run.now)
    except (UploadNotOffered, VisibilityError):
        return ticket.outcome(TicketState.NOT_ADDED, code="not_offered", reason=NO_LONGER_OFFERED)

    try:
        read = read_for_text_path(
            ReceivedUpload(upload=upload, body=body),
            kind=ticket.kind,
            placement=placement,
            owner_id=ticket.owner_id,
            scanner=run.scanner,
            budget_bytes=STANDARD_PARSE_BUDGET,
        )
    except (IngestRefused, KindError) as exc:
        return ticket.outcome(TicketState.NOT_ADDED, code="not_added", reason=str(exc))
    if isinstance(read, ParseFailure):
        return ticket.outcome(TicketState.NOT_ADDED, code=read.cause.value, reason=read.message())

    try:
        await ingest_document(
            run.sessions,
            read.item,
            enqueue=run.enqueue,
            now=run.now,
            env=run.env,
            blocks=read.blocks,
            attributed=attribution(ticket, uploader),
        )
    except ChunkStoreError as exc:
        return ticket.outcome(TicketState.NOT_ADDED, code="not_stored", reason=str(exc))
    return replace(
        ticket,
        state=TicketState.ADDED,
        item_id=read.item.item_id,
        passages=len(read.blocks),
        code="",
        reason="",
    )


def attribution(ticket: Ticket, uploader: Uploader) -> tuple[TextClause, ...]:
    """The ledger's three settings for the worker's write: the uploader, their reach now, and
    the trace of the request that queued it, so the Audit screen ties the two together."""
    return attributed_to(
        actor_id=ticket.owner_id,
        ent_hash=uploader.entitlement.ent_hash(),
        trace_id=ticket.trace_id,
    )


def _admitted_shape(ticket: Ticket) -> AdmittedUpload:
    """The ticket as the upload it describes, to address its original by digest."""
    return AdmittedUpload(
        filename=ticket.filename,
        media_type=ticket.media_type,
        size_bytes=ticket.size_bytes,
        digest=ticket.digest,
    )


# ------------------------------------------------------------------ registering the task
#: How the worker builds its store: a backend and the install's prefix, or why it has none.
StoreMaker = Callable[[], tuple[StorageBackend | None, str, str]]


def _store_from_settings(env: Mapping[str, str] | None) -> StoreMaker:
    def make() -> tuple[StorageBackend | None, str, str]:
        from brain.ops.object_store import object_store_at_start
        from brain.settings import process_environment, settings_from

        settings = settings_from(process_environment() if env is None else env)
        store = object_store_at_start(settings.vault_address, settings.vault_token)
        return store.backend, store.prefix, store.unconnected

    return make


def register_ingest_tasks(
    app: Any,
    *,
    database_url: str,
    env: Mapping[str, str] | None = None,
    make_store: StoreMaker | None = None,
) -> None:
    """Put the ingestion task on the queue driver, on the queue its class derives.

    Called from `brain.ops.worker.register_tasks`, so every process that registers the worker's
    tasks, the web process enqueueing among them, knows these names. The store is built on the
    first job and kept, as the embedding client is, so a worker whose store is not connected
    still starts and each job it is handed fails naming why.
    """
    from brain.ops.queue import enqueue_job, register_task
    from brain.session import make_app_engine, make_application_sessions

    held: list[tuple[StorageBackend | None, str, str]] = []
    build = make_store or _store_from_settings(env)

    async def run(ticket: str) -> str:
        if not held:
            held.append(build())
        backend, prefix, unconnected = held[0]
        if backend is None:
            msg = f"the object store is not connected, so no queued file can be read: {unconnected}"
            raise IngestJobError(msg)

        async def enqueue(job: Job) -> object:
            return await enqueue_job(app, job)

        engine = make_app_engine(database_url)
        try:
            outcome = await run_ingest_job(
                ticket,
                IngestRun(
                    backend=backend,
                    prefix=prefix,
                    sessions=make_application_sessions(engine),
                    enqueue=enqueue,
                    now=datetime.now(tz=UTC),
                    env=env,
                ),
            )
        finally:
            await engine.dispose()
        return outcome.state.value

    register_task(app, INGEST_TASK, run, traffic_class=INGEST_TRAFFIC_CLASS)


def outcome_sentence(ticket: Ticket) -> str:
    """What the console says about one queued file, in the uploader's own terms."""
    match ticket.state:
        case TicketState.QUEUED:
            return f"{ticket.filename} is queued to be read."
        case TicketState.ADDED:
            return f"{ticket.filename} was added."
        case TicketState.NOT_ADDED:
            return f"{ticket.filename} was not added: {ticket.reason}"
