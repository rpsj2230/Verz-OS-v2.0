"""The provider registry from the console: terms recorded, a provider added, the record exported.

`brain.provider_routes` shows every provider and its rungs and switches one on or off. This is
the other half of the Models screen: the writes to `ops.model_provider` and the one document the
registry exports. `brain.models.registry` argues what a row means.

**Recording terms** (M5.6.4, M5.5.3, M5.1.3) is `PUT /models/providers/{provider}/terms`: the
processing region and residency class, where the provider keeps what it is sent, its retention
and training terms, a link to the signed agreement, and the per-lane overrides. A built-in
provider has no row until somebody records its terms, and the first save writes one. A lane
override that would take the answer lane past its wall-clock budget is refused before it is
written, by `driver.check_answer_lane_budget`, which is the call that function's own docstring
says it is for and which nothing made until now.

**Adding a provider** (M5.7.2) is `POST /models/providers`: a name, a label, an https address,
the model names and a key. **The key is written to the vault before the row exists**, so a
provider whose key the vault refused is not left on the screen without one, and the response
never carries it: the route is a `NoEchoRoute`, and the answer is the providers view. A rung is
then added for one of its models through the matrix gate (`brain.routing_routes`), which is how
it takes traffic, and a switch and a check work on it at once.

**Adding needs two authorities**, the matrix write and the credential authority, each held over
everything: it both changes where questions may go and writes a key every question to it is sent
with, and each of those is its own route's rule (`brain.routing_routes`, `brain.credential_routes`).
Both are asked before the body is looked at, and a caller missing either gets the one refusal
this router makes.

**Retiring an added provider** sets `deleted_at`; its rungs then have no transport and are left
out with that reason. It is how an address is changed: retire, then add again with a key. A
built-in provider cannot be retired, because it is the product's.

**The register export** (M5.6.4) is one Markdown document: each provider, its terms, and what it
has been sent by category with counts, generated at the moment it was asked for, answered as JSON
with the name to save it under so the console hands it to the browser as a file. Markdown because
a company shows it as it is, prints it, or pastes it into a contract annex, and it needs nothing
to open.

Rejected: an audit ledger entry per terms edit. The ledger's action list is a check constraint
that four workstreams widen this wave, and a fifth widening in the same release is a merge
conflict in the database; the key write is on the ledger already, through the credential record,
and a terms edit is logged. It is the next migration's to add.

Task ids: M5.6.4, M5.7.2, M5.1.3, M5.5.3
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, insert, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES, NoEchoRoute
from brain.api_routes import Asked
from brain.core.errors import BrainError, Failed
from brain.credential_routes import (
    NOT_KEPT_STATUS,
    CredentialNotKeptView,
    CredentialProblemsView,
    CredentialProblemView,
    credentials_of,
    may_manage,
)
from brain.models.disclosure import TOLD as CATEGORY_TOLD
from brain.models.driver import check_answer_lane_budget
from brain.models.registry import (
    MAX_MODELS,
    ProviderKind,
    ProviderRecord,
    RegistryError,
    check_added,
    check_agreement,
    parse_lane_overrides,
)
from brain.models.routing import TIER_LADDER, ResidencyClass
from brain.models.wire import LOCAL_PROVIDER
from brain.ops.credentials import (
    TOLD as VAULT_TOLD,
)
from brain.ops.credentials import (
    CredentialProblemError,
    CredentialSlot,
    CredentialsUnavailableError,
)
from brain.ops.model_service import disclosure_counts, disclosures
from brain.ops.provider_keys import PROCESS_ADDED_SLOTS, PROVIDER_SLOTS, added_slot
from brain.provider_routes import (
    ProvidersView,
    _not_answerable,
    _sessions,
    _trace_id,
    _view,
    listed_providers,
    may_read,
    may_switch,
    models_of,
)
from brain.tables.model_registry import ModelProviderRow

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why adding a provider asks for two authorities.
ADDING_A_PROVIDER_IS_A_ROUTE_CHANGE_AND_A_KEY_WRITE: Final = (
    "An added provider is somewhere questions may be sent and a key every one of them goes out "
    "with. The matrix write governs the first and the credential authority the second, each held "
    "over everything, so adding needs both, asked before the body is read."
)

#: Why the key is written before the row.
THE_KEY_IS_KEPT_BEFORE_THE_PROVIDER_EXISTS: Final = (
    "A provider row with no key is a provider on the screen whose every call is refused. Writing "
    "the key first means a vault that refused it leaves nothing behind, and a row that then fails "
    "to insert leaves a key in a slot nobody routes to, which the next add of the same name "
    "replaces."
)

#: The widths the table declares, so a value the column cannot hold is refused here.
LABEL_CHARS: Final = 80
ADDRESS_CHARS: Final = 300
REGION_CHARS: Final = 64
TERMS_CHARS: Final = 1000

#: Where the export is served, below the providers collection.
REGISTER_PATH: Final = "/models/providers-register"


# ------------------------------------------------------------------------ the shapes


class TermsAsked(BaseModel):
    """What the company agreed with a provider, and its lane overrides. Every field is sent.

    `models` is only for an added provider, whose model names may be revised; a built-in
    provider's rungs name its models on the Routing screen.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    processing_region: Annotated[str, Field(min_length=1, max_length=REGION_CHARS)]
    residency_class: ResidencyClass
    storage_location: Annotated[str, Field(max_length=ADDRESS_CHARS)]
    retention_terms: Annotated[str, Field(max_length=TERMS_CHARS)]
    training_terms: Annotated[str, Field(max_length=TERMS_CHARS)]
    agreement_url: Annotated[str, Field(max_length=ADDRESS_CHARS)] | None
    lane_overrides: dict[str, dict[str, Any]]
    models: Annotated[list[str], Field(max_length=MAX_MODELS)] | None = None


