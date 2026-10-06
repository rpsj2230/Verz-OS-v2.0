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
argument for taking its order from one authoritative reading. The store reads the database's
clock in the transaction, after the lock, and hands it to the domain as `at`, so the correction the
caller is handed and the row that was written carry the same instant.

**Read as `statement_timestamp()` since 2026-09-29, not `now()`.** `now()` is when the transaction
began, which is before the lock was granted: a revision that waited on another's lock was stamped
earlier than the one it waited for, so the pair's latest word was the wrong one, and two revisions
of one pair written in one transaction were stamped alike and marked each other. The install's
acceptance check, which writes an edit and then forgets it in one transaction, found the second.
`statement_timestamp()` is the start of the statement reading it, after the lock, so revisions are
ordered as they were written. See `A_REVISION_IS_STAMPED_WHEN_IT_IS_DECIDED`.

**The trace and the reach are set before the insert**, as `brain.ops.connector_store` sets them, so
`0061`'s trigger appends the ledger entry under the request's trace and the caller's entitlement
hash. The lock is never the ledger's one-key lock, so the append inside the window takes it without
waiting on this transaction.

**An edit writes three rows in one transaction**: the replacement memory, the learning record that
names what it replaced, and the supersession. `review.Edit` refuses one without the other, and so
does this: a replacement written without its supersession is a second memory recalled beside the one
it corrects.

**A memory formed from a turn is written with its learning record and nothing else.**
`StoredFormations` reads the person's memories and every correction naming them under a lock on the
person, asks `brain.memory.turn.propose_memories`, and writes each memory beside its `mem.learning`
row, which is the revision record the Memory screen reads. No correction is written, because nothing
was replaced.

**An agent whose learning is paused forms nothing from its runs** (M16.7.13).
`StoredFormations.form` reads the agent's latest `agent.learning_pause` row in the transaction
that would write, before the lock on the person, and a paused agent's turn is answered
`NotFormed.PAUSED`. The pause stops formation and nothing else, so it can narrow what is learned
and never widen it.

**A turn is formed from by the answer route since 2026-09-29, and read back for a model.** Nothing
called `StoredFormations.after_turn` until then, so no install ever formed a memory and the Memory
and Learning screens could only be empty; `brain.api_routes.answered_for` now hands it every turn
whose words ask anything to be remembered. `StoredRecall` is the other direction: the asker's own
memories, read and decided by `brain.memory.recall.recall` at the run's reach and the place the
asker is now, whose statements a model is shown as hints. See
`A_MODEL_IS_SHOWN_ONLY_WHAT_THE_ASKER_MAY_RECALL_ABOUT_THEMSELVES`.

**An inference said again is stamped confirmed in the same transaction (M16.7.2).** What
`propose_memories` names in `confirmed` is updated with `confirmation`, the one column `0163` lets
the application touch, in the person's own name and under the turn's trace, and `0163`'s trigger
appends one ledger entry for each. `formation_of` carries the stamp, so every reader decays the
memory from it. Nothing else stamps it: a mark is written by `brain.ops.learning_signal_store`,
which names no memory, so a helpful mark cannot confirm one (M16.7.4).

Task ids: M27.7.21, M27.7.22, M38.2.2.4, M16.6.3, M16.7.13, M16.7.2
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, runtime_checkable

import structlog
from sqlalchemy import Insert, Select, func, insert, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.entitlement import Capability, EntitlementSet
from brain.core.scope import Scope
from brain.knowledge.search import PRINCIPAL_SETTING
from brain.memory.correction import Correction, Demotion, Supersession
from brain.memory.digest import Learning, Undo, undo
from brain.memory.formation import Formation, MemoryKind
from brain.memory.recall import recall
from brain.memory.review import Edit, edit
from brain.memory.signals import Signal
from brain.memory.turn import Held, NotFormed, Turn, propose_memories, worth_forming
from brain.ops.learning_signal_store import paused_in
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


#: Why a revision's instant is read after its lock rather than at its transaction's start.
A_REVISION_IS_STAMPED_WHEN_IT_IS_DECIDED: Final = (
    "The order of two corrections of one pair is the whole of what the pair means, and now() is "
    "when the transaction began, before its lock was granted. A revision that waited would be "
    "stamped before the one it waited for, and two revisions in one transaction would tie and "
    "mark each other. So the instant is the statement's, read after the lock."
)


