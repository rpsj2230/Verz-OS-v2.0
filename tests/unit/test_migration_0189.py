"""`0189` against PostgreSQL: every agent from before it answers everywhere, and a new one nowhere.

One scratch database taken to head, stepped back to the revision `0189` revises, given an agent
written as `install_store` wrote one before this release, and stepped forward again. The step back
names `0189`'s own `down_revision` rather than a number written here, so when the coordinator
re-points it at `0188` this test steps over `0188` too and needs no edit.

Task ids: M13.7.4, M13.7.2
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import pytest

#: Far from any wall clock: nothing here is about the present.
AT = datetime(2019, 3, 1, 9, 0, tzinfo=UTC)
KEY = "a-key-for-the-0189-fixture"
AGENT = "older_helper"
MIGRATION = (
    Path(__file__).parents[2] / "migrations" / "versions" / "0189_agent_channels_and_run_bounds.py"
)


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0189", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- without a database
def test_the_backfilled_list_is_the_list_the_code_derives_from_the_channel_enum() -> None:
    """**The backfill is every channel an agent can be enabled on, and no other.** The migration
    writes its list as data, the day it ran; the code derives it from `Channel` and
    `traffic_class_for`. Delete this and the two can drift, so an upgraded agent is switched on for
    a channel the builder cannot offer or off one it can, and either way nobody chose it."""
    from brain.agents.model import ASKING_CHANNELS

    assert _migration().ASKING_CHANNELS == ASKING_CHANNELS


def test_the_widths_and_caps_the_migration_copies_are_the_models() -> None:
    """The migration copies the column width and the two caps rather than importing them. Delete
    this and the database can admit a bound the record refuses, so a row that constructs nowhere
    reads as an agent nobody can find."""
    from brain.agents.model import MAX_TOOL_CALLS_CAP, MAX_TURNS_CAP
    from brain.tables.agent import CHANNEL_CHARS

    migration = _migration()
    assert (migration.CHANNEL_CHARS, migration.MAX_TURNS_CAP, migration.MAX_TOOL_CALLS_CAP) == (
        CHANNEL_CHARS,
        MAX_TURNS_CAP,
        MAX_TOOL_CALLS_CAP,
    )


# ---------------------------------------------------------------- against PostgreSQL
@contextmanager
def before_0189(name: str) -> Iterator[tuple[str, str]]:
    """A scratch database at the revision `0189` revises, yielded as its name and URL."""
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import admin_url, database_url, migrate

    admin_url()
    own = urlsplit(database_url() or "").path.strip("/").removeprefix("brain_test_")
    database = f"{name}_{own}"[:63] if own else name
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("the chain to 0133 needs pgvector, which CI has")
        migrate(database, "downgrade", _migration().down_revision)
        yield database, url


def _an_older_agent(url: str) -> None:
    """An agent written as `install_store` wrote one before this release: no column `0189` adds."""
    from sqlalchemy import create_engine, insert

    from brain.agents.install_store import agent_values
    from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
    from brain.knowledge.visibility import Visibility
    from brain.tables.agent import AgentRow

    record = AgentRecord(
        agent_id=AGENT,
        display_name="Older helper",
        persona="Answers briefly.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_one"),
        authority=AgentAuthority(),
        created_by="u_one",
    )
    row = agent_values(record)
    for added in ("channels", "max_turns", "max_tool_calls"):
        del row[added]
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        with engine.begin() as conn:
            conn.execute(insert(AgentRow).values(**row))
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def migrated() -> Iterator[tuple[str, str]]:
    from tests.fixtures.scratch_postgres import migrate

    with before_0189("brain_migration_0189") as (database, url):
        _an_older_agent(url)
        migrate(database, "upgrade", "0189")
        yield database, url


def _agents(url: str) -> list[tuple[Any, ...]]:
    from tests.fixtures.scratch_postgres import sql

    return sql(url, "SELECT id, channels, max_turns, max_tool_calls FROM agent.agent ORDER BY id")


@pytest.mark.needs_db
def test_an_agent_from_before_this_release_answers_on_every_channel_and_keeps_the_default_bounds(
    migrated: tuple[str, str],
) -> None:
    """**Nobody's agent goes quiet on upgrade.** The older agent is enabled on every channel it
    could be asked on, in the order the list gives, and its bounds are the product default. Delete
    this and an upgrade can leave every agent on an install answering nowhere, which reads as the
    whole product having stopped."""
    _, url = migrated

    assert _agents(url) == [(AGENT, list(_migration().ASKING_CHANNELS), None, None)]


@pytest.mark.needs_db
def test_an_agent_made_after_it_answers_nowhere_until_a_channel_is_ticked(
    migrated: tuple[str, str],
) -> None:
    """The positive sibling's other half: the column's default is empty, so an agent inserted after
    the backfill is enabled on nothing. Delete this and the default could be every channel, which
    makes the builder's boxes a formality."""
    from tests.fixtures.scratch_postgres import sql

    _, url = migrated
    sql(
        url,
        "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id, scope,"
        " created_by) VALUES ('newer_helper', 'Newer', 'Answers.', 'main', 'company',"
        " 'u_one', '{\"clauses\": []}'::jsonb, 'u_one')",
    )
    try:
        assert sql(url, "SELECT channels FROM agent.agent WHERE id = 'newer_helper'") == [([],)]
    finally:
        sql(url, "DELETE FROM agent.agent WHERE id = 'newer_helper'")


