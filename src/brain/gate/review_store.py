"""The access review's store: what is held, what was last decided about it, and recording one.

`brain.console.govern` decides who may keep or remove a grant in a review round (`may_certify`,
`certify`) and has done since 2026-09-08. Nothing could record the answer, and
`brain.govern_routes.ONLY_THE_HALF_OF_A_ROUND_THAT_HAS_A_ROW_TO_WRITE` said so. This module holds
the SQL for the half that was missing and decides nothing: the route hands in `may`, which asks
`govern.certify`, and this asks it under the row's lock.

**A decision is one transaction with three possible writes and one question.** The attribution
settings first, so every trigger that fires reads them. Then the grant row or the pack assignment
row, locked. Then `may`, about the row as it stands under the lock, because a decision is pressed by
whatever was posted rather than by what the page offered. Then a row in `gate.review_decision`,
whose trigger appends the `certification` entry. And for a removal, the grant row retired, whose
trigger appends the `revoke` entry `0003` has always written. Any refusal after the first write
raises inside the transaction, so a decision recorded against a grant that was then not retired
cannot commit. See `A_REMOVAL_THAT_RECORDS_THE_DECISION_AND_NOT_THE_REMOVAL_IS_A_KEEP`.

**A pack assignment is reviewed as the unit it was granted as.** Removing one capability out of a
pack is not a thing the tables can express, because a pack's grants are not rows: `packs.expand`
produces them from the assignment each time. So a pack row is kept or removed whole, and the
route's `may` asks `certify` about every grant the assignment expands to, all of them. That is
`brain.govern_routes.remove_grant`'s refusal for a pack-borne capability made into the thing it
said was missing: the deliberate act on the assignment.

**What it cannot see.** A grant whose principal row was retired still has its grant row and still
appears, with no name, which is `govern_routes.live_grants`' outer join and argument. A pack that
was retired takes its assignments off the review, because they confer nothing.

Task ids: M27.7.9
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import Select, func, insert, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert, ReturningUpdate

from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.gate import CapabilityGrantRow, CapabilityPackAssignmentRow, CapabilityPackRow
from brain.tables.identity import PrincipalRow
from brain.tables.review import ReviewDecision, ReviewDecisionRow

log = structlog.get_logger(__name__)

#: Why a removal's two writes are one transaction that cannot half commit.
A_REMOVAL_THAT_RECORDS_THE_DECISION_AND_NOT_THE_REMOVAL_IS_A_KEEP: Final = (
    "A removal writes the decision and retires the grant. Committed alone, the decision row says "
    "the grant was removed while the grant goes on conferring everything it did, and the review "
    "screen then shows a round completed over access nobody took away. So the retirement's "
    "absence raises inside the transaction and the decision is rolled back with it."
)


# --------------------------------------------------------------------- the shapes


@dataclass(frozen=True)
class GrantHolding:
    """One live direct grant, and who holds it."""

    row: CapabilityGrantRow
    display_name: str | None
    department: str | None


@dataclass(frozen=True)
class PackHolding:
    """One live pack assignment, its live pack, and who holds it."""

    row: CapabilityPackAssignmentRow
    pack: CapabilityPackRow
    display_name: str | None
    department: str | None


type Holding = GrantHolding | PackHolding


def held_by(holding: Holding) -> str:
    """Who holds this row. A team's grant is never loaded here: see `review_grants`."""
    principal = holding.row.principal_id
    if principal is None:
        msg = "a team's grant is not reviewed person by person"
        raise ValueError(msg)
    return principal


@dataclass(frozen=True)
class LastDecision:
    """The newest decision about one row: what, by whom, and the database's instant."""

    decision: ReviewDecision
    decided_by: str
    decided_at: datetime


@dataclass(frozen=True)
class Decided:
    """What one decision wrote. The row it was about, and the instant the database recorded."""

    row_id: uuid.UUID
    principal_id: str
    decision: ReviewDecision
    decided_at: datetime


class _RefusedError(Exception):
    """Raised inside the transaction to roll it back. Never leaves this module."""


# ---------------------------------------------------------------- the statements


