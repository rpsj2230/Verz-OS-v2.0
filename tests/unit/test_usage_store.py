"""A finished request's cost and its skill uses, written once, from the lane into PostgreSQL.

`brain.ops.usage_store.UsageRecorder` is handed what `brain.gate.answer.answer_lane` finished with,
so most of these run the real lane with a real executor over a scripted transport and read what
landed in a database of this file's own, as the application role. The arithmetic of a price is
`test_model_pricing`'s; the Models screen's price routes are `test_provider_routes`'.
"""

from __future__ import annotations

import asyncio
import importlib.util
import types
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from structlog.testing import capture_logs

from brain.core.lane import Lane
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.db import normalise_database_url
from brain.gate.answer import answer_lane
from brain.gate.context import Channel
from brain.gate.finish import Finished, FinishError, Origin, SkillUse
from brain.gate.model_lane import AgentRun, ModelLane
from brain.models.pricing import Price
from brain.ops.price_store import price_key, read_prices, set_price
from brain.ops.usage_store import (
    NO_DEPARTMENT,
    UsageRecorder,
    department_of,
)
from brain.session import make_session_factory
from brain.tables import skill as skill_table
from brain.tables import skill_invocation as table
from tests.fixtures.scratch_postgres import (
    add_modelled,
    drop,
    engine,
    fresh,
    migrate,
    modelled,
    run,
    shape,
    sql,
)
from tests.unit.test_agent_run_skills import a_run
from tests.unit.test_answer_lane import ACME, CLIENTS, HOURS, Rows, Sink, readers_for
from tests.unit.test_model_calls import Ladder, Scripted, executor, rung
from tests.unit.test_model_lane import CALLER, NOW, QUESTION, VISIBLE, Kept, Passages, completion
from tests.unit.test_skill_library import AGENT

MIGRATION = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0138_skill_invocation.py"
)
TABLES = ("agent.skill_invocation",)
SGD = "SGD"
TRACE = "t-usage-one"

#: The rung the scripted executor walks, and the price this file sets for it. 321 tokens in at
#: 10000 and 45 out at 20000 minor units per million is 4.11, which is 4.
PROVIDER = "anthropic"
MODEL = "anthropic-model"
PRICE = Price(input_minor=Decimal(10000), output_minor=Decimal(20000), currency=SGD)
COST = 4


def asker(department: str | None = "web") -> Principal:
    return Principal(
        id=CALLER.principal_id,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name="Lane asker",
        primary_department=department,
    )


def through_the_lane(
    *recorders: Any,
    agent: AgentRun | None = None,
    department: str | None = "web",
    trace: str = TRACE,
    finished_at: datetime = NOW,
) -> Finished:
    """One question no rule answers, through the real lane and a real executor, recorded."""
    kept = Kept()
    calls, _ = executor(Ladder((rung(PROVIDER),)), {PROVIDER: Scripted(completion())})
    asyncio.run(
        answer_lane(
            QUESTION,
            origin=Origin(trace_id=trace, principal=asker(department), channel=Channel.CONSOLE),
            recorders=(kept, *recorders),
            rules=(HOURS,),
            readers=readers_for(Rows(ACME)),
            entitlement=CALLER,
            policies={"client": CLIENTS.policy()},
            reachable_sources=("laravel",),
            sink=Sink(),
            now=NOW,
            clock=lambda: finished_at,
            model=ModelLane(search=Passages(VISIBLE), model=calls, agent=agent),
        )
    )
    (finished,) = kept.seen
    return finished


# --- what the lane hands the recorder ---------------------------------------------------------


def test_the_lane_hands_the_recorders_each_skill_it_offered_a_model_by_digest() -> None:
    """A run of an agent pinned to an approved skill whose tool the caller may use finishes with
    that skill's name and digest and the agent's id; the answered call is on the usage, under the
    model its rung asked for.

    What breaks if this is deleted: the lane offers the card and the recorder is told nothing, so
    the skills screen counts no run however often the skill is used."""
    agent = a_run()
    (library,) = agent.library
    finished = through_the_lane(agent=agent)

    assert finished.agent_id == AGENT
    assert finished.skills == (SkillUse(skill_name=library.name, digest=library.digest),)
    assert finished.model_usage is not None
    assert [(one.provider, one.model) for one in finished.model_usage.answered] == [
        (PROVIDER, MODEL)
    ]


