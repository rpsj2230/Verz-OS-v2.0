"""Where an undo and an edit are written, and the statements the Learning and Memory screens read.

`brain.memory.digest.undo`, `brain.memory.review.delete` and `brain.memory.review.edit` are every
place in `brain.memory` a memory is revised, and each returns its correction "for whoever owns the
table". `brain.tables.learning` is now that table. This is the one module that writes an undo or an
edit into it, and it takes the values those functions return rather than rows, so there is no second
way to express a revision: whatever writes one hands this the domain's own answer.

**The decision is made inside the transaction that writes it.** A click can arrive twice, or a week
late after something else marked the same memory, and `digest.undo`'s idempotency is a read of the
corrections followed by a write. Read in one transaction and written in another, two undos of one
learning both read "not yet marked" and both write, and the second reverses nothing anybody asked to
reverse. So the store takes a two-key advisory lock on the memory's id, reads the corrections naming
it, reads the database's clock, asks the domain, and inserts, all in one transaction. See
`AN_UNDO_IS_DECIDED_UNDER_THE_LOCK_IT_IS_WRITTEN_UNDER`.

Rejected: a unique index standing in for the lock. There is no column pair a second undo would
duplicate: an undo is a supersession by the replaced memory or a demotion, and a later correction
the other way is legitimately a second row on the same pair.

**The instant is the database's.** `correction.superseded_ids` decides a pair by its latest word and
marks both on a tie, so the order of two corrections is the whole of what an undo means. An instant
from the application's clock is whichever container served the request, which is the ledger's own
argument for taking its order from one authoritative reading. The store reads `now()` in the
transaction and hands it to the domain as `at`, so the correction the caller is handed and the row
that was written carry the same instant.

**The trace and the reach are set before the insert**, as `brain.ops.connector_store` sets them, so
`0061`'s trigger appends the ledger entry under the request's trace and the caller's entitlement
hash. The lock is never the ledger's one-key lock, so the append inside the window takes it without
waiting on this transaction.

**An edit writes three rows in one transaction**: the replacement memory, the learning record that
names what it replaced, and the supersession. `review.Edit` refuses one without the other, and so
does this: a replacement written without its supersession is a second memory recalled beside the one
it corrects.

Task ids: M27.7.21, M27.7.22
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, runtime_checkable

import structlog
from sqlalchemy import Insert, Select, func, insert, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.memory.correction import Correction, Demotion, Supersession
from brain.memory.digest import Learning, Undo, undo
from brain.memory.formation import MemoryKind
from brain.memory.review import Edit, edit
from brain.memory.signals import Signal
from brain.tables.audit import ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.learning import CorrectionRow, LearningRow
from brain.tables.memory import AdaptiveMemoryRow, PersistentMemoryRow

log = structlog.get_logger()

#: Why the idempotency check and the write share a transaction and a lock.
AN_UNDO_IS_DECIDED_UNDER_THE_LOCK_IT_IS_WRITTEN_UNDER: Final = (
    "digest.undo does nothing to a memory already marked, and that is a read of the corrections "
    "followed by a write. Two undos of one learning read in separate transactions both find it "
    "unmarked and both write, and the second is a correction nobody asked for. So one "
    "transaction takes a lock on the memory's id, reads what marks it, asks the domain and "
    "writes, and a second undo waits, then reads the first one's row and does nothing."
)

#: The first key of the lock a revision takes. Its own number: `brain.ops.connector_store` takes
#: 42650, and the ledger's one-key lock is never taken here. The second key is the memory's id,
#: hashed by the database.
REVISION_LOCK_CLASS: Final = 42651


@runtime_checkable
class MemoryRecords(Protocol):
    """What the Learning and Memory routes need written. `StoredMemoryRecords` is one."""

    async def undo(self, learning: Learning, *, actor: str, trace_id: str, ent_hash: str) -> Undo:
        """Write what `digest.undo` decides under the lock, or nothing. See the module docstring."""
        ...

    async def edit(
        self,
        learning: Learning,
        replacement: Learning,
        statement: str,
        *,
        prompted_by: Signal,
        actor: str,
        trace_id: str,
        ent_hash: str,
    ) -> Edit:
        """Write what `review.edit` decides under the lock: three rows, or none."""
        ...


# ------------------------------------------------------------------- the statements


def _set_config(name: str, value: str) -> Any:
    # Transaction-local, as `brain.ops.connector_store` sets the same two for its trigger.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


def lock_on(memory_id: str) -> Any:
    """The transaction lock a revision of this memory takes. Two keys, never the ledger's one."""
    return text("SELECT pg_advisory_xact_lock(:lock_class, hashtext(:memory_id))").bindparams(
        lock_class=REVISION_LOCK_CLASS, memory_id=memory_id
    )


