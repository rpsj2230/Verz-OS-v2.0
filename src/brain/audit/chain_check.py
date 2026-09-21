"""The verification job over the stored ledger, and the head an outside store publishes.

`brain.audit.verify.verify_window` walks entries it is handed and `brain.audit.anchor` describes
an anchor, and until this module nothing handed either of them a row of `obs.audit_entry`. The
public anchor route answered `take_anchor(AuditChain())`, the head of an empty chain, whatever the
ledger held, so every anchor the scheduled workflow committed said the ledger was empty, and a
truncation after it contradicted nothing. This is the reader both were waiting for.

**The walk is in sequence order and in chunks, and every chunk resumes from the one before.**
`verify_window` takes a checkpoint for exactly this, so a long ledger is never loaded whole and a
break in chunk forty is reported at its own sequence number rather than as a failed request. The
checkpoint here is the previous chunk's head, computed in this process from rows it has just
walked, so it is not the "convenience" checkpoint `verify` warns about: nothing stored is trusted.

**A row that does not construct is a break, never a skipped row.** `AuditEntry` refuses a detail
that is a value, so a row edited by hand to carry one fails to construct, and the audit screen
skips such a row because showing it would leak the value. A verifier that skipped it would report
an edited ledger as continuous, so here it is `CONTENT_ALTERED` at that sequence number. See
`A_ROW_THAT_DOES_NOT_CONSTRUCT_IS_A_BREAK_AND_NEVER_A_GAP`.

**The published head is checked by sequence and digest, and one beyond the ledger is missing.**
`verify._partition_anchors` already treats an anchor newer than the window as the window's
business, because a truncated tail looks exactly like a window that ends early. The chunked walk
keeps that property by holding each anchor back until the chunk that should contain it, and an
anchor still held back when the ledger ends names an entry that is gone. See
`AN_ANCHOR_PAST_THE_END_NAMES_ENTRIES_THAT_WERE_REMOVED`.

**The report says how long the ledger is, and that is already public.** The anchor route publishes
the newest sequence number and its digest to anybody, which `brain.audit.anchor` argues is the
minimum an anchor needs. So `brain.audit_routes.verify_ledger` opens for anybody the Audit screen
opens for, and its report adds only where the chain broke, as a position and two digests: no
entry, no actor, no action, no subject, so nothing about an entry the reader may not see beyond
the fact that the chain holding it is intact. Rejected: opening it only to a reader of the whole
ledger. No install's first administrator is one (`brain.identity.first_administrator.
AUDIT_KINDS_WITHHELD`), so the job would have had nobody to run it.

Rejected: a verification table recording each run. The report is recomputed from the ledger in one
request, and a stored report is a second copy of a verdict that the next edit to the ledger makes
stale; the owner's proof is the run shown on the Audit screen, and the anchor history lives in the
outside store.

Task ids: M24.1.2, M24.3.3
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol, runtime_checkable

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.export import Anchor
from brain.audit.ledger import (
    GENESIS_HASH,
    AuditAction,
    AuditEntry,
    BreakReason,
    ChainBreak,
)
from brain.audit.verify import (
    ANCHOR_MISSING_CAVEAT,
    ANCHORED_CAVEAT,
    BROKEN_CAVEAT,
    UNANCHORED_CAVEAT,
    Checkpoint,
    Completeness,
    verify_window,
)
from brain.tables.audit import AuditEntryRow

# ------------------------------------------------------------------ written-down reasons
#: Why a row that fails to construct stops the walk.
A_ROW_THAT_DOES_NOT_CONSTRUCT_IS_A_BREAK_AND_NEVER_A_GAP: Final = (
    "AuditEntry refuses a detail that is a value, so a row somebody edited to carry one does not "
    "construct. The audit screen skips such a row so the value never reaches a person, and a "
    "verifier that did the same would walk past an edited entry and call the ledger continuous. "
    "Here it is content altered at that sequence number, which is what it is."
)

#: Why an anchor newer than the ledger's head is a finding.
AN_ANCHOR_PAST_THE_END_NAMES_ENTRIES_THAT_WERE_REMOVED: Final = (
    "A published head says entry N existed with this digest. A ledger that now ends before N "
    "verifies perfectly on its own, because a chain has no idea how long it was meant to be, so "
    "the only thing that can say entries were removed from the end is the head published "
    "somewhere the database administrator cannot write. Holding the anchor back until the walk "
    "ends and then calling it satisfied would file the truncation as housekeeping."
)

#: How many rows one statement loads. A resource bound, not a permission one.
CHUNK: Final = 2000

#: Where an anchor handed to the console came from, as `Anchor.where` requires a field name.
PUBLISHED_STORE: Final = "published_anchor_store"

#: Who recorded it, as far as this process can say: the store, never a person's name.
PUBLISHED_BY: Final = "anchor_store"


# ------------------------------------------------------------------------ the reader
@runtime_checkable
class LedgerSequence(Protocol):
    """The ledger read in sequence order. `StoredLedgerSequence` over a database."""

    async def after(self, seq: int | None, *, limit: int) -> Sequence[AuditEntryRow]:
        """Up to `limit` rows with a sequence number greater than `seq`, oldest first."""
        ...

    async def newest(self) -> AuditEntryRow | None:
        """The row with the highest sequence number, or None for an empty ledger."""
        ...

    async def at_seq(self, seq: int) -> AuditEntryRow | None:
        """The row at exactly this sequence number, or None."""
        ...


class StoredLedgerSequence:
    """`obs.audit_entry` read as the application role, whose policy admits every row to read."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def after(self, seq: int | None, *, limit: int) -> Sequence[AuditEntryRow]:
        statement = select(AuditEntryRow).order_by(AuditEntryRow.seq).limit(limit)
        if seq is not None:
            statement = statement.where(AuditEntryRow.seq > seq)
        async with self._sessions() as session, session.begin():
            return (await session.execute(statement)).scalars().all()

    async def newest(self) -> AuditEntryRow | None:
        statement = select(AuditEntryRow).order_by(AuditEntryRow.seq.desc()).limit(1)
        async with self._sessions() as session, session.begin():
            return (await session.execute(statement)).scalars().first()

    async def at_seq(self, seq: int) -> AuditEntryRow | None:
        statement = select(AuditEntryRow).where(AuditEntryRow.seq == seq)
        async with self._sessions() as session, session.begin():
            return (await session.execute(statement)).scalars().first()


