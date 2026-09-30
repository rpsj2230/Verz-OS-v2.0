"""Install acceptance checks for getting a document in: the scan, a link, the queue, the width.

The upload door, its scan, the link path, the ingestion queue and the embedding width were built
with unit tests over fakes, and the documents check proves only the plain upload. These checks ask
each on the install as reserved people in the reserved departments, inside the check's
rolled-back transaction, through the functions the routes and the worker call.

**A file the scan refuses is built here, and it is inert.** The structural check refuses a PDF
naming script and a Word file holding a macro project by the bytes they carry, so the files built
below carry those names and nothing that runs: the PDF's script action is empty and the macro part
is a few bytes that are no macro. The antivirus's own test string is assembled at run time from
two halves, so no scanner on a developer's machine, in CI or on the server flags this module's
source as the virus it names. See `A_REFUSED_FILE_IS_BUILT_INERT`.

**A link is fetched from the documentation domain.** `example.com` is reserved by RFC 2606 for
documentation and answers with a short page that exists to be fetched in examples, so the check
fetches the real internet through the product's own fetcher and address rule without naming any
company's site. An install that cannot reach it is told so and the check is not run. See
`A_LINK_IS_FETCHED_FROM_THE_DOCUMENTATION_DOMAIN`.

**What the database cannot roll back is removed by name.** A queued upload keeps its original and
its ticket in the object store, outside any transaction, so the check deletes both keys it wrote
when it ends, whatever happened; the ingestion job itself runs in the check's transaction and is
never put on the install's queue. See
`brain.ops.acceptance.WHAT_THE_DATABASE_CANNOT_ROLL_BACK_IS_REMOVED_BY_NAME`.

**The antivirus half is its own check.** The owner decided on 2026-09-28 (needs-rupash 105) that
uploads get the structural check now and an antivirus with the scanning package later, so an
install with no antivirus set up says that check was not run rather than failing it, and M7.1.3
closes only when both pass.

Task ids: M38.5.1
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _found, _in, _upload
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.knowledge.ingest import ScanCause

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 180

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the refused files are built here and why they are harmless.
A_REFUSED_FILE_IS_BUILT_INERT: Final = (
    "The structural check refuses a PDF naming script and a Word file holding a macro project by "
    "what their bytes name, so the files built here name those and run nothing: an empty script "
    "action and a macro part of a few bytes that is no macro. The antivirus test string is joined "
    "from two halves at run time, so no scanner flags this module's source as a virus."
)

#: Why the link check fetches the documentation domain.
A_LINK_IS_FETCHED_FROM_THE_DOCUMENTATION_DOMAIN: Final = (
    "RFC 2606 reserves example.com for documentation, and it answers with a short page that "
    "exists to be fetched in examples. The check fetches it through the product's own fetcher "
    "and address rule, so the real internet is used and no company's site is named. An install "
    "that cannot reach it says the check was not run."
)

# ------------------------------------------------------------------------ the figures
#: The page the link check adds, and a phrase the page holds.
LINK_CHECKED: Final = "https://example.com/"
LINK_PHRASE: Final = "Example Domain"

#: The industry's antivirus test file, in two halves joined at run time. Not malware: every
#: antivirus reports it as a test signature by agreement, which is what it is for.
EICAR_HEAD: Final = "X5O!P%@AP[4" + chr(92) + "PZX54(P^)7CC)7}$EICAR-STANDARD"
EICAR_TAIL: Final = "-ANTIVIRUS-TEST-FILE!$H+H*"


# --------------------------------------------------------------------------- the files
def a_pdf_naming_script(text: str) -> bytes:
    """`a_pdf` with an empty script action on its catalogue: a name the scan refuses, no script."""
    from brain.ops.acceptance_documents import a_pdf

    plain = a_pdf(text)
    catalogue = b"<< /Type /Catalog /Pages 2 0 R >>"
    active = b"<< /Type /Catalog /Pages 2 0 R /OpenAction << /S /JavaScript /JS () >> >>"
    return plain.replace(catalogue, active, 1)


def a_word_document_holding_a_macro_part(heading: str, paragraph: str) -> bytes:
    """A Word file with a part named as a macro project, holding a few bytes that are no macro."""
    from brain.ops.acceptance_documents import a_word_document

    source = io.BytesIO(a_word_document(heading, paragraph))
    out = io.BytesIO()
    with zipfile.ZipFile(source) as plain, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as made:
        for one in plain.infolist():
            made.writestr(one, plain.read(one.filename))
        made.writestr("word/vbaProject.bin", b"not a macro")
    return out.getvalue()


async def _library(h: Harness) -> tuple[str, str, str]:
    """Both departments founded; a library person and a member in acceptance_a, a member in b."""
    await h.found_departments()
    library, member, outsider = (
        h.principal(A, "library"),
        h.principal(A, "member"),
        h.principal(B, "member"),
    )
    await h.person(library, department=A, grants=_in(A, "admin:knowledge"))
    await h.person(member, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(outsider, department=B, grants=_in(B, *KNOWLEDGE_READS))
    return library, member, outsider


async def _refused_as(h: Harness, uploader: str, filename: str, declared: str, body: bytes) -> str:
    """The sentence the upload door refused a file with, or a failure if it was read."""
    from brain.knowledge.ingest import IngestRefused, ParseFailure

    try:
        read = await _upload(h, uploader, filename=filename, declared=declared, body=body)
    except IngestRefused as refused:
        return str(refused)
    if isinstance(read, ParseFailure):
        raise CheckFailedError("a file the scan should refuse reached the parser")
    raise CheckFailedError("a file the scan should refuse was read and stored")


def _told(cause: ScanCause) -> str:
    from brain.knowledge.ingest import SCAN_CAUSE_TEXT

    return SCAN_CAUSE_TEXT[cause]


# --------------------------------------------------------- 1. the structural scan (M7.1.3)
@check(
    leaves=("M7.1.3",),
    sentence=(
        "A PDF naming a script action and a Word file holding a macro part, uploaded into "
        "acceptance_a, are refused before they are read with the cause each carries, and neither "
        "is found by a member's search; a clean PDF uploaded the same way is read and found."
    ),
)
async def a_file_carrying_script_or_macros_is_refused_before_it_is_read(h: Harness) -> None:
    from brain.knowledge.ingest import MediaType, ParseFailure, ScanCause

    library, member, _ = await _library(h)
    words = {one: h.word() for one in ("pdf", "word", "clean")}
    script = await _refused_as(
        h, library, "Acceptance.pdf", MediaType.PDF.value, a_pdf_naming_script(words["pdf"])
    )
    macro = await _refused_as(
        h,
        library,
        "Acceptance.docx",
        MediaType.DOCX.value,
        a_word_document_holding_a_macro_part("Check", words["word"]),
    )
    if _told(ScanCause.ACTIVE_CONTENT) not in script or _told(ScanCause.MACROS) not in macro:
        raise CheckFailedError("a refused file was not refused with the cause it carries")
    from brain.ops.acceptance_documents import a_pdf

    clean = await _upload(
        h,
        library,
        filename="Acceptance.pdf",
        declared=MediaType.PDF.value,
        body=a_pdf(words["clean"]),
    )
    if isinstance(clean, ParseFailure):
        raise CheckFailedError("a clean PDF uploaded beside the refused ones was not read")
    for key, expected in (("pdf", False), ("word", False), ("clean", True)):
        found, _ = await _found(h, member, words[key])
        if bool(found.records) is not expected:
            raise CheckFailedError("a refused file was stored, or a clean one was not")


# ------------------------------------------------------------- 2. the antivirus (M7.1.3)
@check(
    leaves=("M7.1.3",),
    sentence=(
        "With the install's antivirus set up, the antivirus test file uploaded into acceptance_a "
        "as a Markdown document is refused as malware before it is read and is never found."
    ),
)
async def the_antivirus_test_file_is_refused_as_malware(h: Harness) -> None:
    from brain.knowledge.ingest import MediaType, ScanCause
    from brain.knowledge.scanners import CLAMAV, checked_by

    if CLAMAV not in await asyncio.to_thread(checked_by):
        raise CheckNotRunError(
            "this install checks uploads with the structural check alone and runs no antivirus "
            "yet, so the antivirus half was not asked"
        )
    library, member, _ = await _library(h)
    body = f"{EICAR_HEAD}{EICAR_TAIL}".encode()
    said = await _refused_as(h, library, "Acceptance.md", MediaType.MARKDOWN.value, body)
    if _told(ScanCause.MALWARE_SIGNATURE) not in said:
        raise CheckFailedError("the antivirus test file was not refused as malware")
    found, _ = await _found(h, member, "EICAR")
    if any(one.department == A for one in found.records):
        raise CheckFailedError("the antivirus test file was stored")


# ----------------------------------------------------------------------- 3. a link (M7.1.2)
@check(
    leaves=("M7.1.2",),
    sentence=(
        "A link to the documentation domain added in acceptance_a is fetched through the "
        "install's own fetcher and address rule, read as a page and stored; a member there finds "
        "it by a phrase on the page, cited by its address, and a member of acceptance_b does not."
    ),
)
async def a_link_is_fetched_read_and_found_in_its_department(h: Harness) -> None:
    from brain.knowledge.ingest import IngestRefused, ParseFailure
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.uploads import placement_for_upload, read_for_link, receive_page
    from brain.knowledge.visibility import Visibility
    from brain.knowledge_intake_routes import make_fetcher, make_resolver
    from brain.knowledge_routes import live_departments, may_add, reads_knowledge

    library, member, outsider = await _library(h)
    try:
        page = await asyncio.to_thread(
            receive_page, LINK_CHECKED, fetcher=make_fetcher(), resolver=make_resolver()
        )
    except IngestRefused as refused:
        if "could not be fetched" in str(refused):
            raise CheckNotRunError(
                "this install could not reach the documentation domain, so no link was fetched"
            ) from None
        raise CheckFailedError("the documentation domain's page was refused at the door") from None
    reach = await h.reach(library)
    placement = placement_for_upload(
        Visibility.DEPARTMENT,
        department=A,
        owner_id=library,
        may_add=may_add(reach, await live_departments(h.sessions), h.now),
        reads_knowledge=reads_knowledge(reach, h.now),
    )
    read = await asyncio.to_thread(
        read_for_link,
        page,
        kind=KnowledgeKind.SOP,
        placement=placement,
        owner_id=library,
        taken_on=h.now.date(),
    )
    if isinstance(read, ParseFailure):
        raise CheckFailedError("the documentation domain's page could not be read")
    await _stored(h, library, read)
    item = str(read.item.item_id)
    _, kept = await _found(h, member, LINK_PHRASE)
    if not any(one.get("document_id") == item for one in kept):
        raise CheckFailedError("a member did not find the linked page by a phrase on it")
    opened = await _opened(h, member, item)
    if not opened or page.source not in opened[0]:
        raise CheckFailedError("the linked page, opened by a member, did not name its address")
    elsewhere, _ = await _found(h, outsider, LINK_PHRASE)
    if any(one.document_id == item for one in elsewhere.records):
        raise CheckFailedError("a member of another department found the linked page")


async def _opened(h: Harness, reader: str, document_id: str) -> list[str]:
    """A document's passages in reading order, as the cited document route reads them for
    `reader`: through the registered reader and the passage redaction."""
    from brain.gate.model_lane import redact_passages
    from brain.knowledge.document_tools import DocumentRead
    from brain.knowledge.document_tools import reader as document_reader
    from brain.knowledge.row_store import SessionRowSource

    reach = await h.reach(reader)
    found = await document_reader(SessionRowSource(h.sessions))(
        DocumentRead(document_id=document_id), entitlement=reach, now=h.now
    )
    kept = redact_passages(found, entitlement=reach, now=h.now).payload.records
    return [str(one.get("document", "")) for one in kept]


async def _stored(h: Harness, uploader: str, read: Any) -> None:
    """A read upload stored as `brain.knowledge_routes.store_upload` stores it, queueing nothing."""
    from brain.knowledge.chunk_store import ingest_document
    from brain.knowledge.embed_policy import REVISION_SETTING, REVISION_UNSET
    from brain.tables.audit import attributed_to

    reach = await h.reach(uploader)

    async def no_queue(job: object) -> object:
        raise CheckFailedError("a document added on the text path queued work for a worker")

    await ingest_document(
        h.sessions,
        read.item,
        enqueue=no_queue,
        now=h.now,
        env={REVISION_SETTING: REVISION_UNSET},
        blocks=read.blocks,
        attributed=attributed_to(actor_id=uploader, ent_hash=reach.ent_hash(), trace_id=h.trace_id),
    )


# ---------------------------------------------------------------- 4. the queue (M7.1.5)
@check(
    leaves=("M7.1.5",),
    sentence=(
        "The install's ingestion queue answers how full it is, and the queue route's own "
        "decision takes one more file at that depth and refuses one past the queue's limit with "
        "a hint of when to send it again."
    ),
)
async def a_full_ingestion_queue_refuses_with_a_retry_hint(h: Harness) -> None:
    from brain.knowledge.uploads import admit_ingestion, queue_limits_for
    from brain.knowledge_intake_routes import DriverQueue
    from brain.ops.admission import CapacityState, Resource
    from brain.ops.tuning import configured_budgets

    if not h.settings.database_url:
        raise CheckNotRunError("the process running this check names no database for the queue")
    try:
        waiting, running = await DriverQueue(h.settings.database_url).counts()
    except Exception as exc:
        raise CheckFailedError("the install's ingestion queue did not answer") from exc
    budgets = configured_budgets()
    limits = queue_limits_for(budgets)

    def asked(depth: int) -> Any:
        return admit_ingestion(
            trace_id=h.trace_id,
            budgets=budgets,
            state=CapacityState(used={(Resource.DOCUMENT_JOBS, ""): running}),
            depth=depth,
            now=h.now,
        )

    if waiting < limits.max_depth and not asked(waiting).accepted:
        raise CheckFailedError("a queue with room refused one more file")
    past = asked(limits.max_depth + 1)
    if past.accepted or past.retry_after_seconds <= 0:
        raise CheckFailedError("a full queue took a file, or refused it with no hint")


# ---------------------------------------------- 5. a queued file and its original (M7.1.5, M7.1.4)
@check(
    leaves=("M7.1.5", "M7.1.4"),
    sentence=(
        "A file queued into acceptance_a is scanned and its original kept in the install's object "
        "store, byte for byte, in a bucket that keeps originals; the worker's ingestion job reads "
        "it from there and a member finds it. The original and its ticket are removed after."
    ),
)
async def a_queued_file_is_kept_in_the_store_and_read_by_the_worker(h: Harness) -> None:
    from brain.knowledge.embed_policy import REVISION_SETTING, REVISION_UNSET
    from brain.knowledge.ingest import MediaType, admit_upload
    from brain.knowledge.ingest_queue import (
        IngestRun,
        TicketState,
        new_ticket,
        put_ticket,
        run_ingest_job,
        ticket_key,
    )
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.scanners import configured_scanner
    from brain.knowledge.scanning import scan_for_parsing
    from brain.knowledge.uploads import original_bucket, placement_for_upload, store_original
    from brain.knowledge.visibility import Visibility
    from brain.knowledge_routes import live_departments, may_add, reads_knowledge
    from brain.ops.acceptance_documents import a_markdown_document
    from brain.ops.object_store import object_store_at_start

    store = await asyncio.to_thread(
        object_store_at_start, h.settings.vault_address, h.settings.vault_token
    )
    backend = store.backend
    if backend is None:
        raise CheckNotRunError(
            "this install has no object store connected, so a queued file has nowhere to wait"
        )
    library, member, _ = await _library(h)
    word = h.word()
    body = a_markdown_document("Acceptance queue", f"The queued document says {word}.")
    upload = admit_upload(
        filename="Acceptance queued.md", declared_type=MediaType.MARKDOWN.value, content=body
    )
    scanned = await asyncio.to_thread(scan_for_parsing, upload, body, scanner=configured_scanner())
    reach = await h.reach(library)
    placement = placement_for_upload(
        Visibility.DEPARTMENT,
        department=A,
        owner_id=library,
        may_add=may_add(reach, await live_departments(h.sessions), h.now),
        reads_knowledge=reads_knowledge(reach, h.now),
    )
    ticket = new_ticket(
        upload,
        placement=placement,
        kind=KnowledgeKind.SOP,
        owner_id=library,
        trace_id=h.trace_id,
        now=h.now,
    )
    bucket = original_bucket()
    kept = await asyncio.to_thread(store_original, scanned, backend=backend, prefix=store.prefix)
    h.removes(lambda: backend.delete_object(bucket.name, kept.key))
    h.removes(
        lambda: backend.delete_object(bucket.name, ticket_key(ticket.ticket, prefix=store.prefix))
    )
    await asyncio.to_thread(put_ticket, backend, ticket, prefix=store.prefix)
    if await asyncio.to_thread(backend.get_object, bucket.name, kept.key) != body:
        raise CheckFailedError("the original kept in the object store is not the file queued")
    if kept.retention_days is not None:
        raise CheckFailedError("originals are kept in a bucket that expires them")

    async def refuse(job: object) -> object:
        raise CheckFailedError("the ingestion job queued work beyond the document it read")

    outcome = await run_ingest_job(
        ticket.ticket,
        IngestRun(
            backend=backend,
            prefix=store.prefix,
            sessions=h.sessions,
            enqueue=refuse,
            now=h.now,
            env={REVISION_SETTING: REVISION_UNSET},
        ),
    )
    if outcome.state is not TicketState.ADDED:
        raise CheckFailedError("the worker's ingestion job did not add the queued file")
    found, _ = await _found(h, member, word)
    if not found.records:
        raise CheckFailedError("a member did not find the file the worker read from the queue")


# ------------------------------------------------------------ 6. the width (M7.7.4)
@check(
    leaves=("M7.7.4",),
    sentence=(
        "The install's vector column is the width its setting declares; a width above what the "
        "index supports is refused when the setting is read; and the migration's own refusal, "
        "asked to change the width, is silent over no vectors and refuses once a passage holds one."
    ),
)
async def the_embedding_width_is_the_installs_and_held_under_vectors(
    h: Harness,
) -> None:
    from sqlalchemy import text

    from brain.knowledge.search import (
        EMBEDDING_DIMENSIONS,
        INDEXABLE_DIMENSION_CEILING,
        WIDTH_SETTING,
        SearchError,
        declared_dimensions,
        width_change_refusal,
    )

    column = (
        await h.execute(
            text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute"
                " WHERE attrelid = 'know.chunk'::regclass AND attname = 'embedding'"
            )
        )
    ).scalar_one()
    if column != f"vector({EMBEDDING_DIMENSIONS})":
        raise CheckFailedError("the vector column is not the width this install's setting names")
    try:
        declared_dimensions({WIDTH_SETTING: str(INDEXABLE_DIMENSION_CEILING + 1)})
    except SearchError:
        pass
    else:
        raise CheckFailedError("a width the vector index cannot hold was accepted when read")

    other = EMBEDDING_DIMENSIONS + 1 if EMBEDDING_DIMENSIONS < INDEXABLE_DIMENSION_CEILING else 1
    library, _, _ = await _library(h)
    read = await _upload(
        h,
        library,
        filename="Acceptance width.md",
        declared="text/markdown",
        body=f"# Width\n\nThe width check wrote {h.word()}.\n".encode(),
    )
    from brain.ops.acceptance_retrieval import _embedded

    along = (1.0,) + (0.0,) * (EMBEDDING_DIMENSIONS - 1)
    await _embedded(h, library, str(read.item.item_id), lambda n: along)
    if not await _refused_by_the_migration(h, library, width_change_refusal(other)):
        raise CheckFailedError("the width refusal let a width change pass under a stored vector")


async def _refused_by_the_migration(h: Harness, owner: str, statement: str) -> bool:
    """Whether the migration's own refusal refuses, run as the application at `owner`'s reach.

    As the application rather than as the login, because the chunk table's policy admits a
    passage to the application under a reach and the check's vector is on a reserved passage;
    the login a check runs under need not own the table the migration's owner does. A refusal
    raised inside the savepoint ends the savepoint and leaves the check's transaction whole.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from brain.knowledge.chunk_store import reach_of
    from brain.knowledge.search import session_settings

    try:
        async with h.sessions() as session:
            reach = await reach_of(session, owner, now=h.now)
            if reach is None:
                raise CheckFailedError("the uploader of a passage reached none of it")
            for setting in session_settings(reach):
                await session.execute(setting)
            await session.execute(text(statement))
    except DBAPIError:
        return True
    return False


