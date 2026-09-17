"""The default ladder written into PostgreSQL, followed to its rows, its ledger entries and a plan.

Against a database built through the migrations that ship, to `0059`, connected as the application
role so the table's policy applies, which is how `brain.app.lifespan` and the setup route write it.
Each test reads the rows as the superuser, the ledger as `AuditEntry`s with the chain verified, and
the behaviour through the functions that consume the rows: the Routing screen's own statement and
the executor's assembly. **Skips without a server.**

Task ids: none
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.ledger import AuditChain
from brain.audit.record import RoutingChange
from brain.firstrun import GRANTED_BY
from brain.models.adapter import SdkDriver
from brain.models.assembly import HOSTED_PROFILE, assemble
from brain.models.default_ladder import DEFAULT_TIERS, LadderWritten, default_ladder
from brain.ops.default_ladder_store import SessionLadderWriter
from brain.ops.model_service import SessionLadder
from brain.routing_routes import live_rungs
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_console_control_audit import recorder, seen, summary, through_0059, wanted
from tests.unit.test_credential_writes import entries
from tests.unit.test_model_calls import Scripted, ok

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
FAR_OFF = datetime(2999, 1, 1, tzinfo=UTC)

TRACE = "startup.reconcile.0123456789abcdef"


def as_application[T](
    url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]
) -> T:
    """One piece of work over a session factory connected as the application role."""

    async def go() -> T:
        built = app_engine(url)
        try:
            return await work(make_session_factory(built))
        finally:
            await built.dispose()

    return run(go)


def write(url: str, provider: str, trace_id: str = TRACE) -> LadderWritten:
    async def work(sessions: async_sessionmaker[AsyncSession]) -> LadderWritten:
        return await SessionLadderWriter(sessions).write(
            provider, actor=GRANTED_BY, trace_id=trace_id
        )

    return as_application(url, work)


#: Every live rung, as the superuser reads it. A literal, so no statement here is assembled.
LIVE = (
    "SELECT tier, position, role, deployment_id, provider, model, attempts, timeout_seconds, "
    "max_concurrency, enabled, scope FROM ops.routing_rung WHERE deleted_at IS NULL ORDER BY tier"
)


def live(url: str) -> list[tuple[object, ...]]:
    return sql(url, LIVE)


def test_the_defaults_are_written_once_each_row_recorded_as_added_by_first_run() -> None:
    """**The routing write, followed to the row and the ledger.** The first write puts one row per
    default tier into `ops.routing_rung`, every column as `default_ladder` says, and `0059`'s
    trigger appends one `routing` entry per row, `added`, naming first run as the actor rather than
    the database role marked inferred, under the trace the start supplied. A second write, for
    another provider, finds the ladder held, writes nothing and appends nothing, and the chain
    verifies.

    Delete this and a default ladder can be written twice, written with no record of who wrote it,
    or written over a ladder an administrator already holds, and nothing that reads the table
    would say so."""
    with through_0059("brain_default_ladder_written") as url:
        first = write(url, "anthropic")
        again = write(url, "moonshot", trace_id="startup.reconcile.fedcba9876543210")
        rows = live(url)
        ids = [str(one) for (one,) in sql(url, "SELECT id FROM ops.routing_rung ORDER BY tier")]
        found = seen(url, "routing")
        chain = entries(url)

    assert (first, again) == (LadderWritten.WRITTEN, LadderWritten.HELD)
    expected: list[tuple[object, ...]] = sorted(
        (
            one.tier.value,
            one.position,
            one.role.value,
            one.deployment_id,
            one.provider,
            one.model,
            one.attempts,
            one.timeout_seconds,
            one.max_concurrency,
            True,
            {"clauses": []},
        )
        for one in default_ladder("anthropic")
    )
    assert [(*row[:7], float(str(row[7])), *row[8:]) for row in rows] == expected
    assert sorted(summary(found), key=str) == sorted(
        wanted(
            *(
                (GRANTED_BY, recorder().routing(rung_id=rung_id, change=RoutingChange.ADDED))
                for rung_id in ids
            )
        ),
        key=str,
    )
    assert {one.trace_id for one in found} == {TRACE}
    assert AuditChain(chain).verify() is None


def test_a_ladder_somebody_emptied_is_not_refilled() -> None:
    """**A retirement is a decision.** Once the defaults were written and every rung retired, the
    table's policy shows the application no rung, and the ledger still holds the routing entries,
    so a later write finds the ladder emptied and writes nothing.

    Positive sibling: `test_the_defaults_are_written_once_each_row_recorded_as_added_by_first_run`.

    Delete this and every restart puts back the ladder an administrator took out, which is how an
    install that was stopped from sending text to a provider starts sending it again."""
    with through_0059("brain_default_ladder_emptied") as url:
        assert write(url, "anthropic") is LadderWritten.WRITTEN
        sql(url, "UPDATE ops.routing_rung SET deleted_at = now()")
        refilled = write(url, "anthropic", trace_id="startup.reconcile.1111222233334444")
        remaining = live(url)
        added = [one for one in seen(url, "routing") if dict(one.details)["change"] == "added"]

    assert refilled is LadderWritten.EMPTIED
    assert remaining == []
    assert len(added) == len(DEFAULT_TIERS)


def test_the_written_ladder_is_what_the_routing_screen_lists_and_the_executor_calls() -> None:
    """**The behaviour.** The rows are listed by the Routing screen's own statement, read back by
    the executor's ladder as the application role, and assembled under the hosted profile with the
    provider's key held into a chain every default tier answers from.

    Delete this and the defaults can be rows that a screen shows and no call can plan from, which
    is the fresh install that still answers "no rung names this provider"."""

    async def work(sessions: async_sessionmaker[AsyncSession]) -> tuple[int, set[str]]:
        writer = SessionLadderWriter(sessions)
        assert await writer.write("openai", actor=GRANTED_BY, trace_id=TRACE) is (
            LadderWritten.WRITTEN
        )
        async with sessions() as session:
            listed = len((await session.execute(live_rungs(100))).scalars().all())
        state = await SessionLadder(sessions).current(FAR_OFF)
        assembly = assemble(
            state.rungs,
            profile=HOSTED_PROFILE,
            switched_off=state.switched_off,
            held=frozenset({"openai"}),
            drivers={"openai": SdkDriver(provider="openai", transport=Scripted(ok()))},
        )
        return listed, {one.tier.value for one in assembly.answering}

    with through_0059("brain_default_ladder_behaviour") as url:
        listed, answering = as_application(url, work)

    assert listed == len(DEFAULT_TIERS)
    assert answering == {tier.value for tier in DEFAULT_TIERS}


def test_two_starts_writing_at_once_write_one_ladder() -> None:
    """Two processes starting together each ask for the defaults, and the lock serialises them:
    one writes, the other finds the ladder held, and there is one row per tier.

    Delete this and two replicas starting at once can both find an empty ladder, and the second
    insert is refused by the unique live position and raises at start."""

    async def work(sessions: async_sessionmaker[AsyncSession]) -> list[LadderWritten]:
        writer = SessionLadderWriter(sessions)
        return list(
            await asyncio.gather(
                writer.write("anthropic", actor=GRANTED_BY, trace_id=TRACE),
                writer.write("anthropic", actor=GRANTED_BY, trace_id=TRACE),
            )
        )

    with through_0059("brain_default_ladder_race") as url:
        outcomes = as_application(url, work)
        rows = live(url)

    assert sorted(outcomes) == sorted([LadderWritten.WRITTEN, LadderWritten.HELD])
    assert len(rows) == len(DEFAULT_TIERS)
