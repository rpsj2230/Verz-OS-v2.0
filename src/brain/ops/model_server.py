"""The model server as an install chooses it: which parts, how big, and whether it fits.

`docs/needs-rupash.md` item 120 sized this service as one container holding three models at once,
3,072 MiB with 512 for a document worker and 256 for a file store, and said the three optional
services it competed with (the model server, the trace ledger and the personal data detector) would
not fit the owner's server together. On 2026-10-14 the owner added a constraint that changes the
shape rather than the size: the system should not need more memory than the server has, and the
kernel's cache has to be taken into account. This module is that shape. **Five choices, each
rejected design named, so the next person to want the old one knows what it cost.**

**One part is resident at a time, so the limit is the largest part and never the sum.** The server
has five parts that can be switched on one by one (`Part`): the layout reader, the scanned-page
reader, a general reader for other formats, the embedding model and the entity finder. Item 120's
3,072 MiB was the sum of what three of them hold if all are loaded together, and nothing in the work
needs that: a document is read, then a passage is embedded, and the queue that carries both has no
deadline shorter than a model load. So the supervisor inside the container (`inference_server`)
loads one part, answers its requests, and unloads it before it loads another. The limit is then
`BASE_MIB` plus the largest part, and an install that chooses only the embedding model holds a third
of what item 120 sized. Rejected: all parts resident, which is the sum; and one container per part,
which is the same sum with a second copy of the runtime in each, and a second set of limits to keep
equal to a second set of budget rows.

**Cache is counted twice, on purpose, and the two figures are different questions.** The kernel
charges the pages of a memory-mapped weights file to the container that read them, and gives them
back under pressure. So a part's footprint is two numbers: `anonymous_mib`, which nothing can take
back and which is what the host must really have, and `mapped_mib`, which is cache the part wants
to stay hot but which the kernel will evict before it kills anything. The container's limit has to
cover both, because a limit under the mapped weights makes the part read them from disk again for
every request (it works, slowly, and the kernel's reclaim fights the part for the whole run), and
the host check has to count only the first, because `MemAvailable` already treats cache as spare.
Judging the host by its limits alone, as `brain.ops.overlays` does for every other container,
would call the owner's server full when it holds 7.4 GB of memory it can hand over; judging it by
`MemAvailable` alone would say yes now and be wrong when the neighbours grow. **So there are two
checks, and the second is the supervisor's own, made at the moment it would load a part**
(`inference_server.admit`).

**Idle stops the part's process, and the container stays up holding `BASE_MIB`.** The brief was a
server that starts when work arrives and stops after an idle time. Stopping the container needs
something outside the container to start it again, and there are two candidates, both rejected here.
A process with the docker socket would be a program with root on the host reachable from the network
the documents travel on, which is the most sensitive thing an install has. A timer on the host would
be a second thing every server has to have installed by hand, and `ops/deploy/brain-autodeploy`
shows what that costs: its copy on the first install was three weeks behind. What the supervisor
can do alone is run each part as a child process and end it, which returns its memory to the kernel
for certain, where unloading a model inside a Python process usually does not. **What is held while
nothing is waiting is `BASE_MIB`, and what is held while something is, is a part.** The honest cost
is that the idle container is a small cost the budget cannot take to nothing, and the limit the plan
counts is the working figure, not the idle one, because an idle server can be asked at any moment.

**Every figure here is a judgement or arithmetic, and says which.** `PartSizing.basis` is required
prose for the reason `brain.ops.inference.ServedModel.sizing_basis` is: a number in a memory budget
with no stated origin cannot be checked by anybody. `measured` is False for every part, and nothing
in this module may set it True: the server reports its own peak for every batch it serves
(`brain.ops.model_server_store` keeps them), and `suggested_limit_mib` is what an administrator
reads to replace a judgement with a measurement. There is no server on a host this was written on,
no weights and no image, so there was nothing to measure and no figure here is described as if there
were.

**A configuration the host cannot hold is refused in words, in three places, by two costings.** On
the Settings screen and in the release's plan, which are one costing
(`brain.ops.overlays.plan_in_room`: the limit against what the server last measured it has left,
asked at save with the four settings as they would stand and at deploy of the measured host), and by
the supervisor, which refuses a part when `MemAvailable` is under what the part cannot give back.
This module holds no second sum of what a server has, which would be a second place for the budget
to be subtly wrong; the third is the one fact the other two cannot know, which is the host now.

**What decides what a person is told, and what is read from where.** Nothing here reads the
environment directly: the four settings are `brain.install` values, read through `value_of`, so an
install's choice is the one source for the settings screen, the plan, the container's environment
and the worker's own start-up check.

Task ids: M7.2.1, M7.2.3, M7.2.4, M7.3.3, M7.7.11, M32.2.1.2
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from brain.install import value_of
from brain.knowledge.embed_queue import batch_budget_bytes
from brain.knowledge.ingest import ABSOLUTE_MAX_BYTES, TYPE_LIMITS, Container, ceiling_for
from brain.knowledge.parse_budget import MIB, PARSE_EXPANSION

# ------------------------------------------------------------------ written-down reasons

#: Why the limit is the largest part and not the sum of them.
ONE_PART_IS_RESIDENT_AT_A_TIME: Final = (
    "The supervisor loads one part, answers its requests and ends its process before it loads "
    "another, so the container's limit is the base plus the largest part and not the sum. Item 120 "
    "sized the sum, which is what three models cost if all are held at once, and no work needs "
    "that: a document is read and then a passage is embedded, and the queue between them waits "
    "longer than a model takes to load. An install that runs two parts therefore pays for the "
    "larger of them, and the price of switching between the two is a model load, which is time and "
    "not memory."
)

#: Why mapped weights and anonymous memory are two figures.
CACHE_IS_COUNTED_AS_CACHE: Final = (
    "The kernel charges the pages of a memory-mapped weights file to the container that read "
    "them and takes them back under pressure before it kills anything. Anonymous memory is the "
    "opposite: nothing can take it back. The container's limit has to cover both, because a limit "
    "under the mapped weights makes the part read them from disk again for every request; the "
    "host has to be able to give only the anonymous figure, because it is the only one the "
    "kernel cannot reclaim. Judging a host by container limits alone calls a server full that "
    "holds gigabytes of cache it would hand over, and judging it by what is free this second says "
    "yes now and is wrong when a neighbour grows."
)

#: Why an idle server holds its base and not nothing.
IDLE_ENDS_THE_PARTS_PROCESS_AND_NOT_THE_CONTAINER: Final = (
    "Starting a stopped container again needs a program with the docker socket, which would be "
    "root on the host reachable from the network documents travel on, or a timer on the host, "
    "which is a second thing every server must have installed by hand and which nobody can update "
    "from a release. Ending the part's own process needs neither and returns its memory to the "
    "kernel for certain, which unloading a model inside a Python process usually does not. The "
    "cost is that an idle server still holds its base, and the plan counts the working figure "
    "because an idle server can be asked at any moment."
)

#: Why no figure here is described as measured.
EVERY_FIGURE_HERE_IS_A_JUDGEMENT_UNTIL_THE_SERVER_REPORTS_ITS_OWN_PEAK: Final = (
    "There is no model server, no weights and no image on the host these figures were written "
    "on, so none of them has been measured and each `PartSizing` says what it is derived from. "
    "The server reports its peak for every batch it serves, the product keeps those, and the "
    "settings screen shows what limit they suggest, so a judgement is replaced by a measurement "
    "when there is one and never by a better-sounding judgement."
)

# ------------------------------------------------------------------ the settings

#: The four installation settings, named once. `brain.install` declares them; this module is the
#: one reader, and nothing else may read them or their environment variables.
PARTS_SETTING: Final = "INSTALL_MODEL_PARTS"
IDLE_SETTING: Final = "INSTALL_MODEL_IDLE_SECONDS"
MEMORY_SETTING: Final = "INSTALL_MODEL_MEMORY_MIB"
UPLOAD_SETTING: Final = "INSTALL_MODEL_UPLOAD_MB"

#: The word meaning the memory limit is worked out from the parts, and the setting's default.
AUTOMATIC: Final = "auto"

#: What an install that names nothing gets. Embedding alone, because it is the smallest part that
#: does the most: it is the one the search leg waits on, and every other part is a way of reading a
#: document better, which an install can add when it has the room.
DEFAULT_PARTS_TEXT: Final = "embedding"

#: How long a part stays loaded with nothing to do, and the bounds a person may choose within. Five
#: minutes is longer than a queue's gap between two documents of one upload and shorter than the
#: time a forgotten part would sit holding memory; the bounds stop a value that means "never stop"
#: (which is a model server held resident) and one that reloads between every two requests.
DEFAULT_IDLE_SECONDS: Final = 300
IDLE_BOUNDS: Final = (30, 86_400)

#: The largest document the server is sized to read, in MiB. **Decided by the owner on 2026-10-05
#: (needs-rupash 119, "C now, then A once row 2 of item 120 runs", and its recommendation of 25 MB
#: for every type).** One figure for every document is easy to say, covers nearly all everyday
#: documents and costs the least memory of the choices that do not refuse ordinary files. It is
#: configuration and not a constant for the reason everything else here is: another company's
#: documents are a different size.
DEFAULT_UPLOAD_MB: Final = 25
UPLOAD_BOUNDS: Final = (1, ABSOLUTE_MAX_BYTES // MIB)

#: The least a limit may be set to by hand, in MiB: the base and nothing else. A limit under what
#: the chosen parts need is refused by `limit_problem`, which names the figure.
ROUND_MIB: Final = 64

#: What the supervisor holds with no part loaded: the interpreter, the HTTP server and the meter.
#: A judgement, in the register of `brain.knowledge.parse_budget.PARSE_WORKER_RESERVE_MIB`, which
#: sizes the same kind of thing (an interpreter and its imports) at 64 for a worker that imports
#: the database driver and the object-store client; this imports neither.
BASE_MIB: Final = 64

#: What a part's own runtime holds beyond its weights when it is torch on a CPU: the library, the
#: tokenisers and the allocator's arenas. Carried over unchanged from
#: `brain.ops.inference.INFERENCE_RUNTIME_RESERVE_MIB`, where it was a judgement for the same
#: reason, and it is still one.
TORCH_RUNTIME_MIB: Final = 512


class ModelServerError(Exception):
    """Raised for a model server setting no install could run, with the sentence to show."""


class Part(enum.StrEnum):
    """What the model server can do, one switch each. Closed: the sizing is a table over it."""

    #: Tables and page layout, in PDFs and Office files. M7.2.1.
    LAYOUT = "layout"
    #: Characters read from the image of a page. M7.2.4.
    OCR = "ocr"
    #: A general reader for the formats the layout reader cannot open. M7.2.3.
    TIKA = "tika"
    #: Passages and questions as vectors. M7.3.3.
    EMBEDDING = "embedding"
    #: Names and details the standard rules miss. M32.2.1.2.
    ENTITIES = "entities"


#: The path each part is posted to. Spelled as `inference_server.gateway.ROUTES`, which a test holds
#: this equal to, and as `brain.ops.inference_client.EMBED_PATH` for the embedding part: a path
#: spelled differently on the two sides is a 404, which `classify` reads as this system's own fault
#: and the queue does not retry.
PATH_OF_PART: Final[Mapping[Part, str]] = MappingProxyType(
    {
        Part.EMBEDDING: "/embed",
        Part.LAYOUT: "/parse",
        Part.OCR: "/ocr",
        Part.TIKA: "/extract",
        Part.ENTITIES: "/entities",
    }
)

#: The parts that read a document, and so are sized from the largest upload.
DOCUMENT_PARTS: Final = frozenset({Part.LAYOUT, Part.OCR, Part.TIKA})

#: The containers each document part reads, which decides how much bigger than the file its working
#: set is. Over the door's own `PARSE_EXPANSION` table, so a container added there is answered here.
CONTAINERS_READ: Final[Mapping[Part, tuple[Container, ...]]] = MappingProxyType(
    {
        Part.LAYOUT: (Container.PDF, Container.ZIP),
        Part.OCR: (Container.PDF, Container.PNG, Container.JPEG),
        Part.TIKA: (Container.PDF, Container.ZIP, Container.TEXT),
    }
)


@dataclass(frozen=True)
class PartSizing:
    """What one part holds while it is loaded, and where each figure came from.

    `basis` is required and is the whole reason this is a class and not two integers. `measured`
    defaults to False so that describing a figure as measured is a deliberate edit, and the test
    that reads this table says that none of them is.
    """

    part: Part
    #: What runs the model, so the figure below can be checked against the runtime that makes it.
    engine: str
    model: str
    #: The numeric format the weights are held in, which is the multiplier on their size. Named
    #: here because choosing it is choosing the container's size.
    quantisation: str
    anonymous_mib: int
    mapped_mib: int
    basis: str
    measured: bool = False

    def __post_init__(self) -> None:
        if self.anonymous_mib < 1:
            msg = f"part {self.part.value!r} declares no memory it cannot give back"
            raise ModelServerError(msg)
        if self.mapped_mib < 0:
            msg = f"part {self.part.value!r} declares a negative mapped size"
            raise ModelServerError(msg)
        if not self.basis.strip():
            msg = (
                f"part {self.part.value!r} does not say where its figures came from; a memory "
                "figure with no stated origin cannot be checked by anybody"
            )
            raise ModelServerError(msg)


#: One row per part. **Smaller choices than item 120's, each named with why.**
#:
#: Embedding is Qwen3-Embedding-0.6B, the smallest of the Qwen3 embedding models and the one the
#: leaf names, as a GGUF file quantised to 8 bits and run by llama.cpp. 8-bit rather than 16 halves
#: the weights (the 16-bit file is about 1.2 GB) at a loss in retrieval quality that is small for
#: an 8-bit format, and rather than 4 because the 4-bit formats lose more and this install has no
#: way yet to measure what they lose on its own documents. llama.cpp rather than torch because it
#: maps the file and holds no framework runtime, which is most of the difference between 0.9 GB and
#: 1.5 GB for the same weights. Larger choices are configuration: the file the server loads is
#: whatever sits in its weights volume.
SIZING: Final[Mapping[Part, PartSizing]] = MappingProxyType(
    {
        Part.EMBEDDING: PartSizing(
            part=Part.EMBEDDING,
            engine="llama.cpp, weights memory-mapped",
            model="qwen3-embedding-0.6b",
            quantisation="Q8_0",
            anonymous_mib=256,
            mapped_mib=640,
            basis=(
                "mapped: the 8-bit file of a 0.6e9-parameter model is about 0.64e9 bytes, which "
                "is the published file size rounded up to 640 MiB, not a file this repository has "
                "downloaded. anonymous: the key and value cache is 2 x 28 layers x 8 key-value "
                "heads x 128 dimensions x 2 bytes = 112 KiB a token, so 112 MiB for the 1,024-"
                "token window the supervisor runs one passage at a time in; compute buffers and "
                "llama.cpp's own state are judged at 100 and 44 MiB. The request body is added by "
                "`working_mib`"
            ),
        ),
        Part.ENTITIES: PartSizing(
            part=Part.ENTITIES,
            engine="torch on a CPU",
            model="gliner",
            quantisation="fp32",
            anonymous_mib=832 + TORCH_RUNTIME_MIB,
            mapped_mib=0,
            basis=(
                "carried over from `brain.ops.inference.SERVED_MODELS`: roughly 0.21e9 parameters "
                "at 4 bytes is 801 MiB, rounded up to 832, plus the torch runtime reserve. 32-bit "
                "because the published checkpoint is, and nothing here has checked that a "
                "quantised copy returns the same character offsets, and a span that moves by one "
                "is the half-redacted name `brain.ops.pii` spends a paragraph on"
            ),
        ),
        Part.LAYOUT: PartSizing(
            part=Part.LAYOUT,
            engine="docling on torch on a CPU",
            model="docling-layout-and-tableformer",
            quantisation="fp32",
            anonymous_mib=512 + TORCH_RUNTIME_MIB,
            mapped_mib=0,
            basis=(
                "carried over from `brain.ops.inference.SERVED_MODELS`, where the 512 MiB for the "
                "layout and table models was a judgement because nobody had installed Docling, "
                "plus the torch runtime reserve. The document's own working set is added by "
                "`working_mib` from the largest upload"
            ),
        ),
        Part.OCR: PartSizing(
            part=Part.OCR,
            engine="tesseract",
            model="tesseract-eng-fast",
            quantisation="integer",
            anonymous_mib=256,
            mapped_mib=0,
            basis=(
                "a judgement. Tesseract's English fast model is a few megabytes and the engine "
                "holds a page image, a binarised copy and a layout analysis at a time: one page at "
                "300 dots an inch is 2,550 x 3,300 pixels, 8 MiB at a byte each, and the engine "
                "keeps a few copies. The document's own working set is added by `working_mib`"
            ),
        ),
        Part.TIKA: PartSizing(
            part=Part.TIKA,
            engine="apache tika server, a JVM",
            model="tika",
            quantisation="none",
            anonymous_mib=512,
            mapped_mib=0,
            basis=(
                "a judgement: a 384 MiB heap ceiling for the server, which is what a JVM given "
                "`-Xmx` stays inside, and 128 MiB for the metaspace, thread stacks and the code "
                "cache the heap ceiling does not cover"
            ),
        ),
    }
)


def upload_working_mib(part: Part, upload_mb: int) -> int:
    """What reading the largest upload costs a document part, over and above its model.

    Over the door's own tables: for each type this part reads, the smaller of the install's upload
    limit and that type's ceiling, times that container's expansion, and the largest of them. A
    figure that ignored the type's ceiling would size the scanned-page reader for a 25 MiB image
    the door never admits (images stop at 10).
    """
    containers = CONTAINERS_READ.get(part)
    if containers is None:
        return 0
    limit_bytes = upload_mb * MIB
    worst = max(
        min(limit_bytes, ceiling_for(media_type)) * PARSE_EXPANSION[limit.container]
        for media_type, limit in TYPE_LIMITS.items()
        if limit.container in containers
    )
    return -(-worst // MIB)


def request_working_mib(part: Part) -> int:
    """What one request body costs a part that is sent text, parsed and answered.

    Three copies of the largest body the embedding batch may be: the bytes read off the socket,
    the decoded text, and the parsed request. The same three-copy rule `parse_budget` states for a
    file. Entities are sent one passage and cost nothing worth a line.
    """
    if part is not Part.EMBEDDING:
        return 0
    return -(-3 * batch_budget_bytes() // MIB)


def working_mib(part: Part, upload_mb: int) -> int:
    """The memory a part needs beyond its model while it serves its largest request."""
    return upload_working_mib(part, upload_mb) + request_working_mib(part)


def anonymous_peak_mib(part: Part, upload_mb: int) -> int:
    """What the part cannot give back while it is loaded and serving its largest request."""
    return SIZING[part].anonymous_mib + working_mib(part, upload_mb)


def part_peak_mib(part: Part, upload_mb: int) -> int:
    """What the container holds with this part loaded: the base, the part and its mapped weights."""
    return BASE_MIB + anonymous_peak_mib(part, upload_mb) + SIZING[part].mapped_mib


def rounded_up(mib: int) -> int:
    """A limit in whole `ROUND_MIB` steps, never lower than what it was asked to hold."""
    return -(-mib // ROUND_MIB) * ROUND_MIB


# ------------------------------------------------------------------ one install's choice


@dataclass(frozen=True)
class ModelServerConfig:
    """What this install chose, already checked against what it can mean.

    Frozen and checked on construction for the reason `brain.ops.wiring.Component` is: a value
    that can be built wrong is a value every reader must remember to check.
    """

    parts: tuple[Part, ...] = (Part.EMBEDDING,)
    idle_seconds: int = DEFAULT_IDLE_SECONDS
    #: The limit an administrator set by hand, in MiB, or None to work it out from the parts.
    memory_override_mib: int | None = None
    upload_mb: int = DEFAULT_UPLOAD_MB

    def __post_init__(self) -> None:
        if not self.parts:
            msg = "no part is chosen, so the model server would hold memory and do nothing"
            raise ModelServerError(msg)
        if len(set(self.parts)) != len(self.parts):
            msg = "a part is named twice, which a person writing it twice did not mean"
            raise ModelServerError(msg)
        low, high = IDLE_BOUNDS
        if not low <= self.idle_seconds <= high:
            msg = f"an idle time of {self.idle_seconds} seconds is outside {low} to {high}"
            raise ModelServerError(msg)
        low_mb, high_mb = UPLOAD_BOUNDS
        if not low_mb <= self.upload_mb <= high_mb:
            msg = f"an upload size of {self.upload_mb} MB is outside {low_mb} to {high_mb}"
            raise ModelServerError(msg)
        if self.memory_override_mib is not None and self.memory_override_mib < BASE_MIB:
            msg = f"a limit of {self.memory_override_mib} MiB is under the {BASE_MIB} MiB base"
            raise ModelServerError(msg)

    def has(self, part: Part) -> bool:
        """Whether this install chose the part."""
        return part in self.parts

    @property
    def reads_documents(self) -> bool:
        """Whether any chosen part is sent a document, which is what the upload limit sizes."""
        return any(one in DOCUMENT_PARTS for one in self.parts)


def parts_from(text: str) -> tuple[Part, ...]:
    """The parts a setting's text names, in the order written, or a refusal naming the choices.

    Refuses a name it does not know rather than skipping it: a typo that chose nothing would read
    on the server as a part that failed to load, and in the setting as one that runs.
    """
    names = [one.strip().casefold() for one in text.split(",") if one.strip()]
    choices = ", ".join(one.value for one in Part)
    if not names:
        msg = f"write one or more parts of the model server, separated by commas: {choices}"
        raise ModelServerError(msg)
    found: list[Part] = []
    for name in names:
        try:
            found.append(Part(name))
        except ValueError:
            msg = f"{name!r} is not a part of the model server; the parts are {choices}"
            raise ModelServerError(msg) from None
    return tuple(found)


def _whole_number(text: str, what: str) -> int:
    try:
        return int(text.strip())
    except ValueError:
        msg = f"{what} is written as a whole number, and {text.strip()!r} is not one"
        raise ModelServerError(msg) from None


def config_from(
    *,
    parts: str = DEFAULT_PARTS_TEXT,
    idle: str = str(DEFAULT_IDLE_SECONDS),
    memory: str = AUTOMATIC,
    upload: str = str(DEFAULT_UPLOAD_MB),
) -> ModelServerConfig:
    """One configuration from the four settings' text, or a refusal a person can act on."""
    memory_text = memory.strip().casefold()
    return ModelServerConfig(
        parts=parts_from(parts),
        idle_seconds=_whole_number(idle, "the idle time"),
        memory_override_mib=(
            None if memory_text == AUTOMATIC else _whole_number(memory, "the memory limit")
        ),
        upload_mb=_whole_number(upload, "the upload size"),
    )


