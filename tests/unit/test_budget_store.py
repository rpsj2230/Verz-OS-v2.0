"""Budget versions held by a table that refuses every edit, and read back as the domain's history.

Two halves. Without a server: the stored row becomes a `BudgetRow` through its own checks, and a
version that does not follow is refused before anything is written. With one: `0031` is run for
real in a database this file creates, every level is written and read back, and PostgreSQL is
asked what it does with an UPDATE, a DELETE, a TRUNCATE, a version that skips a number, and two
writers racing for the same next version.

Subjects are named after the test that writes them, because nothing can be removed from this table
between tests, which is the property under test.

Task ids: M21.1.5
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

import psycopg
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.budget_store import append, history_of, in_force, row_from
from brain.ops.budgets import (
    BudgetError,
    BudgetKey,
    BudgetLevel,
    BudgetPeriod,
    BudgetRow,
    agent_ceilings,
    company_budget,
)
from brain.tables.budget import BudgetVersionRow
from tests.fixtures.scratch_postgres import (
    built,
    engine,
    modelled,
    present,
    run,
    secured,
    shape,
    sql,
)

#: Far outside any plausible wall clock, and ordered: each is a day after the one before.
FIRST = datetime(2999, 1, 1, tzinfo=UTC)
SECOND = FIRST + timedelta(days=1)
THIRD = SECOND + timedelta(days=1)

TABLE = "ops.budget_version"


def a_row(
    subject: str,
    *,
    level: BudgetLevel = BudgetLevel.DEPARTMENT,
    period: BudgetPeriod = BudgetPeriod.MONTH,
    version: int = 1,
    effective_from: datetime = FIRST,
    ceiling_minor: int = 100_000,
) -> BudgetRow:
    return BudgetRow(
        level=level,
        subject=subject,
        period=period,
        ceiling_minor=ceiling_minor,
        version=version,
        author="u_rupash",
        effective_from=effective_from,
        reason="set in a test",
        alert_fractions=(0.75, 0.9),
    )


# ------------------------------------------------------------------- without a server
def test_a_stored_version_becomes_the_row_it_was_written_from() -> None:
    """The producer, from a raw stored row with its enums as text and its fractions as a list.

    Delete this and `row_from` could read the period as the level or drop the alert fractions,
    and every test built from a `BudgetRow` would still pass."""
    stored = BudgetVersionRow(
        level="agent",
        subject="a_sentinel",
        period="run",
        ceiling_minor=250,
        version=3,
        author="u_rupash",
        effective_from=FIRST,
        reason="lowered after a loop",
        alert_fractions=[0.5],
    )

    assert row_from(stored) == BudgetRow(
        level=BudgetLevel.AGENT,
        subject="a_sentinel",
        period=BudgetPeriod.RUN,
        ceiling_minor=250,
        version=3,
        author="u_rupash",
        effective_from=FIRST,
        reason="lowered after a loop",
        alert_fractions=(0.5,),
    )


class _Recording(AsyncSession):
    """A session whose every query answers with the same stored rows."""

    def __init__(self, stored: Sequence[BudgetVersionRow]) -> None:
        self.stored = list(stored)
        self.added: list[Any] = []

    async def execute(self, statement: Any, params: Any = None, **_: Any) -> Any:
        return _Answer(self.stored)

    def add(self, instance: Any, _warn: bool = True) -> None:
        self.added.append(instance)

    async def flush(self, objects: Sequence[Any] | None = None) -> None:
        return None


class _Answer:
    def __init__(self, rows: list[BudgetVersionRow]) -> None:
        self._rows = rows

    def scalars(self) -> _Answer:
        return self

    def all(self) -> list[BudgetVersionRow]:
        return self._rows


def _stored(row: BudgetRow) -> BudgetVersionRow:
    return BudgetVersionRow(
        level=row.level.value,
        subject=row.subject,
        period=row.period.value,
        ceiling_minor=row.ceiling_minor,
        version=row.version,
        author=row.author,
        effective_from=row.effective_from,
        reason=row.reason,
        alert_fractions=list(row.alert_fractions),
    )


def test_a_version_that_does_not_go_forwards_is_refused_before_anything_is_written() -> None:
    """The domain's words arrive before the trigger's, and nothing is added to the session.

    Delete this and `append` could write first and let PostgreSQL refuse, so the person changing a
    ceiling is told about a trigger function rather than about their version."""
    first = a_row("web", effective_from=SECOND)
    session = _Recording([_stored(first)])

    with pytest.raises(BudgetError):
        run(lambda: append(session, a_row("web", version=2, effective_from=FIRST)))
    assert session.added == []

    run(
        lambda: append(
            session, first.superseded_by(ceiling_minor=1, author="u_rupash", effective_from=THIRD)
        )
    )
    assert len(session.added) == 1


def test_a_ceiling_nobody_has_written_is_none_and_not_an_unlimited_budget() -> None:
    """No rows is no history, and the caller decides what an absent ceiling means.

    Delete this and a `history_of` that built an empty history would raise, or one that invented a
    row would hand the caller a ceiling nobody agreed to."""
    key: BudgetKey = (BudgetLevel.USER, "u_nobody", BudgetPeriod.DAY)

    assert run(lambda: history_of(_Recording([]), key)) is None
    assert run(lambda: in_force(_Recording([]), key, FIRST)) is None


# ------------------------------------------------------- what only a server can answer
@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    with built("brain_budget_store_check", "0031") as url:
        yield url


async def _append_all(url: str, rows: Sequence[BudgetRow]) -> None:
    made = engine(url)
    try:
        async with async_sessionmaker(made)() as session, session.begin():
            for row in rows:
                await append(session, row)
    finally:
        await made.dispose()


async def _history(url: str, key: BudgetKey) -> Any:
    made = engine(url)
    try:
        async with async_sessionmaker(made)() as session:
            return await history_of(session, key)
    finally:
        await made.dispose()


def test_every_budget_level_is_written_and_read_back_as_the_row_it_was(server: str) -> None:
    """A company month, a department month, a person's day and month, and an agent's run and day.

    Delete this and a level whose rows the table refuses, or reads back wrongly, is found by the
    first person given that kind of budget."""
    rows = (
        company_budget(
            company_id="co_levels", ceiling_minor=1_000_000, author="u_rupash", effective_from=FIRST
        ),
        a_row("dept_levels"),
        a_row("u_levels", level=BudgetLevel.USER, period=BudgetPeriod.DAY),
        a_row("u_levels", level=BudgetLevel.USER, period=BudgetPeriod.MONTH),
        *agent_ceilings(
            agent_id="a_levels",
            per_run_minor=500,
            per_day_minor=5_000,
            author="u_rupash",
            effective_from=FIRST,
        ),
    )
    run(lambda: _append_all(server, rows))

    assert {row.level for row in rows} == set(BudgetLevel)
    for row in rows:
        history = run(partial(_history, server, row.key))
        assert history is not None
        assert history.rows == (row,)


def test_a_superseded_ceiling_still_answers_for_the_time_it_governed(server: str) -> None:
    """Version one from the first day, version two from the second, and each instant gets its own.

    Delete this and a store that read only the latest version would judge last quarter's spend
    against this quarter's ceiling, which is the question the table exists to answer."""
    first = a_row("dept_history", ceiling_minor=100_000)
    second = first.superseded_by(ceiling_minor=60_000, author="u_rupash", effective_from=SECOND)
    run(lambda: _append_all(server, (first,)))
    run(lambda: _append_all(server, (second,)))

    async def ceilings() -> list[BudgetRow | None]:
        made = engine(server)
        try:
            async with async_sessionmaker(made)() as session:
                return [
                    await in_force(session, first.key, at)
                    for at in (FIRST - timedelta(days=1), FIRST, SECOND + timedelta(hours=1))
                ]
        finally:
            await made.dispose()

    assert run(ceilings) == [None, first, second]


