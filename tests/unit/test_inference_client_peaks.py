"""What the embedding client does with the server's account of its own memory.

The client is handed a callable that keeps a report, and the rule these tests hold is the one the
module argues: **a statistic is never a reason to lose a vector.** An answer with a report, one
with a report that cannot be used, and an observer that raises are each shown to leave the vectors
as they were. The positive case is first, so a client that never calls its observer is caught.

Task ids: M7.3.3
"""

from __future__ import annotations

from brain.ops.inference_client import InferenceEmbeddingClient
from brain.ops.model_server import Part
from brain.ops.model_server_peaks import REPORT_KEY, PeakReport
from tests.unit.test_inference_client import (
    A_URL,
    FIXED_NOW,
    FakeResponse,
    FakeTransport,
    _answer,
    _batch,
)

REPORT = {
    "model": "qwen3-embedding-0.6b@abc:1024",
    "items": 2,
    "request_bytes": 900,
    "duration_ms": 40,
    "anon_peak_mib": 400,
    "cache_peak_mib": 640,
    "cgroup_limit_mib": 1088,
}


def _client(
    transport: FakeTransport, seen: list[PeakReport] | None, *, raises: bool = False
) -> InferenceEmbeddingClient:
    def observe(report: PeakReport) -> None:
        if raises:
            msg = "the table refused a row"
            raise RuntimeError(msg)
        assert seen is not None
        seen.append(report)

    return InferenceEmbeddingClient(
        transport=transport, url=A_URL, clock=lambda: FIXED_NOW, observer=observe
    )


def _transport(**changed: object) -> tuple[FakeTransport, list[str]]:
    batch = _batch("k_doc.0001", "k_doc.0002")
    payload = {**_answer(batch), REPORT_KEY: REPORT, **changed}
    return FakeTransport(response=FakeResponse(200, payload)), [one.chunk_id for one in batch.units]


def test_the_servers_report_for_a_batch_reaches_whoever_keeps_it_as_the_embedding_part() -> None:
    """The report is read from the answer, attributed to the embedding part (the caller's knowledge
    and not the server's claim), and handed over once, and the vectors are the ones the server sent.

    Delete this and nothing a server measures is ever kept, and the limit is never tuned."""
    transport, ids = _transport()
    seen: list[PeakReport] = []

    vectors = _client(transport, seen).embed(_batch(*ids))

    assert [one.chunk_id for one in vectors] == ids
    assert len(seen) == 1 and seen[0].part is Part.EMBEDDING
    assert (seen[0].anon_peak_mib, seen[0].cache_peak_mib) == (400, 640)


def test_an_answer_whose_report_cannot_be_used_still_gives_its_vectors_and_calls_nobody() -> None:
    """A malformed report is no report: the vectors are written and the observer is never asked,
    which is also what an older server that sends no block looks like.

    Delete this and a server that garbles its statistics stops an embedding job."""
    transport, ids = _transport(**{REPORT_KEY: {**REPORT, "anon_peak_mib": -4}})
    seen: list[PeakReport] = []

    vectors = _client(transport, seen).embed(_batch(*ids))

    assert len(vectors) == 2 and seen == []


def test_an_observer_that_raises_loses_nothing_of_the_batch() -> None:
    """The table that tunes a limit refused a row, and fifty passages that were embedded stay
    embedded. The failure is logged by its type and swallowed here and nowhere else.

    Delete this and a database hiccup in a statistics write fails the vector write beside it."""
    transport, ids = _transport()

    vectors = _client(transport, None, raises=True).embed(_batch(*ids))

    assert [one.chunk_id for one in vectors] == ids


def test_a_client_with_no_observer_asks_nobody_and_reads_nothing_it_does_not_need() -> None:
    """The default is no observer, so every caller written before this existed is unchanged.

    Delete this and the new field is a required one that breaks them."""
    transport, ids = _transport()
    plain = InferenceEmbeddingClient(transport=transport, url=A_URL, clock=lambda: FIXED_NOW)

    assert plain.observer is None
    assert len(plain.embed(_batch(*ids))) == 2
