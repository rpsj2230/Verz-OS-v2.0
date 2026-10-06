"""Where a learning signal is written, and the only two ways it is read back.

`brain.memory.signals` decides what a signal is and `0197` builds `mem.signal`; this is the half
with a connection. It decides nothing those two do not, and it is written so that the three rules
they state are properties of the code path rather than of anybody's care.

**A signal is written inside the transaction that noticed it, and never costs that transaction
anything.** The writers are where each signal happens:
`brain.chat.thread_store.StoredThreads.record` for a question re-asked in different words and for a
question handed to a person, and `StoredThreads.correct` for an answer marked wrong (M9.2.4). Each
already holds a session in the asker's name with the conversation's rows in it, so `noticed` takes
that session rather than opening its own, and the signal is written in the asker's name by the
policy `0197` puts on the table. It is written in a savepoint, so a refused signal rolls back to
before itself and the exchange or the correction it was noticed beside is kept. See
`A_SIGNAL_NEVER_COSTS_THE_PERSON_THEIR_TRANSCRIPT`. Rejected: a second transaction after the first
commits, which is two round trips on every question and a window in which the exchange exists and
its signal does not.

**A person reads their own signals; the install reads counts of each kind.** `own` reads under the
row-level security `0197` puts on the table, so it returns the asker's rows and nothing else
whoever calls it. `counts_by` hands those rows to `brain.memory.signals.counts_by`, which is the one
place that refuses to group by a principal, rather than restating the refusal here. `counted` reads
the install through `mem.signal_counts`, which groups by kind and returns no column a person could
come back in, and **takes no field argument at all**, so there is no parameter a caller could name
`principal_id` in. See `brain.memory.signals.A_COUNT_PER_PERSON_IS_A_PERFORMANCE_REVIEW`.

**Nothing here changes anything.** No memory, rule, grant or ranking reads this table, which is
`brain.memory.signals`' "a signal is evidence and never an instruction"; the test of that walks the
imports of every package that decides an answer.

Task ids: M16.2.8, M9.2.4
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Final

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.ledger import TRACE_ID
from brain.memory.signals import Observation, Signal, counts_by
from brain.tables.signal_log import SignalRow

log = structlog.get_logger(__name__)

#: Why a signal that cannot be written is logged and the exchange is kept.
A_SIGNAL_NEVER_COSTS_THE_PERSON_THEIR_TRANSCRIPT: Final = (
    "A signal is evidence about an answer and the exchange is the person's own record of it. A "
    "signal the database refuses is written in a savepoint and rolled back alone, so the "
    "question, the answer or the correction it was noticed beside is kept, and the failure is "
    "logged by its type and nothing it carried."
)

#: Why a trace id that does not fit the ledger's grammar is kept as no trace at all.
A_TRACE_IS_KEPT_ONLY_IN_THE_LEDGERS_GRAMMAR: Final = (
    "The trace a signal was noticed on is how somebody finds the request again. One that does "
    "not fit the ledger's grammar came from somewhere other than the middleware that mints them, "
    "and keeping it would put a caller's own string on a row that holds no words, so it is "
    "stored as no trace and the signal is kept."
)

_TRACE: Final = re.compile(TRACE_ID)

_SET_PRINCIPAL: Final = text("SELECT set_config('app.principal_id', :principal, true)")

#: `0197`'s function, written out so no statement here is assembled at run time.
_COUNTS: Final = text("SELECT signal, noticed FROM mem.signal_counts(:after, :until)")


def kept_trace(trace_id: str | None) -> str | None:
    """The trace as it is stored: itself when it fits the ledger's grammar, else None."""
    return trace_id if trace_id and _TRACE.fullmatch(trace_id) else None


async def noticed(session: AsyncSession, observation: Observation, *, trace_id: str | None) -> bool:
    """Write one signal in the transaction `session` holds, in a savepoint; whether it was kept.

    The session must already name `observation.principal_id` as `app.principal_id`, which every
    writer here does for its own reason before reading the conversation; the policy refuses the
    row otherwise, and that refusal is logged and swallowed like any other. A second signal of
    the same kind about the same answer writes nothing and is still a kept signal, for
    `brain.tables.signal_log.ONE_ANSWER_IS_ONE_PIECE_OF_EVIDENCE_PER_KIND`'s reason.
    """
    statement = (
        pg_insert(SignalRow)
        .values(
            signal=observation.signal.value,
            conversation_id=uuid.UUID(observation.conversation_id),
            message_id=uuid.UUID(observation.message_id),
            trace_id=kept_trace(trace_id),
            principal_id=observation.principal_id,
            at=observation.at,
        )
        .on_conflict_do_nothing(index_elements=[SignalRow.signal, SignalRow.message_id])
    )
    try:
        async with session.begin_nested():
            await session.execute(statement)
    except SQLAlchemyError as exc:
        log.warning("signal.not_kept", signal=observation.signal.value, error=type(exc).__name__)
        return False
    return True


class StoredSignals:
    """`mem.signal`, read as one person's own rows or as the install's counts of each kind."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def own(self, principal_id: str) -> tuple[Observation, ...]:
        """This person's signals, oldest first, as `brain.memory.signals.Observation`s.

        Under row-level security in this person's name, so another person's rows are not read
        whatever this is asked, and an unknown person reads nothing.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(_SET_PRINCIPAL, {"principal": principal_id})
            rows = (
                await session.execute(
                    select(
                        SignalRow.signal,
                        SignalRow.conversation_id,
                        SignalRow.message_id,
                        SignalRow.principal_id,
                        SignalRow.at,
                    ).order_by(SignalRow.at, SignalRow.id)
                )
            ).all()
        return tuple(
            Observation(
                signal=Signal(kind),
                conversation_id=str(conversation),
                message_id=str(message),
                principal_id=principal,
                at=at,
            )
            for kind, conversation, message, principal, at in rows
        )

    async def counts_by(self, principal_id: str, field: str) -> Mapping[str, int]:
        """This person's own signals counted by one field, through `signals.counts_by`.

        Which refuses `principal_id` and any name that is not a field an observation may be
        counted by, whether or not this person has any signals to count.
        """
        return counts_by(await self.own(principal_id), field)

    async def counted(self, *, since: datetime, until: datetime) -> Mapping[str, int]:
        """How many signals of each kind the install noticed in `(since, until]`, by kind alone.

        Through `mem.signal_counts`, which reads past the per-person policy and returns a kind and
        a count, so this is the one read of everybody's signals and it cannot say whose they were.
        A kind nothing noticed is absent rather than nought.
        """
        async with self._sessions() as session, session.begin():
            rows = (await session.execute(_COUNTS, {"after": since, "until": until})).all()
        return {str(kind): int(noticed) for kind, noticed in rows}
