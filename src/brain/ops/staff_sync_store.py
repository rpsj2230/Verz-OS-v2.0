"""The SQL for the staff roster and its runs: what the scheduled sync reads, writes and appends.

`brain.identity.staff_roster` decides what a run writes and `brain.ops.staff_sync_run` performs
it. This holds the statements and no judgement, in the split `brain.ops.connector_sync_store`
takes for the same reason: the decision is tested without a database and the statement is tested
by rendering it.

**The member rows and the run row are written in one transaction.** A run whose record said it
added three people while the rows were lost would be a screen describing an estate that does not
exist, and rows without their record would be changes nobody can trace to a run.

**A leaver's agents are found by one join on two digests**, `auth.staff_member.address_hash` to an
email binding's `auth.principal_identity.identity_hash`, so the answer to "whose agents need a new
owner" comes from the mark the sync wrote and a binding somebody proved, never from a display name.

Task ids: M1.6.12, M1.8.9
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from brain.gate.context import Channel
from brain.identity.staff_roster import (
    APPLIED_OUTCOMES,
    Application,
    MemberWrite,
    RunOutcome,
    StoredMember,
    Write,
)
from brain.tables.identity import PrincipalIdentityRow
from brain.tables.staff import StaffMemberRow, StaffSyncRunRow

#: How many runs the console is shown. The newest first; older runs stay in the table.
RUNS_SHOWN = 10


@dataclass(frozen=True)
class RunRecord:
    """One run as the table holds it and the screen draws it."""

    source: str
    started_at: datetime
    finished_at: datetime
    outcome: RunOutcome
    detail: str
    added: tuple[str, ...] = ()
    marked_left: tuple[str, ...] = ()
    renamed: tuple[str, ...] = ()
    withheld: tuple[str, ...] = ()


def members_of(source: str) -> Select[Any]:
    """Every member row this source has written, live or marked as having left."""
    return select(
        StaffMemberRow.address_hash,
        StaffMemberRow.display_name,
        StaffMemberRow.stable_id,
        StaffMemberRow.left_at,
    ).where(StaffMemberRow.source == source)


def last_applied_of(source: str) -> Select[Any]:
    """When a run of this source last applied, or changed nothing, which is also an applied run."""
    return select(func.max(StaffSyncRunRow.finished_at)).where(
        StaffSyncRunRow.source == source,
        StaffSyncRunRow.outcome.in_(sorted(one.value for one in APPLIED_OUTCOMES)),
    )


def recent_runs(limit: int = RUNS_SHOWN) -> Select[Any]:
    """The newest runs of whichever source, newest first."""
    return (
        select(StaffSyncRunRow.__table__)
        .order_by(StaffSyncRunRow.finished_at.desc(), StaffSyncRunRow.id)
        .limit(limit)
    )


def leavers_principals() -> Select[Any]:
    """The principal behind every member marked as having left, through a proven email binding."""
    return (
        select(PrincipalIdentityRow.principal_id)
        .join(
            StaffMemberRow,
            and_(
                StaffMemberRow.address_hash == PrincipalIdentityRow.identity_hash,
                PrincipalIdentityRow.channel == Channel.EMAIL.value,
            ),
        )
        .where(StaffMemberRow.left_at.is_not(None), PrincipalIdentityRow.deleted_at.is_(None))
        .distinct()
    )


def _member_write(source: str, one: MemberWrite, now: datetime) -> Any:
    """The statement one decided write becomes."""
    if one.write is Write.MARK_LEFT:
        return (
            update(StaffMemberRow)
            .where(
                StaffMemberRow.source == source,
                StaffMemberRow.address_hash == one.address_hash,
                StaffMemberRow.left_at.is_(None),
            )
            .values(left_at=now, left_because=one.left_because)
        )
    if one.write is Write.RENAME:
        return (
            update(StaffMemberRow)
            .where(StaffMemberRow.source == source, StaffMemberRow.address_hash == one.was_hash)
            .values(
                address_hash=one.address_hash,
                display_name=one.display_name,
                department=one.department,
                stable_id=one.stable_id,
                last_listed_at=now,
            )
        )
    if one.write is Write.REFRESH:
        return (
            update(StaffMemberRow)
            .where(
                StaffMemberRow.source == source,
                StaffMemberRow.address_hash == one.address_hash,
            )
            .values(
                display_name=one.display_name,
                department=one.department,
                stable_id=one.stable_id,
                last_listed_at=now,
            )
        )
    # An addition is an upsert, so a person who had left and is listed again is the same row
    # with the mark cleared rather than a second row the unique constraint refuses.
    statement = insert(StaffMemberRow).values(
        source=source,
        address_hash=one.address_hash,
        display_name=one.display_name,
        department=one.department,
        stable_id=one.stable_id,
        first_listed_at=now,
        last_listed_at=now,
    )
    return statement.on_conflict_do_update(
        index_elements=[StaffMemberRow.source, StaffMemberRow.address_hash],
        set_={
            "display_name": one.display_name,
            "department": one.department,
            "stable_id": one.stable_id,
            "last_listed_at": now,
            "left_at": None,
            "left_because": None,
        },
    )


def run_row(record: RunRecord) -> Any:
    """The run record, appended."""
    return insert(StaffSyncRunRow).values(
        id=uuid.uuid4(),
        source=record.source,
        started_at=record.started_at,
        finished_at=record.finished_at,
        outcome=record.outcome.value,
        detail=record.detail,
        added=list(record.added),
        marked_left=list(record.marked_left),
        renamed=list(record.renamed),
        withheld=list(record.withheld),
    )


async def read_members(session: AsyncSession, source: str) -> tuple[StoredMember, ...]:
    """The members the last applied runs of this source left behind."""
    rows = (await session.execute(members_of(source))).all()
    return tuple(
        StoredMember(
            address_hash=row.address_hash,
            display_name=row.display_name,
            stable_id=row.stable_id,
            left_at=row.left_at,
        )
        for row in rows
    )


async def read_last_applied(session: AsyncSession, source: str) -> datetime | None:
    """When a run of this source last applied. None means never: the first-run case."""
    found: datetime | None = (await session.execute(last_applied_of(source))).scalar_one_or_none()
    return found


async def write_application(
    session: AsyncSession, application: Application, record: RunRecord
) -> None:
    """Every member write and the run record, in the caller's one transaction."""
    for one in application.writes:
        await session.execute(_member_write(application.source, one, record.finished_at))
    await session.execute(run_row(record))


async def read_runs(session: AsyncSession, limit: int = RUNS_SHOWN) -> tuple[RunRecord, ...]:
    """The newest runs, as the screen draws them."""
    rows = (await session.execute(recent_runs(limit))).mappings().all()
    return tuple(
        RunRecord(
            source=row["source"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            outcome=RunOutcome(row["outcome"]),
            detail=row["detail"],
            added=tuple(row["added"]),
            marked_left=tuple(row["marked_left"]),
            renamed=tuple(row["renamed"]),
            withheld=tuple(row["withheld"]),
        )
        for row in rows
    )


async def read_leavers(session: AsyncSession) -> frozenset[str]:
    """The principals the roster has marked as having left, through their email bindings."""
    return frozenset((await session.execute(leavers_principals())).scalars().all())
