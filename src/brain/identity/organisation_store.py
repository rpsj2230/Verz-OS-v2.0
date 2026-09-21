"""The rows behind who is in each team and who leads each department: read, placed, ended, synced.

`brain.console.organisation` decides who may see a placement and who may make one, and
`brain.govern_people_routes` asks before this is reached. This holds the SQL between them and
decides nothing, for the split CLAUDE.md names: nothing that decides policy owns a client.

**A console write is one transaction that asks its question about the rows it is about to write.**
The attribution first, so the trigger reads it. Then the team or the department, the person, and for
an appointment or a standing down the current lead, each read in the transaction. Then `may`, the
route's call into `brain.console.organisation`, about those rows as they stand rather than about
what the page showed, because a write is pressed by whatever was posted. Then the one or two
statements, whose triggers append the ledger entries. A refusal after the first read writes nothing.

**No lock, because the table is the lock.** One live membership per person per team and one live
lead per department are partial unique indexes, so two placements at once leave one row and an
`IntegrityError`, answered as the ordinary refusal. An appointment ends the current lead **by that
row's id**, so an appointment that raced another cannot end a lead whose authority it never asked
about: its update touches nothing and it is refused, and the insert that would have made a second
lead is refused by the index anyway. See
`A_LEAD_IS_ENDED_BY_ITS_OWN_ROW_AND_NEVER_BY_ITS_DEPARTMENT`.

**The sync applies a plan and judges nothing.** `apply_sync` executes an
`brain.identity.organisation_sync.OrganisationPlan` in one transaction with the source's actor, and
the only rows it may end are rows that actor made, which the statement says as well as the plan.

**The structure is the same shape, with an answer richer than None** (M27.11.1). Creating,
renaming and retiring a department, a team or a scope is one transaction per act: the attribution,
then the rows the act is about read under a row lock, then the route's question about them, then
the statements, whose `0086` triggers append one `organisation` entry per row. A refusal is a
`StructureRefusal` rather than None, because four of them are sentences a caller who holds the
authority may be told, and one is the ordinary refusal every other caller gets. Which is which is
decided by the route's callables and never here: a store that knew a taken scope name was knowable
would be a second answer to who may know a scope exists.

**The expected state is part of every write that changes a live row.** A rename and a retirement
carry the name, or for a scope the predicate, the caller was shown, and a row that no longer has it
is refused as changed since, so a retirement confirmed against one department cannot land on a
department renamed or retired and created again in the meantime. Creating something expects nothing
of that name to be live, which is the name-taken refusal and the partial unique index behind it.

**A retirement is stamped by its own statement**, for
`brain.identity.sign_in_binding.A_RETIREMENT_IS_STAMPED_BY_ITS_OWN_STATEMENT`'s reason: `0045`'s
policies admit a retired row to the application only when its stamp is the retiring statement's
start. Retiring a department retires its teams first, while the department the team trigger reads
its path through is still live, then the scopes the route's callable says go with it, then the
department.

Task ids: M27.7.4, M27.11.1
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, runtime_checkable

import structlog
from sqlalchemy import Select, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert, ReturningUpdate

from brain.core.department import Department as DepartmentRecord
from brain.core.department import ScopeRecord
from brain.core.scope import Scope
from brain.core.scope_sql import PredicateRefusedError
from brain.identity.organisation_sync import HeldLead, HeldMembership, OrganisationPlan
from brain.identity.teams import Team as TeamRecord
from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.gate import DepartmentRow, ScopeRow, TeamRow
from brain.tables.identity import PrincipalRow
from brain.tables.organisation import DepartmentLeadRow, TeamMembershipRow

#: Why an appointment names the lead it ends by row.
A_LEAD_IS_ENDED_BY_ITS_OWN_ROW_AND_NEVER_BY_ITS_DEPARTMENT: Final = (
    "An appointment reads the department's current lead, asks whether the appointer may stand "
    "that person down, and ends them. Ended by department instead, an appointment racing another "
    "would end whichever lead was live when its update ran, a person nobody asked about. Ended by "
    "the row it read, it ends that person or nothing, and ending nothing refuses the appointment."
)


log = structlog.get_logger()


class SyncRefusedError(Exception):
    """A plan that is not safe to apply was handed to `apply_sync`."""


class StructureRefusal(enum.StrEnum):
    """Why a change to a department, a team or a scope wrote nothing.

    `NOT_WRITABLE` is the ordinary refusal: a row that is not there, a row out of the caller's
    reach, and a taken name the caller may not know about are all it, so none of them is told apart.
    The rest are said to a caller the route has already found holds the authority over the row.
    """

    NOT_WRITABLE = "not_writable"
    #: Something live already has that short name.
    NAME_TAKEN = "name_taken"
    #: The row no longer has the name or the predicate the caller was shown.
    CHANGED_SINCE = "changed_since"
    #: A scope names a department no live row carries.
    UNKNOWN_DEPARTMENT = "unknown_department"
    #: The scope that restricts nothing, which is never retired.
    COMPANY_WIDE_SCOPE = "company_wide_scope"
    #: The scope a live department is defined by, which goes with its department.
    DEPARTMENTS_OWN_SCOPE = "departments_own_scope"


@dataclass(frozen=True)
class Attribution:
    """Who is making a change, at what reach, for which request: what the triggers record."""

    actor: str
    ent_hash: str
    trace_id: str


#: What a change to the structure answers: the database's instant, or why nothing was written.
type Structured = datetime | StructureRefusal


@dataclass(frozen=True)
class Person:
    """One principal as a write reads it. `department` is their row's; a missing row is nowhere."""

    principal_id: str
    display_name: str
    department: str | None
    disabled: bool


