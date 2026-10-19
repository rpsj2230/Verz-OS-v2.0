"""The product and the model server over a real socket: each side the real code, the library gone.

Everything between the application's clients and the parts' libraries is the real thing: the
product's `httpx` transport and its two clients, the server's gateway and its supervisor with its
admission check, the framing of a part's answer, the memory block, and the part backends' own
request and answer handling. What is stood in is the library (a stand-in embedder, a stand-in
reader) and the process boundary (a part is held in this process) and the meter (a fixed
measurement, because the test machine has no container's cgroup). So these show that the two
programs agree on a wire neither was tested against the other on, and what the queue is told when a
part cannot be served.

**This is the nearest the repository gets to the server without Docker**, and it is not the server:
nothing here has loaded a model, started a container or crossed a network that is not loopback.

Task ids: M7.2.1, M7.3.3, M7.3.4
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from brain.connectors.throttle import CallOutcome
from brain.knowledge.chunking import BlockKind
from brain.knowledge.embed_policy import (
    COLUMN_DIMENSIONS,
    EmbeddingUnavailable,
    served_embedding_model,
)
from brain.knowledge.embed_queue import EmbeddingBatch, EmbeddingUnit
from brain.knowledge.ingest import MediaType, ScanVerdict, admit_upload
from brain.knowledge.model_server_parsers import ServerLayout
from brain.knowledge.parse_layout import LayoutParser
from brain.knowledge.scanning import ParsedDocument, ScanReport, parse_scanned, scan_for_parsing
from brain.ops.inference import InferenceRefused
from brain.ops.inference_client import InferenceEmbeddingClient, embed_url, http_transport
from brain.ops.model_server_client import ModelServerClient
from brain.ops.model_server_peaks import PeakReport
from inference_server import gateway, meter, supervisor
from inference_server.parts import embedding, layout
from inference_server.worker import Answer
from tests.fixtures.documents import a_pdf
from tests.unit.test_inference_server import server_config

REVISION = "abc123def456"


class _Clean:
    def scan(self, content: bytes) -> ScanReport:
        return ScanReport(verdict=ScanVerdict.CLEAN, scanner="fake-av")


class InProcess:
    """A part held in this process, speaking the frame protocol's envelope without the pipes."""

    def __init__(self, backend: Any, hold: threading.Event | None = None) -> None:
        self.backend = backend
        self.hold = hold
        self.stopped = False

    def start(self) -> str:
        return str(self.backend.label)

    def call(self, body: bytes) -> bytes:
        if self.hold is not None:
            self.hold.wait(timeout=5)
        answer: Answer = self.backend.handle(body)
        envelope = {"status": answer.status, "answer": answer.payload, "items": answer.items}
        return json.dumps(envelope).encode("utf-8")

    def stop(self) -> None:
        self.stopped = True


class _Embedder:
    def embed(self, text: str) -> list[float]:
        return [1.0 + index % 5 for index in range(COLUMN_DIMENSIONS)]


class _Reader:
    def read(self, path: Path) -> list[layout.Item]:
        assert path.read_bytes().startswith(b"%PDF")
        return [
            layout.Item("section_header", "Safety", 1),
            layout.Item("text", "Wear a helmet.", 1),
        ]


class _Measure:
    def start(self) -> None:
        return None

    def stop(self) -> meter.Measurement:
        return meter.Measurement(
            anon_peak_mib=410, cache_peak_mib=640, cgroup_limit_mib=1088, duration_ms=30
        )


@dataclasses.dataclass
class Running:
    base: str
    unit: supervisor.Supervisor
    made: dict[str, InProcess]


@contextlib.contextmanager
def serve_with(
    *, available: int | None = 100_000, hold: threading.Event | None = None, **changed: str
) -> Iterator[Running]:
    config = dataclasses.replace(
        server_config(
            INFERENCE_PARTS="embedding,layout",
            INFERENCE_NEED_LAYOUT_MIB="1288",
            **changed,
        ),
        port=0,
    )
    made: dict[str, InProcess] = {}

    def spawn(part: str) -> InProcess:
        backend: Any
        if part == "embedding":
            backend = embedding.EmbeddingBackend(
                _Embedder(), name="qwen3-embedding-0.6b", revision=REVISION, dimensions=1024
            )
        else:
            backend = layout.LayoutBackend(_Reader())
        made[part] = InProcess(backend, hold)
        return made[part]

    unit = supervisor.Supervisor(
        config,
        spawn=spawn,
        available=lambda: available,
        meter=_Measure,  # type: ignore[arg-type]
    )
    server = gateway.serve(config, unit)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Running(f"http://127.0.0.1:{server.server_address[1]}", unit, made)
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def running() -> Iterator[Running]:
    with serve_with() as running:
        yield running


def _batch(*ids: str) -> EmbeddingBatch:
    return EmbeddingBatch(
        model=served_embedding_model(revision=REVISION),
        units=tuple(EmbeddingUnit(chunk_id=one, text=f"text for {one}") for one in ids),
    )


def _embedding_client(base: str, seen: list[PeakReport] | None = None) -> InferenceEmbeddingClient:
    return InferenceEmbeddingClient(
        transport=http_transport(),
        url=embed_url(base),
        timeout_seconds=10.0,
        observer=None if seen is None else seen.append,
    )


