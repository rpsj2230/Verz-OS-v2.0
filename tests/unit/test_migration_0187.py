"""`0187` against PostgreSQL: everybody who reads the library is given the wiki's own read.

One scratch database taken to head, stepped back to `0186`, given the rows that confer the library
read, and stepped forward again.

Task ids: M13.7.8, M13.8.1
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.needs_db

#: Far from any wall clock: nothing here is about the present.
AT = datetime(2019, 3, 1, 9, 0, tzinfo=UTC)
WEB = json.dumps({"clauses": [{"field": "department", "op": "eq", "value": "web"}]})


@contextmanager
def before_0187(name: str) -> Iterator[tuple[str, str]]:
    """A scratch database at `0186`, yielded as its name and its URL, and dropped afterwards."""
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import admin_url, database_url, migrate

    admin_url()
    own = urlsplit(database_url() or "").path.strip("/").removeprefix("brain_test_")
    database = f"{name}_{own}"[:63] if own else name
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("the chain to 0133 needs pgvector, which CI has")
        migrate(database, "downgrade", "0186")
        yield database, url


def _agent(url: str, agent_id: str, connectors: tuple[str, ...]) -> None:
    """An agent holding the library read and naming `connectors`, as `install_store` writes one."""
    from sqlalchemy import create_engine, insert

    from brain.agents.install_store import agent_values
    from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
    from brain.core.entitlement import Capability
    from brain.knowledge.visibility import Visibility
    from brain.tables.agent import AgentRow

    record = AgentRecord(
        agent_id=agent_id,
        display_name=agent_id,
        persona="Answers from the wiki.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_one"),
        authority=AgentAuthority(
            capabilities=(Capability(value="read:knowledge"),), connectors=connectors
        ),
        created_by="u_one",
    )
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        with engine.begin() as conn:
            conn.execute(insert(AgentRow).values(**agent_values(record)))
    finally:
        engine.dispose()


def _rows(url: str) -> None:
    from tests.fixtures.scratch_postgres import sql

    for pid in ("u_one", "u_two"):
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name) "
            "VALUES (%s, 'human', 'staff', %s)",
            pid,
            pid,
        )
    for pid, capability in (
        ("u_one", "read:knowledge"),
        ("u_two", "read:knowledge.title"),
    ):
        sql(
            url,
            "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by,"
            " reason) VALUES (%s, %s, %s::jsonb, 'u_admin', 'needed')",
            pid,
            capability,
            WEB,
        )
    sql(
        url,
        "INSERT INTO gate.capability_pack (name, description, capabilities) VALUES"
        " ('readers', 'Readers', ARRAY['read:knowledge', 'read:knowledge.title']),"
        " ('clients', 'Clients', ARRAY['read:client.name'])",
    )
    _agent(url, "wiki_helper", ("lark_wiki",))
    _agent(url, "library_helper", ())


def _grants(url: str) -> list[tuple[Any, ...]]:
    from tests.fixtures.scratch_postgres import sql

    return sql(
        url,
        "SELECT principal_id, capability, scope, reason FROM gate.capability_grant"
        " WHERE deleted_at IS NULL ORDER BY principal_id, capability",
    )


@pytest.fixture(scope="module")
def migrated() -> Iterator[tuple[str, str]]:
    from tests.fixtures.scratch_postgres import migrate

    with before_0187("brain_migration_0187") as (database, url):
        _rows(url)
        migrate(database, "upgrade", "0187")
        yield database, url


def test_a_holder_of_the_library_read_is_given_the_wikis_in_the_same_scope(
    migrated: tuple[str, str],
) -> None:
    """**Nobody's reach shrinks.** The library read gains a wiki read with the same scope and
    reason; a field read gains nothing, because it never covered the library read and never
    admitted a wiki page. Delete this and every reader of the wiki loses it on upgrade."""
    _, url = migrated
    scope = json.loads(WEB)

    assert _grants(url) == [
        ("u_one", "read:knowledge", scope, "needed"),
        ("u_one", "read:wiki_page", scope, "needed"),
        ("u_two", "read:knowledge.title", scope, "needed"),
    ]


def test_a_pack_conferring_the_library_read_confers_the_wikis_and_no_other_pack_changes(
    migrated: tuple[str, str],
) -> None:
    """The Starter pack is one such pack on every install. Delete this and everybody holding a
    pack, every joiner included, loses the wiki on upgrade."""
    from tests.fixtures.scratch_postgres import sql

    _, url = migrated

    assert sql(url, "SELECT name, capabilities FROM gate.capability_pack ORDER BY name") == [
        ("clients", ["read:client.name"]),
        ("readers", ["read:knowledge", "read:knowledge.title", "read:wiki_page"]),
    ]


def test_only_an_agent_bound_to_the_wiki_is_given_its_read(migrated: tuple[str, str]) -> None:
    """An agent naming Lark Wiki read it before and keeps reading it; one naming nothing gains no
    wiki read, which is the binding `0186` started. Delete this and either every agent holding the
    library read is handed the wiki, or the one built to read it loses it."""
    from tests.fixtures.scratch_postgres import sql

    _, url = migrated

    assert sql(url, "SELECT id, capabilities FROM agent.agent ORDER BY id") == [
        ("library_helper", ["read:knowledge"]),
        ("wiki_helper", ["read:knowledge", "read:wiki_page"]),
    ]


def test_running_it_again_writes_no_second_copy(migrated: tuple[str, str]) -> None:
    """Down and up again writes nothing twice. Delete this and an install that retried a failed
    upgrade holds every wiki read twice, which is two rows a revocation has to find."""
    from tests.fixtures.scratch_postgres import migrate, sql

    database, url = migrated
    grants = _grants(url)
    packs = sql(url, "SELECT name, capabilities FROM gate.capability_pack ORDER BY name")
    agents = sql(url, "SELECT id, capabilities FROM agent.agent ORDER BY id")
    migrate(database, "downgrade", "0186")
    migrate(database, "upgrade", "0187")

    assert _grants(url) == grants
    assert sql(url, "SELECT name, capabilities FROM gate.capability_pack ORDER BY name") == packs
    assert sql(url, "SELECT id, capabilities FROM agent.agent ORDER BY id") == agents