def entry_of(row: AuditEntryRow) -> AuditEntry | None:
    """One stored row as a chain entry, or None when the ledger's own type refuses it."""
    try:
        return AuditEntry(
            seq=row.seq,
            at=row.at,
            actor_id=row.actor_id,
            action=AuditAction(row.action),
            subject=row.subject,
            ent_hash=row.ent_hash,
            trace_id=row.trace_id,
            details=dict(row.details),
            prev_hash=row.prev_hash,
            entry_hash=row.entry_hash,
        )
    except (ValueError, ValidationError):
        return None


# ------------------------------------------------------------------------ the head
@dataclass(frozen=True)
class PublishedHead:
    """What the public anchor route answers: the newest sequence number and its digest.

    An empty ledger is seq 0 with the genesis digest, which is `brain.audit.anchor`'s shape for an
    anchor taken before the first entry: it proves the ledger started empty on that date.
    """

    seq: int
    head: str

    @property
    def is_empty(self) -> bool:
        return self.head == GENESIS_HASH


async def published_head(ledger: LedgerSequence) -> PublishedHead:
    """The real head of the stored ledger, for the outside store to record."""
    newest = await ledger.newest()
    if newest is None:
        return PublishedHead(seq=0, head=GENESIS_HASH)
    return PublishedHead(seq=newest.seq, head=newest.entry_hash)


async def digest_at(ledger: LedgerSequence, seq: int) -> str | None:
    """The digest stored at one sequence number, for the workflow's coverage check."""
    row = await ledger.at_seq(seq)
    return None if row is None else row.entry_hash


# ------------------------------------------------------------------------ the walk
@dataclass(frozen=True)
class LedgerCheck:
    """One walk of the whole stored ledger, and what it did not prove.

    No field named `verified`, `ok` or `passed`, for `brain.audit.verify`'s reason: `continuous`
    is the claim the walk makes and `completeness` is the separate claim only an anchor can back.
    """

    checked_at: datetime
    entries_walked: int
    first_seq: int | None
    last_seq: int | None
    head: str
    continuous: bool
    break_found: ChainBreak | None
    completeness: Completeness
    #: The published head that was checked, when one was handed in.
    anchor: Anchor | None

    @property
    def caveats(self) -> tuple[str, ...]:
        """What this walk did not check, in words, and never empty."""
        out: list[str] = []
        if not self.continuous:
            out.append(BROKEN_CAVEAT)
        match self.completeness:
            case Completeness.ANCHORED:
                out.append(ANCHORED_CAVEAT)
            case Completeness.UNANCHORED:
                out.append(UNANCHORED_CAVEAT)
            case Completeness.ANCHOR_MISSING:
                out.append(ANCHOR_MISSING_CAVEAT)
        return tuple(out)


