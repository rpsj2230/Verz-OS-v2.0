"""Nominating a person for a role, and the third person who confirms or declines it, over HTTP.

`brain.console.global_surfaces` has had the whole rule since M33.1.2.3 was written: a
`Nomination` nobody can build for themselves, `may_confirm` asking for the grant decision in a
scope admitting the nominee and refusing both people named, and `confirm` building the
`RoleGrant` through that model's own validators with the confirmer as `granted_by`. Nothing
reached any of it. This is the route over it, and `brain.identity.nomination_store` the rows.

**Who may nominate is anybody the Roles screen opens for.** See
`A_NOMINATION_IS_A_PROPOSAL_ANYBODY_ON_THE_ROLES_SCREEN_MAY_MAKE`. A nomination grants nothing,
so asking for the authority that appoints would make it pointless: whoever holds that authority
appoints directly at `/govern/roles/appointment`, and the person a nomination is for is the one
who cannot. Rejected: no gate at all, which would let anybody signed in write proposals into a
queue the governance staff then have to read.

**The confirmation is the grant decision, asked about the nominee's row** (`may_confirm`), and the
appointment's separation-of-duties sentence is said to a confirmer exactly as it is said to an
appointer: only once they have shown the authority to make the grant.

**One refusal for everything else.** A nomination that does not exist, one already decided, one
the reader may not decide and a scope gone since are one answer, `_no_nomination_here`, so the
queue's address answers nothing about what else is in it. The listing is the nominations the
reader may decide and the ones they made, and never a count of anything else.

Task ids: M33.1.2.3
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.attribution import trace_of_request
from brain.console.global_surfaces import GlobalSurfaceError, Nomination, confirm, may_confirm
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Absent, Failed
from brain.core.scope import Scope
from brain.govern_role_routes import _scope_named
from brain.govern_routes import ROLES_SCREEN
from brain.identity.nomination_store import StoredNominations, Verdict
from brain.identity.role_store import Attribution, RoleRefusal
from brain.identity.roles import SEPARATION_OF_DUTIES_WARNING, Role, RoleGrant, separation_crossed
from brain.routing_routes import sessions_of
from brain.tables.role_nomination import REASON_CHARS, SCOPE_SLUG_CHARS, RoleNominationRow

log = structlog.get_logger()

#: Why the Roles screen's read is the whole of what nominating asks.
A_NOMINATION_IS_A_PROPOSAL_ANYBODY_ON_THE_ROLES_SCREEN_MAY_MAKE: Final = (
    "A nomination grants nothing until a third person with the grant decision over the nominee "
    "confirms it, so the authority that appoints is not asked of the person proposing: whoever "
    "holds that authority appoints directly, and a nomination is for the person who cannot. The "
    "Roles screen's read is asked, so the proposals come from people who can see the roles they "
    "are proposing somebody for."
)

#: What a person nominating themselves is told. The refusal is the constructor's
#: (`global_surfaces.A_GATE_ONE_PERSON_PASSES_ALONE_IS_NOT_A_GATE`), in words for the console.
A_PERSON_IS_PROPOSED_BY_SOMEBODY_ELSE: Final = (
    "a person cannot nominate themselves; somebody else proposes them"
)

NOMINATIONS_PATH: Final = "/govern/roles/nominations"
DECISION_PATH: Final = "/govern/roles/nominations/{nomination_id}/decision"


class NominationBody(BaseModel):
    """Propose one person for one role, with a scope by name when the role needs one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str = Field(min_length=1, max_length=128)
    role: Role
    scope_slug: str | None = Field(default=None, min_length=2, max_length=SCOPE_SLUG_CHARS)
    reason: str = Field(min_length=1, max_length=REASON_CHARS)


class Decision(enum.StrEnum):
    CONFIRM = "confirm"
    DECLINE = "decline"


class DecisionBody(BaseModel):
    """Confirm or decline one nomination. An acknowledgement only where a confirmation needs one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Decision
    acknowledgement: str | None = Field(default=None, min_length=1, max_length=REASON_CHARS)


class NominationView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    principal_id: str
    display_name: str | None
    role: str
    scope_slug: str | None
    nominated_by: str
    reason: str
    created_at: datetime
    outcome: str | None
    decided_by: str | None
    decided_at: datetime | None


class NominationsPage(BaseModel):
    """What this reader may decide, and what they proposed. No count of anything else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    deciding: tuple[NominationView, ...]
    mine: tuple[NominationView, ...]


