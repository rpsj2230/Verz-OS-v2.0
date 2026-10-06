"""Where a correction's proposed fix is kept, read for review, and applied once as a new version.

The rules are `brain.knowledge.candidates`'s; this owns the session and decides nothing they do not,
the split `brain.knowledge.lifecycle` and `brain.knowledge.lifecycle_store` keep.

**Proposed through the one write the database offers.** `propose` resolves which document the
corrected answer cited by reading its cited passages at the corrector's reach now, through
`brain.knowledge.document_tools.recaller`, so a passage they no longer reach names no document and
nothing is proposed. It then calls `0198`'s `know.propose_correction` in their name, which opens a
candidate or grows the pending one with the same fix. A failure is logged by its kind and is never
the correction's failure: a person who said an answer was wrong has said so, whatever became of
the words.

**Applied in the transaction that approves it.** `decide` re-reads the candidate and its document
under the decider's reach, asks `candidates.may_decide`, writes the new version through
`lifecycle_store.write_version` as `POST .../versions` does, and records the decision with the new
version's id, all in one transaction. The database's own checks are the second wall: the policy
admits only a decider holding no correction of their own in it, the state moves from pending once,
and the new version's id is unique on the row, so a second apply of one candidate writes nothing.

Task ids: M16.6.5, M16.6.6, M16.7.6
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.chat.turns import Correction
from brain.core.entitlement import EntitlementSet
from brain.knowledge.candidates import (
    NOT_DECIDABLE,
    Candidate,
    CandidateNotOffered,
    CandidateState,
    Passage,
    candidate_id_for,
    corrected_blocks,
    group_key,
    may_decide,
    version_id_for,
    version_title,
)
from brain.knowledge.document_tools import KNOWLEDGE_ENTITY, recaller
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.lifecycle import Authority, StoredItem, successor_place
from brain.knowledge.lifecycle_store import (
    MAX_PASSAGES,
    as_person,
    live_item,
    passages,
    write_version,
)
from brain.knowledge.rows import RowSource
from brain.knowledge.text_path import joined
from brain.member_library import assert_replaceable
from brain.ops.queue import Job
from brain.tables.audit import attributed_to
from brain.tables.learning_candidate import CandidateEvidenceRow, LearningCandidateRow

log = structlog.get_logger(__name__)

#: The most candidates one reviewer's list shows. A list, not a report.
MAX_CANDIDATES: Final = 200

#: Why a document with more passages than one read returns is not corrected this way.
TOO_LONG_TO_CARRY_WHOLE: Final = (
    "this document is longer than a correction can carry into a new version whole; add the "
    "correction as a new version of it by hand"
)

#: Why a document with no kind is not corrected this way.
NO_KIND: Final = (
    "this document has no kind, so a new version of it cannot be made from a correction"
)


class CandidateRefusedError(Exception):
    """An approval that cannot be carried out on this document, said to the reviewer."""


_SET_PRINCIPAL: Final = text("SELECT set_config('app.principal_id', :principal, true)")
_PROPOSE: Final = text(
    "SELECT know.propose_correction(:candidate, :item, :words, :key, :conversation, :answer_at)"
)


async def cited_document(
    records: RowSource, correction: Correction, *, reach: EntitlementSet, now: datetime
) -> str | None:
    """The document the corrected answer cited first, as the corrector reaches it now, or None."""
    chunk_ids = [ref.record_id for ref in correction.refs if ref.entity == KNOWLEDGE_ENTITY]
    if not chunk_ids:
        return None
    found = await recaller(records)(chunk_ids, entitlement=reach, now=now)
    return found.records[0].document_id if found.records else None


async def propose(
    sessions: async_sessionmaker[AsyncSession],
    records: RowSource,
    *,
    correction: Correction,
    thread_id: str,
    words: str,
    reach: EntitlementSet,
    now: datetime,
    trace_id: str,
) -> str | None:
    """Hold what the person said is right as a candidate about the document their answer cited.

    The candidate's id, or None when nothing was proposed: no words, no cited document they still
    reach, this answer already evidence, or the database refused. Never raises.
    """
    said = words.strip()
    if not said:
        return None
    try:
        conversation = uuid.UUID(thread_id)
        item_id = await cited_document(records, correction, reach=reach, now=now)
        if item_id is None:
            return None
        async with sessions() as session, session.begin():
            # The candidate's ledger entry is the proposer's, at their reach, under this request.
            for statement in attributed_to(
                actor_id=correction.principal_id, ent_hash=reach.ent_hash(), trace_id=trace_id
            ):
                await session.execute(statement)
            await session.execute(_SET_PRINCIPAL, {"principal": correction.principal_id})
            found = await session.execute(
                _PROPOSE,
                {
                    "candidate": candidate_id_for(item_id, said, at=now),
                    "item": item_id,
                    "words": said,
                    "key": group_key(item_id, said),
                    "conversation": conversation,
                    "answer_at": correction.answer_at,
                },
            )
            candidate: str | None = found.scalar_one()
        return candidate
    except (DBAPIError, ValueError) as exc:
        log.warning("knowledge.correction_not_proposed", error=type(exc).__name__)
        return None


def _candidate(row: LearningCandidateRow, proposers: Sequence[str]) -> Candidate:
    return Candidate(
        candidate_id=row.candidate_id,
        item_id=row.item_id,
        words=row.words,
        raised_by=row.raised_by,
        raised_at=row.raised_at,
        proposers=frozenset(proposers),
        state=CandidateState(row.state),
        decided_by=row.decided_by or "",
        decided_at=row.decided_at,
        reason=row.reason or "",
        applied_item_id=row.applied_item_id or "",
    )


async def _proposers(session: AsyncSession, candidate_id: str) -> tuple[str, ...]:
    """Who proposed or grew this candidate, read past the evidence policy by its function: a
    decider is shown every proposer, so the four-eyes refusal is not a question of what they see."""
    rows = await session.execute(
        select(CandidateEvidenceRow.principal_id).where(
            CandidateEvidenceRow.candidate_id == candidate_id
        )
    )
    return tuple(sorted({str(one) for one in rows.scalars()}))


@dataclass(frozen=True)
class UnderReview:
    """One candidate as its reviewer reads it: the words, the document, and how many corrections
    said the same. Never who said it."""

    candidate: Candidate
    item: StoredItem
    instances: int


async def held(session: AsyncSession, candidate_id: str) -> tuple[Candidate, StoredItem] | None:
    """One candidate and its live document, as this transaction's reader may see them."""
    row = await session.get(LearningCandidateRow, candidate_id)
    if row is None:
        return None
    item = await live_item(session, row.item_id)
    if item is None:
        return None
    return _candidate(row, await _proposers(session, candidate_id)), item


