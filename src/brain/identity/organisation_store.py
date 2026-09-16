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

Task ids: M27.7.4
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, runtime_checkable

from sqlalchemy import Select, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert, ReturningUpdate

from brain.identity.organisation_sync import HeldLead, HeldMembership, OrganisationPlan
from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.gate import DepartmentRow, TeamRow
from brain.tables.identity import PrincipalRow
from brain.tables.organisation import DepartmentLeadRow, TeamMembershipRow

#: Why an appointment names the lead it ends by row.
A_LEAD_IS_ENDED_BY_ITS_OWN_ROW_AND_NEVER_BY_ITS_DEPARTMENT: Final = (
    "An appointment reads the department's current lead, asks whether the appointer may stand "
    "that person down, and ends them. Ended by department instead, an appointment racing another "
    "would end whichever lead was live when its update ran, a person nobody asked about. Ended by "
    "the row it read, it ends that person or nothing, and ending nothing refuses the appointment."
)


class SyncRefusedError(Exception):
    """A plan that is not safe to apply was handed to `apply_sync`."""


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
