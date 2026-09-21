"""A refusal the gate decided, written to the ledger as a `deny` entry (M24.1.3).

`AuditRecorder.deny` has existed since the ledger did and nothing called it, so on a running
install nobody was ever refused anything: the records route turned a missing grant into its one
404 and wrote a log line. This is the write, through `0104`'s `gate.record_denial`, in one
transaction with the attribution `brain.tables.audit.attributed_to` sets, so the entry names the
caller, their reach digest and the request.

**Written beside the refusal, never in its path, and that is a permission property.** The route
answers an entity nobody may read and an entity that does not exist with one 404 and one body, so
a caller cannot map the install by trying names. A write only on the refusal would put a database
round trip on exactly one of the two, and the difference would be readable as latency. So the
route schedules the write and answers at once (`record_beside`), and a failed write is logged
rather than raised: it must not turn a refusal into a fault, which would be a third answer.

Rejected: a table of denials with a trigger on it, `0060`'s shape. A deny has no state of its own
to keep, so the table would be a second copy of the ledger's rows kept only to fire an append.

Task ids: M24.1.3
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.record import DenyReason, subject
from brain.core.entitlement import Capability
from brain.tables.audit import attributed_to

log = structlog.get_logger()

#: Why the write never delays or changes the refusal.
A_DENIAL_IS_RECORDED_BESIDE_THE_REFUSAL_AND_NEVER_IN_ITS_PATH: Final = (
    "The records route answers an entity nobody may read and one that does not exist with one "
    "404. A ledger write awaited only on the first would make it slower, and a failed write "
    "raised would make it a fault, and either difference tells a caller which names exist. So "
    "the write is scheduled beside the refusal and its failure is a log line."
)


@dataclass(frozen=True)
class Denial:
    """One refusal: who, at what reach, for which request, reaching for what, and why."""

    actor_id: str
    ent_hash: str
    trace_id: str
    subject_kind: str
    subject_id: str
    capability: Capability
    reason: DenyReason

    @property
    def subject(self) -> str:
        """`<kind>:<id>`, refused one frame early for an unknown kind, as the recorder does."""
        return subject(self.subject_kind, self.subject_id)


@runtime_checkable
class Denials(Protocol):
    """Where a refusal is recorded."""

    async def denied(self, denial: Denial) -> None: ...


class StoredDenials:
    """`gate.record_denial`, called as the application role in a transaction of its own."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def denied(self, denial: Denial) -> None:
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(
                actor_id=denial.actor_id, ent_hash=denial.ent_hash, trace_id=denial.trace_id
            ):
                await session.execute(statement)
            await session.execute(
                text("SELECT gate.record_denial(:subject, :capability, :reason)").bindparams(
                    subject=denial.subject,
                    capability=denial.capability.value,
                    reason=denial.reason.value,
                )
            )


#: Tasks scheduled and not yet finished, held so the event loop cannot collect one mid-write.
_PENDING: set[asyncio.Task[None]] = set()


async def _write(denials: Denials, denial: Denial) -> None:
    try:
        await denials.denied(denial)
    except Exception as exc:
        # See A_DENIAL_IS_RECORDED_BESIDE_THE_REFUSAL_AND_NEVER_IN_ITS_PATH.
        log.warning("denial.unrecorded", trace_id=denial.trace_id, error=type(exc).__name__)


def record_beside(denials: Denials | None, denial: Denial) -> asyncio.Task[None] | None:
    """Schedule the write and return at once. None, and a log line, where nothing can record."""
    if denials is None:
        log.info("denial.nowhere_to_record", trace_id=denial.trace_id)
        return None
    task = asyncio.get_running_loop().create_task(_write(denials, denial))
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)
    return task
