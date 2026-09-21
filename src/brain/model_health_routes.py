"""The two routing settings the Models and health screen edits: a tier's numbers, and residency.

`brain.provider_routes` shows the tiers and the residency constraints the router reads; this is
where an administrator changes them. Both are the router's configuration rather than a company's
data, and both take effect on the next call in every process, because the executor reads them in
the same read as the ladder (`brain.ops.model_service.SessionLadder`).

**Held to the matrix's write capability over everything**, exactly as a provider switch is:
`brain.provider_routes.may_switch`. A tier's window decides which pool every department's
questions go to, and a residency constraint decides which regions may process them, so a grant
scoped to one department is not a grant here. The capability is asked before the body is looked
at and before the database is, which is `brain.routing_routes`' order and its argument.

**A tier row is checked by the router's own rule before it is written** (`brain.models.tier_rules.
TierRule`): a window from one token to ten million and a headroom from a tenth to the whole
window, and `none`, which uses no model, is refused. Reset retires the row, and the tier runs at
the product's compiled numbers again, which the screen says. The rule set written holds only the
keys the router reads, so a row this route wrote can never be one the router leaves out.

**A residency constraint is checked by `brain.models.residency.requirement_of` and `Scope` before
it is written.** Refused: a constraint that demands nothing, an empty region list and `global`,
each for the reason that function gives. It is retired, never deleted, so the constraint in force
when a question was refused can still be read. Retiring one widens where questions may go, which
is why it takes the same capability as adding one and is confirmed on the screen like a switch.

Every answer is the providers view read after the write, so the person sees the table or the
constraint list the next call will use.

Task ids: M5.2.2, M5.5.1
"""

from __future__ import annotations

import uuid
from typing import Any, Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, insert, select, update

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import attribute
from brain.core.errors import Failed
from brain.core.scope import Scope
from brain.credential_routes import CredentialProblemsView, CredentialProblemView
from brain.models.residency import ResidencyError, requirement_of
from brain.models.routing import TIER_LADDER, Tier
from brain.models.tier_rules import TierRule, TierRuleError
from brain.provider_routes import (
    ProvidersView,
    _not_answerable,
    _sessions,
    _view,
    may_switch,
    models_of,
)
from brain.tables.model_health import NOTE_CHARS, ResidencyConstraintRow
from brain.tables.routing import RoutingTierRow

log = structlog.get_logger()

#: Why a tier's numbers and a residency constraint take the switch's capability.
ROUTING_SETTINGS_ARE_SET_BY_SOMEBODY_WHO_GOVERNS_EVERY_QUESTION: Final = (
    "A tier's window decides which pool every department's questions go to, and a residency "
    "constraint decides where they may be processed. Either set by a grant scoped to one "
    "department would let its holder decide for all of them, so both take admin:routing_matrix "
    "held over everything, as a provider switch does."
)


class TierRuleAsked(BaseModel):
    """A tier's window, and its escalation headroom or null for the product default."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    context_window: int
    escalation_headroom: float | None = None


class ResidencyAsked(BaseModel):
    """A residency constraint: the scope, and the regions or on-prem it demands."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: `Scope.model_dump()`: `{"clauses": [{"field", "op", "value"}]}`. An empty list is every row.
    scope: dict[str, Any]
    allowed_regions: list[str] | None = None
    on_prem_only: bool = False
    note: str = Field(default="", max_length=NOTE_CHARS)


def _problem(field: str, message: str) -> JSONResponse:
    """A 422 naming the field and saying what is wrong, never repeating what was sent."""
    told = CredentialProblemsView(
        problems=(CredentialProblemView(field=field, code="refused", message=message),)
    )
    return JSONResponse(status_code=422, content=told.model_dump(mode="json"))


def _ladder_tier(tier: str) -> Tier | None:
    """A tier the ladder has, or None; `none` uses no model and takes no numbers."""
    try:
        found = Tier(tier)
    except ValueError:
        return None
    return found if found in TIER_LADDER else None


#: The tier that is not one a model serves, in the words a 422 says it.
NOT_A_MODEL_TIER: Final = "that is not a tier with a model: small, main or heavy"

_REFUSED: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    422: {"model": CredentialProblemsView, "description": "What is wrong with what was sent."},
}

router = APIRouter(prefix=API_PREFIX, tags=["models"])


