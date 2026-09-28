"""A stored document's life over HTTP: verify, hand over, replace and publish it, and the tasks.

K1 added documents from the Knowledge page and nothing could be done to one afterwards. These routes
are the acts M7.4.4, M7.4.5, M7.4.6, M7.6.2 and M7.7.2 ask for, each over `know.item` as it is
stored, each decided by `brain.knowledge.lifecycle`, `promotion` or `solutions`, and each written by
`brain.knowledge.lifecycle_store` in one transaction attributed to the person who asked, so the
triggers `0115` and `0120` put on the tables append the ledger entries and open the tasks.

**What a person may see and do is `Authority`, and nothing else here decides it.** It is built from
the admitted reach, `Asking.reach`, and the live department registry, as K1's upload builds where a
person may add, so a verb this channel or sign-in withholds is withheld here too. A document the
caller may not see, and one that does not exist, are the one 404 with the one sentence; so is an
act on a document they may see and not act on, because telling a reader "you may not verify this"
tells them it is administered by somebody. See
`A_DOCUMENT_YOU_MAY_NOT_ACT_ON_AND_ONE_THAT_IS_NOT_THERE_ARE_ONE_ANSWER`.

**Every refusal the actor can act on is a 422 naming what to do**, as K1's are: a review date not
ahead of today, a document not yet verified being proposed, a new version that is the file already
on file. A promotion already waiting, and an act raced by another, are a 409.

**The routes, in the order the page uses them.**

- `GET /knowledge/items`: the documents this person looks after, which is every live one they
  steward and can read or administer where it sits, with its review date, whether it is due, its
  verification as they may be told it, and their own promotion's state.
- `GET /knowledge/items/{item_id}`: one document's record and its history, each version shown only
  to a reader its own place admits, with the acts offered on it (M7.4.5).
- `GET /knowledge/items/{item_id}/passages`: one version's text, an older one included, to a reader
  whose read admits that version, redacted by the passage policy every answer is (M7.4.5).
- `POST .../verification`: verified by the caller now, with the next review date (M7.4.6).
- `POST .../steward`: handed to another steward, who is told (M7.7.2).
- `POST .../promotion`: asked for company-wide, which waits on the Approvals screen (M7.4.4).
- `POST .../versions`: a newer version, read by K1's text path, superseding this one (M7.4.5).
- `GET /knowledge/tasks` and `POST /knowledge/tasks/{task_id}/done`: what the database opened for
  this person, and closing one that only reports (M7.4.6, M7.7.2).
- `GET` and `POST /knowledge/solutions`, `POST /knowledge/solutions/{id}/decision`: capture a
  solution and decide one (M7.6.2).

**No response carries a count of anything the caller was not shown.** Each list is the caller's own
rows, bounded, and `truncated` says the bound was reached and never by how much.

Task ids: M7.4.4, M7.4.5, M7.4.6, M7.6.2, M7.7.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Annotated, Any, Final
from urllib.parse import unquote
from uuid import uuid4

import structlog
from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, RequestProblemView
from brain.api_routes import Asked, Asking
from brain.attribution import of_request, trace_of_request
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.core.errors import Absent, Failed
from brain.core.redaction import redact
from brain.gate.entitlement_store import RESOLVE, entitlements_from
from brain.gate.model_lane import PASSAGE_POLICY
from brain.knowledge.chunk_store import ChunkStoreError
from brain.knowledge.document_tools import (
    KNOWLEDGE_ENTITY,
    KNOWLEDGE_TOOL_PREFIX,
    KnowledgePassage,
)
from brain.knowledge.embed_policy import embedding_revision
from brain.knowledge.ingest import IngestRefused, ParseFailure, admit_upload, ceiling_for
from brain.knowledge.item import ITEM_ID_PATTERN, KnowledgeError, KnowledgeItem
from brain.knowledge.kinds import KIND_LABELS, KindError, KnowledgeKind
from brain.knowledge.lifecycle import (
    DISMISSABLE,
    NOT_OFFERED,
    NOT_SEEN,
    Authority,
    LifecycleError,
    StewardTask,
    StoredItem,
    TaskKind,
    assert_may_hand_over,
    assert_may_propose,
    authority_for,
    successor_place,
    task_sentence,
    verification_for,
)
from brain.knowledge.lifecycle_store import (
    MAX_ITEMS,
    MAX_PASSAGES,
    LifecycleStoreError,
    as_person,
    close_task,
    held_item,
    live_item,
    live_items,
    open_tasks,
    passages,
    promotions_asked,
    put_promotion,
    put_solution,
    record_decision,
    record_steward,
    record_verification,
    solution_held,
    solution_titles,
    solutions,
    solved,
    titles,
    versions,
    write_solution_document,
    write_version,
)
from brain.knowledge.promotion import (
    PromotionError,
    PromotionStatus,
    raise_promotion,
    status_of,
)
from brain.knowledge.search import Reach, session_settings
from brain.knowledge.solutions import (
    NOT_DECIDABLE,
    CapturedSolution,
    SolutionNotOffered,
    SolutionState,
    approved_item,
    capture,
    decided,
    may_decide,
)
from brain.knowledge.uploads import (
    ReceivedUpload,
    assert_safe_filename,
    read_arriving,
    text_path_type,
)
from brain.knowledge.verification import disclose
from brain.knowledge.visibility import Visibility, VisibilityError, propose_promotion
from brain.knowledge_routes import (
    FOUND_BY_TEXT,
    FOUND_BY_TEXT_AND_MEANING,
    NAME_HEADER,
    live_departments,
    read_one_at_a_time,
)
from brain.member_library import (
    LibraryError,
    PromotionRequest,
    assert_replaceable,
    promotion_tier,
    request_promotion,
)
from brain.ops.queue import Job
from brain.routing_routes import sessions_of

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["knowledge"])

ITEMS_PATH: Final = "/knowledge/items"
ITEM_PATH: Final = "/knowledge/items/{item_id}"
PASSAGES_PATH: Final = "/knowledge/items/{item_id}/passages"
VERIFICATION_PATH: Final = "/knowledge/items/{item_id}/verification"
STEWARD_PATH: Final = "/knowledge/items/{item_id}/steward"
PROMOTION_PATH: Final = "/knowledge/items/{item_id}/promotion"
VERSIONS_PATH: Final = "/knowledge/items/{item_id}/versions"
TASKS_PATH: Final = "/knowledge/tasks"
TASK_DONE_PATH: Final = "/knowledge/tasks/{task_id}/done"
SOLUTIONS_PATH: Final = "/knowledge/solutions"
SOLUTION_DECISION_PATH: Final = "/knowledge/solutions/{solution_id}/decision"

# ------------------------------------------------------------------ written-down reasons
#: Why every refusal about whether the caller may act is the same absence.
A_DOCUMENT_YOU_MAY_NOT_ACT_ON_AND_ONE_THAT_IS_NOT_THERE_ARE_ONE_ANSWER: Final = (
    "A document the caller may not see, one that does not exist, and one they may read and not "
    "act on are one 404 with one sentence. A different answer for the third would tell a reader "
    "the document is administered by somebody else, and a different answer for the first would "
    "let a caller trying ids learn which documents exist."
)

#: What the page says about where a promotion goes, served so the page says the API's sentence.
PROMOTION_WAITS: Final = (
    "Asking for this document to be readable by the whole company puts a card on the Approvals "
    "screen for somebody who may approve it, and it is published when they approve it. You cannot "
    "approve your own, and a card nobody decides within a day lapses and is asked for again."
)

#: The one 404 for a task that is not the caller's to close.
TASK_NOT_CLOSABLE: Final = "that task is not one you may close"

#: The id grammar every path parameter here is held to before anything is read.
_ID: Final = Path(min_length=1, max_length=128, pattern=ITEM_ID_PATTERN)


# ------------------------------------------------------------------ the shapes
class PromotionView(BaseModel):
    """The caller's own promotion of one document, as its proposer reads it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suspension_id: str
    status: PromotionStatus
    expires_at: datetime


