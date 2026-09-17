"""The sequence from a chunk needing an embedding to the writes that store one, the question's
own leg beside it, and what is still missing before anything runs either.

`brain.knowledge.embed_queue` cuts work into batches, `brain.knowledge.embed_policy` holds
every decision taken before a socket is opened, `brain.ops.inference` holds the wire contract
and `brain.ops.inference_client` is the only thing that speaks to the server. Four modules,
each correct, and **until this one there was no order in which to call them**. A caller had to
know to build the model with `served_embedding_model`, cut the work with `plan_batches` against
that same model, and stop at the first failure with `embed_all`. Calls in one order,
discoverable only by reading four files, which is the shape of thing that gets assembled
differently by the second person to need it.

**The width is refused here rather than reported here, and that is the decision in this
module.** `dimension_gaps` compares what the served model produces against what
`know.chunk.embedding` holds, and `brain.ops.worker.advisories` already prints it: a worker
whose column disagrees with its model starts anyway, deliberately, because embedding is one
job type among many and refusing to boot would take the whole queue down to protect one leg.
That argument is about the process. It is not an argument for letting the leg *run*. An
embedding run on a disagreeing install posts the text of every chunk it was given to a model,
one request per batch, for vectors PostgreSQL will refuse at the insert. So the advisory tells
the operator and this refuses before the first request. See
`A_WIDTH_THE_COLUMN_CANNOT_HOLD_IS_REPORTED_AT_STARTUP_AND_REFUSED_HERE`.

**The worker's run starts from stored rows, not from `Chunk` objects, and that changed the entry
point on 2026-09-17.** `embed_chunks` took `Chunk` because `chunk_document` is the only thing that
copies a document's permissions onto a passage. The queued job names an ordinal window rather
than the chunks, so what the worker has in hand is rows read back from `know.chunk`, and a
`Chunk` cannot be rebuilt from a row, by design. `embed_units` is therefore the sequence and
takes `EmbeddingUnit`s, which carry an id and a text and nothing else. The guarantee `Chunk` gave
is kept one step earlier: `brain.knowledge.chunk_store` is the only writer of `know.chunk` and it
writes nothing `chunk_document` did not produce, so a row read back is a chunk that came through
the one door. Rejected: keeping `embed_chunks` beside it, which would have been a function with
tests and no caller, the exact thing `wiring_gaps` exists to report.

**What leaves this system on this path, exactly.** One POST per batch, to the one address
`embedding_endpoint` resolves, carrying `brain.ops.inference.embedding_request`'s two keys: a
model block of name, revision and width, and one input per chunk of an id and a text.
`EmbeddingUnit` has two fields and no third that could hold a scope, and the request is
`MappingProxyType` at every level so nothing can add a key to it on the way out. A question
travels the same way, as a batch of one whose id no chunk can have. Three things stop either
sending more and all three are structural rather than a convention: the value cannot carry a
permission, the mapping cannot grow one, and the network the server sits on is declared
`internal: true`, so a container on it has no route off the host. What is **not** structural is
the host: nothing here can tell an internal name from a public one, and `endpoint_refusals`
says so rather than shipping a list of provider hostnames.

**The embedder is this company's own server on every profile, and a hosted provider is not an
option here.** `embed_policy.EMBEDDING_IS_LOCAL_ON_EVERY_MODEL_PROFILE` argues it and a test holds
the endpoint to one value under both profiles: an embedder is handed every passage of every
document, including the ones nobody may read, so the boundary item 31 drew for a memory reason
is kept for a stronger one. A hosted embedder is a decision for the owner, not an edit here.

**M7.3.3 is not claimed**, which is why `Task ids` below says none. The leaf is "local embedding
via Qwen3 through the inference server" and nothing here has ever embedded anything against a
server: `docker-compose.inference.yml` names an image that does not exist, item 25 records the
container as roughly 3.3 GB over what the host has, and no weights have been pulled. What is
finished is everything on this side of the socket, run end to end against a stand-in service.
`wiring_gaps` names what is still not called by anything, by symbol, and
`tests/unit/test_embed.py` holds every entry to what `brain.ops.controls.call_sites` reads out
of the source, so a step that gains a caller and is still listed here is a red test.

Scope: domain logic. Nothing here opens a connection, loads a model or reads a clock. The
command reads an environment it is handed, which is what `brain.ops.worker.main` does.

Task ids: none
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from brain.knowledge.embed_policy import (
    APP_ENDPOINT_SETTING,
    ENDPOINT_SETTING,
    REVISION_SETTING,
    EmbeddingUnavailable,
    EmbedRun,
    dimension_gaps,
    embed_all,
    embedding_endpoint,
    embedding_revision,
    endpoint_conflicts,
    policy_gaps,
    question_batch,
    question_vector,
    served_embedding_model,
)
from brain.knowledge.embed_queue import EmbeddingService, EmbeddingUnit, plan_batches
from brain.knowledge.embedding import DEFAULT_BATCH_SIZE, EmbeddedVector, EmbeddingError

# ------------------------------------------------------------------ written-down reasons

#: Why the same finding is printed by one caller and refused by this one.
A_WIDTH_THE_COLUMN_CANNOT_HOLD_IS_REPORTED_AT_STARTUP_AND_REFUSED_HERE: Final = (
    "brain.ops.worker.advisories prints dimension_gaps and starts the worker anyway, and that "
    "is right: both workers drain the system queue, embedding is one job type on it, and a "
    "container that refused to start over a corpus column would take every other kind of "
    "housekeeping down with it while the operator read a schema decision they cannot make at "
    "three in the morning. None of that argues for running the leg. A run on an install whose "
    "column and model disagree posts the text of every chunk it was handed, one request per "
    "batch, and every vector that comes back is refused by PostgreSQL at the insert, so the "
    "whole cost is paid to produce nothing. The advisory is for the person; this is for the "
    "corpus, and they are different questions with the same evidence behind them."
)

#: Why an empty sequence is refused rather than answered with an empty run.
EMBEDDING_NOTHING_IS_A_JOB_THAT_REPORTS_SUCCESS_HAVING_DONE_NOTHING: Final = (
    "A run over no chunks completes every batch it planned, which is none, so is_complete is "
    "true and a caller advancing a cursor on it moves past whatever window named no rows. "
    "embed_job already refuses a window that ends before it starts for this exact reason, in "
    "its own words: it names no chunks and the job would report success having embedded "
    "nothing. The same sentence applies one layer up, where the window has already been turned "
    "into rows and the rows came back empty, which is a scan that found nothing rather than a "
    "unit of work."
)


# ------------------------------------------------------ the sequence, in order (M7.3.3)


def embed_units(
    units: Sequence[EmbeddingUnit],
    *,
    service: EmbeddingService,
    revision: str,
    max_chunks: int = DEFAULT_BATCH_SIZE,
    budget_bytes: int | None = None,
) -> EmbedRun:
    """Embed these passages and return the writes, or stop at the first batch that fails.

    Takes `EmbeddingUnit` rather than `Chunk`; see the module docstring for why the queued run
    starts from rows. The units are expected to be read back from `know.chunk`, whose one writer
    is `brain.knowledge.chunk_store`.

    The revision is the caller's, because it is the one part nothing here can know: it is which
    weights are in the volume. `served_embedding_model` refuses an empty one rather than
    defaulting to a first version, and the width is neither of theirs.

    Returns the writes rather than applying them, matching `embed_batch` and `embed_all`: this
    module has no session, and the caller is what holds a transaction to take row locks in,
    which is `brain.knowledge.chunk_store.run_embed_job`.
    """
    if not units:
        raise EmbeddingError(EMBEDDING_NOTHING_IS_A_JOB_THAT_REPORTS_SUCCESS_HAVING_DONE_NOTHING)
    findings = dimension_gaps()
    if findings:
        msg = (
            "this install cannot store what its embedding model produces, so nothing was "
            f"sent: {'; '.join(findings)}"
        )
        raise EmbeddingError(msg)
    model = served_embedding_model(revision=revision)
    batches = plan_batches(units, model=model, max_chunks=max_chunks, budget_bytes=budget_bytes)
    return embed_all(batches, service)


def embed_question(question: str, *, service: EmbeddingService, revision: str) -> EmbeddedVector:
    """A question's vector, from the same service and model a passage is embedded with.

    Never a write, for the reason `embed_policy.A_QUESTIONS_VECTOR_IS_NEVER_A_WRITE` gives, and
    that is why this returns an `EmbeddedVector` and not an `EmbedRun`: there is no value on this
    path that could be applied to `know.chunk`.

    The width refusal is not repeated here and does not need to be. `EmbeddedVector` refuses a
    vector whose length disagrees with the model the server named, and
    `brain.knowledge.search.to_vector_literal` refuses one the column cannot be compared with,
    before a statement is built. An outage raises `EmbeddingUnavailable`, and what that means to
    the person waiting is `embed_policy.outage_response(EmbeddingLeg.QUERY)`, which the caller
    holds.
    """
    model = served_embedding_model(revision=revision)
    return question_vector(service.embed(question_batch(question, model=model)))


# ------------------------------------------------ what is written and what runs it (M7.3.3)


class WiringError(Exception):
    """A declaration about this path that contradicts itself.

    Outside the `brain.core.errors` taxonomy like every refusal in this package, and not an
    `EmbeddingError`: those describe an embedding arrangement that would degrade retrieval,
    and this describes a row in the list below being written wrong.
    """


@dataclass(frozen=True)
class Piece:
    """One step between a chunk needing an embedding and a vector being in the corpus.

    The shape `brain.ops.schedule_runner.Runner` has, including the refusal below, and for the
    reason given there: a row that says it is reached and also says what it still needs reads
    as a step that is wired and is not, and whichever half a reader believes is a coin toss.

    `symbol` is `module:function` because that is what `brain.ops.controls.call_sites` takes,
    and taking the tool's own spelling is what lets the test hold this list to the source
    rather than to a second list somebody keeps beside it.
    """

    #: `module:function`, as `brain.ops.controls.call_sites` spells it.
    symbol: str
    #: What this step does, in the sequence. One line, for the reader of the report.
    step: str
    #: What is missing before anything calls it. Empty means something already does.
    needs: str = ""

    def __post_init__(self) -> None:
        if self.symbol.count(":") != 1 or not all(part.strip() for part in self.symbol.split(":")):
            msg = (
                f"{self.symbol!r} is not a module:function that call_sites could be asked "
                "about, so nothing can check whether this step has a caller"
            )
            raise WiringError(msg)
        if not self.step.strip():
            msg = f"{self.symbol!r} does not say what it does, and the report is the sentence"
            raise WiringError(msg)


#: Every step on the path, in the order it runs, and what each one is waiting for.
#:
#: **Declared rather than discovered, and held to the source by a test rather than trusted.**
#: `brain.ops.controls` makes the same split and states the reason: what a machine can read it
#: reads, and the sentence saying *what a missing piece is* cannot be generated from anything.
#: So the symbols and the `needs` sentences are here, and `tests/unit/test_embed.py` asks
#: `call_sites` whether each claim is still true in both directions.
#:
#: **A caller inside the same module does not count**, because `call_sites` cannot see one: it
#: deliberately ignores a module calling its own function, which is the right answer to the
#: question being asked. That is why the path is split across modules the way it is: the
#: writer, the worker and the tool that asks a question are each somebody else's caller.
#:
#: **The list was rewritten on 2026-09-17 rather than shortened.** Eleven steps, six of them
#: called by nothing, became the fourteen the path actually takes once it runs, and the one
#: that was still an orphan, the first, gained its door later that day.
#:
#: **That door is the connector sync, and what reaches it is narrower than the word suggests.**
#: `brain.ops.connector_sync_run.corpus_sink` hands every document a reading yields to
#: `chunk_store:ingest_document`, with the owner and visibility the reading gave it, on the
#: worker's schedule and with the worker's queue. No reading the console can connect yields a
#: document today (`brain.ops.connector_sync.NO_CONNECTABLE_SOURCE_YIELDS_A_DOCUMENT`), and
#: `brain.member_library.upload` and `lark_wiki.WikiDocument.as_knowledge_item` still build an
#: item nothing hands over, so a corpus on a real install stays empty until one of those is
#: connected. The step is wired; its inputs are the work.
EMBED_PATH: Final[tuple[Piece, ...]] = (
    Piece(
        symbol="brain.knowledge.chunk_store:ingest_document",
        step=(
            "an item and its chunks are written under the owner's reach, and a job to embed "
            "them is handed to the queue once they are committed"
        ),
    ),
    Piece(
        symbol="brain.knowledge.chunking:chunk_document",
        step="a document's text becomes chunks carrying the document's permissions",
    ),
    Piece(
        symbol="brain.knowledge.embed_queue:units_for",
        step=(
            "the chunks become an id and a text each, so a chunk no batch could carry is "
            "refused at the door rather than by every job after it"
        ),
    ),
    Piece(
        symbol="brain.knowledge.embed_queue:embed_job",
        step="the work is queued as an ordinal window and the owner it runs for",
    ),
    Piece(
        symbol="brain.knowledge.chunk_store:run_embed_job",
        step=(
            "a worker reads the window back under the owner's reach as it stands, embeds it, "
            "and writes two columns of each row or nothing"
        ),
    ),
    Piece(
        symbol="brain.knowledge.embed:embed_units",
        step="the calls below, in the one order that produces a resumable run",
    ),
    Piece(
        symbol="brain.knowledge.embed_policy:served_embedding_model",
        step="the identity recorded beside every vector, at the column's width",
    ),
    Piece(
        symbol="brain.knowledge.embed_queue:plan_batches",
        step="the units are cut into batches that each fit one queue slot",
    ),
    Piece(
        symbol="brain.knowledge.embed_policy:embed_all",
        step="the batches are sent in order and the run stops at the first failure",
    ),
    Piece(
        symbol="brain.knowledge.embed_queue:embed_batch",
        step="one batch is sent and the response is turned into updates",
    ),
    Piece(
        symbol="brain.ops.inference_client:make_client",
        step="the one implementation of EmbeddingService, pointed at this install's server",
    ),
    Piece(
        symbol="brain.knowledge.embed:embed_question",
        step="the other leg: a question's vector, from the same model, which is never a write",
    ),
    Piece(
        symbol="brain.knowledge.embed_policy:question_vector",
        step="the response to a question is read as one vector for the one id that was sent",
    ),
    Piece(
        symbol="brain.knowledge.search:vector_query",
        step=(
            "the nearest-neighbour leg, asked with that vector and its model, the asker's "
            "reach conjoined before the limit"
        ),
    ),
)


def wiring_gaps(pieces: Sequence[Piece] = EMBED_PATH) -> tuple[str, ...]:
    """Every step on this path that nothing calls, and what each one is waiting for.

    A report rather than a gate, in the shape `brain.ops.schedule_runner.runner_gaps` takes and
    for the same reason: a check asserting the path complete would be red on arrival for as
    long as any step is missing, and switched off within the week.

    **Deliberately not folded into `policy_gaps`**, and the reason is a test somebody else
    wrote. `policy_gaps` is what `brain.ops.worker.advisories` prints on every worker start,
    and `tests/unit/test_worker.py::test_an_install_whose_declared_width_is_its_models_has_`
    `nothing_to_report` asserts that a correctly configured install has nothing there at all.
    Its docstring argues why: a surface that reports on every install for ever is one an
    operator learns to scroll past, which would cost the width finding its audience. This list
    is a fact about how far the product has got rather than about one deployment, so it is
    printed by a command somebody runs and not by a container that starts.

    In declared order rather than sorted, so the output reads in the order the path runs and
    the first line is the earliest thing missing.
    """
    return tuple(
        f"{one.symbol} ({one.step}) is called by nothing: it needs {one.needs}"
        for one in pieces
        if one.needs
    )


# ------------------------------------------------------------------ the command

#: What an operator runs. Named here so a message telling somebody how to check this and the
#: module they check it with cannot drift apart.
EMBED_COMMAND: Final = "python -m brain.knowledge.embed"

#: The command's refusal: this install could not say where its inference server is.
EXIT_REFUSED: Final = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=EMBED_COMMAND,
        description="Report whether this install could embed, and what the leg still needs.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="the only mode; accepted so the command reads the same as the worker's",
    )
    return parser


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    """`python -m brain.knowledge.embed --check`: can this install embed, and what is missing.

    Four questions and they fail in different places, so they are printed separately rather
    than as one list. Where the text would go is this install's configuration and is one of the
    two that can refuse. Which weights the server holds is the other: an unset revision is an
    install with no vector leg, said in a sentence, and a revision that is not one is refused.
    What is wrong that starting will not fix is `policy_gaps`, which is the same list
    `brain.ops.worker.advisories` prints, repeated here because somebody asking this question is
    not usually reading a worker's startup output. What is not built is `wiring_gaps`, which is
    a property of the product and is the same on every install.

    The environment is a parameter defaulting to the real one, matching
    `brain.ops.worker.main`, so every mode can be tested without one.
    """
    _parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    from brain.settings import process_environment

    environment = process_environment() if env is None else env

    try:
        endpoint = embedding_endpoint(environment)
        revision = embedding_revision(environment)
    except (EmbeddingUnavailable, EmbeddingError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"text to be embedded is sent to {ENDPOINT_SETTING}={endpoint}, and nowhere else")
    for finding in endpoint_conflicts(
        endpoint=endpoint, configured=environment.get(APP_ENDPOINT_SETTING, "")
    ):
        print(f"  - {finding}")
    if revision is None:
        print(
            f"nothing is embedded on this install: {REVISION_SETTING} is unset, so documents "
            "are found by text search alone"
        )
    else:
        print(f"vectors are recorded as {served_embedding_model(revision=revision).identity}")

    advisories = policy_gaps()
    print(
        "wrong with this install and not fixed by starting:"
        if advisories
        else "nothing wrong with this install"
    )
    for finding in advisories:
        print(f"  - {finding}")

    missing = wiring_gaps()
    print(f"not built yet, {len(missing)} of {len(EMBED_PATH)} steps on this path:")
    for finding in missing:
        print(f"  - {finding}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
