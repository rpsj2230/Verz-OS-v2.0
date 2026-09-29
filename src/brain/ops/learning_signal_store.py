"""Where a mark on an answer and a pause on an agent's learning are written, and read back.

`brain.tables.learning_signal` holds the argument for both rows; this is the half with a
connection, and it decides nothing but whose a trace is.

**A person marks their own answer and nobody else's, and whose an answer is, is the ledger's.**
The answer is named by the trace it ran under, and `obs.request_telemetry` has one row per request
the answer lane finished, naming the principal it answered. A mark is written only when that row
names the person marking, received within `MARKABLE_FOR`; anything else, somebody else's trace, a
trace that never ran and one too old to find, writes nothing and is answered as one refusal. See
`A_MARK_IS_ON_AN_ANSWER_THE_MARKER_WAS_GIVEN`. Rejected: accepting any trace id, which would let a
person count against answers other people were given and learn from the refusal which traces exist.

**The count is a count over the whole install and never over a person.** `counted` returns how many
answers were last marked helpful and how many unhelpful in a window, each answer's latest mark
counted once, with nothing grouped by who, for `brain.memory.signals.
A_COUNT_PER_PERSON_IS_A_PERFORMANCE_REVIEW`'s reason.

**Where an agent stands is its latest pause row**, read by `paused_agents`. `brain.ops.memory_store.
StoredFormations` asks it before forming anything from an agent's run.

Task ids: M16.6.4, M16.7.4, M16.7.13
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from sqlalchemy import Select, and_, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.knowledge.search import PRINCIPAL_SETTING
from brain.tables.learning_signal import REASON_CHARS, LearningPauseRow, MarkRow
from brain.tables.telemetry import RequestTelemetryRow

#: How long after an answer it may still be marked. A week: long enough for somebody to find the
#: answer wrong once they acted on it, and a bound on how far back the ledger is read for it.
MARKABLE_FOR: Final = timedelta(days=7)

#: Why a mark needs the ledger to say the answer was the marker's.
A_MARK_IS_ON_AN_ANSWER_THE_MARKER_WAS_GIVEN: Final = (
    "A mark counts against an answer, so only the person the answer was given to may put one "
    "on it. The request ledger names who each finished request answered, and a mark is written "
    "only when the ledger's row for the trace names the person marking; somebody else's trace, "
    "one that never ran and one past the window are one refusal that writes nothing."
)


def _principal_is(principal_id: str) -> Any:
    # Transaction-local, as `brain.mine_routes.principal_setting` sets it for the stewardship read,
    # so the insert policies can check the row is written in the session's own name.
    return select(func.set_config(PRINCIPAL_SETTING, principal_id, True))


def answer_given_to(trace_id: str, principal_id: str, since: datetime) -> Select[tuple[int]]:
    """Whether the ledger holds a finished request under this trace, answering this person."""
    return (
        select(func.count())
        .select_from(RequestTelemetryRow)
        .where(
            RequestTelemetryRow.trace_id == trace_id,
            RequestTelemetryRow.principal == principal_id,
            RequestTelemetryRow.received_at >= since,
        )
    )


def latest_pause(agent_ids: Collection[str]) -> Select[tuple[str, bool]]:
    """Each named agent's latest pause row, as its id and whether it is paused."""
    return (
        select(LearningPauseRow.agent_id, LearningPauseRow.paused)
        .where(LearningPauseRow.agent_id.in_(sorted(set(agent_ids))))
        .order_by(LearningPauseRow.agent_id, LearningPauseRow.at.desc(), LearningPauseRow.id)
        .distinct(LearningPauseRow.agent_id)
    )


@dataclass(frozen=True)
class Tallied:
    """How many answers in a window were last marked helpful, and how many unhelpful."""

    helpful: int
    unhelpful: int


class StoredMarks:
    """Marks on answers, written by the person who was given the answer, and counted."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def mark(self, *, principal_id: str, trace_id: str, helpful: bool, now: datetime) -> bool:
        """Mark one answer the person was given; False, writing nothing, for any other trace."""
        async with self._sessions() as session, session.begin():
            given = (
                await session.execute(answer_given_to(trace_id, principal_id, now - MARKABLE_FOR))
            ).scalar_one()
            if not given:
                return False
            await session.execute(_principal_is(principal_id))
            await session.execute(
                insert(MarkRow).values(
                    trace_id=trace_id, principal_id=principal_id, helpful=helpful
                )
            )
        return True

    async def on(self, trace_id: str) -> Tallied:
        """One answer's marks, each person's latest counted once: what it was counted as."""
        latest = (
            select(MarkRow.principal_id, MarkRow.helpful)
            .where(MarkRow.trace_id == trace_id)
            .order_by(MarkRow.principal_id, MarkRow.marked_at.desc(), MarkRow.id)
            .distinct(MarkRow.principal_id)
            .subquery()
        )
        return await self._tally(select(latest.c.helpful, func.count()).group_by(latest.c.helpful))

    async def counted(self, *, since: datetime, until: datetime) -> Tallied:
        """Every answer marked in `[since, until)`, counted once by its latest mark."""
        latest = (
            select(MarkRow.trace_id, MarkRow.principal_id, MarkRow.helpful)
            .where(and_(MarkRow.marked_at >= since, MarkRow.marked_at < until))
            .order_by(MarkRow.trace_id, MarkRow.principal_id, MarkRow.marked_at.desc(), MarkRow.id)
            .distinct(MarkRow.trace_id, MarkRow.principal_id)
            .subquery()
        )
        return await self._tally(select(latest.c.helpful, func.count()).group_by(latest.c.helpful))

    async def _tally(self, statement: Select[tuple[bool, int]]) -> Tallied:
        async with self._sessions() as session:
            rows = (await session.execute(statement)).all()
        found = {bool(helpful): int(count) for helpful, count in rows}
        return Tallied(helpful=found.get(True, 0), unhelpful=found.get(False, 0))


class StoredLearningPauses:
    """Pauses and resumes of what agents' runs may teach, and where each agent stands."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def set(self, *, agent_id: str, paused: bool, reason: str, by: str) -> None:
        """Write one pause or resume, in the name of the person setting it."""
        said = reason.strip()
        if not said or len(said) > REASON_CHARS:
            msg = f"a pause or a resume needs a reason of at most {REASON_CHARS} characters"
            raise ValueError(msg)
        async with self._sessions() as session, session.begin():
            await session.execute(_principal_is(by))
            await session.execute(
                insert(LearningPauseRow).values(
                    agent_id=agent_id, paused=paused, reason=said, set_by=by
                )
            )

    async def paused(self, agent_ids: Collection[str]) -> frozenset[str]:
        """Which of these agents are paused now."""
        if not agent_ids:
            return frozenset()
        async with self._sessions() as session:
            return await paused_in(session, agent_ids)


async def paused_in(session: AsyncSession, agent_ids: Collection[str]) -> frozenset[str]:
    """Which of these agents are paused, read in a session the caller already holds."""
    rows = (await session.execute(latest_pause(agent_ids))).all()
    return frozenset(agent_id for agent_id, paused in rows if paused)