class DocumentView(BaseModel):
    """One stored document as the lifecycle view shows it. Never its text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    title: str
    kind: str | None
    kind_label: str
    level: str
    department: str | None
    steward_id: str
    state: str
    #: The badge's state, as `brain.knowledge.verification.disclose` decides it for this reader.
    verification: str
    #: Who verified it and when, only when this reader may be told. See `disclose`.
    verified_by: str | None = None
    verified_at: datetime | None = None
    review_by: datetime | None = None
    #: Whether its review date has arrived.
    due: bool = False
    supersedes: str | None = None
    added_at: datetime | None = None
    you_steward: bool = False
    #: What it solved, for an approved solution this reader may see.
    solves: str | None = None
    promotion: PromotionView | None = None


class LookedAfterView(BaseModel):
    """The live documents this person may act on. Their own, and no count of anybody else's."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[DocumentView]
    #: The load came back full. Never how many more.
    truncated: bool = False


class VersionView(BaseModel):
    """One version in a document's history, shown to a reader its own place admits."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    title: str
    state: str
    level: str
    department: str | None
    added_at: datetime | None
    #: Whether this reader may read its text, which is a read of where it sat.
    readable: bool


class OfferedView(BaseModel):
    """Which acts this caller may take on this document now."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verify: bool = False
    new_version: bool = False
    propose: bool = False
    hand_over: bool = False


