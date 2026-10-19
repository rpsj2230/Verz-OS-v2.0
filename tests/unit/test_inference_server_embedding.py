"""The embedding part of the model server, held against the application that writes its vectors.

The part is judged with a stand-in for the one object that touches llama.cpp, and its answers are
fed to the application's own decoder and to `writes_for`, which refuses the four ways an answer can
disagree with the batch it answers. **Nothing here has loaded a real model or run a real library**,
and the part says so at its head: what is shown is this program's own work, which is the request it
reads, the identity it states, the width and length of what it returns and the revision of the file.

Task ids: M7.3.3, M7.3.4, M7.3.5, M7.7.8
"""

from __future__ import annotations

import json
import math
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from brain.knowledge.embed_policy import COLUMN_DIMENSIONS, served_embedding_model
from brain.knowledge.embed_queue import EmbeddingBatch, EmbeddingUnit, writes_for
from brain.ops import inference as product_wire
from brain.ops.inference import decode_embeddings, embedding_request
from brain.ops.inference_client import jsonable
from inference_server.parts import embedding
from tests.unit.test_inference_server import server_config

NAME = served_embedding_model(revision="abc123def456").name
FILE = server_config().embedding_file


class _Embedder:
    """Answers each text with a vector of the width the test chose, not yet of unit length."""

    def __init__(self, width: int = COLUMN_DIMENSIONS, scale: float = 3.0) -> None:
        self.width = width
        self.scale = scale
        self.texts: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.texts.append(text)
        return [self.scale * (1 + index % 3) for index in range(self.width)]


def _backend(embedder: _Embedder | None = None, revision: str = "abc123def456") -> Any:
    return embedding.EmbeddingBackend(
        embedder or _Embedder(), name=NAME, revision=revision, dimensions=COLUMN_DIMENSIONS
    )


def _batch(revision: str = "abc123def456", *ids: str) -> EmbeddingBatch:
    chosen = ids or ("k_doc.0001", "k_doc.0002")
    return EmbeddingBatch(
        model=served_embedding_model(revision=revision),
        units=tuple(EmbeddingUnit(chunk_id=one, text=f"text for {one}") for one in chosen),
    )


def _request(batch: EmbeddingBatch) -> bytes:
    return json.dumps(jsonable(embedding_request(batch))).encode("utf-8")


# ------------------------------------------------------------------ the wire, held equal
def test_the_wire_the_part_speaks_is_the_one_the_application_writes() -> None:
    """The keys of a request, an input, the model and the answer are read from both programs and
    compared, and the model's name is the one the application declares for the model it serves.

    Delete this and a renamed key is an answer the application refuses as unreadable for every
    batch, and nothing is embedded."""
    assert embedding.REQUEST_KEYS == product_wire.REQUEST_KEYS
    assert embedding.INPUT_KEYS == product_wire.INPUT_KEYS
    assert embedding.MODEL_KEYS == product_wire.MODEL_KEYS
    assert embedding.VECTORS_KEY == product_wire.VECTORS_KEY
    assert embedding.VALUES_KEY == product_wire.VALUES_KEY
    assert served_embedding_model(revision="abc123def456").name == NAME
    assert server_config().embedding_model == NAME


def test_an_answer_is_read_by_the_applications_decoder_and_accepted_for_the_batch_it_answers() -> (
    None
):
    """The producer's answer is fed to the consumer: the application's decoder reads it, and
    `writes_for` accepts it for the batch, which checks the model, the ids, their order and their
    number.

    Delete this and the part is tested only against its own idea of what the application reads."""
    batch = _batch()

    answer = _backend().handle(_request(batch))
    writes = writes_for(batch, decode_embeddings(batch, answer.payload))

    assert answer.status == 200 and answer.items == 2
    assert [write.chunk_id for write in writes] == ["k_doc.0001", "k_doc.0002"]


def test_a_revision_other_than_the_one_the_batch_names_is_refused_by_the_application() -> None:
    """The part states its own identity and not the one it was asked for: a batch asking for
    another revision gets an answer the application refuses as a different model.

    Delete this and the part echoes the request, and vectors from other weights are recorded under
    the revision the install declared."""
    from brain.knowledge.embedding import MixedEmbeddingError

    batch = _batch("abc123def456")
    answer = _backend(revision="fff000fff000").handle(_request(batch))

    with pytest.raises(MixedEmbeddingError):
        writes_for(batch, decode_embeddings(batch, answer.payload))


