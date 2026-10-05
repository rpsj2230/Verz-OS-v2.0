"""`0186` against PostgreSQL: an agent's connectors are backfilled, and shared names are copied.

One scratch database taken to head, stepped back to `0154`, given rows naming the old entities and
stepped forward again. On it, Xero is connected and Freshdesk was connected and then disconnected,
so one source of `contact` is live and one is not, which is both halves of the grant rule at once.

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
KEY = "a-key-for-the-0186-fixture"
AGENT = "ledger_helper"
DEPARTMENT_SCOPE = json.dumps(
    {"clauses": [{"field": "department", "op": "eq", "value": "finance"}]}
)


@contextmanager
def before_0186(name: str) -> Iterator[tuple[str, str]]:
    """A scratch database at `0154`, yielded as its name and its URL, and dropped afterwards."""
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import admin_url, database_url, migrate

    admin_url()
    own = urlsplit(database_url() or "").path.strip("/").removeprefix("brain_test_")
    database = f"{name}_{own}"[:63] if own else name
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("the chain to 0133 needs pgvector, which CI has")
        migrate(database, "downgrade", "0154")
        yield database, url


def _agent_rows(url: str) -> None:
    """An agent installed from a template naming Freshdesk, written as `install_store` writes it,
    less the column `0186` adds."""
    from sqlalchemy import create_engine, insert

    from brain.agents.install_store import agent_values, version_values
    from brain.agents.model import AgentAudience
    from brain.agents.template import (
        ManifestAuthority,
        ManifestIdentity,
        TemplateManifest,
        install,
        materialise,
        publish,
    )
    from brain.core.entitlement import Capability
    from brain.core.scope import Scope
    from brain.knowledge.visibility import Visibility
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

    signed = publish(
        TemplateManifest(
            identity=ManifestIdentity(
                template_id=AGENT, version=1, published_by="u_one", display_name="Ledger helper"
            ),
            persona="Answers questions about contacts.",
            authority=ManifestAuthority(
                scope=Scope.unrestricted(),
                capabilities=(
                    Capability(value="read:contact.name"),
                    Capability(value="read:invoice.status"),
                ),
            ),
            connectors=("freshdesk",),
        ),
        key=KEY,
        signed_by="u_one",
        at=AT,
    )
    instance = install(signed, key=KEY, instance_id=AGENT, created_by="u_one", at=AT)
    effective = materialise(
        signed, instance, audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_one")
    )
    row = agent_values(effective.record)
    del row["connectors"]
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        with engine.begin() as conn:
            conn.execute(insert(TemplateVersionRow).values(**version_values(signed)))
            conn.execute(
                insert(TemplateInstanceRow).values(
                    id=AGENT,
                    template_id=instance.template_id,
                    template_version=instance.template_version,
                    content_digest=instance.content_digest,
                    overlay=dict(instance.overlay),
                    field_owners={},
                    effective_document=dict(effective.document),
                    effective_hash=effective.config_hash,
                    created_by="u_one",
                )
            )
            conn.execute(insert(AgentRow).values(**row))
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
    sql(
        url,
        "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
        " VALUES ('xero', '{}'::jsonb, %s, 'u_one')",
        "0" * 64,
    )
    sql(
        url,
        "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by,"
        " disconnected_by, disconnected_at) VALUES ('freshdesk', '{}'::jsonb, %s, 'u_one',"
        " 'u_one', now())",
        "1" * 64,
    )
    for pid, capability in (
        ("u_one", "read:contact.name"),
        ("u_one", "read:invoice.*"),
        ("u_two", "read:ticket.subject"),
    ):
        sql(
            url,
            "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by,"
            " reason) VALUES (%s, %s, %s::jsonb, 'u_admin', 'needed')",
            pid,
            capability,
            DEPARTMENT_SCOPE,
        )
    sql(
        url,
        "INSERT INTO gate.capability_pack (name, description, capabilities)"
        " VALUES ('ledger', 'Ledger', ARRAY['read:contact.name', 'read:ticket'])",
    )
    for source in ("xero", "demo"):
        sql(
            url,
            "INSERT INTO proj.record (source, entity, source_id, local_id, fields, last_seen_at)"
            " VALUES (%s, 'invoice', 'INV-1', gen_random_uuid(), '{}'::jsonb, now())",
            source,
        )
    _agent_rows(url)


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

    with before_0186("brain_migration_0186") as (database, url):
        _rows(url)
        migrate(database, "upgrade", "0186")
        yield database, url


def test_a_grant_on_a_shared_name_is_copied_for_each_connected_source_and_kept(
    migrated: tuple[str, str],
) -> None:
    """**Nobody loses a read they had.** The contact read gains the ledger's copy because Xero is
    connected, and not the helpdesk's because Freshdesk is not; the invoice read gains the ledger's;
    each original stays, and a read on no shared name is untouched. Copies keep the scope and the
    reason. Delete this and the rename can take a person's reads away on upgrade, or give them a
    source the install never connected."""
    _, url = migrated
    scope = json.loads(DEPARTMENT_SCOPE)

    assert _grants(url) == [
        ("u_one", "read:contact.name", scope, "needed"),
        ("u_one", "read:invoice.*", scope, "needed"),
        ("u_one", "read:xero_contact.name", scope, "needed"),
        ("u_one", "read:xero_invoice.*", scope, "needed"),
        ("u_two", "read:ticket.subject", scope, "needed"),
    ]


def test_a_pack_gains_the_copies_for_connected_sources(migrated: tuple[str, str]) -> None:
    """A pack is a grant to everybody holding it, so it follows the grant rule. Delete this and
    every holder of a pack naming `contact` reaches no contact after the rename."""
    from tests.fixtures.scratch_postgres import sql

    _, url = migrated

    assert sql(url, "SELECT capabilities FROM gate.capability_pack WHERE name = 'ledger'") == [
        (["read:contact.name", "read:ticket", "read:xero_contact.name"],)
    ]


def test_an_agent_is_given_its_templates_connectors_and_copies_for_those_alone(
    migrated: tuple[str, str],
) -> None:
    """**The backfill, and the binding it feeds.** The agent's list is read from its own install's
    document, and its capabilities gain copies for the sources it names whether or not the install
    has them connected: the list is its binding, not the install's connections. Its invoice read
    gains nothing, because it does not name Xero. Delete this and every agent installed before this
    release reaches no connected source at all."""
    from tests.fixtures.scratch_postgres import sql

    _, url = migrated

    assert sql(url, "SELECT connectors, capabilities FROM agent.agent WHERE id = %s", AGENT) == [
        (["freshdesk"], ["read:contact.name", "read:invoice.status", "read:freshdesk_contact.name"])
    ]


def test_a_source_s_own_records_are_renamed_and_another_source_s_are_not(
    migrated: tuple[str, str],
) -> None:
    """The minimal index carries its source, so Xero's invoice rows take Xero's name and the
    demo's keep theirs. Delete this and the index Xero answers from names an entity Xero no longer
    reads until the next sync, and the demo's rows could be renamed under a source they are not."""
    from tests.fixtures.scratch_postgres import sql

    _, url = migrated

    assert sql(url, "SELECT source, entity FROM proj.record ORDER BY source") == [
        ("demo", "invoice"),
        ("xero", "xero_invoice"),
    ]


