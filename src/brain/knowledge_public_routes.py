"""Whether a document is public for the website widget, read and changed from its detail page.

`brain.knowledge.public` decides who may mark a document and `brain.knowledge.public_store` writes
the marking; this is the one route that reaches either (M10.7.2). It is the lifecycle routes'
sequence and borrows their pieces rather than restating them: the caller's `Authority` against the
live department registry, and one transaction told who is acting. **The write's transaction is
attributed here, with `brain.attribution.of_request`**, before anything is read, so
`know.record_item` names the marker, their reach and the request's trace in the ledger.

**A document the caller may not see and one that does not exist are one 404**, the lifecycle's
`NOT_SEEN` to a read and `NOT_OFFERED` to a change, for
`A_DOCUMENT_YOU_MAY_NOT_ACT_ON_AND_ONE_THAT_IS_NOT_THERE_ARE_ONE_ANSWER`. **A document they may
see is told why they may not change it**, in the rule's own sentence, because it names nothing
they could not already see: the document is theirs to read and the reason is about their grant.

**The view says which way a press would go and whether it would be taken**, so the page draws a
button that works or a sentence saying why not, and never a button that is refused. A press that
changes nothing (marking a document already public) writes nothing, so the ledger holds decisions
and not repeated presses.

Task ids: M10.7.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody
from brain.api_routes import Asked, Asking
from brain.attribution import of_request
from brain.core.errors import Absent, Failed
from brain.knowledge.item import ITEM_ID_PATTERN
from brain.knowledge.lifecycle import NOT_OFFERED, NOT_SEEN, Authority, StoredItem
from brain.knowledge.lifecycle_store import as_person, held_item, live_item, names_of
from brain.knowledge.public import NOT_PUBLIC, PublicMarking, marking_refusal
from brain.knowledge.public_store import PublicMarkingMovedError, marking_of, record_marking
from brain.knowledge_lifecycle_routes import authority_of, in_transaction, refused
from brain.routing_routes import sessions_of

log = structlog.get_logger(__name__)

router = APIRouter(prefix=API_PREFIX, tags=["knowledge"])

#: Where one document's public marking is read and changed.
PUBLIC_PATH: Final = "/knowledge/items/{item_id}/public"

_ID: Final = Path(min_length=1, max_length=128, pattern=ITEM_ID_PATTERN)

RESPONSES: Final = {
    **COMMON_RESPONSES,
    409: {"model": ErrorBody, "description": "The document or its marking changed first."},
    422: {"model": ErrorBody, "description": "Why this person may not make that change."},
}


class PublicMarkingView(BaseModel):
    """One document's marking as its reader is shown it, and what a press would do."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    public: bool
    marked_by: str | None = None
    marked_by_name: str | None = None
    marked_at: datetime | None = None
    #: Whether this person may move the marking the other way, now.
    may_change: bool
    #: Why not, in the rule's own words, or None when they may.
    says: str | None = None


class PublicMarkingAsked(BaseModel):
    """Make the document public, or stop it being public."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    public: bool


def marking_view(
    item: StoredItem,
    marking: PublicMarking,
    *,
    asked: Asking,
    names: dict[str, str],
) -> PublicMarkingView:
    """What the reader is shown: the marking, and whether the opposite press would be taken."""
    says = marking_refusal(item, marker=asked.reach, now=asked.now, public=not marking.is_public)
    return PublicMarkingView(
        item_id=item.item_id,
        public=marking.is_public,
        marked_by=marking.marked_by or None,
        marked_by_name=names.get(marking.marked_by) if marking.marked_by else None,
        marked_at=marking.marked_at,
        may_change=says is None,
        says=says,
    )


async def _seen(
    session: AsyncSession, authority: Authority, item: StoredItem | None
) -> tuple[StoredItem, PublicMarking] | None:
    if item is None or not authority.may_see(item):
        return None
    return item, await marking_of(session, item.item_id) or NOT_PUBLIC


@router.get(PUBLIC_PATH, response_model=PublicMarkingView, responses=COMMON_RESPONSES)
async def public_marking(
    request: Request, asked: Asked, item_id: Annotated[str, _ID]
) -> PublicMarkingView:
    """Whether this document is public, who made it so, and whether the reader may change it."""
    authority = await authority_of(request, asked)

    async def load(
        session: AsyncSession,
    ) -> tuple[StoredItem, PublicMarking, dict[str, str]] | None:
        seen = await _seen(session, authority, await live_item(session, item_id))
        if seen is None:
            return None
        item, marking = seen
        names = await names_of(session, [marking.marked_by] if marking.marked_by else [])
        return item, marking, names

    found = await in_transaction(request, asked, authority, load)
    if found is None:
        raise Absent(NOT_SEEN)
    item, marking, names = found
    return marking_view(item, marking, asked=asked, names=names)


@router.put(PUBLIC_PATH, response_model=PublicMarkingView, responses=RESPONSES)
async def change_public_marking(
    request: Request, asked: Asked, body: PublicMarkingAsked, item_id: Annotated[str, _ID]
) -> PublicMarkingView | JSONResponse:
    """Make the document public or stop it being public, as the caller, recorded in the ledger."""
    authority = await authority_of(request, asked)

    async def act(
        session: AsyncSession,
    ) -> tuple[StoredItem, PublicMarking, dict[str, str]] | str | None:
        seen = await _seen(session, authority, await held_item(session, item_id))
        if seen is None:
            return None
        item, marking = seen
        if marking.is_public != body.public:
            says = marking_refusal(item, marker=asked.reach, now=asked.now, public=body.public)
            if says is not None:
                return says
            await record_marking(
                session, item_id, public=body.public, by=authority.principal_id, at=asked.now
            )
            marking = await marking_of(session, item_id) or NOT_PUBLIC
        names = await names_of(session, [marking.marked_by] if marking.marked_by else [])
        return item, marking, names

    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    try:
        async with sessions() as session, session.begin():
            for statement in of_request(asked):
                await session.execute(statement)
            await as_person(session, authority)
            done = await act(session)
    except PublicMarkingMovedError as exc:
        return refused("item", "moved", str(exc), status=409)
    if done is None:
        raise Absent(NOT_OFFERED)
    if isinstance(done, str):
        return refused("public", "not_changed", done)
    item, marking, names = done
    log.info(
        "knowledge.public_marking",
        principal=authority.principal_id,
        item=item_id,
        public=marking.is_public,
    )
    return marking_view(item, marking, asked=asked, names=names)
