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

**Role holders are the directory's and the appointments'.** `auth.directory_role_grant` records
what a directory asserts and `gate.role_grant` (`0102`) what a person granted; an Approver in
either counts, and an appointment that has lapsed does not.

**A pack is created, versioned, copied and retired here, each write confirmed and audited**
(M27.15.24). Every write asks `brain.console.scoped_authority.may_write_packs` before the database,
which is `approve:grant` held over everything, because a pack is the whole company's; and a
creation, a versioning and a copy ask `may_bundle` of the pack that results, which is every
capability in it held over everything, because nobody bundles what they could not grant alone. A
versioning asks it of the pack before the change as well, because taking a capability out of a
pack takes it from every holder. See `NOBODY_BUNDLES_WHAT_THEY_COULD_NOT_GRANT_ALONE`. Each
capability must be a live row of `gate.capability_registry`, because the registry is the statement
that a capability was meant to exist and a pack carrying a typo would be granted to everybody who
holds it. `0141`'s trigger writes the `pack` entry, attributed to the writer by
`brain.attribution.attribute`.

**A version is the same row moved in place.** See `A_VERSION_IS_THE_SAME_PACK_MOVED_IN_PLACE`: the
holders move with it, and `0003`'s `capability_pack_bumps_versions` tells each holder's cached
reach. The version the page showed is part of every change to a live pack, so a versioning or a
retirement confirmed against one state cannot land on another.

**Only a pack nobody holds is retired**, because the resolver drops an assignment to a retired pack,
so retiring a held one would take access away from its holders with no decision about any of them.
The refusal says so and names nobody and no figure. See `A_PACK_SOMEBODY_HOLDS_IS_NOT_RETIRED`.

**Every refusal is one refusal except the four a pack writer may read**: a taken short name and a
state that moved since the page was opened, said to anybody holding the pack authority because they
govern every pack there is; a pack somebody still holds, said to the same; and a capability the
registry does not hold, said only to a writer who may also name capabilities, because what the
registry holds is the vocabulary.

Task ids: M1.4.3, M1.4.8, M1.8.4, M27.15.24
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Final, Literal, Self

import structlog
from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import Insert, Select, Update, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import attribute
from brain.console.govern import (
    VOCABULARY_SCREEN,
    Placed,
    approver_misconfigurations,
    may_name_capabilities,
)
from brain.console.reads import permitted
from brain.console.scoped_authority import (
    REACH_AUTHORITY,
    AuthorityError,
    may_bundle,
    may_write_packs,
    write_grant,
)
from brain.console.screens import screen
from brain.core.department import SLUG_PATTERN, ScopeRecord
from brain.core.entitlement import CAPABILITY_RE, Capability
from brain.core.errors import Absent, Failed
from brain.core.scope_sql import PredicateRefusedError
from brain.govern_people_routes import IT_CHANGED_SINCE_YOU_OPENED_IT
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
from brain.tables.gate import (
    CAPABILITY_CHARS,
    CapabilityPackAssignmentRow,
    CapabilityPackRow,
    CapabilityRegistryRow,
)
from brain.tables.identity import DirectoryRoleGrantRow, PrincipalRow
from brain.tables.role_grant import RoleGrantRow

log = structlog.get_logger()

#: How many packs one catalogue answer is loaded from. A pack is written by a person, so an
#: install with more than this has a different problem from a paging one.
MAX_PACKS: Final = 200

#: The most capabilities one pack may carry. A bound on a form, not a permission.
MOST_CAPABILITIES_IN_A_PACK: Final = 100

#: Why a new version of a pack is the same row updated rather than a row of its own.
A_VERSION_IS_THE_SAME_PACK_MOVED_IN_PLACE: Final = (
    "A version is an update of the pack's one row: its capabilities or its label move, its version "
    "goes up by one, and every assignment to it now means the new bundle, because an assignment "
    "names the pack and not a state of it. Nothing is granted again person by person, and every "
    "holder's cached reach is told by the trigger that already tells it about a pack changing. "
    "Rejected: a new row per version, retiring the old. The resolver drops an assignment to a "
    "retired pack, so every existing assignment would be stranded on the old row and its holder "
    "would silently lose the whole pack the moment somebody improved it."
)

#: What a new version does, served on the Packs screen for its confirmation.
A_NEW_VERSION_CHANGES_WHAT_EVERY_HOLDER_HOLDS: Final = (
    "A new version changes what every holder of the pack holds, at once: a capability added is "
    "held by all of them from their next request, and one taken out is held by none of them."
)