def test_running_it_again_writes_no_second_copy(migrated: tuple[str, str]) -> None:
    """Down and up again: the column goes and comes back, and no grant, pack entry or agent
    capability is written twice. Delete this and an install that retried a failed upgrade holds
    every copied grant twice, which is two rows a revocation has to find."""
    from tests.fixtures.scratch_postgres import migrate, sql

    database, url = migrated
    before = _grants(url)
    migrate(database, "downgrade", "0154")
    gone = sql(
        url,
        "SELECT 1 FROM information_schema.columns WHERE table_schema = 'agent'"
        " AND table_name = 'agent' AND column_name = 'connectors'",
    )
    migrate(database, "upgrade", "0186")

    assert gone == []
    assert _grants(url) == before
    assert sql(url, "SELECT capabilities FROM gate.capability_pack WHERE name = 'ledger'") == [
        (["read:contact.name", "read:ticket", "read:xero_contact.name"],)
    ]
    assert sql(url, "SELECT capabilities FROM agent.agent WHERE id = %s", AGENT) == [
        (["read:contact.name", "read:invoice.status", "read:freshdesk_contact.name"],)
    ]


def test_the_column_it_adds_is_the_one_the_model_declares(migrated: tuple[str, str]) -> None:
    """`tests/fixtures/amended_tables.py` leaves `connectors` out of the comparison between the
    creating migration and the model, on the word of this migration's own test, so this is that
    test. Delete this and the model and the database can disagree about the column's width or its
    default with nothing comparing them."""
    from sqlalchemy import String
    from sqlalchemy.dialects.postgresql import ARRAY

    from brain.tables.agent import AgentRow
    from tests.fixtures.amended_tables import ADDED_LATER
    from tests.fixtures.scratch_postgres import sql

    _, url = migrated
    column = AgentRow.__table__.c.connectors
    assert isinstance(column.type, ARRAY)
    item = column.type.item_type
    assert isinstance(item, String)

    assert "connectors" in ADDED_LATER["agent.agent"]
    assert sql(
        url,
        "SELECT udt_name, is_nullable, column_default FROM information_schema.columns"
        " WHERE table_schema = 'agent' AND table_name = 'agent' AND column_name = 'connectors'",
    ) == [("_varchar", "NO", "'{}'::character varying[]")]
    assert sql(
        url,
        "SELECT atttypmod - 4 FROM pg_attribute"
        " WHERE attrelid = 'agent.agent'::regclass AND attname = 'connectors'",
    ) == [(item.length,)]
    assert not column.nullable
