"""A source's steward is named and recorded, and every grant somebody makes to themselves is kept.

The first half needs no server: the migration's copied grammars held to the live ones, and the
order in which a source's steward is decided. The second half builds a database at head and drives
`0167`'s tables as the application role, with the transaction attributed as a route attributes it:
a grant to oneself is recorded by the database whichever way it was made, a grant to somebody else
is not, the record outlives the grant's retirement, a pack brings its capabilities and name, and
naming a steward writes the row, its ledger entry, and refuses a row that names somebody else as
the person who named it. **It skips when there is no server**, and CI always has one.

Task ids: M7.7.2
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, Final

import psycopg
import pytest
from sqlalchemy import String

from brain.audit.ledger import IDENTIFIER
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.ops.stewardship_store import NamedSteward, StoredStewardship, source_steward
from brain.session import make_session_factory
from brain.tables.connector_connection import CONNECTOR_CHARS
from brain.tables.gate import CAPABILITY_CHARS, CapabilityPackRow
from brain.tables.identity import PRINCIPAL_ID_CHARS
from brain.tables.stewardship import PACK_NAME_CHARS, SelfGrantKind
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_tables import VERSIONS, migration_module

MIGRATION: Final = VERSIONS / "0167_stewards_and_self_grants.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

UNRESTRICTED: Final = json.dumps({"clauses": []})


# ------------------------------------------------------------ the migration and the model
def test_the_migration_copies_the_live_grammars_and_widths() -> None:
    """Delete this and the table `0167` builds can drift from the names, identifiers and widths
    the rest of the product writes, so a steward or a self-grant the product produces is refused
    by a constraint nobody updated."""
    migration = migration_module(MIGRATION)
    assert migration.CONNECTOR_NAME_PATTERN == CONNECTOR_NAME_PATTERN
    assert migration.IDENTIFIER == IDENTIFIER
    assert migration.CONNECTOR_CHARS == CONNECTOR_CHARS
    assert migration.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS
    assert migration.CAPABILITY_CHARS == CAPABILITY_CHARS
    assert migration.PACK_NAME_CHARS == PACK_NAME_CHARS
    # Held against the pack table rather than against itself, so a pack name that fits there
    # always fits here.
    column = CapabilityPackRow.__table__.c.name
    assert isinstance(column.type, String) and column.type.length == PACK_NAME_CHARS
    listed = set(re.findall(r"'([a-z]+)'", migration.KINDS))
    assert listed == {one.value for one in SelfGrantKind}


def _named(steward: str) -> NamedSteward:
    return NamedSteward(
        connector="freshdesk", steward_id=steward, named_by="u_admin", named_at=LONG_AGO
    )


def test_a_source_is_stewarded_by_whoever_was_named_else_the_data_steward_else_its_connector() -> (
    None
):
    """`A_SOURCE_IS_STEWARDED_FROM_THE_MOMENT_IT_IS_CONNECTED`: a named steward wins, then the
    install's data steward, then the person who connected it. Delete this and a source nobody
    named anybody for is stewarded by nobody, so a grant reaching it is told to nobody."""
    assert (
        source_steward(
            "freshdesk",
            named={"freshdesk": _named("u_named")},
            data_steward="u_data",
            connected_by="u_c",
        )
        == "u_named"
    )
    assert (
        source_steward("freshdesk", named={}, data_steward="u_data", connected_by="u_c") == "u_data"
    )
    assert source_steward("freshdesk", named={}, data_steward=None, connected_by="u_c") == "u_c"
    assert (
        source_steward(
            "freshdesk", named={"hubspot": _named("u_named")}, data_steward=None, connected_by="u_c"
        )
        == "u_c"
    )


# ------------------------------------------------------------------ against a database
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_stewardship_store") as url:
        for pid in ("u_admin", "u_other", "u_steward"):
            sql(
                url,
                "INSERT INTO auth.principal (id, kind, employment, display_name) "
                "VALUES (%s, 'human', 'staff', %s) ON CONFLICT (id) DO NOTHING",
                pid,
                pid,
            )
        yield url


def as_app(url: str, actor: str | None) -> psycopg.Connection[Any]:
    """The application role, with the transaction attributed to `actor` as a route does it."""
    conn = psycopg.connect(url, autocommit=True)
    conn.execute("SET ROLE brain_app")
    if actor is not None:
        conn.execute("SELECT set_config('brain.actor_id', %s, false)", (actor,))
    return conn


def _grant(url: str, *, principal: str, actor: str | None, granted_by: str, capability: str) -> str:
    with as_app(url, actor) as conn:
        row = conn.execute(
            "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by,"
            " reason) VALUES (%s, %s, %s, %s, 'a test') RETURNING id",
            (principal, capability, UNRESTRICTED, granted_by),
        ).fetchone()
    assert row is not None
    return str(row[0])


def _recorded(url: str, grant_id: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT kind, principal_id, capabilities, scope, pack FROM gate.self_grant "
        "WHERE grant_id = %s",
        grant_id,
    )


@pytest.mark.needs_db
def test_a_grant_to_oneself_is_recorded_and_a_grant_to_somebody_else_is_not(install: str) -> None:
    """The positive case and its sibling, both as the application role with the actor set: the
    administrator granting themselves `read:ticket.*` is kept with the capability and the scope,
    and the same grant to somebody else leaves nothing. Delete this and the triggers can record
    every grant, which buries the one a steward must see, or none."""
    mine = _grant(
        install,
        principal="u_admin",
        actor="u_admin",
        granted_by="u_admin",
        capability="read:ticket.*",
    )
    theirs = _grant(
        install,
        principal="u_other",
        actor="u_admin",
        granted_by="u_admin",
        capability="read:ticket.*",
    )

    assert _recorded(install, mine) == [
        ("capability", "u_admin", ["read:ticket.*"], {"clauses": []}, None)
    ]
    assert _recorded(install, theirs) == []


@pytest.mark.needs_db
def test_the_actor_decides_and_granted_by_answers_only_when_nobody_is_attributed(
    install: str,
) -> None:
    """A grant written as somebody else's act (`granted_by` names the principal, the actor does not)
    is not a self-grant, and with no attribution at all the row's own `granted_by` decides. Delete
    this and a product appointment such as the data steward's, written with a fixed grantor, reads
    as the appointer granting themselves, or an unattributed self-grant slips through."""
    appointed = _grant(
        install,
        principal="u_steward",
        actor="u_admin",
        granted_by="u_steward",
        capability="read:client.*",
    )
    unattributed = _grant(
        install, principal="u_other", actor=None, granted_by="u_other", capability="read:client.*"
    )
    assert _recorded(install, appointed) == []
    assert [row[1] for row in _recorded(install, unattributed)] == ["u_other"]


@pytest.mark.needs_db
def test_the_record_outlives_the_grant_it_was_made_on(install: str) -> None:
    """A grant made to oneself and removed a moment later is still on record, because the grant's
    own row is hidden from the application once retired (`0045`). Delete this and the misuse a
    steward exists to see, a grant made, used and removed, leaves nothing to be told of."""
    mine = _grant(
        install,
        principal="u_admin",
        actor="u_admin",
        granted_by="u_admin",
        capability="read:deal.*",
    )
    with as_app(install, "u_admin") as conn:
        conn.execute(
            "UPDATE gate.capability_grant SET deleted_at = statement_timestamp() WHERE id = %s",
            (mine,),
        )
    assert sql(
        install, "SELECT deleted_at IS NOT NULL FROM gate.capability_grant WHERE id = %s", mine
    ) == [(True,)]
    assert len(_recorded(install, mine)) == 1


@pytest.mark.needs_db
def test_a_pack_assigned_to_oneself_is_recorded_with_its_capabilities_and_name(
    install: str,
) -> None:
    """The second way a grant reaches a person. Delete this and a self-grant made through a pack
    is invisible to every steward whose thing the pack reaches."""
    [(pack_id,)] = sql(
        install,
        "INSERT INTO gate.capability_pack (name, description, capabilities) VALUES (%s, %s, %s) "
        "RETURNING id",
        "support_desk",
        "a pack a test assigned",
        ["read:ticket.*", "read:contact.*"],
    )
    with as_app(install, "u_admin") as conn:
        row = conn.execute(
            "INSERT INTO gate.capability_pack_assignment (principal_id, pack_id, scope, granted_by,"
            " reason) VALUES ('u_admin', %s, %s, 'u_admin', 'a test') RETURNING id",
            (pack_id, UNRESTRICTED),
        ).fetchone()
    assert row is not None
    assert _recorded(install, str(row[0])) == [
        ("pack", "u_admin", ["read:ticket.*", "read:contact.*"], {"clauses": []}, "support_desk")
    ]


def _store(url: str) -> Any:
    async def go() -> Any:
        engine = app_engine(url)
        try:
            store = StoredStewardship(make_session_factory(engine))
            named = await store.name(
                "freshdesk", "u_steward", by="u_admin", ent_hash="0" * 32, trace_id="t-steward"
            )
            again = await store.named_stewards()
            grants = await store.self_grants(LONG_AGO)
            return named, again, grants
        finally:
            await engine.dispose()

    return run(go)


@pytest.mark.needs_db
def test_naming_a_steward_writes_the_row_and_its_ledger_entry_and_is_read_back(
    install: str,
) -> None:
    """Through the store, as the application role: the row is written, the ledger holds a
    `connector` entry with `change: steward` naming the steward, and `named_stewards` reads the
    newest naming back; `self_grants` reads the grants made to oneself above. Delete this and a
    steward can be named with nothing in the ledger, or read back as somebody else."""
    named, again, grants = _store(install)

    assert (named.connector, named.steward_id, named.named_by) == (
        "freshdesk",
        "u_steward",
        "u_admin",
    )
    assert again["freshdesk"].steward_id == "u_steward"
    entries = sql(
        install,
        "SELECT actor_id, action, subject, details FROM obs.audit_entry "
        "WHERE subject = 'connector:freshdesk' ORDER BY seq DESC LIMIT 1",
    )
    assert entries == [
        (
            "u_admin",
            "connector",
            "connector:freshdesk",
            {"change": "steward", "steward": "u_steward"},
        )
    ]
    assert {one.principal_id for one in grants} >= {"u_admin", "u_other"}
    assert all(one.principal_id != "u_steward" for one in grants)


@pytest.mark.needs_db
def test_a_steward_row_naming_somebody_else_as_its_namer_is_refused(install: str) -> None:
    """`0167`'s insert policy: `named_by` must be the actor the transaction is attributed to.
    Delete this and a row can record that somebody else named the steward, which is the ledger
    entry's actor forged by a column."""
    with (
        as_app(install, "u_admin") as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(
            "INSERT INTO ops.connector_steward (connector, steward_id, named_by) "
            "VALUES ('hubspot', 'u_steward', 'u_other')"
        )
