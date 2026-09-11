"""Everything about embedding that is decided before a socket is opened, and by whom.

M7.3.3 is "local embedding via Qwen3 through the inference server", and item 31 of
`docs/needs-rupash.md` decided on 2026-09-06 that the model lives in a service of its own.
`brain.ops.inference` is the seam to that service and holds the wire contract;
`brain.knowledge.embed_queue` holds the batch and the protocol nothing implements. What was
missing between them is this: the decisions a client would otherwise take on its own, in the
module that cannot open a connection, so that the case that is always wrong can be tested
without one. That is the split the layout table states about `brain.ops.limits` and
`brain.ops.limit_store`, and the client half is `brain.ops.inference_client`.

**An embedding failure while ingesting and one while answering are different failures, and
only the first is allowed to be invisible.** This is the decision the rest of the module is
arranged around. A chunk that could not be embedded is still in the corpus, still found by
the lexical leg, and its vector arrives when the queue re-drives the job, so nobody needs to
be told anything and the honest response is to write nothing and wait. A *question* that
could not be embedded is different in kind: the nearest-neighbour leg cannot run at all, the
answer in front of a person right now is composed from text search alone, and no later run
fixes the answer they already read. So the query leg's outage is `Outcome.DEGRADED` and never
`OK`. See `AN_INGEST_OUTAGE_IS_INVISIBLE_AND_A_QUERY_OUTAGE_IS_DECLARED`.

**The vector width is read off the column rather than asked for, so a model of another width
is a migration and cannot be anything else.** `served_embedding_model` has no `dimensions`
parameter and nothing here supplies one: the figure comes from `know.chunk.embedding`'s own
declared type. A server running different weights states its own width in the response,
`EmbeddingModel` is built from that, and `writes_for` refuses the identity mismatch, so a
width change surfaces as a refusal rather than as rows nobody can compare. See
`THE_WIDTH_IS_THE_COLUMNS_SO_A_MODEL_CHANGE_IS_A_MIGRATION`.

**That sentence said "rather than configured" until 2026-09-10 and the correction is worth
reading rather than skipping.** The width is configured now: item 34 made it
`INSTALL_EMBEDDING_DIMENSIONS`, declared in `brain.install` and defaulting to the 1024 below,
because a width compiled into the product makes every client whose model is a different size
a fork. What did not change is anything this module relies on. The setting is read once, on
an install day, by the migration that alters the column; it cannot be read here, it cannot be
passed to `served_embedding_model`, and changing it afterwards is refused unless the corpus
is empty. So the column is still the fact, and `dimension_gaps` still compares the served
model against it. What that check reports has changed direction: it fired for every
deployment while the product shipped one width for a model of another, and it now fires only
for an install whose declared width is not what its own model produces.

**A run that stopped in the middle is not a run that finished, and `EmbedRun` cannot be built
saying otherwise.** `writes_for` already refuses a response that covers part of one batch. The
gap this closes is one level up: a rebuild is many batches, and a loop that swallowed the
third failure and carried on would return the writes of batches one, two, four and five, whose
last chunk id is past a hole nobody embedded. `RebuildCursor.advance` would accept it, because
the position moved forward, and the rows in the hole are then left on the old model with
nothing recording it. So the run stops at the first failure and reports how many of how many
batches it completed. See `A_RUN_THAT_STOPPED_IS_NOT_A_RUN_THAT_FINISHED`.

**Normalisation is checked and never applied.** `brain.knowledge.search.VECTOR_INDEX` chooses
`vector_cosine_ops` and the comment beside it says the embeddings are normalised; nothing
anywhere has ever checked that, and Qwen3 does not normalise unless it is asked to. Rejected:
normalising the vector here on arrival, which is one line and always succeeds. It would make
this process the last thing to change the numbers, so the corpus would hold values that are
not the ones the model produced under the identity recorded beside them, and `EmbeddedVector`
exists to say those two cannot be separated. A check turns a comment into a fact and names the
flag that fixes it; a transform hides which side was wrong. See
`THE_INDEX_ASSUMES_NORMALISED_VECTORS_SO_THE_RESPONSE_IS_CHECKED`.

**A question's vector is never a write.** `question_vector` returns an `EmbeddedVector` and
deliberately does not go through `writes_for`, whose output is an update to `know.chunk`. A
question is not a passage, it belongs to nobody, and the only value that could carry it into
the corpus is one this path never constructs. See `A_QUESTIONS_VECTOR_IS_NEVER_A_WRITE`.

**The timeout is what the queue can tolerate and not what the model needs**, because nothing
here knows the second figure. No such server has ever run on this host, so there is no
throughput to divide a batch by; what is knowable is that a request outlasting
`brain.ops.queue.stale_after` is a job the queue treats as orphaned and re-drives while the
first copy is still waiting, which sends the same batch twice to a server already too slow to
answer once. So `EMBED_TIMEOUT_SECONDS` is derived from those figures rather than chosen
beside them, and if the first measurement says a full batch needs longer, the fix is a smaller
batch rather than a longer timeout.

**Where the inference server is, is read here and in no other place.** `embedding_endpoint`
resolves `INSTALL_MODEL_ENDPOINT` through `brain.install.value_of`, which is the one reader of
an installation value, and `brain.ops.inference_client.make_client` takes no address of its
own: a client that accepted one would be a second answer to "where does this company's
document text go", and the wrong copy is the one that renders. **There is deliberately no
branch on `INSTALL_MODEL_PROFILE` anywhere on this path**; see
`EMBEDDING_IS_LOCAL_ON_EVERY_MODEL_PROFILE` for why `hosted` moves the reasoner and never the
embedder.

**What has no caller yet, stated by name rather than in a paragraph.** This section was prose
until 2026-09-11 and prose is what goes stale: it opened "nothing in this repository calls
anything in this module" three sentences before naming the caller of `policy_gaps`.
`brain.knowledge.embed.wiring_gaps` is that list as a value now, one entry per step between a
chunk needing an embedding and a vector being stored, each saying what it still needs, and
`tests/unit/test_embed.py` holds every entry to what `brain.ops.controls.call_sites` reads out
of the source. A step that gains a caller and is still listed as an orphan is a red test
rather than a sentence nobody re-reads.

Scope: domain logic. Nothing here opens a connection, loads a model or reads a clock. It does
read this installation's declared endpoint, through `brain.install` and with `env` a parameter,
which is the same shape `brain.knowledge.search.declared_dimensions` uses for the width.

Task ids: none
"""