class DocumentDetailView(BaseModel):
    """One document's record, its history, and what the caller may do to it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document: DocumentView
    versions: list[VersionView]
    offered: OfferedView
    promotion_waits: str = PROMOTION_WAITS


class PassageView(BaseModel):
    """One passage of one version, as the passage policy leaves it for this reader."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ordinal: int
    section: str
    page: int | None
    text: str


class PassagesView(BaseModel):
    """One version's text, in order. The bound is a constant and never a count."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    title: str
    state: str
    passages: list[PassageView]
    truncated: bool = False


class VerificationAsked(BaseModel):
    """The next review date, which a verification sets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_by: AwareDatetime


class StewardAsked(BaseModel):
    """Who is to steward the document, by their principal id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    steward_id: str = Field(min_length=1, max_length=128, pattern=ITEM_ID_PATTERN)


class PromotionAsked(BaseModel):
    """Why the whole company should read it, and when somebody must look at it again."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_by: AwareDatetime
    reason: str = Field(min_length=1, max_length=500)


class PromotionRaisedView(BaseModel):
    """The card that now waits on the Approvals screen."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suspension_id: str
    expires_at: datetime
    says: str = PROMOTION_WAITS


class VersionAddedView(BaseModel):
    """The new version, what it replaced, and how it is found."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    supersedes: str
    title: str
    level: str
    department: str | None
    passages: int
    found_by: str


class TaskView(BaseModel):
    """One open task, in the sentence the person reads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    kind: str
    item_id: str
    says: str
    opened_at: datetime
    due_at: datetime | None
    #: Whether it may be closed by saying it was read. A review is closed by verifying.
    closable: bool


class TasksView(BaseModel):
    """This person's open tasks, newest first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[TaskView]


class SolutionView(BaseModel):
    """One captured solution, to its capturer or to somebody who may decide it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    solution_id: str
    department: str
    problem: str
    answer: str
    conversation_ref: str | None
    captured_by: str
    captured_at: datetime
    state: str
    decided_by: str | None
    decided_at: datetime | None
    #: The document it became, once approved.
    item_id: str | None


class SolutionsView(BaseModel):
    """What waits for this person's decision, what they captured, and where they may capture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    waiting: list[SolutionView]
    yours: list[SolutionView]
    departments: list[str]


class CaptureAsked(BaseModel):
    """A solution, in the capturer's words, for one department."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    problem: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=20000)
    department: str = Field(min_length=1, max_length=60)
    conversation_ref: str = Field(default="", max_length=128)


class SolutionDecisionAsked(BaseModel):
    """Approve, with the approved document's review date, or refuse."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: SolutionState
    review_by: AwareDatetime | None = None


LIFECYCLE_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    **COMMON_RESPONSES,
    409: {
        "model": ErrorBody,
        "description": "Something else happened to it first, or it is already waiting.",
    },
    422: {
        "model": ErrorBody,
        "description": "Not done, and why, in words: the message, and the one problem by field.",
    },
}


# ------------------------------------------------------------------ helpers
def refused(field: str, code: str, message: str, *, status: int = 422) -> JSONResponse:
    """A refusal whose message is the reason, as K1's upload says its own."""
    told = ErrorBody(
        message=message, problems=[RequestProblemView(field=field, code=code, message=message)]
    )
    return JSONResponse(status_code=status, content=told.model_dump(mode="json"))


def _sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return sessions


async def authority_of(request: Request, asked: Asking) -> Authority:
    """The caller's authority over stored documents: their admitted reach against the registry."""
    registry = await live_departments(_sessions(request))
    return authority_for(asked.reach, departments=registry, now=asked.now)


async def in_transaction[T](
    request: Request,
    asked: Asking,
    authority: Authority,
    work: Callable[[AsyncSession], Awaitable[T]],
    *,
    attributed: bool = False,
) -> T:
    """One transaction at the caller's reach, attributed to them when it writes."""
    async with _sessions(request)() as session, session.begin():
        if attributed:
            for statement in of_request(asked):
                await session.execute(statement)
        await as_person(session, authority)
        return await work(session)


def _trace() -> str:
    return trace_of_request() or uuid4().hex


def document_view(
    item: StoredItem,
    *,
    authority: Authority,
    reader: EntitlementSet,
    now: datetime,
    promotion: PromotionView | None = None,
    solves: str | None = None,
) -> DocumentView:
    """One document for this reader: the badge as they may be told it, never the text."""
    shown = disclose(item, reader=reader, now=now)
    return DocumentView(
        item_id=item.item_id,
        title=item.title or item.item_id,
        kind=item.kind.value if item.kind else None,
        kind_label=KIND_LABELS[item.kind] if item.kind else "not recorded",
        level=item.visibility.level.value,
        department=item.visibility.department or None,
        steward_id=item.owner_id,
        state=item.state.value,
        verification=shown.state.value,
        verified_by=shown.verified_by or None,
        verified_at=shown.verified_at,
        review_by=item.review_by,
        due=item.review_by is not None and item.review_by <= now and item.is_retrievable,
        supersedes=item.supersedes or None,
        added_at=item.added_at,
        you_steward=item.owner_id == authority.principal_id,
        solves=solves,
        promotion=promotion,
    )


