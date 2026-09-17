"""Where a question no connected source covers is written, and where the gaps screen reads it back.

`brain.gate.answer` declines a question whose shape matches a rule for a source nothing on the
install reads, and names that source on the abstention for the ledger and for nobody else. This is
the ledger's writer and reader, and it decides nothing about who may see a row:
`brain.console.questions_view.gap_lines` is that.

**A row is written from the lane's own abstention and from nothing a person said.** `gap_of` reads
`Abstention.missing_source`, which `brain.gate.abstain.ONLY_NOTHING_CONNECTED_NAMES_A_SOURCE`
refuses on every other reason, and takes the department and the instant from
`brain.adoption.question_of`, the same record the question ledger is written from. So a gap cannot
be written for a question that was refused or found nothing, and a gap's department is the one the
adoption figures use. See `A_GAP_IS_READ_OFF_THE_ABSTENTION_AND_NEVER_INFERRED`.

**The first record of a trace is the one kept**, for `brain.ops.question_store`'s reason, and a
failed write is a warning rather than a fault, for the same one: the answer exists before the
record does, and a database that refused the row would otherwise turn a declined question into an
error the asker sees.

Task ids: M27.7.18
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.adoption import Unanswered, question_of
from brain.gate.abstain import AbstentionReason
from brain.gate.answer import Answered
from brain.gate.finish import Finished
from brain.tables.question_gap import QuestionGapRow

log = structlog.get_logger(__name__)

#: Why a gap is taken from the abstention rather than worked out here.
A_GAP_IS_READ_OFF_THE_ABSTENTION_AND_NEVER_INFERRED: Final = (
    "The lane names a missing source only on nothing connected, which it decides from the rules "
    "and the readers before anything is read. A writer that inferred a gap from a status, a "
    "detail or an empty answer would count refusals as gaps, so this reads the one field the "
    "lane fills and writes nothing when it is empty."
)


class QuestionGapError(Exception):
    """A gap record said something a question no connected source covers cannot say."""


@dataclass(frozen=True)
class Gap:
    """One question no connected source covers: the trace, the department, the source and when."""

    trace_id: str
    department: str
    source: str
    at: datetime

    def __post_init__(self) -> None:
        for label, value in (
            ("trace_id", self.trace_id),
            ("department", self.department),
            ("source", self.source),
        ):
            if not value.strip():
                msg = f"a gap with no {label} cannot be counted or argued from"
                raise QuestionGapError(msg)
        if self.at.tzinfo is None:
            msg = "a naive instant files a gap in the wrong window"
            raise QuestionGapError(msg)

    def unanswered(self) -> Unanswered:
        """The roadmap's own record of it: a department and a source, and nothing else."""
        return Unanswered(department=self.department, missing_source=self.source)


def gap_of(request: Finished) -> Gap | None:
    """The gap a finished request was, or None.

    See `A_GAP_IS_READ_OFF_THE_ABSTENTION_AND_NEVER_INFERRED`.

    None for an answer, a fault, a tool call, every abstention but nothing connected, nothing
    connected with no source named, and an asker with no department, which
    `brain.adoption.question_of` counts nowhere rather than under a guess.
    """
    outcome = request.outcome
    if not isinstance(outcome, Answered) or outcome.abstention is None:
        return None
    declined = outcome.abstention
    if declined.reason is not AbstentionReason.NOTHING_CONNECTED or not declined.missing_source:
        return None
    asked = question_of(request)
    if asked is None:
        return None
    return Gap(
        trace_id=asked.trace_id,
        department=asked.department,
        source=declined.missing_source,
        at=asked.at,
    )


async def record_gap(session: AsyncSession, gap: Gap) -> bool:
    """Append one gap unless its trace already has one. Returns whether it was kept. No commit."""
    statement = (
        insert(QuestionGapRow)
        .values(trace_id=gap.trace_id, department=gap.department, source=gap.source, at=gap.at)
        .on_conflict_do_nothing(index_elements=[QuestionGapRow.trace_id])
        .returning(QuestionGapRow.trace_id)
    )
    kept = await session.execute(statement)
    return kept.scalar_one_or_none() is not None


async def gaps_between(session: AsyncSession, *, start: datetime, end: datetime) -> tuple[Gap, ...]:
    """Every gap recorded in `[start, end)`, oldest first, each rebuilt through `Gap`'s checks."""
    found = await session.execute(
        select(QuestionGapRow)
        .where(QuestionGapRow.at >= start, QuestionGapRow.at < end)
        .order_by(QuestionGapRow.at, QuestionGapRow.trace_id)
    )
    return tuple(
        Gap(trace_id=one.trace_id, department=one.department, source=one.source, at=one.at)
        for one in found.scalars().all()
    )


class GapRecorder:
    """The `brain.gate.finish.RequestRecorder` that writes a question no connected source covers."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def finished(self, request: Finished) -> None:
        """Record the gap this request was, if it was one."""
        gap = gap_of(request)
        if gap is None:
            return
        try:
            async with self.sessions() as session:
                await record_gap(session, gap)
                await session.commit()
        except Exception as exc:
            # Broad on purpose, for `brain.ops.question_store`'s reason: the answer exists, and a
            # record that cannot be written must not take it away. The trace and never the source.
            log.warning("question_gap.unrecorded", trace_id=gap.trace_id, error=type(exc).__name__)