def test_a_run_that_offered_no_card_used_no_skill() -> None:
    """A detached skill and a run with no agent both finish with no skills: the use is the card
    sent, never the assignment.

    What breaks if this is deleted: every run of an agent is counted as a use of every skill it
    holds, which is the assignment list M27.15.9 says the count must never be."""
    assert through_the_lane(agent=a_run(pinned=False)).skills == ()
    assert through_the_lane().skills == ()


def test_skills_with_no_agent_are_refused_as_a_wiring_fault() -> None:
    """What breaks if this is deleted: a use is recorded under an agent nobody can name."""
    finished = through_the_lane()
    with pytest.raises(FinishError):
        Finished(
            finished.origin,
            finished.at,
            None,
            completed_at=finished.completed_at,
            entitlement_hash=finished.entitlement_hash,
            lane=Lane.ANSWER,
            tool_calls=0,
            skills=(SkillUse(skill_name="x", digest="0" * 64),),
        )


def test_a_person_with_no_department_is_charged_to_no_department() -> None:
    """The directory's department when it names one, and `NO_DEPARTMENT` for none or a blank.

    What breaks if this is deleted: a cost is dropped for a person with no department, or filed
    under a department somebody's grant matches."""
    finished = through_the_lane()
    assert department_of(finished) == "web"
    for none in (None, "  "):
        assert department_of(through_the_lane(department=none)) == NO_DEPARTMENT
    assert NO_DEPARTMENT.startswith("(")


# --- the database ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """`0034` and `0043` for the cost table, `0138` for the uses, and `ops.setting` from its model.

    Each migration is run for real after a stamp of its predecessor, because none of the three
    points at anything the stamped migrations built. `ops.setting` is built from the model rather
    than through `0004`, whose later triggers need the audit ledger; what is under test there is
    the price store's statement, which needs the table's shape and nothing else.
    """
    name = "brain_test_m27125_usage_store"
    scratch = fresh(name)
    try:
        migrate(name, "stamp", "0024")
        migrate(name, "upgrade", "0025")
        migrate(name, "stamp", "0033")
        migrate(name, "upgrade", "0034")
        migrate(name, "stamp", "0042")
        migrate(name, "upgrade", "0043")
        migrate(name, "stamp", "0118")
        migrate(name, "upgrade", "0138")
        add_modelled(scratch, ("ops.setting",))
        sql(scratch, "GRANT SELECT ON ops.setting TO brain_app")
        yield scratch
    finally:
        drop(name)


@pytest.fixture
def empty(database: str) -> str:
    sql(database, "TRUNCATE ops.spend_actual, agent.skill_invocation, ops.setting")
    return database


def app_engine(url: str) -> AsyncEngine:
    """An engine whose every connection is the application role, so the policies apply."""
    return create_async_engine(
        normalise_database_url(url),
        poolclass=NullPool,
        connect_args={"options": "-c role=brain_app"},
    )


def priced(url: str, *prices: tuple[str, str, Price]) -> None:
    """Prices set as an administrator would, through the store's own statement."""

    async def go() -> None:
        made = engine(url)
        try:
            async with make_session_factory(made)() as session:
                for provider, model, price in prices:
                    await set_price(session, provider, model, price, by="u_admin")
                await session.commit()
        finally:
            await made.dispose()

    run(go)


def recording(
    url: str, work: Callable[[UsageRecorder], Any], currency: str = SGD
) -> Sequence[Mapping[str, Any]]:
    """Run `work` with a recorder over the application role, and hand back what it logged."""

    async def go() -> None:
        made = app_engine(url)
        try:
            recorder = UsageRecorder(make_session_factory(made), currency=lambda: currency)
            outcome = work(recorder)
            if asyncio.iscoroutine(outcome):
                await outcome
        finally:
            await made.dispose()

    with capture_logs() as logged:
        run(go)
    return logged


