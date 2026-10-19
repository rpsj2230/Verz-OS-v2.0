"""The embedding part: Qwen3-Embedding-0.6B at 8 bits through llama.cpp, one passage at a time.

**Never run against the real library or the real file.** Nothing in this repository has installed
llama-cpp-python or downloaded the weights, so the calls into `llama_cpp` (`Llama(...)`,
`embed(...)`, `n_embd()`) are written from its published interface and have not been executed. The
request it reads, the answer it writes, the revision it states and the checks it makes on a vector
are this program's own and are tested through a stand-in for the one object that touches the
library.

**One passage at a time, in a window of 1,024 tokens.** That is the figure the budget's anonymous
memory was worked out for (`brain.ops.model_server.SIZING`): the key and value cache is a fixed
112 KiB a token, so the window is what sets it. A passage longer than the window is cut by the
library to the window, so a very long chunk is embedded by its first thousand tokens; chunks are
cut well under that by `brain.knowledge.chunking`, and the window is the bound, not a goal. Texts
are embedded one by one and not as a list, because a list is a batch the library holds the cache
for at once.

**The model identity is the file's own.** The application records beside every vector which weights
made it and refuses a vector under any other, so what this says must be what it is: the name the
install was started with, the first twelve characters of the file's SHA-256 as the revision, and
the vector's width as the library reports it. The digest is the one `inference_server.fetch` wrote
when it put the file in the volume, trusted only while the file still has the length it recorded,
and computed here, once, when there is no record or the length differs: **a file replaced by hand
has a new revision, which is the model change that has no symptom made into one.** The install's
`INSTALL_EMBEDDING_REVISION` is set to this, and the install check that holds the two equal says
so in words when they part.

**A passage with no text, a vector of the wrong width and a vector with no length are failures of
this program, not facts about the text.** The first is refused as the application's mistake (a 400);
the others raise, which the worker reports as an outage and the application retries. A vector that
is not unit length is made so here, because the column's search is by angle and the library's own
normalisation is a flag this program does not trust itself to have set.

**What it does not do.** Qwen3-Embedding is trained to read a question with an instruction in front
of it and a passage without one. The wire has no field that says which this is, so every text is
embedded as a passage, and a question is embedded as one: a measured loss of retrieval quality that
nothing here has measured. Adding the field is a change to the wire's contract, which is the
application's to make, not this program's.

Task ids: M7.3.3, M7.3.4, M7.3.5, M7.7.8
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final, Protocol

from inference_server.config import ServerConfig
from inference_server.parts.documents import BadRequest, bad_request
from inference_server.worker import Answer

#: The keys one request, one input, the model and the answer carry. Spelled as
#: `brain.ops.inference.REQUEST_KEYS`, `INPUT_KEYS`, `MODEL_KEYS`, `VECTORS_KEY` and `VALUES_KEY`,
#: which a test holds equal.
REQUEST_KEYS: Final = ("model", "inputs")
INPUT_KEYS: Final = ("chunk_id", "text")
MODEL_KEYS: Final = ("name", "revision", "dimensions")
VECTORS_KEY: Final = "vectors"
VALUES_KEY: Final = "values"

#: How many characters of the file's SHA-256 are the revision. Within the application's own bound on
#: a revision (`brain.knowledge.embedding`), and long enough that two files do not share one.
REVISION_CHARS: Final = 12

#: The context window, in tokens, the budget's anonymous figure was worked out for.
WINDOW_TOKENS: Final = 1024

#: The record `inference_server.fetch` keeps of what it put in the volume.
RECORD: Final = "fetched.json"

CHUNK: Final = 1024 * 1024


class Embedder(Protocol):
    """What turns one text into one vector. The real one is llama.cpp's; a test supplies its own."""

    def embed(self, text: str) -> Sequence[float]: ...


def recorded_revision(model_dir: Path, name: str) -> str | None:
    """The revision the fetch recorded for the file, while the file still has the length it did.

    **Never hashes**, so the readiness route may ask it every twenty seconds for the life of the
    container: a gigabyte read on a health check would be the cost the check exists not to have.
    None where there is no file, no record, or a file of another length than the one recorded.
    """
    try:
        size = (model_dir / name).stat().st_size
        held = json.loads((model_dir / RECORD).read_text(encoding="utf-8")).get(name)
    except (OSError, ValueError, AttributeError):
        return None
    if isinstance(held, dict) and held.get("bytes") == size and isinstance(held.get("sha256"), str):
        return str(held["sha256"])[:REVISION_CHARS]
    return None