#: What retiring waits for, served for its confirmation and said as its refusal.
A_PACK_SOMEBODY_HOLDS_IS_NOT_RETIRED: Final = (
    "A pack somebody still holds is not retired, because retiring it would take its capabilities "
    "away from every holder without anybody deciding that; remove each assignment first, on a "
    "person's page or in an access review"
)

#: The readable refusal of a short name another live pack has.
A_PACK_NAME_IS_TAKEN: Final = (
    "that short name is already used by a live pack, so choose another; a retired pack's short "
    "name can be used again"
)

#: The readable refusal of a capability the registry does not hold. `{capability}` is what the
#: writer typed, so it is their own submission read back.
NOT_A_REGISTERED_CAPABILITY: Final = (
    "{capability} is not a registered capability on this install, so no pack can carry it"
)

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
    """One live pack: its slug, what it is for, the capabilities it bundles, and its version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    label: str
    capabilities: tuple[str, ...]
    #: Which state of the pack this is, from one. A versioning and a retirement name it back.
    version: int


class PackCatalogue(BaseModel):
    """Every live pack, or none for a reader who may not name capabilities."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    packs: tuple[PackView, ...]
    #: Whether this reader holds the pack authority. Presentation only: every write asks again,
    #: and asks `may_bundle` of the pack itself.
    may_write: bool = False
    versioning: str = A_NEW_VERSION_CHANGES_WHAT_EVERY_HOLDER_HOLDS
    retiring: str = f"{A_PACK_SOMEBODY_HOLDS_IS_NOT_RETIRED}."


#: A pack's short name, as `CapabilityPack.slug` and `gate.capability_pack.name` both accept.
PackSlug = Annotated[str, Field(min_length=2, max_length=60, pattern=SLUG_PATTERN)]

#: What a pack is for, as a person reads it, trimmed, as the table's `described` check requires.
PackLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=PACK_LABEL_CHARS)
]

#: One capability a pack carries, checked against the grammar so a malformed one is a 422.
CapabilityName = Annotated[str, Field(pattern=CAPABILITY_RE.pattern, max_length=CAPABILITY_CHARS)]


def _each_once(capabilities: Sequence[str]) -> None:
    # A shape fault, so a 422 is honest, and it names nothing but what the writer typed.
    if len(set(capabilities)) != len(capabilities):
        msg = "a pack names each capability once"
        raise ValueError(msg)


class PackWriting(BaseModel):
    """A new pack: its short name, what it is for, and what it carries. Nothing else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: PackSlug
    label: PackLabel
    capabilities: list[CapabilityName] = Field(min_length=1, max_length=MOST_CAPABILITIES_IN_A_PACK)

    @model_validator(mode="after")
    def _once(self) -> Self:
        _each_once(self.capabilities)
        return self


class PackVersioning(BaseModel):
    """A pack's next version: the version the page showed, and what it is to be now."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: PackSlug
    expected_version: int = Field(ge=1)
    label: PackLabel
    capabilities: list[CapabilityName] = Field(min_length=1, max_length=MOST_CAPABILITIES_IN_A_PACK)

    @model_validator(mode="after")
    def _once(self) -> Self:
        _each_once(self.capabilities)
        return self


class PackCopying(BaseModel):
    """A new pack carrying what an existing one carries, under a short name of its own."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: PackSlug
    new_slug: PackSlug
    label: PackLabel

    @model_validator(mode="after")
    def _somewhere_new(self) -> Self:
        if self.new_slug == self.slug:
            msg = "a copy has a short name of its own"
            raise ValueError(msg)
        return self


class PackRetirement(BaseModel):
    """Which pack, and the version the confirmation showed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: PackSlug
    expected_version: int = Field(ge=1)