def the_clock() -> Select[Any]:
    """The database's instant for this transaction."""
    return select(func.now())


def corrections_naming(memory_ids: Collection[str]) -> Select[tuple[CorrectionRow]]:
    """Every correction that marks one of these memories or names one as the replacement.

    Both columns, because `correction.superseded_ids` decides a pair by its latest word, and the
    word that puts a memory back is a supersession *by* it. Ordered by instant and then id, so the
    rows a tie is decided over arrive in one order on every reading.
    """
    ids = sorted(set(memory_ids))
    return (
        select(CorrectionRow)
        .where(or_(CorrectionRow.memory_id.in_(ids), CorrectionRow.by_id.in_(ids)))
        .order_by(CorrectionRow.at, CorrectionRow.id)
    )


def learnings_of_agents(agent_ids: Collection[str], limit: int) -> Select[tuple[LearningRow]]:
    """The learnings formed while these agents ran, most recently recorded first, bounded."""
    return (
        select(LearningRow)
        .where(LearningRow.agent_id.in_(sorted(set(agent_ids))))
        .order_by(LearningRow.recorded_at.desc(), LearningRow.memory_id)
        .limit(limit)
    )


def learnings_named(memory_ids: Collection[str]) -> Select[tuple[LearningRow]]:
    """The learning records of these memories, for what each replaced and which agent ran."""
    return (
        select(LearningRow)
        .where(LearningRow.memory_id.in_(sorted(set(memory_ids))))
        .order_by(LearningRow.memory_id)
    )


def stated_named(memory_ids: Collection[str]) -> Select[tuple[PersistentMemoryRow]]:
    """These memories, from the table of what people stated."""
    return (
        select(PersistentMemoryRow)
        .where(PersistentMemoryRow.id.in_(sorted(set(memory_ids))))
        .order_by(PersistentMemoryRow.id)
    )


def inferred_named(memory_ids: Collection[str]) -> Select[tuple[AdaptiveMemoryRow]]:
    """These memories, from the table of what the system inferred."""
    return (
        select(AdaptiveMemoryRow)
        .where(AdaptiveMemoryRow.id.in_(sorted(set(memory_ids))))
        .order_by(AdaptiveMemoryRow.id)
    )


def correction_row(correction: Supersession | Demotion, actor: str) -> Insert:
    """The row one correction leaves, recorded by `actor` at the correction's own instant."""
    if isinstance(correction, Supersession):
        return insert(CorrectionRow).values(
            memory_id=correction.superseded_id,
            correction=Correction.SUPERSEDED.value,
            by_id=correction.by_id,
            prompted_by=correction.prompted_by.value,
            field=None,
            recorded_by=actor,
            at=correction.at,
        )
    return insert(CorrectionRow).values(
        memory_id=correction.memory_id,
        correction=Correction.DEMOTED.value,
        by_id=None,
        prompted_by=None,
        field=correction.field,
        recorded_by=actor,
        at=correction.at,
    )


def learning_row(learning: Learning) -> Insert:
    """The learning record of one memory: its proposal, agent, evidence and what it replaced."""
    return insert(LearningRow).values(
        memory_id=learning.memory_id,
        change=learning.proposal.change.value,
        tier=int(learning.proposal.tier),
        subject=learning.proposal.subject,
        agent_id=learning.agent_id,
        replaced_id=learning.replaced_id,
        evidence=sorted(one.value for one in learning.evidence),
    )


