"""`0069` against a real server: the run record granted to read and not to write, and the two item
reads that return what `know.item`'s policy withholds from a load with no principal.

Two databases built through the migrations that ship: one stopped at `0064`, which is the state a
staging install was in when four console screens failed, and one upgraded through `0069`. Every
statement runs as `brain_app`, which is what the application's sessions run as, and the route
statements are the routes' own, executed rather than restated.

Every test with a database skips without `DATABASE_URL`, and CI always sets it.

Task ids: M27.9.7
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.estate_routes import retrievable_items
from brain.knowledge.item import RETRIEVABLE_STATES
from brain.mine_routes import items_stewarded, principal_setting
from tests.fixtures.scratch_postgres import drop, engine, fresh, migrate, run, sql

MIGRATION = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0069_application_reads.py"
)

#: Rows written as the database owner: a company item, a department draft, a personal item, and an
#: archived one no read may return.
ITEMS: tuple[tuple[str, str, str, str | None, str], ...] = (
    ("kb.company", "u_c", "company", None, "published"),
    ("kb.draft", "u_a", "department", "web", "draft"),
    ("kb.personal", "u_b", "personal", None, "published"),
    ("kb.retired", "u_b", "company", None, "archived"),
)


def the_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0069", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def built(database: str, *, through_0069: bool) -> Iterator[str]:
    """`ops.control_run` from `0025` and `know.item` from `0040`, stamped at `0064`, and `0069`.

    `0069` runs after a stamp of the revision it names, so the migrations between `0064` and it,
    which build tables this chain never made, are not run over a database without them."""
    scratch = fresh(database)
    try:
        migrate(database, "stamp", "0024")
        migrate(database, "upgrade", "0025")
        migrate(database, "stamp", "0039")
        migrate(database, "upgrade", "0040")
        migrate(database, "stamp", "0064")
        if through_0069:
            migrate(database, "stamp", the_migration().down_revision)
            migrate(database, "upgrade", "0069")
        sql(scratch, "INSERT INTO ops.control_run (name) VALUES ('canary_run')")
        for item_id, owner, visibility, department, state in ITEMS:
            sql(
                scratch,
                "INSERT INTO know.item (item_id, title, owner_id, visibility, department, state) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                item_id,
                f"The title of {item_id}",
                owner,
                visibility,
                department,
                state,
            )
        yield scratch
    finally:
        drop(database)


@pytest.fixture(scope="module")
def before() -> Iterator[str]:
    yield from built("brain_test_application_reads_before", through_0069=False)


@pytest.fixture(scope="module")
def after() -> Iterator[str]:
    yield from built("brain_test_application_reads_after", through_0069=True)


def as_application(url: str, statement: str, *params: object) -> list[tuple[object, ...]]:
    """One statement as `brain_app`, in a transaction rolled back afterwards."""
    with psycopg.connect(url) as conn:
        conn.execute("SET ROLE brain_app")
        try:
            return conn.execute(statement, params or None).fetchall()
        finally:
            conn.rollback()


# ------------------------------------------------------------------------ without a server
def test_the_migrations_state_list_is_the_knowledge_layers() -> None:
    """Delete this and a state added to `RETRIEVABLE_STATES` is listed by retrieval and missing
    from the library and My workspace, whose functions carry the list as SQL."""
    migration = the_migration()

    assert tuple(sorted(migration.RETRIEVABLE)) == tuple(
        sorted(one.value for one in RETRIEVABLE_STATES)
    )
    assert migration.revision == "0069"


# --------------------------------------------------------------------------- the run record
def test_the_run_record_is_refused_before_0069_and_readable_after_and_never_writable(
    before: str, after: str
) -> None:
    """Before, reading `ops.control_run` as `brain_app` is `permission denied`, which is the fault
    the staging install logged for Live runs, Scheduled jobs, Errors and Quality. After, the read
    returns the row and an insert is still refused, because the worker writes the record as the
    database owner and the application must not be able to say a control ran.

    Delete this and the grant can be dropped, or widened to the writes the policies describe."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        as_application(before, "SELECT name FROM ops.control_run")

    assert as_application(after, "SELECT name FROM ops.control_run") == [("canary_run",)]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        as_application(after, "INSERT INTO ops.control_run (name) VALUES ('canary_run')")


# ------------------------------------------------------------------------------ the library
def test_the_library_reads_every_retrievable_item_the_policy_withholds_and_never_a_title(
    after: str,
) -> None:
    """As `brain_app` with no settings, the table shows the company item alone; the library's own
    statement, executed, returns every retrievable item in reference order, bounded, with the four
    columns it places an item by.

    Delete this and the function can stop reading past the policy, or return the title, or drop
    the state list, with the route tests green over a stub that keeps the contract for it."""
    assert as_application(after, "SELECT item_id FROM know.item") == [("kb.company",)]

    async def load(limit: int) -> list[tuple[object, ...]]:
        bound = engine(after)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET LOCAL ROLE brain_app"))
                result = await session.execute(retrievable_items(limit))
                return [(tuple(result.keys()),), *(tuple(row) for row in result.all())]
        finally:
            await bound.dispose()

    columns, *rows = run(lambda: load(10))
    assert columns == (("item_id", "owner_id", "visibility", "department"),)
    assert rows == [
        ("kb.company", "u_c", "company", None),
        ("kb.draft", "u_a", "department", "web"),
        ("kb.personal", "u_b", "personal", None),
    ]
    _, *bounded = run(lambda: load(2))
    assert [row[0] for row in bounded] == ["kb.company", "kb.draft"]


# ---------------------------------------------------------------------------- My workspace
def test_what_a_person_stewards_is_read_as_them_and_is_nobody_elses(after: str) -> None:
    """The route's own two statements, executed as `brain_app`: the principal set, then the
    function. A person gets their own personal item and draft, which the table withholds from a
    load naming nobody, and never another person's; a session naming nobody gets nothing.

    Delete this and the function can be keyed to a parameter any caller names, or drop the owner
    clause, with the route tests green over a stub."""

    async def stewarded(principal: str | None) -> list[str]:
        bound = engine(after)
        try:
            async with async_sessionmaker(bound)() as session:
                await session.execute(text("SET LOCAL ROLE brain_app"))
                if principal is not None:
                    await session.execute(principal_setting(principal))
                result = await session.execute(items_stewarded(10))
                return [str(row.item_id) for row in result.all()]
        finally:
            await bound.dispose()

    assert run(lambda: stewarded("u_b")) == ["kb.personal"]
    assert run(lambda: stewarded("u_a")) == ["kb.draft"]
    assert run(lambda: stewarded(None)) == []
    assert as_application(after, "SELECT item_id FROM know.item WHERE owner_id = 'u_b'") == []