def read_config(
    env: Mapping[str, str] | None = None, saved: Mapping[str, str] | None = None
) -> ModelServerConfig:
    """This install's choice, read through the one installation reader."""
    return config_from(
        parts=value_of(PARTS_SETTING, env=env, saved=saved),
        idle=value_of(IDLE_SETTING, env=env, saved=saved),
        memory=value_of(MEMORY_SETTING, env=env, saved=saved),
        upload=value_of(UPLOAD_SETTING, env=env, saved=saved),
    )


# ------------------------------------------------------------------ what it needs


@dataclass(frozen=True)
class Requirement:
    """What a configuration asks of a host, as two figures and the part that sets each."""

    #: What the container may hold: the base, the largest part and its mapped weights, rounded up.
    limit_mib: int
    #: What the host must be able to give and cannot take back: the base and the largest part's
    #: anonymous memory. Never rounded, because it is compared with a measurement, not provisioned.
    non_reclaimable_mib: int
    #: Each chosen part's own peak, so a screen can say which one sets the limit.
    by_part: Mapping[Part, int]
    largest: Part


def requirement(config: ModelServerConfig) -> Requirement:
    """What this configuration needs. The largest part sets both figures; the rest wait."""
    by_part = {one: part_peak_mib(one, config.upload_mb) for one in config.parts}
    largest = max(config.parts, key=lambda one: by_part[one])
    non_reclaimable = max(non_reclaimable_mib(one, config.upload_mb) for one in config.parts)
    return Requirement(
        limit_mib=rounded_up(by_part[largest]),
        non_reclaimable_mib=non_reclaimable,
        by_part=MappingProxyType(by_part),
        largest=largest,
    )


