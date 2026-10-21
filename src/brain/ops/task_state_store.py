"""What the records say about the runs behind a person's answers, read as that person (M40.7.6).

`StoredTaskStates.facts` takes the trace ids of the latest answers on a person's thread list and
returns, for each, the `RunFacts` `brain.member_task_state` decides from: the actions its run held
for approval (`gate.suspension`, whose `0042` policy lets the raiser read their own), what the
worker did with each once approved (`ops.operation`, keyed to the approval by `intent_ref`, and
asked for this person's operations only) and, for a failed request, the gate steps it entered
(`obs.request_telemetry.stage_ms`, asked for this person's requests only).

**Every query names the person twice**, once to row-level security (`app.principal_id`) and once in
its own `WHERE`, because `ops.operation` and `obs.request_telemetry` have read policies open to the
application role: the filter on the person is the code's, and a test holds it. Three reads in one
transaction for the whole list, never one per thread.

**Nothing is written.** The state of a run is derived each time it is asked, so there is no copy of
it to go stale, and the store has no write.

Task ids: M40.7.6
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.leash import ApprovalState
from brain.knowledge.search import PRINCIPAL_SETTING
from brain.member_task_state import HeldAction, RunFacts, lapsed
from brain.ops.idempotency import OperationState
from brain.tables.chat import RunState
from brain.tables.operation import OperationRow
from brain.tables.suspension import SuspensionRow
from brain.tables.telemetry import RequestTelemetryRow


def _as(principal_id: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(
        name=PRINCIPAL_SETTING, value=principal_id
    )


def _operation(state: str | None) -> OperationState | None:
    try:
        return None if state is None else OperationState(state)
    except ValueError:
        # A state this build does not know is a run nobody can vouch for: still going on.
        return OperationState.UNKNOWN


def _approval(state: str) -> ApprovalState:
    try:
        return ApprovalState(state)
    except ValueError:
        return ApprovalState.REJECTED


class StoredTaskStates:
    """The records behind a run's state, read for one person."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def facts(
        self,
        principal_id: str,
        answers: dict[str, RunState | None],
        now: datetime,
    ) -> dict[str, RunFacts]:
        """The facts for each trace in `answers`, a trace id mapped to its answer's run state."""
        traces = [one for one in answers if one]
        if not traces:
            return {}
        async with self._sessions() as session, session.begin():
            await session.execute(_as(principal_id))
            held = (
                await session.execute(
                    select(
                        SuspensionRow.trace_id,
                        SuspensionRow.id,
                        SuspensionRow.state,
                        SuspensionRow.expires_at,
                    ).where(
                        SuspensionRow.principal_id == principal_id,
                        SuspensionRow.trace_id.in_(traces),
                    )
                )
            ).all()
            ran: dict[str, str] = {}
            if held:
                ran = dict(
                    (
                        await session.execute(
                            select(OperationRow.intent_ref, OperationRow.state).where(
                                OperationRow.principal_id == principal_id,
                                OperationRow.intent_ref.in_([one.id for one in held]),
                            )
                        )
                    )
                    .tuples()
                    .all()
                )
            failed = [one for one, state in answers.items() if state is RunState.FAILED and one]
            stages: dict[str, tuple[str, ...]] = {}
            if failed:
                stages = {
                    trace: tuple(stage or ())
                    for trace, stage in (
                        await session.execute(
                            select(
                                RequestTelemetryRow.trace_id, RequestTelemetryRow.stage_ms
                            ).where(
                                RequestTelemetryRow.principal == principal_id,
                                RequestTelemetryRow.trace_id.in_(failed),
                            )
                        )
                    ).all()
                }
        return {
            trace: RunFacts(
                run_state=state,
                held=tuple(
                    HeldAction(
                        state=_approval(one.state),
                        lapsed=lapsed(one.expires_at, now),
                        operation=_operation(ran.get(one.id)),
                    )
                    for one in held
                    if one.trace_id == trace
                ),
                steps=stages.get(trace, ()),
            )
            for trace, state in answers.items()
            if trace
        }


def traces_of(answers: Sequence[tuple[str, RunState | None]]) -> dict[str, RunState | None]:
    """The latest answer's trace and run state per thread, as `facts` takes them."""
    return {trace: state for trace, state in answers if trace}