# ------------------------------------------------------------------ what a vector is
def test_every_vector_is_returned_at_unit_length_and_in_the_order_asked() -> None:
    """A vector scaled by the library is scaled back to length one, and each is under its own
    chunk id.

    Delete this and a search by angle compares vectors of different lengths."""
    answer = _backend().handle(_request(_batch()))

    vectors = answer.payload["vectors"]
    assert isinstance(vectors, list)
    assert [one["chunk_id"] for one in vectors] == ["k_doc.0001", "k_doc.0002"]
    for one in vectors:
        assert math.isclose(sum(v * v for v in one["values"]), 1.0, rel_tol=1e-9)


def test_a_vector_of_the_wrong_width_or_with_no_length_is_a_failure_of_the_part() -> None:
    """The wrong width, and a vector of zeros, raise: an outage the application retries, never a
    vector written.

    Delete this and a model that returned 768 numbers is stored in a column of 1,024."""
    with pytest.raises(ValueError, match="where 1024 is due"):
        _backend(_Embedder(width=768)).handle(_request(_batch()))
    with pytest.raises(ValueError, match="no length"):
        _backend(_Embedder(scale=0.0)).handle(_request(_batch()))


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"inputs": []}',
        b'{"inputs": [{"chunk_id": "", "text": "x"}]}',
        b'{"inputs": [{"chunk_id": "a", "text": "   "}]}',
        b'{"inputs": [{"chunk_id": "a", "text": "x"}, {"chunk_id": "a", "text": "y"}]}',
        b'{"inputs": ["a"]}',
    ],
)
def test_a_request_with_no_text_or_no_chunk_id_is_a_bad_request(body: bytes) -> None:
    """No inputs, a missing or repeated id and an empty text are the application's mistake and
    are refused as such, so nothing is embedded for them.

    Delete this and a blank passage gets a vector, or two vectors share one chunk id."""
    answer = _backend().handle(body)

    assert answer.status == 400


def test_the_texts_are_embedded_one_at_a_time_in_the_order_given() -> None:
    """Each text is its own call, which is the one-passage-at-a-time the memory was sized for.

    Delete this and a list is handed to the library, which holds the cache for all of it."""
    embedder = _Embedder()

    _backend(embedder).handle(_request(_batch()))

    assert embedder.texts == ["text for k_doc.0001", "text for k_doc.0002"]


# ------------------------------------------------------------------ the revision of the file
def _volume(tmp_path: Path, content: bytes = b"weights") -> Path:
    (tmp_path / FILE).write_bytes(content)
    return tmp_path


def test_the_revision_is_the_recorded_digest_while_the_file_is_the_length_it_was() -> None:
    """The record is used and the file is not read: the record names a digest that is not the
    file's, and the revision is the record's.

    Delete this and every load, and every readiness check, hashes a gigabyte."""
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        volume = _volume(Path(directory), b"weights")
        (volume / "fetched.json").write_text(
            json.dumps({FILE: {"sha256": "ab" * 32, "bytes": len(b"weights")}})
        )

        assert embedding.revision_of(volume, FILE) == "abababababab"
        assert embedding.recorded_revision(volume, FILE) == "abababababab"
        # Twelve characters, which the application accepts as a revision and holds as its own.
        assert served_embedding_model(revision=embedding.revision_of(volume, FILE) or "")


def test_a_file_that_is_not_the_length_recorded_is_hashed_and_the_health_check_does_not() -> None:
    """A replaced file (another length than the record) has the revision its bytes give, which is
    a new one; the readiness route's own reading says nothing rather than hash.

    Delete this and a model replaced by hand keeps the old revision, which is the change that has
    no symptom."""
    import hashlib
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        volume = _volume(Path(directory), b"other weights")
        (volume / "fetched.json").write_text(json.dumps({FILE: {"sha256": "ab" * 32, "bytes": 3}}))

        expected = hashlib.sha256(b"other weights").hexdigest()[:12]
        assert embedding.revision_of(volume, FILE) == expected
        assert embedding.recorded_revision(volume, FILE) is None


