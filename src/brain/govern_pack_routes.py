"""Capability packs and the Approver misconfiguration flag, over HTTP.

Two things the Govern screens could not do before this module. A pack could be read but never
assigned: nothing in the application inserted `gate.capability_pack_assignment`, so a scope-bound
pack assignment (M1.4.3) could not be made on an install, and its audit entry (M1.4.8, written by
`0003`'s trigger on that table) could never appear. And the Approver role and the approve
permission could disagree in both directions with nothing saying so (M1.8.4).

**Nothing here decides.** An assignment is `brain.identity.packs.expand`ed and every grant it means
goes through `brain.console.scoped_authority.write_grant`, so a pack cannot carry a capability, a
scope or a lapse the assigner could not have granted one at a time. Removal is the Access review's
decision (`POST /govern/access-review/decision`), which already retires an assignment and whose
`revoke` entry the same trigger writes. The flag is
`brain.console.govern.approver_misconfigurations`.

**Role holders come from the directory today.** `auth.directory_role_grant` is the only record of a
held role: the hand-made `role_grant` table (M1.3.2) needs a migration and is not built. The flag
therefore judges directory-asserted Approvers; the day the other table lands it is one more load.

Task ids: M1.4.3, M1.4.8, M1.8.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Insert, Select, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import attribute
from brain.console.govern import (
    VOCABULARY_SCREEN,
    Placed,
    approver_misconfigurations,
)
from brain.console.reads import permitted
from brain.console.scoped_authority import REACH_AUTHORITY, AuthorityError, write_grant
from brain.console.screens import screen
from brain.core.department import SLUG_PATTERN, ScopeRecord
from brain.core.entitlement import Capability
from brain.core.errors import Absent, Failed
from brain.core.scope_sql import PredicateRefusedError
from brain.govern_routes import (
    MAX_PEOPLE_PER_PAGE,
    PACK_LABEL_CHARS,
    PEOPLE_SCREEN,
    REASON_CHARS,
    ROLES_SCREEN,
    live_assignments,
    live_grants,
    one_live_scope,
    placed_assignment,
    placed_grant,
)
from brain.identity.packs import CapabilityPack, PackAssignment, SubjectGrant, expand
from brain.identity.roles import Role, RoleMismatch, RoleMismatchKind
from brain.identity.teams import PrincipalSubject
from brain.routing_routes import sessions_of
from brain.tables.gate import CapabilityPackAssignmentRow, CapabilityPackRow
from brain.tables.identity import DirectoryRoleGrantRow, PrincipalRow

log = structlog.get_logger()

#: How many packs one catalogue answer is loaded from. A pack is written by a person, so an
#: install with more than this has a different problem from a paging one.
MAX_PACKS: Final = 200

#: What each mismatch says, in words the Roles screen shows beside the person.
MISMATCH_SENTENCES: Final[dict[RoleMismatchKind, str]] = {
    RoleMismatchKind.ROLE_WITHOUT_CAPABILITY: (
        "Holds the Approver role and no approve permission, so they cannot approve anything."
    ),
    RoleMismatchKind.CAPABILITY_WITHOUT_ROLE: (
        "Holds an approve permission without the Approver role, so they can approve and are "
        "not listed as an approver."
    ),
}


# ------------------------------------------------------------------- the shapes


class PackView(BaseModel):
    """One live pack: its slug, what it is for, and the capabilities it bundles."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    label: str
    capabilities: tuple[str, ...]


class PackCatalogue(BaseModel):
    """Every live pack, or none for a reader who may not name capabilities."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    packs: tuple[PackView, ...]


class PackProposal(BaseModel):
    """Assign one pack to one person over one named scope. No predicate, no granter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str = Field(min_length=1, max_length=128)
    pack_slug: str = Field(min_length=2, max_length=60, pattern=SLUG_PATTERN)
    scope_slug: str = Field(min_length=2, max_length=60)
    reason: str = Field(min_length=1, max_length=REASON_CHARS)
    not_after: datetime | None = None


class PackAssigned(BaseModel):
    """The assignment as the database now holds it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    principal_id: str
    pack_slug: str
    scope_slug: str
    granted_at: datetime
    not_after: datetime | None


class MisconfigurationView(BaseModel):
    """One person whose Approver role and approve permission disagree."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    kind: str
    sentence: str


