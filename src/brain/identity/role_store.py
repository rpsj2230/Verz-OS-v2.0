"""`gate.role_grant` read and written, each change under a lock and judged against its rows.

`brain.identity.roles` holds the rules and no connection; this holds the statements and no rule.
An appointment and a retirement each take `ROLE_LOCK`, the lock `0102`'s guard takes, read the
live grants they are about inside the transaction, and hand them to the caller's own judge, so the
separation of duties (M1.8.7) and the Super Admin floor (M1.3.4) are decided about the rows as they
stand rather than as a page showed them. The database's guard is the second answer and a refusal
from it arrives as the ordinary one.

Every write names its actor, reach digest and request to the transaction first, so `0102`'s
trigger records who appointed or removed whom.

Task ids: M1.3.2, M1.3.3, M1.3.4, M1.8.7
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, runtime_checkable

from sqlalchemy import Select, func, insert, null, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.scope import Scope
from brain.identity.roles import Role, RoleGrant
from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.identity import PrincipalRow
from brain.tables.role_grant import RoleGrantRow

#: `0102`'s lock, so the application and the guard serialise on one number.
ROLE_LOCK: Final = 8274419102


class RoleRefusal(enum.StrEnum):
    """Why a role change wrote nothing. Callers without the authority only see `NOT_WRITABLE`."""

    NOT_WRITABLE = "not_writable"
    #: The appointment crosses a separated pair and carries no acknowledgement.
    UNACKNOWLEDGED = "unacknowledged"
    #: Retiring it would leave fewer standing Super Admins than the floor.
    FLOOR = "floor"


@dataclass(frozen=True)
class Attribution:
    actor: str
    ent_hash: str
    trace_id: str


def role_grant_of(row: RoleGrantRow) -> RoleGrant:
    """A stored row as the type the rules are written against. `created_at` is `granted_at`."""
    return RoleGrant(
        principal_id=row.principal_id,
        role=Role(row.role),
        scope=None if row.scope is None else Scope.model_validate(row.scope),
        granted_by=row.granted_by,
        reason=row.reason,
        granted_at=row.created_at,
        not_after=row.not_after,
        deputy_of=row.deputy_of,
    )


def live_role_grants(limit: int) -> Select[tuple[RoleGrantRow, str | None]]:
    """Every live role grant and the department its holder sits in."""
    return (
        select(RoleGrantRow, PrincipalRow.primary_department)
        .join(
            PrincipalRow,
            (PrincipalRow.id == RoleGrantRow.principal_id) & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        .where(RoleGrantRow.deleted_at.is_(None))
        .order_by(RoleGrantRow.role, RoleGrantRow.principal_id)
        .limit(limit)
    )


def live_grants_of(principal_id: str) -> Select[tuple[RoleGrantRow]]:
    return select(RoleGrantRow).where(
        RoleGrantRow.principal_id == principal_id, RoleGrantRow.deleted_at.is_(None)
    )


def every_live_grant() -> Select[tuple[RoleGrantRow]]:
    return select(RoleGrantRow).where(RoleGrantRow.deleted_at.is_(None))


def one_live_grant(grant_id: uuid.UUID) -> Select[tuple[RoleGrantRow]]:
    return (
        select(RoleGrantRow)
        .where(RoleGrantRow.id == grant_id, RoleGrantRow.deleted_at.is_(None))
        .with_for_update()
    )


def adding(grant: RoleGrant, acknowledgement: str | None) -> Any:
    """The INSERT for one role grant. The instant is the database's `created_at`."""
    return (
        insert(RoleGrantRow)
        .values(
            principal_id=grant.principal_id,
            role=grant.role.value,
            # `null()`, not None: a JSONB column stores None as the JSON value `null`, which is
            # not SQL NULL, and `0102`'s scope rule would refuse every company-wide role.
            scope=null() if grant.scope is None else grant.scope.model_dump(mode="json"),
            deputy_of=grant.deputy_of,
            granted_by=grant.granted_by,
            reason=grant.reason,
            acknowledgement=acknowledgement,
            not_after=grant.not_after,
        )
        .returning(RoleGrantRow)
    )


def retiring(grant_id: uuid.UUID) -> Any:
    """`deleted_at` stamped by its own statement, which `0102`'s update policy requires."""
    return (
        update(RoleGrantRow)
        .where(RoleGrantRow.id == grant_id, RoleGrantRow.deleted_at.is_(None))
        .values(deleted_at=func.statement_timestamp())
        .returning(RoleGrantRow.deleted_at)
    )


