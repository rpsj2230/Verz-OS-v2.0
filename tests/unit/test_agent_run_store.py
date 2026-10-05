"""`ops.agent_run` on PostgreSQL: a run is written in its own principal's name and read by them.

Over `brain.ops.agent_run_store` and `0188`, as the application role, so the row-level policies
are what is tested. Plus the widths `0188` copies, held equal to the model.

Task ids: M13.7.2
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from brain.core.lane import Lane
from brain.db import normalise_database_url
from brain.gate.runtime import RunRecord
from brain.gate.stop import StopReason
from brain.ops.agent_run_store import StoredAgentRuns, run_values
from brain.tables.agent_run import TRACE_ID_CHARS, VOCABULARY_CHARS, AgentRunRow
from tests.unit.test_tables import MIGRATION_AGENT_RUN, migration_module

#: Far from any wall clock: nothing here is about the present.
STARTED = datetime(2019, 3, 1, 9, 0, tzinfo=UTC)


def a_run(principal: str = "u_asker", stop: StopReason = StopReason.ANSWERED) -> RunRecord:
    return RunRecord(
        trace_id="t-run-store-1",
        principal_id=principal,
        agent_id="pricing_desk",
        lane=Lane.ANSWER,
        stop_reason=stop,
        turns=2,
        tool_calls=1,
        tokens=40,
        steered=0,
        started_at=STARTED,
        ended_at=STARTED + timedelta(seconds=3),
    )


def test_a_row_holds_counts_and_names_and_nothing_a_run_read() -> None:
    """The row is exactly these columns: no question, argument, result or prompt. Delete this and
    a column holding what a run read can be added to the one table with no masking in front of
    it."""
    assert set(run_values(a_run())) == {
        "trace_id",
        "principal_id",
        "agent_id",
        "lane",
        "stop_reason",
        "turns",
        "tool_calls",
        "tokens",
        "steered",
        "started_at",
        "ended_at",
    }
    assert set(run_values(a_run())) | {"id"} == set(AgentRunRow.__table__.columns.keys())


def test_the_migration_and_the_model_agree_on_the_vocabularies_and_widths() -> None:
    """`0188` writes the lane and stop-reason lists out as data; they must be today's enums, and
    its widths the model's. Delete this and a stop reason added to the loop is refused by the
    database on the first run that reaches it."""
    migration = migration_module(MIGRATION_AGENT_RUN)
    assert tuple(sorted(migration.LANES)) == tuple(sorted(one.value for one in Lane))
    assert tuple(sorted(migration.STOP_REASONS)) == tuple(sorted(one.value for one in StopReason))
    assert migration.VOCABULARY_CHARS == VOCABULARY_CHARS
    assert migration.TRACE_ID_CHARS == TRACE_ID_CHARS
    assert max(len(one.value) for one in (*Lane, *StopReason)) <= VOCABULARY_CHARS


def _as_app[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = create_async_engine(
            normalise_database_url(url),
            poolclass=NullPool,
            connect_args={"options": "-c role=brain_app"},
        )
        try:
            return await work(async_sessionmaker(engine, class_=AsyncSession))
        finally:
            await engine.dispose()

    if os.name == "nt":
        return asyncio.run(go(), loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(go())


async def _visible(sessions: async_sessionmaker[AsyncSession], reader: str) -> list[Any]:
    async with sessions() as session, session.begin():
        await session.execute(
            sa.text("SELECT set_config('app.principal_id', :p, true)"), {"p": reader}
        )
        found = await session.execute(sa.select(AgentRunRow.principal_id, AgentRunRow.stop_reason))
        return [tuple(row) for row in found]


@pytest.mark.needs_db
def test_a_run_is_written_in_its_name_and_read_only_by_its_principal() -> None:
    """**The policy, both halves.** A run is recorded for its principal and read back by them,
    and another person reading sees none of it. Delete this and a person's runs, the agents they
    used and when, are readable by everybody holding the application role."""
    from tests.unit.test_acceptance import at_head

    with at_head("brain_agent_run_store") as url:

        async def work(sessions: async_sessionmaker[AsyncSession]) -> tuple[list[Any], list[Any]]:
            await StoredAgentRuns(sessions).record(a_run())
            return await _visible(sessions, "u_asker"), await _visible(sessions, "u_other")

        own, other = _as_app(url, work)

    assert own == [("u_asker", "answered")]
    assert other == []


@pytest.mark.needs_db
def test_a_row_naming_somebody_else_is_refused_by_the_database() -> None:
    """The insert policy admits only a row in the session's own name. Delete this and the store,
    or anything else holding the application role, can write a run under any name."""
    from tests.unit.test_acceptance import at_head

    with at_head("brain_agent_run_store_refused") as url:

        async def work(sessions: async_sessionmaker[AsyncSession]) -> list[Any]:
            async with sessions() as session, session.begin():
                await session.execute(
                    sa.text("SELECT set_config('app.principal_id', 'u_mallory', true)")
                )
                try:
                    await session.execute(sa.insert(AgentRunRow).values(**run_values(a_run())))
                except sa.exc.DBAPIError:
                    await session.rollback()
                    return ["refused"]
            return ["written"]

        outcome = _as_app(url, work)

    assert outcome == ["refused"]


def test_a_run_that_cannot_be_recorded_does_not_raise() -> None:
    """A store that cannot be reached is logged and swallowed, because the record is about a run
    whose person has already been answered. Delete this and an outage of one table fails every
    agent answer."""

    def broken() -> Any:
        msg = "no database"
        raise OSError(msg)

    asyncio.run(StoredAgentRuns(broken).record(a_run()))  # type: ignore[arg-type]