from __future__ import annotations

import enum
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final
from urllib.parse import urlsplit

from brain.core.errors import Outcome
from brain.install import value_of
from brain.knowledge.embed_queue import (
    Embedded,
    EmbeddingBatch,
    EmbeddingService,
    EmbeddingUnit,
    EmbeddingWrite,
    embed_batch,
)
from brain.knowledge.embedding import (
    EMBEDDING_FIELD,
    EmbeddedVector,
    EmbeddingError,
    EmbeddingModel,
)
from brain.knowledge.search import CHUNK, Vector
from brain.ops.inference import (
    INFERENCE_DESTINATION_SETTINGS,
    InferenceRefused,
    InferenceTask,
    served_model,
)
from brain.ops.queue import HEARTBEAT_SECONDS, stale_after

# ------------------------------------------------------------------ written-down reasons

#: Why the two legs fail differently, and which of them is allowed to say nothing.
AN_INGEST_OUTAGE_IS_INVISIBLE_AND_A_QUERY_OUTAGE_IS_DECLARED: Final = (
    "A chunk whose embedding failed is still a chunk: it is in the corpus, the lexical leg "
    "still finds it, and the queue re-drives the job, so the only correct response is to "
    "write nothing and let it arrive late. Nobody is told, and nobody needs to be, because "
    "nothing a person can see is wrong. A question whose embedding failed is not the same "
    "event wearing different clothes. There is no vector, so there is no nearest-neighbour "
    "leg, so the answer being composed at that moment comes from text search alone, and no "
    "later run repairs the answer somebody has already read. That is the degradation "
    "brain.knowledge.embedding is written against arriving from the other end of the "
    "pipeline, and the one thing that stops it being invisible is refusing to call it OK. So "
    "the ingest leg fails the job and the query leg returns Outcome.DEGRADED, and neither "
    "writes a row. What is deliberately not done on either leg is a retry inside the call: "
    "the ingest leg already has one, which is the queue, and a loop that slept and tried "
    "again would hold a slot for the length of an outage while the queue thought the job was "
    "running."
)

#: Why nothing here takes a width, and what a change to it actually is.
THE_WIDTH_IS_THE_COLUMNS_SO_A_MODEL_CHANGE_IS_A_MIGRATION: Final = (
    "The width is part of the type of know.chunk.embedding, so it is a fact about the "
    "database. An install chooses it once through INSTALL_EMBEDDING_DIMENSIONS, which the "
    "migration reads and the migration alone; nothing at run time may supply one. A dimensions "
    "parameter on this path would let a caller point one request at a model of another width, "
    "at which point every insert is refused by PostgreSQL, or worse, the width happens to "
    "match and the vectors are from a space nothing recorded. So served_embedding_model has no "
    "dimensions parameter, and the figure it uses is read off the column object rather than "
    "from a constant that sits beside it: a column altered without the constant being edited "
    "would otherwise leave the two disagreeing with nothing to notice. What is left is a model "
    "whose native width is not the column's, and that is a migration and a full re-embed, "
    "which is what dimension_gaps says in words rather than leaving somebody to discover at "
    "the first insert."
)

#: Why a partial run reports itself as one, and why it stops rather than carrying on.
A_RUN_THAT_STOPPED_IS_NOT_A_RUN_THAT_FINISHED: Final = (
    "writes_for refuses a response covering part of one batch, and that is not enough on its "
    "own, because a rebuild is many batches and the loop over them is where partial success "
    "gets rounded up. A loop that caught the third batch's failure and carried on would hand "
    "back the writes of one, two, four and five; their last chunk id is past a hole, "
    "RebuildCursor.advance accepts it because the position moved forward, and the rows in the "
    "hole stay on the old model with nothing anywhere recording it, which is exactly the "
    "silent state A_REBUILD_RESUMES_BY_KEY_AND_NEVER_BY_OFFSET is about. So the run stops at "
    "the first failure, its position is the last chunk of the last batch that completed "
    "whole, and it carries how many of how many batches it managed. A run holding a failure "
    "cannot also report itself complete, and that is refused at construction rather than left "
    "to a caller reading the right field."
)

