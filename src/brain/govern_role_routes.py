"""Who holds each role, and the controls that appoint, deputise and remove, over HTTP.

The Roles screen said who holds a role was not recorded, because `role_grant` did not exist. It
does now (`0102`), so this serves the holders and the three writes, each of which decides nothing
itself: whether a holder may be shown is `brain.console.govern.role_holders`; whether a role may be
written or removed is `brain.console.scoped_authority.may_appoint_role`, with `appoint` for a
deputy; what a grant may be is `brain.identity.roles.RoleGrant`; whether an appointment crosses
the separation of duties is `roles.separation_crossed`; and whether a removal breaches the floor
is `roles.revoke_role`. The store asks the last two under the lock about the rows as they stand.

**The separation of duties is a sentence to the person appointing, and an acknowledgement.**
Appointing one person to Super Admin and Connector Admin is refused with
`roles.SEPARATION_OF_DUTIES_WARNING` until the body carries a reason, and the reason is written on
the row, where `0102`'s trigger puts it on the ledger entry (M1.8.7). The warning is said only to a
caller who already holds the authority to make the appointment.

**Every other refusal is one refusal**, the rule `brain.govern_routes` argues for grants.

Task ids: M1.3.2, M1.3.3, M1.3.4, M1.8.7
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.console.govern import Placed, role_holders
from brain.console.reads import permitted
from brain.console.scoped_authority import (
    REACH_AUTHORITY,
    AuthorityError,
    appoint,
    may_appoint_role,
)
from brain.console.screens import screen
from brain.core.department import ScopeRecord
from brain.core.errors import Absent, Failed
from brain.core.scope_sql import PredicateRefusedError
from brain.govern_routes import REASON_CHARS, ROLES_SCREEN, one_live_scope
from brain.identity.role_store import (
    Attribution,
    RoleRecords,
    RoleRefusal,
    StoredRoles,
    role_grant_of,
)
from brain.identity.roles import (
    DEPUTY_MAX,
    SEPARATION_OF_DUTIES_WARNING,
    IdentityError,
    Role,
    RoleGrant,
    revoke_role,
    separation_crossed,
)
from brain.routing_routes import sessions_of
from brain.tables.role_grant import RoleGrantRow

log = structlog.get_logger()

#: How many role grants one Roles answer is loaded from. A role is held by a handful of people.
MAX_HOLDERS: Final = 500

#: What a removal that would breach the floor says, to a caller who could otherwise remove it.
THE_FLOOR_IS_TWO: Final = (
    "removing this would leave fewer than two standing Super Admins; appoint another first"
)


class HolderView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    principal_id: str
    role: str
    scope: dict[str, Any] | None
    deputy_of: str | None
    granted_by: str
    granted_at: datetime
    not_after: datetime | None


class Holders(BaseModel):
    """The role grants this reader may see. No count of anybody left out."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: tuple[HolderView, ...]
    #: Whether this caller may appoint at all. Presentation only.
    editable: bool = False


class Appointment(BaseModel):
    """Appoint one person to one role, with a scope by name when the role needs one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str = Field(min_length=1, max_length=128)
    role: Role
    scope_slug: str | None = Field(default=None, min_length=2, max_length=60)
    reason: str = Field(min_length=1, max_length=REASON_CHARS)
    #: Required only when the appointment crosses the separation of duties.
    acknowledgement: str | None = Field(default=None, min_length=1, max_length=REASON_CHARS)


class DeputyAppointment(BaseModel):
    """Cover a standing grant with a deputy for at most thirty days."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    grant_id: uuid.UUID
    principal_id: str = Field(min_length=1, max_length=128)
    days: int = Field(ge=1, le=DEPUTY_MAX.days)
    reason: str = Field(min_length=1, max_length=REASON_CHARS)


class Removal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    grant_id: uuid.UUID


