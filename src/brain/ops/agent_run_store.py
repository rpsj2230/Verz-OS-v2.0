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

**Other people's runs of one agent are read for its steward and its administrators, one agent at a
time** (needs-rupash 121, option B). `0227`'s second select policy admits a row when its agent is
the one `app.overseen_agent` names and is not a personal agent, so the route that names it has
decided who may be told, the way `app.approvable` is decided by `EntitlementSet.holds` and not by
SQL. What is read is who, when and how it ended, never a count of what was left out, and never a
word: the table holds none. See
`brain.console.agent_conversations.OTHERS_CONVERSATIONS_SAY_THAT_THEY_HAPPENED_AND_NOTHING_THEY_SAID`.

Task ids: M13.7.2, M39.11.1
"""

from __future__ import annotations

from typing import Final

import structlog
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.console.agent_conversations import OtherConversation, outcome_of
from brain.gate.runtime import RunRecord
from brain.tables.agent_run import AgentRunRow

log = structlog.get_logger(__name__)

#: The most other-people runs one agent's page lists. A bound on the page and never a total.
OTHERS_LISTED: Final = 50

#: Why a run that cannot be recorded is logged and not raised, and what that makes the table.
AN_AGENT_RUN_ROW_IS_A_COUNT_AND_NOT_AN_AUDIT_RECORD: Final = (
    "ops.agent_run holds counts and names for operating the runtime: how runs ended and what they "
    "spent. A write that fails is logged by its class and the answer stands, so a row can be "
    "missing, and the table is never the record of what an agent did. That record is the "
    "ledger's, written by triggers on the rows an action changes, and the trace's, behind its own "
    "role. Nothing may treat a missing row here as proof a run did not happen."
)


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
        """Write one finished run, or log why not, and never raise.

        See `AN_AGENT_RUN_ROW_IS_A_COUNT_AND_NOT_AN_AUDIT_RECORD`.
        """
        try:
            async with self.sessions() as session, session.begin():
                await session.execute(
                    text("SELECT set_config('app.principal_id', :principal, true)"),
                    {"principal": run.principal_id},
                )
                await session.execute(insert(AgentRunRow).values(**run_values(run)))
        except Exception as exc:
            log.warning("agent_run.unrecorded", trace_id=run.trace_id, error=type(exc).__name__)

    async def others_of(
        self, agent_id: str, *, reader_id: str, limit: int = OTHERS_LISTED
    ) -> tuple[OtherConversation, ...]:
        """Other people's runs of this agent, newest first, for a reader the route has admitted.

        The caller has decided the reader may oversee the agent; this names it to the database as
        the one agent, in this transaction, and asks for nobody else's rows than the reader's own
        are excluded here. No total and no count of what the bound left out.
        """
        async with self.sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.principal_id', :principal, true)"),
                {"principal": reader_id},
            )
            await session.execute(
                text("SELECT set_config('app.overseen_agent', :agent, true)"), {"agent": agent_id}
            )
            found = await session.execute(
                select(
                    AgentRunRow.principal_id,
                    AgentRunRow.started_at,
                    AgentRunRow.ended_at,
                    AgentRunRow.stop_reason,
                )
                .where(AgentRunRow.agent_id == agent_id, AgentRunRow.principal_id != reader_id)
                .order_by(AgentRunRow.started_at.desc())
                .limit(limit)
            )
            return tuple(
                OtherConversation(
                    principal_id=one.principal_id,
                    started_at=one.started_at,
                    ended_at=one.ended_at,
                    outcome=outcome_of(one.stop_reason),
                )
                for one in found
            )