#: Why an un-normalised vector is refused rather than normalised on arrival.
THE_INDEX_ASSUMES_NORMALISED_VECTORS_SO_THE_RESPONSE_IS_CHECKED: Final = (
    "brain.knowledge.search.VECTOR_INDEX picks vector_cosine_ops and says in a comment that "
    "the embeddings are normalised, so cosine and inner product rank identically. That is an "
    "assertion about the far side that nothing has ever tested, and it is not free: sentence "
    "encoders return un-normalised vectors unless asked, so the claim is one flag away from "
    "being false and the day it becomes false is the day somebody swaps the operator class "
    "for the faster one and every ranking quietly changes. Normalising here was rejected. It "
    "always succeeds, which is the problem: the numbers written to the corpus would then not "
    "be the numbers the model produced, under an identity that says they are, and "
    "EmbeddedVector exists precisely to say those two cannot be separated. A check makes the "
    "comment a fact and its message names the flag on the far side; a transform makes it true "
    "by rewriting the evidence."
)

#: Why a question's vector never travels as a write.
A_QUESTIONS_VECTOR_IS_NEVER_A_WRITE: Final = (
    "The response to a question and the response to a batch of chunks arrive in the same "
    "shape, and the tempting saving is to read both with writes_for. Its output is an "
    "EmbeddingWrite, which is an update to a row of know.chunk, and a question has no row: it "
    "is nobody's passage, it carries no permissions, and a value that could be written is a "
    "value somebody eventually writes. So the query leg has its own reader that returns the "
    "vector and nothing that could reach the corpus. The batch's id is a constant rather than "
    "an invented chunk id for the same reason from the other side: it cannot be produced by "
    "chunk_document, which builds every id as an item id and a four-digit ordinal, so a "
    "question can never be confused for a passage even by a response that is wrong."
)


#: Why `INSTALL_MODEL_PROFILE` does not reach this path at all.
EMBEDDING_IS_LOCAL_ON_EVERY_MODEL_PROFILE: Final = (
    "INSTALL_MODEL_PROFILE says whether this install may reach an external provider, and it "
    "is about the reasoner. Reading it here and sending embeddings to a hosted model on "
    "'hosted' would be a different decision wearing the same word, because the two legs send "
    "different things to different extents. A reasoner is handed one person's question and the "
    "passages that person was already entitled to, at the moment they ask. An embedder is "
    "handed every passage of every document this company has ever uploaded, including the ones "
    "nobody has asked about and the ones nobody may read, and it is handed them again on every "
    "model change. Item 31 decided the models live in a service of this company's own for a "
    "memory reason and that boundary is worth more than the reason that bought it. There is a "
    "second cost that is not about privacy: the model identity is recorded beside every vector, "
    "so a profile that moved the embedder would leave the corpus holding two spaces and "
    "A_MIXED_CORPUS_HAS_NO_VECTOR_LEG turns the vector leg off until somebody re-embeds all of "
    "it. So there is no branch on the profile on this path, and a test asserts the endpoint is "
    "the same value under both."
)

#: Why the address has to be a bare origin and is refused when it is anything else.
AN_ENDPOINT_IS_AN_ORIGIN_BECAUSE_THE_PATH_IS_JOINED_BY_CONCATENATION: Final = (
    "brain.ops.inference_client.embed_url builds the address it posts to by concatenation, "
    "trimming a trailing slash and appending its own path. Only an origin survives that. An "
    "endpoint carrying a query or a fragment produces a URL with the appended path after the "
    "question mark, which is a request to the wrong place that no test on either side would "
    "see; an endpoint carrying credentials puts them in every string this address appears in, "
    "and this server authenticates nobody because it is reached over a network with "
    "internal: true and no route off the host. An endpoint carrying a base path is the third "
    "and it is the one worth refusing rather than joining properly: /v1 is how a hosted "
    "provider's API is addressed, so permitting a base path is permitting the single edit that "
    "turns this leg into an external call, and it would be made by whoever is copying an "
    "environment file rather than by anybody deciding it. An install that genuinely serves its "
    "own model under a path needs embed_url to join two paths, which is a change with somebody "
    "looking at it."
)


class EmbeddingUnavailable(EmbeddingError):  # noqa: N818 - the family in embedding.py has no suffixes
    """The service could not be asked, or did not answer. Distinct from a bad answer.

    Its own name inside `EmbeddingError` for the reason `InferenceRefused` has one: an
    operator has to be able to tell "the server is down" from "the server said something
    nobody expected", because the first is a deployment and the second is a contract. Both
    are caught by anything wrapping the embed leg, and both write nothing.
    """


# ------------------------------------------------------------------ the two legs (M7.3.3)


class EmbeddingLeg(enum.StrEnum):
    """Which side of the corpus an embedding was for. Closed, because the policy is a map.

    Two, and the difference between them is the whole of
    `AN_INGEST_OUTAGE_IS_INVISIBLE_AND_A_QUERY_OUTAGE_IS_DECLARED`. A third would need
    somebody to decide what an outage means for it rather than inheriting one by accident.
    """

    #: Writing vectors for chunks that are already in the corpus.
    INGEST = "ingest"
    #: Embedding a question so the nearest-neighbour leg can run.
    QUERY = "query"


