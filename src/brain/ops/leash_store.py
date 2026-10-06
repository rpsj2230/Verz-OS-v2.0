"""An agent's leash moves, supervised actions, verdicts and supervision pin, read and written.

`brain.agents.leash_moves` decides every move and `brain.agents.supervision` every review; this
module keeps what they decide in `0195`'s four tables and decides nothing itself beyond the order
of its writes. It holds no policy, which is `brain.ops.limit_store`'s split: the rules can be tested
without a database, and the database half without the rules.

**Every write is in its writer's own name.** Each table's insert policy admits a row naming the
session's principal as its changer, reviewer, decider or the person an action ran for, and the
store sets that principal from the row itself, so a write cannot be recorded as somebody else's.
A move also sets the three settings `0195`'s trigger reads, so its ledger entry names the request.

**A row that no longer constructs is absent, not a fault**, for `brain.ops.skill_store`'s reason:
one row broken by hand would otherwise take every agent page down.

**An action is recorded once per route.** The same action retried is the same digest, and the
conflict leaves the first row where it was, which is what `brain.agents.supervision` counts: an
agent that retried one action ten times did one action.

Task ids: M39.3.2.1, M39.3.2.5, M39.8.2
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.leash_moves import LeashMove, LeashMoveError
from brain.agents.supervision import ShadowPin, ShadowReview, SupervisionError
from brain.audit.record import ApprovalVerdict
from brain.console.reach_view import CircuitBreak, LeashError, PromotionEvidence
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.gate.leash import ActionRecord, CheckName, Route
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.tables.audit import attributed_to
from brain.tables.leash import (
    ActionVerdictRow,
    LeashChangeRow,
    MoveKind,
    PinOutcome,
    SupervisedActionRow,
    SupervisionPinRow,
)

log = structlog.get_logger()

#: The most rows of each kind one agent's page is built from. A resource bound on the read.
MAX_ROWS: Final = 2_000


def _as(principal_id: str) -> Any:
    # Transaction-local, as `brain.ops.artifact_store` sets the same setting.
    return text("SELECT set_config(:name, :value, true)").bindparams(
        name=PRINCIPAL_SETTING, value=principal_id
    )


# ------------------------------------------------------------------------ rows to records
def move_of(row: LeashChangeRow) -> LeashMove | None:
    """The move a row holds, or None when it does not construct."""
    try:
        kind = MoveKind(row.kind)
        promotion = (
            PromotionEvidence(
                clean_runs=row.clean_runs or 0,
                agreement_rate=row.agreement_rate or 0.0,
                approver_id=row.approver_id or "",
                second_approver_id=row.second_approver_id or "",
            )
            if kind in (MoveKind.PROPOSED, MoveKind.RAISED)
            else None
        )
        trip = (
            CircuitBreak(
                metric=row.metric or "",
                measured=row.measured or 0.0,
                threshold=row.threshold or 0.0,
                at=row.changed_at,
            )
            if kind is MoveKind.TRIPPED
            else None
        )
        return LeashMove(
            agent_id=row.agent_id,
            target=row.target,
            scope=Scope.model_validate(row.scope),
            was=AutonomyTier(row.was),
            became=AutonomyTier(row.became),
            kind=kind,
            at=row.changed_at,
            changed_by=row.changed_by,
            irreversible=row.irreversible,
            promotion=promotion,
            trip=trip,
        )
    except (LeashMoveError, LeashError, ValueError) as exc:
        log.warning("leash move does not construct", move=str(row.id), error=type(exc).__name__)
        return None


def move_values(
    move: LeashMove, *, reason_code: str, ent_hash: str, trace_id: str
) -> dict[str, Any]:
    """The row one move is recorded as, every column named."""
    promotion, trip = move.promotion, move.trip
    return {
        "id": uuid.uuid4(),
        "agent_id": move.agent_id,
        "target": move.target,
        "scope": move.scope.model_dump(mode="json"),
        "was": int(move.was),
        "became": int(move.became),
        "kind": move.kind.value,
        "irreversible": move.irreversible,
        "approver_id": None if promotion is None else promotion.approver_id,
        "second_approver_id": (
            None
            if promotion is None or not promotion.second_approver_id
            else promotion.second_approver_id
        ),
        "clean_runs": None if promotion is None else promotion.clean_runs,
        "agreement_rate": None if promotion is None else promotion.agreement_rate,
        "metric": None if trip is None else trip.metric,
        "measured": None if trip is None else trip.measured,
        "threshold": None if trip is None else trip.threshold,
        "changed_by": move.changed_by,
        "reason_code": reason_code,
        "entitlement_hash": ent_hash,
        "trace_id": trace_id,
        "changed_at": move.at,
    }


def action_of(row: SupervisedActionRow) -> ActionRecord | None:
    try:
        return ActionRecord(
            trace_id=row.trace_id,
            agent_id=row.agent_id,
            tool_name=row.tool_name,
            target=row.target,
            principal_id=row.principal_id,
            ent_hash=row.ent_hash,
            action_digest=row.action_digest,
            route=Route(row.route),
            tier=AutonomyTier(row.tier),
            checks=tuple(CheckName(one) for one in row.checks),
            at=row.at,
        )
    except ValueError as exc:
        log.warning("supervised action does not construct", error=type(exc).__name__)
        return None


def verdict_of(row: ActionVerdictRow) -> ShadowReview | None:
    try:
        return ShadowReview(
            agent_id=row.agent_id,
            action_digest=row.action_digest,
            verdict=ApprovalVerdict(row.verdict),
            reviewer_id=row.reviewer_id,
            at=row.at,
        )
    except ValueError as exc:
        log.warning("action verdict does not construct", error=type(exc).__name__)
        return None


@dataclass(frozen=True)
class PinState:
    """The newest supervision row for an agent: the pin as it stands and what the review found."""

    pin: ShadowPin
    outcome: PinOutcome
    understood: int | None
    reviewed: int | None
    simulated: int | None
    decided_at: datetime


def pin_of(row: SupervisionPinRow) -> PinState | None:
    try:
        return PinState(
            pin=ShadowPin(
                agent_id=row.agent_id, pinned_at=row.pinned_at, review_due_at=row.review_due_at
            ),
            outcome=PinOutcome(row.outcome),
            understood=row.understood,
            reviewed=row.reviewed,
            simulated=row.simulated,
            decided_at=row.decided_at,
        )
    except (SupervisionError, ValueError) as exc:
        log.warning("supervision pin does not construct", error=type(exc).__name__)
        return None


@dataclass(frozen=True)
class LeashState:
    """Everything one agent's leash is decided from, as stored."""

    moves: tuple[LeashMove, ...]
    actions: tuple[ActionRecord, ...]
    verdicts: tuple[ShadowReview, ...]
    pin: PinState | None


