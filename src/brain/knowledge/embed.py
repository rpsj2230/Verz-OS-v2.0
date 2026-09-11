"""The sequence from a chunk needing an embedding to the writes that store one, and what is
still missing before anything runs it.

`brain.knowledge.embed_queue` cuts work into batches, `brain.knowledge.embed_policy` holds
every decision taken before a socket is opened, `brain.ops.inference` holds the wire contract
and `brain.ops.inference_client` is the only thing that speaks to the server. Four modules,
each correct, and **until this one there was no order in which to call them**. A caller had to
know to build the model with `served_embedding_model`, drop the permissions with `units_for`,
cut the work with `plan_batches` against that same model, and stop at the first failure with
`embed_all`. Four calls in one order, discoverable only by reading four files, which is the
shape of thing that gets assembled differently by the second person to need it.

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

**What leaves this system on this path, exactly.** One POST per batch, to the one address
`embedding_endpoint` resolves, carrying `brain.ops.inference.embedding_request`'s two keys: a
model block of name, revision and width, and one input per chunk of an id and a text.
`EmbeddingUnit` has two fields and no third that could hold a scope, `units_for` takes `Chunk`
objects and keeps two of their nine attributes, and the request is `MappingProxyType` at every
level so nothing can add a key to it on the way out. Three things stop it sending more and all
three are structural rather than a convention: the value cannot carry a permission, the mapping
cannot grow one, and the network the server sits on is declared `internal: true`, so a
container on it has no route off the host. What is **not** structural is the host: nothing here
can tell an internal name from a public one, and `endpoint_refusals` says so rather than
shipping a list of provider hostnames.

**Nothing calls `embed_chunks`, and that is a fact about the queue rather than about this
module.** `embed_job` builds the job and nothing enqueues one; `know.chunk` is a table and a
set of queries with no writer, so the writes this returns have nowhere to be applied; and the
inference server has no published image. `wiring_gaps` names each of those by symbol, in the
order the path runs, and `tests/unit/test_embed.py` holds every entry to what
`brain.ops.controls.call_sites` reads out of the source, so a step that gains a caller and is
still listed here is a red test. That is the shape `brain.ops.schedule_runner.runner_gaps`
takes for twelve controls, and the reason is the same: a written-down omission is not a check.

**M7.3.3 is not claimed and cannot be**, which is why `Task ids` below says none. The leaf is
"local embedding via Qwen3 through the inference server" and nothing here has ever embedded
anything: `docker-compose.inference.yml` names an image that does not exist, item 25 records
the container as roughly 3.3 GB over what the host has, and no weights have been pulled. What
is finished is everything on this side of the socket.

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

from brain.knowledge.chunking import Chunk
from brain.knowledge.embed_policy import (
    APP_ENDPOINT_SETTING,
    ENDPOINT_SETTING,
    EmbeddingUnavailable,
    EmbedRun,
    dimension_gaps,
    embed_all,
    embedding_endpoint,
    endpoint_conflicts,
    policy_gaps,
    served_embedding_model,
)
from brain.knowledge.embed_queue import EmbeddingService, plan_batches, units_for
from brain.knowledge.embedding import DEFAULT_BATCH_SIZE, EmbeddingError

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


def embed_chunks(
    chunks: Sequence[Chunk],
    *,
    service: EmbeddingService,
    revision: str,
    max_chunks: int = DEFAULT_BATCH_SIZE,
    budget_bytes: int | None = None,
) -> EmbedRun:
    """Embed these chunks and return the writes, or stop at the first batch that fails.

    Takes `Chunk` rather than text for the reason `units_for` does: `chunk_document` is the
    only thing in this system that copies a document's permissions onto a passage, and a
    caller that could assemble embedding work out of loose strings is a caller that can embed
    text no row will ever be found by.

    The revision is the caller's, because it is the one part nothing here can know: it is which
    weights are in the volume. `served_embedding_model` refuses an empty one rather than
    defaulting to a first version, and the width is neither of theirs.

    Returns the writes rather than applying them, matching `embed_batch` and `embed_all`: this
    module has no session, and the caller is what holds a transaction to take row locks in.
    There is no such caller today; see `wiring_gaps`.
    """
    if not chunks:
        raise EmbeddingError(EMBEDDING_NOTHING_IS_A_JOB_THAT_REPORTS_SUCCESS_HAVING_DONE_NOTHING)
    findings = dimension_gaps()
    if findings:
        msg = (
            "this install cannot store what its embedding model produces, so nothing was "
            f"sent: {'; '.join(findings)}"
        )
        raise EmbeddingError(msg)
    model = served_embedding_model(revision=revision)
    batches = plan_batches(
        units_for(chunks), model=model, max_chunks=max_chunks, budget_bytes=budget_bytes
    )
    return embed_all(batches, service)


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
#: deliberately ignores a module calling its own function, so `embed_chunks` being called by
#: the command at the bottom of this file leaves it an orphan by that tool's definition, which
#: is the right answer to the question being asked. Nothing schedules it.
EMBED_PATH: Final[tuple[Piece, ...]] = (
    Piece(
        symbol="brain.knowledge.chunking:chunk_document",
        step="a parsed document becomes chunks carrying the document's permissions",
        needs=(
            "a parse. brain.knowledge.ingest decides what may be admitted and nothing turns an "
            "admitted file into blocks: M7.2.1 is Docling, which item 31 put behind the same "
            "inference server this leaf is waiting on"
        ),
    ),
    Piece(
        symbol="brain.knowledge.embed_queue:units_for",
        step="the chunks become an id and a text each, with the permissions left behind",
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
        needs=(
            "a process that holds a queue slot and a batch. The address is resolved now, by "
            "embedding_endpoint, and what is absent is anything that would build a client: no "
            "embedding job has ever been enqueued, because embed_job has no caller"
        ),
    ),
    Piece(
        symbol="brain.knowledge.embed_queue:embed_job",
        step="the work is queued as an ordinal window rather than a list of chunk ids",
        needs=(
            "an ingestion path that enqueues one when a document's chunks are written. "
            "chunk_document is where those chunks would come from and nothing calls it either, "
            "so this is the same gap one step earlier"
        ),
    ),
    Piece(
        symbol="brain.knowledge.embed:embed_chunks",
        step="the four calls above, in the one order that produces a resumable run",
        needs=(
            "a worker task registered against knowledge.embed, and somewhere to apply what it "
            "returns. know.chunk is a table and a set of queries with no writer in this "
            "repository, so an EmbeddingWrite is an update nobody performs"
        ),
    ),
    Piece(
        symbol="brain.knowledge.embed_policy:question_vector",
        step="the other leg: a question's vector, which is never a write",
        needs=(
            "a retrieval path that embeds the question before it searches. brain.knowledge."
            "assembly composes an answer out of rows somebody else fetched, and nobody fetches "
            "them"
        ),
    ),
    Piece(
        symbol="brain.knowledge.search:vector_query",
        step="the nearest-neighbour leg, asked with a vector and a model identity",
        needs=(
            "the same retrieval path, plus a session. It is still called with a vector nobody "
            "produces, which is the sentence brain.knowledge.embed_policy has carried since the "
            "seam was declared"
        ),
    ),
)


def wiring_gaps(pieces: Sequence[Piece] = EMBED_PATH) -> tuple[str, ...]:
    """Every step on this path that nothing calls, and what each one is waiting for.

    A report rather than a gate, in the shape `brain.ops.schedule_runner.runner_gaps` takes and
    for the same reason: most of this path is unwired today and a check asserting otherwise
    would be red on arrival and switched off within the week.

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

    Three questions and they fail in different places, so they are printed separately rather
    than as one list. Where the text would go is this install's configuration and is the only
    one that can refuse. What is wrong that starting will not fix is `policy_gaps`, which is
    the same list `brain.ops.worker.advisories` prints, repeated here because somebody asking
    this question is not usually reading a worker's startup output. What is not built is
    `wiring_gaps`, which is a property of the product and is the same on every install.

    The environment is a parameter defaulting to the real one, matching
    `brain.ops.worker.main`, so every mode can be tested without one.
    """
    _parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    import os

    environment = os.environ if env is None else env

    try:
        endpoint = embedding_endpoint(environment)
    except EmbeddingUnavailable as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"text to be embedded is sent to {ENDPOINT_SETTING}={endpoint}, and nowhere else")
    for finding in endpoint_conflicts(
        endpoint=endpoint, configured=environment.get(APP_ENDPOINT_SETTING, "")
    ):
        print(f"  - {finding}")

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