@dataclass(frozen=True)
class OutageResponse:
    """What happens on one leg when the service cannot answer, as a value rather than prose.

    `writes_anything` is on here even though it is False for both legs, and that is
    deliberate: it is the field a future third leg would have to fill in, and a policy where
    the dangerous answer has to be typed out is one nobody reaches by omission.
    """

    leg: EmbeddingLeg
    #: Whether any row is written. False on both legs; see the class docstring.
    writes_anything: bool
    #: Whether something else will try again without a person asking it to.
    retried: bool
    #: What the caller reports. Never `Outcome.DENIED` or `Outcome.ABSENT`: an outage is a
    #: fact about this system and says nothing about what exists or who may see it.
    outcome: Outcome
    reason: str


#: Exhaustive over `EmbeddingLeg`, in the shape `brain.ops.limit_store.UNREACHABLE_POLICY` is
#: exhaustive over `LimitScope`, and tested per member for the same reason: a missing entry
#: would otherwise take whichever behaviour the lookup happened to fall through to.
OUTAGE_POLICY: Final[Mapping[EmbeddingLeg, OutageResponse]] = MappingProxyType(
    {
        EmbeddingLeg.INGEST: OutageResponse(
            leg=EmbeddingLeg.INGEST,
            writes_anything=False,
            retried=True,
            outcome=Outcome.FAILED,
            reason=(
                "the job failed and nothing was written; the chunks stay unembedded and the "
                "queue re-drives it, which is safe because an embedding is an update of two "
                "columns keyed by chunk id"
            ),
        ),
        EmbeddingLeg.QUERY: OutageResponse(
            leg=EmbeddingLeg.QUERY,
            writes_anything=False,
            retried=False,
            outcome=Outcome.DEGRADED,
            reason=(
                "the question has no vector, so the nearest-neighbour leg did not run and "
                "this answer was composed from the lexical leg alone; nothing repairs an "
                "answer that has already been read, so it is reported rather than absorbed"
            ),
        ),
    }
)


def outage_response(leg: EmbeddingLeg) -> OutageResponse:
    """What this leg does when the service cannot answer, or a refusal naming the legs.

    Refuses rather than returning a default, matching `brain.ops.inference.served_model`. A
    default here is the one that gets chosen by accident, and the accident nobody notices is
    the one that reports a degraded answer as an ordinary one.
    """
    response = OUTAGE_POLICY.get(leg)
    if response is None:
        msg = (
            f"no outage response is declared for the {leg.value!r} leg; every leg has to say "
            f"what an unreachable service means for it, and the ones that do are "
            f"{sorted(one.value for one in OUTAGE_POLICY)}"
        )
        raise EmbeddingError(msg)
    return response


# ------------------------------------------------------ the width, from the column (M7.3.3)


def _column_dimensions() -> int:
    """The width of `know.chunk.embedding`, read off the column rather than from a constant.

    `brain.knowledge.search.EMBEDDING_DIMENSIONS` is the number the column was built from and
    importing it would be the obvious thing to do. It is one step too far away: a column
    altered to another width without that constant being edited leaves the two disagreeing,
    and the disagreement presents as every insert being refused by PostgreSQL long after the
    model was chosen. The type object is the fact.
    """
    column_type = CHUNK.c[EMBEDDING_FIELD].type
    if not isinstance(column_type, Vector):
        msg = (
            f"{EMBEDDING_FIELD} is a {type(column_type).__name__} rather than a vector column, "
            "so nothing here can say what width a model has to produce"
        )
        raise EmbeddingError(msg)
    return column_type.dimensions


#: What the corpus can hold, which is the only width this system may ask for.
COLUMN_DIMENSIONS: Final[int] = _column_dimensions()

#: What Qwen3-Embedding-0.6B produces. **Not measured here**, in the register
#: `brain.ops.inference.ServedModel.sizing_basis` requires: it is the hidden size on the
#: published model card, and that card also offers Matryoshka truncation, which shortens a
#: vector and cannot lengthen one. So this figure is a ceiling as well as a default, and no
#: setting on the far side lengthens what this model returns. There is no such server on this
#: host, so there is nothing to measure it against; `dimension_gaps` is what compares the two
#: ends rather than a sentence here claiming they agree.
#:
#: **This is where `INSTALL_EMBEDDING_DIMENSIONS`'s default comes from**, and the arrow points
#: this way rather than the other: the install setting defaults to the width the model this
#: product serves produces, and `tests/unit/test_search.py` holds the two together so that
#: neither can be edited into agreement with itself.
QWEN3_EMBEDDING_DIMENSIONS: Final = 1024


def served_embedding_model(*, revision: str) -> EmbeddingModel:
    """The model this system will record against a vector. No width parameter, deliberately.

    The name comes from `brain.ops.inference.SERVED_MODELS`, which is where the weights the
    container was sized for are declared, so a model served without being declared there is
    memory no budget accounted for and cannot be reached through this function at all.

    The revision is the caller's because it is the one part nobody here can know: it is which
    weights are in the volume, and `EmbeddingModel` refuses an empty one rather than defaulting
    to a first version, which would be a promise made on behalf of somebody who did not check.

    The width is neither, and that is the point. See
    `THE_WIDTH_IS_THE_COLUMNS_SO_A_MODEL_CHANGE_IS_A_MIGRATION`.
    """
    return EmbeddingModel(
        name=served_model(InferenceTask.EMBEDDING).name,
        revision=revision,
        dimensions=COLUMN_DIMENSIONS,
    )