# --------------------------------------------------------------------------- the reads
async def moves_in(session: AsyncSession, agent_id: str) -> tuple[LeashMove, ...]:
    rows = (
        (
            await session.execute(
                select(LeashChangeRow)
                .where(LeashChangeRow.agent_id == agent_id)
                .order_by(LeashChangeRow.changed_at)
                .limit(MAX_ROWS)
            )
        )
        .scalars()
        .all()
    )
    return tuple(one for one in (move_of(row) for row in rows) if one is not None)


async def pin_in(session: AsyncSession, agent_id: str) -> PinState | None:
    row = (
        await session.execute(
            select(SupervisionPinRow)
            .where(SupervisionPinRow.agent_id == agent_id)
            .order_by(SupervisionPinRow.decided_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return None if row is None else pin_of(row)


async def state_in(session: AsyncSession, agent_id: str) -> LeashState:
    """The moves, the actions, the verdicts and the pin of one agent, in one session."""
    actions = (
        (
            await session.execute(
                select(SupervisedActionRow)
                .where(SupervisedActionRow.agent_id == agent_id)
                .order_by(SupervisedActionRow.at)
                .limit(MAX_ROWS)
            )
        )
        .scalars()
        .all()
    )
    verdicts = (
        (
            await session.execute(
                select(ActionVerdictRow)
                .where(ActionVerdictRow.agent_id == agent_id)
                .order_by(ActionVerdictRow.at)
                .limit(MAX_ROWS)
            )
        )
        .scalars()
        .all()
    )
    return LeashState(
        moves=await moves_in(session, agent_id),
        actions=tuple(one for one in (action_of(row) for row in actions) if one is not None),
        verdicts=tuple(one for one in (verdict_of(row) for row in verdicts) if one is not None),
        pin=await pin_in(session, agent_id),
    )


# --------------------------------------------------------------------------- the writes
class StoredLeash:
    """`0195`'s four tables over the application's sessions."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def state(self, agent_id: str) -> LeashState:
        async with self._sessions() as session:
            return await state_in(session, agent_id)

    async def move(
        self, move: LeashMove, *, reason_code: str, ent_hash: str, trace_id: str
    ) -> None:
        """Record one move in its changer's name, with the ledger entry its trigger appends."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(move.changed_by))
            for statement in attributed_to(
                actor_id=move.changed_by, ent_hash=ent_hash, trace_id=trace_id
            ):
                await session.execute(statement)
            session.add(
                LeashChangeRow(
                    **move_values(
                        move, reason_code=reason_code, ent_hash=ent_hash, trace_id=trace_id
                    )
                )
            )

    async def record_action(self, record: ActionRecord) -> bool:
        """Keep one action an agent took or simulated. A refusal is not an action; False then."""
        if record.route is Route.REFUSED:
            return False
        async with self._sessions() as session, session.begin():
            await session.execute(_as(record.principal_id))
            written = await session.execute(
                insert(SupervisedActionRow)
                .values(
                    action_digest=record.action_digest,
                    route=record.route.value,
                    agent_id=record.agent_id,
                    tool_name=record.tool_name,
                    target=record.target,
                    principal_id=record.principal_id,
                    ent_hash=record.ent_hash,
                    tier=int(record.tier),
                    checks=[one.value for one in record.checks],
                    trace_id=record.trace_id,
                    at=record.at,
                )
                .on_conflict_do_nothing(index_elements=["action_digest", "route"])
            )
        return bool(getattr(written, "rowcount", 0))

    async def give_verdict(self, review: ShadowReview) -> bool:
        """Keep one person's verdict on one action. A second verdict on it is refused: False."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(review.reviewer_id))
            written = await session.execute(
                insert(ActionVerdictRow)
                .values(
                    action_digest=review.action_digest,
                    agent_id=review.agent_id,
                    verdict=review.verdict.value,
                    reviewer_id=review.reviewer_id,
                    at=review.at,
                )
                .on_conflict_do_nothing(index_elements=["action_digest"])
            )
        return bool(getattr(written, "rowcount", 0))

    async def write_pin(
        self,
        pin: ShadowPin,
        outcome: PinOutcome,
        *,
        by: str,
        counts: tuple[int, int, int] | None,
        at: datetime,
        ent_hash: str,
        trace_id: str,
    ) -> None:
        """Record a pin, or what a review of it found, as a new row."""
        understood, reviewed, simulated = counts if counts is not None else (None, None, None)
        async with self._sessions() as session, session.begin():
            await session.execute(_as(by))
            session.add(
                SupervisionPinRow(
                    id=uuid.uuid4(),
                    agent_id=pin.agent_id,
                    outcome=outcome.value,
                    pinned_at=pin.pinned_at,
                    review_due_at=pin.review_due_at,
                    understood=understood,
                    reviewed=reviewed,
                    simulated=simulated,
                    decided_by=by,
                    entitlement_hash=ent_hash,
                    trace_id=trace_id,
                    decided_at=at,
                )
            )


def simulated_only(actions: Sequence[ActionRecord]) -> tuple[ActionRecord, ...]:
    """The actions a supervision review counts: the simulated ones."""
    return tuple(one for one in actions if one.route is Route.SIMULATE)