def costs(url: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT trace_id, principal_id, department, agent_id, model, lane, cost_minor, at "
        "FROM ops.spend_actual ORDER BY at",
    )


def test_a_model_call_is_metered_once_however_often_its_request_is_recorded(empty: str) -> None:
    """**A call is metered once (W3.5).** A question a model answered, recorded by the recorder
    the lane hands it to and then twice more, leaves one cost: its trace, its person, their
    department, the agent, the rung's model, the answer lane, the price's figure and the instant
    it finished.

    What breaks if this is deleted: a recorder retried or run twice doubles the agent's cost, or
    the cost lands under the response's model name and misses every report by model."""
    priced(empty, (PROVIDER, MODEL, PRICE))
    finished = through_the_lane(agent=a_run())

    async def thrice(recorder: UsageRecorder) -> None:
        for _ in range(3):
            await recorder.finished(finished)

    logged = recording(empty, thrice)

    assert costs(empty) == [(TRACE, CALLER.principal_id, "web", AGENT, MODEL, "answer", COST, NOW)]
    assert [one["event"] for one in logged].count("spend.already_recorded") == 2


def test_a_second_request_under_a_trace_it_shares_is_costed_as_its_own(empty: str) -> None:
    """A caller may propose its own trace id, so two requests can carry one. They finished at two
    instants, and each is costed.

    What breaks if this is deleted: the once-only key narrows to the trace, and a caller keeps
    every later request out of their budget by reusing one id."""
    priced(empty, (PROVIDER, MODEL, PRICE))
    first = through_the_lane()
    second = through_the_lane(finished_at=NOW + timedelta(seconds=5))

    async def both(recorder: UsageRecorder) -> None:
        await recorder.finished(first)
        await recorder.finished(second)

    recording(empty, both)

    assert [row[0] for row in costs(empty)] == [TRACE, TRACE]


def test_a_call_to_an_unpriced_model_leaves_no_cost_and_names_the_model_in_the_log(
    empty: str,
) -> None:
    """No price, and a price in another currency, each leave no row and say which provider and
    model in the log; the test above is the sibling that is costed.

    What breaks if this is deleted: an install nobody priced records every request at nought, and
    the agent page draws 0.00 as what the agent cost."""
    finished = through_the_lane()
    logged = recording(empty, lambda recorder: recorder.finished(finished))
    priced(empty, (PROVIDER, MODEL, PRICE))
    elsewhere = recording(empty, lambda recorder: recorder.finished(finished), currency="EUR")

    assert costs(empty) == []
    for events in (logged, elsewhere):
        (unpriced,) = [one for one in events if one["event"] == "spend.unpriced"]
        assert unpriced["models"] == [f"{PROVIDER}/{MODEL}"]


def test_a_person_with_no_department_is_costed_under_no_department(empty: str) -> None:
    """What breaks if this is deleted: the cost of everybody the directory gave no department is
    dropped, and every total the owner reads is short with nothing saying so."""
    priced(empty, (PROVIDER, MODEL, PRICE))
    finished = through_the_lane(department=None)
    recording(empty, lambda recorder: recorder.finished(finished))

    assert [row[2] for row in costs(empty)] == [NO_DEPARTMENT]


def test_a_run_that_used_a_skill_leaves_one_invocation_row(empty: str) -> None:
    """**M27.15.9.** The lane runs an agent whose pinned skill it offers, the recorder it hands the
    request to writes the use, and writing it again is nothing: one row naming the request, the
    person, the agent, the skill, its digest and when. A run whose skill is detached writes none.

    What breaks if this is deleted: the skills screen's count of runs stays empty however often
    a skill is used, or counts one run twice."""
    agent = a_run()
    (library,) = agent.library
    # One engine for the lane's own recording and the repeat, each on a loop of its own; the
    # pool keeps no connection, so nothing crosses from one loop to the next.
    made = app_engine(empty)
    recorder = UsageRecorder(make_session_factory(made), currency=lambda: SGD)
    try:
        used = through_the_lane(recorder, agent=agent)
        run(lambda: recorder.finished(used))
        through_the_lane(recorder, agent=a_run(pinned=False), trace="t-detached")
    finally:
        run(made.dispose)

    assert sql(
        empty,
        "SELECT trace_id, principal_id, agent_id, skill_name, digest, used_at "
        "FROM agent.skill_invocation",
    ) == [(TRACE, CALLER.principal_id, AGENT, library.name, library.digest, NOW)]