def promotion_view(one: Any, now: datetime) -> PromotionView:
    return PromotionView(
        suspension_id=one.id, status=status_of(one, now=now), expires_at=one.expires_at
    )


def offered_on(item: StoredItem, authority: Authority, waiting: bool) -> OfferedView:
    """Which acts are offered, each asked of the rule that would refuse it."""
    if not authority.may_act(item):
        return OfferedView()
    new_version = item.visibility.level is not Visibility.COMPANY or bool(
        item.visibility.department
    )
    propose = (
        not waiting
        and item.visibility.level is not Visibility.COMPANY
        and item.verified_at is not None
    )
    return OfferedView(
        verify=True,
        new_version=new_version,
        propose=propose,
        hand_over=item.visibility.level is not Visibility.PERSONAL,
    )


async def _enqueue(request: Request, job: Job | None) -> None:
    """Queue an embedding job after the commit, as K1's store does, and log a refusal."""
    if job is None:
        return
    from brain.ops.queue import enqueue_job, queue_app
    from brain.ops.worker import register_tasks

    settings = getattr(request.app.state, "settings", None)
    url = str(getattr(settings, "database_url", "") or "")
    try:
        app = queue_app(url, pool_max=1)
        register_tasks(app, database_url=url)
        async with app.open_async():
            await enqueue_job(app, job)
    except Exception as exc:
        # Broad on purpose and after the commit, as K1's `store_upload` argues.
        log.warning("knowledge.embed_not_queued", error=type(exc).__name__)


# ------------------------------------------------------------------ the documents
@router.get(ITEMS_PATH, response_model=LookedAfterView, responses=COMMON_RESPONSES)
async def looked_after(request: Request, asked: Asked) -> LookedAfterView:
    """Every live document this person may act on, with its review and their own promotion."""
    authority = await authority_of(request, asked)

    async def load(
        session: AsyncSession,
    ) -> tuple[tuple[StoredItem, ...], dict[str, Any], dict[str, str]]:
        items = await live_items(session, limit=MAX_ITEMS)
        kept = [one.item_id for one in items if one.kind is KnowledgeKind.APPROVED_SOLUTION]
        found = await solved(session, kept)
        asked_for = await promotions_asked(session, reach=asked.reach, now=asked.now)
        return items, asked_for, found

    items, asked_for, found = await in_transaction(request, asked, authority, load)
    return LookedAfterView(
        items=[
            document_view(
                one,
                authority=authority,
                reader=asked.reach,
                now=asked.now,
                promotion=(
                    promotion_view(asked_for[one.item_id], asked.now)
                    if one.item_id in asked_for
                    else None
                ),
                solves=found.get(one.item_id),
            )
            for one in items
            if authority.may_act(one)
        ],
        truncated=len(items) >= MAX_ITEMS,
    )


@router.get(ITEM_PATH, response_model=DocumentDetailView, responses=COMMON_RESPONSES)
async def one_document(
    request: Request, asked: Asked, item_id: Annotated[str, _ID]
) -> DocumentDetailView:
    """One document's record and history, for a reader who may see it. Absent otherwise."""
    authority = await authority_of(request, asked)

    async def load(
        session: AsyncSession,
    ) -> tuple[tuple[StoredItem, ...], dict[str, Any], dict[str, str]]:
        chain = await versions(session, item_id)
        asked_for = await promotions_asked(session, reach=asked.reach, now=asked.now)
        found = await solved(session, [one.item_id for one in chain])
        return chain, asked_for, found

    chain, asked_for, found = await in_transaction(request, asked, authority, load)
    target = next((one for one in chain if one.item_id == item_id), None)
    if target is None or not authority.may_see(target):
        raise Absent(NOT_SEEN)
    mine = asked_for.get(item_id)
    promotion = promotion_view(mine, asked.now) if mine is not None else None
    waiting = promotion is not None and promotion.status is PromotionStatus.WAITING
    return DocumentDetailView(
        document=document_view(
            target,
            authority=authority,
            reader=asked.reach,
            now=asked.now,
            promotion=promotion,
            solves=found.get(item_id),
        ),
        versions=[
            VersionView(
                item_id=one.item_id,
                title=one.title or one.item_id,
                state=one.state.value,
                level=one.visibility.level.value,
                department=one.visibility.department or None,
                added_at=one.added_at,
                readable=authority.may_read(one),
            )
            for one in chain
            if authority.may_see(one)
        ],
        offered=offered_on(target, authority, waiting),
    )


