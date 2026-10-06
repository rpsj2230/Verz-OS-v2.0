"""A connector for a new API, submitted and reviewed from the console, and nothing else here.

M11.7.8: an administrator pastes an API's specification, picks the operations, maps and classifies
the fields, gives the vendor's ceiling and chooses how its key is sent; a second person holding the
authority to connect it approves it; and from that moment it is on the Connectors screen like any
shipped source, connected through the same form and its key kept by
`brain.connector_routes.keep_credential`, read by the worker and answered from on Ask. This router
is the first two steps. `brain.ops.custom_connector` judges a definition,
`brain.ops.custom_connector_store` keeps it and refuses a self-approval, and
`brain.ops.connector_catalogue` is how an approved one becomes available, read where a declaration
is next served (`brain.reviewed_connectors`).

**Every write is asked of the authority a connection asks, for the definition's own name**
(`brain.ops.connector_admin.may_connect_source`), before anything is judged, so a person who may not
connect a source may not define one under its name either, and is refused the one way this console
refuses anybody. The list is the Connectors screen's read.

**What the review screen shows a reviewer is what they approve.** A definition is listed whole,
document included, to a reader who may connect it, and the review names the revision it was made on,
so an edit landing between reading and approving is refused rather than approved unread.

**A submitter's own approval is told, not hidden.** They can see the definition, so the refusal says
why in words (`NOBODY_APPROVES_THEIR_OWN_DEFINITION`) as a 422 with a code, rather than as the
console's one refusal, which would read as a fault.

**The specification arrives as the text that was pasted**, and is parsed here with its size cap
before anything else is built from it; an external `$ref` is refused at that step
(`brain.ops.custom_connector.A_SPECIFICATION_NEVER_FETCHES`).

Task ids: M11.7.8
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain import demo
from brain.api import API_PREFIX, COMMON_RESPONSES, NoEchoRoute
from brain.api_routes import Asked
from brain.connectors.declaration import KeyScheme, shipped
from brain.connectors.manifest import FieldShape
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.core.field_policy import Classification
from brain.ops.connectable import CONNECTABLE
from brain.ops.connector_admin import may_connect_source
from brain.ops.connector_slots import SLOT_SCOPES
from brain.ops.custom_connector import (
    MAX_DOCUMENT_BYTES,
    SCHEMES,
    Ceiling,
    CustomConnectorError,
    CustomDefinition,
    DefinitionProblem,
    EntityDefinition,
    MappedField,
    ReviewState,
    parse_document,
    problems,
)
from brain.ops.custom_connector_store import (
    NOBODY_APPROVES_THEIR_OWN_DEFINITION,
    DefinitionMovedError,
    DefinitionTakenError,
    NoSuchDefinitionError,
    OwnDefinitionError,
    StoredCustomConnectors,
    StoredDefinition,
    entities_json,
)
from brain.ops.skill_fetch import SystemResolver
from brain.reviewed_connectors import current as reviewed_now
from brain.routing_routes import sessions_of
from brain.tools.fetch import Resolver
from brain.tools.startup import BUILT_IN_ROW_ENTITIES

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: What a person is told when a definition is kept.
SUBMITTED: Final = (
    "Kept, waiting for review. It is not offered, has no tools and is not read until a second "
    "person who may connect it approves it."
)

#: What a reviewer is told after deciding.
APPROVED: Final = (
    "Approved. It is on the Connectors screen now, connected with its key like any source, and "
    "its records reach an agent and Ask once it is connected and read."
)
REJECTED: Final = "Rejected. It stays listed, and is not offered."

#: What the review screen says before anybody decides.
THE_REVIEW: Final = (
    "A second person who may connect this source reads the specification, the operations, every "
    "mapped field with its classification, the department and the ceiling, and approves or "
    "rejects exactly that revision. Nobody approves their own, and any change sends it back here."
)

#: Where a definition is submitted, changed, decided and listed.
DEFINITIONS_PATH: Final = "/custom-connectors"
DEFINITION_PATH: Final = DEFINITIONS_PATH + "/{name}"
REVIEW_PATH: Final = DEFINITION_PATH + "/review"

#: The longest pasted specification the body accepts: the domain's cap, with room for escaping.
MAX_DOCUMENT_CHARS: Final = MAX_DOCUMENT_BYTES

router = APIRouter(prefix=API_PREFIX, tags=["connectors"], route_class=NoEchoRoute)


# ------------------------------------------------------------------------ the shapes
class FieldAsked(BaseModel):
    """One mapped field: our name, the vendor's path, its classification, and how it is kept."""

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1, max_length=64)
    source_path: str = Field(min_length=1, max_length=200)
    classification: Classification
    kept: FieldShape | None = None