class PackChanged(BaseModel):
    """What a write to a pack did, in the word the writer pressed, and the database's instant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slug: str
    version: int
    change: Literal["created", "versioned", "copied", "retired"]
    at: datetime


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


def pack_locked(slug: str) -> Select[tuple[CapabilityPackRow]]:
    """The live pack with this name, locked for a change, or nothing."""
    return one_live_pack(slug).with_for_update()


def registered(capabilities: Sequence[str]) -> Select[tuple[str]]:
    """Which of these capabilities are live rows of `gate.capability_registry`."""
    return select(CapabilityRegistryRow.capability).where(
        CapabilityRegistryRow.capability.in_(list(capabilities)),
        CapabilityRegistryRow.deleted_at.is_(None),
    )


def held_by_somebody(pack: CapabilityPackRow) -> Select[tuple[uuid.UUID]]:
    """One live, unlapsed assignment of this pack, or nothing. Never who, never how many."""
    return (
        select(CapabilityPackAssignmentRow.id)
        .where(
            CapabilityPackAssignmentRow.pack_id == pack.id,
            CapabilityPackAssignmentRow.deleted_at.is_(None),
            or_(
                CapabilityPackAssignmentRow.not_after.is_(None),
                CapabilityPackAssignmentRow.not_after > func.statement_timestamp(),
            ),
        )
        .limit(1)
    )


def creating_pack(slug: str, label: str, capabilities: Sequence[str]) -> Insert:
    """The INSERT for one pack at version one. The label is the table's `description`."""
    return (
        insert(CapabilityPackRow)
        .values(name=slug, description=label, capabilities=list(capabilities))
        .returning(CapabilityPackRow.version, CapabilityPackRow.created_at)
    )


def versioning_pack(
    pack: CapabilityPackRow, expected: int, label: str, capabilities: Sequence[str]
) -> Update:
    """The UPDATE that moves one live pack to its next version, if it is still at `expected`.

    See `A_VERSION_IS_THE_SAME_PACK_MOVED_IN_PLACE`. The version in the WHERE clause as well as in
    the read before it, so two versionings from one page cannot both land.
    """
    return (
        update(CapabilityPackRow)
        .where(
            CapabilityPackRow.id == pack.id,
            CapabilityPackRow.version == expected,
            CapabilityPackRow.deleted_at.is_(None),
        )
        .values(
            description=label,
            capabilities=list(capabilities),
            version=CapabilityPackRow.version + 1,
        )
        .returning(CapabilityPackRow.version, CapabilityPackRow.updated_at)
    )


def retiring_pack(pack: CapabilityPackRow, expected: int) -> Update:
    """The UPDATE that retires one live pack at `expected`, stamped by its own statement.

    `statement_timestamp()` for `brain.identity.sign_in_binding.A_RETIREMENT_IS_STAMPED_BY_ITS_OWN_
    STATEMENT`'s reason: `0045`'s policy admits a retired row only at the retiring statement's own
    instant.
    """
    return (
        update(CapabilityPackRow)
        .where(
            CapabilityPackRow.id == pack.id,
            CapabilityPackRow.version == expected,
            CapabilityPackRow.deleted_at.is_(None),
        )
        .values(deleted_at=func.statement_timestamp())
        .returning(CapabilityPackRow.version, CapabilityPackRow.deleted_at)
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


def approver_appointments(limit: int) -> Select[tuple[str, str | None, datetime | None]]:
    """Who holds the Approver role by a person's grant (`0102`), their department and lapse."""
    return (
        select(RoleGrantRow.principal_id, PrincipalRow.primary_department, RoleGrantRow.not_after)
        .join(
            PrincipalRow,
            (PrincipalRow.id == RoleGrantRow.principal_id) & (PrincipalRow.deleted_at.is_(None)),
        )
        .where(RoleGrantRow.role == Role.APPROVER.value, RoleGrantRow.deleted_at.is_(None))
        .order_by(RoleGrantRow.principal_id)
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


def _no_pack_here() -> Absent:
    """One refusal for every way a write to a pack can fail that its writer is not told."""
    return Absent("that pack is not writable by this caller")


def _said(message: str) -> Absent:
    """A refusal a writer holding the pack authority may read, as `prompt_routes` says."""
    return Absent(message, public_message=f"Nothing was changed: {message}.")


def _nothing_changed() -> RequestValidationError:
    """A versioning that would leave the pack as it is: a shape fault in the body, so a 422."""
    return RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", "capabilities"),
                "msg": "the new version carries the capabilities and the label it already has",
                "input": None,
            }
        ]
    )


def pack_view(row: CapabilityPackRow) -> PackView:
    """One stored pack, through `pack_of` so a row the type refuses raises `ValueError`."""
    pack = pack_of(row)
    return PackView(
        slug=pack.slug,
        label=pack.label,
        capabilities=tuple(one.value for one in pack.capabilities),
        version=row.version,
    )


# -------------------------------------------------------------------- the routes