@router.get(PASSAGES_PATH, response_model=PassagesView, responses=COMMON_RESPONSES)
async def version_text(
    request: Request, asked: Asked, item_id: Annotated[str, _ID]
) -> PassagesView:
    """One version's text, an older one included, redacted as every answer's passages are.

    The reader's read must admit the version's own place, which is `Authority.may_read`; an
    administrator who reads nothing is refused, as every answer would refuse them.
    """
    authority = await authority_of(request, asked)

    async def load(session: AsyncSession) -> tuple[tuple[StoredItem, ...], tuple[Any, ...]]:
        chain = await versions(session, item_id)
        target = next((one for one in chain if one.item_id == item_id), None)
        if target is None or not authority.may_read(target):
            return chain, ()
        return chain, await passages(session, item_id)

    chain, found = await in_transaction(request, asked, authority, load)
    target = next((one for one in chain if one.item_id == item_id), None)
    if target is None or not authority.may_read(target):
        raise Absent(NOT_SEEN)
    shown: list[PassageView] = []
    for one in found:
        # One passage at a time, so a passage the policy withholds is dropped by itself and the
        # rest keep their order and their place.
        record = KnowledgePassage(
            entity=KNOWLEDGE_ENTITY,
            id=one.chunk_id,
            document_id=target.item_id,
            title=one.title,
            section=one.section,
            document=one.body,
            department=target.visibility.department or None,
            visibility=target.visibility.level.value,
            owner_id=target.owner_id,
        )
        kept = redact(
            TypedResult[KnowledgePassage](
                records=(record,), source=f"{KNOWLEDGE_TOOL_PREFIX}.history"
            ),
            entitlement=asked.reach,
            policy=PASSAGE_POLICY,
            now=asked.now,
        ).payload.records
        if kept and kept[0].get("document"):
            shown.append(
                PassageView(
                    ordinal=one.ordinal,
                    section=str(kept[0].get("section") or ""),
                    page=one.page,
                    text=str(kept[0]["document"]),
                )
            )
    return PassagesView(
        item_id=target.item_id,
        title=target.title or target.item_id,
        state=target.state.value,
        passages=shown,
        truncated=len(found) >= MAX_PASSAGES,
    )


async def _acted_on(
    request: Request,
    asked: Asking,
    authority: Authority,
    item_id: str,
    act: Callable[[AsyncSession, StoredItem], Awaitable[None]],
) -> StoredItem:
    """Hold one live document the caller may act on, act, and read it back, in one transaction."""

    async def work(session: AsyncSession) -> StoredItem | None:
        item = await held_item(session, item_id)
        if item is None or not authority.may_act(item):
            return None
        await act(session, item)
        return await live_item(session, item_id) or item

    done = await in_transaction(request, asked, authority, work, attributed=True)
    if done is None:
        raise Absent(NOT_OFFERED)
    return done


@router.post(VERIFICATION_PATH, response_model=DocumentView, responses=LIFECYCLE_RESPONSES)
async def verify(
    request: Request, asked: Asked, body: VerificationAsked, item_id: Annotated[str, _ID]
) -> DocumentView | JSONResponse:
    """Verified by the caller now, with the next review date (M7.4.6)."""
    authority = await authority_of(request, asked)

    async def act(session: AsyncSession, item: StoredItem) -> None:
        done = verification_for(
            item, by=authority.principal_id, at=asked.now, review_by=body.review_by
        )
        await record_verification(session, item, done)

    try:
        item = await _acted_on(request, asked, authority, item_id, act)
    except LifecycleError as exc:
        return refused("review_by", "not_verified", str(exc))
    except LifecycleStoreError as exc:
        return refused("item", "moved", str(exc), status=409)
    log.info("knowledge.verified", principal=authority.principal_id, item=item_id)
    return document_view(item, authority=authority, reader=asked.reach, now=asked.now)


async def entitlement_of(session: AsyncSession, principal_id: str, now: datetime) -> EntitlementSet:
    """Another person's grants as they stand, read the way the store reads a steward's.

    The resolver is told whose grants it reads first, `entitlement_store`'s rule. The caller sets
    the transaction back to themselves afterwards.
    """
    for setting in session_settings(Reach(principal_id=principal_id)):
        await session.execute(setting)
    payload = (
        await session.execute(RESOLVE, {"principal_id": principal_id, "at": now})
    ).scalar_one()
    return entitlements_from(payload)


