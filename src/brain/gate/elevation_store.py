"""The rows behind an elevation request: filed, listed, approved into a lapsing grant, or denied.

`brain.console.elevation` decides who may be shown a request and who may decide one, and
`brain.govern_people_routes` asks the cheap half before this is reached. This holds the SQL between
them and decides nothing, for the split CLAUDE.md names.

**An approval is one transaction, and the question is asked with the database's clock and the
requester's reach as the resolver answers it at that instant.** The attribution first, so the grant
trigger names the approver. Then the request, locked and still pending, with the requester's row and
the named scope. Then `now()`, the transaction's instant, which is also the instant every trigger in
it stamps. Then the requester's reach from `gate.entitlements_with_lapse`, the one resolver, never a
query of this module's own over the grant tables. Then `grant_for`, the route's call into
`brain.console.elevation.may_approve`, which builds the grant with the lapse the request asked for
or refuses. Then three writes: a lapsed grant of the same capability retired, the grant inserted,
and the request marked approved with the grant's id and lapse. See
`THE_GRANT_AND_THE_DECISION_ARE_ONE_WRITE`.

**Why a lapsed grant is retired first.** `gate.capability_grant` holds one live row per person and
capability, and a grant whose `not_after` has passed is still a live row. Without this a person
elevated once could never be elevated to the same capability again. A lapsed row confers nothing, so
retiring it changes no reach; it writes the `revoke` entry `0003` writes for every retirement, which
is the ledger saying truthfully that the old row was taken off the table. A grant that has not
lapsed is not retired: the resolver would have returned it, and `may_approve` refuses a capability
the requester already holds.

**The lapse needs nobody.** Nothing here ends an elevation. `gate.held_grants` stops returning the
grant at its `not_after`, the resolved reach says when with `next_grant_lapse`, and
`brain.gate.resolve` retires a cached reach at that instant.

Task ids: M27.7.8
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, runtime_checkable

from sqlalchemy import Select, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert, ReturningUpdate

from brain.core.entitlement import EntitlementSet
from brain.gate.entitlement_store import PRINCIPAL_SETTING, RESOLVE, entitlements_from
from brain.identity.packs import SubjectGrant
from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.elevation import ElevationDecision, ElevationRequestRow
from brain.tables.gate import CapabilityGrantRow, ScopeRow
from brain.tables.identity import PrincipalRow

#: Why the grant and the decision cannot come apart.
THE_GRANT_AND_THE_DECISION_ARE_ONE_WRITE: Final = (
    "An approval recorded without its grant says somebody was given access they do not have, and "
    "a grant written without the approval is access nobody decided. So the retirement, the grant "
    "and the decision are one transaction, the decision names the grant's row and lapse, and the "
    "table refuses an approval with no grant. Any refusal after the first write raises inside the "
    "transaction and nothing is recorded."
)


@dataclass(frozen=True)
class StoredRequest:
    """One request as the screen reads it, with its requester's name and department."""

    request_id: uuid.UUID
    principal_id: str
    display_name: str | None
    department: str | None
    capability: str
    scope_slug: str
    reason: str
    explanation: str
    hours: int
    requested_at: datetime
    decision: ElevationDecision | None
    decided_by: str | None
    decided_at: datetime | None
    lapses_at: datetime | None
    #: Whether the grant an approval wrote is still a live row. False for anything not approved.
    grant_live: bool


@dataclass(frozen=True)
class NamedScope:
    """The live `gate.scope` row a request names, as `ScopeRecord.from_predicate` takes it."""

    slug: str
    predicate: dict[str, Any]
    is_department: bool
    label: str


@dataclass(frozen=True)
class PendingRequest:
    """A request under its lock, and the scope it names, or None when no live scope has the slug."""

    request: StoredRequest
    scope: NamedScope | None


@dataclass(frozen=True)
class Decided:
    """What a decision wrote: the request, the word, the instant, and the lapse of an approval."""

    request_id: uuid.UUID
    principal_id: str
    decision: ElevationDecision
    decided_at: datetime
    lapses_at: datetime | None


