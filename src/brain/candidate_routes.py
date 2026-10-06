"""The corrections a person may decide: listed, read and decided, as a new version of a document is.

`brain.knowledge.candidates` argues every rule and `brain.knowledge.candidate_store` holds the
session. These three routes are the addresses the console reads them at:

- `GET /knowledge/corrections`: every pending correction this person may decide, named by the
  document it would change, with how many corrections said the same and never who said it.
- `GET /knowledge/corrections/{candidate_id}`: one of them, with the words and who will read them
  if they are approved, in plain terms.
- `POST /knowledge/corrections/{candidate_id}/decision`: approve it as a new version of the
  document, with the new version's review date, or reject it with a reason.

**One refusal for everything a person may not decide.** A correction that is not theirs to
decide, one that holds their own correction, one already decided and one that does not exist are
the same 404 in the same words, so these routes are not a way to ask which documents were
corrected. The person who corrected an answer is told nothing here: their correction is theirs, and
the steward's task is the steward's.

**The review queue M16.6.6 names is the steward's task and this route, not the Approvals screen.**
The Approvals screen offers a card to whoever holds a capability in a scope, and the person who may
add a new version of a document is its steward or an administrator of where it sits, which
`brain.knowledge.lifecycle.Authority.may_act` decides and no capability states. See
`brain.knowledge.candidates.A_CORRECTION_IS_DECIDED_BY_WHOEVER_MAY_ADD_A_NEW_VERSION`.

Task ids: M16.6.5, M16.6.6, M16.7.6
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import of_request
from brain.core.errors import Absent
from brain.knowledge.candidate_store import (
    CandidateRefusedError,
    Decided,
    UnderReview,
    decidable,
    decide,
    under_review,
)
from brain.knowledge.candidates import (
    NOT_DECIDABLE,
    REASON_CHARS,
    CandidateNotOffered,
    audience,
)
from brain.knowledge.chunk_store import ChunkStoreError
from brain.knowledge.embed_policy import embedding_revision
from brain.knowledge.item import ITEM_ID_PATTERN
from brain.knowledge.lifecycle import successor_place
from brain.knowledge.lifecycle_store import LifecycleStoreError
from brain.knowledge_lifecycle_routes import (
    LIFECYCLE_RESPONSES,
    _enqueue,
    _sessions,
    authority_of,
    in_transaction,
    refused,
)
from brain.ops.reliability import sqlstate_in

log = structlog.get_logger(__name__)

router = APIRouter(prefix=API_PREFIX, tags=["knowledge"])

CORRECTIONS_PATH: Final = "/knowledge/corrections"
#: What PostgreSQL says when a row-level policy refuses a write: `0198`'s update policy refusing a
#: decider whose correction the candidate holds.
REFUSED_BY_A_POLICY: Final = "42501"
CORRECTION_PATH: Final = "/knowledge/corrections/{candidate_id}"
CORRECTION_DECISION_PATH: Final = "/knowledge/corrections/{candidate_id}/decision"

_ID: Final = Path(min_length=1, max_length=128, pattern=ITEM_ID_PATTERN)


class CorrectionSummaryView(BaseModel):
    """One correction in a reviewer's list: which document, how many said it, when first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    item_id: str
    title: str
    instances: int
    raised_at: datetime


class CorrectionsView(BaseModel):
    """Every pending correction this reader may decide, oldest first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[CorrectionSummaryView]


class CorrectionReviewView(CorrectionSummaryView):
    """One correction as its reviewer reads it: the words, and who will read them if approved."""

    words: str
    #: Who reads the document the words would become a passage of, in plain terms. See
    #: `brain.knowledge.candidates.APPROVED_WORDS_ARE_READ_BY_EVERYONE_WHO_READS_THE_DOCUMENT`.
    audience: str


class CorrectionDecisionAsked(BaseModel):
    """Approve as a new version with its review date, or reject with a reason. Nothing else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approve: bool
    reason: str | None = Field(default=None, max_length=REASON_CHARS)
    review_by: datetime | None = None


