"""Where a learned rule is held, counted and promoted: `mem.learned_rule`, `mem.rule_occurrence`,
and the copy into `gate.fast_path_rule` that applies it.

The rules are `brain.memory.promotion`'s; this owns the session and decides nothing they do not, the
split `brain.gate.fast_lane` and `brain.gate.rule_store` keep.

**Counted after the answer, in a transaction of its own, and never raised.** `count_occurrence`
matches the question against the asker's department's held rules and writes one occurrence per
match, in the asker's name so `0206`'s policy can hold it to their own conversation, and logs
rather than raises whatever goes wrong. See
`brain.memory.promotion.A_SHADOW_OCCURRENCE_NEVER_SLOWS_OR_FAILS_AN_ANSWER`.

**Pressed and applied in one transaction.** `promote` reads the held rule and its occurrences,
asks `promotion.press`, moves the row, and on the last press writes the live rule in the
promoter's name with `learned_from`, so a promotion and the rule it applies commit together. The
database's checks are the second wall: a promotion by the proposer, a two-person promotion by one
person, and a press in somebody else's name are each refused by `0206` whatever wrote them.

Task ids: M39.4.2.3
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

import structlog
from sqlalchemy import or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.fast_lane import DECLARED_FIELDS, FastLaneError, FastPathRule, match_rule
from brain.memory.promotion import (
    LearnedRule,
    Pressed,
    PromotionRefusedError,
    PromotionState,
    press,
)
from brain.memory.tiers import Occurrence
from brain.ops.classification_store import Writer
from brain.tables.audit import attributed_to
from brain.tables.fast_lane import FastPathRuleRow
from brain.tables.learned_rule import LearnedRuleRow, RuleOccurrenceRow

log = structlog.get_logger(__name__)

#: Said when the database refuses a press the rules here admitted.
REFUSED_BY_THE_DATABASE: Final = "This press is not one you may make on this rule."

#: Said when the promoted rule's words are already a live rule's in its department.
ALREADY_LIVE: Final = (
    "A live rule in this department already has these words, so this one cannot be promoted."
)

_SET_PRINCIPAL: Final = "SELECT set_config('app.principal_id', :principal, true)"


def rule_of(row: LearnedRuleRow) -> FastPathRule:
    """The rule a held row proposes, validated as every live rule is."""
    return FastPathRule(**{field: getattr(row, field) for field in DECLARED_FIELDS})


def learned_of(row: LearnedRuleRow) -> LearnedRule:
    return LearnedRule(
        memory_id=row.memory_id,
        rule=rule_of(row),
        department=row.department,
        proposed_by=row.proposed_by,
        state=PromotionState(row.state),
        needs_two=row.needs_two,
        first_by=row.first_by,
        promoted_by=row.promoted_by,
    )


class StoredLearnedRules:
    """`mem.learned_rule` and `mem.rule_occurrence` over one session factory."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def hold(
        self, memory_id: str, rule: FastPathRule, *, department: str | None, proposed_by: str | None
    ) -> None:
        """Hold the rule a tier-two learning proposes. Nothing answers with it."""
        values = {field: getattr(rule, field) for field in DECLARED_FIELDS}
        async with self._sessions() as session, session.begin():
            await session.execute(
                pg_insert(LearnedRuleRow).values(
                    memory_id=memory_id,
                    department=department,
                    proposed_by=proposed_by,
                    state=PromotionState.HELD.value,
                    **values,
                )
            )

    async def held_for(self, department: str | None) -> tuple[LearnedRule, ...]:
        """The rules held, not yet promoted, that an asker in `department` would be matched by."""
        applies = (
            LearnedRuleRow.department.is_(None)
            if department is None
            else or_(LearnedRuleRow.department.is_(None), LearnedRuleRow.department == department)
        )
        statement = (
            select(LearnedRuleRow)
            .where(LearnedRuleRow.state != PromotionState.PROMOTED.value, applies)
            .order_by(LearnedRuleRow.memory_id)
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).scalars().all()
        return tuple(learned_of(one) for one in rows)

    async def learned(self, memory_id: str) -> LearnedRule | None:
        async with self._sessions() as session:
            row = await session.get(LearnedRuleRow, memory_id)
        return None if row is None else learned_of(row)

    async def occurrences(self, memory_ids: Sequence[str]) -> Mapping[str, tuple[Occurrence, ...]]:
        """Every occurrence counted for these learnings, as `tiers.Occurrence`s."""
        if not memory_ids:
            return {}
        statement = select(RuleOccurrenceRow).where(
            RuleOccurrenceRow.memory_id.in_(sorted(set(memory_ids)))
        )
        async with self._sessions() as session:
            rows = (await session.execute(statement)).scalars().all()
        found: dict[str, list[Occurrence]] = {}
        for one in rows:
            on = datetime(one.on_day.year, one.on_day.month, one.on_day.day, tzinfo=UTC)
            found.setdefault(one.memory_id, []).append(
                Occurrence(conversation_id=str(one.conversation_id), on=on)
            )
        return {key: tuple(value) for key, value in found.items()}

    async def count_occurrence(
        self,
        question: str,
        *,
        principal_id: str,
        department: str | None,
        thread_id: str,
        now: datetime,
    ) -> tuple[str, ...]:
        """The learnings this question would have used, each counted once for this conversation
        and day. Never raises. See `A_SHADOW_OCCURRENCE_NEVER_SLOWS_OR_FAILS_AN_ANSWER`."""
        try:
            conversation = uuid.UUID(thread_id)
            held = await self.held_for(department)
            if not held:
                return ()
            served = frozenset((one.rule.source, one.rule.entity) for one in held)
            try:
                found = match_rule(question, [one.rule for one in held], served=served)
            except FastLaneError:
                return ()
            if found is None:
                return ()
            used = tuple(one.memory_id for one in held if one.rule.rule_id == found.rule.rule_id)
            async with self._sessions() as session, session.begin():
                await session.execute(_principal(principal_id))
                for memory_id in used:
                    await session.execute(
                        pg_insert(RuleOccurrenceRow)
                        .values(
                            memory_id=memory_id, conversation_id=conversation, on_day=now.date()
                        )
                        .on_conflict_do_nothing()
                    )
            return used
        except Exception as exc:
            log.warning("learned_rule.occurrence_not_counted", error=type(exc).__name__)
            return ()

    async def promote(
        self, memory_id: str, *, writer: Writer, ready: bool, two: bool, now: datetime
    ) -> Pressed:
        """One press, in one transaction, applied on the last. Raises `PromotionRefusedError`."""
        async with self._sessions() as session, session.begin():
            for setting in _attributed(writer):
                await session.execute(setting)
            row = await session.get(LearnedRuleRow, memory_id, with_for_update=True)
            if row is None:
                raise PromotionRefusedError("There is no learned rule by that name.")
            learned = learned_of(row)
            # A second press is judged by the rule its first press recorded: `press` reads `two`
            # only for a held rule, and a rule waiting for its second person needs two by then.
            pressed = press(learned, by=writer.actor_id, ready=ready, two=two)
            values: dict[str, Any] = {
                "state": pressed.state.value,
                "needs_two": pressed.needs_two,
                "updated_at": now,
            }
            if learned.state is PromotionState.HELD:
                values |= {"first_by": pressed.first_by, "first_at": now}
            if pressed.promoted_by is not None:
                values |= {"promoted_by": pressed.promoted_by, "promoted_at": now}
            try:
                async with session.begin_nested():
                    await session.execute(
                        update(LearnedRuleRow)
                        .where(LearnedRuleRow.memory_id == memory_id)
                        .values(**values)
                    )
            except DBAPIError:
                # `0206`'s second wall: its checks refuse a promotion by the proposer and a
                # two-person promotion by one, and its policy a press in another's name.
                raise PromotionRefusedError(REFUSED_BY_THE_DATABASE) from None
            if pressed.state is PromotionState.PROMOTED:
                rule = {field: getattr(learned.rule, field) for field in DECLARED_FIELDS}
                try:
                    async with session.begin_nested():
                        await session.execute(
                            pg_insert(FastPathRuleRow).values(
                                **rule,
                                department=learned.department,
                                created_by=writer.actor_id,
                                learned_from=memory_id,
                            )
                        )
                except IntegrityError:
                    raise PromotionRefusedError(ALREADY_LIVE) from None
        return pressed


def _principal(principal_id: str) -> Any:
    return text(_SET_PRINCIPAL).bindparams(principal=principal_id)


def _attributed(writer: Writer) -> tuple[Any, ...]:
    return attributed_to(
        actor_id=writer.actor_id, ent_hash=writer.ent_hash, trace_id=writer.trace_id
    )


async def counted_after_answering(
    state: Any,
    question: str,
    *,
    principal_id: str,
    department: str | None,
    thread_id: str | None,
    now: datetime,
) -> tuple[str, ...]:
    """The answer route's one call, run after the response has gone. Never raises.

    No thread is no conversation to count, and no database is nowhere to count it: both are
    nothing counted. See `A_SHADOW_OCCURRENCE_NEVER_SLOWS_OR_FAILS_AN_ANSWER`.
    """
    sessions = getattr(state, "db_sessions", None)
    if not thread_id or not isinstance(sessions, async_sessionmaker):
        return ()
    return await StoredLearnedRules(sessions).count_occurrence(
        question, principal_id=principal_id, department=department, thread_id=thread_id, now=now
    )