def effective_limit_mib(config: ModelServerConfig) -> int:
    """The limit the plan costs and the container starts with: the override, or the derived one."""
    if config.memory_override_mib is not None:
        return config.memory_override_mib
    return requirement(config).limit_mib


def limit_problem(config: ModelServerConfig) -> str:
    """Why a limit set by hand is too small for what was chosen, or empty when it is not.

    A limit under the need is refused and a limit over it is not: a larger one wastes memory the
    plan will say it is spending, and a smaller one is a part killed on its first large request,
    which is the failure with no symptom until a document is large.
    """
    if config.memory_override_mib is None:
        return ""
    needed = requirement(config)
    if config.memory_override_mib >= needed.limit_mib:
        return ""
    return (
        f"{config.memory_override_mib} MiB is less than the model server needs for what is "
        f"chosen. The {needed.largest.value} part alone needs {needed.limit_mib} MiB with "
        f"documents up to {config.upload_mb} MB. Write {AUTOMATIC} to let it be worked out, write "
        f"at least {needed.limit_mib}, or choose fewer parts or a smaller upload size."
    )


def environment(config: ModelServerConfig) -> tuple[tuple[str, str], ...]:
    """The variables the model server's compose file reads, in the order they are handed over.

    The names are the container's own, so the compose file interpolates the one name it already
    carries. Numbers and a comma list only: nothing here can hold a space, a quote or a newline,
    which is what lets the deploy step hand them to a shell without quoting.
    """
    return (
        ("INFERENCE_PARTS", ",".join(one.value for one in config.parts)),
        ("INFERENCE_IDLE_SECONDS", str(config.idle_seconds)),
        ("INFERENCE_MEMORY_MIB", str(effective_limit_mib(config))),
        ("INFERENCE_UPLOAD_MB", str(config.upload_mb)),
        ("INFERENCE_MAX_REQUEST_BYTES", str(request_ceiling_bytes(config))),
        *(
            (
                f"INFERENCE_NEED_{one.value.upper()}_MIB",
                str(non_reclaimable_mib(one, config.upload_mb)),
            )
            for one in Part
        ),
    )


