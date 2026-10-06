"""The entity registry's writer, over a real schema as the application role.

Records are written into `proj.record` as the superuser, the way a sync leaves them, and the
registry is run over them as `brain_app`. The pure half holds the comparison row and the blocked
filter, and the declaration half holds what each connector says its records are.

Task ids: M14.1.1, M14.1.2, M14.1.3, M14.1.4, M14.1.6, M14.6.1, M14.7.3
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

import pytest

from brain.connectors.resolves import ResolvesAs, ResolvesError
from brain.resolution.canonical import EntityType, IdentifierKind, SourceRef, identifier_hash
from brain.resolution.registry_store import (
    REGISTRY_ACTOR,
    StoredRegistry,
    observation_row,
    without_blocked,
)
from brain.resolution.sources import ANCHOR, resolution_source_gaps, resolved_entities

#: Far from any wall clock, for the reason `tests/unit/test_scope_and_capability.py` gives.
AT = datetime(2019, 3, 4, 12, tzinfo=UTC)
PEPPER = "ab" * 32
SOURCE = "hubspot"
ENTITY = "hubspot_company"
DOMAIN = "registry-check.example"
DECLARED = MappingProxyType(
    {
        (SOURCE, ENTITY): ResolvesAs(
            entity=ENTITY,
            entity_type=EntityType.COMPANY,
            fields={"name": "name", "domain": "domain"},
        )
    }
)


def ref(source_id: str) -> SourceRef:
    return SourceRef(source=SOURCE, entity=ENTITY, source_id=source_id)


# ------------------------------------------------------------------- the declarations
def test_discovery_finds_every_declared_record_and_the_anchor_is_among_them() -> None:
    """Xero's contact is a client, so discovery that does not find it has stopped finding all.

    Delete this and discovery can come back empty, every record stays unresolved, and the
    registry reports that it had nothing to do."""
    found = resolved_entities()
    assert ANCHOR in found
    assert found[ANCHOR].entity_type is EntityType.COMPANY
    assert found[ANCHOR].carries_money
    assert ("hubspot", "hubspot_company") in found
    assert resolution_source_gaps() == ()


def test_a_declaration_naming_an_entity_or_field_its_connector_does_not_keep_is_a_gap() -> None:
    """Every declared entity and renamed field is held against the connector's own manifest.

    Delete this and a declaration can name a field nothing projects, which resolves nothing and
    reads as though it did."""
    from dataclasses import replace

    from brain.connectors.declaration import shipped

    declared = dict(shipped())
    hubspot = declared["hubspot"]
    wrong_field = ResolvesAs(
        entity=ENTITY, entity_type=EntityType.COMPANY, fields={"name": "amount_due"}
    )
    declared["hubspot"] = replace(hubspot, resolves=(wrong_field,))
    assert any("amount_due" in one for one in resolution_source_gaps(declared))

    without_anchor = dict(shipped())
    without_anchor["xero"] = replace(without_anchor["xero"], resolves=())
    assert any("discovery has stopped" in one for one in resolution_source_gaps(without_anchor))


@pytest.mark.parametrize(
    ("fields", "said"),
    [
        ({"domain": "domain"}, "names no field for the name"),
        ({"name": "name", "home_address": "street"}, "which no profile reads"),
        ({"name": " "}, "onto no projected field"),
    ],
)
def test_a_resolution_declaration_that_reads_nothing_usable_is_refused(
    fields: dict[str, str], said: str
) -> None:
    """A declaration with no name, a renaming no profile reads, or a blank field is refused.

    Delete this and a record could reach the cascade with nothing to normalise, or a renaming
    could claim a field that is read by nothing."""
    with pytest.raises(ResolvesError, match=said):
        ResolvesAs(entity=ENTITY, entity_type=EntityType.COMPANY, fields=fields)
    assert ResolvesAs(entity=ENTITY, entity_type=EntityType.COMPANY, fields={"name": "label"})


def test_a_connector_declaring_one_entity_twice_or_one_it_never_reads_is_refused() -> None:
    """The declaration refuses a duplicate and an entity its reading keeps no record of.

    Delete this and a connector could declare a record nothing ever reads, which is a type
    nothing resolves."""
    from dataclasses import replace

    from brain.connectors.declaration import DeclarationError, shipped

    xero = shipped()["xero"]
    twice = (*xero.resolves, *xero.resolves)
    with pytest.raises(DeclarationError, match="twice"):
        replace(xero, resolves=twice)
    unread = ResolvesAs(entity="invoice_line", entity_type=EntityType.COMPANY, fields={"name": "n"})
    with pytest.raises(DeclarationError, match="keeps no record"):
        replace(xero, resolves=(unread,))


def test_registering_a_record_of_an_undeclared_entity_is_refused() -> None:
    """A record whose connector says nothing about it is not read as anything.

    Delete this and the registry could mint an entity for a record of no declared type."""
    from brain.resolution.registry_store import RegistryError

    store = StoredRegistry(None, declared=DECLARED)  # type: ignore[arg-type]
    other = SourceRef(source="freshdesk", entity="ticket", source_id="1")
    with pytest.raises(RegistryError, match="declare no record"):
        asyncio.run(store.register([other], pepper=PEPPER, now=AT))


# ----------------------------------------------------------------------- the pure half
def test_the_comparison_row_carries_digests_and_keys_and_no_value() -> None:
    """The row the score reads holds the name's keys and digests, never the domain itself.

    Delete this and the comparison row can grow a column a contact detail would fit in."""
    from brain.connectors.projection import ProjectedRecord
    from brain.resolution.entities import COMPANY_PROFILE, observe

    observed = observe(
        ProjectedRecord(
            source=SOURCE,
            entity=ENTITY,
            source_id="1",
            last_seen_at=AT,
            fields={"name": "Registry Check Pte. Ltd.", "domain": DOMAIN},
        ),
        COMPANY_PROFILE,
        pepper=PEPPER,
    )
    row = observation_row(observed.observation, "company")

    assert row["name_key"] == "registry check"
    assert row["name_collapsed"] == "registry check pte ltd"
    assert row["domain_hash"] == identifier_hash(IdentifierKind.DOMAIN, DOMAIN, pepper=PEPPER)
    assert DOMAIN not in json.dumps(row, default=str)


def test_a_blocked_digest_is_removed_and_an_unblocked_one_kept() -> None:
    """The install's blocklist removes exactly the digests it holds.

    Delete this and a blocked switchboard number joins every client that lists it, or the
    filter removes every key and nothing ever joins."""
    from brain.connectors.projection import ProjectedRecord
    from brain.resolution.entities import COMPANY_PROFILE, observe

    observed = observe(
        ProjectedRecord(
            source=SOURCE,
            entity=ENTITY,
            source_id="1",
            last_seen_at=AT,
            fields={"name": "Registry Check", "domain": DOMAIN},
        ),
        COMPANY_PROFILE,
        pepper=PEPPER,
    ).observation
    digest = identifier_hash(IdentifierKind.DOMAIN, DOMAIN, pepper=PEPPER)

    kept, removed = without_blocked(observed, frozenset({("uen", digest)}))
    assert removed == 0 and kept is observed
    dropped, removed = without_blocked(observed, frozenset({("domain", digest)}))
    assert removed == 1
    assert IdentifierKind.DOMAIN not in dropped.identifiers


# ------------------------------------------------------------------- on a real schema
@pytest.fixture
def schema() -> Iterator[tuple[str, Callable[..., Any]]]:
    from tests.fixtures.scratch_postgres import sql
    from tests.unit.test_acceptance import at_head

    with at_head("brain_registry_store") as url:
        yield url, sql


def write_record(url: str, sql: Callable[..., Any], source_id: str, **fields: str) -> None:
    sql(
        url,
        "INSERT INTO proj.record (source, entity, source_id, fields, last_seen_at)"
        " VALUES (%s, %s, %s, %s::jsonb, %s)"
        " ON CONFLICT (source, entity, source_id) DO UPDATE SET fields = excluded.fields,"
        " updated_at = now()",
        SOURCE,
        ENTITY,
        source_id,
        json.dumps(fields),
        AT,
    )


def as_app(url: str, act: Callable[[StoredRegistry], Any]) -> Any:
    from brain.db import normalise_database_url
    from brain.session import make_app_engine, make_session_factory

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await act(StoredRegistry(make_session_factory(engine), declared=DECLARED))
        finally:
            await engine.dispose()

    return asyncio.run(run())


def register(url: str, *ids: str) -> Any:
    return as_app(
        url, lambda store: store.register([ref(one) for one in ids], pepper=PEPPER, now=AT)
    )


@pytest.mark.needs_db
def test_a_record_read_for_the_first_time_is_minted_an_entity_with_its_link_names_and_keys(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """One entity of the declared type with its provenance, one link, the verbatim alias, the
    domain as a digest, the comparison row, and the record's local id set to the entity.

    Delete this and the registry can write a graph that resolves nothing: an entity with no
    link, a key stored in the clear, or a record whose local id stays empty."""
    url, sql = schema
    write_record(url, sql, "1", name="Registry Check Pte. Ltd.", domain=DOMAIN)

    done = register(url, "1")

    assert (done.read, done.minted, done.reobserved) == (1, 1, 0)
    [(entity_id, kind, by, source_id)] = sql(
        url,
        "SELECT entity_id, entity_type, created_by, created_from_source_id FROM er.canonical",
    )
    assert (kind, by, source_id) == ("company", REGISTRY_ACTOR, "1")
    assert sql(url, "SELECT entity_id, confidence FROM er.link") == [(entity_id, 1.0)]
    assert sql(url, "SELECT name FROM er.alias") == [("Registry Check Pte. Ltd.",)]
    assert sql(url, "SELECT kind, key_hash FROM er.identifier") == [
        ("domain", identifier_hash(IdentifierKind.DOMAIN, DOMAIN, pepper=PEPPER))
    ]
    assert sql(url, "SELECT name_key FROM er.observation") == [("registry check",)]
    assert sql(url, "SELECT local_id FROM proj.record") == [(entity_id,)]
    assert sql(url, "SELECT entity_id, name FROM er.resolved_alias") == [
        (entity_id, "Registry Check Pte. Ltd.")
    ]


@pytest.mark.needs_db
def test_two_records_are_two_entities_and_a_record_read_again_keeps_its_own(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """Two records sharing a domain stay two entities until a merge, and a record renamed and
    read again keeps its entity, gains the new name form and keeps the old one.

    Delete this and the writer can link a new record to an existing entity, which is a merge
    with no audit, or mint a second entity for a record it already holds."""
    url, sql = schema
    write_record(url, sql, "1", name="Registry Check", domain=DOMAIN)
    write_record(url, sql, "2", name="Registry Check Holdings", domain=DOMAIN)
    register(url, "1", "2")
    [(first,)] = sql(url, "SELECT local_id FROM proj.record WHERE source_id = '1'")

    write_record(url, sql, "1", name="Registry Check Renamed", domain=DOMAIN)
    assert [one.source_id for one in as_app(url, lambda store: store.pending())] == ["1"]
    again = register(url, "1")

    assert (again.minted, again.reobserved) == (0, 1)
    assert sql(url, "SELECT count(*) FROM er.canonical") == [(2,)]
    assert sql(url, "SELECT local_id FROM proj.record WHERE source_id = '1'") == [(first,)]
    assert sql(url, "SELECT name FROM er.alias WHERE source_id = '1' ORDER BY name") == [
        ("Registry Check",),
        ("Registry Check Renamed",),
    ]
    assert sql(url, "SELECT name_key FROM er.observation WHERE source_id = '1'") == [
        ("registry check renamed",)
    ]
    assert as_app(url, lambda store: store.pending()) == ()


@pytest.mark.needs_db
def test_a_value_this_install_blocks_is_never_written_as_a_join_key(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """A blocked domain is kept off the record's identifiers and its comparison row, while
    another record's domain is still written; the blocked value is held only as its digest.

    Delete this and an administrator's block reaches nothing, or the table keeps the value."""
    url, sql = schema
    write_record(url, sql, "1", name="Registry Check", domain=DOMAIN)
    write_record(url, sql, "2", name="Another Client", domain="another-client.example")
    digest = as_app(
        url,
        lambda store: store.block(
            IdentifierKind.DOMAIN,
            DOMAIN,
            pepper=PEPPER,
            reason="the domain of a shared portal, not of a client",
            by="u_admin",
            trace_id="t",
        ),
    )

    done = register(url, "1", "2")

    assert done.blocked == 1
    assert sql(url, "SELECT source_id FROM er.identifier") == [("2",)]
    assert sql(url, "SELECT domain_hash FROM er.observation WHERE source_id = '1'") == [(None,)]
    assert sql(url, "SELECT kind, key_hash, blocked_by FROM er.blocked_value") == [
        ("domain", digest, "u_admin")
    ]
    assert DOMAIN not in json.dumps(sql(url, "SELECT * FROM er.blocked_value"), default=str)