async def under_review(
    session: AsyncSession, authority: Authority, candidate_id: str
) -> UnderReview | None:
    """One candidate this person may decide, with its document; None, alike, for any other."""
    found = await held(session, candidate_id)
    if found is None:
        return None
    candidate, item = found
    if not may_decide(candidate, item, authority):
        return None
    return UnderReview(candidate=candidate, item=item, instances=len(candidate.proposers))


async def decidable(session: AsyncSession, authority: Authority) -> tuple[UnderReview, ...]:
    """Every pending candidate this person may decide, oldest first."""
    rows = await session.execute(
        select(LearningCandidateRow.candidate_id)
        .where(LearningCandidateRow.state == CandidateState.PENDING.value)
        .order_by(LearningCandidateRow.raised_at, LearningCandidateRow.candidate_id)
        .limit(MAX_CANDIDATES)
    )
    found: list[UnderReview] = []
    for candidate_id in rows.scalars():
        one = await under_review(session, authority, str(candidate_id))
        if one is not None:
            found.append(one)
    return tuple(found)


def corrected_version(
    item: StoredItem, candidate: Candidate, kept: Sequence[Passage], *, review_by: datetime
) -> tuple[KnowledgeItem, tuple[Any, ...]]:
    """The new version an approved candidate becomes, and its blocks: every passage as it was,
    then the correction, placed where a new version of this document goes and stewarded as it
    is."""
    blocks = corrected_blocks(kept, candidate.words)
    successor = KnowledgeItem(
        item_id=version_id_for(candidate.candidate_id, item.item_id),
        content=joined(blocks),
        title=version_title(item.title or item.item_id),
        visibility=successor_place(item),
        owner_id=item.owner_id,
        state=KnowledgeState.PUBLISHED,
        kind=item.kind,
        review_by=review_by,
    )
    return successor, blocks


@dataclass(frozen=True)
class Decided:
    """What a decision came to: the candidate as decided, and the embedding job to queue."""

    candidate: Candidate
    job: Job | None


async def decide(
    session: AsyncSession,
    authority: Authority,
    candidate_id: str,
    *,
    approve: bool,
    reason: str,
    review_by: datetime | None,
    revision: str | None,
    now: datetime,
) -> Decided:
    """Approve as a new version or reject with a reason, in this transaction. `CandidateNotOffered`
    for a candidate this person may not decide, alike for one that does not exist."""
    await as_person(session, authority)
    found = await under_review(session, authority, candidate_id)
    if found is None:
        raise CandidateNotOffered(NOT_DECIDABLE)
    candidate, item = found.candidate, found.item
    successor: KnowledgeItem | None = None
    blocks: tuple[Any, ...] = ()
    if approve:
        if review_by is None:
            msg = "an approved correction is a new version, and a new version has a review date"
            raise ValueError(msg)
        read = await passages(session, item.item_id, limit=MAX_PASSAGES + 1)
        if len(read) > MAX_PASSAGES:
            raise CandidateRefusedError(TOO_LONG_TO_CARRY_WHOLE)
        if item.kind is None:
            raise CandidateRefusedError(NO_KIND)
        kept = tuple(Passage(body=one.body, section=one.section, page=one.page) for one in read)
        successor, blocks = corrected_version(item, candidate, kept, review_by=review_by)
        assert_replaceable(item, successor)
    applied = "" if successor is None else successor.item_id
    state = CandidateState.APPROVED if approve else CandidateState.REJECTED
    values: Mapping[str, object] = {
        "state": state.value,
        "decided_by": authority.principal_id,
        "decided_at": now,
        "reason": None if approve else reason.strip(),
        "applied_item_id": applied or None,
    }
    # The decision first, while its document is still the live version the policy asks about;
    # the new version supersedes it a statement later, in the same transaction, so the two
    # commit together or not at all.
    moved = await session.execute(
        update(LearningCandidateRow)
        .where(
            LearningCandidateRow.candidate_id == candidate_id,
            LearningCandidateRow.state == CandidateState.PENDING.value,
        )
        .values(**values)
        .returning(LearningCandidateRow.candidate_id)
    )
    if moved.scalar_one_or_none() is None:
        raise CandidateNotOffered(NOT_DECIDABLE)
    job: Job | None = None
    if successor is not None:
        job = await write_version(
            session, item, successor, blocks=blocks, revision=revision, now=now
        )
    decided = Candidate(
        candidate_id=candidate.candidate_id,
        item_id=candidate.item_id,
        words=candidate.words,
        raised_by=candidate.raised_by,
        raised_at=candidate.raised_at,
        proposers=candidate.proposers,
        state=state,
        decided_by=authority.principal_id,
        decided_at=now,
        reason="" if approve else reason.strip(),
        applied_item_id=applied,
    )
    return Decided(candidate=decided, job=job)