router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get("/govern/packs", response_model=PackCatalogue, responses=COMMON_RESPONSES)
async def packs(request: Request, asked: Asked) -> PackCatalogue:
    """Every live pack and what it bundles, under the vocabulary's grant.

    A pack's contents are capability names, so the Capabilities screen's read decides, asked
    before the database for the ordering every govern route keeps.
    """
    may_write = may_write_packs(asked.reach, asked.now)
    if not permitted(screen(VOCABULARY_SCREEN).read, asked.reach, asked.now):
        return PackCatalogue(packs=(), may_write=may_write)
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        rows = (await session.execute(live_packs(MAX_PACKS))).scalars().all()
    shown: list[PackView] = []
    for row in rows:
        try:
            shown.append(pack_view(row))
        except ValueError:
            log.warning("pack row does not construct", pack=row.name)
    return PackCatalogue(packs=tuple(shown), may_write=may_write)


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
        # FOR SHARE, so a retirement waits for this assignment to commit and then sees it, and an
        # assignment racing a retirement re-reads the pack and finds it retired.
        pack_row = (
            await session.execute(one_live_pack(body.pack_slug).with_for_update(read=True))
        ).scalar_one_or_none()
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


# ------------------------------------------------------------------- writing packs (M27.15.24)


def _factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _capabilities(values: Sequence[str]) -> list[Capability] | None:
    """Stored or submitted capabilities as the type reads them, or None when one does not read."""
    try:
        return [Capability(value=one) for one in values]
    except ValueError:
        return None


async def _registered_or_refused(
    session: AsyncSession, capabilities: Sequence[str], asked: Asked
) -> None:
    """Refuse a capability the registry does not hold, readably to a reader of the vocabulary.

    The first one the writer typed that is missing, named back to them, and only when they may name
    capabilities at all, because what the registry holds is the vocabulary the Capabilities screen
    governs. Anybody else gets the one refusal.
    """
    found = set((await session.execute(registered(capabilities))).scalars().all())
    missing = next((one for one in capabilities if one not in found), None)
    if missing is None:
        return
    await session.rollback()
    log.info("pack names an unregistered capability", principal=asked.caller.principal.id)
    if may_name_capabilities(asked.reach, asked.now):
        raise _said(NOT_A_REGISTERED_CAPABILITY.format(capability=missing))
    raise _no_pack_here()


async def _refuse(session: AsyncSession, refusal: Absent) -> Absent:
    await session.rollback()
    return refusal


@router.post(
    "/govern/packs", response_model=PackChanged, responses=COMMON_RESPONSES, status_code=201
)
async def create_pack(request: Request, body: PackWriting, asked: Asked) -> PackChanged:
    """Create a pack at version one, only if its writer could grant everything in it everywhere.

    `may_bundle` before the database; then a taken short name, said, because the writer governs
    every pack; then the registry; then the insert, attributed, whose trigger records `created`.
    """
    reach, now = asked.reach, asked.now
    wanted = _capabilities(body.capabilities)
    if wanted is None or not may_bundle(reach, wanted, now):
        log.info("pack not creatable", principal=asked.caller.principal.id)
        raise _no_pack_here()
    async with _factory(request)() as session:
        if (await session.execute(one_live_pack(body.slug))).first() is not None:
            raise await _refuse(session, _said(A_PACK_NAME_IS_TAKEN))
        await _registered_or_refused(session, body.capabilities, asked)
        await attribute(session, asked)
        try:
            version, at = (
                await session.execute(creating_pack(body.slug, body.label, body.capabilities))
            ).one()
        except IntegrityError:
            # A pack written with this name in the moment since the read: the same sentence.
            raise await _refuse(session, _said(A_PACK_NAME_IS_TAKEN)) from None
        await session.commit()
    return PackChanged(slug=body.slug, version=version, change="created", at=at)


@router.post("/govern/packs/version", response_model=PackChanged, responses=COMMON_RESPONSES)
async def version_pack(request: Request, body: PackVersioning, asked: Asked) -> PackChanged:
    """Move a pack to its next version in place, if it is still at the version the page showed.

    See `A_VERSION_IS_THE_SAME_PACK_MOVED_IN_PLACE`. `may_bundle` of the new pack before the
    database and of the stored one under the row's lock, so nobody takes out of a pack what they
    could not have put in; only then is the version compared and said, and a body leaving the pack
    as it is answered 422.
    """
    reach, now = asked.reach, asked.now
    wanted = _capabilities(body.capabilities)
    if wanted is None or not may_bundle(reach, wanted, now):
        log.info("pack not versionable", principal=asked.caller.principal.id)
        raise _no_pack_here()
    async with _factory(request)() as session:
        row = (await session.execute(pack_locked(body.slug))).scalar_one_or_none()
        held = None if row is None else _capabilities(row.capabilities)
        if row is None or held is None or not may_bundle(reach, held, now):
            raise await _refuse(session, _no_pack_here())
        if row.version != body.expected_version:
            raise await _refuse(session, _said(IT_CHANGED_SINCE_YOU_OPENED_IT))
        if row.description == body.label and set(row.capabilities) == set(body.capabilities):
            await session.rollback()
            raise _nothing_changed()
        await _registered_or_refused(session, body.capabilities, asked)
        await attribute(session, asked)
        moved = (
            await session.execute(
                versioning_pack(row, body.expected_version, body.label, body.capabilities)
            )
        ).one_or_none()
        if moved is None:
            raise await _refuse(session, _said(IT_CHANGED_SINCE_YOU_OPENED_IT))
        await session.commit()
    return PackChanged(slug=body.slug, version=moved[0], change="versioned", at=moved[1])


