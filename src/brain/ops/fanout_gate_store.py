"""Where the fan-out gate's decision is kept: write one, read the recent ones.

`brain.orchestration.fanout.decide` returns a `GateRecord` and `ops.fanout_gate` (`0240`) holds it.
This module is the whole of the translation, in both directions, and it re-decides nothing: a row
read back is rebuilt through `GateRecord`'s own constructor, which refuses a `parallel` verdict that
did not evaluate all six conditions or that names a failure, so a row written by another route that
the table's check constraint somehow admitted still cannot come back as a record that says what the
gate never said.

**Written in the session's own name.** `0240`'s insert policy admits a row whose `decided_by` is
`app.principal_id`, so the principal is set here, in the caller's transaction, before the insert,
and the same function that sets it names it in the row. Rejected: a store that took the principal
from nowhere and left the policy to refuse a row with no name, which is a refusal nobody can act on.

**Numbers and a verdict, never what was asked.** The record has no objective, subtask name or text
(`brain.orchestration.fanout.A_GATE_RECORD_IS_NUMBERS_AND_NEVER_A_QUESTION`), so nothing here could
write one.

Task ids: M18.2.4
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from brain.orchestration.fanout import Condition, GateInputs, GateRecord, Verdict
from brain.tables.fanout_gate import FanoutGateRow

#: The most decisions one read returns, newest first. A screen showing more is a log.
MOST_READ: Final = 50


@dataclass(frozen=True)
class Decided:
    """One kept decision: the gate's record and who asked for the weighing."""

    record: GateRecord
    by: str


async def keep(session: AsyncSession, record: GateRecord, *, by: str) -> None:
    """Write one decision in the caller's transaction, as `by`. Does not commit."""
    await session.execute(text("SELECT set_config('app.principal_id', :by, true)"), {"by": by})
    await session.execute(
        insert(FanoutGateRow).values(
            run_id=record.run_id,
            decided_at=record.at,
            decided_by=by,
            branches=record.inputs.branches,
            depth=record.inputs.depth,
            cost_multiplier=record.inputs.cost_multiplier,
            speedup=record.inputs.speedup,
            largest_share=record.inputs.largest_share,
            evaluated=[one.value for one in record.evaluated],
            failed=[one.value for one in record.failed],
            verdict=record.verdict.value,
        )
    )


def record_of(row: FanoutGateRow) -> Decided:
    """The decision a stored row holds, rebuilt through `GateRecord`'s own constructor."""
    at: datetime = row.decided_at
    return Decided(
        record=GateRecord(
            run_id=row.run_id,
            at=at,
            inputs=GateInputs(
                branches=row.branches,
                depth=row.depth,
                cost_multiplier=row.cost_multiplier,
                speedup=row.speedup,
                largest_share=row.largest_share,
            ),
            evaluated=tuple(Condition(one) for one in row.evaluated),
            failed=tuple(Condition(one) for one in row.failed),
            verdict=Verdict(row.verdict),
        ),
        by=row.decided_by,
    )


async def recent(session: AsyncSession, *, limit: int = MOST_READ) -> tuple[Decided, ...]:
    """The newest decisions first, at most `limit` and never more than `MOST_READ`."""
    found = await session.execute(
        select(FanoutGateRow)
        .order_by(FanoutGateRow.decided_at.desc(), FanoutGateRow.id)
        .limit(min(limit, MOST_READ))
    )
    return tuple(record_of(row) for row in found.scalars().all())