# ------------------------------------------------------------------ embedding across the wire
def test_a_batch_is_embedded_across_the_wire_and_the_servers_peak_reaches_the_client(
    running: Running,
) -> None:
    """The product's embedding client, over real HTTP, to the real gateway and supervisor and the
    real embedding backend: the vectors decode and `writes_for` accepts them, and the memory block
    the supervisor added arrives at the client's observer attributed to the embedding part.

    Delete this and the two programs agree on a wire only in tests written against one side."""
    seen: list[PeakReport] = []

    embedded = _embedding_client(running.base, seen).embed(_batch("k_doc.0001", "k_doc.0002"))

    assert [one.chunk_id for one in embedded] == ["k_doc.0001", "k_doc.0002"]
    assert all(len(one.vector.values) == COLUMN_DIMENSIONS for one in embedded)
    [report] = seen
    assert (report.part.value, report.anon_peak_mib, report.cache_peak_mib) == (
        "embedding",
        410,
        640,
    )
    assert report.items == 2 and report.cgroup_limit_mib == 1088
    assert running.unit.loaded == "embedding"


def test_a_host_with_no_room_for_the_part_is_an_outage_the_queue_retries() -> None:
    """With the host unable to give what the part cannot return, the server answers 503 and loads
    nothing, and the product's client raises the outage class the queue re-drives, never the
    refusal class that reads as this system having sent something malformed.

    Delete this and a part the host cannot hold ends embedding jobs instead of waiting."""
    with serve_with(available=10) as running:
        with pytest.raises(EmbeddingUnavailable):
            _embedding_client(running.base).embed(_batch("k_doc.0001"))

        assert running.made == {} and running.unit.loaded is None


def test_a_server_busy_with_another_request_is_an_outage_and_not_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """While one request is being served a second waits for the lock, and past the wait it is told
    busy with a 503: an outage, so the second job is re-driven and nothing is lost.

    Delete this and a busy server ends a job."""
    monkeypatch.setattr(supervisor, "QUEUE_WAIT_SECONDS", 0.2)
    release = threading.Event()
    with serve_with(hold=release) as running:
        first: list[Any] = []

        def slow() -> None:
            first.append(_embedding_client(running.base).embed(_batch("k_doc.0001")))

        worker = threading.Thread(target=slow)
        worker.start()
        while running.unit.loaded is None:
            threading.Event().wait(0.01)
        try:
            with pytest.raises(EmbeddingUnavailable):
                _embedding_client(running.base).embed(_batch("k_doc.0002"))
        finally:
            release.set()
            worker.join(timeout=10)
        assert len(first) == 1


def test_a_request_over_the_ceiling_is_refused_and_is_the_contract_failing_not_an_outage() -> None:
    """A body over what the install's server accepts is a 413 without a byte read, which the
    product reads as a rejected request: a refusal, because sending it again changes nothing.

    Delete this and an oversize request is retried for ever as though the server were unwell."""
    with (
        serve_with(INFERENCE_MAX_REQUEST_BYTES="50") as running,
        pytest.raises(InferenceRefused),
    ):
        _embedding_client(running.base).embed(_batch("k_doc.0001"))


# ------------------------------------------------------------------ a document across the wire
def test_a_document_is_read_across_the_wire_and_decoded_by_the_guard_that_protects_the_corpus(
    running: Running,
) -> None:
    """The product's layout reader, over real HTTP: the request it writes carries a document the
    server writes to a file for its reader and deletes, the blocks come back laid out where the
    application's own decoder demands, and the gate returns a parsed document.

    Delete this and the document path is tested only in two halves that were never joined."""
    body = a_pdf("Quarterly report")
    upload = admit_upload(filename="q.pdf", declared_type=MediaType.PDF.value, content=body)
    content = scan_for_parsing(upload, body, scanner=_Clean())
    seen: list[PeakReport] = []
    client = ModelServerClient(
        transport=http_transport(),
        base_url=running.base,
        timeout_seconds=10.0,
        observer=seen.append,
    )

    parsed = parse_scanned(content, parser=LayoutParser(service=ServerLayout(client)))

    assert isinstance(parsed, ParsedDocument)
    assert [(block.text, block.kind, block.section) for block in parsed.blocks] == [
        ("Safety", BlockKind.PROSE, "Safety"),
        ("Wear a helmet.", BlockKind.PROSE, "Safety"),
    ]
    assert [(one.part.value, one.items) for one in seen] == [("layout", 2)]


def test_the_server_not_running_a_part_is_a_rejection_and_not_a_document_refused_for_ever() -> None:
    """A part this install did not choose is a 404 from the server, which the document client reads
    as rejected: the outcome is not OK and no block is read, so the route does not index nothing.

    Delete this and a request for a part nobody started reads as an empty document."""
    with serve_with() as running:
        client = ModelServerClient(
            transport=http_transport(), base_url=running.base, timeout_seconds=10.0
        )
        from brain.ops.model_server import Part

        reply = client.ask(Part.OCR, {"document": {}})

        assert reply.outcome is CallOutcome.REJECTED
        assert dict(reply.payload) == {}