@router.post(
    "/govern/packs/copy", response_model=PackChanged, responses=COMMON_RESPONSES, status_code=201
)
async def copy_pack(request: Request, body: PackCopying, asked: Asked) -> PackChanged:
    """Create a pack carrying what a live one carries, at version one, under a new short name.

    The pack authority before the database, and `may_bundle` of what the copy will carry once the
    source is read, so a copy is never a way to write a pack its writer could not create.
    """
    reach, now = asked.reach, asked.now
    if not may_write_packs(reach, now):
        log.info("pack not copyable", principal=asked.caller.principal.id)
        raise _no_pack_here()
    async with _factory(request)() as session:
        source = (await session.execute(one_live_pack(body.slug))).scalar_one_or_none()
        carried = None if source is None else _capabilities(source.capabilities)
        if source is None or carried is None or not may_bundle(reach, carried, now):
            raise await _refuse(session, _no_pack_here())
        if (await session.execute(one_live_pack(body.new_slug))).first() is not None:
            raise await _refuse(session, _said(A_PACK_NAME_IS_TAKEN))
        capabilities = list(source.capabilities)
        await _registered_or_refused(session, capabilities, asked)
        await attribute(session, asked)
        try:
            version, at = (
                await session.execute(creating_pack(body.new_slug, body.label, capabilities))
            ).one()
        except IntegrityError:
            raise await _refuse(session, _said(A_PACK_NAME_IS_TAKEN)) from None
        await session.commit()
    return PackChanged(slug=body.new_slug, version=version, change="copied", at=at)


@router.post("/govern/packs/retirement", response_model=PackChanged, responses=COMMON_RESPONSES)
async def retire_pack(request: Request, body: PackRetirement, asked: Asked) -> PackChanged:
    """Retire a pack nobody holds, if it is still at the version the confirmation showed.

    See `A_PACK_SOMEBODY_HOLDS_IS_NOT_RETIRED`: one live assignment refuses it, in a sentence that
    names nobody and no figure. An assignment racing this waits on the row's lock, because the
    assignment route reads the pack FOR SHARE.
    """
    reach, now = asked.reach, asked.now
    if not may_write_packs(reach, now):
        log.info("pack not retirable", principal=asked.caller.principal.id)
        raise _no_pack_here()
    async with _factory(request)() as session:
        row = (await session.execute(pack_locked(body.slug))).scalar_one_or_none()
        if row is None:
            raise await _refuse(session, _no_pack_here())
        if row.version != body.expected_version:
            raise await _refuse(session, _said(IT_CHANGED_SINCE_YOU_OPENED_IT))
        if (await session.execute(held_by_somebody(row))).first() is not None:
            raise await _refuse(session, _said(A_PACK_SOMEBODY_HOLDS_IS_NOT_RETIRED))
        await attribute(session, asked)
        retired = (await session.execute(retiring_pack(row, body.expected_version))).one_or_none()
        if retired is None:
            raise await _refuse(session, _said(IT_CHANGED_SINCE_YOU_OPENED_IT))
        await session.commit()
    return PackChanged(slug=body.slug, version=retired[0], change="retired", at=retired[1])


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
        holders = [
            (pid, department)
            for pid, department in (
                await session.execute(approver_holders(MAX_PEOPLE_PER_PAGE))
            ).all()
        ]
        # A person's appointment counts while it has not lapsed, beside the directory's.
        holders += [
            (pid, department)
            for pid, department, lapses in (
                await session.execute(approver_appointments(MAX_PEOPLE_PER_PAGE))
            ).all()
            if lapses is None or lapses > asked.now
        ]

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