def non_reclaimable_mib(part: Part, upload_mb: int) -> int:
    """What the host must be able to give for this part to load: the base and its anonymous peak.

    The figure the supervisor compares with `MemAvailable` before it loads the part, one per part so
    that a host able to hold the embedding model is not refused it for the sake of a layout reader
    that is bigger.
    """
    return BASE_MIB + anonymous_peak_mib(part, upload_mb)


def request_ceiling_bytes(config: ModelServerConfig) -> int:
    """The largest request body the server accepts, in bytes.

    The larger of the two things it is sent: a document, encoded as base64 inside JSON, up to the
    install's upload limit, and an embedding batch up to the slot's budget. Derived from both so
    neither can exceed what the other was sized for, and rounded to whole mebibytes so the compose
    file's figure is one a person can read.
    """
    document = ((config.upload_mb * MIB + 2) // 3) * 4 if config.reads_documents else 0
    body = max(document, batch_budget_bytes() if config.has(Part.EMBEDDING) else 0)
    return -(-max(body, 1) // MIB) * MIB


# ------------------------------------------------------------------ whether it may be saved


def settings_problem(*, parts: str, idle: str, memory: str, upload: str) -> str:
    """Everything wrong with these four values together, as one sentence, or empty.

    **Whether the host can hold the result is not asked here.** That is the one costing in
    `brain.ops.overlays.plan_in_room`, which the Settings route asks of the install's whole list of
    services with these four as they would stand (`brain.ops.overlays.memory_problem`), so the
    model server is never refused by a second sum of what a server has.
    """
    try:
        config = config_from(parts=parts, idle=idle, memory=memory, upload=upload)
    except ModelServerError as error:
        return str(error)
    return limit_problem(config)


#: The four settings, in the order the screen lists them.
SETTINGS: Final = (PARTS_SETTING, IDLE_SETTING, MEMORY_SETTING, UPLOAD_SETTING)


def setting_problem(name: str, written: str, *, current: Mapping[str, str] | None = None) -> str:
    """Why this value may not be saved for this setting, given the other three, or empty.

    One setting at a time is what a screen saves, and what is wrong with a value is often a
    property of it with the others: a limit is too small for parts chosen before it, and a part is
    too large for a limit set before it. So the value written replaces its own entry among the
    four as they stand, and the four are judged together. `current` is the other three as they
    stand and defaults to what this install resolves.
    """
    if name not in SETTINGS:
        msg = f"{name!r} is not a model server setting"
        raise ModelServerError(msg)
    texts = {one: (current or {}).get(one) or value_of(one) for one in SETTINGS}
    texts[name] = written
    return settings_problem(
        parts=texts[PARTS_SETTING],
        idle=texts[IDLE_SETTING],
        memory=texts[MEMORY_SETTING],
        upload=texts[UPLOAD_SETTING],
    )


# ------------------------------------------------------------------ a measurement, read back


def suggested_limit_mib(peaks: Sequence[int], *, headroom: float = 1.15) -> int | None:
    """The limit a set of measured peaks suggests, or None when there is nothing measured.

    The largest measured peak with a margin, in whole steps. A margin because the peaks are of the
    batches that happened, and the next one may be larger; 15% because the figures it replaces are
    judgements and this one is at least a measurement of something that ran. Never applied by
    itself: a limit that moved on its own would be a container that restarted on a Tuesday for
    reasons nobody chose.
    """
    if not peaks:
        return None
    return rounded_up(int(max(peaks) * headroom) + 1)