@dataclass(frozen=True)
class LiveMembership:
    """One live membership, as the page reads it."""

    department: str
    team: str
    principal_id: str


@dataclass(frozen=True)
class LiveLead:
    """One live lead, as the page reads it."""

    department: str
    principal_id: str


@runtime_checkable
class OrganisationRecords(Protocol):
    """What the Departments and teams routes need to write. `StoredOrganisation` is one."""

    async def place(
        self,
        *,
        department: str,
        team: str,
        principal_id: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[Person], bool],
    ) -> datetime | None:
        """Put a person in a team if `may` says so. When, or None and nothing written."""
        ...

    async def unplace(
        self,
        *,
        department: str,
        team: str,
        principal_id: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[Person], bool],
    ) -> datetime | None:
        """Take a person out of a team if `may` says so. When, or None and nothing written."""
        ...

    async def appoint(
        self,
        *,
        department: str,
        principal_id: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[Person, Person | None], bool],
    ) -> datetime | None:
        """Make a person a department's lead, ending the current one, if `may` says so."""
        ...

    async def stand_down(
        self,
        *,
        department: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[Person], bool],
    ) -> datetime | None:
        """End a department's current lead if `may` says so about them."""
        ...


@runtime_checkable
class StructureRecords(Protocol):
    """What the routes that create, rename and retire departments, teams and scopes need to write.

    A protocol of its own rather than more methods on `OrganisationRecords`, so a double of the
    placements is not required to be a double of the structure too. `StoredOrganisation` is both.
    """

    async def found_department(
        self, *, department: DepartmentRecord, scope: ScopeRecord, by: Attribution
    ) -> Structured:
        """Write a department and the scope it is defined by, or neither."""
        ...

    async def rename_department(
        self, *, slug: str, expected_name: str, name: str, by: Attribution
    ) -> Structured:
        """Change a live department's name, if it still has the name the caller was shown."""
        ...

    async def retire_department(
        self,
        *,
        slug: str,
        expected_name: str,
        takes: Callable[[str, ScopeRecord | None, str], bool],
        by: Attribution,
    ) -> Structured:
        """Retire a live department, its teams, and every live scope `takes` says goes with it.

        `takes` is asked about each live scope's slug, the scope as the type reads it or None when
        the type refuses the row, and the slug of the scope the department row names.
        """
        ...

    async def add_team(self, *, team: TeamRecord, by: Attribution) -> Structured:
        """Write a team into a live department."""
        ...

    async def rename_team(
        self, *, department: str, slug: str, expected_name: str, name: str, by: Attribution
    ) -> Structured:
        """Change a live team's name, if it still has the name the caller was shown."""
        ...

    async def retire_team(
        self, *, department: str, slug: str, expected_name: str, by: Attribution
    ) -> Structured:
        """Retire a live team, if it still has the name the caller was shown."""
        ...

    async def draw_scope(
        self,
        *,
        scope: ScopeRecord,
        departments: Sequence[str],
        may_know: Callable[[ScopeRecord | None], bool],
        by: Attribution,
        team: str | None = None,
    ) -> Structured:
        """Write a scope over live departments. A taken slug is `NAME_TAKEN` only if `may_know`
        says so about the live scope holding it, and the ordinary refusal otherwise. A `team`
        must be a live team of the one department named, or the ordinary refusal."""
        ...

    async def retire_scope(
        self,
        *,
        slug: str,
        expected: Scope,
        judge: Callable[[ScopeRecord, bool], StructureRefusal | None],
        by: Attribution,
    ) -> Structured:
        """Retire a live scope if `judge` finds nothing against it and its predicate is `expected`.

        `judge` is asked about the scope and whether a live department names it as its own.
        """
        ...


