"""The badge read on PostgreSQL, as the application role, under the policy `0040` put on items.

`tests/unit/test_badge_store.py` holds the statement to its shape. This holds the policy to the
answer: a reader in one department reads the items of that department and the company's, and not
another department's, through `StoredItems` over `SessionRowSource` connected as `brain_app`, with
`0040`'s own policy statements executed. A superuser bypasses row-level security, so the role is
set on the connection, for `tests/unit/test_document_second_wall.py`'s reason.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is.

Task ids: M7.4.7
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.db import libpq_url, normalise_database_url
from brain.gate.badge_store import ITEM, StoredItems
from brain.knowledge.item import KnowledgeItem
from brain.knowledge.row_store import SessionRowSource
from brain.knowledge.search import KNOWLEDGE_READ
from brain.knowledge.verification import disclose
from brain.tables.gate import DepartmentRow
from tests.unit import test_document_second_wall as wall

pytestmark = pytest.mark.needs_db

#: A database of this file's own, created and dropped here.
DATABASE = "brain_badge_store"

MIGRATION = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0040_knowledge_item.py"
)

COMPANY = "c_badge_store"
WEB = "web"
FINANCE = "finance"

#: Far from any wall clock; the badges' due states are computed against this.
NOW = datetime(2099, 6, 1, 9, 0, tzinfo=UTC)

#: One published item at each place, every one verified, so a missing badge is the policy's doing.
ITEMS: tuple[tuple[str, str, str | None], ...] = (
    ("doc_web", "department", WEB),
    ("doc_finance", "department", FINANCE),
    ("doc_company", "company", None),
)

#: Reads the knowledge plane over web only.
WEB_READER = EntitlementSet(
    principal_id="u_web_reader",
    grants=(Grant(capability=Capability(value=KNOWLEDGE_READ.value), scope=Scope.department(WEB)),),
)


def _migration() -> Any:
    spec = importlib.util.spec_from_file_location("m0040_badge_store", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build(admin: str, url: str) -> None:
    """`know.item` and `gate.department` from the models, with `0040`'s policy and a read grant."""
    import psycopg

    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{DATABASE}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{DATABASE}"')

    scratch = wall._pointed_at(admin, DATABASE)
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("CREATE SCHEMA know")
        conn.execute("CREATE SCHEMA gate")
        conn.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'brain_app') "
            "THEN CREATE ROLE brain_app NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$"
        )
        conn.execute("GRANT USAGE ON SCHEMA know, gate TO brain_app")

    metadata = sa.MetaData()
    ITEM.to_metadata(metadata)
    DepartmentRow.metadata.tables["gate.department"].to_metadata(metadata)
    engine = sa.create_engine(
        wall._pointed_at(normalise_database_url(url), DATABASE), poolclass=NullPool
    )
    try:
        metadata.create_all(engine)
    finally:
        engine.dispose()

    with psycopg.connect(scratch, autocommit=True) as conn:
        for statement in _migration().RLS:
            conn.execute(statement)
        # `0040`'s grants name the review function, which this scratch database does not build.
        conn.execute("GRANT SELECT ON know.item TO brain_app")
        conn.execute("GRANT SELECT ON gate.department TO brain_app")
        for slug in (WEB, FINANCE):
            conn.execute(
                "INSERT INTO gate.department (company_id, slug, name, scope_slug) "
                "VALUES (%s, %s, %s, %s)",
                (COMPANY, slug, slug.title(), slug),
            )
        for item_id, visibility, department in ITEMS:
            conn.execute(
                "INSERT INTO know.item (item_id, title, owner_id, visibility, department, state, "
                "verified_by, verified_at, review_by) "
                "VALUES (%s, %s, 'u_owner', %s, %s, 'published', 'u_steward', %s, %s)",
                (
                    item_id,
                    item_id.title(),
                    visibility,
                    department,
                    NOW - timedelta(days=30),
                    NOW + timedelta(days=300),
                ),
            )


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    """The SQLAlchemy url of the scratch database above."""
    import psycopg

    url = os.environ.get("DATABASE_URL") or os.environ.get("BRAIN_DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")
    admin = libpq_url(url)
    _build(admin, url)
    yield wall._pointed_at(normalise_database_url(url), DATABASE)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{DATABASE}" WITH (FORCE)')


def read(url: str, reader: EntitlementSet, ids: list[str]) -> tuple[KnowledgeItem, ...]:
    """`StoredItems.items` over the scratch database, connected as `brain_app`."""

    async def go() -> tuple[KnowledgeItem, ...]:
        engine = create_async_engine(
            url, poolclass=NullPool, connect_args={"options": "-c role=brain_app"}
        )
        try:
            source = SessionRowSource(async_sessionmaker(engine, class_=AsyncSession))
            return await StoredItems(source).items(ids, entitlement=reader, now=NOW)
        finally:
            await engine.dispose()

    if os.name == "nt":
        return asyncio.run(go(), loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(go())


def test_a_reader_reads_the_items_of_their_department_and_the_companys(server: str) -> None:
    """**The positive case on a real server.** Both items the web reader reaches come back,
    verified, and each discloses a verified badge to them.

    Delete this and a read returning nothing passes the refusal below."""
    found = read(server, WEB_READER, ["doc_web", "doc_company"])

    assert {one.item_id for one in found} == {"doc_web", "doc_company"}
    for one in found:
        assert disclose(one, reader=WEB_READER, now=NOW).state.value == "verified"


def test_another_departments_item_is_not_read_for_a_badge(server: str) -> None:
    """**The wall.** Asked for finance's item by reference, the policy returns nothing, so no
    badge can be computed from a record the reader could not have been cited.

    Delete this and the read can run with settings that admit every department, or none at all,
    which the policy answers with company items only and this test would still catch."""
    found = read(server, WEB_READER, ["doc_web", "doc_finance", "doc_company"])

    assert "doc_finance" not in {one.item_id for one in found}
    assert "doc_web" in {one.item_id for one in found}
