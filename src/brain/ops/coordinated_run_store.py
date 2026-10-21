"""Where a coordinated run is kept: write one, read the recent ones.

`brain.orchestration.coordinator.coordinate` returns a `Coordinated` and `ops.coordinated_run`
(`0272`) holds how it went. This module is the whole of the translation, in both directions, and it
decides nothing: a row read back is rebuilt through the engine's own types, so a status the engine
never says cannot come back as one, and a run that never started (a refusal) is not a row, because
there is nothing to say about it that a person has not been told.

**Written in the session's own name.** The insert policy admits a row whose `asked_by` is
`app.principal_id`, so the principal is set here, in the caller's transaction, before the insert.

**Numbers, words from closed lists and hashes, never what was asked.** The row has nowhere to put
a request, an objective or a result value, and the store reads only the engine's trace to fill it.

Task ids: M18.6.2
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from brain.orchestration.coordinator import ChildStatus, ChildTrace, Coordinated, Mode, Why
from brain.tables.coordinated_run import CoordinatedRunRow

#: The most runs one read returns, newest first. A screen showing more is a log.
MOST_READ: Final = 50


@dataclass(frozen=True)
class KeptRun:
    """One kept run: how it was run, why not together, each child, and who asked."""

    run_id: str
    coordinator_id: str
    started_at: datetime
    mode: Mode
    why: tuple[Why, ...]
    children: tuple[ChildTrace, ...]
    complete: bool
    total_minor: int
    by: str


def _child_of(one: ChildTrace) -> dict[str, object]:
    return {
        "subtask_id": one.subtask_id,
        "callee_id": one.callee_id,
        "depth": one.depth,
        "reach_hash": one.reach_hash,
        "status": one.status.value,
        "minor": one.minor,
        "seconds": one.seconds,
    }


def _trace_of(raw: dict[str, object]) -> ChildTrace:
    return ChildTrace(
        subtask_id=str(raw["subtask_id"]),
        callee_id=str(raw["callee_id"]),
        depth=int(str(raw["depth"])),
        reach_hash=str(raw["reach_hash"]),
        status=ChildStatus(str(raw["status"])),
        minor=int(str(raw["minor"])),
        seconds=float(str(raw["seconds"])),
    )


async def keep(
    session: AsyncSession, run: Coordinated, *, coordinator_id: str, at: datetime, by: str
) -> bool:
    """Write one started run in the caller's transaction, as `by`. Does not commit.

    False, and nothing written, for a run that never started: it has no mode and no merged answer.
    """
    if run.mode is None or run.merged is None:
        return False
    await session.execute(text("SELECT set_config('app.principal_id', :by, true)"), {"by": by})
    await session.execute(
        insert(CoordinatedRunRow).values(
            run_id=run.run_id,
            coordinator_id=coordinator_id,
            asked_by=by,
            started_at=at,
            mode=run.mode.value,
            why=[one.value for one in run.why],
            children=[_child_of(one) for one in run.children],
            complete=run.merged.is_complete,
            total_minor=run.merged.total_minor,
        )
    )
    return True


def kept_of(row: CoordinatedRunRow) -> KeptRun:
    """The run a stored row holds, rebuilt through the engine's own types."""
    return KeptRun(
        run_id=row.run_id,
        coordinator_id=row.coordinator_id,
        started_at=row.started_at,
        mode=Mode(row.mode),
        why=tuple(Why(one) for one in row.why),
        children=tuple(_trace_of(dict(one)) for one in row.children),
        complete=row.complete,
        total_minor=row.total_minor,
        by=row.asked_by,
    )


async def recent(session: AsyncSession, *, limit: int = MOST_READ) -> tuple[KeptRun, ...]:
    """The newest runs first, at most `limit` and never more than `MOST_READ`."""
    found = await session.execute(
        select(CoordinatedRunRow)
        .order_by(CoordinatedRunRow.started_at.desc(), CoordinatedRunRow.id)
        .limit(min(limit, MOST_READ))
    )
    return tuple(kept_of(row) for row in found.scalars().all())