def test_a_volume_with_no_weights_has_no_revision(tmp_path: Path) -> None:
    """Nothing is made up for a file that is not there.

    Delete this and an empty volume reports a revision, and the install check that compares it with
    the declared one passes for weights nobody fetched."""
    assert embedding.revision_of(tmp_path, FILE) is None
    assert embedding.recorded_revision(tmp_path, FILE) is None


def test_the_readiness_route_states_the_revision_without_hashing(tmp_path: Path) -> None:
    """`/ready` carries the revision of the weights the install chose, from the record.

    Delete this and the install has nowhere to read the value it has to declare."""
    from inference_server import gateway

    (tmp_path / FILE).write_bytes(b"weights")
    (tmp_path / "fetched.json").write_text(
        json.dumps({FILE: {"sha256": "cd" * 32, "bytes": len(b"weights")}})
    )
    config = server_config(INFERENCE_MODEL_DIR=str(tmp_path))
    embeds_only = server_config(INFERENCE_MODEL_DIR=str(tmp_path), INFERENCE_PARTS="ocr")

    assert gateway.revisions_of(config) == {"embedding": "cdcdcdcdcdcd"}
    assert gateway.revisions_of(embeds_only) == {}


# ------------------------------------------------------------- the object that touches the library
def _llama_module(width: int = COLUMN_DIMENSIONS) -> types.ModuleType:
    module = types.ModuleType("llama_cpp")
    module.LLAMA_POOLING_TYPE_LAST = 4  # type: ignore[attr-defined]
    module.created = []  # type: ignore[attr-defined]

    class Llama:
        def __init__(self, **kwargs: Any) -> None:
            module.created.append(kwargs)

        def n_embd(self) -> int:
            return width

        def embed(self, text: str, normalize: bool, truncate: bool) -> Any:
            return [[1.0] * width] if text == "rows" else [1.0] * width

    module.Llama = Llama  # type: ignore[attr-defined]
    return module


def test_the_library_is_asked_for_last_token_pooling_in_a_window_of_a_thousand_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The settings the memory sizing and the model's training depend on are the ones passed: the
    last token pooled, a 1,024-token window, memory-mapped, on the CPU, quiet.

    Delete this and the cache is sized for one window and the library runs another, or the vector
    is pooled by a method the model was not trained for and every distance is wrong."""
    module = _llama_module()
    monkeypatch.setitem(sys.modules, "llama_cpp", module)

    embedder = embedding.LlamaEmbedder(tmp_path / FILE, threads=3)

    [kwargs] = module.created
    assert kwargs["pooling_type"] == 4 and kwargs["embedding"] is True
    assert kwargs["n_ctx"] == embedding.WINDOW_TOKENS == 1024
    assert kwargs["use_mmap"] is True and kwargs["use_mlock"] is False
    assert kwargs["n_gpu_layers"] == 0 and kwargs["n_threads"] == 3
    assert embedder.dimensions == COLUMN_DIMENSIONS
    assert len(embedder.embed("one text")) == COLUMN_DIMENSIONS
    assert len(embedder.embed("rows")) == COLUMN_DIMENSIONS


def test_loading_names_the_part_by_its_file_and_states_the_width_the_library_reports(
    tmp_path: Path,
) -> None:
    """`load` builds the identity from the install's name, the file's revision and the library's
    width, and refuses a volume with no file.

    Delete this and the part states an identity of its own invention."""
    volume = _volume(tmp_path)
    config = server_config(INFERENCE_MODEL_DIR=str(volume))

    class Stub(_Embedder):
        dimensions = COLUMN_DIMENSIONS

    backend = embedding.load(config, embedder=lambda path, threads: Stub())  # type: ignore[arg-type,return-value]
    assert backend.name == NAME and backend.dimensions == COLUMN_DIMENSIONS
    assert backend.label == f"{NAME}@{backend.revision}:{COLUMN_DIMENSIONS}"
    with pytest.raises(RuntimeError, match="not in the volume"):
        embedding.load(server_config(INFERENCE_MODEL_DIR=str(tmp_path / "empty")))
