"""What a finished request cost and which skills it used, written once when the lane finishes it.

`brain.ops.spend_store.record` was written and tested against a real server in September and had
no caller, so every agent's cost was 0.00 over no rows and the console had to be told nothing was
recorded (`brain.console.agent_profile.RUN_SPEND_IS_RECORDED`). A skill's use had nowhere to go at
all. This is the recorder that writes both, and it is a `brain.gate.finish.RequestRecorder` for
`brain.gate.finish`'s reason: the lane's `finally` is the one place every request ends, so a
request that called a model cannot finish without being offered to it.

**A model call is metered once, in the install's currency, from the provider's own count and the
configured price (M27.12.5).** `Finished.model_usage` carries each answered call with the model its
rung asked for, `brain.ops.price_store` holds the price an administrator set for that provider and
model, and `brain.models.pricing.cost_of` sums them exactly and rounds once. A request with any
unpriced call is not costed, and the log names the provider and the model so the Models screen's
unpriced list can be checked against it. See
`brain.models.pricing.AN_UNPRICED_CALL_IS_NOT_COSTED_AND_NEVER_COSTED_AT_NOUGHT`.

**Once per request, by a lock and a look, not by a unique index.** A unique index on
`ops.spend_actual.trace_id` narrows what the previous release may insert, which
`brain.deployment.compatibility` refuses on a table that already exists, and a key on the trace
alone would be wrong anyway: a caller may propose its own trace id, so two requests can share one,
and the second request's cost would vanish. A request is its trace and the instant the lane
finished it, which is read once per request. The write takes a transaction-scoped advisory lock on
the trace, looks for a cost under that trace and instant, and appends only when there is none, so
the recorder run twice, or two processes finishing one request, leave one row. See
`A_REQUEST_IS_COSTED_ONCE_UNDER_ITS_TRACE_AND_THE_INSTANT_IT_FINISHED`.

**A cost with no department is kept under a name that is no department, and never dropped.**
`brain.adoption` counts a question with no department nowhere, which is right for a count a
department head reads as their people's. Money is different: a cost dropped because the directory
gave a person no department is a figure missing from every total, including the unrestricted ones
the owner reads, with nothing on it saying so. `NO_DEPARTMENT` is not a department, so no
department-scoped reader's grant matches it and nobody's department is charged with it. See
`A_COST_WITH_NO_DEPARTMENT_IS_KEPT_AND_CHARGED_TO_NO_DEPARTMENT`.

**The skills a run used are written in the same session, one row each (M27.15.9).** The unique key
on `agent.skill_invocation` is new with its table, so it is the database that holds a use to one
row per request, and a second write of the same use is nothing.

**A write that fails does not take the answer with it.** The rule is
`brain.ops.question_store.A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT`,
imported rather than restated. The cost and the skills are written in separate transactions, so a
refused cost does not lose the uses, and each failure has its own log event.

What is not here: the price of a call no request owns. Every model call this product makes is made
for a request that finishes through a lane: an answer, a provider check, an automation's step.

Task ids: M27.12.5, M27.15.9, M27.15.27, M39.2.2.4
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import Select, select, text
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.context import traffic_class_for
from brain.gate.finish import Finished, SkillUse
from brain.locale import currency as install_currency
from brain.models.pricing import Costed, Price, cost_of, unpriced
from brain.ops import spend_store
from brain.ops.price_store import read_prices
from brain.ops.question_store import (
    A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT,
)
from brain.ops.spend import Actual
from brain.tables.skill_invocation import SkillInvocationRow
from brain.tables.spend import SpendActualRow

log = structlog.get_logger(__name__)

__all__ = [
    "A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT",
    "UsageRecorder",
]

# ------------------------------------------------------------------- written-down reasons

#: Why a cost is held to one row by a lock rather than an index.
A_REQUEST_IS_COSTED_ONCE_UNDER_ITS_TRACE_AND_THE_INSTANT_IT_FINISHED: Final = (
    "A request is its trace and the instant the lane finished it. The recorder locks the trace for "
    "its transaction, looks for a cost under that trace and instant, and writes only when there "
    "is none, so a recorder run twice leaves one row. A unique index on the trace would refuse "
    "the previous release's inserts during a deploy, and would drop the cost of a second request "
    "whose caller proposed the same trace id."
)

#: Why a cost with no department is kept rather than dropped.
A_COST_WITH_NO_DEPARTMENT_IS_KEPT_AND_CHARGED_TO_NO_DEPARTMENT: Final = (
    "A person the directory gave no department still spent money. Dropping their cost would leave "
    "every total short with nothing saying so, so it is kept under NO_DEPARTMENT, a name no "
    "department has and no department-scoped grant matches: only a reader of everybody's spend "
    "sees it, and no department is charged with it."
)

#: The department a cost is kept under when the directory gave the person none. Parenthesised,
#: as `brain.ops.spend.NO_AGENT` is, so it cannot be a slug any department is created under.
NO_DEPARTMENT: Final = "(no department)"

#: The advisory lock's namespace, so a lock taken here never waits on one taken elsewhere.
LOCK_NAMESPACE: Final = "ops.spend_actual"

#: Serialises every writer of one trace's cost until its transaction ends.
_LOCKED: Final = text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))")


def department_of(request: Finished) -> str:
    """The department a request's cost is charged to: the person's, or `NO_DEPARTMENT`."""
    named = request.origin.principal.primary_department
    return named.strip() if named and named.strip() else NO_DEPARTMENT


def actual_for(request: Finished, costed: Costed) -> Actual:
    """The accounting row one finished request becomes, through `Actual`'s own checks.

    Everything comes from what the gate decided: the principal, its kind and the channel's
    traffic class, the agent the lane ran, the lane whose budget it spent, and the instant it
    finished. Nothing the request supplied is read.
    """
    principal = request.origin.principal
    return Actual(
        principal_id=principal.id,
        principal_kind=principal.kind,
        traffic=traffic_class_for(request.origin.channel),
        department=department_of(request),
        agent_id=request.agent_id,
        model=costed.model,
        lane=request.lane,
        cost_minor=costed.cost_minor,
        at=request.completed_at,
        trace_id=request.origin.trace_id,
    )


def costed_already(trace_id: str, at: datetime) -> Select[tuple[Any]]:
    """Whether this request's cost is on the table: its trace, at the instant it finished."""
    return (
        select(SpendActualRow.id)
        .where(SpendActualRow.trace_id == trace_id, SpendActualRow.at == at)
        .limit(1)
    )


