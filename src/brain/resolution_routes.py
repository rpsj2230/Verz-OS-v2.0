"""The Resolution review screen's API: the pairs waiting for a person, one pair, and a decision.

`brain.resolution.matching_store` raises a review item for every pair the cascade could not settle
and every match it held. This is where a reviewer reads them and decides each one (M14.6.4,
M14.8.5).

**Who may review is decided twice, and both are needed.** The capability, `admin:entity_merge`
over everything, is the reviewer's role; the owner decided it is the Owner's and the
Administrator's (decision (c), held in `brain.identity.first_administrator.ADMINISTRATION`). Then
each item is shown only to a reviewer who reaches both of its records, through
`guardrails.review_queue` and `review_store.seen_by`, which is Ask's own question about a row. A
reviewer without the capability, an item that does not exist, and an item whose records the
reviewer does not both reach get one 404 with one body, for
`guardrails.BOTH_HALVES_OR_THE_ITEM_IS_NOT_THERE`'s reason.

**The evidence is sentences, and the queue carries no count of anything withheld.** A card is
`review.card_for`: each line is a field name and a band in words, never a weight, and the figures
above the queue are counted from the cards the reader is shown. See
`review.A_PAGE_BUILT_FROM_WHAT_A_READER_SEES_CANNOT_DESCRIBE_WHAT_THEY_DO_NOT`.

**A decision is a reviewed merge or a rejection, written in the reviewer's own name.** A merge goes
through `review_store.merge_reviewed`, which is `merge_store.merge_entities` with a
`ReviewedMerge` naming the reviewer and this item, and so is on the ledger with its evidence and
undoable; the item is then closed. A rejection only closes the item, and the pair is never raised
again. Either way the reviewer's sentence is the merge's reason.

Task ids: M14.6.4, M14.8.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final, Literal

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.automation_schedule_routes import NotChangedView
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import Capability
from brain.core.errors import Absent, Failed
from brain.knowledge.columns import ColumnView
from brain.resolution.canonical import SourceRef
from brain.resolution.review import card_for, review_page
from brain.resolution.review_store import (
    StoredItem,
    StoredReviews,
    label_of,
    merge_reviewed,
    seen_by,
)
from brain.routing_routes import sessions_of
from brain.tables.resolution_review import ReviewState

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["resolution"])

#: Reads the review queue and decides a pair. Held over everything or not at all.
ENTITY_MERGE_CAPABILITY: Final = Capability(value="admin:entity_merge")

REVIEW_PATH: Final = "/resolution/review"
ITEM_PATH: Final = "/resolution/review/{item_id}"
DECISION_PATH: Final = "/resolution/review/{item_id}/decision"

#: The words a 409 carries.
ALREADY_DECIDED: Final = "decided"
#: What a reviewer reads when somebody decided the pair first.
DECIDED_ALREADY: Final = (
    "Somebody decided this pair while you were reading it, so nothing was changed. Open the queue "
    "again to see what is still waiting."
)


class RecordView(BaseModel):
    """One record of a pair: its connector, its kind and what the reader sees it called."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    entity: str
    label: str


class ReviewCardView(BaseModel):
    """One pair, in the words a reviewer reads. No score, no weight, no stage number."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    left: RecordView
    right: RecordView
    #: Each piece of evidence as a sentence, strongest first.
    lines: list[str]
    #: Why the pair is here, in the cascade's or the hold's own words.
    why: str
    #: `cascade`, `held` or `money`.
    origin: str
    state: str
    raised_at: datetime
    weight_version: str
    calibrated: bool


class ReviewQueueView(BaseModel):
    """The pairs this reviewer may decide, and the bands of their best evidence, counted from them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cards: list[ReviewCardView]
    by_strongest: dict[str, int]


class ReviewDecisionAsked(BaseModel):
    """A reviewer's decision about one pair, and their reason in a sentence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Literal["merge", "reject"]
    reason: str = Field(min_length=1, max_length=400)


class ReviewDecidedView(BaseModel):
    """What the decision did."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    state: str
    #: True when two entities were merged, false for a rejection or a pair already one entity.
    merged: bool


def may_review(asked: Asking) -> bool:
    """Whether this reader holds the reviewer's capability over everything."""
    return _in_reach(asked.reach, ENTITY_MERGE_CAPABILITY, NOWHERE, asked.now)


def _not_here(asked: Asking, reason: str) -> Absent:
    """The one refusal. The reason reaches a log and never a response."""
    log.info("review item not answerable", reason=reason, principal=asked.caller.principal.id)
    return Absent("no review item is answerable for this caller")


def _reviews(request: Request) -> StoredReviews:
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredReviews(sessions)