class RoleChanged(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    change: str
    at: datetime


def _no_role_change_here() -> Absent:
    return Absent("that role change is not writable by this caller")


def _said(message: str) -> Absent:
    return Absent(message, public_message=f"Nothing was changed: {message}")


def _by(asked: Asking) -> Attribution:
    return Attribution(
        actor=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=str(structlog.contextvars.get_contextvars().get("trace_id", "")),
    )


def role_records_of(request: Request) -> RoleRecords:
    """`app.state.role_records` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "role_records", None)
    if isinstance(found, RoleRecords):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredRoles(factory)


def holder_view(row: Any) -> HolderView:
    return HolderView(
        id=str(row.id),
        principal_id=row.principal_id,
        role=row.role,
        scope=row.scope,
        deputy_of=row.deputy_of,
        granted_by=row.granted_by,
        granted_at=row.created_at,
        not_after=row.not_after,
    )


def _authority_asked(asked: Asking) -> None:
    """The cheap half, before any store: a caller holding no grant authority anywhere."""
    if asked.reach.scope_for(REACH_AUTHORITY, asked.now) is None:
        raise _no_role_change_here()


def _refused(outcome: RoleRefusal) -> Absent:
    """The two sentences a caller with the authority may read, and the one refusal otherwise."""
    if outcome is RoleRefusal.UNACKNOWLEDGED:
        return _said(SEPARATION_OF_DUTIES_WARNING)
    if outcome is RoleRefusal.FLOOR:
        return _said(THE_FLOOR_IS_TWO)
    return _no_role_change_here()


def _written(outcome: RoleGrantRow | RoleRefusal, change: str) -> RoleChanged:
    if isinstance(outcome, RoleRefusal):
        raise _refused(outcome)
    return RoleChanged(id=str(outcome.id), change=change, at=outcome.created_at)


router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get("/govern/roles/holders", response_model=Holders, responses=COMMON_RESPONSES)
async def holders(request: Request, asked: Asked) -> Holders:
    """Who holds each role, narrowed by `role_holders` over where each holder sits."""
    if not permitted(screen(ROLES_SCREEN).read, asked.reach, asked.now):
        raise Absent(f"the {ROLES_SCREEN} screen is not answerable for this caller")
    rows = await role_records_of(request).holders(MAX_HOLDERS)
    placed: list[tuple[Any, Placed[RoleGrant]]] = []
    for row, department in rows:
        try:
            record = role_grant_of(row)
        except ValueError:
            log.warning("role grant does not construct", grant=str(row.id))
            continue
        where = {} if department is None else {"department": department}
        placed.append((row, Placed(record=record, where=where)))
    shown = {id(one) for one in role_holders([p for _, p in placed], asked.reach, asked.now)}
    return Holders(
        items=tuple(holder_view(row) for row, one in placed if id(one) in shown),
        editable=asked.reach.scope_for(REACH_AUTHORITY, asked.now) is not None,
    )


async def _scope_named(request: Request, slug: str | None) -> Any:
    if slug is None:
        return None
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        row = (await session.execute(one_live_scope(slug))).scalar_one_or_none()
    if row is None:
        raise _no_role_change_here()
    try:
        return ScopeRecord.from_predicate(
            row.slug, row.predicate, is_department=row.is_department, label=row.label
        ).scope
    except (ValueError, PredicateRefusedError):
        raise _no_role_change_here() from None


@router.post(
    "/govern/roles/appointment",
    response_model=RoleChanged,
    responses=COMMON_RESPONSES,
    status_code=201,
)
async def appoint_role(request: Request, body: Appointment, asked: Asked) -> RoleChanged:
    """Appoint one person to one role, and say the separation of duties when it is crossed."""
    _authority_asked(asked)
    scope = await _scope_named(request, body.scope_slug)
    by = asked.caller.principal.id
    try:
        grant = RoleGrant(
            principal_id=body.principal_id,
            role=body.role,
            scope=scope,
            granted_by=by,
            reason=body.reason,
            granted_at=asked.now,
        )
    except ValueError:
        raise _no_role_change_here() from None
    if not may_appoint_role(grant, asked.reach, by, asked.now):
        raise _no_role_change_here()

    def judge(held: Sequence[RoleGrant]) -> RoleRefusal | None:
        crossing = separation_crossed(
            (one.role for one in held if one.is_active(asked.now)), body.role
        )
        return RoleRefusal.UNACKNOWLEDGED if crossing and body.acknowledgement is None else None

    outcome = await role_records_of(request).appoint(
        grant, acknowledgement=body.acknowledgement, judge=judge, by=_by(asked)
    )
    return _written(outcome, "appointed")


@router.post(
    "/govern/roles/deputy",
    response_model=RoleChanged,
    responses=COMMON_RESPONSES,
    status_code=201,
)
async def appoint_role_deputy(
    request: Request, body: DeputyAppointment, asked: Asked
) -> RoleChanged:
    """Cover a standing grant with a deputy, through `scoped_authority.appoint`."""
    _authority_asked(asked)
    store = role_records_of(request)
    row = await store.one(body.grant_id)
    if row is None:
        raise _no_role_change_here()
    by = asked.caller.principal.id
    try:
        deputy = appoint(
            role_grant_of(row),
            asked.reach,
            body.principal_id,
            granted_by=by,
            reason=body.reason,
            now=asked.now,
            days=body.days,
        )
    except (ValueError, IdentityError, AuthorityError):
        raise _no_role_change_here() from None
    if deputy.principal_id == by:
        raise _no_role_change_here()
    outcome = await store.appoint(deputy, acknowledgement=None, judge=lambda _: None, by=_by(asked))
    return _written(outcome, "deputised")


@router.post("/govern/roles/removal", response_model=RoleChanged, responses=COMMON_RESPONSES)
async def remove_role(request: Request, body: Removal, asked: Asked) -> RoleChanged:
    """Retire one role grant, refusing a removal that breaches the Super Admin floor."""
    _authority_asked(asked)
    by = asked.caller.principal.id

    def judge(target: RoleGrant, every: Sequence[RoleGrant]) -> RoleRefusal | None:
        if not may_appoint_role(target, asked.reach, by, asked.now):
            return RoleRefusal.NOT_WRITABLE
        try:
            revoke_role(every, target, now=asked.now)
        except IdentityError:
            return RoleRefusal.FLOOR
        return None

    outcome = await role_records_of(request).retire(body.grant_id, judge=judge, by=_by(asked))
    if isinstance(outcome, RoleRefusal):
        raise _refused(outcome)
    return RoleChanged(id=str(body.grant_id), change="removed", at=outcome)