class NominationChanged(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    change: str
    at: datetime


def _no_nomination_here() -> Absent:
    return Absent("that nomination is not answerable for this caller")


def _said(message: str) -> Absent:
    return Absent(message, public_message=f"Nothing was changed: {message}")


def _store(request: Request) -> StoredNominations:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredNominations(factory)


def _by(asked: Asking) -> Attribution:
    return Attribution(
        actor=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
    )


def _screen_asked(asked: Asking) -> None:
    if not permitted(screen(ROLES_SCREEN).read, asked.reach, asked.now):
        raise _no_nomination_here()


def _where(department: str | None) -> dict[str, str]:
    """The row the nominee sits in, as `may_confirm` reads it. Nowhere for somebody unplaced."""
    return {} if department is None else {"department": department}


def nomination_of(row: RoleNominationRow, scope: Scope | None = None) -> Nomination | None:
    """A stored row as the type the rules are written against, or None where it does not build."""
    try:
        return Nomination(
            principal_id=row.principal_id,
            role=Role(row.role),
            nominated_by=row.nominated_by,
            reason=row.reason,
            at=row.created_at,
            scope=scope,
        )
    except (GlobalSurfaceError, ValueError):
        return None


def view_of(row: RoleNominationRow, display_name: str | None) -> NominationView:
    return NominationView(
        id=str(row.id),
        principal_id=row.principal_id,
        display_name=display_name,
        role=row.role,
        scope_slug=row.scope_slug,
        nominated_by=row.nominated_by,
        reason=row.reason,
        created_at=row.created_at,
        outcome=row.outcome,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
    )


router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get(NOMINATIONS_PATH, response_model=NominationsPage, responses=COMMON_RESPONSES)
async def listed_nominations(request: Request, asked: Asked) -> NominationsPage:
    """The undecided nominations this reader may decide, and every one they made (M33.1.2.3)."""
    _screen_asked(asked)
    caller = asked.caller.principal.id
    deciding: list[NominationView] = []
    mine: list[NominationView] = []
    for row, department, name in await _store(request).listed():
        if row.nominated_by == caller:
            mine.append(view_of(row, name))
            continue
        nomination = nomination_of(row)
        if (
            row.outcome is None
            and nomination is not None
            and may_confirm(nomination, asked.reach, _where(department), asked.now)
        ):
            deciding.append(view_of(row, name))
    return NominationsPage(deciding=tuple(deciding), mine=tuple(mine))


@router.post(
    NOMINATIONS_PATH,
    response_model=NominationChanged,
    responses=COMMON_RESPONSES,
    status_code=201,
)
async def nominate(request: Request, body: NominationBody, asked: Asked) -> NominationChanged:
    """Propose one person for one role. See `A_NOMINATION_IS_A_PROPOSAL_ANYBODY_ON_THE_..._MAKE`."""
    _screen_asked(asked)
    await _scope_named(request, body.scope_slug)
    if body.principal_id == asked.caller.principal.id:
        # The constructor refuses this too; asked first so the person it is about is told why,
        # which tells them nothing about anybody else.
        raise _said(A_PERSON_IS_PROPOSED_BY_SOMEBODY_ELSE)
    try:
        proposal = Nomination(
            principal_id=body.principal_id,
            role=body.role,
            nominated_by=asked.caller.principal.id,
            reason=body.reason,
            at=asked.now,
        )
    except GlobalSurfaceError:
        raise _no_nomination_here() from None
    stored = await _store(request).nominate(
        principal_id=proposal.principal_id,
        role=proposal.role.value,
        scope_slug=body.scope_slug,
        reason=proposal.reason,
        by=_by(asked),
    )
    if stored is None:
        raise _no_nomination_here()
    return NominationChanged(id=str(stored.id), change="nominated", at=stored.created_at)


@router.post(DECISION_PATH, response_model=NominationChanged, responses=COMMON_RESPONSES)
async def decide_nomination(
    request: Request,
    body: DecisionBody,
    asked: Asked,
    nomination_id: Annotated[uuid.UUID, Path()],
) -> NominationChanged:
    """Confirm a nomination into its role grant, or decline it, as a third person (M33.1.2.3)."""
    _screen_asked(asked)
    store = _store(request)
    by = _by(asked)
    if body.decision is Decision.DECLINE:

        def may_decline(row: RoleNominationRow, department: str | None) -> bool:
            nomination = nomination_of(row)
            return nomination is not None and may_confirm(
                nomination, asked.reach, _where(department), asked.now
            )

        declined = await store.decline(nomination_id, judge=may_decline, by=by)
        if isinstance(declined, RoleRefusal) or declined.decided_at is None:
            raise _no_nomination_here()
        return NominationChanged(id=str(declined.id), change="declined", at=declined.decided_at)

    found = await store.one(nomination_id)
    if found is None:
        raise _no_nomination_here()
    scope = await _scope_named(request, found.scope_slug)

    def judge(row: RoleNominationRow, department: str | None, held: Sequence[RoleGrant]) -> Verdict:
        nomination = nomination_of(row, scope)
        if nomination is None or row.scope_slug != found.scope_slug:
            return RoleRefusal.NOT_WRITABLE
        try:
            grant = confirm(
                nomination, asked.reach, where=_where(department), at=asked.now, now=asked.now
            )
        except (GlobalSurfaceError, ValueError):
            return RoleRefusal.NOT_WRITABLE
        crossing = separation_crossed(
            (one.role for one in held if one.is_active(asked.now)), grant.role
        )
        if crossing and body.acknowledgement is None:
            return RoleRefusal.UNACKNOWLEDGED
        return grant, body.acknowledgement

    confirmed = await store.confirm(nomination_id, judge=judge, by=by)
    if confirmed is RoleRefusal.UNACKNOWLEDGED:
        raise _said(SEPARATION_OF_DUTIES_WARNING)
    if isinstance(confirmed, RoleRefusal) or confirmed.decided_at is None:
        raise _no_nomination_here()
    return NominationChanged(id=str(confirmed.id), change="confirmed", at=confirmed.decided_at)