@router.post(STEWARD_PATH, response_model=DocumentView, responses=LIFECYCLE_RESPONSES)
async def hand_over(
    request: Request, asked: Asked, body: StewardAsked, item_id: Annotated[str, _ID]
) -> DocumentView | JSONResponse:
    """Handed to another steward, who can reach it and is told (M7.7.2)."""
    authority = await authority_of(request, asked)
    registry = await live_departments(_sessions(request))

    async def act(session: AsyncSession, item: StoredItem) -> None:
        theirs = await entitlement_of(session, body.steward_id, asked.now)
        await as_person(session, authority)
        named = authority_for(theirs, departments=registry, now=asked.now)
        assert_may_hand_over(item, to=body.steward_id, theirs=named)
        await record_steward(session, item, to=body.steward_id)

    try:
        item = await _acted_on(request, asked, authority, item_id, act)
    except LifecycleError as exc:
        return refused("steward_id", "not_handed_over", str(exc))
    except LifecycleStoreError as exc:
        return refused("item", "moved", str(exc), status=409)
    log.info("knowledge.handed_over", principal=authority.principal_id, item=item_id)
    return document_view(item, authority=authority, reader=asked.reach, now=asked.now)


@router.post(
    PROMOTION_PATH,
    status_code=201,
    response_model=PromotionRaisedView,
    responses=LIFECYCLE_RESPONSES,
)
async def propose(
    request: Request, asked: Asked, body: PromotionAsked, item_id: Annotated[str, _ID]
) -> PromotionRaisedView | JSONResponse:
    """Asked for company-wide, as a card on the Approvals screen (M7.4.4).

    Its steward asks through `brain.member_library.request_promotion`, and an administrator of
    where it sits through the same proposal at the same tier, which is ARC-A-121's Department
    Admin proposing. Nobody else is offered it.
    """
    authority = await authority_of(request, asked)

    async def load(session: AsyncSession) -> tuple[StoredItem | None, Any]:
        item = await live_item(session, item_id)
        asked_for = await promotions_asked(session, reach=asked.reach, now=asked.now)
        return item, asked_for.get(item_id)

    item, earlier = await in_transaction(request, asked, authority, load)
    if item is None or not authority.may_act(item):
        raise Absent(NOT_OFFERED)
    if earlier is not None and status_of(earlier, now=asked.now) is PromotionStatus.WAITING:
        return refused(
            "item",
            "already_waiting",
            f"this document is already waiting on the Approvals screen until "
            f"{earlier.expires_at.isoformat()}",
            status=409,
        )
    try:
        assert_may_propose(item)
        if authority.stewards(item):
            asking = request_promotion(
                item,
                proposer_id=authority.principal_id,
                review_by=body.review_by,
                reason=body.reason,
                now=asked.now,
            )
        else:
            asking = PromotionRequest(
                proposal=propose_promotion(
                    item_id=item.item_id,
                    from_level=item.visibility.level,
                    to_level=Visibility.COMPANY,
                    proposer_id=authority.principal_id,
                    owner_id=item.owner_id,
                    review_by=body.review_by,
                    reason=body.reason,
                    now=asked.now,
                ),
                tier=promotion_tier(),
            )
        suspension = raise_promotion(
            asking.proposal,
            title=item.title,
            kind=item.kind,
            department=item.visibility.department,
            reach=asked.reach,
            trace_id=_trace(),
            now=asked.now,
        )
    except (LifecycleError, VisibilityError, LibraryError, PromotionError) as exc:
        return refused("review_by", "not_proposed", str(exc))

    async def write(session: AsyncSession) -> None:
        await put_promotion(session, suspension, reach=asked.reach, now=asked.now)

    await in_transaction(request, asked, authority, write, attributed=True)
    log.info("knowledge.promotion_asked", principal=authority.principal_id, item=item_id)
    return PromotionRaisedView(suspension_id=suspension.id, expires_at=suspension.expires_at)