# ------------------------------------------------------------------- the statements


def _set_config(name: str, value: str) -> Any:
    """Transaction-local, for `brain.identity.session_store`'s reason about pooled connections."""
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


def live_memberships(limit: int) -> Select[tuple[str, str, str]]:
    """Every live membership of a live team of a live department: department, team, person."""
    return (
        select(DepartmentRow.slug, TeamRow.slug, TeamMembershipRow.principal_id)
        .join(TeamRow, TeamRow.id == TeamMembershipRow.team_id)
        .join(DepartmentRow, DepartmentRow.id == TeamRow.department_id)
        .where(
            TeamMembershipRow.ended_at.is_(None),
            TeamRow.deleted_at.is_(None),
            DepartmentRow.deleted_at.is_(None),
        )
        .order_by(DepartmentRow.slug, TeamRow.slug, TeamMembershipRow.principal_id)
        .limit(limit)
    )


def live_leads(limit: int) -> Select[tuple[str, str]]:
    """Every live lead of a live department: department, person."""
    return (
        select(DepartmentRow.slug, DepartmentLeadRow.principal_id)
        .join(DepartmentRow, DepartmentRow.id == DepartmentLeadRow.department_id)
        .where(DepartmentLeadRow.ended_at.is_(None), DepartmentRow.deleted_at.is_(None))
        .order_by(DepartmentRow.slug)
        .limit(limit)
    )


def one_team(department: str, team: str) -> Select[tuple[Any]]:
    """The live team by its department's slug and its own, or nothing."""
    return (
        select(TeamRow.id)
        .join(DepartmentRow, DepartmentRow.id == TeamRow.department_id)
        .where(
            DepartmentRow.slug == department,
            DepartmentRow.deleted_at.is_(None),
            TeamRow.slug == team,
            TeamRow.deleted_at.is_(None),
        )
    )


def one_department(department: str) -> Select[tuple[Any]]:
    """The live department by slug, or nothing."""
    return select(DepartmentRow.id).where(
        DepartmentRow.slug == department, DepartmentRow.deleted_at.is_(None)
    )


def one_person(principal_id: str) -> Select[tuple[str, str, str | None, datetime | None]]:
    """A live principal's id, name, department and disablement, or nothing."""
    return select(
        PrincipalRow.id,
        PrincipalRow.display_name,
        PrincipalRow.primary_department,
        PrincipalRow.disabled_at,
    ).where(PrincipalRow.id == principal_id, PrincipalRow.deleted_at.is_(None))


def current_lead(department_id: Any) -> Select[tuple[Any, str]]:
    """The live lead row of one department: its id and whose."""
    return select(DepartmentLeadRow.id, DepartmentLeadRow.principal_id).where(
        DepartmentLeadRow.department_id == department_id, DepartmentLeadRow.ended_at.is_(None)
    )


def joining(team_id: Any, principal_id: str, actor: str) -> ReturningInsert[tuple[datetime]]:
    return (
        insert(TeamMembershipRow)
        .values(team_id=team_id, principal_id=principal_id, added_by=actor)
        .returning(TeamMembershipRow.added_at)
    )


def leaving(
    team_id: Any, principal_id: str, actor: str, *, made_by: str | None = None
) -> ReturningUpdate[tuple[datetime | None]]:
    """End one live membership. `made_by` narrows it to rows one actor made: the sync's filter."""
    statement = update(TeamMembershipRow).where(
        TeamMembershipRow.team_id == team_id,
        TeamMembershipRow.principal_id == principal_id,
        TeamMembershipRow.ended_at.is_(None),
    )
    if made_by is not None:
        statement = statement.where(TeamMembershipRow.added_by == made_by)
    return statement.values(ended_by=actor, ended_at=func.now()).returning(
        TeamMembershipRow.ended_at
    )


def appointing(
    department_id: Any, principal_id: str, actor: str
) -> ReturningInsert[tuple[datetime]]:
    return (
        insert(DepartmentLeadRow)
        .values(department_id=department_id, principal_id=principal_id, appointed_by=actor)
        .returning(DepartmentLeadRow.appointed_at)
    )


