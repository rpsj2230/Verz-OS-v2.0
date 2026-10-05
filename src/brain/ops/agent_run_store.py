"""Where a finished agent run is written: `ops.agent_run`, in the run's own principal's name.

`brain.gate.runtime.RunLog` over `0188`'s table. It holds the SQL and decides nothing: how a run
ended is the runtime's, and what a row may hold is `brain.tables.agent_run`'s argument.

**A run that cannot be recorded does not take its answer with it.** The row is written after the
person has been answered, and a failure is logged by its class and swallowed, for the reason
`brain.ops.trace_store.A_TRACE_THAT_CANNOT_BE_WRITTEN_DOES_NOT_TAKE_THE_ANSWER_WITH_IT` gives: the
record is about the run, and losing it is a gap an operator can see, where failing the answer is a
person told nothing.

**The session states whose row it is before it writes it.** `0188`'s insert policy admits a row
whose principal is `app.principal_id`, set here in the same transaction, so this store cannot write
a run under somebody else's name even by mistake.

Task ids: M13.7.2
"""

from __future__ import annotations

import structlog
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.gate.runtime import RunRecord
from brain.tables.agent_run import AgentRunRow

log = structlog.get_logger(__name__)


def run_values(run: RunRecord) -> dict[str, object]:
    """The row a run is written as. Counts and names, nothing a run read."""
    return {
        "trace_id": run.trace_id,
        "principal_id": run.principal_id,
        "agent_id": run.agent_id,
        "lane": run.lane.value,
        "stop_reason": run.stop_reason.value,
        "turns": run.turns,
        "tool_calls": run.tool_calls,
        "tokens": run.tokens,
        "steered": run.steered,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
    }


class StoredAgentRuns:
    """`brain.gate.runtime.RunLog` over `ops.agent_run`."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def record(self, run: RunRecord) -> None:
        """Write one finished run, or log why not, and never raise."""
        try:
            async with self.sessions() as session, session.begin():
                await session.execute(
                    text("SELECT set_config('app.principal_id', :principal, true)"),
                    {"principal": run.principal_id},
                )
                await session.execute(insert(AgentRunRow).values(**run_values(run)))
        except Exception as exc:
            log.warning("agent_run.unrecorded", trace_id=run.trace_id, error=type(exc).__name__)