def revision_of(model_dir: Path, name: str) -> str | None:
    """The revision the weights file in the volume has, or None when there is no such file.

    The recorded digest is used while the file has the length it recorded; otherwise the file is
    read and hashed, which costs a second or two once per load and never per request.
    """
    recorded = recorded_revision(model_dir, name)
    if recorded is not None:
        return recorded
    path = model_dir / name
    if not path.is_file():
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            hasher.update(chunk)
    return hasher.hexdigest()[:REVISION_CHARS]


def unit_length(values: Sequence[float]) -> list[float]:
    """The vector scaled to length one, or a refusal when it has none to scale."""
    norm = math.sqrt(sum(one * one for one in values))
    if not math.isfinite(norm) or norm == 0.0:
        msg = "the library returned a vector with no length"
        raise ValueError(msg)
    return [one / norm for one in values]


def read_inputs(body: bytes) -> list[tuple[str, str]]:
    """The (chunk id, text) pairs of a request, or `BadRequest` saying which part is wrong."""
    try:
        request = json.loads(body)
    except ValueError as error:
        msg = "the body is not JSON"
        raise BadRequest(msg) from error
    inputs = request.get("inputs") if isinstance(request, dict) else None
    if not isinstance(inputs, list) or not inputs:
        msg = "the request carries no inputs"
        raise BadRequest(msg)
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in inputs:
        chunk_id = entry.get("chunk_id") if isinstance(entry, dict) else None
        text = entry.get("text") if isinstance(entry, dict) else None
        if not isinstance(chunk_id, str) or not chunk_id or chunk_id in seen:
            msg = "an input names no chunk, or names one twice"
            raise BadRequest(msg)
        if not isinstance(text, str) or not text.strip():
            msg = "an input carries no text"
            raise BadRequest(msg)
        seen.add(chunk_id)
        pairs.append((chunk_id, text))
    return pairs


class EmbeddingBackend:
    """`Backend`: one vector for each text of a request, under this file's own identity."""

    def __init__(self, embedder: Embedder, *, name: str, revision: str, dimensions: int) -> None:
        self._embedder = embedder
        self.name = name
        self.revision = revision
        self.dimensions = dimensions
        self.label = f"{name}@{revision}:{dimensions}"

    def model_block(self) -> dict[str, object]:
        """The identity every answer states, in the application's three fields."""
        return {"name": self.name, "revision": self.revision, "dimensions": self.dimensions}

    def handle(self, body: bytes) -> Answer:
        try:
            pairs = read_inputs(body)
        except BadRequest as error:
            return bad_request(error)
        vectors: list[dict[str, object]] = []
        for chunk_id, text in pairs:
            values = unit_length(self._embedder.embed(text))
            if len(values) != self.dimensions:
                msg = (
                    f"the library returned a vector of {len(values)} where {self.dimensions} is due"
                )
                raise ValueError(msg)
            vectors.append({"chunk_id": chunk_id, VALUES_KEY: values})
        return Answer(200, {"model": self.model_block(), VECTORS_KEY: vectors}, items=len(vectors))


class LlamaEmbedder:
    """The one object that touches llama.cpp. Imported only when an embedding part is loaded."""

    def __init__(self, path: Path, threads: int) -> None:
        import llama_cpp

        self._llama: Any = llama_cpp.Llama(
            model_path=str(path),
            embedding=True,
            pooling_type=llama_cpp.LLAMA_POOLING_TYPE_LAST,
            n_ctx=WINDOW_TOKENS,
            n_threads=threads,
            n_gpu_layers=0,
            use_mmap=True,
            use_mlock=False,
            verbose=False,
        )

    @property
    def dimensions(self) -> int:
        return int(self._llama.n_embd())

    def embed(self, text: str) -> Sequence[float]:
        result = self._llama.embed(text, normalize=False, truncate=True)
        # One text gives one vector; a list of lists is what a library that did not pool gives, and
        # the first row of it is not this model's embedding, so it is refused by its width later.
        if result and isinstance(result[0], list):
            return list(result[0])
        return list(result)


def load(
    config: ServerConfig, *, embedder: Callable[[Path, int], LlamaEmbedder] | None = None
) -> EmbeddingBackend:
    """The embedding backend, with the file in the volume memory-mapped by the library."""
    revision = revision_of(config.model_dir, config.embedding_file)
    if revision is None:
        msg = "the embedding weights are not in the volume"
        raise RuntimeError(msg)
    loaded = (embedder or LlamaEmbedder)(config.model_dir / config.embedding_file, config.threads)
    return EmbeddingBackend(
        loaded, name=config.embedding_model, revision=revision, dimensions=loaded.dimensions
    )
