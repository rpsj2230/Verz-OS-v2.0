"""Asking for access over HTTP: the asker learns nothing, and the owner sees the question.

`brain.core.access_route.route_access_request` is the one place a lock becomes a notice, and until
this module nothing called it (M4.3.4). An answer that stated a department gap told the asker
they could request access and gave them nowhere to do it (M2.2.4). Two routes close both.

**`POST /access-requests` answers every request with the same 202 and the same sentence.**
`brain.core.redaction.ASKER_ACKNOWLEDGEMENT`, whether a notice was stored, whether the field is
classified, whether anybody owns it, whether the department exists. Every one of those would be an
oracle; see `brain.core.access_route`. What is refused with a 422 is only the shape of the body,
which is the asker's own typing and says nothing about the company.

**A request is stored only where it could be granted.** A field request needs the caller to reach
rows of the entity already, because a lock is only ever shown on a record they may see, and not to
hold the field's capability, because then there is nothing to ask for. A department request needs
the caller's knowledge scope not to admit the department, `brain.core.department.admits_department`,
the same decision the answer's gap came from. Anything else stores nothing and says the same.

**The owner is the data steward.** `brain.identity.data_steward` argues that every read of the
company's data begins with that person: they are the one principal every install has who can
grant a data read, so a request routed anywhere else could arrive at somebody who cannot act on it.
An install with no steward stores nothing, logged as an operations fault and invisible to the asker.

**`GET /access-requests` is the owner's list, and is how a request is delivered.** It returns the
requests addressed to the caller and nobody else, newest first, with the question in the asker's
words; no grant opens it and none is needed, because it holds only what was sent to the reader.

Task ids: M4.3.4, M2.2.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from brain.api import API_PREFIX, COMMON_RESPONSES, Page
from brain.api_routes import Asked, Asking
from brain.core.access_route import CapabilityOwner, OwnerDirectory, route_access_request
from brain.core.department import SLUG_PATTERN, admits_department
from brain.core.errors import Failed
from brain.core.redaction import ASKER_ACKNOWLEDGEMENT, LockedField
from brain.identity.data_steward import steward_in
from brain.knowledge.rows import row_scope_for
from brain.knowledge.search import KNOWLEDGE_READ
from brain.listing import Column, ListAsked, Listing
from brain.ops.access_request_store import Request as Stored
from brain.ops.access_request_store import addressed_to, record
from brain.routing_routes import sessions_of
from brain.tables.access_request import NAME_PATTERN, QUESTION_CHARS
from brain.tools.startup import classification_for

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["access"])

ACCESS_REQUESTS_PATH: Final = "/access-requests"

#: How many requests addressed to one owner one read loads before the list is cut. A resource
#: bound on the load, applied to rows that are all the reader's own; the page is cut by the
#: listing's own limit and cursor after it.
MAX_LOADED: Final = 2000

#: A lock carries a record id the asker was shown; the request is about the field, so the id is
#: not kept, and this stands in for it when the lock is rebuilt for routing.
ANY_RECORD: Final = "any"


class AccessAsked(BaseModel):
    """One request: a locked field (`entity` and `field`) or a department, and the question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: Annotated[
        str, StringConstraints(min_length=1, max_length=QUESTION_CHARS, strip_whitespace=True)
    ]
    entity: Annotated[str, StringConstraints(pattern=NAME_PATTERN, max_length=120)] | None = None
    field: Annotated[str, StringConstraints(pattern=NAME_PATTERN, max_length=120)] | None = None
    department: Annotated[str, StringConstraints(pattern=SLUG_PATTERN, max_length=60)] | None = None

    @model_validator(mode="after")
    def _one_subject(self) -> AccessAsked:
        a_field = self.entity is not None and self.field is not None and self.department is None
        a_department = self.entity is None and self.field is None and self.department is not None
        if not (a_field or a_department):
            msg = "name a field on an entity, or a department, and only one of them"
            raise ValueError(msg)
        return self


class AccessAcknowledged(BaseModel):
    """What the asker is told. One constant, whatever happened."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message: str


class AccessRequestView(BaseModel):
    """One request addressed to the reader, as its owner sees it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    asker_id: str
    #: `entity.field`, or `department:<slug>`.
    subject: str
    question: str
    requested_capability: str
    requested_at: datetime


class AccessRequestsPage(Page[AccessRequestView]):
    """One page of the requests addressed to the reader, newest first unless asked otherwise.

    `total` is inherited and never populated; every row is the reader's own, so a count would say
    nothing hidden, and none is computed anyway. `truncated` says a further row matches.
    """

    truncated: bool = False