def standing_down(
    lead_id: Any, actor: str, *, made_by: str | None = None
) -> ReturningUpdate[tuple[datetime | None]]:
    """End one live lead row, by its id.

    See `A_LEAD_IS_ENDED_BY_ITS_OWN_ROW_AND_NEVER_BY_ITS_DEPARTMENT`.
    """
    statement = update(DepartmentLeadRow).where(
        DepartmentLeadRow.id == lead_id, DepartmentLeadRow.ended_at.is_(None)
    )
    if made_by is not None:
        statement = statement.where(DepartmentLeadRow.appointed_by == made_by)
    return statement.values(ended_by=actor, ended_at=func.now()).returning(
        DepartmentLeadRow.ended_at
    )


def held_memberships() -> Select[tuple[str, str, str, str]]:
    """Every live membership with the actor who made it, for the sync."""
    return (
        select(
            DepartmentRow.slug,
            TeamRow.slug,
            TeamMembershipRow.principal_id,
            TeamMembershipRow.added_by,
        )
        .join(TeamRow, TeamRow.id == TeamMembershipRow.team_id)
        .join(DepartmentRow, DepartmentRow.id == TeamRow.department_id)
        .where(TeamMembershipRow.ended_at.is_(None))
    )


def held_leads() -> Select[tuple[str, str, str]]:
    """Every live lead with the actor who appointed them, for the sync."""
    return (
        select(DepartmentRow.slug, DepartmentLeadRow.principal_id, DepartmentLeadRow.appointed_by)
        .join(DepartmentRow, DepartmentRow.id == DepartmentLeadRow.department_id)
        .where(DepartmentLeadRow.ended_at.is_(None))
    )


def department_locked(slug: str) -> Select[tuple[Any, str, str]]:
    """The live department by slug, its id, name and the slug of its scope, locked for a change."""
    return (
        select(DepartmentRow.id, DepartmentRow.name, DepartmentRow.scope_slug)
        .where(DepartmentRow.slug == slug, DepartmentRow.deleted_at.is_(None))
        .with_for_update()
    )


def team_locked(department: str, slug: str) -> Select[tuple[Any, str]]:
    """The live team by its department's slug and its own, its id and name, locked for a change."""
    return (
        select(TeamRow.id, TeamRow.name)
        .join(DepartmentRow, DepartmentRow.id == TeamRow.department_id)
        .where(
            DepartmentRow.slug == department,
            DepartmentRow.deleted_at.is_(None),
            TeamRow.slug == slug,
            TeamRow.deleted_at.is_(None),
        )
        .with_for_update(of=TeamRow)
    )


def live_scope_named(slug: str) -> Select[tuple[ScopeRow]]:
    """The live scope with this slug, or nothing. `uq_scope_slug_live` makes it at most one."""
    return select(ScopeRow).where(ScopeRow.slug == slug, ScopeRow.deleted_at.is_(None))


def live_scopes_for_retirement() -> Select[tuple[ScopeRow]]:
    """Every live scope, locked, for a department's retirement to ask which go with it."""
    return select(ScopeRow).where(ScopeRow.deleted_at.is_(None)).with_for_update()


def live_departments_named(slugs: Sequence[str]) -> Select[tuple[str]]:
    """Which of these slugs a live department carries."""
    return select(DepartmentRow.slug).where(
        DepartmentRow.slug.in_(list(slugs)), DepartmentRow.deleted_at.is_(None)
    )


def defines_a_live_department(scope_slug: str) -> Select[tuple[Any]]:
    """A live department whose own scope is this one, or nothing."""
    return (
        select(DepartmentRow.id)
        .where(DepartmentRow.scope_slug == scope_slug, DepartmentRow.deleted_at.is_(None))
        .limit(1)
    )


def founding_scope(record: ScopeRecord) -> ReturningInsert[tuple[datetime]]:
    """The INSERT for one scope. `ScopeRecord.predicate`, the document form, never a model dump."""
    return (
        insert(ScopeRow)
        .values(
            slug=record.slug,
            predicate=record.predicate(),
            is_department=record.is_department,
            label=record.label,
        )
        .returning(ScopeRow.created_at)
    )


def founding_department(record: DepartmentRecord) -> ReturningInsert[tuple[datetime]]:
    return (
        insert(DepartmentRow)
        .values(
            company_id=record.company_id,
            slug=record.slug,
            name=record.name,
            scope_slug=record.scope_slug,
        )
        .returning(DepartmentRow.created_at)
    )


def adding_team(department_id: Any, record: TeamRecord) -> ReturningInsert[tuple[datetime]]:
    return (
        insert(TeamRow)
        .values(department_id=department_id, slug=record.slug, name=record.name)
        .returning(TeamRow.created_at)
    )