@pytest.mark.needs_db
def test_no_registry_table_holds_a_join_key_value(
    schema: tuple[str, Callable[..., Any]],
) -> None:
    """After registration the domain appears in the record it came from and in no er table.

    Delete this and a join key can be written in the clear anywhere the registry writes."""
    url, sql = schema
    write_record(url, sql, "1", name="Registry Check", domain=DOMAIN)
    register(url, "1")

    for table in (
        "er.canonical",
        "er.alias",
        "er.identifier",
        "er.link",
        "er.observation",
        "er.blocked_value",
    ):
        rows = sql(url, f"SELECT * FROM {table}")  # noqa: S608 - names are this file's constants
        assert DOMAIN not in json.dumps(rows, default=str), table
    assert DOMAIN in json.dumps(sql(url, "SELECT fields FROM proj.record"))


@pytest.mark.needs_db
def test_a_retired_record_is_not_pending(schema: tuple[str, Callable[..., Any]]) -> None:
    """A record its source retired waits for nothing, and a live one beside it still does.

    Delete this and the registry mints entities for records the source has deleted."""
    url, sql = schema
    write_record(url, sql, "1", name="Registry Check", domain=DOMAIN)
    write_record(url, sql, "2", name="Retired Client", domain="retired.example")
    sql(url, "UPDATE proj.record SET deleted_at = now() WHERE source_id = '2'")

    assert [one.source_id for one in as_app(url, lambda store: store.pending())] == ["1"]


