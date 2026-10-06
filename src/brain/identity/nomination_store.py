"""`gate.role_nomination` read and written, and a confirmation that writes its role grant.

`brain.console.global_surfaces` holds the rules about a nomination (`Nomination`, `may_confirm`,
`confirm`) and no connection; this holds the statements and no rule. Every decision is the
caller's judge, asked inside the transaction about the row as it stands.

**A confirmation and its grant are one transaction.** The role grant is inserted through
`brain.identity.role_store.adding`, the statement an appointment uses, under `ROLE_LOCK` and with
the nominee's live grants read inside the lock, so the separation of duties is judged about the
rows as they stand, exactly as `StoredRoles.appoint` judges an appointment. The nomination is then
marked confirmed with the grant's id. Rejected: confirming through `StoredRoles.appoint` and
marking afterwards, which owns its own transaction, so a failure between the two would leave a
grant whose nomination still reads undecided and could be confirmed a second time.

**Every write names the session's principal** (`app.principal_id`), which `0208`'s policies compare
with `nominated_by` and `decided_by`, and runs `brain.tables.audit.attributed_to` first, so `0102`'s
trigger puts the confirmer on the grant's ledger entry.

Task ids: M33.1.2.3
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from sqlalchemy import Select, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.identity.role_store import (
    ROLE_LOCK,
    Attribution,
    RoleRefusal,
    adding,
    live_grants_of,
    role_grant_of,
)
from brain.identity.roles import RoleGrant
from brain.tables.audit import attributed_to
from brain.tables.identity import PrincipalRow
from brain.tables.role_grant import RoleGrantRow
from brain.tables.role_nomination import NominationOutcome, RoleNominationRow

#: The most nominations one listing reads. A role is nominated for a handful of times a year.
MOST_NOMINATIONS_READ: Final = 500

#: What a confirmation's judge returns: the grant and its acknowledgement, or why not.
Verdict = tuple[RoleGrant, str | None] | RoleRefusal

#: A nomination with the department its nominee sits in and their name, either missing.
Listed = tuple[RoleNominationRow, str | None, str | None]


def nominations(limit: int) -> Select[tuple[RoleNominationRow, str | None, str | None]]:
    """Every nomination, newest first, with the nominee's department and name where recorded."""
    # `cast` at the library boundary: the outer join makes both columns nullable, which their
    # declared types cannot say.
    return cast(
        "Select[tuple[RoleNominationRow, str | None, str | None]]",
        select(RoleNominationRow, PrincipalRow.primary_department, PrincipalRow.display_name)
        .join(
            PrincipalRow,
            (PrincipalRow.id == RoleNominationRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        .order_by(RoleNominationRow.created_at.desc(), RoleNominationRow.id)
        .limit(limit),
    )


def undecided(nomination_id: uuid.UUID) -> Select[tuple[RoleNominationRow, str | None]]:
    """One undecided nomination and its nominee's department, locked for the decision."""
    return (
        select(RoleNominationRow, PrincipalRow.primary_department)
        .join(
            PrincipalRow,
            (PrincipalRow.id == RoleNominationRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        .where(RoleNominationRow.id == nomination_id, RoleNominationRow.outcome.is_(None))
        .with_for_update(of=RoleNominationRow)
    )


def deciding(
    nomination_id: uuid.UUID, outcome: NominationOutcome, by: str, grant_id: uuid.UUID | None
) -> Any:
    """The one UPDATE a decision is: the outcome, who, when, and the grant a confirmation wrote."""
    return (
        update(RoleNominationRow)
        .where(RoleNominationRow.id == nomination_id, RoleNominationRow.outcome.is_(None))
        .values(
            outcome=outcome.value,
            decided_by=by,
            decided_at=func.statement_timestamp(),
            grant_id=grant_id,
        )
        .returning(RoleNominationRow)
    )


class _RefusedError(Exception):
    def __init__(self, why: RoleRefusal) -> None:
        super().__init__(why.value)
        self.why = why


@dataclass(frozen=True)
class StoredNominations:
    """`gate.role_nomination` over the application's pool."""

    sessions: async_sessionmaker[AsyncSession]

    async def _open(self, session: AsyncSession, by: Attribution) -> None:
        for statement in attributed_to(
            actor_id=by.actor, ent_hash=by.ent_hash, trace_id=by.trace_id
        ):
            await session.execute(statement)
        await session.execute(
            text("SELECT set_config('app.principal_id', :by, true)").bindparams(by=by.actor)
        )

    async def nominate(
        self,
        *,
        principal_id: str,
        role: str,
        scope_slug: str | None,
        reason: str,
        by: Attribution,
    ) -> RoleNominationRow | None:
        """Write one nomination in the caller's own name, or None where the table refused it."""
        try:
            async with self.sessions() as session, session.begin():
                await self._open(session, by)
                stored: RoleNominationRow = (
                    await session.execute(
                        insert(RoleNominationRow)
                        .values(
                            principal_id=principal_id,
                            role=role,
                            scope_slug=scope_slug,
                            nominated_by=by.actor,
                            reason=reason,
                        )
                        .returning(RoleNominationRow)
                    )
                ).scalar_one()
                return stored
        except (IntegrityError, DBAPIError):
            return None

    async def listed(self, limit: int = MOST_NOMINATIONS_READ) -> list[Listed]:
        async with self.sessions() as session:
            return [
                (row, dept, name) for row, dept, name in await session.execute(nominations(limit))
            ]

    async def one(self, nomination_id: uuid.UUID) -> RoleNominationRow | None:
        async with self.sessions() as session:
            found: RoleNominationRow | None = (
                await session.execute(
                    select(RoleNominationRow).where(RoleNominationRow.id == nomination_id)
                )
            ).scalar_one_or_none()
            return found

    async def confirm(
        self,
        nomination_id: uuid.UUID,
        *,
        judge: Callable[[RoleNominationRow, str | None, Sequence[RoleGrant]], Verdict],
        by: Attribution,
    ) -> RoleNominationRow | RoleRefusal:
        """Write the grant `judge` returns and mark the nomination confirmed, or write nothing."""
        try:
            async with self.sessions() as session, session.begin():
                await self._open(session, by)
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": ROLE_LOCK}
                )
                found = (await session.execute(undecided(nomination_id))).one_or_none()
                if found is None:
                    raise _RefusedError(RoleRefusal.NOT_WRITABLE)
                row, department = found
                held = (await session.execute(live_grants_of(row.principal_id))).scalars()
                verdict = judge(row, department, [role_grant_of(one) for one in held])
                if isinstance(verdict, RoleRefusal):
                    raise _RefusedError(verdict)
                grant, acknowledgement = verdict
                written: RoleGrantRow = (
                    await session.execute(adding(grant, acknowledgement))
                ).scalar_one()
                decided: RoleNominationRow = (
                    await session.execute(
                        deciding(nomination_id, NominationOutcome.CONFIRMED, by.actor, written.id)
                    )
                ).scalar_one()
                return decided
        except _RefusedError as refused:
            return refused.why
        except (IntegrityError, DBAPIError):
            # A standing grant already held, a nominee who is not a person, or the guard's refusal.
            return RoleRefusal.NOT_WRITABLE

    async def decline(
        self,
        nomination_id: uuid.UUID,
        *,
        judge: Callable[[RoleNominationRow, str | None], bool],
        by: Attribution,
    ) -> RoleNominationRow | RoleRefusal:
        """Mark the nomination declined where `judge` admits the caller, or write nothing."""
        try:
            async with self.sessions() as session, session.begin():
                await self._open(session, by)
                found = (await session.execute(undecided(nomination_id))).one_or_none()
                if found is None or not judge(found[0], found[1]):
                    raise _RefusedError(RoleRefusal.NOT_WRITABLE)
                decided: RoleNominationRow = (
                    await session.execute(
                        deciding(nomination_id, NominationOutcome.DECLINED, by.actor, None)
                    )
                ).scalar_one()
                return decided
        except _RefusedError as refused:
            return refused.why
        except (IntegrityError, DBAPIError):
            return RoleRefusal.NOT_WRITABLE