def _trace_id() -> str:
    return f"resolution-review-{uuid.uuid4().hex}"


def _record(record: SourceRef, view: ColumnView) -> RecordView:
    return RecordView(source=record.source, entity=record.entity, label=label_of(record, view))


def _card(stored: StoredItem, views: dict[SourceRef, ColumnView]) -> ReviewCardView:
    card = card_for(stored.item)
    return ReviewCardView(
        item_id=card.item_id,
        left=_record(card.left, views[card.left]),
        right=_record(card.right, views[card.right]),
        lines=list(card.lines),
        why=stored.reason,
        origin=stored.origin.value,
        state=stored.state.value,
        raised_at=stored.raised_at,
        weight_version=card.weight_version,
        calibrated=card.calibrated,
    )


async def _visible(
    reviews: StoredReviews, asked: Asking, items: tuple[StoredItem, ...]
) -> dict[SourceRef, ColumnView]:
    """What the reader sees of every record these items name, for the records they reach at all."""
    refs = sorted(
        {one.item.left for one in items} | {one.item.right for one in items},
        key=SourceRef.sort_key,
    )
    fields = await reviews.records(refs)
    views = {}
    for ref in refs:
        view = seen_by(asked.reach, ref, fields.get(ref), asked.now)
        if view is not None:
            views[ref] = view
    return views


@router.get(REVIEW_PATH, response_model=ReviewQueueView, responses=COMMON_RESPONSES)
async def review_queue_view(request: Request, asked: Asked) -> ReviewQueueView:
    """Every pair waiting that this reviewer reaches both halves of (M14.6.4)."""
    if not may_review(asked):
        raise _not_here(asked, "capability")
    reviews = _reviews(request)
    stored = await reviews.open_items()
    views = await _visible(reviews, asked, stored)
    page = review_page(
        [one.item for one in stored],
        reviewer_id=asked.caller.principal.id,
        reaches=lambda record: record in views,
    )
    by_id = {one.item.item_id: one for one in stored}
    return ReviewQueueView(
        cards=[_card(by_id[card.item_id], views) for card in page.cards],
        by_strongest={band.name.lower(): count for band, count in page.by_strongest.items()},
    )


async def _answerable(
    request: Request, item_id: str, asked: Asking
) -> tuple[StoredItem, dict[SourceRef, ColumnView]]:
    """One item this reviewer may decide, or the one 404."""
    if not may_review(asked):
        raise _not_here(asked, "capability")
    reviews = _reviews(request)
    stored = await reviews.one(item_id)
    if stored is None:
        raise _not_here(asked, "absent")
    views = await _visible(reviews, asked, (stored,))
    if stored.item.left not in views or stored.item.right not in views:
        raise _not_here(asked, "reach")
    return stored, views


@router.get(ITEM_PATH, response_model=ReviewCardView, responses=COMMON_RESPONSES)
async def review_item_view(request: Request, item_id: str, asked: Asked) -> ReviewCardView:
    """One pair, open or decided, for a reviewer who reaches both of its records."""
    stored, views = await _answerable(request, item_id, asked)
    return _card(stored, views)


@router.post(
    DECISION_PATH,
    response_model=ReviewDecidedView,
    responses={
        **COMMON_RESPONSES,
        409: {"model": NotChangedView, "description": "Nothing was changed, and why."},
    },
)
async def decide_review_item(
    request: Request, item_id: str, body: ReviewDecisionAsked, asked: Asked
) -> ReviewDecidedView | JSONResponse:
    """Merge the pair's two entities on this reviewer's word, or reject the pair (M14.8.5)."""
    stored, _ = await _answerable(request, item_id, asked)
    if stored.state is not ReviewState.OPEN:
        return _decided_already()
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    trace_id = _trace_id()
    merged = False
    if body.decision == "merge":
        merged = await merge_reviewed(
            sessions,
            stored,
            reviewer_id=asked.caller.principal.id,
            at=asked.now,
            ent_hash=asked.reach.ent_hash(),
            trace_id=trace_id,
            reason=body.reason,
        )
    state = ReviewState.MERGED if body.decision == "merge" else ReviewState.REJECTED
    closed = await StoredReviews(sessions).decide(
        item_id,
        state=state,
        by=asked.caller.principal.id,
        at=asked.now,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_id,
    )
    if not closed:
        return _decided_already()
    log.info("review item decided", item=item_id, state=state.value, merged=merged)
    return ReviewDecidedView(item_id=item_id, state=state.value, merged=merged)


def _decided_already() -> JSONResponse:
    body = NotChangedView(outcome=ALREADY_DECIDED, sentence=DECIDED_ALREADY)
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))