class EntityAsked(BaseModel):
    """One entity: its operations, its id, the field it is named by, its words and its fields."""

    model_config = ConfigDict(extra="forbid")

    entity: str = Field(min_length=1, max_length=64)
    list_operation: str = Field(min_length=1, max_length=80)
    one_operation: str | None = Field(default=None, max_length=80)
    id_path: str = Field(min_length=1, max_length=200)
    named_by: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=300)
    fields: list[FieldAsked] = Field(min_length=1, max_length=24)


class DefinitionAsked(BaseModel):
    """A definition as the submit form sends it. The specification is the text pasted."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=80)
    document: str = Field(min_length=2, max_length=MAX_DOCUMENT_CHARS)
    entities: list[EntityAsked] = Field(min_length=1, max_length=8)
    key_scheme: KeyScheme
    ceiling_per_minute: int | None = None
    ceiling_per_day: int | None = None
    ceiling_cited: str = Field(default="", max_length=500)
    department: str = Field(min_length=1, max_length=64)
    page_parameter: str | None = Field(default=None, max_length=80)
    page_size: int | None = None


class ReviewAsked(BaseModel):
    """A decision on the revision the reviewer read."""

    model_config = ConfigDict(extra="forbid")

    approve: bool
    revision: int = Field(ge=1)


class DefinitionProblemView(BaseModel):
    field: str
    code: str
    message: str


class DefinitionProblemsView(BaseModel):
    """Everything wrong with what was sent, by field, and nothing kept."""

    problems: list[DefinitionProblemView]


class DefinitionView(BaseModel):
    """One definition as the review screen shows it."""

    name: str
    label: str
    state: ReviewState
    revision: int
    department: str
    key_scheme: KeyScheme
    ceiling_per_minute: int
    ceiling_per_day: int | None
    ceiling_cited: str
    page_parameter: str | None
    page_size: int | None
    entities: list[EntityAsked]
    #: The specification, for a reader who may connect this source, and nothing for anybody else.
    document: dict[str, object] | None
    submitted_by: str
    submitted_at: datetime
    reviewed_by: str | None
    reviewed_at: datetime | None
    #: Whether this reader may approve or reject this revision now.
    reviewable: bool
    #: Whether the Connectors screen offers it now.
    offered: bool


class DefinitionsPage(BaseModel):
    """Every definition this reader may be told of, and what the submit form chooses from."""

    definitions: list[DefinitionView]
    classifications: list[Classification]
    shapes: list[FieldShape]
    schemes: list[KeyScheme]
    review: str


class DefinitionChangedView(BaseModel):
    """What a submit, a change or a decision did."""

    definition: DefinitionView
    told: str


_WRITE_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    422: {"model": DefinitionProblemsView, "description": "What is wrong with what was sent."},
}


# ------------------------------------------------------------------------ the wiring
def _not_answerable(surface: str) -> Absent:
    """The one refusal, as `brain.connector_routes` makes it. `surface` reaches a log only."""
    log.info("custom connector surface not answerable", surface=surface)
    return Absent("this part of the console is not answerable for this caller")


def store_of(request: Request) -> StoredCustomConnectors:
    """`app.state.custom_connectors` when a test put one there, and the database otherwise."""
    found = getattr(request.app.state, "custom_connectors", None)
    if isinstance(found, StoredCustomConnectors):
        return found
    sessions: async_sessionmaker[AsyncSession] | None = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredCustomConnectors(sessions)


def resolver_of(request: Request) -> Resolver:
    """`app.state.connector_resolver` when a test put one there, and the system's otherwise."""
    found = getattr(request.app.state, "connector_resolver", None)
    if isinstance(found, Resolver):
        return found
    return SystemResolver()


def taken_names() -> frozenset[str]:
    """Names a definition may not have: a shipped connector, a key slot, the demo's source."""
    return frozenset({*shipped(), *SLOT_SCOPES, demo.DEMO_SOURCE})


def taken_entities(others: Iterable[CustomDefinition]) -> frozenset[str]:
    """Entities another source already has, whose capabilities a definition would share."""
    found = {one.entity for one in BUILT_IN_ROW_ENTITIES}
    found |= {one.entity for one in demo.row_classifications()}
    for declared in shipped().values():
        if declared.ask is not None:
            found |= {one.entity for one in declared.ask.entities}
        if declared.reading is not None:
            found |= set(declared.reading.entities())
    for other in others:
        found |= {one.entity for one in other.entities}
    return frozenset(found)