def review_grants(limit: int) -> Select[tuple[CapabilityGrantRow, str, str | None]]:
    """Every live direct grant, with its holder's name and department, at most `limit`.

    An outer join to the principal, for `brain.govern_routes.live_grants`' fail-closed argument:
    a grant whose principal row is gone arrives with no department and reaches only a reviewer
    whose authority is company-wide.
    """
    return (
        select(CapabilityGrantRow, PrincipalRow.display_name, PrincipalRow.primary_department)
        .join(
            PrincipalRow,
            (PrincipalRow.id == CapabilityGrantRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        # A team's grant (M1.5.3) is reviewed as the team's, which this round does not yet do.
        .where(
            CapabilityGrantRow.deleted_at.is_(None), CapabilityGrantRow.principal_id.is_not(None)
        )
        .order_by(CapabilityGrantRow.principal_id, CapabilityGrantRow.capability)
        .limit(limit)
    )


def review_assignments(
    limit: int,
) -> Select[tuple[CapabilityPackAssignmentRow, CapabilityPackRow, str, str | None]]:
    """Every live pack assignment of a live pack, with its holder, at most `limit`.

    An inner join to the pack, for `brain.govern_routes.live_assignments`' reason: an assignment
    of a retired pack confers nothing and is not a holding to review.
    """
    return (
        select(
            CapabilityPackAssignmentRow,
            CapabilityPackRow,
            PrincipalRow.display_name,
            PrincipalRow.primary_department,
        )
        .join(
            CapabilityPackRow,
            (CapabilityPackRow.id == CapabilityPackAssignmentRow.pack_id)
            & (CapabilityPackRow.deleted_at.is_(None)),
        )
        .join(
            PrincipalRow,
            (PrincipalRow.id == CapabilityPackAssignmentRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        .where(CapabilityPackAssignmentRow.deleted_at.is_(None))
        .order_by(CapabilityPackAssignmentRow.principal_id, CapabilityPackAssignmentRow.pack_id)
        .limit(limit)
    )


def decisions_about(row_ids: Sequence[uuid.UUID]) -> Select[tuple[ReviewDecisionRow]]:
    """Every decision about these rows, newest first. The newest per row is the one shown."""
    return (
        select(ReviewDecisionRow)
        .where(
            or_(
                ReviewDecisionRow.grant_id.in_(row_ids),
                ReviewDecisionRow.assignment_id.in_(row_ids),
            )
        )
        .order_by(ReviewDecisionRow.created_at.desc(), ReviewDecisionRow.id)
    )


def one_grant_to_decide(
    row_id: uuid.UUID,
) -> Select[tuple[CapabilityGrantRow, str, str | None]]:
    """One live direct grant, locked until the transaction ends, or nothing."""
    return (
        select(CapabilityGrantRow, PrincipalRow.display_name, PrincipalRow.primary_department)
        .join(
            PrincipalRow,
            (PrincipalRow.id == CapabilityGrantRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        .where(
            CapabilityGrantRow.id == row_id,
            CapabilityGrantRow.deleted_at.is_(None),
            CapabilityGrantRow.principal_id.is_not(None),
        )
        .with_for_update(of=CapabilityGrantRow)
    )


def one_assignment_to_decide(
    row_id: uuid.UUID,
) -> Select[tuple[CapabilityPackAssignmentRow, CapabilityPackRow, str, str | None]]:
    """One live pack assignment of a live pack, locked until the transaction ends, or nothing."""
    return (
        select(
            CapabilityPackAssignmentRow,
            CapabilityPackRow,
            PrincipalRow.display_name,
            PrincipalRow.primary_department,
        )
        .join(
            CapabilityPackRow,
            (CapabilityPackRow.id == CapabilityPackAssignmentRow.pack_id)
            & (CapabilityPackRow.deleted_at.is_(None)),
        )
        .join(
            PrincipalRow,
            (PrincipalRow.id == CapabilityPackAssignmentRow.principal_id)
            & (PrincipalRow.deleted_at.is_(None)),
            isouter=True,
        )
        .where(
            CapabilityPackAssignmentRow.id == row_id,
            CapabilityPackAssignmentRow.deleted_at.is_(None),
        )
        .with_for_update(of=CapabilityPackAssignmentRow)
    )


def record_decision(
    holding: Holding, decision: ReviewDecision, decided_by: str
) -> ReturningInsert[tuple[datetime]]:
    """The decision row. The trigger on it writes the `certification` entry.

    Exactly one of the two row columns, chosen by the holding's type rather than by a flag, so a
    pack decision cannot be written against a grant id.
    """
    values: dict[str, Any] = {
        "principal_id": holding.row.principal_id,
        "decision": decision.value,
        "decided_by": decided_by,
    }
    if isinstance(holding, GrantHolding):
        values["grant_id"] = holding.row.id
    else:
        values["assignment_id"] = holding.row.id
    return insert(ReviewDecisionRow).values(**values).returning(ReviewDecisionRow.created_at)


def retire(holding: Holding) -> ReturningUpdate[tuple[datetime | None]]:
    """Retire the grant row or the assignment row. `deleted_at`, and nothing else.

    `deleted_at IS NULL` in the WHERE clause, so a row somebody else retired first is updated
    nowhere and the decision is rolled back rather than recorded over a removal it did not make.
    The database's clock, for `brain.db.TimestampMixin`'s reason.

    **`statement_timestamp()` and never `now()`.** This was `now()` until 2026-09-17, and as
    `brain_app` every removal was refused with "new row violates row-level security policy":
    `0045`'s policies admit a retired row only when its stamp is the retiring statement's own
    start, and `now()` is the transaction's, which began before the lock and the decision row. The
    stubbed tests compared the SET list with the defect; only CI's database ran it. See
    `brain.identity.sign_in_binding.A_RETIREMENT_IS_STAMPED_BY_ITS_OWN_STATEMENT`.
    """
    table = CapabilityGrantRow if isinstance(holding, GrantHolding) else CapabilityPackAssignmentRow
    return (
        update(table)
        .where(table.id == holding.row.id, table.deleted_at.is_(None))
        .values(deleted_at=func.statement_timestamp())
        .returning(table.deleted_at)
    )


def _set_config(name: str, value: str) -> Any:
    """Transaction-local, for `brain.identity.session_store`'s reason about pooled connections."""
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


def newest(rows: Sequence[ReviewDecisionRow]) -> Mapping[uuid.UUID, LastDecision]:
    """The newest decision per row, from decisions already ordered newest first."""
    found: dict[uuid.UUID, LastDecision] = {}
    for one in rows:
        about = one.grant_id if one.grant_id is not None else one.assignment_id
        if about is None or about in found:
            continue
        found[about] = LastDecision(
            decision=ReviewDecision(one.decision),
            decided_by=one.decided_by,
            decided_at=one.created_at,
        )
    return found


# ------------------------------------------------------------------- the store


@dataclass(frozen=True)
class StoredReview:
    """The grant tables and `gate.review_decision`, read and written as the application role."""

    sessions: async_sessionmaker[AsyncSession]

    async def holdings(
        self, *, limit: int
    ) -> tuple[tuple[Holding, ...], Mapping[uuid.UUID, LastDecision], bool]:
        """Every live holding, the newest decision about each, and whether a load came back full."""
        async with self.sessions() as session, session.begin():
            grants = (await session.execute(review_grants(limit))).all()
            assigned = (await session.execute(review_assignments(limit))).all()
            found: list[Holding] = [
                GrantHolding(row=row, display_name=name, department=department)
                for row, name, department in grants
            ]
            found.extend(
                PackHolding(row=row, pack=pack, display_name=name, department=department)
                for row, pack, name, department in assigned
            )
            ids = [one.row.id for one in found]
            decided = (await session.execute(decisions_about(ids))).scalars().all() if ids else []
        full = len(grants) >= limit or len(assigned) >= limit
        return tuple(found), newest(list(decided)), full

    async def decide(
        self,
        row_id: uuid.UUID,
        *,
        pack: bool,
        decision: ReviewDecision,
        may: Callable[[Holding], bool],
        decided_by: str,
        ent_hash: str,
        trace_id: str,
    ) -> Decided | None:
        """Record one decision about one holding if `may` says so, or return None and write nothing.

        None for a row that is not there, not live, not decidable by the caller, or retired by
        somebody else first, and the four are one answer for the reason
        `brain.console.govern.A_CONTROL_THAT_REFUSES_DIFFERENTLY_SAYS_THE_SESSION_IS_THERE` gives
        about a control. An `IntegrityError` is the same None, for
        `brain.govern_routes.A_CONSTRAINT_VIOLATION_IS_A_FACT_ABOUT_SOMEBODY_ELSE`.
        """
        try:
            async with self.sessions() as session, session.begin():
                await session.execute(_set_config(ACTOR_SETTING, decided_by))
                await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
                await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
                holding = await _locked(session, row_id, pack=pack)
                if holding is None or not may(holding):
                    raise _RefusedError
                stamped = (
                    await session.execute(record_decision(holding, decision, decided_by))
                ).scalar_one_or_none()
                if stamped is None:
                    raise _RefusedError
                if decision is ReviewDecision.REMOVE:
                    retired = (await session.execute(retire(holding))).scalar_one_or_none()
                    if retired is None:
                        raise _RefusedError
        except (_RefusedError, IntegrityError):
            return None
        log.info("review.decided", principal=holding.row.principal_id, decided_by=decided_by)
        return Decided(
            row_id=holding.row.id,
            principal_id=held_by(holding),
            decision=decision,
            decided_at=stamped,
        )


async def _locked(session: AsyncSession, row_id: uuid.UUID, *, pack: bool) -> Holding | None:
    """The holding, locked, or None."""
    if pack:
        found = (await session.execute(one_assignment_to_decide(row_id))).one_or_none()
        if found is None:
            return None
        row, pack_row, name, department = found
        return PackHolding(row=row, pack=pack_row, display_name=name, department=department)
    grant = (await session.execute(one_grant_to_decide(row_id))).one_or_none()
    if grant is None:
        return None
    row, name, department = grant
    return GrantHolding(row=row, display_name=name, department=department)
