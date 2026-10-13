"""How often an agent's answers cited each document: kept by the day, read over a window, written
only while the switch is on, and naming nobody.

Builds `ops.agent_item_use` through `0213` and drives it as the application role, so the policies
apply; it skips when there is no server, as every file using `tests.fixtures.scratch_postgres`
does. The first test proves the connection is the application role, because a superuser connection
bypasses every policy here.

Task ids: M39.2.3.5
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

import brain.api_routes as api_routes
from brain.db import normalise_database_url
from brain.ops.agent_item_use import (
    MAX_DOCUMENTS_PER_ANSWER,
    WINDOW_DAYS,
    StoredItemUses,
    cited_item_ids,
    window_start,
)
from brain.ops.features import AGENT_ITEM_COUNTS, FEATURES
from brain.session import make_session_factory
from brain.tables.agent_item_use import AgentItemUseRow
from tests.fixtures.scratch_postgres import drop, fresh, migrate, run, secured, sql

#: Pinned far outside any plausible wall clock, so a window is a window and not a race.
TODAY = date(2999, 6, 15)
AGENT = "web_desk"


@contextmanager
def counts(database: str) -> Iterator[str]:
    """A fresh database holding `ops.agent_item_use`, built by `0213` itself."""
    scratch = fresh(database)
    try:
        migrate(database, "stamp", "0212")
        migrate(database, "upgrade", "0213")
        yield scratch
    finally:
        drop(database)


def with_store[T](url: str, work: Callable[[StoredItemUses], Awaitable[T]]) -> T:
    from sqlalchemy.ext.asyncio import create_async_engine

    async def go() -> T:
        engine = create_async_engine(
            normalise_database_url(url),
            poolclass=NullPool,
            connect_args={"options": "-c role=brain_app"},
        )
        try:
            return await work(StoredItemUses(make_session_factory(engine)))
        finally:
            await engine.dispose()

    return run(go)


def as_app(url: str) -> psycopg.Connection[Any]:
    conn = psycopg.connect(url, autocommit=True)
    conn.execute("SET ROLE brain_app")
    return conn


def test_the_store_connects_as_the_application_role() -> None:
    """Delete this and every policy test below can pass on a superuser connection that bypasses
    row-level security entirely."""
    with counts("brain_aiu_role") as url:

        async def work(store: StoredItemUses) -> Any:
            async with store._sessions() as session:
                return tuple((await session.execute(text("SELECT current_user"))).one())

        assert with_store(url, work) == ("brain_app",)


def test_a_document_cited_twice_in_a_day_is_one_row_raised_and_a_new_day_is_a_new_row() -> None:
    """The count is per agent, document and day, and two answers at once both count: the upsert is
    one statement. Delete this and a second answer overwrites the first, or a day's rows multiply
    with the questions asked."""
    with counts("brain_aiu_upsert") as url:

        async def work(store: StoredItemUses) -> dict[str, int]:
            await store.count(AGENT, ["one", "two"], TODAY)
            await store.count(AGENT, ["one"], TODAY)
            await store.count(AGENT, ["one"], TODAY + timedelta(days=1))
            return await store.uses(AGENT, ["one", "two", "never"], today=TODAY + timedelta(days=1))

        assert with_store(url, work) == {"one": 3, "two": 1}
        assert sql(url, "SELECT count(*) FROM ops.agent_item_use") == [(3,)]


def test_a_use_outside_the_window_is_not_counted_and_another_agents_is_not_either() -> None:
    """The figure is the last thirty days of this agent. Delete this and a document drawn on a
    year ago reads as in use, or one agent's use reads as another's."""
    with counts("brain_aiu_window") as url:
        old = TODAY - timedelta(days=WINDOW_DAYS)
        sql(
            url,
            "INSERT INTO ops.agent_item_use (agent_id, item_id, day, uses) VALUES"
            " (%s, 'one', %s, 1), (%s, 'one', %s, 1), ('finance_desk', 'one', %s, 1)",
            AGENT,
            old,
            AGENT,
            window_start(TODAY),
            TODAY,
        )

        async def work(store: StoredItemUses) -> dict[str, int]:
            return await store.uses(AGENT, ["one"], today=TODAY)

        assert with_store(url, work) == {"one": 1}


def test_the_application_may_neither_delete_nor_lower_a_count_nor_start_one_above_one() -> None:
    """The grants and policies of `0213`: raised by one and nothing else. Delete this and a
    session can rewrite the report an owner decides what to prune from."""
    with counts("brain_aiu_policy") as url:
        sql(
            url,
            "INSERT INTO ops.agent_item_use (agent_id, item_id, day, uses)"
            " VALUES (%s, 'one', %s, 5)",
            AGENT,
            TODAY,
        )
        with as_app(url) as conn:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("DELETE FROM ops.agent_item_use")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("UPDATE ops.agent_item_use SET agent_id = 'other'")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute("UPDATE ops.agent_item_use SET uses = 1")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(
                    "INSERT INTO ops.agent_item_use (agent_id, item_id, day, uses)"
                    " VALUES (%s, 'two', %s, 9)",
                    (AGENT, TODAY),
                )
            conn.execute("UPDATE ops.agent_item_use SET uses = uses + 1")
        assert sql(url, "SELECT uses FROM ops.agent_item_use") == [(6,)]
        assert secured(url, ["ops.agent_item_use"]) == {"ops.agent_item_use": True}


def test_a_count_has_room_for_an_agent_a_document_a_day_and_a_number_and_nothing_else() -> None:
    """Held to the columns the argument allows: no question, person, passage or trace. Delete this
    and a column that makes the table a log of what somebody read arrives without anybody
    deciding it should."""
    assert [one.name for one in AgentItemUseRow.__table__.columns] == [
        "agent_id",
        "item_id",
        "day",
        "uses",
    ]


def test_the_counting_switch_is_declared_and_ships_off() -> None:
    """The feature is in the closed list, read by the one function that asks. Delete this and the
    counts can start being kept on every install without an administrator turning anything on."""
    assert AGENT_ITEM_COUNTS in FEATURES
    assert AGENT_ITEM_COUNTS.read_by == ("brain.ops.agent_item_use:counting_is_on",)


def test_the_documents_an_answer_cited_are_each_once_sorted_and_bounded() -> None:
    """From the records' `document_id`, which is the item id; a record with none, or a non-string,
    names no document. Delete this and two passages of one document count twice, or a malformed
    record is counted as a document."""
    records: list[dict[str, Any]] = [
        {"document_id": "b"},
        {"document_id": "a"},
        {"document_id": "b"},
        {"document_id": 7},
        {"document_id": "  "},
        {"title": "no id"},
    ]
    assert cited_item_ids(records) == ("a", "b")
    many = [{"document_id": f"d{n:03d}"} for n in range(MAX_DOCUMENTS_PER_ANSWER + 10)]
    assert len(cited_item_ids(many)) == MAX_DOCUMENTS_PER_ANSWER


def test_the_window_is_thirty_days_counting_today() -> None:
    """The first day a figure counts. Delete this and a window of thirty is thirty-one, or twenty-
    nine, with nothing saying which."""
    assert (TODAY - window_start(TODAY)).days == WINDOW_DAYS - 1


class State:
    """The application's state as `counted_citations` reads it: sessions and nothing else."""

    def __init__(self, sessions: async_sessionmaker[Any]) -> None:
        self.db_sessions = sessions


