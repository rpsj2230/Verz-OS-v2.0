"""Writing a routed access request, and reading the ones addressed to one owner.

Functions over `gate.access_request` and its handled marks, none of which commits: the caller owns
the transaction, for `brain.ops.telemetry_store.record`'s reason.

**An owner reads their own and nobody else's.** `addressed_to` takes the owner's principal id and
selects by it; there is no parameter that could name somebody else's list, and no count of rows
addressed elsewhere is computed.

**An owner marks their own handled, once.** `mark_handled` inserts a row into `0146`'s
`gate.access_request_handled` only for a request addressed to the owner it is given, and a second
mark is a conflict that inserts nothing; a request that is somebody else's, already handled or
missing is one answer, False. The request row itself is never updated.

Task ids: M4.3.4, M27.16.1
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as insert_or_skip
from sqlalchemy.ext.asyncio import AsyncSession

from brain.tables.access_request import AccessRequestHandledRow, AccessRequestRow


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


async def mark_handled(
    session: AsyncSession, request_id: uuid.UUID, *, owner_id: str, at: datetime
) -> bool:
    """Mark one request handled by its owner. False when it is not theirs or is handled already.

    Does not commit. The same answer for a request addressed elsewhere, one handled already and
    one that does not exist, so a caller cannot ask it which requests exist. `0146`'s insert
    policy refuses a mark naming anybody but the request's owner even if this check were gone.
    """
    addressed = await session.execute(
        select(AccessRequestRow.id)
        .where(AccessRequestRow.id == request_id)
        .where(AccessRequestRow.owner_id == owner_id)
    )
    if addressed.scalar_one_or_none() is None:
        return False
    # What the insert returns, not its row count, which a skipped conflict does not zero here.
    done = await session.execute(
        insert_or_skip(AccessRequestHandledRow)
        .values(request_id=request_id, handled_by=owner_id, handled_at=at)
        .on_conflict_do_nothing(index_elements=[AccessRequestHandledRow.request_id])
        .returning(AccessRequestHandledRow.request_id)
    )
    return done.scalar_one_or_none() is not None


async def handled_among(
    session: AsyncSession, request_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    """When each of these requests was marked handled, for those that were. Does not commit."""
    if not request_ids:
        return {}
    found = await session.execute(
        select(AccessRequestHandledRow.request_id, AccessRequestHandledRow.handled_at).where(
            AccessRequestHandledRow.request_id.in_(list(request_ids))
        )
    )
    return {row[0]: row[1] for row in found.all()}