def published_anchor(*, seq: int, head: str, recorded_at: datetime) -> Anchor:
    """A head copied from the outside store, as the anchor `verify_window` checks."""
    return Anchor(
        seq=seq,
        entry_hash=head,
        recorded_at=recorded_at,
        recorded_by=PUBLISHED_BY,
        where=PUBLISHED_STORE,
    )


def _refused_row(index: int, row: AuditEntryRow) -> ChainBreak:
    return ChainBreak(
        index=index,
        seq=row.seq,
        reason=BreakReason.CONTENT_ALTERED,
        expected="an entry the ledger's own type admits",
        actual="a row that does not construct",
    )


async def check_ledger(
    ledger: LedgerSequence,
    *,
    at: datetime,
    anchor: Anchor | None = None,
    chunk: int = CHUNK,
) -> LedgerCheck:
    """Walk every stored entry from the first, and check the published head if one is given.

    See the module docstring for the chunking, the refused row and the held-back anchor.
    """
    checkpoint: Checkpoint | None = None
    walked = 0
    first_seq: int | None = None
    last_seq: int | None = None
    head = GENESIS_HASH
    # An anchor of the empty ledger claims a start and no length, so there is nothing to check.
    pending = anchor if anchor is not None and anchor.entry_hash != GENESIS_HASH else None
    completeness = Completeness.UNANCHORED
    after: int | None = None

    while True:
        rows = await ledger.after(after, limit=chunk)
        if not rows:
            break
        if after is None and rows[0].seq != 0:
            # The ledger is never pruned (`brain.tables.audit`), so a first row that is not entry
            # nought is a removed head, which a window starting mid-ledger would call unmoored.
            return LedgerCheck(
                checked_at=at,
                entries_walked=0,
                first_seq=rows[0].seq,
                last_seq=None,
                head=head,
                continuous=False,
                break_found=ChainBreak(
                    index=0,
                    seq=rows[0].seq,
                    reason=BreakReason.SEQUENCE_BROKEN,
                    expected="0",
                    actual=str(rows[0].seq),
                ),
                completeness=Completeness.UNANCHORED,
                anchor=anchor,
            )
        entries: list[AuditEntry] = []
        for index, row in enumerate(rows):
            entry = entry_of(row)
            if entry is None:
                return LedgerCheck(
                    checked_at=at,
                    entries_walked=walked + index,
                    first_seq=first_seq if first_seq is not None else row.seq,
                    last_seq=last_seq,
                    head=head,
                    continuous=False,
                    break_found=_refused_row(walked + index, row),
                    completeness=Completeness.UNANCHORED,
                    anchor=anchor,
                )
            entries.append(entry)
        # The anchor goes to the chunk that should hold it and to no earlier one: see
        # AN_ANCHOR_PAST_THE_END_NAMES_ENTRIES_THAT_WERE_REMOVED.
        due = pending is not None and pending.seq <= entries[-1].seq
        report = verify_window(
            entries,
            at=at,
            checkpoint=checkpoint,
            anchors=(pending,) if due and pending is not None else (),
        )
        if due:
            completeness = report.completeness
            pending = None
        if first_seq is None:
            first_seq = entries[0].seq
        if not report.continuous:
            broken = report.break_found
            assert broken is not None  # VerificationReport holds the two in agreement.
            return LedgerCheck(
                checked_at=at,
                entries_walked=walked + broken.index,
                first_seq=first_seq,
                last_seq=last_seq,
                head=head,
                continuous=False,
                break_found=broken.model_copy(update={"index": walked + broken.index}),
                completeness=Completeness.UNANCHORED,
                anchor=anchor,
            )
        walked += len(entries)
        last_seq = entries[-1].seq
        head = report.head
        checkpoint = Checkpoint(
            through_seq=last_seq, entry_hash=head, recorded_at=at, recorded_by="chain_check"
        )
        after = last_seq
        if len(rows) < chunk:
            break

    if pending is not None:
        # Still held back when the ledger ended: see
        # AN_ANCHOR_PAST_THE_END_NAMES_ENTRIES_THAT_WERE_REMOVED.
        completeness = Completeness.ANCHOR_MISSING
    return LedgerCheck(
        checked_at=at,
        entries_walked=walked,
        first_seq=first_seq,
        last_seq=last_seq,
        head=head,
        continuous=True,
        break_found=None,
        completeness=completeness,
        anchor=anchor,
    )