def renaming_department(department_id: Any, name: str) -> ReturningUpdate[tuple[datetime]]:
    """The name and nothing else, so a rename can never move the slug every grant carries."""
    return (
        update(DepartmentRow)
        .where(DepartmentRow.id == department_id, DepartmentRow.deleted_at.is_(None))
        .values(name=name)
        .returning(DepartmentRow.updated_at)
    )


def renaming_team(team_id: Any, name: str) -> ReturningUpdate[tuple[datetime]]:
    return (
        update(TeamRow)
        .where(TeamRow.id == team_id, TeamRow.deleted_at.is_(None))
        .values(name=name)
        .returning(TeamRow.updated_at)
    )


def retiring_department(department_id: Any) -> ReturningUpdate[tuple[datetime | None]]:
    """`deleted_at` from the statement's own clock. See the module docstring."""
    return (
        update(DepartmentRow)
        .where(DepartmentRow.id == department_id, DepartmentRow.deleted_at.is_(None))
        .values(deleted_at=func.statement_timestamp())
        .returning(DepartmentRow.deleted_at)
    )


def retiring_team(team_id: Any) -> ReturningUpdate[tuple[datetime | None]]:
    return (
        update(TeamRow)
        .where(TeamRow.id == team_id, TeamRow.deleted_at.is_(None))
        .values(deleted_at=func.statement_timestamp())
        .returning(TeamRow.deleted_at)
    )


def retiring_teams_of(department_id: Any) -> ReturningUpdate[tuple[str]]:
    """Every live team of one department, retired with it."""
    return (
        update(TeamRow)
        .where(TeamRow.department_id == department_id, TeamRow.deleted_at.is_(None))
        .values(deleted_at=func.statement_timestamp())
        .returning(TeamRow.slug)
    )


def retiring_scopes(slugs: Sequence[str]) -> ReturningUpdate[tuple[str]]:
    return (
        update(ScopeRow)
        .where(ScopeRow.slug.in_(list(slugs)), ScopeRow.deleted_at.is_(None))
        .values(deleted_at=func.statement_timestamp())
        .returning(ScopeRow.slug)
    )


def retiring_scope(slug: str) -> ReturningUpdate[tuple[datetime | None]]:
    return (
        update(ScopeRow)
        .where(ScopeRow.slug == slug, ScopeRow.deleted_at.is_(None))
        .values(deleted_at=func.statement_timestamp())
        .returning(ScopeRow.deleted_at)
    )


def scope_record(row: ScopeRow) -> ScopeRecord | None:
    """A stored scope as the type reads it, or None when the type refuses the row."""
    try:
        return ScopeRecord.from_predicate(
            row.slug, row.predicate, is_department=row.is_department, label=row.label
        )
    except (ValueError, PredicateRefusedError):
        log.warning("scope row does not construct", slug=row.slug)
        return None


def _person(row: Any, principal_id: str) -> Person:
    """The person a write asks about, or somebody at nowhere when their row is not live."""
    if row is None:
        return Person(principal_id=principal_id, display_name="", department=None, disabled=True)
    pid, name, department, disabled_at = row
    return Person(
        principal_id=pid, display_name=name, department=department, disabled=disabled_at is not None
    )


class _RefusedError(Exception):
    """Raised inside the transaction to roll it back. Never leaves this module."""


class _StructureRefusedError(Exception):
    """`_RefusedError` carrying why, for the structure's writes. Never leaves this module."""

    def __init__(self, why: StructureRefusal) -> None:
        super().__init__(why.value)
        self.why = why


# ------------------------------------------------------------------------ the store


