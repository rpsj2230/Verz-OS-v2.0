"""Install acceptance checks for the document leg that waits on a model server.

Layout reading, scanned pages, search by meaning and the names only a model finds all wait on one
service that does not fit beside everything else on the owner's host (needs-rupash 120). That does
not make them unprovable, and it does not make them proved. **Six checks, and each says in its
sentence which half it shows.** What the install can be asked without a model server is asked of
the install: the memory bound on a parse, what the worker prints at start, whether a document's
chunks are embedded in bounded batches and carry the model that made them. What needs the server
itself is either asked of it live and recorded as not run while nobody answers, or shown over a
stand-in the check made, and **a leaf that passes only over a stand-in is held in
`docs/proof-sweep-holds.json`** so a pass here is never read as the server working.

1. **A routed read says which reader read the file.** The product's own `parse_by_route` over a
   layout reader, a text fallback and an OCR engine, each made up for the check: a table read by the
   layout path stays one table with its page and no other path is asked; an outage never moves a
   document to a weaker path; a file the layout reader cannot open is read by the fallback and says
   so; a scan under the confidence floor is refused as illegible rather than indexed. Held: M7.2.1,
   M7.2.3 and M7.2.4 are the model server and an extractor, and nothing in this check is either.
2. **The parse worker refuses a file over its budget before opening it.** The sizing the product
   declares for the container that parses, read as it stands, with the three ways it is shown to
   fire. It writes nothing and asks no model, so it is proof of the declaration and not of a kill.
3. **A document is embedded in bounded batches and every vector names its model.** A document is
   added in the reserved department, the product's own ingest builds the job, and the product's own
   worker function reads the chunks, sends them through the product's own client to a transport
   that answers as the server's contract says, and writes the vectors. Held: the transport is made
   up. This is the half of M7.3.4 that does not depend on the server; M7.3.3 is **not** named here.
4. **The install's own inference server embeds a sentence in the recorded model.** The one check
   that names M7.3.3, and it asks the real server: with no revision declared or nothing answering it
   is recorded as not run, so the leaf can only close when the server really embedded something.
5. **The worker says at start what the door admits beyond what the parse service takes.** The
   advisory the worker prints once an install declares a model server, the arithmetic behind it and
   its silence on an install with none. Held: the half of M7.7.11 that parses the largest upload in
   the layout service's container needs the server and the owner's choice of limit (item 119).
6. **A name only the model finds is scrubbed, and the model's absence costs nothing.** The wire
   contract and the merge, over a response the check made: the model's span is added to what the
   patterns found, never taken from it; a score under the declared threshold is dropped; a span
   naming a label nobody asked for is refused. Held: M32.2.1.2 is GLiNER finding names, not a
   check handing back a span.

**Rejected: naming M7.3.5 and M7.7.8 on check 3.** The rebuild command plans, reports and refuses a
claim that it finished; nothing registers the task a rebuild is carried out by, so no chunk is
re-embedded on a model change. And "answers keep using the previous vectors while a rebuild runs"
is the opposite of what `brain.knowledge.embedding` decided: a corpus holding two models has no
vector leg at all. A check that passed on the first and said nothing of the second would close a
leaf whose sentence is half false. M7.7.9 and M7.7.10 are not named either: no chunk records its
parser, and the OCR floor is one figure per document rather than per page.

**Rejected: a stand-in server for check 4.** It would pass on every install and prove the one thing
check 3 already shows. Not run is the true answer while no server answers.

Task ids: M7.2.1, M7.2.3, M7.2.4, M7.2.6, M7.3.3, M7.3.4, M7.7.11, M32.2.1.2
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _upload
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from brain.knowledge.chunking import Block
    from brain.knowledge.scanning import ScannedContent, ScanReport

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 745

A: Final = "acceptance_a"

# ------------------------------------------------------------------ written-down reasons
#: What the made-up readers, engine and transport of the stand-in checks hold, and what they
#: never do.
THE_STAND_INS_HOLD_WORDS_THE_CHECK_MADE: Final = (
    "The layout reader, the fallback, the OCR engine and the embedding transport of these checks "
    "are made in memory for them. Nothing is sent to a socket and no document of the install's is "
    "read, so a pass shows the product's own routing, refusals and writes behave as written and "
    "shows nothing about a model server of the owner's."
)

#: The reason check 4 is recorded as not run when the install declares no model server.
NO_EMBEDDING_REVISION_IS_DECLARED: Final = (
    "this install declares no embedding revision, so it has no model server to embed a sentence "
    "with"
)

#: The reason check 4 is recorded as not run when a declared server does not answer.
NO_EMBEDDING_SERVER_ANSWERED: Final = (
    "no model server answered at the address this install names, so no sentence could be embedded"
)

#: The words a request to the model server may never carry, restated here so a field added to the
#: product's request fails this check rather than moving with the product.
WORDS_NO_REQUEST_MAY_CARRY: Final = ("department", "owner", "visibility", "reach", "principal")


# ---------------------------------------------------------------- the made-up readers
@dataclass
class _Reader:
    """A parser made for a check: answers what it was told to and counts how often it was asked."""

    outcome: Any
    calls: int = 0

    def parse(self, content: ScannedContent) -> Any:
        self.calls += 1
        return self.outcome


@dataclass
class _Layout:
    """A layout service made for a check, answering a scripted outcome and payload."""

    outcome: Any
    payload: Mapping[str, object] = field(default_factory=dict)
    calls: int = 0

    def layout(self, content: ScannedContent) -> Any:
        from brain.knowledge.parse_layout import LayoutResponse

        self.calls += 1
        return LayoutResponse(outcome=self.outcome, payload=self.payload)


@dataclass
class _Engine:
    """An OCR engine made for a check, reporting one reading and counting how often it was asked."""

    outcome: Any
    calls: int = 0

    def read(self, content: ScannedContent) -> Any:
        self.calls += 1
        return self.outcome


class _Cleared:
    """A scanner made for a check that reports every buffer clean."""

    def scan(self, content: bytes) -> ScanReport:
        from brain.knowledge.ingest import ScanVerdict
        from brain.knowledge.scanning import ScanReport

        return ScanReport(verdict=ScanVerdict.CLEAN, scanner="acceptance-stand-in")


def _cleared_pdf() -> ScannedContent:
    """A tiny PDF admitted and scanned the way the parse worker receives one."""
    from brain.knowledge.ingest import MediaType, admit_upload
    from brain.knowledge.scanning import scan_for_parsing

    body = b"%PDF-1.7\n1 0 obj\n<< >>\nendobj\n"
    admitted = admit_upload(
        filename="acceptance.pdf", declared_type=MediaType.PDF.value, content=body
    )
    return scan_for_parsing(admitted, body, scanner=_Cleared())


def _prose(text: str, *, page: int | None = None) -> Block:
    from brain.knowledge.chunking import Block, BlockKind

    return Block(kind=BlockKind.PROSE, text=text, start=0, page=page)


# ------------------------------------------------------------------ 1. a routed read
@check(
    leaves=("M7.2.1", "M7.2.3", "M7.2.4"),
    sentence=(
        "The product's route over a layout reader, a text fallback and an OCR engine (each made up "
        "for the check) keeps a table whole with its page, never moves a document to a weaker "
        "reader on an outage, records the fallback when the layout reader cannot open a file, and "
        "refuses a scan under the confidence floor as illegible."
    ),
)
async def a_routed_read_records_its_path_and_an_outage_never_falls_back(h: Harness) -> None:
    from brain.connectors.throttle import CallOutcome
    from brain.knowledge.chunking import BlockKind
    from brain.knowledge.ingest import IngestRefused, ParseCause, ParseFailure
    from brain.knowledge.parse_layout import (
        BLOCKS_KEY,
        REFUSAL_KEY,
        LayoutParser,
        layout_provenance,
    )
    from brain.knowledge.parse_ocr import (
        OCR_FLOOR_CONFIDENCE,
        OcrParser,
        OcrReading,
        ocr_provenance,
    )
    from brain.knowledge.parse_paths import (
        AttributedParse,
        ParsePath,
        ParseProvenance,
        RoutedParser,
        parse_by_route,
        route_refusals,
    )
    from brain.knowledge.scanning import ParseRefusal, ParseStage

    table = "| item | amount |\n| a | 1 |"

    def read(layout: _Layout, fallback: _Reader, engine: _Engine) -> Any:
        route = (
            RoutedParser(provenance=layout_provenance(), parser=LayoutParser(service=layout)),
            RoutedParser(
                provenance=ParseProvenance(path=ParsePath.FALLBACK, engine="acceptance-text"),
                parser=fallback,
            ),
            RoutedParser(provenance=ocr_provenance(), parser=OcrParser(engine=engine)),
        )
        return parse_by_route(_cleared_pdf(), route=route)

    def refused(cause: ParseCause, stage: ParseStage) -> dict[str, object]:
        return {REFUSAL_KEY: {"cause": cause.value, "stage": stage.value}}

    prose = [_prose("the same table read as prose")]
    sure = OcrReading(blocks=(_prose("recognised words"),), confidence=0.99)

    # The layout reader answers: one table, whole, on its page, and nobody else is asked.
    layout = _Layout(
        CallOutcome.OK,
        {BLOCKS_KEY: [{"kind": BlockKind.TABLE.value, "text": table, "start": 0, "page": 2}]},
    )
    fallback, engine = _Reader(prose), _Engine(sure)
    won = read(layout, fallback, engine)
    if not isinstance(won, AttributedParse) or won.provenance.path is not ParsePath.LAYOUT:
        raise CheckFailedError(
            "a document the layout reader could read was not recorded as read by it"
        )
    first = won.blocks[0]
    if first.kind is not BlockKind.TABLE or first.page != 2 or first.text != table:
        raise CheckFailedError("a table read by the layout path did not stay one table on its page")
    if won.fell_back or fallback.calls or engine.calls:
        raise CheckFailedError("a weaker reader was asked after the layout reader had answered")

    # The layout service does not answer: the document waits, and no weaker reader is asked.
    fallback, engine = _Reader(prose), _Engine(sure)
    waiting = read(_Layout(CallOutcome.UNAVAILABLE), fallback, engine)
    if not isinstance(waiting, ParseFailure) or waiting.cause is not ParseCause.PARSER_UNAVAILABLE:
        raise CheckFailedError("an outage at the layout service was not reported as an outage")
    if not waiting.is_retryable or fallback.calls or engine.calls:
        raise CheckFailedError("an outage moved a document to a weaker reader or was not retryable")

    # The layout reader opened the file and does not handle it: the fallback reads it, and says so.
    fallback, engine = _Reader(prose), _Engine(sure)
    fell = read(
        _Layout(CallOutcome.OK, refused(ParseCause.UNSUPPORTED, ParseStage.LAYOUT)),
        fallback,
        engine,
    )
    if not isinstance(fell, AttributedParse) or fell.provenance.path is not ParsePath.FALLBACK:
        raise CheckFailedError(
            "a file the layout reader could not open was not read by the fallback"
        )
    if (
        not fell.fell_back
        or fell.refused[0].provenance.path is not ParsePath.LAYOUT
        or engine.calls
    ):
        raise CheckFailedError("a fallback read did not record the path it displaced")

    # Neither text reader finds a text layer: OCR reads it, last, and records itself.
    no_text = ParseRefusal(cause=ParseCause.NO_TEXT_LAYER, stage=ParseStage.TEXT)
    gone = refused(ParseCause.NO_TEXT_LAYER, ParseStage.LAYOUT)
    scanned = read(_Layout(CallOutcome.OK, gone), _Reader(no_text), _Engine(sure))
    if not isinstance(scanned, AttributedParse) or scanned.provenance.path is not ParsePath.OCR:
        raise CheckFailedError("a scanned file with no text layer was not read by the OCR path")
    if len(scanned.refused) != 2:
        raise CheckFailedError("an OCR read did not record the two paths it came after")

    # A reading under the floor is refused as illegible and never indexed.
    unsure = OcrReading(blocks=(_prose("garbled"),), confidence=OCR_FLOOR_CONFIDENCE / 2)
    lost = read(_Layout(CallOutcome.OK, gone), _Reader(no_text), _Engine(unsure))
    if not isinstance(lost, ParseFailure) or lost.cause is not ParseCause.ILLEGIBLE:
        raise CheckFailedError(
            "a scan under the confidence floor was indexed or not called illegible"
        )

    # A route in the wrong order is refused before a byte is parsed.
    wrong = (
        RoutedParser(provenance=ocr_provenance(), parser=OcrParser(engine=_Engine(sure))),
        RoutedParser(
            provenance=layout_provenance(), parser=LayoutParser(service=_Layout(CallOutcome.OK))
        ),
    )
    if not route_refusals(wrong):
        raise CheckFailedError("a route with OCR ahead of the layout reader was not refused")
    try:
        parse_by_route(_cleared_pdf(), route=wrong)
    except IngestRefused:
        pass
    else:
        raise CheckFailedError("a route in the wrong order was run")


# ------------------------------------------------------------------ 2. the parse worker's bound
@check(
    leaves=("M7.2.6",),
    sentence=(
        "The container that parses is sized with a reserve under its limit and one parse at a "
        "time, holds the largest file the door admits, and is refused as mis-sized when given a "
        "second slot or no reserve; a file over the budget is refused before the parser is opened "
        "and one within it is parsed."
    ),
)
async def the_parse_worker_refuses_an_oversize_file_before_opening_it(h: Harness) -> None:
    from brain.gate.context import TrafficClass
    from brain.knowledge.ingest import ParseCause, ParseFailure
    from brain.knowledge.parse_budget import (
        MIB,
        PARSE_WORKER_COMPONENT,
        PARSES_AT_ONCE,
        declared_cost_bytes,
        parse_budget_bytes,
        parse_worker_gaps,
    )
    from brain.knowledge.scanning import ParsedDocument, ParseStage, parse_scanned
    from brain.ops.wiring import component

    limit_mib = component(PARSE_WORKER_COMPONENT).memory_mib
    budget = parse_budget_bytes()
    if not 0 < budget < limit_mib * MIB:
        raise CheckFailedError("the parse budget is not strictly inside the container's limit")
    one_slot = {TrafficClass.SYSTEM: PARSES_AT_ONCE}
    if parse_worker_gaps(one_slot) != ():
        raise CheckFailedError(
            "the container that parses cannot hold the largest file the door admits"
        )
    if not parse_worker_gaps({TrafficClass.SYSTEM: PARSES_AT_ONCE + 1}):
        raise CheckFailedError("a second parse slot in one container was not refused")
    if not parse_worker_gaps(one_slot, reserve_mib=0):
        raise CheckFailedError("a container with no reserve under its limit was not refused")

    content = _cleared_pdf()
    reader = _Reader([_prose("some words")])
    over = parse_scanned(
        content, parser=reader, budget_bytes=declared_cost_bytes(content.upload) - 1
    )
    if not isinstance(over, ParseFailure) or over.cause is not ParseCause.OUT_OF_MEMORY:
        raise CheckFailedError("a file over the budget was not refused as too large")
    if reader.calls:
        raise CheckFailedError("the parser was opened on a file over its budget")
    if ParseStage.ADMIT.value not in over.detail:
        raise CheckFailedError(
            "a refusal over the budget did not say it came before any parser ran"
        )
    within = parse_scanned(content, parser=reader, budget_bytes=declared_cost_bytes(content.upload))
    if not isinstance(within, ParsedDocument) or not reader.calls:
        raise CheckFailedError("a file inside the budget was not parsed")


# ------------------------------------------------------------------ 3. batches and the model
class _Answer:
    """A response as the inference client reads one: a status and a body."""

    status_code = 200

    def __init__(self, body: object) -> None:
        self._body = body

    def json(self) -> object:
        return self._body


@dataclass
class _Server:
    """A transport made for a check that answers as the server's contract says it does.

    It reads the request the product's client sent, keeps it, and returns one unit-length vector
    per input under the model block the request named. The vector is a function of the text, so
    the same words always get the same direction and nothing in an answer is random.
    """

    sent: list[Mapping[str, Any]] = field(default_factory=list)

    def post(self, url: str, *, json: Any, timeout: float) -> _Answer:
        self.sent.append(json)
        width = int(json["model"]["dimensions"])
        vectors = []
        for one in json["inputs"]:
            seed = int.from_bytes(hashlib.sha256(str(one["text"]).encode()).digest()[:8], "big")
            drawn = random.Random(seed)  # noqa: S311 - a direction for a made-up vector, not a secret
            raw = [drawn.gauss(0.0, 1.0) for _ in range(width)]
            norm = sum(value * value for value in raw) ** 0.5
            vectors.append({"chunk_id": one["chunk_id"], "values": [value / norm for value in raw]})
        return _Answer({"model": json["model"], "vectors": vectors})


@check(
    leaves=("M7.3.4",),
    sentence=(
        "A document added in acceptance_a has its embedding job built by the product's own ingest "
        "as a safe-to-repeat job naming no permission; the worker's function reads its chunks, "
        "sends them in bounded batches through the product's client to a transport the check made, "
        "and every chunk is left holding a vector and the model that made it."
    ),
)
async def a_document_is_embedded_in_batches_each_vector_names_its_model(
    h: Harness,
) -> None:
    from sqlalchemy import select

    from brain.knowledge.chunk_store import ingest_document, reach_of, run_embed_job
    from brain.knowledge.embed_policy import REVISION_SETTING, served_embedding_model
    from brain.knowledge.embed_queue import (
        EMBED_TASK,
        MODEL_ARGUMENT,
        OWNER_ARGUMENT,
        EmbeddingUnit,
        batch_budget_bytes,
        plan_batches,
    )
    from brain.knowledge.embedding import DEFAULT_BATCH_SIZE
    from brain.knowledge.ingest import MediaType, ParseFailure
    from brain.knowledge.search import CHUNK, session_settings
    from brain.ops.acceptance_documents import a_markdown_document
    from brain.ops.inference_client import InferenceEmbeddingClient
    from brain.ops.queue import Redrive
    from brain.tables.audit import attributed_to

    revision = f"acceptance-{h.run}"
    model = served_embedding_model(revision=revision)

    # The batches: more chunks than one request may carry are cut in order, each within the budget.
    units = tuple(
        EmbeddingUnit(chunk_id=f"acceptance.{n:04d}", text=f"passage number {n}")
        for n in range(2 * DEFAULT_BATCH_SIZE + 1)
    )
    batches = plan_batches(units, model=model)
    if len(batches) != 3 or any(len(one.units) > DEFAULT_BATCH_SIZE for one in batches):
        raise CheckFailedError("chunks beyond one request's size were not cut into bounded batches")
    if tuple(unit for one in batches for unit in one.units) != units:
        raise CheckFailedError("cutting chunks into batches changed their order or lost one")
    if any(one.cost_bytes > batch_budget_bytes() for one in batches):
        raise CheckFailedError("a batch was planned over the budget of the slot that runs it")

    # The document, added as an upload is, and its job built by the product's own ingest.
    await h.found_departments()
    owner = h.principal(A, "library")
    await h.person(owner, department=A, grants=_in(A, *KNOWLEDGE_READS, "admin:knowledge"))
    word = h.word()
    read = await _upload(
        h,
        owner,
        filename="Embedding.md",
        declared=MediaType.MARKDOWN.value,
        body=a_markdown_document("Check", word),
    )
    if isinstance(read, ParseFailure):
        raise CheckFailedError("a well-formed document the door accepts could not be read")
    reach = await h.reach(owner)
    queued: list[Any] = []

    async def hold(job: Any) -> None:
        queued.append(job)

    job = await ingest_document(
        h.sessions,
        read.item,
        enqueue=hold,
        now=h.now,
        env={REVISION_SETTING: revision},
        blocks=read.blocks,
        attributed=attributed_to(actor_id=owner, ent_hash=reach.ent_hash(), trace_id=h.trace_id),
    )
    if job is None or queued != [job]:
        raise CheckFailedError("an install with a declared revision queued no embedding job")
    if job.task != EMBED_TASK or job.redrive is not Redrive.SAFE:
        raise CheckFailedError("the embedding job is not the safe-to-repeat embedding task")
    arguments = dict(job.args)
    if set(arguments) != {
        "document_id",
        "first_ordinal",
        "last_ordinal",
        MODEL_ARGUMENT,
        OWNER_ARGUMENT,
    }:
        raise CheckFailedError("the embedding job carries more than a window, a model and an owner")
    if arguments[MODEL_ARGUMENT] != model.identity:
        raise CheckFailedError("the embedding job names a model other than the one declared")

    # The worker's own function, through the product's own client, over the made-up transport.
    server = _Server()
    client = InferenceEmbeddingClient(
        transport=server, url="http://inference.acceptance.invalid/embed"
    )
    done = await run_embed_job(
        document_id=str(arguments["document_id"]),
        first_ordinal=int(arguments["first_ordinal"]),
        last_ordinal=int(arguments["last_ordinal"]),
        model=str(arguments[MODEL_ARGUMENT]),
        owner_id=str(arguments[OWNER_ARGUMENT]),
        sessions=h.sessions,
        service=client,
        revision=revision,
        now=h.now,
    )
    if not done or not server.sent:
        raise CheckFailedError("the worker's embedding function embedded nothing")
    for request in server.sent:
        if set(request) != {"model", "inputs"}:
            raise CheckFailedError(
                "a request to the model server carried more than a model and inputs"
            )
        if len(request["inputs"]) > DEFAULT_BATCH_SIZE:
            raise CheckFailedError(
                "a request to the model server held more chunks than a batch may"
            )
        if any(set(one) != {"chunk_id", "text"} for one in request["inputs"]):
            raise CheckFailedError(
                "an input to the model server carried more than an id and a text"
            )
        wire = str(request).lower()
        if any(word_ in wire for word_ in WORDS_NO_REQUEST_MAY_CARRY):
            raise CheckFailedError("a request to the model server named a permission")

    async with h.sessions() as session:
        held = await reach_of(session, owner, now=h.now)
        if held is None:
            raise CheckFailedError("the owner of a document reached none of it to read back")
        for setting in session_settings(held):
            await session.execute(setting)
        rows = (
            await session.execute(
                select(
                    CHUNK.c.chunk_id, CHUNK.c.embedding_model, CHUNK.c.embedding.is_not(None)
                ).where(CHUNK.c.document_id == read.item.item_id)
            )
        ).all()
    if not rows:
        raise CheckFailedError("a document that was added holds no chunk")
    if any(not has_vector for _, _, has_vector in rows):
        raise CheckFailedError("a chunk was left without the vector the worker wrote")
    if any(identity != model.identity for _, identity, _ in rows):
        raise CheckFailedError("a stored vector did not record the model that made it")


# ------------------------------------------------------------------ 4. the real server
@check(
    leaves=("M7.3.3",),
    sentence=(
        "The inference server this install names embeds one fixed sentence through the product's "
        "own client, and what comes back is one unit-length vector of the column's width under "
        "the model identity the install declared."
    ),
)
async def the_install_s_inference_server_embeds_a_sentence_as_declared(
    h: Harness,
) -> None:
    from brain.knowledge.embed import embed_question
    from brain.knowledge.embed_policy import (
        EmbeddingUnavailable,
        embedding_revision,
        served_embedding_model,
    )
    from brain.knowledge.embedding import EmbeddingError
    from brain.ops.inference_client import make_client

    try:
        revision = embedding_revision()
    except EmbeddingError as exc:
        raise CheckNotRunError(NO_EMBEDDING_REVISION_IS_DECLARED) from exc
    if revision is None:
        raise CheckNotRunError(NO_EMBEDDING_REVISION_IS_DECLARED)
    sentence = f"An acceptance check asks for one vector. {secrets.token_hex(4)}"
    try:
        client = make_client(timeout_seconds=15.0)
        vector = await asyncio.to_thread(
            embed_question, sentence, service=client, revision=revision
        )
    except EmbeddingUnavailable as exc:
        raise CheckNotRunError(NO_EMBEDDING_SERVER_ANSWERED) from exc
    except EmbeddingError as exc:
        raise CheckFailedError(
            "the model server answered with something the product refuses"
        ) from exc
    served = served_embedding_model(revision=revision)
    if vector.model.identity != served.identity:
        raise CheckFailedError("the vector names a model other than the one this install declared")
    if len(vector.values) != served.dimensions:
        raise CheckFailedError("the vector is not the width of the column it would be stored in")


# ------------------------------------------------------------------ 5. what the worker says
@check(
    leaves=("M7.7.11",),
    sentence=(
        "A worker on an install whose model server reads documents prints, at start, that the "
        "largest file the door admits is larger than a request the server is sized to accept, and "
        "prints nothing about it on an install with no model server or one that only embeds; the "
        "arithmetic fires on a ceiling below the file and is silent on one above it."
    ),
)
async def the_worker_says_at_start_what_the_door_admits_beyond_the_server(
    h: Harness,
) -> None:
    from brain.knowledge.embed_policy import REVISION_SETTING
    from brain.knowledge.ingest import ParseCause, ParseFailure
    from brain.knowledge.parse_budget import PARSE_WORKER_COMPONENT
    from brain.knowledge.parse_layout import (
        LayoutParser,
        encoded_size_bytes,
        largest_admissible_bytes,
        layout_request_gaps,
    )
    from brain.knowledge.scanning import parse_scanned
    from brain.ops.model_server import config_from
    from brain.ops.model_server import request_ceiling_bytes as server_request_ceiling
    from brain.ops.worker import advisories, model_server_advisory

    _, raw = largest_admissible_bytes()
    if not layout_request_gaps(ceiling_bytes=encoded_size_bytes(raw) - 1):
        raise CheckFailedError(
            "a request ceiling below the largest file the door admits was not reported"
        )
    if layout_request_gaps(ceiling_bytes=encoded_size_bytes(raw)):
        raise CheckFailedError(
            "a request ceiling that holds the largest file the door admits was reported"
        )
    # The three installs, each read over settings the check supplies and nothing the install saved:
    # one with no model server, one whose server only embeds, and one whose server reads a
    # document and is sized for 25 MB against a door that admits more.
    nothing: dict[str, str] = {}
    if model_server_advisory(None, nothing, nothing) != ():
        raise CheckFailedError("an install with no model server was told about one")
    revision = f"acceptance-{h.run}"
    embeds_only = {REVISION_SETTING: revision, "INSTALL_MODEL_PARTS": "embedding"}
    if model_server_advisory(revision, embeds_only, nothing) != ():
        raise CheckFailedError(
            "an install whose server is sent no document was told about the door"
        )
    declared = {
        REVISION_SETTING: revision,
        "INSTALL_MODEL_PARTS": "layout",
        "INSTALL_MODEL_UPLOAD_MB": "25",
    }
    expected = layout_request_gaps(
        ceiling_bytes=server_request_ceiling(config_from(parts="layout", upload="25"))
    )
    if not expected or model_server_advisory(revision, declared, nothing) != expected:
        raise CheckFailedError(
            "an install whose server reads documents was not told what the door admits beyond it"
        )
    printed = advisories(declared, worker_component=PARSE_WORKER_COMPONENT)
    if set(model_server_advisory(revision, declared)) - set(printed):
        raise CheckFailedError(
            "the worker did not print the finding an install with a model server is owed"
        )

    # A file over the ceiling is refused before the service is asked, as the file's own fault.
    content = _cleared_pdf()
    asked = _Layout(outcome=None)
    over = parse_scanned(content, parser=LayoutParser(service=asked, ceiling_bytes=1))
    if (
        not isinstance(over, ParseFailure)
        or over.cause is not ParseCause.OUT_OF_MEMORY
        or asked.calls
    ):
        raise CheckFailedError("a file over the request ceiling was sent to the parse service")


# ------------------------------------------------------------------ 6. the names only a model finds
@check(
    leaves=("M32.2.1.2",),
    sentence=(
        "Over a response the check made, the entity model's span for a three-word name no pattern "
        "describes is scrubbed beside the pattern-found address, a score under the declared "
        "threshold is dropped, a label nobody asked for is refused, and with no response the "
        "patterns' scrub is exactly what is left."
    ),
)
async def a_name_only_the_model_finds_is_scrubbed_and_its_absence_is_free(
    h: Harness,
) -> None:
    from brain.ops.pii import (
        ENTITY_REQUEST_KEYS,
        ENTITY_SPANS_KEY,
        GLINER_LABELS,
        PiiError,
        detect,
        detect_with_model,
        entity_request,
        scrub,
    )

    given = secrets.choice(("Quenby", "Zorrel", "Haldric", "Mavonne"))
    middle = secrets.choice(("Thistlewick", "Orrelby", "Pendrave", "Valdane"))
    family = secrets.choice(("Brightmoor", "Ashkettle", "Holloway", "Marrowby"))
    name = f"{given} {middle} {family}"
    address = f"{secrets.token_hex(4)}@acceptance.invalid"
    text = f"Thanks from {name}, write to {address} please."
    start = text.index(name)
    span = {
        "label": GLINER_LABELS[0].label,
        "start": start,
        "end": start + len(name),
        "score": 0.95,
    }

    if tuple(entity_request(text)) != ENTITY_REQUEST_KEYS or set(ENTITY_REQUEST_KEYS) != {
        "model",
        "labels",
        "text",
    }:
        raise CheckFailedError(
            "a request to the entity model carried more than a model, labels and text"
        )
    floor = scrub(text, detect(text))
    answered = scrub(text, detect_with_model(text, {ENTITY_SPANS_KEY: [span]}))
    if "[email]" not in answered or address in answered:
        raise CheckFailedError(
            "the address a pattern finds was not scrubbed beside the model's span"
        )
    if any(part in answered for part in (given, middle, family)):
        raise CheckFailedError("a name the model found was left in the scrubbed text")
    if "[person_name]" not in answered:
        raise CheckFailedError("the name the model found was not scrubbed under its own kind")
    if scrub(text, detect_with_model(text, None)) != floor:
        raise CheckFailedError(
            "with no answer from the model the scrub was not exactly the patterns'"
        )
    under = {**span, "score": 0.05}
    if scrub(text, detect_with_model(text, {ENTITY_SPANS_KEY: [under]})) != floor:
        raise CheckFailedError("a span scored under the declared threshold was scrubbed")
    over_the_address = {
        "label": GLINER_LABELS[0].label,
        "start": text.index(address),
        "end": text.index(address) + len(address),
        "score": 0.99,
    }
    merged = scrub(text, detect_with_model(text, {ENTITY_SPANS_KEY: [over_the_address]}))
    if merged != floor:
        raise CheckFailedError("a model span over a pattern's span changed what the pattern found")
    unreadable: tuple[Mapping[str, object], ...] = (
        {ENTITY_SPANS_KEY: [{**span, "label": "organisation"}]},
        {ENTITY_SPANS_KEY: [{**span, "end": len(text) + 1}]},
        {"spans_elsewhere": []},
    )
    for broken in unreadable:
        try:
            detect_with_model(text, broken)
        except PiiError:
            continue
        raise CheckFailedError("an answer the product cannot read was taken as a finding")