def test_the_price_of_each_model_is_merged_into_its_providers_one_row(empty: str) -> None:
    """Two models of one provider priced one after the other both hold, a price set again is the
    new one, and the provider has one live row under its key.

    What breaks if this is deleted: the upsert overwrites the provider's row, and pricing a second
    model silently unprices the first."""
    cheaper = Price(input_minor=Decimal("0.075"), output_minor=Decimal("0.3"), currency=SGD)
    priced(
        empty, (PROVIDER, MODEL, PRICE), (PROVIDER, "haiku", PRICE), (PROVIDER, "haiku", cheaper)
    )

    async def read(session: AsyncSession) -> dict[tuple[str, str], Price]:
        return await read_prices(session)

    async def go() -> dict[tuple[str, str], Price]:
        made = app_engine(empty)
        try:
            async with make_session_factory(made)() as session:
                return await read(session)
        finally:
            await made.dispose()

    assert run(go) == {(PROVIDER, MODEL): PRICE, (PROVIDER, "haiku"): cheaper}
    assert sql(empty, "SELECT key, value_type FROM ops.setting") == [(price_key(PROVIDER), "json")]


# --- the table ---------------------------------------------------------------------------------


def migration_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0138", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_builds_the_table_exactly_as_the_model_declares_it(database: str) -> None:
    """Constraints, indexes and columns read back from two catalogues, and the widths the migration
    copies held to the model's.

    What breaks if this is deleted: the migration's unique key or digest check drifts from the
    model's, and the first use is refused inside the lane's `finally`."""
    with modelled("brain_test_m27125_skill_invocation_model", TABLES) as from_model:
        assert shape(database, TABLES) == shape(from_model, TABLES)
    copied = migration_module()
    assert copied.DIGEST_PATTERN == table.DIGEST_PATTERN
    assert copied.TRACE_ID_CHARS == table.TRACE_ID_CHARS
    assert (copied.AGENT_ID_CHARS, copied.NAME_CHARS, copied.DIGEST_CHARS) == (
        skill_table.AGENT_ID_CHARS,
        skill_table.NAME_CHARS,
        skill_table.DIGEST_CHARS,
    )


@pytest.mark.parametrize(
    "statement",
    ["UPDATE agent.skill_invocation SET agent_id = 'x'", "DELETE FROM agent.skill_invocation"],
)
def test_the_application_may_read_and_append_a_use_and_never_change_or_remove_one(
    empty: str, statement: str
) -> None:
    """Row-level security is on, and the role the application connects as may insert and read a
    use and is refused an edit or a removal by the server.

    What breaks if this is deleted: a later grant widens the table, and how often a skill was used
    becomes a figure anybody holding the application's credentials can rewrite."""
    assert sql(
        empty, "SELECT relrowsecurity FROM pg_class WHERE oid = 'agent.skill_invocation'::regclass"
    ) == [(True,)]
    with psycopg.connect(empty, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute(
            "INSERT INTO agent.skill_invocation "
            "(trace_id, principal_id, agent_id, skill_name, digest, used_at) "
            "VALUES ('t', 'p', 'a', 's', %s, now())",
            ("0" * 64,),
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(statement)
        assert conn.execute("SELECT count(*) FROM agent.skill_invocation").fetchone() == (1,)


def test_a_process_with_a_database_installs_the_usage_recorder_on_the_answer_path() -> None:
    """What breaks if this is deleted: the recorder is written and installed nowhere, and nothing
    writes a cost again with every test above still green."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from brain.app import request_recorders_for

    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker()
    found = [one for one in request_recorders_for(sessions) if isinstance(one, UsageRecorder)]
    assert len(found) == 1
    assert found[0].sessions is sessions
