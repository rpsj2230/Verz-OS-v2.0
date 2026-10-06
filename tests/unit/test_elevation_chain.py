"""The second chain: approved elevations in `obs.elevation_entry`, walked and anchored on their own.

The pure half holds `0209`'s copies to the ledger's grammars and to the console's
`ELEVATION_ACTIONS`, and the table to its model. The server half approves elevation requests on
PostgreSQL at head and reads both chains back through `brain.audit.chain_check`, as the anchor route
and the verification walk read them, and asks `brain.console.elevation.chain_findings` about the
pair as stored.

Task ids: M33.7.1.3
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.app import Settings, create_app
from brain.audit import ledger
from brain.audit.chain_check import StoredLedgerSequence, check_ledger, entry_of
from brain.audit.ledger import AuditAction, AuditChain, AuditEntry
from brain.console.elevation import (
    A_SECOND_CHAIN_IS_A_SECOND_ANCHOR_AND_NOT_A_STRONGER_LEDGER,
    ELEVATION_ACTIONS,
    ELEVATION_CHAIN,
    chain_findings,
)
from brain.db import metadata
from brain.docs_routes import ELEVATION_ANCHOR_PATH
from brain.session import make_session_factory
from brain.tables import audit
from brain.tables.audit import AuditEntryRow, ElevationEntryRow
from brain.tables.elevation import ElevationDecision
from brain.tables.identity import one_of
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_entitlement_store import a_principal
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0209_elevation_chain.py"
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect


def module() -> Any:
    return migration_module(MIGRATION)


# ------------------------------------------------------------------------ the migration
def test_the_migration_builds_the_elevation_chain_exactly_as_the_model_declares_it() -> None:
    """Compared on rendered DDL. Delete this and the model can declare the one-action check or the
    fork refusal while the database never has it."""
    emitted = squash(rendered("upgrade", MIGRATION))
    table = metadata.tables["obs.elevation_entry"]
    assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted
    for index in table.indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


def test_the_grammars_the_migration_copies_are_the_ledgers_and_the_consoles() -> None:
    """Each copy against what it copies, from outside it. Delete this and an identifier, a digest
    or the one action can be admitted by the table and refused by `AuditEntry`, so the walk calls
    an honest entry altered, or the chain can hold an action the console says it never holds."""
    m = module()
    assert (m.IDENTIFIER, m.ENT_HASH, m.TRACE_ID, m.DIGEST) == (
        ledger.IDENTIFIER,
        ledger.ENT_HASH,
        ledger.TRACE_ID,
        ledger.DIGEST,
    )
    assert m.SUBJECT == audit.ELEVATION_SUBJECT_PATTERN
    assert (
        frozenset(audit.ELEVATION_CHAIN_ACTIONS) == ELEVATION_ACTIONS == {AuditAction.BREAK_GLASS}
    )
    assert one_of("action", ELEVATION_ACTIONS) == m.ACTIONS
    assert AuditAction.BREAK_GLASS.value == m.ACTION
    assert ElevationDecision.APPROVED.value == m.APPROVED
    assert "own cadence" in A_SECOND_CHAIN_IS_A_SECOND_ANCHOR_AND_NOT_A_STRONGER_LEDGER


def test_the_chain_is_appended_and_never_amended_and_0104s_function_is_left_alone() -> None:
    """Read off the emitted statements. Delete this and the application can be granted an UPDATE
    on the chain, a statement trigger can be left unexecuted, the second copy can fire on other
    statements than `0104`'s, or 0209 can quietly replace `0104`'s function and take break-glass
    sessions off the main ledger the Audit screen reads."""
    m = module()
    up = squash(rendered("upgrade", MIGRATION))
    down = squash(rendered("downgrade", MIGRATION))
    assert "GRANT SELECT, INSERT ON obs.elevation_entry TO brain_app" in up
    assert "ALTER TABLE obs.elevation_entry ENABLE ROW LEVEL SECURITY" in up
    for verb, name in (("UPDATE", "amendment"), ("DELETE", "removal"), ("TRUNCATE", "truncation")):
        assert (
            f"CREATE TRIGGER elevation_entry_refuses_{name} BEFORE {verb} ON obs.elevation_entry"
            in up
        )
    assert "CREATE FUNCTION gate.record_elevation_chain()" in up
    assert "record_break_glass" not in up
    shipped = migration_module(VERSIONS / "0104_compliance_record_and_decision_entries.py")
    assert "AFTER INSERT OR UPDATE OF decision ON gate.elevation_request" in squash(
        shipped.BREAK_GLASS_TRIGGER
    )
    assert (
        "CREATE TRIGGER elevation_request_is_chained AFTER INSERT OR UPDATE OF decision ON "
        "gate.elevation_request" in up
    )
    assert "INSERT INTO obs.elevation_entry" in squash(m.CHAIN_FUNCTION)
    assert "obs.audit_entry " not in squash(m.CHAIN_FUNCTION).replace("obs.audit_entry_hash", "")
    assert "DROP TRIGGER IF EXISTS elevation_request_is_chained ON gate.elevation_request" in down
    assert "DROP FUNCTION IF EXISTS gate.record_elevation_chain()" in down
    assert "record_break_glass" not in down


# ------------------------------------------------------------------------ on a server
@pytest.fixture
def install() -> Iterator[str]:
    with at_head("brain_elevation_chain") as url:
        for pid in ("u_requester", "u_approver"):
            a_principal(url, pid)
        yield url


def requested(url: str) -> str:
    [(request_id,)] = sql(
        url,
        "INSERT INTO gate.elevation_request (principal_id, capability, scope_slug, reason,"
        " explanation, hours) VALUES ('u_requester', 'read:client.name', 'web_all',"
        " 'incident_response', 'the portal is down', 2) RETURNING id",
    )
    return str(request_id)


def approved(url: str, request_id: str) -> None:
    # A person holds one live grant of a capability, so the one an earlier approval wrote is
    # retired first, as the store's own approval retires it.
    sql(
        url,
        "UPDATE gate.capability_grant SET deleted_at = now()"
        " WHERE principal_id = 'u_requester' AND deleted_at IS NULL",
    )
    [(grant_id,)] = sql(
        url,
        "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by, reason)"
        " VALUES ('u_requester', 'read:client.name', '{\"clauses\": []}', 'u_approver',"
        " 'an elevation') RETURNING id",
    )
    sql(
        url,
        "UPDATE gate.elevation_request SET decision = 'approved', decided_by = 'u_approver',"
        " decided_at = now(), grant_id = %s, lapses_at = now() + interval '1 hour'"
        " WHERE id = %s",
        grant_id,
        request_id,
    )


def denied(url: str, request_id: str) -> None:
    sql(
        url,
        "UPDATE gate.elevation_request SET decision = 'denied', decided_by = 'u_approver',"
        " decided_at = now() WHERE id = %s",
        request_id,
    )


def stored(url: str) -> tuple[list[AuditEntry], list[AuditEntry], Any, Any]:
    """Both chains read through `StoredLedgerSequence` as the application role, and both walked."""

    async def go() -> tuple[list[AuditEntry], list[AuditEntry], Any, Any]:
        built = app_engine(url)
        try:
            sessions = make_session_factory(built)
            main = StoredLedgerSequence(sessions)
            second = StoredLedgerSequence(sessions, ElevationEntryRow)
            main_rows = await main.after(None, limit=10_000)
            second_rows = await second.after(None, limit=10_000)
            at = datetime.now(UTC)
            return (
                [one for one in map(entry_of, main_rows) if one is not None],
                [one for one in map(entry_of, second_rows) if one is not None],
                await check_ledger(main, at=at),
                await check_ledger(second, at=at),
            )
        finally:
            await built.dispose()

    return run(go)


def test_an_approval_is_one_entry_in_the_elevation_chain_and_its_twin_in_the_main_one(
    install: str,
) -> None:
    """**M33.7.1.3 on PostgreSQL.** Two approvals and a denial: the elevation chain holds exactly
    the two sessions the approvals opened, each by its approver with `AuditRecorder.break_glass`'s
    three names, and walks as a continuous chain through the same reader as the main ledger; the
    main ledger holds the requests, their decisions and the same two sessions as twins; and
    `chain_findings` about the stored pair finds nothing. Delete this and approvals can write their
    sessions where the separate anchor never sees them, or the two copies can say different things
    with every chain verifying."""
    first, second, refused = requested(install), requested(install), requested(install)
    approved(install, first)
    denied(install, refused)
    approved(install, second)

    main, elevations, main_walk, elevation_walk = stored(install)

    assert [(one.action, one.subject, one.actor_id) for one in elevations] == [
        (AuditAction.BREAK_GLASS, f"session:{first}", "u_approver"),
        (AuditAction.BREAK_GLASS, f"session:{second}", "u_approver"),
    ]
    assert dict(elevations[0].details) == {
        "reason": "incident_response",
        "principal": "u_requester",
        "authorised_by": "u_approver",
    }
    # The main ledger keeps `0104`'s copy of each, so the Audit screen shows both sessions too.
    twins = [(one.subject, one.actor_id) for one in main if one.action is AuditAction.BREAK_GLASS]
    assert twins == [(one.subject, one.actor_id) for one in elevations]
    assert {one.action for one in main} >= {AuditAction.ELEVATION}
    assert chain_findings(main=AuditChain(main), elevation=AuditChain(elevations)) == ()
    assert (elevation_walk.continuous, elevation_walk.entries_walked) == (True, 2)
    assert elevation_walk.head == elevations[-1].entry_hash
    assert main_walk.continuous


def test_an_approval_decided_again_is_not_copied_twice(install: str) -> None:
    """`0104`'s own condition, held by the copy: a statement setting an approved request's decision
    to approved again writes no second session to either chain. Delete this and the elevation
    chain's head can move for a decision nobody made, and its twin count stops matching the main
    chain's."""
    request_id = requested(install)
    approved(install, request_id)
    sql(
        install,
        "UPDATE gate.elevation_request SET decision = 'approved' WHERE id = %s",
        request_id,
    )
    assert sql(
        install,
        "SELECT (SELECT count(*) FROM obs.elevation_entry),"
        " (SELECT count(*) FROM obs.audit_entry WHERE action = 'break_glass')",
    ) == [(1, 1)]


