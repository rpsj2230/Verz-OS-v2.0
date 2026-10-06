"""The fast lane reads as `brain_fastlane`, which reads what the lane answers from and nothing more.

The pure half holds the role's name and the statement that takes it to what `0001` created and
`brain.ops.migration_policy` enforces, `0162`'s grants to the one table and the usage its name
needs, the policy check to the three statements `0162` adds and to each way of widening them, and
the fast lane to marking every read it makes and no read after it.

The database half builds PostgreSQL to head once for the module and asks the database itself, as
the role, through the product's own statement: it reads the projected records and an uploaded
table's rows, and it is refused every other table in `know`, a table in each of three other
schemas, and every write. `brain.ops.acceptance_checks_speed` proves the same on an install, with
the answer route answering an uploaded list's price on the lane.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M6.1.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from brain.api_routes import row_readers
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.fast_lane import FastPathRule, respond
from brain.knowledge.row_store import FAST_LANE_ROLE, SET_FAST_LANE_ROLE, SessionRowSource
from brain.knowledge.rows import RowQuery, is_a_fast_lane_read, read_as_the_fast_lane
from brain.ops import migration_policy
from brain.ops.migration_policy import check_file
from brain.tools.startup import build_registry
from tests.unit.test_acceptance import ROOT, at_head

MIGRATION = ROOT / "migrations" / "versions" / "0162_fast_lane_reads_uploaded_rows.py"

#: Tables in `know` the role was not given, each asked by name.
KNOW_NOT_GRANTED = ("know.item", "know.chunk", "know.classified_table")

#: A table in each of three schemas the role has no business in.
OTHER_SCHEMAS = ("gate.capability_grant", "mem.persistent", "ops.setting")

#: A write of each kind, on each table the role may read.
WRITES = (
    "INSERT INTO know.classified_row (entity, version, position, fields) "
    "VALUES ('fastlane_test', 1, 0, '{}'::jsonb)",
    "UPDATE know.classified_row SET position = position WHERE false",
    "DELETE FROM know.classified_row WHERE false",
    "INSERT INTO proj.record (source, entity, source_id, fields) "
    "VALUES ('fastlane_test', 'x', '1', '{}'::jsonb)",
    "UPDATE proj.record SET entity = entity WHERE false",
    "DELETE FROM proj.record WHERE false",
)


def migration() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("migration_0162", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------ without a database
def test_the_role_the_lane_takes_is_the_one_the_migrations_restrict() -> None:
    """Held against `brain.ops.migration_policy`, which reads every migration for grants to the
    role. Delete this and the lane can be pointed at a role nothing restricts, with every grant
    check still green about the one it no longer reads as."""
    assert FAST_LANE_ROLE == migration_policy.FAST_LANE_ROLE
    assert f"SET LOCAL ROLE {migration_policy.FAST_LANE_ROLE}" == SET_FAST_LANE_ROLE


def test_the_migration_gives_the_role_one_table_and_the_usage_its_name_needs() -> None:
    """The whole of what `0162` hands the role, as statements. Delete this and a second table
    can be added to the grant in the file that already names the first."""
    module = migration()
    assert module.GRANTS == (
        "GRANT USAGE ON SCHEMA know TO brain_fastlane",
        "GRANT SELECT ON know.classified_row TO brain_fastlane",
    )
    assert module.down_revision is not None
    assert [f for f in check_file(MIGRATION) if "fast lane" in f.rule] == []


@pytest.mark.parametrize(
    "statement",
    [
        pytest.param("GRANT SELECT ON know.classified_row, know.item TO brain_fastlane", id="two"),
        pytest.param("GRANT SELECT ON ALL TABLES IN SCHEMA know TO brain_fastlane", id="all"),
        pytest.param("GRANT SELECT, INSERT ON know.classified_row TO brain_fastlane", id="write"),
        pytest.param("GRANT SELECT ON know.classified_table TO brain_fastlane", id="table"),
        pytest.param(
            "CREATE POLICY p ON know.classified_row FOR ALL TO brain_fastlane USING (true)",
            id="policy",
        ),
    ],
)
def test_every_widening_of_the_know_grant_is_a_finding(tmp_path: Path, statement: str) -> None:
    """The allowed list names `know.classified_row` exactly, so each way past it is a finding: a
    second table beside it, the whole schema, a write, a sibling table and a writing policy.
    Delete this and the three shapes `0162` needed can be loosened to a pattern over `know`, which
    admits the document chunks the day somebody writes the grant."""
    path = tmp_path / "0199_widening.py"
    path.write_text(
        f'def upgrade():\n    pass\n\n\ndef downgrade():\n    pass\n\n\nG = ("{statement}",)\n'
    )

    assert len([f for f in check_file(path) if "fast lane" in f.rule]) == 1


def test_every_read_the_fast_lane_makes_is_marked_and_nothing_after_it_is() -> None:
    """The lane's reads carry the mark a source takes the role for, and a read made after the lane
    has answered does not, so a model's tool call is read as the application. Driven through
    `respond` with the registry's own handlers, over a stand-in source that records the mark.
    Delete this and the lane can stop marking its reads with every database test still green
    about a role the lane never asks for."""
    seen: list[bool] = []

    class Watching:
        async def rows(self, query: Any) -> list[dict[str, Any]]:
            del query
            seen.append(is_a_fast_lane_read())
            return []

    registry = build_registry(source="local", records=Watching())
    readers = row_readers(registry)
    rule = FastPathRule(
        rule_id="marked",
        template="the marked price of {sku}",
        slot="sku",
        source="local",
        entity="price_list",
        match_field="sku",
        answer_field="sell_price",
    )
    reach = EntitlementSet(
        principal_id="u_one",
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in ("read:price_list", "read:price_list.sku", "read:price_list.sell_price")
        ),
    )
    asyncio.run(
        respond("the marked price of WEB-1", rules=(rule,), readers=readers, entitlement=reach)
    )

    assert seen == [True]
    assert is_a_fast_lane_read() is False
    with read_as_the_fast_lane():
        assert is_a_fast_lane_read() is True
    assert is_a_fast_lane_read() is False


# ------------------------------------------------------------------------ a real database
@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    """One database at head for the module. Every statement here runs as the role and is rolled
    back, so they can share it."""
    with at_head("brain_fast_lane_role") as url:
        yield url


def as_the_role(url: str, statement: str) -> str | None:
    """Run one statement as the fast lane's role, through the product's own statement taking it,
    and say how it ended: None when it ran, or the SQLSTATE the database refused it with."""
    import psycopg

    with psycopg.connect(url) as conn:
        try:
            conn.execute(SET_FAST_LANE_ROLE)
            conn.execute(statement)
        except psycopg.Error as refused:
            return str(refused.sqlstate or "")
        finally:
            conn.rollback()
    return None


def who(url: str, *, marked: bool) -> list[str]:
    """Who the install's row source reads as over the application's own sessions, for a read the
    fast lane made or one it did not."""
    from brain.session import make_app_engine, make_application_sessions

    query = RowQuery(
        entity="fastlane_test",
        source="fastlane_test",
        columns=("who",),
        statement=select(func.current_user().label("who")),
        certainly_empty=False,
    )

    async def run() -> list[str]:
        from brain.db import normalise_database_url

        engine = make_app_engine(normalise_database_url(url))
        try:
            source = SessionRowSource(make_application_sessions(engine))
            if not marked:
                return [str(one["who"]) for one in await source.rows(query)]
            with read_as_the_fast_lane():
                return [str(one["who"]) for one in await source.rows(query)]
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.mark.needs_db
def test_a_marked_read_is_read_as_the_role_and_any_other_as_the_application(
    database: str,
) -> None:
    """Asked of the database, over the sessions every request is served through. Delete this and
    the source can ignore the lane's mark with every grant test still passing about a role no read
    ever takes."""
    assert who(database, marked=True) == [FAST_LANE_ROLE]
    assert who(database, marked=False) == ["brain_app"]


@pytest.mark.needs_db
def test_the_role_reads_the_projected_records_and_an_uploaded_tables_rows(database: str) -> None:
    """The positive half, which a role refused everything would fail: a row written to each table
    the lane answers from is read back as the role. Delete this and a grant can be lost with every
    refusal still passing."""
    import psycopg

    assert as_the_role(database, "SELECT 1 FROM proj.record LIMIT 1") is None
    with psycopg.connect(database) as conn:
        # Written as the owner with triggers and keys off, so the row needs no table and no
        # ledger entry: what is tested is the read that follows, as the role, in this transaction.
        conn.execute("SET LOCAL session_replication_role = replica")
        conn.execute(
            "INSERT INTO know.classified_row (entity, version, position, fields)"
            " VALUES ('fastlane_read', 1, 0, '{\"name\": \"x\"}'::jsonb)"
        )
        conn.execute(SET_FAST_LANE_ROLE)
        found = conn.execute(
            "SELECT fields->>'name' FROM know.classified_row WHERE entity = 'fastlane_read'"
        ).fetchall()
        conn.rollback()
    assert found == [("x",)]


@pytest.mark.needs_db
@pytest.mark.parametrize("table", KNOW_NOT_GRANTED)
def test_the_role_is_refused_a_know_table_it_was_not_granted(database: str, table: str) -> None:
    """`USAGE ON SCHEMA know` lets the role name the table and gives it none. Delete this and a
    grant over `know` can reach the document chunks with nothing failing but a static pattern."""
    # The table names are this module's constants, never input.
    assert as_the_role(database, f"SELECT 1 FROM {table} LIMIT 1") == "42501"  # noqa: S608


@pytest.mark.needs_db
@pytest.mark.parametrize("table", OTHER_SCHEMAS)
def test_the_role_is_refused_every_other_schema(database: str, table: str) -> None:
    """Grants, memories and settings, one in each schema the lane never answers from. Delete this
    and the role can be given usage on another schema and a table in it unnoticed."""
    # The table names are this module's constants, never input.
    assert as_the_role(database, f"SELECT 1 FROM {table} LIMIT 1") == "42501"  # noqa: S608


@pytest.mark.needs_db
@pytest.mark.parametrize("statement", WRITES)
def test_the_role_is_refused_every_write(database: str, statement: str) -> None:
    """An insert, an update and a delete on each table it may read, refused before a row is
    considered. Delete this and a writing grant is caught only by a pattern over the migration's
    text."""
    assert as_the_role(database, statement) == "42501"