@runtime_checkable
class ElevationRecords(Protocol):
    """What the Elevation requests routes need from the database. `StoredElevations` is one."""

    async def requests(self, *, limit: int) -> tuple[tuple[StoredRequest, ...], bool]:
        """Every request, newest first, at most `limit`, and whether the load came back full."""
        ...

    async def file(
        self,
        *,
        principal_id: str,
        capability: str,
        scope_slug: str,
        reason: str,
        explanation: str,
        hours: int,
        ent_hash: str,
        trace_id: str,
    ) -> StoredRequest | None:
        """Record a pending request by `principal_id`, or None and nothing written."""
        ...

    async def approve(
        self,
        request_id: uuid.UUID,
        *,
        approver_id: str,
        ent_hash: str,
        trace_id: str,
        grant_for: Callable[[PendingRequest, EntitlementSet, datetime], SubjectGrant | None],
    ) -> Decided | None:
        """Approve a pending request into the grant `grant_for` builds, or None and no write."""
        ...

    async def deny(
        self,
        request_id: uuid.UUID,
        *,
        decider_id: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[PendingRequest], bool],
    ) -> Decided | None:
        """Deny a pending request if `may` says so, or None and nothing written."""
        ...


# ------------------------------------------------------------------- the statements


def _set_config(name: str, value: str) -> Any:
    """Transaction-local, for `brain.identity.session_store`'s reason about pooled connections."""
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


_COLUMNS = (
    ElevationRequestRow.id,
    ElevationRequestRow.principal_id,
    PrincipalRow.display_name,
    PrincipalRow.primary_department,
    ElevationRequestRow.capability,
    ElevationRequestRow.scope_slug,
    ElevationRequestRow.reason,
    ElevationRequestRow.explanation,
    ElevationRequestRow.hours,
    ElevationRequestRow.requested_at,
    ElevationRequestRow.decision,
    ElevationRequestRow.decided_by,
    ElevationRequestRow.decided_at,
    ElevationRequestRow.lapses_at,
)