def definition_of(body: DefinitionAsked, document: dict[str, object]) -> CustomDefinition:
    """What was sent, as a definition. Judged by `problems` before anything is kept."""
    ceiling = (
        None
        if body.ceiling_per_minute is None
        else Ceiling(
            per_minute=body.ceiling_per_minute,
            per_day=body.ceiling_per_day,
            cited=body.ceiling_cited,
        )
    )
    return CustomDefinition(
        name=body.name.strip(),
        label=body.label.strip(),
        document=document,
        entities=tuple(
            EntityDefinition(
                entity=one.entity.strip(),
                list_operation=one.list_operation.strip(),
                one_operation=(one.one_operation or "").strip() or None,
                id_path=one.id_path.strip(),
                named_by=one.named_by.strip(),
                description=one.description.strip(),
                fields=tuple(
                    MappedField(
                        target=field.target.strip(),
                        source_path=field.source_path.strip(),
                        classification=field.classification,
                        kept=field.kept,
                    )
                    for field in one.fields
                ),
            )
            for one in body.entities
        ),
        key_scheme=body.key_scheme,
        # A scheme the domain does not allow is refused by `problems`; the shape is its partner.
        credential_shape=SCHEMES.get(body.key_scheme, next(iter(SCHEMES.values()))),
        ceiling=ceiling,
        department=body.department.strip(),
        page_parameter=(body.page_parameter or "").strip() or None,
        page_size=body.page_size,
    )


def _problems(found: Iterable[DefinitionProblem]) -> JSONResponse:
    view = DefinitionProblemsView(
        problems=[
            DefinitionProblemView(field=one.field, code=one.code, message=one.message)
            for one in found
        ]
    )
    return JSONResponse(status_code=422, content=view.model_dump(mode="json"))


def view_of(one: StoredDefinition, reach: EntitlementSet, now: datetime) -> DefinitionView:
    definition = one.definition
    may = may_connect_source(reach, definition.name, now)
    ceiling = definition.ceiling
    return DefinitionView(
        name=definition.name,
        label=definition.label,
        state=one.state,
        revision=definition.revision,
        department=definition.department,
        key_scheme=definition.key_scheme,
        ceiling_per_minute=0 if ceiling is None else ceiling.per_minute,
        ceiling_per_day=None if ceiling is None else ceiling.per_day,
        ceiling_cited="" if ceiling is None else ceiling.cited,
        page_parameter=definition.page_parameter,
        page_size=definition.page_size,
        entities=[EntityAsked.model_validate(raw) for raw in entities_json(definition)],
        document=dict(definition.document) if may else None,
        submitted_by=one.submitted_by,
        submitted_at=one.submitted_at,
        reviewed_by=one.reviewed_by,
        reviewed_at=one.reviewed_at,
        reviewable=(
            may and one.state is ReviewState.UNREVIEWED and one.submitted_by != reach.principal_id
        ),
        offered=definition.name in CONNECTABLE,
    )


def _trace_id() -> str:
    return uuid.uuid4().hex


def _told(view: DefinitionView, told: str) -> JSONResponse:
    answered = DefinitionChangedView(definition=view, told=told)
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))


# ------------------------------------------------------------------------ the routes
@router.get(DEFINITIONS_PATH, response_model=DefinitionsPage, responses=COMMON_RESPONSES)
async def definitions(request: Request, asked: Asked) -> DefinitionsPage:
    """Every definition, for a reader of the Connectors screen, and what the form chooses from."""
    if not permitted(screen("connectors").read, asked.reach, asked.now):
        raise _not_answerable("custom connectors")
    await reviewed_now(request.app.state)
    found = await store_of(request).listed()
    return DefinitionsPage(
        definitions=[view_of(one, asked.reach, asked.now) for one in found],
        classifications=list(Classification),
        shapes=list(FieldShape),
        schemes=list(SCHEMES),
        review=THE_REVIEW,
    )


#: What a submit, a change or a decision produced: the definition kept, or every problem.
Outcome = StoredDefinition | tuple[DefinitionProblem, ...]

#: What a submitter is told of their own approval.
OWN: Final = DefinitionProblem(
    field="review", code="own_definition", message=NOBODY_APPROVES_THEIR_OWN_DEFINITION
)
MOVED: Final = DefinitionProblem(
    field="review",
    code="moved",
    message=(
        "This definition changed or was decided since you read it. Read it again and decide on "
        "what it says now."
    ),
)
EXISTS: Final = DefinitionProblem(
    field="name", code="exists", message="A definition by that name exists. Change it there."
)