# ------------------------------------------------------- 7. a price list is a table (M7.7.3)
@check(
    leaves=("M7.7.3",),
    sentence=(
        "A price list sent to acceptance_a as a document, one at a time and to the queue, is "
        "answered with the offer to add it on Classification and nothing of it is read or found; "
        "the same file added on Classification is kept as a table of classified rows."
    ),
)
async def a_price_list_sent_as_a_document_is_offered_to_classification(h: Harness) -> None:
    import json
    from urllib.parse import quote

    from fastapi import FastAPI
    from starlette.requests import Request

    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.uploads import TABLE_OFFER_TEXT
    from brain.knowledge.visibility import Visibility
    from brain.knowledge_intake_routes import queue_upload
    from brain.knowledge_routes import NAME_HEADER, OFFERED_AS_A_TABLE, upload
    from brain.ops.acceptance_checks_tables import (
        ASKED_COLUMNS,
        ASKED_HEADINGS,
        _administrator,
        _price_list,
    )
    from brain.ops.acceptance_checks_tables import _upload as _classified

    library, member, _ = await _library(h)
    prices = _price_list(h, "offer", ASKED_HEADINGS, ASKED_COLUMNS)
    body = prices.csv()
    app = FastAPI()
    app.state.db_sessions = h.sessions
    person = await StoredPrincipals(h.sessions).live_principal(library)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    # With a second factor, as an administrator adding knowledge signs in: `admit` withholds an
    # `admin:` verb from a session without one.
    reach = admit(await h.reach(library), Channel.CONSOLE, Assurance.STRONG)
    # A cast at the routes' boundary: they read the caller's principal, reach and instant, and a
    # `Caller` is minted only from a verified token.
    asking = cast(
        Any, SimpleNamespace(caller=SimpleNamespace(principal=person), reach=reach, now=h.now)
    )

    def sent(path: str) -> Any:
        headers = [
            (b"content-type", b"text/csv"),
            (b"content-length", str(len(body)).encode()),
            (NAME_HEADER.encode(), quote("Acceptance price list.csv").encode()),
        ]

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        scope = {"type": "http", "app": app, "headers": headers, "method": "POST", "path": path}
        return Request(scope, receive)

    for door in (upload, queue_upload):
        answered = await door(
            sent("/api/v1/knowledge/uploads"),
            asking,
            KnowledgeKind.PRICING_NOTE,
            Visibility.DEPARTMENT,
            A,
        )
        told = json.loads(bytes(getattr(answered, "body", b"{}")) or b"{}")
        problems = told.get("problems") or [{}]
        if (
            getattr(answered, "status_code", 0) != 422
            or problems[0].get("code") != OFFERED_AS_A_TABLE
            or told.get("message") != TABLE_OFFER_TEXT
        ):
            raise CheckFailedError(
                "a price list sent as a document was not offered to Classification"
            )
    words = {value for row in prices.rows for value in row.values() if value != A}
    for word in sorted(words)[:3]:
        found, _ = await _found(h, member, word)
        if found.records:
            raise CheckFailedError("a price list sent as a document was read as text")

    admin = await _administrator(h)
    stored, _ = await _classified(
        h, admin, prices, filename="Acceptance price list.csv", content=body
    )
    if stored.entity != prices.entity:
        raise CheckFailedError("the price list added on Classification was not kept as a table")