def answered_with(*documents: str) -> Any:
    records = [{"document_id": one, "document": "words"} for one in documents]
    return SimpleNamespace(composed=SimpleNamespace(payload=SimpleNamespace(records=records)))


def drive(
    url: str, monkeypatch: pytest.MonkeyPatch, *, on: bool, agent: str | None, answered: Any
) -> list[tuple[Any, ...]]:
    from sqlalchemy.ext.asyncio import create_async_engine

    async def switched(_sessions: Any) -> bool:
        return on

    monkeypatch.setattr(api_routes, "counting_is_on", switched)

    async def go() -> None:
        engine = create_async_engine(
            normalise_database_url(url),
            poolclass=NullPool,
            connect_args={"options": "-c role=brain_app"},
        )
        try:
            await api_routes.counted_citations(
                State(make_session_factory(engine)),
                agent,
                answered,
                now=datetime(2999, 6, 15, 9, 0, tzinfo=UTC),
            )
        finally:
            await engine.dispose()

    run(go)
    return sql(url, "SELECT agent_id, item_id, uses FROM ops.agent_item_use ORDER BY item_id")


def test_an_answer_adds_one_to_each_document_it_cited_only_while_the_switch_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hook the answer route calls. On: one per document, once. Off, with no agent or with an
    abstention: nothing is written. Delete this and the counts are kept on installs that did not
    ask for them, or an answer that cited nothing is counted."""
    with counts("brain_aiu_hook") as url:
        assert drive(url, monkeypatch, on=False, agent=AGENT, answered=answered_with("one")) == []
        assert drive(url, monkeypatch, on=True, agent=None, answered=answered_with("one")) == []
        assert (
            drive(url, monkeypatch, on=True, agent=AGENT, answered=SimpleNamespace(composed=None))
            == []
        )
        assert drive(
            url, monkeypatch, on=True, agent=AGENT, answered=answered_with("one", "one", "two")
        ) == [
            (AGENT, "one", 1),
            (AGENT, "two", 1),
        ]
        assert drive(url, monkeypatch, on=True, agent=AGENT, answered=answered_with("one")) == [
            (AGENT, "one", 2),
            (AGENT, "two", 1),
        ]