async def judged(
    store: StoredCustomConnectors, body: DefinitionAsked, *, resolver: Resolver
) -> CustomDefinition | tuple[DefinitionProblem, ...]:
    """The definition sent, or every problem it has. Parsed with its cap before anything else."""
    try:
        document = parse_document(body.document)
    except CustomConnectorError as refused:
        return refused.problems
    definition = definition_of(body, document)
    others = [one.definition for one in await store.listed() if one.definition.name != body.name]
    found = problems(
        definition,
        resolver=resolver,
        taken_names=taken_names(),
        taken_entities=taken_entities(others),
    )
    return found or definition


async def submission(
    store: StoredCustomConnectors,
    body: DefinitionAsked,
    *,
    reach: EntitlementSet,
    now: datetime,
    resolver: Resolver,
) -> Outcome:
    """A new definition kept, waiting for a second person, or why not. What `POST` runs."""
    if not may_connect_source(reach, body.name.strip(), now):
        raise _not_answerable("submit")
    found = await judged(store, body, resolver=resolver)
    if isinstance(found, tuple):
        return found
    try:
        return await store.submit(
            found, by=reach.principal_id, ent_hash=reach.ent_hash(), trace_id=_trace_id()
        )
    except DefinitionTakenError:
        return (EXISTS,)


async def changing(
    store: StoredCustomConnectors,
    name: str,
    body: DefinitionAsked,
    *,
    reach: EntitlementSet,
    now: datetime,
    resolver: Resolver,
) -> Outcome:
    """A definition changed, a new revision waiting for review again, or why not."""
    if not may_connect_source(reach, name, now) or body.name.strip() != name:
        raise _not_answerable("change")
    if await store.one(name) is None:
        raise _not_answerable("change")
    found = await judged(store, body, resolver=resolver)
    if isinstance(found, tuple):
        return found
    try:
        return await store.change(
            found, by=reach.principal_id, ent_hash=reach.ent_hash(), trace_id=_trace_id()
        )
    except NoSuchDefinitionError as absent:
        raise _not_answerable("change") from absent


async def deciding(
    store: StoredCustomConnectors,
    name: str,
    body: ReviewAsked,
    *,
    reach: EntitlementSet,
    now: datetime,
) -> Outcome:
    """The revision read, approved or rejected by a second person, or why not."""
    if not may_connect_source(reach, name, now):
        raise _not_answerable("review")
    try:
        return await store.decide(
            name,
            approve=body.approve,
            revision=body.revision,
            by=reach.principal_id,
            at=now,
            ent_hash=reach.ent_hash(),
            trace_id=_trace_id(),
        )
    except NoSuchDefinitionError as absent:
        raise _not_answerable("review") from absent
    except OwnDefinitionError:
        return (OWN,)
    except DefinitionMovedError:
        return (MOVED,)


def _answered(found: Outcome, reach: EntitlementSet, now: datetime, told: str) -> JSONResponse:
    if isinstance(found, tuple):
        return _problems(found)
    return _told(view_of(found, reach, now), told)


@router.post(DEFINITIONS_PATH, response_model=DefinitionChangedView, responses=_WRITE_RESPONSES)
async def submit(request: Request, body: DefinitionAsked, asked: Asked) -> JSONResponse:
    """Keep a new definition, waiting for a second person, or say everything wrong with it."""
    found = await submission(
        store_of(request),
        body,
        reach=asked.reach,
        now=asked.now,
        resolver=resolver_of(request),
    )
    log.info("connector definition submitted", principal=asked.reach.principal_id)
    return _answered(found, asked.reach, asked.now, SUBMITTED)


@router.post(DEFINITION_PATH, response_model=DefinitionChangedView, responses=_WRITE_RESPONSES)
async def change(request: Request, name: str, body: DefinitionAsked, asked: Asked) -> JSONResponse:
    """Change a definition: a new revision, waiting for review again whatever it was before."""
    found = await changing(
        store_of(request),
        name,
        body,
        reach=asked.reach,
        now=asked.now,
        resolver=resolver_of(request),
    )
    log.info("connector definition changed", name=name, principal=asked.reach.principal_id)
    return _answered(found, asked.reach, asked.now, SUBMITTED)


@router.post(REVIEW_PATH, response_model=DefinitionChangedView, responses=_WRITE_RESPONSES)
async def review(request: Request, name: str, body: ReviewAsked, asked: Asked) -> JSONResponse:
    """Approve or reject the revision the reviewer read, as a second person, or say why not."""
    found = await deciding(store_of(request), name, body, reach=asked.reach, now=asked.now)
    # Read again, so an approval made here is said to be offered in this same answer.
    await reviewed_now(request.app.state)
    log.info("connector definition reviewed", name=name, principal=asked.reach.principal_id)
    return _answered(found, asked.reach, asked.now, APPROVED if body.approve else REJECTED)