def the_clock() -> Select[Any]:
    """The database's instant for this revision: the reading statement's, after the lock."""
    return select(func.statement_timestamp())


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


def learnings_of_conversations(limit: int) -> Select[tuple[LearningRow]]:
    """The learnings formed with no agent running, most recently recorded first, bounded."""
    return (
        select(LearningRow)
        .where(LearningRow.agent_id.is_(None))
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


# ------------------------------------------------------------------ forming from a turn
#: The first key of the lock a turn's formation takes. Its own number beside `REVISION_LOCK_CLASS`;
#: the second key is the person's id, so two turns by one person form one after the other and two
#: people's turns never wait on each other.
FORMATION_LOCK_CLASS: Final = 42652

#: Why a formation is decided under a lock on the person.
TWO_TURNS_BY_ONE_PERSON_FORM_ONE_AFTER_THE_OTHER: Final = (
    "Whether a statement is already remembered is a read of the person's memories followed by a "
    "write. Two turns saying the same thing, formed in two transactions at once, would both read "
    "nothing and both write, and the person would have the same memory twice. So one transaction "
    "takes a lock on the person, reads what they have and what corrected it, asks the domain and "
    "writes, and the second turn waits and then finds the first one's memory standing."
)


def lock_on_person(principal_id: str) -> Any:
    """The transaction lock a formation for this person takes. Two keys, never the ledger's one."""
    return text("SELECT pg_advisory_xact_lock(:lock_class, hashtext(:principal_id))").bindparams(
        lock_class=FORMATION_LOCK_CLASS, principal_id=principal_id
    )


def stated_by(principal_id: str) -> Select[tuple[str, str, str]]:
    """Every memory this person stated, as id, kind and statement."""
    return (
        select(PersistentMemoryRow.id, PersistentMemoryRow.kind, PersistentMemoryRow.statement)
        .where(PersistentMemoryRow.principal_id == principal_id)
        .order_by(PersistentMemoryRow.id)
    )


def inferred_of(principal_id: str) -> Select[tuple[str, str, str]]:
    """Every memory the system inferred about this person, as id, kind and statement."""
    return (
        select(AdaptiveMemoryRow.id, AdaptiveMemoryRow.kind, AdaptiveMemoryRow.statement)
        .where(AdaptiveMemoryRow.principal_id == principal_id)
        .order_by(AdaptiveMemoryRow.id)
    )


@dataclass(frozen=True)
class Formed:
    """What one turn wrote, by memory id, and why anything it proposed was not written."""

    memory_ids: tuple[str, ...]
    skipped: tuple[NotFormed, ...]
    #: The standing inferences the turn said again, stamped confirmed (M16.7.2).
    confirmed: tuple[str, ...] = ()


def confirmation(principal_id: str, memory_ids: Collection[str]) -> Any:
    """Stamp these inferences of this person's confirmed, by the database's clock (M16.7.2).

    The one column `0163` lets the application update, in the person's own name, which the policy
    reads from `app.principal_id`, stamped `statement_timestamp()`, which is the only value the
    policy admits. The ledger entry is `0163`'s trigger's, one per row the update moves.
    """
    return (
        update(AdaptiveMemoryRow)
        .where(
            AdaptiveMemoryRow.id.in_(sorted(set(memory_ids))),
            AdaptiveMemoryRow.principal_id == principal_id,
        )
        .values(last_confirmed_at=func.statement_timestamp())
    )


class StoredFormations:
    """The step after an answered turn: read what the person has, propose, write with the record.

    See `brain.memory.turn` for the rules and where the answer lane calls this, and
    `TWO_TURNS_BY_ONE_PERSON_FORM_ONE_AFTER_THE_OTHER` for the lock.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def form(self, turn: Turn) -> Formed:
        """Write what this turn proposes, each memory with its learning record, in one transaction.

        Raises what the database raises. `after_turn` is the call that must not. A refused turn,
        and one with nothing in it to remember, are answered before any connection is opened.
        """
        if turn.refused:
            return Formed(memory_ids=(), skipped=(NotFormed.REFUSED,))
        if not worth_forming(turn.said):
            return Formed(memory_ids=(), skipped=(NotFormed.NOTHING_TO_REMEMBER,))
        async with self._sessions() as session, session.begin():
            # An agent whose learning is paused teaches nothing from its runs (M16.7.13). Read in
            # the transaction that would write, so a pause set a moment ago is honoured.
            if turn.agent_id is not None and await paused_in(session, (turn.agent_id,)):
                return Formed(memory_ids=(), skipped=(NotFormed.PAUSED,))
            await session.execute(lock_on_person(turn.principal_id))
            held = [
                Held(memory_id=row[0], kind=MemoryKind(row[1]), statement=row[2])
                for query in (stated_by(turn.principal_id), inferred_of(turn.principal_id))
                for row in (await session.execute(query)).all()
                if row[1] in {one.value for one in MemoryKind}
            ]
            rows = (
                (await session.execute(corrections_naming([one.memory_id for one in held])))
                .scalars()
                .all()
                if held
                else []
            )
            found = corrections_of(rows)
            proposed = propose_memories(
                turn, held, supersessions=found.supersessions, demotions=found.demotions
            )
            for one in proposed.formed:
                await session.execute(memory_row(one.learning, one.statement))
                await session.execute(learning_row(one.learning))
            if proposed.confirmed:
                # In the person's own name and under the turn's trace, for the policy and the
                # ledger entry `0163`'s trigger appends for each confirmation.
                await session.execute(_set_config(PRINCIPAL_SETTING, turn.principal_id))
                await session.execute(_set_config(TRACE_ID_SETTING, turn.trace_id))
                await session.execute(_set_config(ENT_HASH_SETTING, turn.reach.ent_hash()))
                await session.execute(confirmation(turn.principal_id, proposed.confirmed))
        return Formed(
            memory_ids=tuple(one.learning.memory_id for one in proposed.formed),
            skipped=proposed.skipped,
            confirmed=proposed.confirmed,
        )

    async def after_turn(self, turn: Turn) -> Formed | None:
        """`form`, for the answer lane's caller, which must never fail an answer over a memory.

        A failure is logged with the trace and the exception's type, never its text or the words,
        and answered with None, for `brain.ops.question_store.
        A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT`'s reason.
        """
        try:
            return await self.form(turn)
        except Exception as exc:
            # Broad on purpose: whatever the store raised, the answer has already been given.
            log.warning("memory formation failed", trace=turn.trace_id, error=type(exc).__name__)
            return None


# ------------------------------------------------------------------ recalling for an answer
#: How many memories a model is shown about the person asking. A handful of sentences is what a
#: person tells a colleague about how they like to be answered; more is a profile, and every hint
#: is a sentence sent to a provider.
MAX_HINTS: Final = 5

#: How many of each table's rows a recall reads for one person, newest first. Bounded so a person
#: with years of memories costs one bounded read, and far above what `MAX_HINTS` shows.
MAX_READ_FOR_RECALL: Final = 200

#: Why recall for an answer reads nothing but the asker's own memories.
A_MODEL_IS_SHOWN_ONLY_WHAT_THE_ASKER_MAY_RECALL_ABOUT_THEMSELVES: Final = (
    "The memories read for an answer are the asker's own, and each one is shown only when "
    "brain.memory.recall admits it at the run's reach, at the place the asker is now, after the "
    "corrections are read. A memory formed in another department, under a grant since removed, "
    "undone by a person, or decayed below the floor is not shown, and nothing says one was left "
    "out."
)


@dataclass(frozen=True)
class Kept:
    """One stored memory as recall reads it, with the words it keeps."""

    memory_id: str
    formation: Formation
    formed_confidence: float
    statement: str


def formation_of(row: PersistentMemoryRow | AdaptiveMemoryRow) -> Formation:
    """The formation a stored row records. Raises `ValueError` for a row the types refuse.

    A kind no `MemoryKind` names, a capability tag the grammar refuses and a scope the model
    refuses are each possible on disk, since a tag column is bounded only by width and `kind` by
    no check constraint, and each is refused here rather than recalled on a reading of it.
    """
    return Formation(
        principal_id=row.principal_id,
        capabilities=tuple(Capability(value=one) for one in row.capability_tags),
        scope=Scope.model_validate(row.scope),
        ent_hash=row.ent_hash,
        formed_at=row.formed_at,
        kind=MemoryKind(row.kind),
        confirmed_at=row.last_confirmed_at if isinstance(row, AdaptiveMemoryRow) else None,
    )


def kept_of(row: PersistentMemoryRow | AdaptiveMemoryRow) -> Kept | None:
    """One row as recall reads it, or None for a row the types refuse or a session kind.

    A stated row is recalled at the confidence it was formed with, which is certain, since the
    stated table keeps no confidence: `brain.memory.formation.A_STATED_MEMORY_DOES_NOT_DECAY`.
    """
    try:
        formation = formation_of(row)
    except ValueError as exc:
        log.warning("memory row does not construct", memory=row.id, error=type(exc).__name__)
        return None
    if formation.kind is MemoryKind.SESSION:
        return None
    confidence = row.formed_confidence if isinstance(row, AdaptiveMemoryRow) else 1.0
    return Kept(
        memory_id=row.id,
        formation=formation,
        formed_confidence=confidence,
        statement=row.statement,
    )


def stated_rows_of(principal_id: str, limit: int) -> Select[tuple[PersistentMemoryRow]]:
    """What this person stated, newest first, bounded."""
    return (
        select(PersistentMemoryRow)
        .where(PersistentMemoryRow.principal_id == principal_id)
        .order_by(PersistentMemoryRow.formed_at.desc(), PersistentMemoryRow.id)
        .limit(limit)
    )


def inferred_rows_of(principal_id: str, limit: int) -> Select[tuple[AdaptiveMemoryRow]]:
    """What the system inferred about this person, newest first, bounded."""
    return (
        select(AdaptiveMemoryRow)
        .where(AdaptiveMemoryRow.principal_id == principal_id)
        .order_by(AdaptiveMemoryRow.formed_at.desc(), AdaptiveMemoryRow.id)
        .limit(limit)
    )


class StoredRecall:
    """The memories a model answering one person may be shown about them, as hints.

    See `A_MODEL_IS_SHOWN_ONLY_WHAT_THE_ASKER_MAY_RECALL_ABOUT_THEMSELVES`. The decision is
    `brain.memory.recall.recall`, called and never restated; this reads the rows and the
    corrections naming them and hands over the words of what it admitted, most confident first.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def recalled(
        self,
        reader: EntitlementSet,
        *,
        where: Mapping[str, object],
        now: datetime,
        limit: int = MAX_HINTS,
    ) -> tuple[str, ...]:
        """The statements of the reader's own memories they may recall now, at most `limit`.

        Raises what the database raises. `hints` is the call that must not.
        """
        async with self._sessions() as session:
            rows: list[PersistentMemoryRow | AdaptiveMemoryRow] = [
                *(
                    await session.execute(stated_rows_of(reader.principal_id, MAX_READ_FOR_RECALL))
                ).scalars(),
                *(
                    await session.execute(
                        inferred_rows_of(reader.principal_id, MAX_READ_FOR_RECALL)
                    )
                ).scalars(),
            ]
            kept = [one for one in map(kept_of, rows) if one is not None]
            marks = (
                (await session.execute(corrections_naming([one.memory_id for one in kept])))
                .scalars()
                .all()
                if kept
                else []
            )
        found = corrections_of(marks)
        said = {one.memory_id: one.statement for one in kept}
        admitted = recall(
            kept,
            reader,
            now=now,
            supersessions=found.supersessions,
            demotions=found.demotions,
            where=where,
        )
        return tuple(said[one.memory_id] for one in admitted[:limit])

    async def hints(
        self,
        reader: EntitlementSet,
        *,
        where: Mapping[str, object],
        now: datetime,
        trace_id: str,
    ) -> tuple[str, ...]:
        """`recalled`, for the answer lane's caller, which must never fail an answer over a hint.

        A failure is logged with the trace and the exception's type and answered with no hints,
        for `StoredFormations.after_turn`'s reason: the answer does not depend on them.
        """
        try:
            return await self.recalled(reader, where=where, now=now)
        except Exception as exc:
            # Broad on purpose: whatever the store raised, the question is answered without hints.
            log.warning("memory recall failed", trace=trace_id, error=type(exc).__name__)
            return ()
