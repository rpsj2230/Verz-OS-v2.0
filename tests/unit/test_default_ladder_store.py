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
from brain.models.default_ladder import (
    DEFAULT_TIERS,
    LadderWritten,
    default_ladder,
    earlier_default,
)
from brain.ops.default_ladder_store import SessionLadderWriter, insert_rungs
from brain.ops.model_service import SessionLadder
from brain.routing_routes import live_rungs
from brain.session import make_session_factory
from brain.tables.audit import attributed_to
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
    "max_concurrency, enabled, scope FROM ops.routing_rung WHERE deleted_at IS NULL "
    "ORDER BY tier, position"
)


def live(url: str) -> list[tuple[object, ...]]:
    return sql(url, LIVE)


def rows_of(provider: str) -> list[tuple[object, ...]]:
    """A provider's default as `LIVE` reads it back, role and all, in the same order."""
    return sorted(
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
        for one in default_ladder(provider)
    )


def read(rows: list[tuple[object, ...]]) -> list[tuple[object, ...]]:
    """`LIVE`'s rows with the timeout as a float, the way `rows_of` holds it."""
    return sorted((*row[:7], float(str(row[7])), *row[8:]) for row in rows)


def write_earlier(url: str, provider: str) -> None:
    """The rows the product wrote until 2026-09-29, written the way it wrote them: as the
    application role, attributed to first run, in one statement."""

    async def work(sessions: async_sessionmaker[AsyncSession]) -> None:
        async with sessions() as session, session.begin():
            for statement in attributed_to(actor_id=GRANTED_BY, ent_hash="", trace_id=TRACE):
                await session.execute(statement)
            await session.execute(insert_rungs(earlier_default(provider)))

    as_application(url, work)


#: The Medium step narrowed to one department's questions, which only a person does.
NARROWED = """UPDATE ops.routing_rung
SET scope = '{"clauses": [{"field": "department", "op": "eq", "value": "sales"}]}'::jsonb
WHERE tier = 'main'"""

#: One routing change as the matrix gate records it, with its status left to fill in.
CHANGE = (
    "INSERT INTO ops.routing_change (kind, proposed, status, proposed_by, decided_at) "
    "VALUES ('add', '{{}}'::jsonb, '{status}', 'p_admin', now())"
)


def test_the_defaults_are_written_once_each_row_recorded_as_added_by_first_run() -> None:
    """**The routing write, followed to the row and the ledger.** The first write puts one row per
    default tier into `ops.routing_rung`, every column as `default_ladder` says, and `0059`'s
    trigger appends one `routing` entry per row, `added`, naming first run as the actor rather than
    the database role marked inferred, under the trace the start supplied. For Anthropic that is
    the owner's twelve steps, each with the role `0097`'s trigger derives, which is the role the
    module derives. A second write, for another provider, finds the ladder held, writes nothing
    and appends nothing, and the chain verifies.

    Delete this and a default ladder can be written twice, written with no record of who wrote it,
    or written over a ladder an administrator already holds, and nothing that reads the table
    would say so."""
    with through_0059("brain_default_ladder_written") as url:
        first = write(url, "anthropic")
        again = write(url, "moonshot", trace_id="startup.reconcile.fedcba9876543210")
        rows = live(url)
        ids = [str(one) for (one,) in sql(url, "SELECT id FROM ops.routing_rung")]
        found = seen(url, "routing")
        chain = entries(url)

    assert (first, again) == (LadderWritten.WRITTEN, LadderWritten.HELD)
    assert read(rows) == rows_of("anthropic")
    assert len(rows) == 12
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
    assert len(added) == len(default_ladder("anthropic"))


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
    assert len(rows) == len(default_ladder("anthropic"))


# --- an earlier default, completed ---------------------------------------------------------------


def test_an_untouched_earlier_default_is_completed_once_and_the_next_start_adds_nothing() -> None:
    """**The upgrade, followed to the rows and the ledger.** An install holding the two rows the
    product wrote before 2026-09-29, with only a held change on record, is completed at a start:
    the ten missing steps are added, the ladder is the owner's matrix row for row with each role
    derived by the trigger, and each new row is on the ledger as `added` by first run. The next
    start finds the ladder held and adds nothing.

    Delete this and the owner's install stays on two steps, Simple empty and no failover, however
    many times it restarts, or a start adds the ten steps again and the unique index refuses it."""
    with through_0059("brain_default_ladder_completed") as url:
        write_earlier(url, "anthropic")
        before = {str(one) for (one,) in sql(url, "SELECT id FROM ops.routing_rung")}
        sql(url, CHANGE.format(status="held"))
        first = write(url, "anthropic", trace_id="startup.reconcile.aaaa0000bbbb1111")
        again = write(url, "anthropic", trace_id="startup.reconcile.cccc2222dddd3333")
        rows = live(url)
        ids = {str(one) for (one,) in sql(url, "SELECT id FROM ops.routing_rung")}
        found = seen(url, "routing")
        chain = entries(url)

    assert (first, again) == (LadderWritten.COMPLETED, LadderWritten.HELD)
    assert read(rows) == rows_of("anthropic")
    added = [one for one in found if one.trace_id == "startup.reconcile.aaaa0000bbbb1111"]
    assert sorted(summary(added), key=str) == sorted(
        wanted(
            *(
                (GRANTED_BY, recorder().routing(rung_id=rung_id, change=RoutingChange.ADDED))
                for rung_id in ids - before
            )
        ),
        key=str,
    )
    assert len(ids - before) == 10
    assert not [one for one in found if one.trace_id == "startup.reconcile.cccc2222dddd3333"]
    assert AuditChain(chain).verify() is None


def test_an_earlier_default_somebody_changed_is_left_alone() -> None:
    """**A ladder anybody changed is theirs.** The earlier default with one number edited is left
    as it is, and so is one whose step was narrowed to one department's questions, and so is the
    earlier default on an install where a change was once applied, even though its rows look
    untouched, because an applied change is somebody having decided.

    Positive sibling: `test_an_untouched_earlier_default_is_completed_once_and_the_next_start_...`.

    Delete this and a start adds the owner's matrix behind an administrator's own ladder, which is
    the product undoing a decision at every restart."""
    with through_0059("brain_default_ladder_edited") as url:
        write_earlier(url, "anthropic")
        sql(url, "UPDATE ops.routing_rung SET timeout_seconds = 20 WHERE tier = 'main'")
        edited = write(url, "anthropic")
        edited_rows = len(live(url))
    with through_0059("brain_default_ladder_applied") as url:
        write_earlier(url, "anthropic")
        sql(url, CHANGE.format(status="applied"))
        applied = write(url, "anthropic")
        applied_rows = len(live(url))
    with through_0059("brain_default_ladder_narrowed") as url:
        write_earlier(url, "anthropic")
        sql(url, NARROWED)
        narrowed = write(url, "anthropic")
        narrowed_rows = len(live(url))

    assert (edited, edited_rows) == (LadderWritten.HELD, 2)
    assert (applied, applied_rows) == (LadderWritten.HELD, 2)
    assert (narrowed, narrowed_rows) == (LadderWritten.HELD, 2)