def test_nobody_may_edit_or_remove_a_version_not_even_the_owner(server: str) -> None:
    """UPDATE, DELETE and TRUNCATE, each refused by the trigger to the superuser, and UPDATE refused
    to the application role by its grants before the trigger is reached.

    Delete this and a ceiling can be quietly rewritten after an overspend, leaving a history that
    says it was always what it is now."""
    run(lambda: _append_all(server, (a_row("dept_sealed"),)))

    with psycopg.connect(server, autocommit=True) as conn:
        for statement in (
            "UPDATE ops.budget_version SET ceiling_minor = 1 WHERE subject = 'dept_sealed'",
            "DELETE FROM ops.budget_version WHERE subject = 'dept_sealed'",
            "TRUNCATE ops.budget_version",
        ):
            with pytest.raises(psycopg.errors.RestrictViolation):
                conn.execute(statement)

    with psycopg.connect(server) as conn:
        conn.execute("SET ROLE brain_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "UPDATE ops.budget_version SET ceiling_minor = 1 WHERE subject = 'dept_sealed'"
            )
        conn.rollback()

    assert sql(
        server, "SELECT ceiling_minor FROM ops.budget_version WHERE subject = 'dept_sealed'"
    ) == [(100_000,)]


def _insert(url: str, subject: str, version: int, effective_from: datetime) -> None:
    sql(
        url,
        "INSERT INTO ops.budget_version (level, subject, period, ceiling_minor, version, author, "
        "effective_from) VALUES ('department', %s, 'month', 1000, %s, 'u_rupash', %s)",
        subject,
        version,
        effective_from,
    )