@router.post(
    VERSIONS_PATH,
    status_code=201,
    response_model=VersionAddedView,
    responses=LIFECYCLE_RESPONSES,
)
async def new_version(
    request: Request,
    asked: Asked,
    item_id: Annotated[str, _ID],
    review_by: Annotated[datetime, Query()],
    kind: Annotated[KnowledgeKind | None, Query()] = None,
) -> VersionAddedView | JSONResponse:
    """A newer version, read by K1's text path, superseding this one (M7.4.5).

    Placed where this one sits and stewarded as it is, which is `successor_place`; its review date
    is required and ahead, which is `brain.member_library.assert_replaceable`. The older version
    stays on file and in the history, and answers use the newer from the commit on.
    """
    authority = await authority_of(request, asked)

    async def load(session: AsyncSession) -> tuple[StoredItem | None, tuple[StoredItem, ...]]:
        return await live_item(session, item_id), await versions(session, item_id)

    predecessor, chain = await in_transaction(request, asked, authority, load)
    if predecessor is None or not authority.may_act(predecessor):
        raise Absent(NOT_OFFERED)
    if review_by.tzinfo is None or review_by <= asked.now:
        return refused("review_by", "not_ahead", "the new version's review date has to be ahead")
    chosen = kind or predecessor.kind
    if chosen is None:
        return refused("kind", "no_kind", "choose what kind of document the new version is")
    try:
        placement = successor_place(predecessor)
    except LifecycleError as exc:
        return refused("item", "no_new_version", str(exc))

    filename = unquote(request.headers.get(NAME_HEADER, ""))
    declared = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    try:
        assert_safe_filename(filename)
        media_type = text_path_type(declared)
        body = await read_arriving(request.stream(), ceiling=ceiling_for(media_type))
        received = ReceivedUpload(
            upload=admit_upload(filename=filename, declared_type=media_type.value, content=body),
            body=body,
        )
        read = await asyncio.to_thread(
            read_one_at_a_time,
            received,
            kind=chosen,
            placement=placement,
            owner_id=predecessor.owner_id,
        )
    except (IngestRefused, KindError) as exc:
        return refused("file", "not_added", str(exc))
    if isinstance(read, ParseFailure):
        return refused("file", read.cause.value, read.message())
    successor = KnowledgeItem.model_validate({**read.item.model_dump(), "review_by": review_by})
    if successor.item_id in {one.item_id for one in chain}:
        return refused("file", "already_on_file", "this file is already a version of this document")
    try:
        assert_replaceable(predecessor, successor)
    except (LibraryError, KnowledgeError, VisibilityError) as exc:
        return refused("file", "not_a_new_version", str(exc))

    revision = embedding_revision()

    async def write(session: AsyncSession) -> Job | None:
        again = await held_item(session, item_id)
        if again is None or again.owner_id != predecessor.owner_id:
            msg = "the document changed while its new version was being read"
            raise LifecycleStoreError(msg)
        return await write_version(
            session, predecessor, successor, blocks=read.blocks, revision=revision, now=asked.now
        )

    try:
        job = await in_transaction(request, asked, authority, write, attributed=True)
    except (LifecycleStoreError, ChunkStoreError) as exc:
        return refused("item", "moved", str(exc), status=409)
    except DBAPIError:
        log.warning("knowledge.version_refused_by_database", item=item_id)
        return refused(
            "item",
            "moved",
            "the document changed while its new version was being added; open it again",
            status=409,
        )
    await _enqueue(request, job)
    log.info("knowledge.new_version", principal=authority.principal_id, item=successor.item_id)
    return VersionAddedView(
        item_id=successor.item_id,
        supersedes=predecessor.item_id,
        title=successor.title,
        level=successor.visibility.level.value,
        department=successor.visibility.department or None,
        passages=len(read.blocks),
        found_by=FOUND_BY_TEXT if job is None else FOUND_BY_TEXT_AND_MEANING,
    )


# ------------------------------------------------------------------ the tasks
def _task_view(one: StewardTask, title: str) -> TaskView:
    return TaskView(
        task_id=one.task_id,
        kind=one.kind.value,
        item_id=one.item_id,
        says=task_sentence(one, title=title),
        opened_at=one.opened_at,
        due_at=one.due_at,
        closable=one.kind in DISMISSABLE,
    )


@router.get(TASKS_PATH, response_model=TasksView, responses=COMMON_RESPONSES)
async def my_tasks(request: Request, asked: Asked) -> TasksView:
    """This person's open tasks about documents and solutions they may still see."""
    authority = await authority_of(request, asked)

    async def load(
        session: AsyncSession,
    ) -> tuple[tuple[StewardTask, ...], dict[str, str], dict[str, str]]:
        found = await open_tasks(session)
        about_solutions = [one.item_id for one in found if one.kind is TaskKind.SOLUTION_DECIDED]
        about_documents = [
            one.item_id for one in found if one.kind is not TaskKind.SOLUTION_DECIDED
        ]
        return (
            found,
            await titles(session, about_documents),
            await solution_titles(session, about_solutions),
        )

    found, named, solutions_named = await in_transaction(request, asked, authority, load)
    shown: list[TaskView] = []
    for one in found:
        title = (
            solutions_named.get(one.item_id)
            if one.kind is TaskKind.SOLUTION_DECIDED
            else named.get(one.item_id)
        )
        # A task about a document this person no longer reaches says nothing: naming it would
        # tell them it exists.
        if title is not None:
            shown.append(_task_view(one, title))
    return TasksView(items=shown)


