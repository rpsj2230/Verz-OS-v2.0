"""`ops.breach_case`: a suspected breach opened, assessed, notified and closed, by the app role.

`brain.audit.compliance.BreachCase` has computed the PDPA clock since M24.2.4 was first written and
nothing stored one, so the tracker audit found no case had ever been opened on the install. This
is the store; `brain.compliance_routes` is the screen's half.

**Every write is a column going from empty to set, and each is one ledger entry by the database.**
`0104`'s trigger appends a `breach` entry for it, attributed to the row's `updated_by`, which the
update policy pins to the session's principal. So an entry cannot name somebody other than the
person whose session moved the case, and a case cannot move without its entry.

**A case is read back as the model, and the model reports what is wrong.** `case_from` builds a
`BreachCase` from the row, so the obligations and findings the screen shows are the module's
arithmetic and nothing computed here. The model records a late or out-of-order notification
rather than refusing it; closing is the one step refused, and only for an assessment that has
not been made, which is `CLOSING_NEEDS_A_MADE_ASSESSMENT`.

Task ids: M24.2.4
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, runtime_checkable

from sqlalchemy import TextClause, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.compliance import (
    Assessment,
    Awareness,
    AwarenessBasis,
    AwarenessSource,
    BreachCase,
    ExceptionGround,
    HarmDetermination,
    Notifiability,
    NotificationException,
)
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.tables.audit import attributed_to
from brain.tables.compliance import BreachCaseRow

#: How many cases the screen lists, newest awareness first.
CASES_SHOWN: Final = 100

#: Why a case is closed only once its assessment has been made.
CLOSING_NEEDS_A_MADE_ASSESSMENT: Final = (
    "A case is closed only once its assessment has been made: recorded, and not undetermined. "
    "Whether a breach is notifiable is a person's judgement, and a case closed without it is one "
    "whose clock nobody can say was met."
)


class BreachRefusedError(Exception):
    """A step the case cannot take, with the sentence that says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class BreachRecord:
    """One stored case: the model, and the facts about the record the model does not carry."""

    case: BreachCase
    closed_at: datetime | None
    closed_by: str | None
    updated_by: str


@dataclass(frozen=True)
class Actor:
    """Who is moving a case, at what reach, in which request."""

    principal_id: str
    ent_hash: str
    trace_id: str


def case_from(row: BreachCaseRow) -> BreachRecord:
    """The model a row holds, through the model's own checks."""
    assessment = None
    if row.assessed_at is not None:
        assert row.significant_harm is not None
        assert row.harm_decided_by is not None and row.harm_rationale_reference is not None
        assessment = Assessment(
            assessed_at=row.assessed_at,
            harm=HarmDetermination(
                significant_harm=row.significant_harm,
                decided_by=row.harm_decided_by,
                decided_at=row.assessed_at,
                rationale_reference=row.harm_rationale_reference,
            ),
            affected_count=row.affected_count,
        )
    exception = None
    if row.exception_ground is not None:
        assert row.exception_decided_by is not None and row.exception_decided_at is not None
        assert row.exception_rationale_reference is not None
        exception = NotificationException(
            ground=ExceptionGround(row.exception_ground),
            decided_by=row.exception_decided_by,
            decided_at=row.exception_decided_at,
            rationale_reference=row.exception_rationale_reference,
        )
    case = BreachCase(
        case_id=str(row.case_id),
        awareness=Awareness(
            became_aware_at=row.became_aware_at,
            basis=AwarenessBasis(row.awareness_basis),
            source=AwarenessSource(row.awareness_source),
            earliest_possible_at=row.earliest_possible_at,
            recorded_at=row.recorded_at,
            recorded_by=row.recorded_by,
            evidence_reference=row.evidence_reference,
        ),
        confirmed_at=row.confirmed_at,
        assessment=assessment,
        commission_notified_at=row.commission_notified_at,
        individuals_notified_at=row.individuals_notified_at,
        individuals_exception=exception,
    )
    return BreachRecord(
        case=case, closed_at=row.closed_at, closed_by=row.closed_by, updated_by=row.updated_by
    )


def closable(record: BreachRecord) -> bool:
    """Whether a case's assessment has been made. See `CLOSING_NEEDS_A_MADE_ASSESSMENT`."""
    made = record.case.assessment
    return made is not None and made.outcome is not Notifiability.UNDETERMINED