def _set_config(name: str, value: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


class _RefusedError(Exception):
    def __init__(self, why: RoleRefusal) -> None:
        self.why = why


@runtime_checkable
class RoleRecords(Protocol):
    """What the Roles routes need of the store, so a test can hand them one without a server."""

    async def holders(self, limit: int) -> list[tuple[RoleGrantRow, str | None]]: ...

    async def one(self, grant_id: uuid.UUID) -> RoleGrantRow | None: ...

    async def appoint(
        self,
        grant: RoleGrant,
        *,
        acknowledgement: str | None,
        judge: Callable[[Sequence[RoleGrant]], RoleRefusal | None],
        by: Attribution,
    ) -> RoleGrantRow | RoleRefusal: ...

    async def retire(
        self,
        grant_id: uuid.UUID,
        *,
        judge: Callable[[RoleGrant, Sequence[RoleGrant]], RoleRefusal | None],
        by: Attribution,
    ) -> datetime | RoleRefusal: ...


@dataclass(frozen=True)
class StoredRoles:
    """`gate.role_grant` over the application's pool."""

    sessions: async_sessionmaker[AsyncSession]

    async def _open(self, session: AsyncSession, by: Attribution) -> None:
        await session.execute(_set_config(ACTOR_SETTING, by.actor))
        await session.execute(_set_config(ENT_HASH_SETTING, by.ent_hash))
        await session.execute(_set_config(TRACE_ID_SETTING, by.trace_id))
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": ROLE_LOCK})

    async def holders(self, limit: int) -> list[tuple[RoleGrantRow, str | None]]:
        async with self.sessions() as session:
            return [(row, dept) for row, dept in (await session.execute(live_role_grants(limit)))]

    async def one(self, grant_id: uuid.UUID) -> RoleGrantRow | None:
        async with self.sessions() as session:
            found: RoleGrantRow | None = (
                await session.execute(
                    select(RoleGrantRow).where(
                        RoleGrantRow.id == grant_id, RoleGrantRow.deleted_at.is_(None)
                    )
                )
            ).scalar_one_or_none()
            return found

    async def appoint(
        self,
        grant: RoleGrant,
        *,
        acknowledgement: str | None,
        judge: Callable[[Sequence[RoleGrant]], RoleRefusal | None],
        by: Attribution,
    ) -> RoleGrantRow | RoleRefusal:
        """Write `grant` if `judge`, asked about its holder's live grants under the lock, allows."""
        try:
            async with self.sessions() as session, session.begin():
                await self._open(session, by)
                held = (await session.execute(live_grants_of(grant.principal_id))).scalars()
                refused = judge([role_grant_of(one) for one in held])
                if refused is not None:
                    raise _RefusedError(refused)
                stored: RoleGrantRow = (
                    await session.execute(adding(grant, acknowledgement))
                ).scalar_one()
                return stored
        except _RefusedError as refused:
            return refused.why
        except (IntegrityError, DBAPIError):
            # A duplicate standing grant, an unknown person, or the guard's depth refusal.
            return RoleRefusal.NOT_WRITABLE

    async def retire(
        self,
        grant_id: uuid.UUID,
        *,
        judge: Callable[[RoleGrant, Sequence[RoleGrant]], RoleRefusal | None],
        by: Attribution,
    ) -> datetime | RoleRefusal:
        """Retire one live grant if `judge`, asked about it and every live grant, allows."""
        try:
            async with self.sessions() as session, session.begin():
                await self._open(session, by)
                row = (await session.execute(one_live_grant(grant_id))).scalar_one_or_none()
                if row is None:
                    raise _RefusedError(RoleRefusal.NOT_WRITABLE)
                every = [
                    role_grant_of(one)
                    for one in (await session.execute(every_live_grant())).scalars()
                ]
                refused = judge(role_grant_of(row), every)
                if refused is not None:
                    raise _RefusedError(refused)
                at: datetime | None = (await session.execute(retiring(grant_id))).scalar_one()
                if at is None:
                    raise _RefusedError(RoleRefusal.NOT_WRITABLE)
                return at
        except _RefusedError as refused:
            return refused.why
        except (IntegrityError, DBAPIError):
            # The guard's floor, reached by a row the judge was not shown.
            return RoleRefusal.FLOOR