class AddAsked(BaseModel):
    """An OpenAI-compatible provider: its name, label, address, model names and key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: Annotated[str, Field(min_length=2, max_length=31)]
    label: Annotated[str, Field(min_length=1, max_length=LABEL_CHARS)]
    base_url: Annotated[str, Field(min_length=9, max_length=ADDRESS_CHARS)]
    models: Annotated[list[str], Field(min_length=1, max_length=MAX_MODELS)]
    key: str


# ------------------------------------------------------------------------ the helpers


def _problem(field: str, message: str) -> JSONResponse:
    """A 422 naming the field and saying what to do, never repeating what was sent."""
    told = CredentialProblemsView(
        problems=(CredentialProblemView(field=field, code="refused", message=message),)
    )
    return JSONResponse(status_code=422, content=told.model_dump(mode="json"))


def _require(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = _sessions(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def overrides_fit_the_answer_lane(
    records: dict[str, ProviderRecord], plan_chain: Any, candidate: ProviderRecord
) -> str | None:
    """Why these overrides would take the answer lane past its budget, or None when they fit."""
    clients = {slug: record.client for slug, record in records.items()}
    clients[candidate.slug] = candidate.client
    for tier in TIER_LADDER:
        try:
            check_answer_lane_budget(plan_chain, tier, clients)
        except ValueError as over:
            return str(over)
    return None


def register_document(
    records: list[ProviderRecord],
    disclosed: dict[str, dict[Any, int]],
    *,
    listed: tuple[str, ...],
    at: datetime,
) -> str:
    """The register as one Markdown document: each provider's terms and what it was sent."""
    by_slug = {one.slug: one for one in records}
    lines = [
        "# Model provider register",
        "",
        f"Generated {at.strftime('%Y-%m-%d %H:%M UTC')}.",
        "",
        "Each provider this install may send data to, what the company agreed with it, and how "
        "many model calls carried each category of data. Counts are calls, not people.",
    ]
    for slug in listed:
        record = by_slug.get(slug)
        lines += ["", f"## {slug}" if record is None else f"## {record.label} ({slug})", ""]
        if record is None:
            lines.append("- No terms recorded.")
        else:
            lines += [
                f"- Kind: {record.kind.value}",
                *([f"- Address: {record.base_url}"] if record.base_url else []),
                *([f"- Models: {', '.join(record.models)}"] if record.models else []),
                f"- Processing region: {record.processing_region}",
                f"- Residency: {record.residency_class.value}",
                f"- Storage location: {record.storage_location or 'not recorded'}",
                f"- Retention terms: {record.retention_terms or 'not recorded'}",
                f"- Training terms: {record.training_terms or 'not recorded'}",
                f"- Signed agreement: {record.agreement_url or 'not recorded'}",
            ]
        sent = disclosed.get(slug, {})
        if not sent:
            lines.append("- Data sent: none recorded.")
        else:
            lines.append("- Data sent:")
            lines += [
                f"  - {CATEGORY_TOLD[category]}: {count} calls"
                for category, count in sorted(sent.items())
            ]
    return "\n".join(lines) + "\n"


