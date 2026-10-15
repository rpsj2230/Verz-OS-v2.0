"""The install's checks for the model server it has switched on.

`brain.ops.overlays` starts the server where `INSTALL_SERVICES` names `modelserver` and the
server has room for it, and a container that started proves nothing about the memory design this
product sells to the owner: that it holds what the install chose and no more. So these ask, from the
worker, what a person with a shell on the server would ask.

**A server this install has not switched on is not run, never failed.** An install that chose not
to run one, or whose server had no room for it, has not got it wrong, and a red row there would
teach an owner to ignore the page. Each reason is one literal sentence (`brain.ops.acceptance`): a
reason is served on a public page, so it cannot be built from anything the check read.

**The limit is judged on what the server's docker said, and the parts on what the server itself
says.** Whether a container runs, is healthy and is held to a memory limit is invisible from inside
the worker, so the deploy step asks docker after it starts the services and keeps the answer for the
release (`brain.ops.overlays`, `THE_SERVER_REPORTS_WHAT_RUNS_AND_THE_CHECK_READS_IT`); the first
check reads it and compares the limit with the one this install's own settings cost, which is not a
constant in this file. The second asks the server's readiness route, which lists the parts it was
told to run and every file or program one of them is missing, and which loads nothing.
**Rejected: loading a part to prove it works.** That would hold the memory the check is there to
show is given back, and a check that cost the install what it measures is a check nobody can run
beside the work.

**The document parts are asked with a page this module writes.** A one-page PDF with one line of
text printed on it (`a_page_of_text`) is sent to each part the install chose, through the
product's own reader for that part, and the line must come back: as a block from layout, as a
recognised page from the scanned-page part (the page is rendered and recognised, so it proves the
render and the recogniser and not a photograph), as a paragraph from the general reader. A page
with nothing on it, or a scan, would prove less; this proves that each part loads, reads and
answers in the shape the product decodes, once, on this install's own server.

**What these do not prove, and the leaves that wait for something else.** That a passage is
embedded is proved by the checks of the part that does it, and that a measured peak reaches the
database is proved by the check that sends the server a batch. The largest upload the install admits
is held against the limit by the peaks the server has really recorded
(`no_recorded_model_server_peak_exceeds_its_costed_limit`), which is only as good as the
documents it has really been sent: **no check sends a 25 MB document on every update**, because a
part loading and reading one takes minutes and an acceptance run follows every update. Nothing here
claims a leaf closed: they are evidence that the frame is the one that was costed and that the
parts read.

Task ids: M7.2.1, M7.2.3, M7.2.4, M7.3.3, M7.7.11
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Final

import structlog

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.ops.model_server import Part
    from brain.ops.overlays import Seen

#: Where this module's checks stand on the Install page, before every larger key.
CHECK_ORDER: Final = 396

log = structlog.get_logger(__name__)

#: How long the readiness route may take. It reads the disk and answers; it loads nothing.
READY_TIMEOUT_SECONDS: Final = 10.0

#: Said where the install has not switched the model server on.
NO_MODEL_SERVER_HERE: Final = (
    "this install has not switched the model server on: INSTALL_SERVICES does not name modelserver"
)

#: Said where the deploy step has not reported this release's optional services.
NOT_REPORTED_FOR_THIS_RELEASE: Final = (
    "the deploy step has not reported this release's optional services yet, so there is nothing "
    "the server said to judge; it reports them after every deploy that starts them"
)

#: Said where the server's docker does not show the model server running and healthy.
THE_MODEL_SERVER_IS_NOT_RUNNING: Final = (
    "the model server is not running and healthy on this release as the server reported it"
)

#: Said where it runs under a limit other than the one this install's settings cost.
THE_MODEL_SERVER_IS_NOT_HELD_TO_ITS_LIMIT: Final = (
    "the model server runs under a memory limit other than the one this install's settings cost; "
    "the worker's log gives both figures"
)

#: Said where the settings cannot be read as a configuration at all.
THE_SETTINGS_CANNOT_BE_READ: Final = (
    "the model server's settings on this install are not a configuration it could have started "
    "with, so there is no limit to compare the running one with"
)

#: Said where the server does not answer its readiness route from the worker.
THE_MODEL_SERVER_DID_NOT_ANSWER: Final = (
    "the model server this install has switched on did not answer its readiness route from the "
    "worker"
)

#: Said where it answers that it is not ready.
A_PART_IS_NOT_READY: Final = (
    "the model server says a part this install chose is missing what it needs to load; the "
    "worker's log names which"
)

#: Said where it answers ready for a set of parts other than the ones this install chose.
IT_RUNS_OTHER_PARTS_THAN_WERE_CHOSEN: Final = (
    "the model server reports running a set of parts other than the one this install chose, so "
    "the memory it was costed for is not the memory it may take"
)


async def _reported(h: Harness) -> dict[str, Seen]:
    """What the deploy step reported of the services for this release, or not run."""
    from brain.ops.overlays import BY_NAME, OBSERVED_KEY, seen_in, switched_on_here
    from brain.ops.setting_store import read_namespace

    if BY_NAME["modelserver"] not in switched_on_here():
        raise CheckNotRunError(NO_MODEL_SERVER_HERE)
    namespace = OBSERVED_KEY.split(".", 1)[0]
    async with h.sessions() as session:
        held = await read_namespace(session, namespace)
    row = held.get(OBSERVED_KEY)
    seen = None if row is None else seen_in(row.value, commit=h.settings.resolved_commit())
    if seen is None:
        raise CheckNotRunError(NOT_REPORTED_FOR_THIS_RELEASE)
    return dict(seen)


@check(
    leaves=("M7.3.3",),
    sentence=(
        "The model server this install has switched on runs and is reported healthy by the "
        "server's own docker on this release, under a memory limit equal to the one this "
        "install's own settings cost, so it cannot take memory the plan did not give it."
    ),
)
async def the_model_server_runs_under_the_limit_this_install_costed(h: Harness) -> None:
    from brain.ops.model_server import ModelServerError, effective_limit_mib, read_config
    from brain.ops.wiring import component

    seen = await _reported(h)
    name = component("inference-server").name
    one = seen.get(name)
    if one is None or (one.state, one.health) != ("running", "healthy"):
        raise CheckFailedError(THE_MODEL_SERVER_IS_NOT_RUNNING)
    try:
        wanted = effective_limit_mib(read_config())
    except ModelServerError as error:
        raise CheckFailedError(THE_SETTINGS_CANNOT_BE_READ) from error
    log.info("acceptance.model_server_limit", costed_mib=wanted, running_mib=one.limit_mib)
    if one.limit_mib != wanted:
        raise CheckFailedError(THE_MODEL_SERVER_IS_NOT_HELD_TO_ITS_LIMIT)


@check(
    leaves=("M7.3.3",),
    sentence=(
        "The model server this install has switched on says, from the worker, that every part "
        "this install chose has its weights and its libraries and that it runs those parts and "
        "no others, without loading any of them."
    ),
)
async def the_model_server_reports_ready_for_exactly_the_parts_chosen(h: Harness) -> None:
    import httpx

    from brain.knowledge.embed_policy import embedding_endpoint
    from brain.ops.model_server import ModelServerError, read_config
    from brain.ops.overlays import BY_NAME, switched_on_here

    if BY_NAME["modelserver"] not in switched_on_here():
        raise CheckNotRunError(NO_MODEL_SERVER_HERE)
    try:
        chosen = {one.value for one in read_config().parts}
    except ModelServerError as error:
        raise CheckFailedError(THE_SETTINGS_CANNOT_BE_READ) from error
    try:
        async with httpx.AsyncClient(timeout=READY_TIMEOUT_SECONDS) as client:
            answer = await client.get(f"{embedding_endpoint().rstrip('/')}/ready")
            body = answer.json()
            status = answer.status_code
    except (httpx.HTTPError, ValueError) as error:
        raise CheckFailedError(THE_MODEL_SERVER_DID_NOT_ANSWER) from error
    if not isinstance(body, dict):
        raise CheckFailedError(THE_MODEL_SERVER_DID_NOT_ANSWER)
    gaps = body.get("gaps")
    log.info(
        "acceptance.model_server_ready",
        status=status,
        gaps=[str(one) for one in gaps] if isinstance(gaps, list) else [],
    )
    if status != 200 or body.get("ready") is not True:
        raise CheckFailedError(A_PART_IS_NOT_READY)
    parts = body.get("parts")
    if not isinstance(parts, list) or {str(one) for one in parts} != chosen:
        raise CheckFailedError(IT_RUNS_OTHER_PARTS_THAN_WERE_CHOSEN)


# ------------------------------------------------------------------------ the document parts
#: The words a check puts on a page and looks for in what the parts read back. One word, lower case,
#: because a recogniser gets the case of a printed word wrong far more often than the letters.
PROBE_WORD: Final = "acceptance"

#: Said where the server runs and the install chose no part that is sent a document.
NO_DOCUMENT_PART_HERE: Final = (
    "this install's model server has no part chosen that reads a document: INSTALL_MODEL_PARTS "
    "names none of layout, ocr or tika"
)

#: Said where the part could not be asked, or did not answer.
A_DOCUMENT_PART_DID_NOT_ANSWER: Final = (
    "a part of the model server this install chose did not answer when sent a one-page document, "
    "so it was not read; the part may still be loading, and the next run asks again"
)

#: Said where a part answered and read nothing of a page that has one printed line on it.
A_DOCUMENT_PART_READ_NOTHING: Final = (
    "a part of the model server this install chose was sent a page with one line of printed text "
    "on it and did not give that line back"
)

#: Said where a part refused a one-page document.
A_DOCUMENT_PART_REFUSED_THE_PAGE: Final = (
    "a part of the model server this install chose refused a one-page document that is a valid "
    "PDF with its text printed on it"
)


def pages_of_text(*lines: str) -> bytes:
    """A valid PDF with one line of text printed on each page in a standard font, and a blank page
    for each empty line.

    Written byte by byte so that it needs no library, which matters for the same reason the check
    needs a real page: the readers it is given to are the ones that decide what a page is. A line
    must not contain a parenthesis or a backslash, which a PDF string would need escaped.
    """
    font = 3 + 2 * len(lines)
    kids = " ".join(f"{3 + 2 * index} 0 R" for index in range(len(lines)))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(lines)} >>".encode("ascii"),
    ]
    for index, words in enumerate(lines):
        stream = f"BT /F1 36 Tf 40 60 Td ({words}) Tj ET".encode("latin-1") if words else b""
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 120] "
                f"/Contents {4 + 2 * index} 0 R /Resources << /Font << /F1 {font} 0 R >> >> >>"
            ).encode("ascii")
        )
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii") + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)


def a_page_of_text(words: str) -> bytes:
    """A valid one-page PDF with `words` printed on it and nothing else."""
    return pages_of_text(words)


def _document_parts_here() -> frozenset[Part]:
    """The parts this install runs that are sent a document, or not run."""
    from brain.ops.model_server import DOCUMENT_PARTS, ModelServerError, read_config
    from brain.ops.overlays import BY_NAME, switched_on_here

    if BY_NAME["modelserver"] not in switched_on_here():
        raise CheckNotRunError(NO_MODEL_SERVER_HERE)
    try:
        chosen = read_config().parts
    except ModelServerError as error:
        raise CheckFailedError(THE_SETTINGS_CANNOT_BE_READ) from error
    parts = frozenset(part for part in chosen if part in DOCUMENT_PARTS)
    if not parts:
        raise CheckNotRunError(NO_DOCUMENT_PART_HERE)
    return parts


@check(
    leaves=("M7.2.1", "M7.2.3", "M7.2.4"),
    sentence=(
        "Each part of the model server this install chose that reads a document is sent a "
        "one-page PDF with a line of text printed on it, and gives that line back through the "
        "product's own reader for it, the layout part as a block, the scanned-page part as a "
        "recognised page and the general reader as a paragraph."
    ),
)
async def each_document_part_chosen_reads_a_printed_line(h: Harness) -> None:
    import asyncio

    from brain.knowledge.ingest import MediaType, admit_upload
    from brain.knowledge.model_server_parsers import ServerExtract, ServerLayout, ServerOcr
    from brain.knowledge.parse_layout import LayoutParser
    from brain.knowledge.parse_ocr import OcrParser
    from brain.knowledge.scanning import Parser, ParseRefusal, ReadWithGaps, scan_for_parsing
    from brain.knowledge.text_path import StructuralCheck
    from brain.ops.model_server import Part
    from brain.ops.model_server_client import make_model_server_client

    parts = _document_parts_here()
    page = a_page_of_text(f"{PROBE_WORD.capitalize()} check page")
    upload = admit_upload(
        filename="acceptance.pdf", declared_type=MediaType.PDF.value, content=page
    )
    content = scan_for_parsing(upload, page, scanner=StructuralCheck())
    server = make_model_server_client()
    parsers: dict[Part, Parser] = {
        Part.LAYOUT: LayoutParser(service=ServerLayout(server)),
        Part.OCR: OcrParser(engine=ServerOcr(server)),
        Part.TIKA: ServerExtract(server),
    }
    for part in (Part.LAYOUT, Part.OCR, Part.TIKA):
        if part not in parts:
            continue
        outcome = await asyncio.to_thread(parsers[part].parse, content)
        if isinstance(outcome, ParseRefusal):
            log.info("acceptance.document_part_refused", part=part.value, cause=outcome.cause.value)
            if outcome.cause.value in ("parser_unavailable", "timed_out"):
                raise CheckFailedError(A_DOCUMENT_PART_DID_NOT_ANSWER)
            raise CheckFailedError(A_DOCUMENT_PART_REFUSED_THE_PAGE)
        blocks = outcome.blocks if isinstance(outcome, ReadWithGaps) else tuple(outcome)
        if PROBE_WORD not in " ".join(block.text for block in blocks).casefold():
            raise CheckFailedError(A_DOCUMENT_PART_READ_NOTHING)


#: Said where the ring holds no measurement of a part yet.
NO_PEAK_HAS_BEEN_RECORDED_YET: Final = (
    "the model server has not recorded the memory of any batch or document yet, so there is no "
    "measured peak to hold against the limit"
)

#: Said where a recorded peak is larger than the limit the plan gave.
A_PEAK_WAS_LARGER_THAN_THE_LIMIT: Final = (
    "a memory peak the model server recorded for a part is larger than the limit this install's "
    "settings cost; the model server screen gives the figures and the limit they suggest"
)


@check(
    leaves=("M7.7.11",),
    sentence=(
        "Every memory peak the model server has recorded for the work it did on this install, "
        "counting what cannot be given back, is at or under the limit the install's settings "
        "cost, so the largest document it has read so far was read within the memory it was given."
    ),
)
async def no_recorded_model_server_peak_exceeds_its_costed_limit(h: Harness) -> None:
    from brain.ops.model_server import ModelServerError, effective_limit_mib, read_config
    from brain.ops.model_server_peaks import summarise
    from brain.ops.model_server_store import recorded_peaks
    from brain.ops.overlays import BY_NAME, switched_on_here

    if BY_NAME["modelserver"] not in switched_on_here():
        raise CheckNotRunError(NO_MODEL_SERVER_HERE)
    try:
        limit = effective_limit_mib(read_config())
    except ModelServerError as error:
        raise CheckFailedError(THE_SETTINGS_CANNOT_BE_READ) from error
    async with h.sessions() as session:
        rows = await recorded_peaks(session)
    if not rows:
        raise CheckNotRunError(NO_PEAK_HAS_BEEN_RECORDED_YET)
    for summary in summarise(rows):
        log.info(
            "acceptance.model_server_peak",
            part=summary.part.value,
            largest_anon_mib=summary.largest_anon_mib,
            costed_mib=limit,
        )
        if summary.largest_anon_mib > limit:
            raise CheckFailedError(A_PEAK_WAS_LARGER_THAN_THE_LIMIT)


# ------------------------------------------------------------------------ a photograph at the door
@check(
    leaves=("M7.2.4",),
    sentence=(
        "The structural check clears a PNG and a JPEG whose headers claim an ordinary page and "
        "refuses one whose header claims more pixels than any page has and one whose header "
        "cannot be read, so a photograph is judged before a library decodes it."
    ),
)
async def a_photograph_is_judged_by_what_its_header_claims(h: Harness) -> None:
    from brain.knowledge.ingest import ScanVerdict
    from brain.knowledge.text_path import StructuralCheck

    scan = StructuralCheck().scan

    def png(width: int, height: int) -> bytes:
        size = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes((8, 2, 0, 0, 0))
        return (
            bytes((0x89,))
            + b"PNG\r\n"
            + bytes((0x1A, 0x0A))
            + bytes((0, 0, 0, 13))
            + (b"IHDR" + size + bytes(4))
        )

    def jpeg(width: int, height: int) -> bytes:
        app = bytes((0xFF, 0xE0, 0, 16)) + b"JFIF" + bytes(10)
        frame = bytes((0xFF, 0xC0, 0, 17, 8)) + height.to_bytes(2, "big") + width.to_bytes(2, "big")
        return bytes((0xFF, 0xD8)) + app + frame + bytes(10)

    ordinary = (2480, 3508)
    # Sixty thousand by sixty thousand: past any page by a factor of thirty-six, and the widest a
    # JPEG's two-byte header can say, so the figure is the same for both formats and does not move
    # with the bound it is held against.
    over = (60_000, 60_000)
    for make in (png, jpeg):
        if scan(make(*ordinary)).verdict is not ScanVerdict.CLEAN:
            raise CheckFailedError("a photograph of an ordinary page was refused at the door")
        if scan(make(*over)).verdict is ScanVerdict.CLEAN:
            raise CheckFailedError(
                "a photograph claiming more pixels than any page has was cleared"
            )
    if scan(bytes((0x89,)) + b"PNG\r\n" + bytes((0x1A, 0x0A)) + bytes(8)).verdict is (
        ScanVerdict.CLEAN
    ):
        raise CheckFailedError("a photograph whose header cannot be read was cleared")


# ------------------------------------------------------------------------ the revision it holds
#: Said where the install chose the embedding part and has declared no revision for it.
NO_EMBEDDING_REVISION_IS_DECLARED_HERE: Final = (
    "this install has not declared a revision for the embedding weights: "
    "INSTALL_EMBEDDING_REVISION is unset, so nothing is embedded and there is nothing to compare"
)

#: Said where the install has not chosen the embedding part, so there are no weights to hold.
NO_EMBEDDING_PART_HERE: Final = (
    "this install's model server does not run the embedding part: INSTALL_MODEL_PARTS does not "
    "name embedding"
)

#: Said where the server states no revision for weights that this install chose.
THE_SERVER_STATES_NO_REVISION: Final = (
    "the model server states no revision for the embedding weights it was chosen to run, which "
    "means the weights file is not in its volume or the release's step has not fetched it"
)

#: Said where the revision declared is not the one the server holds.
THE_DECLARED_REVISION_IS_NOT_THE_HELD_ONE: Final = (
    "the embedding revision this install declares is not the one the model server holds, so every "
    "vector it returns is refused; the model server screen gives the revision it holds"
)


@check(
    leaves=("M7.3.3",),
    sentence=(
        "The embedding revision this install declares is the revision the model server says its "
        "embedding weights have, so a vector it returns is recorded under the weights that made it "
        "and is not refused for being made by others."
    ),
)
async def the_declared_embedding_revision_is_the_one_the_server_holds(h: Harness) -> None:
    from brain.knowledge.embed_policy import embedding_revision
    from brain.knowledge.embedding import EmbeddingError
    from brain.ops.model_server import ModelServerError, Part, read_config
    from brain.ops.model_server_client import held_embedding_revision, server_readiness
    from brain.ops.overlays import BY_NAME, switched_on_here

    if BY_NAME["modelserver"] not in switched_on_here():
        raise CheckNotRunError(NO_MODEL_SERVER_HERE)
    try:
        chosen = read_config().parts
    except ModelServerError as error:
        raise CheckFailedError(THE_SETTINGS_CANNOT_BE_READ) from error
    if Part.EMBEDDING not in chosen:
        raise CheckNotRunError(NO_EMBEDDING_PART_HERE)
    try:
        declared = embedding_revision()
    except EmbeddingError as error:
        raise CheckFailedError(THE_DECLARED_REVISION_IS_NOT_THE_HELD_ONE) from error
    if declared is None:
        raise CheckNotRunError(NO_EMBEDDING_REVISION_IS_DECLARED_HERE)
    answered = await server_readiness()
    if answered is None:
        raise CheckFailedError(THE_MODEL_SERVER_DID_NOT_ANSWER)
    held = held_embedding_revision(answered[1])
    if held is None:
        raise CheckFailedError(THE_SERVER_STATES_NO_REVISION)
    if held != declared:
        raise CheckFailedError(THE_DECLARED_REVISION_IS_NOT_THE_HELD_ONE)


# ------------------------------------------------------------------------ the entity part
#: A name no pattern describes: three ordinary capitalised words with no connector, the case
#: `brain.ops.pii.GLINER_LABELS` gives for asking a model at all. Invented here, and nobody's.
NAME_NO_PATTERN_DESCRIBES: Final = "Tan Wei Ling"

#: Said where the install did not choose the entity part.
NO_ENTITY_PART_HERE: Final = (
    "this install's model server does not run the entity part: INSTALL_MODEL_PARTS does not name "
    "entities"
)

#: Said where the entity part could not be asked, or did not give a reading.
THE_ENTITY_PART_DID_NOT_ANSWER: Final = (
    "the entity part of the model server this install chose did not give a readable answer to a "
    "sentence with a name in it; it may still be loading, and the next run asks again"
)

#: Said where it answered and the name is still in the text once the scrub has run.
THE_ENTITY_PART_LEFT_THE_NAME: Final = (
    "the entity part of the model server this install chose was sent a sentence with a name no "
    "pattern describes in it, and that name is still in the text after the scrub"
)

#: How long the check waits for the entity part, in seconds: long enough for a cold load of the
#: model, which is the one thing this check may be the first to ask for.
ENTITY_PART_WAIT_SECONDS: Final = 180.0


@check(
    leaves=("M32.2.1.2",),
    sentence=(
        "The entity part of the model server this install chose is sent a sentence with a "
        "three-word name no pattern describes in it, and the name is gone from the text once the "
        "application's own scrub has folded in what the part found."
    ),
)
async def the_entity_part_finds_a_name_no_pattern_describes(h: Harness) -> None:
    import asyncio

    import httpx

    from brain.ops.egress import AnalyserUnavailableError, entities
    from brain.ops.model_server_client import entity_endpoint
    from brain.ops.overlays import BY_NAME, switched_on_here
    from brain.ops.pii import PiiError, detect, merge_detections, scrub

    if BY_NAME["modelserver"] not in switched_on_here():
        raise CheckNotRunError(NO_MODEL_SERVER_HERE)
    address = entity_endpoint()
    if address is None:
        raise CheckNotRunError(NO_ENTITY_PART_HERE)
    text = f"Please send the signed lease to {NAME_NO_PATTERN_DESCRIBES} before Friday."

    def ask() -> str:
        with httpx.Client(follow_redirects=False) as client:
            found = entities(address, client)(text, timeout_seconds=ENTITY_PART_WAIT_SECONDS)
        return scrub(text, merge_detections(detect(text), found))

    try:
        scrubbed = await asyncio.to_thread(ask)
    except (AnalyserUnavailableError, PiiError) as error:
        raise CheckFailedError(THE_ENTITY_PART_DID_NOT_ANSWER) from error
    if any(word in scrubbed for word in NAME_NO_PATTERN_DESCRIBES.split()):
        raise CheckFailedError(THE_ENTITY_PART_LEFT_THE_NAME)


# ------------------------------------------------------------------------ how a passage was read
class _MadeUpServer:
    """A model server for the check: the layout part reads the first page of a two-page PDF and the
    scanned-page part reads the second, with the confidence the check gives it.

    **It is made up, and the check says so in its sentence.** What the check proves is the
    product's own side on this install's own database (the route, the stamping, the chunk rows, the
    table's constraints and the item's notice), and nothing about the parts: that is the checks
    above, which ask the real ones.
    """

    def __init__(self, confidence: float) -> None:
        self.confidence = confidence

    def ask(self, part: object, request: object) -> object:
        from brain.connectors.throttle import CallOutcome
        from brain.ops.model_server import Part
        from brain.ops.model_server_client import Reply

        def block(text: str, page: int) -> dict[str, object]:
            return {"kind": "prose", "text": text, "start": 0, "page": page, "section": ""}

        if part is Part.LAYOUT:
            return Reply(CallOutcome.OK, {"blocks": [block("First page read by layout", 1)]})
        if part is Part.OCR:
            answer = {
                "blocks": [block("Second page read by recognition", 2)],
                "pages": [{"page": 2, "confidence": self.confidence}],
            }
            return Reply(CallOutcome.OK, answer)
        return Reply(CallOutcome.UNAVAILABLE)


#: Said where the rows a document was stored as are not the ones its reading should have made.
A_PASSAGE_WAS_STORED_WITH_THE_WRONG_READING: Final = (
    "a document read by the layout part and the scanned-page part was stored with a path and "
    "engine on its passages other than the ones that read each page"
)

#: Said where an unclear page was stored anyway, or its notice was not.
AN_UNCLEAR_PAGE_WAS_NOT_LEFT_OUT_AND_NAMED: Final = (
    "a scanned page recognised too poorly to trust was stored, or was left out with no notice "
    "naming it on the item"
)


@check(
    leaves=("M7.7.9", "M7.7.10"),
    sentence=(
        "A PDF with a page of text and a page with none, read over answers the check made by "
        "the layout part and the scanned-page part, is stored on this install with each passage "
        "saying which of the two read it, and when the scanned page is too unclear to trust it "
        "is not stored and the item's notice names that page."
    ),
)
async def a_document_read_two_ways_is_stored_passage_by_passage(h: Harness) -> None:
    from sqlalchemy import select

    from brain.knowledge.chunk_store import ingest_document, reach_of
    from brain.knowledge.embed_policy import REVISION_SETTING, REVISION_UNSET
    from brain.knowledge.ingest import MediaType, ParseFailure, admit_upload
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.model_server_parsers import services_for
    from brain.knowledge.search import CHUNK, session_settings
    from brain.knowledge.uploads import ReadUpload, ReceivedUpload, read_for_text_path
    from brain.knowledge.visibility import KnowledgeVisibility
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
    from brain.ops.model_server import Part
    from brain.tables.audit import attributed_to
    from brain.tables.knowledge import KnowledgeItemRow

    await h.found_departments()
    department = "acceptance_a"
    owner = h.principal(department, "reader")
    await h.person(
        owner, department=department, grants=_in(department, *KNOWLEDGE_READS, "admin:knowledge")
    )
    reach = await h.reach(owner)

    async def stored(confidence: float) -> tuple[ReadUpload, list[Any], str | None]:
        body = pages_of_text(f"Acceptance {h.word()} first page", "")
        upload = admit_upload(
            filename="two-ways.pdf", declared_type=MediaType.PDF.value, content=body
        )
        services = services_for((Part.LAYOUT, Part.OCR), _MadeUpServer(confidence))  # type: ignore[arg-type]
        read = await asyncio.to_thread(
            read_for_text_path,
            ReceivedUpload(upload=upload, body=body),
            kind=KnowledgeKind.SOP,
            placement=KnowledgeVisibility.of_department(department, owner_id=owner),
            owner_id=owner,
            services=services,
        )
        if isinstance(read, ParseFailure):
            raise CheckFailedError(A_DOCUMENT_PART_REFUSED_THE_PAGE)

        async def no_queue(job: object) -> object:
            raise CheckFailedError("a document with no declared revision queued an embedding job")

        await ingest_document(
            h.sessions,
            read.item,
            enqueue=no_queue,
            now=h.now,
            env={REVISION_SETTING: REVISION_UNSET},
            blocks=read.blocks,
            attributed=attributed_to(
                actor_id=owner, ent_hash=reach.ent_hash(), trace_id=h.trace_id
            ),
        )
        async with h.sessions() as session:
            held = await reach_of(session, owner, now=h.now)
            if held is None:
                raise CheckFailedError("the owner of a document reached none of it to read back")
            for setting in session_settings(held):
                await session.execute(setting)
            rows = (
                await session.execute(
                    select(CHUNK.c.page, CHUNK.c.parse_path, CHUNK.c.parse_engine)
                    .where(CHUNK.c.document_id == read.item.item_id)
                    .order_by(CHUNK.c.ordinal)
                )
            ).all()
            notice = (
                await session.execute(
                    select(KnowledgeItemRow.parse_notice).where(
                        KnowledgeItemRow.item_id == read.item.item_id
                    )
                )
            ).scalar_one_or_none()
        return read, [tuple(one) for one in rows], notice

    _, clear_rows, clear_notice = await stored(0.95)
    pages_and_paths = [(page, path) for page, path, _ in clear_rows]
    if pages_and_paths != [(1, "layout"), (2, "ocr")] or any(not row[2] for row in clear_rows):
        raise CheckFailedError(A_PASSAGE_WAS_STORED_WITH_THE_WRONG_READING)
    if clear_notice is not None:
        raise CheckFailedError(AN_UNCLEAR_PAGE_WAS_NOT_LEFT_OUT_AND_NAMED)
    _, unclear_rows, unclear_notice = await stored(0.2)
    if [page for page, _, _ in unclear_rows] != [1]:
        raise CheckFailedError(AN_UNCLEAR_PAGE_WAS_NOT_LEFT_OUT_AND_NAMED)
    if not unclear_notice or "Page 2" not in unclear_notice:
        raise CheckFailedError(AN_UNCLEAR_PAGE_WAS_NOT_LEFT_OUT_AND_NAMED)