@runtime_checkable
class BreachCases(Protocol):
    """Opening, reading and moving breach cases."""

    async def open(self, awareness: Awareness, *, actor: Actor) -> BreachRecord: ...

    async def cases(self) -> tuple[BreachRecord, ...]: ...

    async def move(
        self, case_id: str, changes: dict[str, Any], *, actor: Actor
    ) -> BreachRecord: ...


def _setting(name: str, value: str) -> TextClause:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


async def _attribute(session: AsyncSession, actor: Actor) -> None:
    await session.execute(_setting(PRINCIPAL_SETTING, actor.principal_id))
    for statement in attributed_to(
        actor_id=actor.principal_id, ent_hash=actor.ent_hash, trace_id=actor.trace_id
    ):
        await session.execute(statement)


#: The columns a move may set, and nothing else: never the awareness, which is fixed at opening.
MOVABLE: Final = frozenset(
    {
        "assessed_at",
        "significant_harm",
        "harm_decided_by",
        "harm_rationale_reference",
        "affected_count",
        "commission_notified_at",
        "individuals_notified_at",
        "exception_ground",
        "exception_decided_by",
        "exception_decided_at",
        "exception_rationale_reference",
        "confirmed_at",
        "closed_at",
        "closed_by",
    }
)

#: Columns set once. A second value for any of them is a different history, not a correction.
SET_ONCE: Final = frozenset(
    {"commission_notified_at", "individuals_notified_at", "exception_ground", "closed_at"}
)


class StoredBreachCases:
    """`ops.breach_case`, opened, read and moved as the application role."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def open(self, awareness: Awareness, *, actor: Actor) -> BreachRecord:
        row = BreachCaseRow(
            case_id=uuid.uuid4(),
            became_aware_at=awareness.became_aware_at,
            awareness_basis=awareness.basis.value,
            awareness_source=awareness.source.value,
            earliest_possible_at=awareness.earliest_possible_at,
            recorded_at=awareness.recorded_at,
            recorded_by=awareness.recorded_by,
            evidence_reference=awareness.evidence_reference,
            updated_by=actor.principal_id,
        )
        async with self._sessions() as session, session.begin():
            await _attribute(session, actor)
            session.add(row)
            await session.flush()
            return case_from(row)

    async def cases(self) -> tuple[BreachRecord, ...]:
        async with self._sessions() as session, session.begin():
            rows = (
                (
                    await session.execute(
                        select(BreachCaseRow)
                        .order_by(BreachCaseRow.became_aware_at.desc(), BreachCaseRow.case_id)
                        .limit(CASES_SHOWN)
                    )
                )
                .scalars()
                .all()
            )
            return tuple(case_from(row) for row in rows)

    async def move(self, case_id: str, changes: dict[str, Any], *, actor: Actor) -> BreachRecord:
        """Set the columns `changes` names on an open case, checked by `checked_move` first."""
        async with self._sessions() as session, session.begin():
            await _attribute(session, actor)
            row = await session.scalar(
                select(BreachCaseRow)
                .where(BreachCaseRow.case_id == uuid.UUID(case_id))
                .with_for_update()
            )
            if row is not None:
                # Detached, so the statement below is the only write the transaction makes and
                # the trigger sees one change per column.
                session.expunge(row)
            moved = checked_move(row, changes, by=actor.principal_id)
            await session.execute(
                update(BreachCaseRow)
                .where(BreachCaseRow.case_id == uuid.UUID(case_id))
                .values(**changes, updated_by=actor.principal_id)
            )
            return moved


def checked_move(row: BreachCaseRow | None, changes: dict[str, Any], *, by: str) -> BreachRecord:
    """The case after `changes`, or the refusal: not open, a column it does not move by, a column
    set once already, or a close before the assessment was made. `row` itself is left as it was.
    """
    unknown = sorted(set(changes) - MOVABLE)
    if unknown:
        raise BreachRefusedError(f"a case does not move by {unknown}")
    if row is None or row.closed_at is not None:
        raise BreachRefusedError("that case is not open")
    closing = changes.get("closed_at") is not None
    already = sorted(k for k in SET_ONCE & set(changes) if getattr(row, k) is not None)
    if already:
        raise BreachRefusedError(f"that case already records {already}")
    after = BreachCaseRow(**{c.key: getattr(row, c.key) for c in BreachCaseRow.__table__.columns})
    for key, value in changes.items():
        setattr(after, key, value)
    after.updated_by = by
    moved = case_from(after)
    if closing and not closable(moved):
        raise BreachRefusedError(CLOSING_NEEDS_A_MADE_ASSESSMENT)
    return moved