router = APIRouter(prefix=API_PREFIX, tags=["models"], route_class=NoEchoRoute)

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": CredentialNotKeptView, "description": "No vault, or the vault refused."},
    422: {"model": CredentialProblemsView, "description": "What is wrong with what was sent."},
    503: {"model": CredentialNotKeptView, "description": "The vault did not answer."},
}

_REFUSED: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    422: {"model": CredentialProblemsView, "description": "What is wrong with what was sent."},
}


@router.put("/models/providers/{provider}/terms", response_model=ProvidersView, responses=_REFUSED)
async def record_terms(
    request: Request, provider: str, body: TermsAsked, asked: Asked
) -> JSONResponse | ProvidersView:
    """Record what the company agreed with one provider, and its lane overrides."""
    if not may_switch(asked.reach, asked.now):
        log.info("provider terms refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    calls = models_of(request).calls
    plan = await calls.planned()
    if provider not in listed_providers(plan):
        log.info("provider terms name no provider", principal=asked.caller.principal.id)
        raise _not_answerable()
    try:
        check_agreement(body.agreement_url)
        overrides = parse_lane_overrides(body.lane_overrides)
    except RegistryError as refused:
        return _problem("terms", str(refused))
    records = {one.slug: one for one in plan.state.providers}
    existing = records.get(provider)
    kind = ProviderKind.BUILTIN if existing is None else existing.kind
    if body.models is not None and kind is not ProviderKind.OPENAI_COMPATIBLE:
        return _problem("models", "only an added provider's model names are edited here")
    try:
        candidate = ProviderRecord(
            slug=provider,
            kind=kind,
            label=provider if existing is None else existing.label,
            base_url=None if existing is None else existing.base_url,
            models=tuple(body.models)
            if body.models is not None
            else (() if existing is None else existing.models),
            processing_region=body.processing_region.strip(),
            residency_class=body.residency_class,
            storage_location=body.storage_location.strip(),
            retention_terms=body.retention_terms.strip(),
            training_terms=body.training_terms.strip(),
            agreement_url=body.agreement_url,
            lane_overrides=overrides,
        )
        if candidate.base_url is not None:
            check_added(provider, candidate.base_url, candidate.models, taken=())
    except RegistryError as refused:
        return _problem("terms", str(refused))
    over = overrides_fit_the_answer_lane(records, plan.assembly.chain, candidate)
    if over is not None:
        return _problem("lane_overrides", over)
    values: dict[str, Any] = {
        "models": list(candidate.models),
        "processing_region": candidate.processing_region,
        "residency_class": candidate.residency_class.value,
        "storage_location": candidate.storage_location,
        "retention_terms": candidate.retention_terms,
        "training_terms": candidate.training_terms,
        "agreement_url": candidate.agreement_url,
        "lane_overrides": {
            lane.value: {
                key: value
                for key, value in (
                    ("timeout_seconds", one.timeout_seconds),
                    ("attempts", one.attempts),
                )
                if value is not None
            }
            for lane, one in candidate.lane_overrides.items()
        },
        "updated_by": asked.caller.principal.id,
    }
    async with _require(request)() as session:
        if existing is None:
            described = {one.slug: one.description for one in PROVIDER_SLOTS}
            await session.execute(
                insert(ModelProviderRow).values(
                    slug=provider,
                    kind=ProviderKind.BUILTIN.value,
                    label=described.get(provider, provider)[:LABEL_CHARS] or provider,
                    **values,
                )
            )
        else:
            await session.execute(
                update(ModelProviderRow)
                .where(ModelProviderRow.slug == provider, ModelProviderRow.deleted_at.is_(None))
                .values(**values)
            )
        await session.commit()
    log.info("provider terms recorded", provider=provider, principal=asked.caller.principal.id)
    return await _view(request, asked, calls)


@router.post("/models/providers", response_model=ProvidersView, responses=_TOLD)
async def add_provider(
    request: Request, body: AddAsked, asked: Asked
) -> JSONResponse | ProvidersView:
    """Add an OpenAI-compatible provider: its key to the vault first, then its row."""
    if not (may_switch(asked.reach, asked.now) and may_manage(asked.reach, asked.now)):
        log.info("provider add refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    calls = models_of(request).calls
    plan = await calls.planned()
    taken = (*listed_providers(plan), *(one.slug for one in PROVIDER_SLOTS), LOCAL_PROVIDER)
    try:
        check_added(body.slug, body.base_url, body.models, taken=taken)
    except RegistryError as refused:
        return _problem("provider", str(refused))
    factory = _require(request)
    provider_slot = added_slot(body.slug)
    slot = CredentialSlot(
        path=provider_slot.path, description=provider_slot.description, provider=provider_slot
    )
    store = credentials_of(request)
    try:
        await store.keep(
            slot,
            body.key,
            actor=asked.reach.principal_id,
            trace_id=_trace_id(),
            ent_hash=asked.reach.ent_hash(),
        )
    except CredentialProblemError as refused:
        told = CredentialProblemsView(
            problems=tuple(
                CredentialProblemView(field="key", code=one.code, message=one.message)
                for one in refused.problems
            )
        )
        return JSONResponse(status_code=422, content=told.model_dump(mode="json"))
    except CredentialsUnavailableError as unavailable:
        view = CredentialNotKeptView(
            message=VAULT_TOLD[unavailable.state],
            trace_id=_trace_id(),
            slot=slot.path,
            vault=unavailable.state,
        )
        return JSONResponse(
            status_code=NOT_KEPT_STATUS[unavailable.state], content=view.model_dump(mode="json")
        )
    except BrainError:
        raise
    except Exception as exc:
        # The type name alone, for `brain.credential_routes`' reason: a message can quote a value.
        raise Failed(f"keeping a provider key: {type(exc).__name__}") from exc
    async with factory() as session:
        await session.execute(
            insert(ModelProviderRow).values(
                slug=body.slug,
                kind=ProviderKind.OPENAI_COMPATIBLE.value,
                label=body.label.strip(),
                base_url=body.base_url,
                models=list(body.models),
                updated_by=asked.caller.principal.id,
            )
        )
        await session.commit()
    PROCESS_ADDED_SLOTS.learn(
        (
            *(
                one.slug
                for one in plan.state.providers
                if one.kind is ProviderKind.OPENAI_COMPATIBLE
            ),
            body.slug,
        )
    )
    store.put_to_use(slot, body.key)
    log.info("provider added", provider=body.slug, principal=asked.caller.principal.id)
    return await _view(request, asked, calls)


@router.post(
    "/models/providers/{provider}/retire", response_model=ProvidersView, responses=_REFUSED
)
async def retire_provider(request: Request, provider: str, asked: Asked) -> ProvidersView:
    """Retire a provider added from the console. Its rungs are then left out as unreachable."""
    if not may_switch(asked.reach, asked.now):
        log.info("provider retire refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    calls = models_of(request).calls
    plan = await calls.planned()
    added = {one.slug for one in plan.state.providers if one.kind is ProviderKind.OPENAI_COMPATIBLE}
    if provider not in added:
        log.info("provider retire names no added provider", principal=asked.caller.principal.id)
        raise _not_answerable()
    async with _require(request)() as session:
        await session.execute(
            update(ModelProviderRow)
            .where(ModelProviderRow.slug == provider, ModelProviderRow.deleted_at.is_(None))
            .values(deleted_at=func.statement_timestamp(), updated_by=asked.caller.principal.id)
        )
        await session.commit()
    log.info("provider retired", provider=provider, principal=asked.caller.principal.id)
    return await _view(request, asked, calls)


class RegisterView(BaseModel):
    """The register as one Markdown document, named for saving. Carries no key and no address
    beyond what the register itself states."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str
    document: str
    generated_at: datetime


#: The name the console saves the register under.
REGISTER_FILENAME: Final = "model-provider-register.md"


@router.get(REGISTER_PATH, response_model=RegisterView, responses=COMMON_RESPONSES)
async def register(request: Request, asked: Asked) -> RegisterView:
    """The provider register as one Markdown document the company can show."""
    if not may_read(asked.reach, asked.now):
        log.info("provider register not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    plan = await models_of(request).calls.planned()
    disclosed: dict[str, dict[Any, int]] = {}
    factory = _sessions(request)
    if factory is not None:
        async with factory() as session:
            rows = (await session.execute(disclosures())).all()
        disclosed = dict(disclosure_counts([(str(p), str(c), int(n)) for p, c, n in rows]))
    at = datetime.now(UTC)
    return RegisterView(
        filename=REGISTER_FILENAME,
        document=register_document(
            list(plan.state.providers), disclosed, listed=listed_providers(plan), at=at
        ),
        generated_at=at,
    )