def memory_row(learning: Learning, statement: str) -> Insert:
    """The memory itself, in the table its kind lives in, with the statement a person wrote.

    A session memory is refused: it lives in a cache keyed by thread and in neither table, so an
    edit that produced one would be writing a conversation's working as though somebody stated it.
    """
    formation = learning.formation
    values: dict[str, object] = {
        "id": learning.memory_id,
        "principal_id": formation.principal_id,
        "statement": statement,
        "capability_tags": [one.value for one in formation.capabilities],
        "scope": formation.scope.model_dump(mode="json"),
        "ent_hash": formation.ent_hash,
        "kind": formation.kind.value,
        "formed_at": formation.formed_at,
    }
    if formation.kind is MemoryKind.PERSISTENT:
        return insert(PersistentMemoryRow).values(**values)
    if formation.kind is MemoryKind.ADAPTIVE:
        return insert(AdaptiveMemoryRow).values(
            **values, formed_confidence=learning.formed_confidence
        )
    msg = f"a {formation.kind.value} memory lives in neither memory table and cannot be written"
    raise ValueError(msg)


# ------------------------------------------------------------------- rows to values


@dataclass(frozen=True)
class Corrections:
    """Every supersession and demotion a load read, in the order it read them."""

    supersessions: tuple[Supersession, ...]
    demotions: tuple[Demotion, ...]


def corrections_of(rows: Iterable[CorrectionRow]) -> Corrections:
    """The domain's corrections from stored rows, skipping a row the domain refuses.

    A row the constraints admit always constructs; the skip is for a row an operator wrote around
    them. It is logged and not reported, for `brain.govern_routes.
    A_ROW_THE_TYPE_REFUSES_IS_A_ROW_AND_NOT_THE_END_OF_THE_SCREEN`'s reason.
    """
    supersessions: list[Supersession] = []
    demotions: list[Demotion] = []
    for row in rows:
        try:
            if row.correction == Correction.SUPERSEDED.value:
                supersessions.append(
                    Supersession(
                        superseded_id=row.memory_id,
                        by_id=row.by_id or "",
                        prompted_by=Signal(row.prompted_by or ""),
                        at=row.at,
                    )
                )
            else:
                demotions.append(
                    Demotion(memory_id=row.memory_id, field=row.field or "", at=row.at)
                )
        except ValueError as exc:
            log.warning(
                "correction row does not construct", memory=row.memory_id, error=type(exc).__name__
            )
    return Corrections(supersessions=tuple(supersessions), demotions=tuple(demotions))


# ------------------------------------------------------------------------ the store


class StoredMemoryRecords:
    """`MemoryRecords` over this install's database."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def undo(self, learning: Learning, *, actor: str, trace_id: str, ent_hash: str) -> Undo:
        async with self._sessions() as session, session.begin():
            await session.execute(lock_on(learning.memory_id))
            found = await self._marks(session, learning.memory_id)
            at: datetime = (await session.execute(the_clock())).scalar_one()
            decided = undo(
                learning, at=at, supersessions=found.supersessions, demotions=found.demotions
            )
            if decided.correction is not None:
                await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
                await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
                await session.execute(correction_row(decided.correction, actor))
        return decided

    async def edit(
        self,
        learning: Learning,
        replacement: Learning,
        statement: str,
        *,
        prompted_by: Signal,
        actor: str,
        trace_id: str,
        ent_hash: str,
    ) -> Edit:
        if not statement.strip():
            msg = "an edit with no statement writes a memory that says nothing"
            raise ValueError(msg)
        async with self._sessions() as session, session.begin():
            await session.execute(lock_on(learning.memory_id))
            found = await self._marks(session, learning.memory_id)
            at: datetime = (await session.execute(the_clock())).scalar_one()
            decided = edit(
                learning,
                replacement,
                at=at,
                prompted_by=prompted_by,
                supersessions=found.supersessions,
                demotions=found.demotions,
            )
            if decided.replacement is not None and decided.correction is not None:
                await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
                await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
                await session.execute(memory_row(decided.replacement, statement))
                await session.execute(learning_row(decided.replacement))
                await session.execute(correction_row(decided.correction, actor))
        return decided

    @staticmethod
    async def _marks(session: AsyncSession, memory_id: str) -> Corrections:
        rows = (await session.execute(corrections_naming((memory_id,)))).scalars().all()
        return corrections_of(rows)
