"""What the model server says it held at its peak, read off an answer and trusted with nothing.

Every answer the model server gives carries a `memory` block: the high-water mark of what the
container held that nothing could take back, the cache the kernel had charged to it at that moment,
how long the batch took and how large it was. This module reads that block into a `PeakReport`, and
`brain.ops.model_server_store` writes it to `ops.model_server_peak`. **It is the only place a
figure about the model server's memory enters this product as something that happened rather than
something that was reckoned**, and so the one thing in `brain.ops.model_server` that can replace a
judgement.

**A missing or malformed report is no report, and never a reason to refuse the answer.** The
measurement is about the machine and the work is about a document: an answer whose memory block is
absent, or wrong in any field, has still read the document or embedded the passage, and throwing
that away to protect a statistic would make a monitoring field the thing that can lose a file.
`read_report` therefore returns None for anything it cannot use and says nothing else, and its
caller records nothing. The opposite rule is held for the answer itself, which `brain.ops.inference`
refuses when it cannot be read, because a vector nobody can check is a vector that is wrong.

**The two figures are kept apart and never added.** `anon_peak_mib` is memory the kernel cannot take
back, and `cache_peak_mib` is file-backed pages it can: a memory-mapped weights file shows up in the
second and is the reason a container's limit has to be larger than what the host must have spare.
The suggested limit adds them because a container's limit counts both; the figure the host check
compares is the first alone. See `brain.ops.model_server.CACHE_IS_COUNTED_AS_CACHE`.

**What a report cannot be.** It cannot name a document, a person, a trace or a passage: its fields
are a part, a model's name and numbers, and `read_report` builds a `PeakReport` from exactly those
keys, dropping every other key in the block for the reason
`brain.knowledge.parse_layout.decode_layout` drops the ones it does not read. A server that grew a
field, or a document that persuaded one to echo a string into its memory block, has nowhere to put
it.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.ops.model_server import Part, suggested_limit_mib
from brain.tables.model_server import MODEL_CHARS, RING_SLOTS

#: The key an answer carries its report under, and the keys of the report. Held equal to the
#: server's own spelling (`inference_server.meter.REPORT_KEY` and `REPORT_FIELDS`) by a test,
#: because the two programs are built and deployed apart and a name spelled differently on each is
#: a measurement that is never recorded and never missed.
REPORT_KEY: Final = "memory"
REPORT_FIELDS: Final[tuple[str, ...]] = (
    "model",
    "items",
    "request_bytes",
    "duration_ms",
    "anon_peak_mib",
    "cache_peak_mib",
    "cgroup_limit_mib",
)

#: The largest figure a field may hold. Wide enough for any real machine and narrow enough that a
#: field a server filled with a timestamp or a byte count in the wrong unit is refused rather than
#: written: the columns are `integer`, and a number past it would be a database error in a worker.
MOST: Final = 2_000_000_000


@dataclass(frozen=True)
class PeakReport:
    """One batch's measured peak, as the server stated it."""

    part: Part
    model: str
    items: int
    request_bytes: int
    duration_ms: int
    anon_peak_mib: int
    cache_peak_mib: int
    cgroup_limit_mib: int | None

    @property
    def total_peak_mib(self) -> int:
        """What the container's limit had to cover at the peak: both kinds of memory."""
        return self.anon_peak_mib + self.cache_peak_mib


def _count(value: object) -> int | None:
    """A non-negative whole number inside the columns, or None for anything else.

    Booleans are refused because `True` is a number to Python and a flag where a count was due is
    a server that is not the one this reads.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if not 0 <= value <= MOST:
        return None
    return value


def read_report(payload: object, *, part: Part) -> PeakReport | None:
    """The report in one answer, or None when there is none that can be used.

    The part is the caller's and never the server's: the caller knows which part it asked, and a
    block naming a different one would be recorded under the wrong row of the table the limit is
    tuned from.
    """
    if not isinstance(payload, Mapping):
        return None
    block = payload.get(REPORT_KEY)
    if not isinstance(block, Mapping):
        return None
    model = block.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > MODEL_CHARS:
        return None
    figures: dict[str, int] = {}
    for name in (
        "items",
        "request_bytes",
        "duration_ms",
        "anon_peak_mib",
        "cache_peak_mib",
    ):
        figure = _count(block.get(name))
        if figure is None:
            return None
        figures[name] = figure
    limit = block.get("cgroup_limit_mib")
    if limit is not None:
        known = _count(limit)
        if known is None or known == 0:
            return None
        limit = known
    return PeakReport(
        part=part,
        model=model.strip(),
        items=figures["items"],
        request_bytes=figures["request_bytes"],
        duration_ms=figures["duration_ms"],
        anon_peak_mib=figures["anon_peak_mib"],
        cache_peak_mib=figures["cache_peak_mib"],
        cgroup_limit_mib=limit,
    )


def slot_for(batch_no: int) -> int:
    """Where the ring puts this batch: its number, folded into the slots a part has."""
    return batch_no % RING_SLOTS


@dataclass(frozen=True)
class RecordedPeak:
    """One row of the ring as it was read back."""

    part: Part
    batch_no: int
    at: datetime
    model: str
    items: int
    request_bytes: int
    duration_ms: int
    anon_peak_mib: int
    cache_peak_mib: int
    cgroup_limit_mib: int | None

    @property
    def total_peak_mib(self) -> int:
        """What the limit had to cover when this batch ran."""
        return self.anon_peak_mib + self.cache_peak_mib


@dataclass(frozen=True)
class PeakSummary:
    """What the ring says about one part, for a person tuning its limit."""

    part: Part
    batches: int
    largest_anon_mib: int
    largest_total_mib: int
    #: The limit the largest total suggests, or None before there is a measurement.
    suggested_limit_mib: int | None


def summarise(rows: Sequence[RecordedPeak]) -> tuple[PeakSummary, ...]:
    """One line per part that has been measured, in the order the parts are declared.

    The suggestion is made from the largest total, never an average: a limit has to hold the
    biggest batch the install has sent, and the average is the figure that is right until the
    day it is not.
    """
    summaries: list[PeakSummary] = []
    for part in Part:
        ours = [row for row in rows if row.part is part]
        if not ours:
            continue
        summaries.append(
            PeakSummary(
                part=part,
                batches=len(ours),
                largest_anon_mib=max(row.anon_peak_mib for row in ours),
                largest_total_mib=max(row.total_peak_mib for row in ours),
                suggested_limit_mib=suggested_limit_mib([row.total_peak_mib for row in ours]),
            )
        )
    return tuple(summaries)


def suggested_overall_mib(summaries: Sequence[PeakSummary]) -> int | None:
    """The limit the whole of what has been measured suggests: the largest part's, and not the sum.

    The container holds one part at a time, so its limit is the largest part's. See
    `brain.ops.model_server.ONE_PART_IS_RESIDENT_AT_A_TIME`.
    """
    suggestions = [one.suggested_limit_mib for one in summaries if one.suggested_limit_mib]
    return max(suggestions) if suggestions else None