#: What the owner's list may search, filter and order by: the fields a row shows.
REQUESTS: Final[Listing[AccessRequestView]] = Listing(
    name="access-requests",
    columns=(
        Column("requested_at", lambda row: row.requested_at.isoformat(), sort=True),
        Column("asker_id", lambda row: row.asker_id, search=True, filter=True, sort=True),
        Column("subject", lambda row: row.subject, search=True, filter=True, sort=True),
        Column("requested_capability", lambda row: row.requested_capability, filter=True),
        Column("question", lambda row: row.question, search=True),
    ),
    key=lambda row: row.request_id,
    order="-requested_at",
)
RequestsQuery = Annotated[ListAsked, Depends(REQUESTS.query())]


def field_request(asked: Asking, body: AccessAsked, steward: str) -> Stored | None:
    """The request to store for a locked field, or None where nothing could be granted."""
    assert body.entity is not None and body.field is not None
    classification = classification_for(body.entity)
    if classification is None or row_scope_for(body.entity, asked.reach, asked.now) is None:
        # No lock is ever shown on an entity nobody classified, or on rows the caller cannot see.
        return None
    policy = classification.policy()
    rule = policy.rule_for(body.entity, body.field)
    if rule is not None and asked.reach.holds(rule.required_capability, asked.now):
        # Already held: there is no lock on this field for this caller, and nothing to ask for.
        return None
    routed = route_access_request(
        LockedField(entity=body.entity, record_id=ANY_RECORD, field=body.field),
        asker_id=asked.caller.principal.id,
        question=body.question,
        policy=policy,
        owners=OwnerDirectory(
            owners=()
            if rule is None
            else (CapabilityOwner(capability=rule.required_capability, principal_id=steward),)
        ),
    )
    if routed.notice is None:
        return None
    return Stored(
        asker_id=routed.notice.asker_id,
        owner_id=routed.owner_id,
        question=routed.notice.question,
        requested_capability=routed.notice.requested_capability.value,
        entity=routed.notice.entity,
        field=routed.notice.field,
    )


def department_request(asked: Asking, body: AccessAsked, steward: str) -> Stored | None:
    """The request to store for a department, or None where the caller already reaches it."""
    assert body.department is not None
    scope = asked.reach.scope_for(KNOWLEDGE_READ, asked.now)
    if scope is not None and admits_department(scope, body.department):
        return None
    return Stored(
        asker_id=asked.caller.principal.id,
        owner_id=steward,
        question=body.question,
        requested_capability=KNOWLEDGE_READ.value,
        department=body.department,
    )


@router.post(
    ACCESS_REQUESTS_PATH,
    status_code=202,
    response_model=AccessAcknowledged,
    responses=COMMON_RESPONSES,
)
async def ask_for_access(request: Request, body: AccessAsked, asked: Asked) -> JSONResponse:
    """Pass a request on to whoever can decide it, and tell the asker one constant sentence."""
    sessions = sessions_of(request)
    if sessions is None:
        # Unreachable in practice: `asking` refuses before this on a process with no database.
        raise Failed("no database on this process")
    async with sessions() as session:
        steward = await steward_in(session)
        if steward is None:
            log.warning("access_request.no_steward")
        else:
            stored = (
                department_request(asked, body, steward)
                if body.department is not None
                else field_request(asked, body, steward)
            )
            if stored is not None:
                await record(session, stored, at=asked.now)
                await session.commit()
                log.info("access_request.stored", owner_id=stored.owner_id)
    return JSONResponse(
        status_code=202, content=AccessAcknowledged(message=ASKER_ACKNOWLEDGEMENT).model_dump()
    )


@router.get(ACCESS_REQUESTS_PATH, response_model=AccessRequestsPage, responses=COMMON_RESPONSES)
async def access_requests(
    request: Request, asked: Asked, listed: RequestsQuery
) -> AccessRequestsPage:
    """One page of the requests addressed to the caller. Nobody else's."""
    plan = REQUESTS.plan(listed, reader=asked.caller.principal.id)
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    async with sessions() as session:
        rows = await addressed_to(session, asked.caller.principal.id, limit=MAX_LOADED)
    views = [
        AccessRequestView(
            request_id=str(row.id),
            asker_id=row.asker_id,
            subject=f"department:{row.department}"
            if row.department is not None
            else f"{row.entity}.{row.field}",
            question=row.question,
            requested_capability=row.requested_capability,
            requested_at=row.requested_at,
        )
        for row in rows
    ]
    page = plan.page(views)
    return AccessRequestsPage(
        items=list(page.items), next_cursor=page.next_cursor, truncated=page.next_cursor is not None
    )