@pytest.mark.needs_db
def test_a_bound_outside_its_range_is_refused_by_the_database(migrated: tuple[str, str]) -> None:
    """Zero turns and a tool-call bound past the cap are refused; the cap itself is admitted. Delete
    this and a row written some other way can bound a run to nothing, or to more than the record
    would ever construct with."""
    import psycopg

    from brain.agents.model import MAX_TOOL_CALLS_CAP
    from tests.fixtures.scratch_postgres import sql

    _, url = migrated
    for statement, value in (
        ("UPDATE agent.agent SET max_turns = %s WHERE id = %s", 0),
        ("UPDATE agent.agent SET max_tool_calls = %s WHERE id = %s", MAX_TOOL_CALLS_CAP + 1),
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            sql(url, statement, value, AGENT)
    sql(url, "UPDATE agent.agent SET max_tool_calls = %s WHERE id = %s", MAX_TOOL_CALLS_CAP, AGENT)
    try:
        assert _agents(url)[0][3] == MAX_TOOL_CALLS_CAP
    finally:
        sql(url, "UPDATE agent.agent SET max_tool_calls = NULL WHERE id = %s", AGENT)


@pytest.mark.needs_db
def test_running_it_again_changes_nothing(migrated: tuple[str, str]) -> None:
    """Down and up again: the columns go and come back, and the agent holds what it held. Delete
    this and an install that retried a failed upgrade could hold a different list from one that did
    not, or fail on a column that already exists."""
    from tests.fixtures.scratch_postgres import migrate, sql

    database, url = migrated
    before = _agents(url)
    migrate(database, "downgrade", _migration().down_revision)
    gone = sql(
        url,
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'agent'"
        " AND table_name IN ('agent', 'manifest_act')"
        " AND column_name IN ('channels', 'max_turns', 'max_tool_calls')",
    )
    migrate(database, "upgrade", "0189")

    assert gone == []
    assert _agents(url) == before


@pytest.mark.needs_db
def test_the_columns_it_adds_are_the_ones_the_models_declare(migrated: tuple[str, str]) -> None:
    """`tests/fixtures/amended_tables.py` leaves these columns out of the comparison between each
    creating migration and its model, on the word of this test. Delete this and the models and the
    database can disagree about a width, a default or whether a bound may be NULL with nothing
    comparing them."""
    from sqlalchemy import String
    from sqlalchemy.dialects.postgresql import ARRAY

    from brain.tables.agent import AgentRow
    from brain.tables.manifest_draft import ManifestActRow
    from tests.fixtures.amended_tables import ADDED_LATER
    from tests.fixtures.scratch_postgres import sql

    _, url = migrated
    assert {"channels", "max_turns", "max_tool_calls"} <= set(ADDED_LATER["agent.agent"])
    assert ADDED_LATER["agent.manifest_act"] == ("channels",)
    for table, model in (("agent", AgentRow), ("manifest_act", ManifestActRow)):
        column = model.__table__.c.channels
        assert isinstance(column.type, ARRAY)
        item = column.type.item_type
        assert isinstance(item, String)
        assert not column.nullable
        assert sql(
            url,
            "SELECT udt_name, is_nullable, column_default FROM information_schema.columns"
            " WHERE table_schema = 'agent' AND table_name = %s AND column_name = 'channels'",
            table,
        ) == [("_varchar", "NO", "'{}'::character varying[]")]
        assert sql(
            url,
            "SELECT atttypmod - 4 FROM pg_attribute"
            " WHERE attrelid = %s::regclass AND attname = 'channels'",
            f"agent.{table}",
        ) == [(item.length,)]
    for name in ("max_turns", "max_tool_calls"):
        assert AgentRow.__table__.c[name].nullable
        assert sql(
            url,
            "SELECT data_type, is_nullable FROM information_schema.columns"
            " WHERE table_schema = 'agent' AND table_name = 'agent' AND column_name = %s",
            name,
        ) == [("integer", "YES")]