def test_the_elevation_chain_refuses_an_edit_a_removal_and_a_truncation_by_anybody(
    install: str,
) -> None:
    """The statement triggers, as the table's owner, who holds every privilege. Delete this and the
    chain's tail can be removed by whoever can connect as the owner, which only an anchor would then
    notice."""
    approved(install, requested(install))
    for statement in (
        "UPDATE obs.elevation_entry SET actor_id = 'u_other'",
        "DELETE FROM obs.elevation_entry",
        "TRUNCATE obs.elevation_entry",
    ):
        with pytest.raises(psycopg.errors.RestrictViolation):
            sql(install, statement)
    assert sql(install, "SELECT count(*) FROM obs.elevation_entry") == [(1,)]


def test_the_elevation_chains_head_and_its_digests_are_published_on_their_own_route(
    install: str,
) -> None:
    """The route the anchor workflow reads, over this database: the chain's own name, its newest
    position and digest, the digest at a position, and none past the end. Delete this and the
    separate chain has no separate anchor, which is the one thing it was for."""
    approved(install, requested(install))
    approved(install, requested(install))
    [(seq, head)] = sql(
        install, "SELECT seq, entry_hash FROM obs.elevation_entry ORDER BY seq DESC LIMIT 1"
    )
    [(first,)] = sql(install, "SELECT entry_hash FROM obs.elevation_entry WHERE seq = 0")

    async def go() -> tuple[Any, Any, Any, Any]:
        built = app_engine(install)
        try:
            app = create_app(Settings(env="development"))
            app.state.db_sessions = make_session_factory(built)
            import httpx

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as c:
                return (
                    await c.get(ELEVATION_ANCHOR_PATH),
                    await c.get(f"{ELEVATION_ANCHOR_PATH}/0"),
                    await c.get(f"{ELEVATION_ANCHOR_PATH}/40"),
                    await c.get("/api/audit/anchor"),
                )
        finally:
            await built.dispose()

    anchored, at_zero, past, main = run(go)

    assert anchored.status_code == 200, anchored.text
    body = anchored.json()
    assert (body["chain"], body["seq"], body["head"]) == (ELEVATION_CHAIN, seq, head)
    assert set(body) == {"chain", "head", "seq", "taken_at", "version"}
    assert at_zero.json() == {"seq": 0, "head": first}
    assert past.json() == {"seq": 40, "head": None}
    assert main.json()["chain"] == "main" and main.json()["head"] != head


def test_a_process_with_no_database_publishes_no_elevation_head() -> None:
    """The main route's rule, held for the second. Delete this and a process that cannot see its
    chain anchors "empty", which no truncation would ever contradict."""
    built = create_app(Settings(env="development"))
    with TestClient(built, raise_server_exceptions=False) as c:
        built.state.db_sessions = None
        assert c.get(ELEVATION_ANCHOR_PATH).status_code == 503
        assert c.get(f"{ELEVATION_ANCHOR_PATH}/0").status_code == 503


def test_the_reader_reads_the_table_it_is_handed() -> None:
    """The two chains are two tables read by one reader. Delete this and the second reader can
    quietly read the main ledger, whose head the separate anchor would then publish twice."""
    sessions: Any = object()
    assert StoredLedgerSequence(sessions)._table is AuditEntryRow
    assert StoredLedgerSequence(sessions, ElevationEntryRow)._table is ElevationEntryRow