class StoredOrganisation:
    """`OrganisationRecords` over this install's database, as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def _attributed(
        self, session: AsyncSession, *, actor: str, ent_hash: str, trace_id: str
    ) -> None:
        await session.execute(_set_config(ACTOR_SETTING, actor))
        await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
        await session.execute(_set_config(TRACE_ID_SETTING, trace_id))

    async def place(
        self,
        *,
        department: str,
        team: str,
        principal_id: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[Person], bool],
    ) -> datetime | None:
        try:
            async with self._sessions() as session, session.begin():
                await self._attributed(session, actor=actor, ent_hash=ent_hash, trace_id=trace_id)
                team_id = (await session.execute(one_team(department, team))).scalar_one_or_none()
                row = (await session.execute(one_person(principal_id))).one_or_none()
                if team_id is None or row is None or not may(_person(row, principal_id)):
                    raise _RefusedError
                return (await session.execute(joining(team_id, principal_id, actor))).scalar_one()
        except (_RefusedError, IntegrityError):
            return None

    async def unplace(
        self,
        *,
        department: str,
        team: str,
        principal_id: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[Person], bool],
    ) -> datetime | None:
        try:
            async with self._sessions() as session, session.begin():
                await self._attributed(session, actor=actor, ent_hash=ent_hash, trace_id=trace_id)
                team_id = (await session.execute(one_team(department, team))).scalar_one_or_none()
                row = (await session.execute(one_person(principal_id))).one_or_none()
                if team_id is None or not may(_person(row, principal_id)):
                    raise _RefusedError
                ended = (
                    await session.execute(leaving(team_id, principal_id, actor))
                ).scalar_one_or_none()
                if ended is None:
                    raise _RefusedError
                return ended
        except _RefusedError:
            return None

    async def appoint(
        self,
        *,
        department: str,
        principal_id: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[Person, Person | None], bool],
    ) -> datetime | None:
        try:
            async with self._sessions() as session, session.begin():
                await self._attributed(session, actor=actor, ent_hash=ent_hash, trace_id=trace_id)
                department_id = (
                    await session.execute(one_department(department))
                ).scalar_one_or_none()
                row = (await session.execute(one_person(principal_id))).one_or_none()
                if department_id is None or row is None:
                    raise _RefusedError
                live = (await session.execute(current_lead(department_id))).one_or_none()
                incumbent = None
                if live is not None:
                    held = (await session.execute(one_person(live[1]))).one_or_none()
                    incumbent = _person(held, live[1])
                if not may(_person(row, principal_id), incumbent):
                    raise _RefusedError
                if live is not None:
                    if live[1] == principal_id:
                        raise _RefusedError
                    ended = (
                        await session.execute(standing_down(live[0], actor))
                    ).scalar_one_or_none()
                    if ended is None:
                        raise _RefusedError
                return (
                    await session.execute(appointing(department_id, principal_id, actor))
                ).scalar_one()
        except (_RefusedError, IntegrityError):
            return None

    async def stand_down(
        self,
        *,
        department: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[Person], bool],
    ) -> datetime | None:
        try:
            async with self._sessions() as session, session.begin():
                await self._attributed(session, actor=actor, ent_hash=ent_hash, trace_id=trace_id)
                department_id = (
                    await session.execute(one_department(department))
                ).scalar_one_or_none()
                if department_id is None:
                    raise _RefusedError
                live = (await session.execute(current_lead(department_id))).one_or_none()
                if live is None:
                    raise _RefusedError
                held = (await session.execute(one_person(live[1]))).one_or_none()
                if not may(_person(held, live[1])):
                    raise _RefusedError
                ended = (await session.execute(standing_down(live[0], actor))).scalar_one_or_none()
                if ended is None:
                    raise _RefusedError
                return ended
        except _RefusedError:
            return None

    # ------------------------------------------------------------------ the structure

    async def found_department(
        self, *, department: DepartmentRecord, scope: ScopeRecord, by: Attribution
    ) -> Structured:
        try:
            async with self._sessions() as session, session.begin():
                await self._attributed(
                    session, actor=by.actor, ent_hash=by.ent_hash, trace_id=by.trace_id
                )
                taken = (await session.execute(one_department(department.slug))).first()
                named = (await session.execute(live_scope_named(scope.slug))).first()
                if taken is not None or named is not None:
                    raise _StructureRefusedError(StructureRefusal.NAME_TAKEN)
                await session.execute(founding_scope(scope))
                return (await session.execute(founding_department(department))).scalar_one()
        except _StructureRefusedError as refused:
            return refused.why
        except IntegrityError:
            return StructureRefusal.NAME_TAKEN

    async def rename_department(
        self, *, slug: str, expected_name: str, name: str, by: Attribution
    ) -> Structured:
        try:
            async with self._sessions() as session, session.begin():
                await self._attributed(
                    session, actor=by.actor, ent_hash=by.ent_hash, trace_id=by.trace_id
                )
                row = (await session.execute(department_locked(slug))).one_or_none()
                if row is None:
                    raise _StructureRefusedError(StructureRefusal.NOT_WRITABLE)
                if row[1] != expected_name:
                    raise _StructureRefusedError(StructureRefusal.CHANGED_SINCE)
                return (await session.execute(renaming_department(row[0], name))).scalar_one()
        except _StructureRefusedError as refused:
            return refused.why

    async def retire_department(
        self,
        *,
        slug: str,
        expected_name: str,
        takes: Callable[[str, ScopeRecord | None, str], bool],
        by: Attribution,
    ) -> Structured:
        try:
            async with self._sessions() as session, session.begin():
                await self._attributed(
                    session, actor=by.actor, ent_hash=by.ent_hash, trace_id=by.trace_id
                )
                row = (await session.execute(department_locked(slug))).one_or_none()
                if row is None:
                    raise _StructureRefusedError(StructureRefusal.NOT_WRITABLE)
                department_id, name, defining = row
                if name != expected_name:
                    raise _StructureRefusedError(StructureRefusal.CHANGED_SINCE)
                # Teams first, while the department their trigger reads the path through is live.
                await session.execute(retiring_teams_of(department_id))
                scopes = (await session.execute(live_scopes_for_retirement())).scalars().all()
                going = [one.slug for one in scopes if takes(one.slug, scope_record(one), defining)]
                if going:
                    await session.execute(retiring_scopes(going))
                retired = (
                    await session.execute(retiring_department(department_id))
                ).scalar_one_or_none()
                if retired is None:
                    raise _StructureRefusedError(StructureRefusal.NOT_WRITABLE)
                return retired
        except _StructureRefusedError as refused:
            return refused.why

    async def add_team(self, *, team: TeamRecord, by: Attribution) -> Structured:
        try:
            async with self._sessions() as session, session.begin():
                await self._attributed(
                    session, actor=by.actor, ent_hash=by.ent_hash, trace_id=by.trace_id
                )
                department_id = (
                    await session.execute(one_department(team.department_slug))
                ).scalar_one_or_none()
                if department_id is None:
                    raise _StructureRefusedError(StructureRefusal.NOT_WRITABLE)
                if (await session.execute(one_team(team.department_slug, team.slug))).first():
                    raise _StructureRefusedError(StructureRefusal.NAME_TAKEN)
                return (await session.execute(adding_team(department_id, team))).scalar_one()
        except _StructureRefusedError as refused:
            return refused.why
        except IntegrityError:
            return StructureRefusal.NAME_TAKEN

    async def rename_team(
        self, *, department: str, slug: str, expected_name: str, name: str, by: Attribution
    ) -> Structured:
        try:
            async with self._sessions() as session, session.begin():
                await self._attributed(
                    session, actor=by.actor, ent_hash=by.ent_hash, trace_id=by.trace_id
                )
                row = (await session.execute(team_locked(department, slug))).one_or_none()
                if row is None:
                    raise _StructureRefusedError(StructureRefusal.NOT_WRITABLE)
                if row[1] != expected_name:
                    raise _StructureRefusedError(StructureRefusal.CHANGED_SINCE)
                return (await session.execute(renaming_team(row[0], name))).scalar_one()
        except _StructureRefusedError as refused:
            return refused.why

    async def retire_team(
        self, *, department: str, slug: str, expected_name: str, by: Attribution
    ) -> Structured:
        try:
            async with self._sessions() as session, session.begin():
                await self._attributed(
                    session, actor=by.actor, ent_hash=by.ent_hash, trace_id=by.trace_id
                )
                row = (await session.execute(team_locked(department, slug))).one_or_none()
                if row is None:
                    raise _StructureRefusedError(StructureRefusal.NOT_WRITABLE)
                if row[1] != expected_name:
                    raise _StructureRefusedError(StructureRefusal.CHANGED_SINCE)
                retired = (await session.execute(retiring_team(row[0]))).scalar_one_or_none()
                if retired is None:
                    raise _StructureRefusedError(StructureRefusal.NOT_WRITABLE)
                return retired
        except _StructureRefusedError as refused:
            return refused.why

    async def draw_scope(
        self,
        *,
        scope: ScopeRecord,
        departments: Sequence[str],
        may_know: Callable[[ScopeRecord | None], bool],
        by: Attribution,
        team: str | None = None,
    ) -> Structured:
        try:
            async with self._sessions() as session, session.begin():
                await self._attributed(
                    session, actor=by.actor, ent_hash=by.ent_hash, trace_id=by.trace_id
                )
                held = (await session.execute(live_scope_named(scope.slug))).scalar_one_or_none()
                if held is not None:
                    raise _StructureRefusedError(
                        StructureRefusal.NAME_TAKEN
                        if may_know(scope_record(held))
                        else StructureRefusal.NOT_WRITABLE
                    )
                live = set(
                    (await session.execute(live_departments_named(departments))).scalars().all()
                )
                if not set(departments) <= live:
                    raise _StructureRefusedError(StructureRefusal.UNKNOWN_DEPARTMENT)
                if team is not None and (
                    len(departments) != 1
                    or (await session.execute(one_team(departments[0], team))).first() is None
                ):
                    raise _StructureRefusedError(StructureRefusal.NOT_WRITABLE)
                return (await session.execute(founding_scope(scope))).scalar_one()
        except _StructureRefusedError as refused:
            return refused.why
        except IntegrityError:
            # A scope written by somebody else in the moment between the read and the insert. Who
            # may know about it cannot be asked of a row this transaction never saw, so it is the
            # ordinary refusal. See `draw_scope`'s protocol docstring.
            return StructureRefusal.NOT_WRITABLE

    async def retire_scope(
        self,
        *,
        slug: str,
        expected: Scope,
        judge: Callable[[ScopeRecord, bool], StructureRefusal | None],
        by: Attribution,
    ) -> Structured:
        try:
            async with self._sessions() as session, session.begin():
                await self._attributed(
                    session, actor=by.actor, ent_hash=by.ent_hash, trace_id=by.trace_id
                )
                row = (
                    await session.execute(live_scope_named(slug).with_for_update())
                ).scalar_one_or_none()
                record = None if row is None else scope_record(row)
                if record is None:
                    raise _StructureRefusedError(StructureRefusal.NOT_WRITABLE)
                defines = (await session.execute(defines_a_live_department(slug))).first()
                found = judge(record, defines is not None)
                if found is not None:
                    raise _StructureRefusedError(found)
                if record.scope != expected:
                    raise _StructureRefusedError(StructureRefusal.CHANGED_SINCE)
                retired = (await session.execute(retiring_scope(slug))).scalar_one_or_none()
                if retired is None:
                    raise _StructureRefusedError(StructureRefusal.NOT_WRITABLE)
                return retired
        except _StructureRefusedError as refused:
            return refused.why

    # ------------------------------------------------------------------- the sync

    async def sync_holdings(
        self,
    ) -> tuple[tuple[HeldMembership, ...], tuple[HeldLead, ...], frozenset[str], frozenset[str]]:
        """What `organisation_sync.organisation_plan` compares a roster against.

        Live memberships and leads with who made each, every registered team path and every
        registered department slug.
        """
        async with self._sessions() as session, session.begin():
            members = (await session.execute(held_memberships())).all()
            leads = (await session.execute(held_leads())).all()
            teams = (await session.execute(live_team_paths())).all()
            departments = (await session.execute(one_department_slugs())).scalars().all()
        return (
            tuple(
                HeldMembership(team=f"{d}.{t}", principal_id=p, added_by=by)
                for d, t, p, by in members
            ),
            tuple(HeldLead(department=d, principal_id=p, appointed_by=by) for d, p, by in leads),
            frozenset(f"{d}.{t}" for d, t in teams),
            frozenset(departments),
        )

    async def apply_sync(self, plan: OrganisationPlan, *, trace_id: str) -> None:
        """Execute a plan in one transaction, as the source's actor. Raises and writes nothing
        when the plan is not safe to apply, when a row it names is gone, or when it collides."""
        if not plan.safe_to_apply:
            raise SyncRefusedError(plan.source)
        actor = plan.actor
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(ACTOR_SETTING, actor))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            for one in plan.to_leave:
                department, _, team = one.team.partition(".")
                team_id = (await session.execute(one_team(department, team))).scalar_one()
                ended = (
                    await session.execute(leaving(team_id, one.principal_id, actor, made_by=actor))
                ).scalar_one_or_none()
                if ended is None:
                    raise SyncRefusedError(one.team)
            for lead in plan.to_stand_down:
                department_id = (
                    await session.execute(one_department(lead.department))
                ).scalar_one()
                live = (await session.execute(current_lead(department_id))).one()
                if live[1] != lead.principal_id:
                    raise SyncRefusedError(lead.department)
                ended = (
                    await session.execute(standing_down(live[0], actor, made_by=actor))
                ).scalar_one_or_none()
                if ended is None:
                    raise SyncRefusedError(lead.department)
            for placement in plan.to_join:
                department, _, team = placement.where.partition(".")
                team_id = (await session.execute(one_team(department, team))).scalar_one()
                await session.execute(joining(team_id, placement.principal_id, actor))
            for placement in plan.to_appoint:
                department_id = (
                    await session.execute(one_department(placement.where))
                ).scalar_one()
                await session.execute(appointing(department_id, placement.principal_id, actor))


def live_team_paths() -> Select[tuple[str, str]]:
    """Every live team of a live department, as its department's slug and its own."""
    return (
        select(DepartmentRow.slug, TeamRow.slug)
        .join(DepartmentRow, DepartmentRow.id == TeamRow.department_id)
        .where(TeamRow.deleted_at.is_(None), DepartmentRow.deleted_at.is_(None))
    )


def one_department_slugs() -> Select[tuple[str]]:
    """Every live department's slug."""
    return select(DepartmentRow.slug).where(DepartmentRow.deleted_at.is_(None))