async def record_once(session: AsyncSession, actual: Actual) -> bool:
    """Append this request's cost unless it is there already. True when it was written.

    Does not commit; the lock is held until the caller's transaction ends, which is what makes
    the look and the write one step. See
    `A_REQUEST_IS_COSTED_ONCE_UNDER_ITS_TRACE_AND_THE_INSTANT_IT_FINISHED`.
    """
    await session.execute(_LOCKED, {"key": f"{LOCK_NAMESPACE}:{actual.trace_id}"})
    if (await session.execute(costed_already(actual.trace_id, actual.at))).first() is not None:
        return False
    await spend_store.record(session, actual)
    return True


def uses_statement(request: Finished, skills: Sequence[SkillUse]) -> Insert:
    """One row per skill the run used, and nothing for a use already written."""
    agent_id = request.agent_id or ""
    return (
        insert(SkillInvocationRow)
        .values(
            [
                {
                    "trace_id": request.origin.trace_id,
                    "principal_id": request.origin.principal.id,
                    "agent_id": agent_id,
                    "skill_name": one.skill_name,
                    "digest": one.digest,
                    "used_at": request.completed_at,
                }
                for one in skills
            ]
        )
        .on_conflict_do_nothing()
    )


class UsageRecorder:
    """The `brain.gate.finish.RequestRecorder` that writes a request's cost and its skill uses."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        currency: Callable[[], str] = install_currency,
    ) -> None:
        self.sessions = sessions
        self.currency = currency

    async def finished(self, request: Finished) -> None:
        """Write what this request cost and which skills it used, and never raise."""
        await self._cost(request)
        await self._skills(request)

    async def _cost(self, request: Finished) -> None:
        usage = request.model_usage
        if usage is None or not usage.answered:
            return
        trace_id = request.origin.trace_id
        try:
            code = self.currency()
        except Exception as exc:
            # See A_MEASUREMENT_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT.
            log.warning("spend.currency_unreadable", trace_id=trace_id, error=type(exc).__name__)
            return
        try:
            async with self.sessions() as session:
                prices: dict[tuple[str, str], Price] = await read_prices(session)
                costed = cost_of(usage.answered, prices, currency=code)
                if costed is None:
                    missing = unpriced(usage.answered, prices, currency=code)
                    log.warning(
                        "spend.unpriced",
                        trace_id=trace_id,
                        models=[f"{provider}/{model}" for provider, model in missing],
                    )
                    return
                written = await record_once(session, actual_for(request, costed))
                await session.commit()
        except Exception as exc:
            log.warning("spend.unrecorded", trace_id=trace_id, error=type(exc).__name__)
            return
        if not written:
            log.info("spend.already_recorded", trace_id=trace_id)

    async def _skills(self, request: Finished) -> None:
        if not request.skills or request.agent_id is None:
            return
        try:
            async with self.sessions() as session:
                await session.execute(uses_statement(request, request.skills))
                await session.commit()
        except Exception as exc:
            log.warning(
                "skills.unrecorded", trace_id=request.origin.trace_id, error=type(exc).__name__
            )