def dimension_gaps(
    *,
    model_dimensions: int = QWEN3_EMBEDDING_DIMENSIONS,
    column_dimensions: int = COLUMN_DIMENSIONS,
) -> tuple[str, ...]:
    """Whether the served model can produce what this column holds, in words naming the fix.

    **This is a schema finding even though a setting decides it**, which is why it is a
    sentence about a migration rather than about a restart. `INSTALL_EMBEDDING_DIMENSIONS` is
    read once, by the migration that alters the column, and a column already holding vectors
    refuses the change: an operator who edits the setting and restarts has changed nothing
    the database knows about. Both figures are parameters with defaults for the reason
    `brain.ops.inference.weights_mib` takes one: a check that can only ever be run against the
    constants beside it cannot be shown to fail.

    **It fired for every deployment until 2026-09-10 and now fires for a misconfigured one**,
    which is the whole difference this check was waiting on. The column was the width of a
    hosted model chosen in `brain.knowledge.search` and Qwen3-Embedding-0.6B is narrower, so
    the product shipped unable to embed with the model it names; item 34 narrowed the column
    to the served model's width and made that width the install's. What is left is the case
    this check is worth having for: an install that declares a width its own inference server
    does not produce, where every embedding job fails at the insert and nothing else does.
    """
    if model_dimensions == column_dimensions:
        return ()
    return (
        f"the served embedding model produces {model_dimensions} dimensions and "
        f"know.chunk.embedding holds {column_dimensions}; the width is part of the column "
        "type, so this is a migration that alters the column and rebuilds the vector index, "
        "plus a re-embed of every chunk, and not an edit to INSTALL_EMBEDDING_DIMENSIONS and "
        "a restart: that setting is read by the migration and the migration refuses to move "
        "a column that already holds vectors. Nothing is written in the meantime: an insert "
        "of the wrong width is refused by PostgreSQL",
    )


# ------------------------------------------------------ normalisation, checked (M7.3.3)

#: The relative error a half-precision pipeline accumulates before a vector is even returned.
#: A judgement rather than a measurement, in the register `PARSE_EXPANSION` is: fp16 carries
#: about three decimal digits, so a norm computed from fp16 components is right to about this.
FP16_ACCUMULATED_ERROR: Final = 1e-3

#: How far a returned vector's norm may sit from one. Ten times the figure above, so ordinary
#: half-precision arithmetic can never trip it, and far below one, so a vector that was not
#: normalised at all cannot pass however small its scale happens to be.
VECTOR_NORM_TOLERANCE: Final = 1e-2

if VECTOR_NORM_TOLERANCE <= FP16_ACCUMULATED_ERROR:  # pragma: no cover - a constant
    _msg = (
        f"a norm tolerance of {VECTOR_NORM_TOLERANCE} is inside the {FP16_ACCUMULATED_ERROR} "
        "a half-precision pipeline accumulates, so every honest response would be refused"
    )
    raise EmbeddingError(_msg)

if VECTOR_NORM_TOLERANCE >= 1.0:  # pragma: no cover - a constant
    _msg = (
        f"a norm tolerance of {VECTOR_NORM_TOLERANCE} admits a vector of every scale down to "
        "zero, which is the check not being one"
    )
    raise EmbeddingError(_msg)


def vector_norm(values: Sequence[float]) -> float:
    """The Euclidean length of a returned vector.

    `math.fsum` rather than the built-in sum, so the error in the check is not the thing the
    check measures: over a thousand terms an ordinary sum accumulates its own drift, and a
    refusal has to be the far side's fault and never this arithmetic's.
    """
    return math.sqrt(math.fsum(value * value for value in values))


def accept_vectors(embedded: Sequence[Embedded]) -> tuple[Embedded, ...]:
    """The vectors a response carried, or a refusal that names the flag on the far side.

    Checks what `brain.knowledge.search.VECTOR_INDEX` assumes and nothing checks. See
    `THE_INDEX_ASSUMES_NORMALISED_VECTORS_SO_THE_RESPONSE_IS_CHECKED` for why this is a check
    rather than a normalisation, and `InferenceRefused` rather than a name of its own because
    this is the same event that class already describes: the service answered, and the answer
    cannot be written down.

    Returns the vectors rather than None so a caller cannot use the unchecked list by
    forgetting to assign, which is the shape `brain.knowledge.embed_queue.writes_for` uses.
    """
    for one in embedded:
        norm = vector_norm(one.vector.values)
        if abs(norm - 1.0) > VECTOR_NORM_TOLERANCE:
            msg = (
                f"chunk {one.chunk_id!r} came back with a vector of length {norm:.4f} rather "
                "than one. The vector index is built with vector_cosine_ops on the stated "
                "assumption that these are normalised, and nothing else in this system checks "
                "it; ask the server to normalise its embeddings rather than normalising them "
                "here, because a vector rewritten on arrival is no longer the one the recorded "
                "model produced"
            )
            raise InferenceRefused(msg)
    return tuple(embedded)


