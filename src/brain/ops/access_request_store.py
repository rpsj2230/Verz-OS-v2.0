"""Writing a routed access request, and reading the ones addressed to one owner.

Two functions over `gate.access_request`, neither of which commits: the caller owns the
transaction, for `brain.ops.telemetry_store.record`'s reason.

**An owner reads their own and nobody else's.** `addressed_to` takes the owner's principal id and
selects by it; there is no parameter that could name somebody else's list, and no count of rows
addressed elsewhere is computed.

Task ids: M4.3.4
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from brain.tables.access_request import AccessRequestRow


@dataclass(frozen=True)
class Request:
    """One request as it is stored: exactly one of a field (`entity`, `field`) or `department`."""

    asker_id: str
    owner_id: str
    question: str
    requested_capability: str
    entity: str | None = None
    field: str | None = None
    department: str | None = None

    def __post_init__(self) -> None:
        a_field = self.entity is not None and self.field is not None and self.department is None
        a_department = self.entity is None and self.field is None and self.department is not None
        if not (a_field or a_department):
            msg = "an access request names a field on an entity or a department, and only one"
            raise ValueError(msg)


async def record(session: AsyncSession, request: Request, *, at: datetime) -> None:
    """Store one request, addressed to its owner. Does not commit."""
    await session.execute(
        insert(AccessRequestRow).values(
            asker_id=request.asker_id,
            owner_id=request.owner_id,
            entity=request.entity,
            field=request.field,
            department=request.department,
            question=request.question,
            requested_capability=request.requested_capability,
            requested_at=at,
        )
    )


async def addressed_to(
    session: AsyncSession, owner_id: str, *, limit: int
) -> Sequence[AccessRequestRow]:
    """The newest requests addressed to this owner, at most `limit` of them."""
    found = await session.execute(
        select(AccessRequestRow)
        .where(AccessRequestRow.owner_id == owner_id)
        .order_by(AccessRequestRow.requested_at.desc(), AccessRequestRow.id)
        .limit(limit)
    )
    return found.scalars().all()
