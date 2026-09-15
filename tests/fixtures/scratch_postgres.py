"""A PostgreSQL database of a test file's own, built through the migrations that ship.

`tests/unit/test_delegation_sql.py` wrote this recipe for itself before there was a second
caller. The outbox, the budget table and the plugin registry are three more, so the recipe is
written once here rather than copied three times, and a fix to it lands everywhere.

**Stamped at `0029`, not built from empty.** `0001` creates pgvector, which a development
machine may not have, and none of the tables these tests exercise points at anything `0002` to
`0029` built. So the schemas and the roles `0001` would have left are made by hand, the database
is stamped at `0029`, and the migration under test is then run for real. `0025` is the
exception and is run for real first, because `0030` widens a constraint on the table it
builds, and it needs nothing `0002` to `0024` built. What is under test is
the migration that ships and not a copy of its DDL.

**Every database here is the caller's own and is dropped afterwards.** CI's unit job runs pytest
against an empty database before it migrates anything, so creating schemas in the shared one
would collide with the migration step later in the same job.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[2]

#: What `0001` builds, restated because `0001` itself cannot run without pgvector.
SCHEMAS: tuple[str, ...] = ("auth", "gate", "agent", "know", "mem", "obs", "proj", "er", "ops")

#: The last migration these tests stamp rather than run.
STAMPED_AT = "0029"


def database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("BRAIN_DATABASE_URL") or None


def pointed_at(url: str, database: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{database}"))


def admin_url() -> str:
    """The server's own URL in libpq form, or a skip when there is no server to ask."""
    from brain.db import libpq_url

    url = database_url()
    if url is None:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")
    return libpq_url(url)


def drop(database: str) -> None:
    import psycopg

    with psycopg.connect(admin_url(), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')


def fresh(database: str) -> str:
    """A database holding what `0001` would have left: schemas, roles and schema grants."""
    import psycopg

    admin = admin_url()
    drop(database)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{database}"')
    scratch = pointed_at(admin, database)
    with psycopg.connect(scratch, autocommit=True) as conn:
        for schema in SCHEMAS:
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        conn.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'brain_app') "
            "THEN CREATE ROLE brain_app NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$"
        )
        conn.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'brain_fastlane') "
            "THEN CREATE ROLE brain_fastlane NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT; END IF; "
            "END $$"
        )
        for schema in SCHEMAS:
            conn.execute(f"GRANT USAGE ON SCHEMA {schema} TO brain_app")
    return scratch


def migrate(database: str, verb: str, revision: str) -> None:
    """One alembic command against one scratch database, through the migrations that ship."""
    from alembic import command
    from alembic.config import Config

    url = database_url()
    assert url is not None
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    # On the config and not in the environment. This used to set `DATABASE_URL` for the length
    # of the command, which worked only because `migrations/env.py` read that variable; it now
    # believes the config first and `Settings` after, where `BRAIN_DATABASE_URL` would win over
    # a `DATABASE_URL` set here and migrate the shared database instead of the scratch one.
    config.set_main_option("sqlalchemy.url", pointed_at(url, database).replace("%", "%%"))
    commands = {"stamp": command.stamp, "upgrade": command.upgrade, "downgrade": command.downgrade}
    commands[verb](config, revision)


@contextmanager
def built(database: str, head: str) -> Iterator[str]:
    """A fresh database migrated to `head`, yielded as a libpq URL and dropped afterwards."""
    scratch = fresh(database)
    try:
        migrate(database, "stamp", "0024")
        migrate(database, "upgrade", "0025")
        migrate(database, "stamp", STAMPED_AT)
        migrate(database, "upgrade", head)
        yield scratch
    finally:
        drop(database)


@contextmanager
def modelled(database: str, qualified: Sequence[str]) -> Iterator[str]:
    """A fresh database holding only these tables, built from the models rather than a migration."""
    from sqlalchemy import create_engine

    import brain.tables  # noqa: F401 - registers every table on the metadata
    from brain.db import metadata, normalise_database_url

    scratch = fresh(database)
    engine = create_engine(normalise_database_url(scratch), poolclass=NullPool)
    try:
        metadata.create_all(engine, tables=[metadata.tables[one] for one in qualified])
        yield scratch
    finally:
        engine.dispose()
        drop(database)


def sql(url: str, statement: str, *params: object) -> list[tuple[Any, ...]]:
    """One statement in its own autocommitted connection, as the superuser the URL names."""
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        cursor = conn.execute(statement, params or None)
        return cursor.fetchall() if cursor.description else []


def shape(url: str, qualified: Sequence[str]) -> dict[str, set[str]]:
    """Every constraint by name and definition, every index and every column, per table."""
    found: dict[str, set[str]] = {}
    for one in qualified:
        schema, table = one.split(".")
        constraints = sql(
            url,
            "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = %s::regclass",
            one,
        )
        indexes = sql(
            url,
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = %s AND tablename = %s",
            schema,
            table,
        )
        columns = sql(
            url,
            "SELECT column_name, data_type, is_nullable, column_default, character_maximum_length "
            "FROM information_schema.columns WHERE table_schema = %s AND table_name = %s",
            schema,
            table,
        )
        found[one] = {repr(row) for row in (*constraints, *indexes, *columns)}
    return found


def secured(url: str, qualified: Sequence[str]) -> dict[str, bool]:
    """Whether row-level security is enabled, per table."""
    return {
        one: bool(
            sql(url, "SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass", one)[0][0]
        )
        for one in qualified
    }


def present(url: str, qualified: Sequence[str]) -> set[str]:
    """Which of these tables exist."""
    return {one for one in qualified if sql(url, "SELECT to_regclass(%s)", one)[0][0] is not None}


def engine(url: str) -> AsyncEngine:
    from brain.db import normalise_database_url

    return create_async_engine(normalise_database_url(url), poolclass=NullPool)


def run[T](factory: Callable[[], Awaitable[T]]) -> T:
    """Run a coroutine on a loop psycopg accepts. See `brain.ops.worker._loop_factory`."""

    async def main() -> T:
        return await factory()

    loop_factory = asyncio.SelectorEventLoop if os.name == "nt" else None
    return asyncio.run(main(), loop_factory=loop_factory)