# ------------------------------------------------------ how long a request may take (M7.3.3)

#: The most a single embedding request may take before it is abandoned. Derived from the
#: queue's own figures rather than chosen beside them: a worker writes its heartbeat in its
#: own transaction, so a worker blocked in a request is a worker writing none, and a request
#: that outlasts `stale_after` is a job the queue treats as orphaned and re-drives while the
#: first copy is still waiting. One heartbeat of margin, which is the smallest unit the queue
#: measures staleness in.
#:
#: **It is not an estimate of how long a batch takes.** Nothing here knows that: no inference
#: server has ever run on this host, so there is no throughput to divide a batch by. If a
#: measurement one day says a full batch needs longer than this, the answer is a smaller
#: batch, because a longer timeout is a job running twice.
EMBED_TIMEOUT_SECONDS: Final[float] = stale_after().total_seconds() - HEARTBEAT_SECONDS


# ------------------------------------------------------ a question, not a passage (M7.3.3)

#: What the wire calls the single input a question is sent as. A constant rather than an
#: invented chunk id, and one no chunk can hold: `chunk_document` builds every id as an item
#: id, a full stop and a four-digit ordinal. See `A_QUESTIONS_VECTOR_IS_NEVER_A_WRITE`.
QUESTION_UNIT_ID: Final = "question"


def question_batch(text: str, *, model: EmbeddingModel) -> EmbeddingBatch:
    """One question, as the same batch a chunk would travel in.

    The same value rather than a second request shape, because the server, the budget and
    every refusal in `decode_embeddings` apply unchanged to one input, and a second shape
    would be a second thing to keep right. What is not shared is what comes back: see
    `question_vector`.
    """
    return EmbeddingBatch(model=model, units=(EmbeddingUnit(chunk_id=QUESTION_UNIT_ID, text=text),))


def question_vector(embedded: Sequence[Embedded]) -> EmbeddedVector:
    """The question's vector, or a refusal. Never an `EmbeddingWrite`.

    Refuses a response that is not exactly one vector for exactly the id that was sent, which
    is `A_VECTOR_IS_MATCHED_TO_A_CHUNK_BY_ID_AND_NEVER_BY_POSITION` applied to a batch of one:
    a response carrying two entries, or one naming something else, is a server answering a
    different question, and taking the first entry would embed the wrong text with nothing
    downstream able to see it.

    The width is not checked here and does not need to be: `EmbeddedVector` refuses a vector
    whose length disagrees with the model that claims it, and `vector_query` refuses one whose
    length disagrees with the column.
    """
    if len(embedded) != 1:
        msg = (
            f"a question was sent as one input and {len(embedded)} vector(s) came back; there "
            "is no rule for choosing among them, and choosing the first embeds whichever text "
            "the far side happened to put there"
        )
        raise InferenceRefused(msg)
    only = embedded[0]
    if only.chunk_id != QUESTION_UNIT_ID:
        msg = (
            f"the response names {only.chunk_id!r} and the question was sent as "
            f"{QUESTION_UNIT_ID!r}; a vector matched to an input by its position rather than "
            "its id is how the wrong text gets searched for"
        )
        raise InferenceRefused(msg)
    return only.vector


# ------------------------------------------------------ many batches, one run (M7.3.3)


@dataclass(frozen=True)
class EmbedRun:
    """What a run over several batches actually achieved, and whether it finished.

    The invariants are enforced here rather than left to a caller reading the right field,
    because the failure this closes is a caller reading the wrong one. See
    `A_RUN_THAT_STOPPED_IS_NOT_A_RUN_THAT_FINISHED`.
    """

    planned: int
    completed: int
    writes: tuple[EmbeddingWrite, ...] = ()
    #: Why the run stopped, empty when it did not. A string rather than an exception, because
    #: this value is what a caller logs and what a cursor is advanced from, and an exception
    #: carried in a field is one somebody re-raises far from where it happened.
    failure: str = ""

    def __post_init__(self) -> None:
        if self.planned < 0 or self.completed < 0:
            msg = "a run cannot have planned or completed a negative number of batches"
            raise EmbeddingError(msg)
        if self.completed > self.planned:
            msg = (
                f"a run completed {self.completed} of {self.planned} batch(es), which is more "
                "than it had; the count that would be trusted is the one that is wrong"
            )
            raise EmbeddingError(msg)
        if self.failure and self.completed == self.planned:
            msg = (
                f"a run of {self.planned} batch(es) reports every one complete and also "
                f"carries a failure ({self.failure}); one of the two is false and a reader "
                "cannot tell which"
            )
            raise EmbeddingError(msg)
        if not self.failure and self.completed != self.planned:
            msg = (
                f"a run stopped after {self.completed} of {self.planned} batch(es) and says "
                "why nowhere; a run that stopped for no stated reason is reported as one that "
                "was interrupted by nothing, and its position is past rows nobody embedded"
            )
            raise EmbeddingError(msg)

    @property
    def is_complete(self) -> bool:
        """Whether every planned batch was written. The one question a caller may ask."""
        return not self.failure and self.completed == self.planned

    @property
    def last_chunk_id(self) -> str:
        """The last chunk actually written, which is how far a cursor may be advanced.

        The last write rather than the largest id. `plan_batches` keeps the order it was
        given and the rebuild scan is ordered by key, so the two agree; where they would not,
        `RebuildCursor.advance` refuses a position that is not forward, which is the check
        that should fire rather than this one quietly picking the biggest number it can see.
        """
        return self.writes[-1].chunk_id if self.writes else ""