def every_request(limit: int) -> Select[Any]:
    """Every request, newest first, with its requester and whether its grant is still live.

    Outer joins to the requester and to the grant. A retired grant is hidden from the application
    role by `0045`'s policy and filtered here as well, for `brain.govern_routes.live_grants`' reason
    about a statement that depends on a policy being installed.
    """
    return (
        select(
            *_COLUMNS,
            (CapabilityGrantRow.id.is_not(None)).label("grant_live"),
        )
        .join(
            PrincipalRow,
            (PrincipalRow.id == ElevationRequestRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        .join(
            CapabilityGrantRow,
            (CapabilityGrantRow.id == ElevationRequestRow.grant_id)
            & (CapabilityGrantRow.deleted_at.is_(None)),
            isouter=True,
        )
        .order_by(ElevationRequestRow.requested_at.desc(), ElevationRequestRow.id)
        .limit(limit)
    )


def one_pending(request_id: uuid.UUID) -> Select[Any]:
    """One pending request with its requester, locked until the transaction ends, or nothing."""
    return (
        select(*_COLUMNS)
        .join(
            PrincipalRow,
            (PrincipalRow.id == ElevationRequestRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        .where(ElevationRequestRow.id == request_id, ElevationRequestRow.decision.is_(None))
        .with_for_update(of=ElevationRequestRow)
    )


def named_scope(slug: str) -> Select[tuple[str, dict[str, Any], bool, str]]:
    """The live scope a request names, or nothing."""
    return select(ScopeRow.slug, ScopeRow.predicate, ScopeRow.is_department, ScopeRow.label).where(
        ScopeRow.slug == slug, ScopeRow.deleted_at.is_(None)
    )


def filing(
    *,
    principal_id: str,
    capability: str,
    scope_slug: str,
    reason: str,
    explanation: str,
    hours: int,
) -> ReturningInsert[tuple[uuid.UUID, datetime]]:
    """A pending request. Nothing that decides it is among the values."""
    return (
        insert(ElevationRequestRow)
        .values(
            principal_id=principal_id,
            capability=capability,
            scope_slug=scope_slug,
            reason=reason,
            explanation=explanation,
            hours=hours,
        )
        .returning(ElevationRequestRow.id, ElevationRequestRow.requested_at)
    )


def retiring_a_lapsed_grant(principal_id: str, capability: str, at: datetime) -> Any:
    """Retire the live row of this capability whose lapse has passed, if there is one.

    `statement_timestamp()` for the stamp, for `brain.gate.review_store.retire`'s reason about
    `0045`'s policy. Only a row with a lapse at or before `at`: a live unlapsed grant is not
    touched, and the insert after this is refused by the unique index if one exists.
    """
    return (
        update(CapabilityGrantRow)
        .where(
            CapabilityGrantRow.principal_id == principal_id,
            CapabilityGrantRow.capability == capability,
            CapabilityGrantRow.deleted_at.is_(None),
            CapabilityGrantRow.not_after.is_not(None),
            CapabilityGrantRow.not_after <= at,
        )
        .values(deleted_at=func.statement_timestamp())
    )


def granting(grant: SubjectGrant, principal_id: str) -> ReturningInsert[tuple[uuid.UUID]]:
    """The grant an approval writes. `0003`'s triggers bump the version and record it."""
    return (
        insert(CapabilityGrantRow)
        .values(
            principal_id=principal_id,
            capability=grant.capability.value,
            scope=grant.scope.model_dump(),
            granted_by=grant.granted_by,
            reason=grant.reason,
            not_after=grant.not_after,
        )
        .returning(CapabilityGrantRow.id)
    )


def deciding(
    request_id: uuid.UUID,
    *,
    decision: ElevationDecision,
    decided_by: str,
    decided_at: datetime,
    grant_id: uuid.UUID | None = None,
    lapses_at: datetime | None = None,
) -> ReturningUpdate[tuple[datetime | None]]:
    """Mark a pending request decided. `decision IS NULL` in the WHERE, so a second is nothing."""
    return (
        update(ElevationRequestRow)
        .where(ElevationRequestRow.id == request_id, ElevationRequestRow.decision.is_(None))
        .values(
            decision=decision.value,
            decided_by=decided_by,
            decided_at=decided_at,
            grant_id=grant_id,
            lapses_at=lapses_at,
        )
        .returning(ElevationRequestRow.decided_at)
    )


def _stored(row: Any, *, grant_live: bool = False) -> StoredRequest:
    return StoredRequest(
        request_id=row[0],
        principal_id=row[1],
        display_name=row[2],
        department=row[3],
        capability=row[4],
        scope_slug=row[5],
        reason=row[6],
        explanation=row[7],
        hours=row[8],
        requested_at=row[9],
        decision=None if row[10] is None else ElevationDecision(row[10]),
        decided_by=row[11],
        decided_at=row[12],
        lapses_at=row[13],
        grant_live=grant_live,
    )


class _RefusedError(Exception):
    """Raised inside the transaction to roll it back. Never leaves this module."""


# ------------------------------------------------------------------------ the store


class StoredElevations:
    """`ElevationRecords` over this install's database, as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def requests(self, *, limit: int) -> tuple[tuple[StoredRequest, ...], bool]:
        async with self._sessions() as session, session.begin():
            rows = (await session.execute(every_request(limit))).all()
        return tuple(_stored(row, grant_live=bool(row[14])) for row in rows), len(rows) >= limit

    async def file(
        self,
        *,
        principal_id: str,
        capability: str,
        scope_slug: str,
        reason: str,
        explanation: str,
        hours: int,
        ent_hash: str,
        trace_id: str,
    ) -> StoredRequest | None:
        try:
            async with self._sessions() as session, session.begin():
                await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
                await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
                request_id, at = (
                    await session.execute(
                        filing(
                            principal_id=principal_id,
                            capability=capability,
                            scope_slug=scope_slug,
                            reason=reason,
                            explanation=explanation,
                            hours=hours,
                        )
                    )
                ).one()
        except IntegrityError:
            return None
        return StoredRequest(
            request_id=request_id,
            principal_id=principal_id,
            display_name=None,
            department=None,
            capability=capability,
            scope_slug=scope_slug,
            reason=reason,
            explanation=explanation,
            hours=hours,
            requested_at=at,
            decision=None,
            decided_by=None,
            decided_at=None,
            lapses_at=None,
            grant_live=False,
        )

    async def _pending(self, session: AsyncSession, request_id: uuid.UUID) -> PendingRequest:
        row = (await session.execute(one_pending(request_id))).one_or_none()
        if row is None:
            raise _RefusedError
        request = _stored(row)
        found = (await session.execute(named_scope(request.scope_slug))).one_or_none()
        scope = (
            None
            if found is None
            else NamedScope(
                slug=found[0], predicate=dict(found[1]), is_department=found[2], label=found[3]
            )
        )
        return PendingRequest(request=request, scope=scope)

    async def approve(
        self,
        request_id: uuid.UUID,
        *,
        approver_id: str,
        ent_hash: str,
        trace_id: str,
        grant_for: Callable[[PendingRequest, EntitlementSet, datetime], SubjectGrant | None],
    ) -> Decided | None:
        try:
            async with self._sessions() as session, session.begin():
                await session.execute(_set_config(ACTOR_SETTING, approver_id))
                await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
                await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
                pending = await self._pending(session, request_id)
                principal_id = pending.request.principal_id
                at: datetime = (await session.execute(select(func.now()))).scalar_one()
                await session.execute(_set_config(PRINCIPAL_SETTING, principal_id))
                reach = entitlements_from(
                    (
                        await session.execute(RESOLVE, {"principal_id": principal_id, "at": at})
                    ).scalar_one()
                )
                grant = grant_for(pending, reach, at)
                if grant is None or grant.not_after is None:
                    raise _RefusedError
                await session.execute(
                    retiring_a_lapsed_grant(principal_id, grant.capability.value, at)
                )
                grant_id = (await session.execute(granting(grant, principal_id))).scalar_one()
                decided = (
                    await session.execute(
                        deciding(
                            request_id,
                            decision=ElevationDecision.APPROVED,
                            decided_by=approver_id,
                            decided_at=at,
                            grant_id=grant_id,
                            lapses_at=grant.not_after,
                        )
                    )
                ).scalar_one_or_none()
                if decided is None:
                    raise _RefusedError
                return Decided(
                    request_id=request_id,
                    principal_id=principal_id,
                    decision=ElevationDecision.APPROVED,
                    decided_at=decided,
                    lapses_at=grant.not_after,
                )
        except (_RefusedError, IntegrityError):
            return None

    async def deny(
        self,
        request_id: uuid.UUID,
        *,
        decider_id: str,
        ent_hash: str,
        trace_id: str,
        may: Callable[[PendingRequest], bool],
    ) -> Decided | None:
        try:
            async with self._sessions() as session, session.begin():
                await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
                await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
                pending = await self._pending(session, request_id)
                if not may(pending):
                    raise _RefusedError
                at: datetime = (await session.execute(select(func.now()))).scalar_one()
                decided = (
                    await session.execute(
                        deciding(
                            request_id,
                            decision=ElevationDecision.DENIED,
                            decided_by=decider_id,
                            decided_at=at,
                        )
                    )
                ).scalar_one_or_none()
                if decided is None:
                    raise _RefusedError
                return Decided(
                    request_id=request_id,
                    principal_id=pending.request.principal_id,
                    decision=ElevationDecision.DENIED,
                    decided_at=decided,
                    lapses_at=None,
                )
        except (_RefusedError, IntegrityError):
            return None