class CorrectionDecidedView(BaseModel):
    """What the decision came to: its state, and the new version an approval became."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    state: str
    applied_item_id: str | None = None


def _summary(one: UnderReview) -> CorrectionSummaryView:
    return CorrectionSummaryView(
        candidate_id=one.candidate.candidate_id,
        item_id=one.item.item_id,
        title=one.item.title or one.item.item_id,
        instances=one.instances,
        raised_at=one.candidate.raised_at,
    )


@router.get(CORRECTIONS_PATH, response_model=CorrectionsView, responses=COMMON_RESPONSES)
async def corrections(request: Request, asked: Asked) -> CorrectionsView:
    """Every pending correction this person may decide (M16.6.6)."""
    authority = await authority_of(request, asked)

    async def load(session: AsyncSession) -> tuple[UnderReview, ...]:
        return await decidable(session, authority)

    found = await in_transaction(request, asked, authority, load)
    return CorrectionsView(items=[_summary(one) for one in found])


@router.get(CORRECTION_PATH, response_model=CorrectionReviewView, responses=COMMON_RESPONSES)
async def correction(
    request: Request, asked: Asked, candidate_id: Annotated[str, _ID]
) -> CorrectionReviewView:
    """One correction this person may decide, with its words and who would read them."""
    authority = await authority_of(request, asked)

    async def load(session: AsyncSession) -> UnderReview | None:
        return await under_review(session, authority, candidate_id)

    found = await in_transaction(request, asked, authority, load)
    if found is None:
        raise Absent(NOT_DECIDABLE)
    return CorrectionReviewView(
        **_summary(found).model_dump(),
        words=found.candidate.words,
        audience=audience(successor_place(found.item)),
    )


@router.post(
    CORRECTION_DECISION_PATH,
    response_model=CorrectionDecidedView,
    responses=LIFECYCLE_RESPONSES,
)
async def decide_correction(
    request: Request,
    asked: Asked,
    candidate_id: Annotated[str, _ID],
    body: CorrectionDecisionAsked,
) -> CorrectionDecidedView | JSONResponse:
    """Approve a correction as a new version of its document, or reject it with a reason.

    An approval needs the new version's review date, ahead, as `POST .../versions` does; a
    rejection needs its reason, which is kept. Applied in the decision's own transaction, once.
    """
    if body.approve and (body.review_by is None or body.review_by <= asked.now):
        return refused("review_by", "not_ahead", "the new version's review date has to be ahead")
    reason = (body.reason or "").strip()
    if not body.approve and not reason:
        return refused("reason", "no_reason", "say why the correction is rejected")
    authority = await authority_of(request, asked)
    revision = embedding_revision()

    async def work(session: AsyncSession) -> Decided:
        return await decide(
            session,
            authority,
            candidate_id,
            approve=body.approve,
            reason=reason,
            review_by=body.review_by,
            revision=revision,
            now=asked.now,
        )

    try:
        async with _sessions(request)() as session, session.begin():
            # Attributed before anything is written: the candidate's decision, the new version
            # and the old one's supersession are all on the ledger under the reviewer.
            for statement in of_request(asked):
                await session.execute(statement)
            decided = await work(session)
    except CandidateNotOffered:
        raise Absent(NOT_DECIDABLE) from None
    except CandidateRefusedError as exc:
        return refused("candidate", "not_applied", str(exc))
    except (LifecycleStoreError, ChunkStoreError, ValueError) as exc:
        return refused("candidate", "not_applied", str(exc), status=409)
    except DBAPIError as exc:
        if sqlstate_in(exc, REFUSED_BY_A_POLICY):
            # The database's half of the four-eyes rule, or its deciders, refused the row: the
            # same one refusal as Python's, so the second wall says nothing the first does not.
            raise Absent(NOT_DECIDABLE) from None
        log.warning("knowledge.correction_refused_by_database", candidate=candidate_id)
        return refused(
            "candidate",
            "moved",
            "the document changed while the correction was being decided; open it again",
            status=409,
        )
    await _enqueue(request, decided.job)
    log.info(
        "knowledge.correction_decided",
        principal=authority.principal_id,
        candidate=candidate_id,
        state=decided.candidate.state.value,
    )
    return CorrectionDecidedView(
        candidate_id=candidate_id,
        state=decided.candidate.state.value,
        applied_item_id=decided.candidate.applied_item_id or None,
    )