def embed_all(batches: Sequence[EmbeddingBatch], service: EmbeddingService) -> EmbedRun:
    """Send these batches in order and stop at the first one that fails.

    **Stops rather than continuing**, and that is the decision in this function. Carrying on
    would produce writes whose last chunk id is beyond a hole nobody embedded, and the cursor
    would accept it because the position moved forward. It is also the right thing on the
    evidence: the first failure is almost always the server, and the batches after it fail too
    while costing a round trip each.

    Catches `EmbeddingError` and nothing wider. A `TypeError` here is a bug in this repository
    and has to reach somebody, not be folded into a run report as though a server had done it.

    The writes are returned rather than applied, matching `embed_batch`: this module has no
    session, and the caller is what holds a transaction to take row locks in.
    """
    writes: list[EmbeddingWrite] = []
    for done, batch in enumerate(batches):
        try:
            writes.extend(embed_batch(batch, service))
        except EmbeddingError as exc:
            return EmbedRun(
                planned=len(batches),
                completed=done,
                writes=tuple(writes),
                failure=str(exc),
            )
    return EmbedRun(planned=len(batches), completed=len(batches), writes=tuple(writes))


# ------------------------------------------------- where the text is sent, once (M7.3.3)

#: The setting that says where this install's inference server answers. One name, read through
#: `brain.install.value_of` and nowhere else, because two readers is two defaults and the wrong
#: one is the one nobody looked at.
ENDPOINT_SETTING: Final = "INSTALL_MODEL_ENDPOINT"

#: The other setting that names the same destination, spelled as an operator sets it. Derived
#: from `brain.ops.inference.INFERENCE_DESTINATION_SETTINGS` rather than typed, so a rename
#: there cannot leave this asking about a variable nobody sets.
#:
#: It exists for a different job and `endpoint_conflicts` is what keeps the two jobs apart:
#: `brain.config.check` refuses this one being set on a profile that deploys no inference
#: server, which is a refusal about a *destination being configured at all*. Nothing dials it.
APP_ENDPOINT_SETTING: Final = f"BRAIN_{INFERENCE_DESTINATION_SETTINGS[0].upper()}"

#: The schemes an inference endpoint may use. Two, and `https` is here for an install that
#: terminates TLS in front of its own server rather than because anything about this path
#: needs it: the compose network is internal, so plain HTTP on it leaves no host.
ENDPOINT_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https"})


def endpoint_refusals(address: str) -> tuple[str, ...]:
    """Every reason this address is not somewhere this system may post a document's text to.

    A pure function over a string rather than a check inside the resolver, for the reason
    `dimension_gaps` is one: a refusal that can only be reached by setting an environment
    variable is a refusal nobody can show firing, and this one is the last thing between a
    client's corpus and an address somebody pasted.

    Four refusals and they are argued in
    `AN_ENDPOINT_IS_AN_ORIGIN_BECAUSE_THE_PATH_IS_JOINED_BY_CONCATENATION`. What is
    deliberately **not** checked is whether the host is inside the client's network. Nothing
    here can tell: `inference-server` is a name Docker resolves and a public name resolves
    identically, and the alternative is a list of provider hostnames, which is the shape
    `brain.ops.independence.A_BLOCKLIST_OF_ONE_CLIENTS_NAMES_PASSES_FOR_EVERY_OTHER_CLIENT`
    refuses. What does stop the text leaving is structural and lives in the deployment: the
    `inference` network is `internal: true`, so a container on it has no route off the host.

    Returns all of them rather than the first, matching `brain.ops.worker.preflight`.
    """
    findings: list[str] = []
    trimmed = address.strip()
    if not trimmed:
        return (
            f"{ENDPOINT_SETTING} is empty, so there is nowhere to send text to be embedded. It "
            "has no safe default that could be filled in here: a client whose inference server "
            "is somewhere else would then have this company's documents posted at whatever "
            "answers on the name this product happened to ship",
        )
    parts = urlsplit(trimmed)
    if parts.scheme not in ENDPOINT_SCHEMES:
        findings.append(
            f"{ENDPOINT_SETTING}={trimmed!r} has scheme {parts.scheme!r} and an inference "
            f"endpoint is one of {sorted(ENDPOINT_SCHEMES)}; an address with no scheme at all "
            "is read as one whose scheme is its own hostname, so the request goes nowhere and "
            "the failure names a protocol nobody chose"
        )
    if not parts.hostname:
        findings.append(
            f"{ENDPOINT_SETTING}={trimmed!r} names no host, so nothing can be dialled; an "
            "address that is all path is the shape a relative URL takes after somebody has "
            "removed the scheme"
        )
    if parts.username or parts.password:
        findings.append(
            f"{ENDPOINT_SETTING} carries credentials in the address, which puts them in every "
            "string this endpoint appears in; the inference server authenticates nobody, "
            "because it is reached over a network declared internal, so a credential here "
            "means the address is something else's API"
        )
    if parts.path.strip("/") or parts.query or parts.fragment:
        findings.append(
            f"{ENDPOINT_SETTING}={trimmed!r} is not a bare origin. "
            f"{AN_ENDPOINT_IS_AN_ORIGIN_BECAUSE_THE_PATH_IS_JOINED_BY_CONCATENATION}"
        )
    return tuple(findings)