def test_the_registry_run_declines_in_report_only_mode_and_otherwise_registers_with_the_pepper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asked to only report, the worker's run reads no pepper and registers nothing, and says so;
    asked to run, it hands the pepper the vault gave it to the registry.

    Delete this and a report-only run could write, or a real run could hash with something other
    than the install's pepper."""
    import brain.ops.join_key_pepper as pepper
    import brain.ops.schedule_runner as runner
    from brain.ops.leases import SealedSecret
    from brain.resolution.registry_store import Registered

    calls: list[tuple[str, str]] = []

    def ran(database_url: str, *, now: datetime, pepper: str, loop_factory: Any) -> Registered:
        calls.append((database_url, pepper))
        return Registered(read=1, minted=1)

    monkeypatch.setattr(runner, "run_registry_now", ran)
    monkeypatch.setattr(pepper, "pepper_vault", lambda address, token, role: object())
    monkeypatch.setattr(pepper, "read_pepper", lambda vault: SealedSecret(PEPPER))

    declined = runner.entity_resolution(AT, True, "postgresql://nowhere")
    assert runner.A_REGISTRY_RUN_IN_REPORT_ONLY_MODE_WRITES_NOTHING in declined
    assert calls == []

    said = runner.entity_resolution(AT, False, "postgresql://somewhere")
    assert calls == [("postgresql://somewhere", PEPPER)]
    assert said == Registered(read=1, minted=1).summary()
