"""Where the questions people asked are written, and where adoption reads them back from.

`brain.adoption` decides what a question record is and what a department's adoption line may
say, and `brain.console.adoption_view` decides which departments a reader may be shown. This is
the half that talks to PostgreSQL, and it decides neither: a row written is an `Asked` built
through its own checks by `brain.adoption.question_of`, and a window read comes back as `Asked`
records for the measure to fold.

**The first record of a trace is the question, and a later one is dropped rather than refused.**
The table is keyed on the trace id and the write is `ON CONFLICT DO NOTHING`. A hop under the
root trace is therefore one row, which is the property adoption needs. The alternative, keeping
every record and letting `adoption_by_department` refuse a trace whose records disagree, is
correct about delegation and wrong about the header: `brain.app`'s middleware lets a caller
propose a trace id, so two different people can finish under one id, and a table holding both
would make the adoption report refuse for every reader. Anybody able to reuse an id could
switch the report off. With the key, a disagreeing record cannot reach the table, so that
refusal is unreachable from anything stored. What remains is stated in
`THE_FIRST_RECORD_OF_A_TRACE_IS_THE_QUESTION`.

**A question that cannot be written does not take its answer with it.** The recorder runs in
the lane's `finally`, after the answer exists, and a database that refused the write would
otherwise turn an answered question into a fault the asker sees. So `QuestionRecorder` catches
its own failure and writes a warning naming the trace, which is the visible half: an adoption
figure that is short is found by the log line rather than by nobody. See
`A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT`.

**The window is filtered in SQL and again in the measure, and the two agree by construction.**
One row per trace means a trace's earliest record is its only record, so `[start, end)` on the
row is `adoption_by_department`'s own dating rule. The measure still applies its window, and it
still refuses a naive or empty one; this module adds no second check of either.

Task ids: M37.3.2.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.adoption import Asked, question_of
from brain.core.principal import PrincipalKind
from brain.gate.context import Channel
from brain.gate.finish import Finished
from brain.tables.adoption import QuestionAskedRow

log = structlog.get_logger(__name__)

#: Why a second record under a trace is dropped, and what that costs.
THE_FIRST_RECORD_OF_A_TRACE_IS_THE_QUESTION: Final = (
    "A delegated question finishes under its root trace, so one question is one trace and one "
    "row. A caller may also propose a trace id, so two people can finish under one; keeping "
    "both would let anybody who reuses an id make the adoption report refuse for everybody. "
    "So the first record is kept and later ones are dropped. The cost is bounded and falls on "
    "the person choosing: reusing your own id counts your questions once, and pre-empting "
    "somebody else's record needs their id before they have used it, which a minted id does "
    "not give."
)

#: Why a failed write is logged and not raised.
A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT: Final = (
    "The record is written after the answer exists. Raising would turn a question that was "
    "answered into a fault the asker sees, over a figure only a department head reads. So "
    "the failure is a warning naming the trace, which is how a short adoption figure is "
    "explained, and the answer is delivered."
)


def asked_from(stored: QuestionAskedRow) -> Asked:
    """The question record a stored row holds, through `Asked`'s own checks."""
    return Asked(
        trace_id=stored.trace_id,
        principal_id=stored.principal_id,
        principal_kind=PrincipalKind(stored.principal_kind),
        channel=Channel(stored.channel),
        department=stored.department,
        at=stored.at,
    )


async def record(session: AsyncSession, asked: Asked) -> bool:
    """Append one question unless its trace already has one. Returns whether it was kept.

    Does not commit. See `THE_FIRST_RECORD_OF_A_TRACE_IS_THE_QUESTION`.
    """
    statement = (
        insert(QuestionAskedRow)
        .values(
            trace_id=asked.trace_id,
            principal_id=asked.principal_id,
            principal_kind=asked.principal_kind.value,
            channel=asked.channel.value,
            department=asked.department,
            at=asked.at,
        )
        .on_conflict_do_nothing(index_elements=[QuestionAskedRow.trace_id])
        .returning(QuestionAskedRow.trace_id)
    )
    kept = await session.execute(statement)
    return kept.scalar_one_or_none() is not None


async def asked_between(
    session: AsyncSession, *, start: datetime, end: datetime
) -> tuple[Asked, ...]:
    """Every question asked in `[start, end)`, oldest first, for `adoption_by_department`."""
    found = await session.execute(
        select(QuestionAskedRow)
        .where(QuestionAskedRow.at >= start, QuestionAskedRow.at < end)
        .order_by(QuestionAskedRow.at, QuestionAskedRow.trace_id)
    )
    return tuple(asked_from(one) for one in found.scalars().all())


class QuestionRecorder:
    """The `brain.gate.finish.RequestRecorder` that writes who asked, one row per trace."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def finished(self, request: Finished) -> None:
        """Record the question this request was, if it can be attributed to a department."""
        asked = question_of(request)
        if asked is None:
            # Counted nowhere rather than under a guessed department. The trace id and not
            # the principal, because the question of who lacks a department belongs to the
            # directory, which can answer it without this line.
            log.info("question.unattributed", trace_id=request.origin.trace_id)
            return
        try:
            async with self.sessions() as session:
                kept = await record(session, asked)
                await session.commit()
        except Exception as exc:
            # Broad on purpose, and named in the constant this module states it in:
            # A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT.
            log.warning("question.unrecorded", trace_id=asked.trace_id, error=type(exc).__name__)
            return
        if not kept:
            log.info("question.already_recorded", trace_id=asked.trace_id)