def embedding_endpoint(env: Mapping[str, str] | None = None) -> str:
    """Where this install's inference server answers, or a refusal naming every reason.

    **The one place this is read, and it takes no model profile.** See
    `EMBEDDING_IS_LOCAL_ON_EVERY_MODEL_PROFILE`: there is no parameter here that could name a
    provider and no branch that could choose one, so an install switching
    `INSTALL_MODEL_PROFILE` to `hosted` changes what the reasoner may reach and changes nothing
    about where a document's text goes.

    `env` is a parameter for the reason `brain.install.value_of` takes one, and it is load
    bearing rather than a convenience: every refusal below is unreachable from a test that
    cannot set the value.

    **The empty refusal cannot fire from here and that is worth stating rather than leaving a
    reader to assume it can.** `value_of` substitutes the declared default for a setting that
    is blank, so an install that empties `INSTALL_MODEL_ENDPOINT` gets the product's own
    service name back rather than nothing. `endpoint_refusals` still carries the empty case
    because `embed_url` is exported and asks it about an address somebody built by hand, and a
    joiner handed an empty string produces `/embed`, which is a relative URL posted at whatever
    the process resolves it against. What an environment file can actually produce here is the
    other four shapes.

    `EmbeddingUnavailable` rather than a class of its own, matching `embed_url`. A misconfigured
    address and an absent server are the same event to the leg that is waiting: nothing is
    written, and the ingest job is re-driven. What separates them for the operator is that this
    one is a finding on `python -m brain.knowledge.embed --check` rather than only a job that
    keeps failing.
    """
    address = value_of(ENDPOINT_SETTING, env).strip()
    findings = endpoint_refusals(address)
    if findings:
        raise EmbeddingUnavailable("; ".join(findings))
    return address


def endpoint_conflicts(*, endpoint: str, configured: str) -> tuple[str, ...]:
    """Whether the address that is checked at startup is the address text is actually sent to.

    Two settings name one destination and they answer to different halves of the system.
    `brain.config.check` calls `brain.ops.inference.inference_config_conflicts` on
    `BRAIN_INFERENCE_URL`, which is what refuses a destination being configured on a profile
    that deploys no inference server; `INSTALL_MODEL_ENDPOINT` is what
    `brain.ops.inference_client.make_client` dials. An install that sets both, differently, is
    the case worth a sentence: the check at startup passed judgement on a host nothing will
    contact, and the text goes to the other one with nothing having looked at it.

    Compared as origins rather than as strings, so a trailing slash is not a finding. An unset
    `BRAIN_INFERENCE_URL` is not a conflict either: it is the ordinary state of a `standard`
    install, where the startup check has nothing to refuse and the endpoint is the declared
    one.

    Both are parameters with no defaults, so this can be shown to fire; nothing here reads an
    environment.
    """
    other = configured.strip()
    if not other:
        return ()
    if urlsplit(other).netloc == urlsplit(endpoint.strip()).netloc:
        return ()
    return (
        f"{APP_ENDPOINT_SETTING} and {ENDPOINT_SETTING} name two different hosts, and only "
        f"{ENDPOINT_SETTING} is dialled. brain.config.check judges the first at startup, so "
        "this install has had a destination approved that nothing contacts while the text of "
        "its documents goes to the second, which nothing checked against the profile",
    )


# ------------------------------------------------------------------ the deployment check


def policy_gaps(
    *,
    model_dimensions: int = QWEN3_EMBEDDING_DIMENSIONS,
    column_dimensions: int = COLUMN_DIMENSIONS,
    timeout_seconds: float = EMBED_TIMEOUT_SECONDS,
) -> tuple[str, ...]:
    """Every reason this deployment cannot embed, whatever the inference server is doing.

    Called by `brain.ops.worker.preflight` beside `embed_batch_gaps`, which is the process
    that runs these batches. It went uncalled from the day it was written until 2026-09-07,
    for the ordinary reason: the file it belonged in was busy, the omission was written down
    honestly, and a written-down omission is not a check.

    Two checks, and they fail in opposite directions. The width is a refusal at the first
    insert, which is loud. The timeout is not a refusal at all: a request allowed to outlast
    `stale_after` produces a second copy of the job rather than an error, so the symptom is
    load rather than a message, and it appears only when the server is already slow.

    Returns all of them rather than the first, matching `brain.ops.worker.preflight`.
    """
    findings = list(
        dimension_gaps(model_dimensions=model_dimensions, column_dimensions=column_dimensions)
    )
    stale_seconds = stale_after().total_seconds()
    if timeout_seconds >= stale_seconds:
        findings.append(
            f"an embedding request may take {timeout_seconds}s and the queue treats a job as "
            f"orphaned after {stale_seconds}s; a slow server would have the same batch sent "
            "twice rather than reported once, and nothing in the log would say so"
        )
    if timeout_seconds <= 0:
        findings.append(
            f"an embedding request is allowed {timeout_seconds}s, which is a client that "
            "abandons every request before the server has read it"
        )
    return tuple(findings)