class Misconfigurations(BaseModel):
    """Every mismatch this reader may see, judged whole. No count of anything withheld."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: tuple[MisconfigurationView, ...]


# ---------------------------------------------------------------- the statements


def live_packs(limit: int) -> Select[tuple[CapabilityPackRow]]:
    """Every live pack, in name order."""
    return (
        select(CapabilityPackRow)
        .where(CapabilityPackRow.deleted_at.is_(None))
        .order_by(CapabilityPackRow.name)
        .limit(limit)
    )


def one_live_pack(slug: str) -> Select[tuple[CapabilityPackRow]]:
    """The live pack with this name, or nothing."""
    return (
        select(CapabilityPackRow)
        .where(CapabilityPackRow.name == slug, CapabilityPackRow.deleted_at.is_(None))
        .limit(1)
    )


def add_assignment(
    assignment: PackAssignment, principal_id: str, pack: CapabilityPackRow
) -> Insert:
    """The INSERT for one assignment. The instant is the database's `created_at`."""
    return (
        insert(CapabilityPackAssignmentRow)
        .values(
            principal_id=principal_id,
            pack_id=pack.id,
            scope=assignment.scope.model_dump(),
            granted_by=assignment.granted_by,
            reason=assignment.reason,
            not_after=assignment.not_after,
        )
        .returning(CapabilityPackAssignmentRow)
    )


