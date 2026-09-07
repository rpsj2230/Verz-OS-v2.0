"""The source that runs a compiled statement, held to what it must not add to one.

Everything about what may come back was decided by `compile_row_query` under the caller's
entitlements. This runs the statement. The failure it could introduce is not a wrong answer,
it is a second opinion: a filter, a limit or an ordering appended here would be a permission
decision taken by a module that holds a connection and does not know whose reach it is running
under.

Driven against a stand-in session rather than a database. There is no PostgreSQL on this
machine, and what these assert is what the source does with the statement it was handed, which
needs no server to establish.

Task ids: none
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from sqlalchemy import select

from brain.knowledge.row_store import (
    SOURCE_RUNS_THE_STATEMENT_AND_DECIDES_NOTHING,
    SessionRowSource,
)
from brain.knowledge.rows import RowQuery, RowSource


class Recorded:
    """What one execution was asked to run, and what it hands back."""

    def __init__(self, rows: Sequence[Mapping[str, Any]] = ()) -> None:
        self.statements: list[Any] = []
        self.rows = rows
        self.closed = 0
        self.committed = 0

    # --- the async session surface the source actually touches -------------------
    async def execute(self, statement: Any) -> Recorded:
        self.statements.append(statement)
        return self

    def mappings(self) -> Recorded:
        return self

    def all(self) -> Sequence[Mapping[str, Any]]:
        return self.rows

    async def commit(self) -> None:
        self.committed += 1

    async def __aenter__(self) -> Recorded:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.closed += 1


class Sessions:
    """A factory, so the source's own lifetime handling is what is under test."""

    def __init__(self, session: Recorded) -> None:
        self.session = session
        self.opened = 0

    def __call__(self) -> Recorded:
        self.opened += 1
        return self.session


def query() -> RowQuery:
    """A compiled query object carrying a statement this test can recognise."""
    return RowQuery(
        entity="ticket",
        source="laravel",
        columns=("subject",),
        statement=select(1),
        certainly_empty=False,
    )


def test_the_source_runs_exactly_the_statement_it_was_given() -> None:
    """**The property the module exists to keep.**

    Everything about what may come back was decided by `compile_row_query` under the caller's
    entitlements. A source that appended a filter, a limit or an ordering would be forming a
    second opinion about a permission question, from a module that holds a connection and does
    not know whose reach it is running under.

    Asserted by identity rather than by comparing rendered SQL: the object handed to
    `execute` is the object the compiler built, so nothing was wrapped, rebuilt or added to on
    the way.

    Delete this and a `.limit(1000)` appears here for safety, and the safety it buys is a
    caller silently receiving fewer rows than they asked for and no way to tell."""
    session = Recorded()
    sessions = Sessions(session)
    compiled = query()

    asyncio.run(SessionRowSource(sessions).rows(compiled))  # type: ignore[arg-type]

    assert len(session.statements) == 1
    assert session.statements[0] is compiled.statement


def test_rows_come_back_keyed_by_name_and_not_by_position() -> None:
    """`read_rows` looks its columns up by name. A positional result would make the record
    depend on the order the projection happened to compile in, which is stable today and is
    not a thing anybody should have to rely on.

    Delete this and the source can hand back tuples, which fail at the point a record is
    built rather than here, with an error about a missing key."""
    session = Recorded([{"entity": "ticket", "id": "t_1", "subject": "Form broken"}])

    got = asyncio.run(SessionRowSource(Sessions(session)).rows(query()))  # type: ignore[arg-type]

    assert got == [{"entity": "ticket", "id": "t_1", "subject": "Form broken"}]
    assert isinstance(got[0], dict)


def test_a_read_takes_one_session_and_gives_it_back() -> None:
    """A session held across reads is a transaction held across reads, and two callers sharing
    one would see each other's uncommitted work.

    The factory is called once per read and the context manager exits, so the pool's checkout
    is as short as the statement.

    Delete this and a session can be held on the instance, which works in a test and holds a
    connection open for the life of the process in production."""
    session = Recorded()
    sessions = Sessions(session)
    source = SessionRowSource(sessions)  # type: ignore[arg-type]

    asyncio.run(source.rows(query()))
    asyncio.run(source.rows(query()))

    assert sessions.opened == 2
    assert session.closed == 2


def test_a_read_commits_nothing() -> None:
    """Nothing is written, so nothing is committed. The context manager rolls back on the way
    out, which for a read is the cheapest correct thing and means a statement that somehow
    modified something could not persist it.

    Delete this and a `commit()` is added because it looks tidy, and the one statement that
    should never have been able to write becomes able to."""
    session = Recorded()

    asyncio.run(SessionRowSource(Sessions(session)).rows(query()))  # type: ignore[arg-type]

    assert session.committed == 0


def test_the_source_satisfies_the_protocol_it_is_written_against() -> None:
    """Structural rather than nominal: `RowSource` is a `Protocol`, so nothing inherits from
    it and nothing checks at import that this matches.

    Both halves matter. The name has to be `rows`, and it has to be awaitable, because the
    protocol became awaitable on 2026-09-07 precisely so an implementation could use the
    application's own pool.

    Delete this and a rename or a stray `def` in place of `async def` is found by mypy if
    somebody runs it and by nothing at all if they do not."""
    assert hasattr(SessionRowSource, "rows")
    assert inspect.iscoroutinefunction(SessionRowSource.rows)

    taken = list(inspect.signature(SessionRowSource.rows).parameters)
    assert taken == ["self", "query"]

    protocol = inspect.signature(RowSource.rows)
    assert list(protocol.parameters) == ["self", "query"]


def test_the_module_says_why_it_adds_nothing_to_a_statement() -> None:
    """The rule a reviewer must not break gets a named constant stating it in words, which is
    how it survives the person who wrote it.

    The phrase asserted is the argument rather than a word that could appear anywhere: what
    somebody about to add a `LIMIT` needs to read is why the limit is not theirs to add.

    Delete this and the constant becomes a paragraph somebody trims."""
    assert "second opinion about a permission question" in (
        SOURCE_RUNS_THE_STATEMENT_AND_DECIDES_NOTHING
    )
    assert "does not know whose reach" in SOURCE_RUNS_THE_STATEMENT_AND_DECIDES_NOTHING


@pytest.mark.parametrize("forbidden", ["limit", "where", "order_by", "filter", "scope"])
def test_the_source_holds_no_method_that_could_narrow_a_statement(forbidden: str) -> None:
    """The structural half of the constant above. A rule saying "do not add a filter" holds
    until somebody needs one; a class with nowhere to put one is a different kind of promise.

    Parametrised so the failure names which of the five arrived.

    Delete this and the module can grow a `with_limit` that every caller then has to remember
    not to use."""
    assert not hasattr(SessionRowSource, forbidden)