@router.put("/models/tiers/{tier}", response_model=ProvidersView, responses=_REFUSED)
async def set_tier(
    request: Request, tier: str, body: TierRuleAsked, asked: Asked
) -> JSONResponse | ProvidersView:
    """Set one tier's window and headroom; the next call is classified against them."""
    if not may_switch(asked.reach, asked.now):
        log.info("tier rule refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    named = _ladder_tier(tier)
    if named is None:
        return _problem("tier", NOT_A_MODEL_TIER)
    try:
        rule = TierRule(
            tier=named, context_window=body.context_window, headroom=body.escalation_headroom
        )
    except TierRuleError as exc:
        return _problem("context_window", str(exc))
    factory = _sessions(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        await attribute(session, asked)
        live = (
            await session.execute(
                select(RoutingTierRow.id).where(
                    RoutingTierRow.tier == named.value, RoutingTierRow.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if live is None:
            await session.execute(
                insert(RoutingTierRow).values(
                    tier=named.value, context_window=rule.context_window, rules=rule.rules()
                )
            )
        else:
            await session.execute(
                update(RoutingTierRow)
                .where(RoutingTierRow.id == live)
                .values(context_window=rule.context_window, rules=rule.rules())
            )
        await session.commit()
    log.info("tier rule set", tier=named.value, principal=asked.caller.principal.id)
    return await _view(request, asked, models_of(request).calls)


@router.post("/models/tiers/{tier}/reset", response_model=ProvidersView, responses=_REFUSED)
async def reset_tier(request: Request, tier: str, asked: Asked) -> JSONResponse | ProvidersView:
    """Retire one tier's row, so it runs at the product's compiled numbers again."""
    if not may_switch(asked.reach, asked.now):
        log.info("tier reset refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    named = _ladder_tier(tier)
    if named is None:
        return _problem("tier", NOT_A_MODEL_TIER)
    factory = _sessions(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        await attribute(session, asked)
        await session.execute(
            update(RoutingTierRow)
            .where(RoutingTierRow.tier == named.value, RoutingTierRow.deleted_at.is_(None))
            .values(deleted_at=func.statement_timestamp())
        )
        await session.commit()
    log.info("tier rule reset", tier=named.value, principal=asked.caller.principal.id)
    return await _view(request, asked, models_of(request).calls)


@router.post("/models/residency", response_model=ProvidersView, responses=_REFUSED)
async def add_residency(
    request: Request, body: ResidencyAsked, asked: Asked
) -> JSONResponse | ProvidersView:
    """Attach a residency constraint to a scope; the next call whose reach touches it honours it."""
    if not may_switch(asked.reach, asked.now):
        log.info("residency constraint refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    try:
        scope = Scope.model_validate(body.scope)
    except ValidationError:
        return _problem("scope", "the scope is not one a grant could hold")
    try:
        requirement_of(body.allowed_regions, on_prem_only=body.on_prem_only)
    except ResidencyError as exc:
        return _problem("allowed_regions", str(exc))
    factory = _sessions(request)
    if factory is None:
        raise Failed("no database on this process")
    regions = None if body.allowed_regions is None else [r.strip() for r in body.allowed_regions]
    async with factory() as session:
        await attribute(session, asked)
        await session.execute(
            insert(ResidencyConstraintRow).values(
                scope=scope.model_dump(mode="json"),
                allowed_regions=regions,
                on_prem_only=body.on_prem_only,
                note=body.note.strip(),
                created_by=asked.caller.principal.id,
            )
        )
        await session.commit()
    log.info("residency constraint added", principal=asked.caller.principal.id)
    return await _view(request, asked, models_of(request).calls)


@router.post(
    "/models/residency/{constraint_id}/retire",
    response_model=ProvidersView,
    responses=COMMON_RESPONSES,
)
async def retire_residency(
    request: Request, constraint_id: uuid.UUID, asked: Asked
) -> ProvidersView:
    """Retire one residency constraint. Questions it held back may go where it forbade."""
    if not may_switch(asked.reach, asked.now):
        log.info("residency retirement refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    factory = _sessions(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        await attribute(session, asked)
        await session.execute(
            update(ResidencyConstraintRow)
            .where(
                ResidencyConstraintRow.id == constraint_id,
                ResidencyConstraintRow.deleted_at.is_(None),
            )
            .values(deleted_at=func.statement_timestamp())
        )
        await session.commit()
    log.info("residency constraint retired", principal=asked.caller.principal.id)
    return await _view(request, asked, models_of(request).calls)
