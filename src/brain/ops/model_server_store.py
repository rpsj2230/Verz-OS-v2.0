"""The model server's switch, and where its measured peaks are kept and read back.

`brain.ops.model_server_peaks` decides what a report is; this is the half that opens a session. It
is deliberately small, and it holds three things that have to be in a module that touches the
database and nothing else.

**The switch is asked here.** `model_server_is_on` is the one function that asks the feature
`brain.ops.features_declared.model_server.MODEL_SERVER`, which is what
`brain.ops.features.feature_gaps` reads to hold the declared reader to the source. Every caller
that would send a document or a passage to the server asks this first, and the server being
started by a release (`INSTALL_SERVICES`) is not the same question: see the feature's own text.

**A peak is written in the transaction of the work that measured it.** The ring has a slot per
batch number, so a writer that chooses the same number as another overwrites a row it would have
written anyway, and nothing about the ring needs a lock. A failure to write a peak is a failure to
write a statistic, and `record_peak` is called in a savepoint by every caller for that reason: a
batch that embedded fifty passages is not undone because the table that tunes a limit refused a row.

**What the host has left is not read here.** The room the release's step measured is kept and
asked by `brain.ops.overlays` (`ROOM_KEY`, `memory_problem`), which is the one costing for every
optional service; this module holds no second reading of it.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import TYPE_CHECKING, Final, cast

import structlog
from sqlalchemy import Table, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.features import is_on
from brain.ops.features_declared.model_server import MODEL_SERVER
from brain.ops.model_server import Part
from brain.ops.model_server_peaks import PeakReport, RecordedPeak, slot_for
from brain.tables.model_server import ModelServerPeakRow

if TYPE_CHECKING:
    from collections.abc import Sequence

log = structlog.get_logger()

# A cast at a library boundary: SQLAlchemy types a mapped class's `__table__` as the broader
# `FromClause`, and `insert` wants the `Table` it always is. Proving it to mypy buys nothing.
_PEAK = cast(Table, ModelServerPeakRow.__table__)


async def model_server_is_on(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether documents and passages may be sent to the model server. Off until switched on."""
    async with sessions() as session:
        return await is_on(session, MODEL_SERVER)


async def record_peak(session: AsyncSession, report: PeakReport, *, at: datetime) -> int:
    """Keep one batch's peak in its part's ring, and say which batch number it was.

    The newest number for the part, plus one, folded into the ring's slots. A writer that picked
    the same number as another lands in the same slot and overwrites it, which loses one of two
    figures measured at the same moment and is the cost of a table that needs no lock.
    """
    newest = (
        await session.execute(
            select(func.coalesce(func.max(_PEAK.c.batch_no), 0)).where(
                _PEAK.c.part == report.part.value
            )
        )
    ).scalar_one()
    batch_no = int(newest) + 1
    values = {
        "part": report.part.value,
        "slot": slot_for(batch_no),
        "batch_no": batch_no,
        "at": at,
        "model": report.model,
        "items": report.items,
        "request_bytes": report.request_bytes,
        "duration_ms": report.duration_ms,
        "anon_peak_mib": report.anon_peak_mib,
        "cache_peak_mib": report.cache_peak_mib,
        "cgroup_limit_mib": report.cgroup_limit_mib,
    }
    statement = insert(_PEAK).values(**values)
    overwritten = {
        name: statement.excluded[name] for name in values if name not in ("part", "slot")
    }
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[_PEAK.c.part, _PEAK.c.slot], set_=overwritten
        )
    )
    return batch_no


async def recorded_peaks(session: AsyncSession) -> Sequence[RecordedPeak]:
    """Every batch the ring still holds, parts in declaration order and oldest first within each."""
    rows = (
        await session.execute(select(_PEAK).order_by(_PEAK.c.part, _PEAK.c.batch_no))
    ).mappings()
    return tuple(
        RecordedPeak(
            part=Part(row["part"]),
            batch_no=row["batch_no"],
            at=row["at"],
            model=row["model"],
            items=row["items"],
            request_bytes=row["request_bytes"],
            duration_ms=row["duration_ms"],
            anon_peak_mib=row["anon_peak_mib"],
            cache_peak_mib=row["cache_peak_mib"],
            cgroup_limit_mib=row["cgroup_limit_mib"],
        )
        for row in rows
    )


class PeakKeeper:
    """Holds the reports a worker's clients were told of, until a job writes them down.

    **A client is called from a thread and a session belongs to the event loop**, so the report
    cannot be written where it is heard. This is the hand-off: `keep` is what a client calls (it
    is the `observer` of `ModelServerClient` and of `InferenceEmbeddingClient`), `flush` is what the
    job calls once it is back on the loop with a session of its own. A list and a lock, and nothing
    that can fail, because the thread calling it is in the middle of a document.

    **A statistic is never a reason to fail a job.** `flush` writes each report in a savepoint of
    its own and drops the one that is refused, saying so by type and nothing else, so a table that
    would not take a row costs that row and not the passages the job has just embedded. It is
    called in a `finally`, so the figures of a job that failed are kept as well: a batch that ran
    the server out of memory is the one whose peak is wanted most.

    **Bounded.** A worker whose database is down for an hour must not grow without limit, so the
    oldest reports are dropped past `LARGEST_KEPT`, which is a ring's worth for every part.
    """

    #: The most reports held at once: one ring for each part, which is all a ring could keep.
    LARGEST_KEPT: Final = 50 * len(Part)

    def __init__(self) -> None:
        self._held: list[PeakReport] = []
        self._lock = threading.Lock()

    def keep(self, report: PeakReport) -> None:
        """What a client calls when the server told it its memory for a request."""
        with self._lock:
            self._held.append(report)
            del self._held[: -self.LARGEST_KEPT]

    def drain(self) -> tuple[PeakReport, ...]:
        """Everything held, and nothing held afterwards."""
        with self._lock:
            held, self._held = tuple(self._held), []
        return held

    async def flush(self, sessions: async_sessionmaker[AsyncSession], *, at: datetime) -> int:
        """Write what is held, one savepoint each, and say how many were kept."""
        written = 0
        for report in self.drain():
            try:
                async with sessions() as session, session.begin(), session.begin_nested():
                    await record_peak(session, report, at=at)
                written += 1
            except Exception as error:
                log.warning("the model server's peak was not kept", error=type(error).__name__)
        return written