@router.post(TASK_DONE_PATH, response_model=TasksView, responses=COMMON_RESPONSES)
async def close(request: Request, asked: Asked, task_id: Annotated[str, _ID]) -> TasksView:
    """Close one task that only reports. A review is closed by verifying, and refused here."""
    authority = await authority_of(request, asked)

    async def work(session: AsyncSession) -> bool:
        return await close_task(session, task_id, kinds=DISMISSABLE)

    if not await in_transaction(request, asked, authority, work, attributed=True):
        raise Absent(TASK_NOT_CLOSABLE)
    return await my_tasks(request, asked)


# ------------------------------------------------------------------ the solutions
def _solution_view(one: CapturedSolution) -> SolutionView:
    return SolutionView(
        solution_id=one.solution_id,
        department=one.department,
        problem=one.problem,
        answer=one.answer,
        conversation_ref=one.conversation_ref or None,
        captured_by=one.captured_by,
        captured_at=one.captured_at,
        state=one.state.value,
        decided_by=one.decided_by or None,
        decided_at=one.decided_at,
        item_id=one.item_id if one.state is SolutionState.APPROVED else None,
    )


def _solutions_view(found: Sequence[CapturedSolution], authority: Authority) -> SolutionsView:
    return SolutionsView(
        waiting=[_solution_view(one) for one in found if may_decide(one, authority)],
        yours=[_solution_view(one) for one in found if one.captured_by == authority.principal_id],
        departments=list(authority.store_reach().departments),
    )


@router.get(SOLUTIONS_PATH, response_model=SolutionsView, responses=COMMON_RESPONSES)
async def solutions_page(request: Request, asked: Asked) -> SolutionsView:
    """What waits for this person's decision, what they captured, and where they may capture."""
    authority = await authority_of(request, asked)

    async def load(session: AsyncSession) -> tuple[CapturedSolution, ...]:
        return await solutions(session, principal_id=authority.principal_id)

    found = await in_transaction(request, asked, authority, load)
    return _solutions_view(found, authority)


@router.post(
    SOLUTIONS_PATH, status_code=201, response_model=SolutionView, responses=LIFECYCLE_RESPONSES
)
async def capture_solution(
    request: Request, asked: Asked, body: CaptureAsked
) -> SolutionView | JSONResponse:
    """A solution captured for one department, waiting for somebody else to decide it (M7.6.2)."""
    authority = await authority_of(request, asked)
    try:
        solution = capture(
            problem=body.problem,
            answer=body.answer,
            department=body.department,
            conversation_ref=body.conversation_ref,
            by=authority,
            now=asked.now,
        )
    except SolutionNotOffered as exc:
        raise Absent(str(exc)) from exc
    except LifecycleError as exc:
        return refused("problem", "not_captured", str(exc))

    async def write(session: AsyncSession) -> None:
        await put_solution(session, solution)

    await in_transaction(request, asked, authority, write, attributed=True)
    log.info("knowledge.solution_captured", principal=authority.principal_id)
    return _solution_view(solution)


@router.post(SOLUTION_DECISION_PATH, response_model=SolutionView, responses=LIFECYCLE_RESPONSES)
async def decide_solution(
    request: Request,
    asked: Asked,
    body: SolutionDecisionAsked,
    solution_id: Annotated[str, _ID],
) -> SolutionView | JSONResponse:
    """Approved into a verified document, or refused, by somebody but its capturer (M7.6.2)."""
    authority = await authority_of(request, asked)
    if body.verdict is SolutionState.PENDING:
        return refused("verdict", "not_a_decision", "a decision approves or refuses")
    if body.verdict is SolutionState.APPROVED and body.review_by is None:
        return refused("review_by", "no_review_date", "an approved solution needs a review date")
    revision = embedding_revision()

    async def work(session: AsyncSession) -> tuple[CapturedSolution, Job | None] | None:
        held = await solution_held(session, solution_id)
        if held is None or not may_decide(held, authority):
            return None
        job: Job | None = None
        if body.verdict is SolutionState.APPROVED:
            assert body.review_by is not None  # refused above
            item = approved_item(held, by=authority, review_by=body.review_by, now=asked.now)
            job = await write_solution_document(session, item, revision=revision, now=asked.now)
        moved = decided(held, by=authority, outcome=body.verdict, at=asked.now)
        await record_decision(session, moved)
        return moved, job

    try:
        done = await in_transaction(request, asked, authority, work, attributed=True)
    except SolutionNotOffered as exc:
        raise Absent(NOT_DECIDABLE) from exc
    except LifecycleError as exc:
        return refused("review_by", "not_decided", str(exc))
    except (LifecycleStoreError, ChunkStoreError) as exc:
        return refused("solution", "moved", str(exc), status=409)
    if done is None:
        raise Absent(NOT_DECIDABLE)
    moved, job = done
    await _enqueue(request, job)
    log.info("knowledge.solution_decided", principal=authority.principal_id, verdict=moved.state)
    return _solution_view(moved)