def approver_holders(limit: int) -> Select[tuple[str, str | None]]:
    """Who the directory says holds the Approver role, and the department each sits in."""
    return (
        select(DirectoryRoleGrantRow.principal_id, PrincipalRow.primary_department)
        .join(
            PrincipalRow,
            (PrincipalRow.id == DirectoryRoleGrantRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
        )
        .where(DirectoryRoleGrantRow.role == Role.APPROVER.value)
        .distinct()
        .order_by(DirectoryRoleGrantRow.principal_id)
        .limit(limit)
    )


def pack_of(row: CapabilityPackRow) -> CapabilityPack:
    """A stored pack as the type `expand` takes. `name` is the slug, `description` the label."""
    return CapabilityPack(
        slug=row.name,
        label=row.description[:PACK_LABEL_CHARS],
        capabilities=tuple(Capability(value=one) for one in row.capabilities),
    )


def _no_assignment_here() -> Absent:
    """One refusal for every way an assignment can fail, as `_no_grant_here` is for a grant."""
    return Absent("that pack assignment is not writable by this caller")


# -------------------------------------------------------------------- the routes

router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get("/govern/packs", response_model=PackCatalogue, responses=COMMON_RESPONSES)
async def packs(request: Request, asked: Asked) -> PackCatalogue:
    """Every live pack and what it bundles, under the vocabulary's grant.

    A pack's contents are capability names, so the Capabilities screen's read decides, asked
    before the database for the ordering every govern route keeps.
    """
    if not permitted(screen(VOCABULARY_SCREEN).read, asked.reach, asked.now):
        return PackCatalogue(packs=())
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        rows = (await session.execute(live_packs(MAX_PACKS))).scalars().all()
    shown: list[PackView] = []
    for row in rows:
        try:
            pack = pack_of(row)
        except ValueError:
            log.warning("pack row does not construct", pack=row.name)
            continue
        shown.append(
            PackView(
                slug=pack.slug,
                label=pack.label,
                capabilities=tuple(one.value for one in pack.capabilities),
            )
        )
    return PackCatalogue(packs=tuple(shown))


@router.post(
    "/govern/packs/assignment",
    response_model=PackAssigned,
    responses=COMMON_RESPONSES,
    status_code=201,
)
async def assign_pack(request: Request, body: PackProposal, asked: Asked) -> PackAssigned:
    """Assign one pack to one person over a named scope, only if every grant it means is ours.

    The authority is asked before the database. Then the scope and the pack are loaded by name,
    the assignment is built (which refuses an unrestricted scope), expanded, and every grant it
    expands to must pass `write_grant`: one capability the assigner lacks refuses the lot, since
    a pack is where that capability hides in the middle of a list nobody reads.
    """
    if asked.reach.scope_for(REACH_AUTHORITY, asked.now) is None:
        log.info("pack not assignable", principal=asked.caller.principal.id)
        raise _no_assignment_here()

    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        scope_row = (await session.execute(one_live_scope(body.scope_slug))).scalar_one_or_none()
        pack_row = (await session.execute(one_live_pack(body.pack_slug))).scalar_one_or_none()
        if scope_row is None or pack_row is None:
            await session.rollback()
            log.info("pack assignment names nothing live", principal=asked.caller.principal.id)
            raise _no_assignment_here()
        try:
            record = ScopeRecord.from_predicate(
                scope_row.slug,
                scope_row.predicate,
                is_department=scope_row.is_department,
                label=scope_row.label,
            )
            assignment = PackAssignment(
                subject=PrincipalSubject(principal_id=body.principal_id),
                pack_slug=pack_row.name,
                scope=record.scope,
                granted_by=asked.caller.principal.id,
                reason=body.reason,
                granted_at=asked.now,
                not_after=body.not_after,
            )
            for one in expand(pack_of(pack_row), assignment):
                write_grant(one, asked.reach, asked.now)
        except (ValueError, PredicateRefusedError, AuthorityError):
            await session.rollback()
            log.info("pack assignment refused", principal=asked.caller.principal.id)
            raise _no_assignment_here() from None

        stored = await _write(session, assignment, body.principal_id, pack_row, asked)
        await session.commit()
        return PackAssigned(
            id=str(stored.id),
            principal_id=stored.principal_id,
            pack_slug=pack_row.name,
            scope_slug=record.slug,
            granted_at=stored.created_at,
            not_after=stored.not_after,
        )


async def _write(
    session: AsyncSession,
    assignment: PackAssignment,
    principal_id: str,
    pack: CapabilityPackRow,
    asked: Asked,
) -> CapabilityPackAssignmentRow:
    """The insert, attributed to the caller so `0003`'s trigger records who assigned it, at what
    reach and in which request: `brain.attribution.attribute` (M24.3.1)."""
    await attribute(session, asked)
    try:
        stored: CapabilityPackAssignmentRow | None = (
            await session.execute(add_assignment(assignment, principal_id, pack))
        ).scalar_one_or_none()
    except IntegrityError:
        # An unknown person or a pack they already hold: facts about somebody else.
        await session.rollback()
        log.info("pack assignment refused by a constraint", principal=asked.caller.principal.id)
        raise _no_assignment_here() from None
    if stored is None:
        await session.rollback()
        raise _no_assignment_here()
    return stored


@router.get(
    "/govern/roles/misconfigurations",
    response_model=Misconfigurations,
    responses=COMMON_RESPONSES,
)
async def misconfigurations(request: Request, asked: Asked) -> Misconfigurations:
    """Who holds the Approver role without an approve permission, or the reverse (M1.8.4).

    Opens for a reader of both the Roles and the People screens, asked before the database;
    which rows appear is `approver_misconfigurations`, over what this reader may already see.
    """
    if not (
        permitted(screen(ROLES_SCREEN).read, asked.reach, asked.now)
        and permitted(screen(PEOPLE_SCREEN).read, asked.reach, asked.now)
    ):
        log.info("role misconfigurations not answerable", principal=asked.caller.principal.id)
        raise Absent(f"the {ROLES_SCREEN} screen is not answerable for this caller")

    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        grants = (await session.execute(live_grants(MAX_PEOPLE_PER_PAGE + 1))).all()
        assignments = (await session.execute(live_assignments(MAX_PEOPLE_PER_PAGE + 1))).all()
        holders = (await session.execute(approver_holders(MAX_PEOPLE_PER_PAGE))).all()

    if len(grants) > MAX_PEOPLE_PER_PAGE or len(assignments) > MAX_PEOPLE_PER_PAGE:
        # Judged whole or not at all: a flag over part of the grants reads as "nobody else".
        raise Failed("the grant tables are larger than the Approver flag can judge whole")
    holdings: list[Placed[SubjectGrant]] = []
    for row, department in grants:
        try:
            holdings.append(placed_grant(row, department))
        except ValueError:
            log.warning("grant row does not construct", grant=str(row.id))
    for assigned, pack, department in assignments:
        try:
            holdings.extend(placed_assignment(assigned, pack, department))
        except ValueError:
            log.warning("pack assignment does not construct", assignment=str(assigned.id))
    role = [
        Placed(record=pid, where={} if department is None else {"department": department})
        for pid, department in holders
    ]
    found: tuple[RoleMismatch, ...] = approver_misconfigurations(
        holdings, role, asked.reach, asked.now
    )
    return Misconfigurations(
        items=tuple(
            MisconfigurationView(
                principal_id=one.principal_id,
                kind=one.kind.value,
                sentence=MISMATCH_SENTENCES[one.kind],
            )
            for one in found
        )
    )