def test_a_version_that_does_not_follow_the_last_is_refused_at_insert(server: str) -> None:
    """Written straight to the table, past the store: a first version other than one, a version
    that skips a number, and one that takes effect no later than the last, each refused; the next
    version at a later instant is written.

    Delete this and one disordered row, which nothing can ever remove, makes that ceiling's history
    refuse to construct for good."""
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(server, "dept_order", 2, FIRST)
    _insert(server, "dept_order", 1, FIRST)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(server, "dept_order", 3, THIRD)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(server, "dept_order", 2, FIRST)
    _insert(server, "dept_order", 2, SECOND)

    assert sql(
        server, "SELECT version FROM ops.budget_version WHERE subject = 'dept_order' ORDER BY 1"
    ) == [(1,), (2,)]


def test_two_writers_racing_for_the_same_next_version_cannot_both_land(server: str) -> None:
    """Both read version one, both pass the trigger, and the unique key refuses the second when the
    first commits. The trigger cannot see an uncommitted row, so this is the half that holds.

    Delete this and the unique constraint could be dropped with the ordering test above still
    green, because that test never writes from two transactions at once."""
    first = a_row("dept_race")
    run(lambda: _append_all(server, (first,)))
    one = first.superseded_by(ceiling_minor=90_000, author="u_rupash", effective_from=SECOND)
    other = first.superseded_by(ceiling_minor=80_000, author="u_aaron", effective_from=THIRD)

    async def race() -> None:
        made = engine(server)
        try:
            maker = async_sessionmaker(made)
            async with maker() as winner, maker() as loser:
                await winner.begin()
                await loser.begin()
                await append(winner, one)
                blocked = asyncio.create_task(append(loser, other))
                await asyncio.sleep(0.5)
                await winner.commit()
                with pytest.raises(IntegrityError):
                    await blocked
                await loser.rollback()
        finally:
            await made.dispose()

    run(race)
    history = run(lambda: _history(server, first.key))
    assert history is not None
    assert [row.ceiling_minor for row in history.rows] == [100_000, 90_000]


def test_row_level_security_is_on_for_the_budget_table(server: str) -> None:
    """Asked of the one table `0031` builds.

    Delete this and a table created without its ENABLE statement is found by CI only."""
    assert secured(server, (TABLE,)) == {TABLE: True}


def test_the_migration_builds_exactly_what_the_model_declares(server: str) -> None:
    """Every constraint by name and definition, every index and every column.

    Delete this and the migration and the model can disagree about a constraint's name, which is
    the thing a later migration dropping it has to get right."""
    with modelled("brain_budget_store_modelled", (TABLE,)) as from_models:
        assert shape(server, (TABLE,)) == shape(from_models, (TABLE,))


def test_the_migration_comes_down_and_goes_back_up() -> None:
    """Upgrade, downgrade and upgrade again, asking after the table and both functions each time.

    Delete this and a downgrade that left a trigger function behind makes the next upgrade fail on
    `CREATE FUNCTION`, on the day somebody is rolling a release forward again."""
    from tests.fixtures.scratch_postgres import migrate

    functions = (
        "SELECT count(*) FROM pg_proc WHERE pronamespace = 'ops'::regnamespace "
        "AND proname LIKE 'budget_version_%%'"
    )
    with built("brain_budget_store_round_trip", "0031") as url:
        assert present(url, (TABLE,)) == {TABLE}
        assert sql(url, functions) == [(2,)]
        migrate("brain_budget_store_round_trip", "downgrade", "0030")
        assert present(url, (TABLE,)) == set()
        assert sql(url, functions) == [(0,)]
        migrate("brain_budget_store_round_trip", "upgrade", "0031")
        assert present(url, (TABLE,)) == {TABLE}
