"""The vault's audit log reaches the ledger: where a run starts, what it ships, and the trigger.

`tests/unit/test_vault_audit.py` holds the parser. The first half here needs no server: a log file
in a temporary directory read by `read_since`, `ship_once` over an in-memory store, and `0093` read
as the SQL it renders and the constants it copied. The second half builds a database through the
whole chain and ships a log into it as the application role, and proves each row appends exactly
the entry `AuditRecorder.vault_access` writes and the chain still verifies. **It skips without a
server**, which is every development machine here, and CI always has one.

Task ids: M31.3.2.4, M31.3.2.6
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from sqlalchemy import Table, create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateTable

from brain.audit.ledger import AuditChain
from brain.audit.record import CREDENTIAL_SLOT, CREDENTIAL_SLOT_CHARS, AuditRecorder
from brain.db import metadata
from brain.deployment import app_environment
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.vault_audit import Part, VaultAccess
from brain.ops.vault_audit_ship import (
    VAULT_AUDIT_LOG,
    StoredVaultAccess,
    VaultAuditShipError,
    access_rows,
    log_identity,
    read_since,
    run_vault_audit_ship_now,
    ship_once,
)
from brain.session import make_session_factory
from brain.tables import connector_sync as connector_sync_table
from brain.tables import vault_access as vault_access_table
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
MIGRATION = VERSIONS / "0093_vault_leases_and_audit.py"
REPO = Path(__file__).resolve().parents[2]

LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
ACCESSOR = "d" * 64


def line(path: str = "connector_keys/data/xero", operation: str = "read", **overrides: Any) -> str:
    # The operation sits inside `request`, as the vault logs it; a top-level key is ignored.
    entry: dict[str, Any] = {
        "time": "2019-03-04T09:00:00Z",
        "type": "response",
        "auth": {"accessor": f"hmac-sha256:{ACCESSOR}"},
        "request": {"operation": operation, "path": path},
    }
    entry.update(overrides)
    return json.dumps(entry) + "\n"


def a_log(tmp_path: Path, *lines: str) -> Path:
    log = tmp_path / "audit.log"
    log.write_bytes("".join(lines).encode())
    return log


class Memory(StoredVaultAccess):
    """`StoredVaultAccess` in memory, keyed as the table's unique constraint keys it."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, int], VaultAccess] = {}

    async def start_for(self, identity: str) -> int:
        return max((offset for ident, offset in self.rows if ident == identity), default=0)

    async def ship(self, identity: str, entries: Sequence[tuple[VaultAccess, int]]) -> None:
        for entry, offset in entries:
            self.rows.setdefault((identity, offset), entry)


# ------------------------------------------------------------------ reading from an offset
def test_a_read_returns_each_entry_with_the_offset_past_it_and_leaves_a_half_written_line(
    tmp_path: Path,
) -> None:
    """Chatter is stepped over but moves the offset; a line the vault is still writing is left
    for the next run. Delete this and a half-written line is shipped as malformed, failing every
    run until the vault finishes writing it."""
    chatter = line("sys/health")
    first, second = line(), line("providers/metadata/anthropic")
    log = a_log(tmp_path, first, chatter, second, '{"time": "2019')

    found = read_since(log, 0)

    assert [(one.slot, offset) for one, offset in found.entries] == [
        ("connector_keys/xero", len(first)),
        ("providers/anthropic", len(first) + len(chatter) + len(second)),
    ]
    assert found.reached == len(first) + len(chatter) + len(second)
    assert (found.malformed_at, found.more) == (None, False)


def test_a_line_that_is_not_an_entry_stops_the_read_there(tmp_path: Path) -> None:
    """Skipping it would make a tampered log read as a quiet one. Delete this and a corrupt line
    and everything after it are shipped as nothing."""
    first = line()
    log = a_log(tmp_path, first, "not json at all\n", line())
    found = read_since(log, 0)
    assert [offset for _, offset in found.entries] == [len(first)]
    assert found.malformed_at == len(first)


def test_a_truncated_log_is_read_from_its_start_and_a_bounded_read_says_more_waits(
    tmp_path: Path,
) -> None:
    """Delete this and a log shorter than the furthest offset shipped is never read again, and a
    years-old log is read in one run holding one transaction."""
    log = a_log(tmp_path, line(), line())
    assert len(read_since(log, 10_000).entries) == 2
    bounded = read_since(log, 0, max_bytes=1)
    assert (len(bounded.entries), bounded.more) == (1, True)


def test_a_file_is_known_by_its_first_line_and_has_no_identity_until_it_has_one(
    tmp_path: Path,
) -> None:
    """A log replaced by a new one must start from nothing. Delete this and the new file is read
    from the old file's offset, and its first entries never reach the ledger."""
    empty = a_log(tmp_path, '{"time"')
    assert log_identity(empty) is None
    one = log_identity(a_log(tmp_path, line()))
    other = log_identity(a_log(tmp_path, line("providers/data/anthropic")))
    assert one is not None and other is not None and one != other
    assert log_identity(tmp_path / "missing.log") is None


# ------------------------------------------------------------------------- one run
def test_a_run_ships_what_is_new_and_a_second_run_ships_nothing_twice(tmp_path: Path) -> None:
    """Where a run starts is what was shipped, so a restarted or second worker writes each entry
    once. Delete this and every run ships the whole log again."""
    log = a_log(tmp_path, line(), line(error="permission denied"))
    store = Memory()

    said = asyncio.run(ship_once(store, log))
    again = asyncio.run(ship_once(store, log))
    with log.open("ab") as more:
        more.write(line("webhooks/data/sub_one").encode())
    later = asyncio.run(ship_once(store, log))

    assert said == "2 vault entries shipped to the ledger"
    assert again == "0 vault entries shipped to the ledger"
    assert later == "1 vault entries shipped to the ledger"
    assert [one.refused for one in store.rows.values()] == [False, True, False]


def test_a_run_ships_what_came_before_a_malformed_line_and_then_fails_naming_it(
    tmp_path: Path,
) -> None:
    """Delete this and a corrupt log fails without shipping anything, or succeeds past the line."""
    store = Memory()
    log = a_log(tmp_path, line(), "garbage\n")
    with pytest.raises(VaultAuditShipError, match="not an entry"):
        asyncio.run(ship_once(store, log))
    assert len(store.rows) == 1


def test_a_missing_log_fails_and_an_empty_one_waits(tmp_path: Path) -> None:
    """A worker whose overlay mounts nothing is a failure the Scheduled jobs screen shows; a log
    with no complete entry yet is the ordinary state of a new vault. Delete this and the two read
    alike."""
    with pytest.raises(VaultAuditShipError, match="declared in ops/openbao/compose"):
        asyncio.run(ship_once(Memory(), tmp_path / "audit.log"))
    said = asyncio.run(ship_once(Memory(), a_log(tmp_path, "")))
    assert said == "the audit log holds no complete entry yet"


def test_a_worker_with_no_vault_ships_nothing_and_succeeds_saying_so() -> None:
    """Delete this and every install without a vault records a failed run every five minutes."""
    said = run_vault_audit_ship_now("postgresql+psycopg://nowhere/none", vault_address="")
    assert "names no secrets vault" in said


def test_the_log_path_is_where_the_worker_overlay_mounts_the_vaults_log_volume() -> None:
    """The volume's name is the vault project's name and its key, read from the vault's compose
    file, and the path is the overlay's mount. Delete this and the worker mounts a volume the
    vault never writes, and every run fails saying the log is missing."""
    vault = yaml.safe_load((REPO / "ops/openbao/compose.yml").read_text(encoding="utf-8"))
    assert f"{vault['name']}_brain-vault-logs" == app_environment.VAULT_AUDIT_VOLUME
    assert "brain-vault-logs" in vault["volumes"]
    assert VAULT_AUDIT_LOG == app_environment.VAULT_AUDIT_LOG


# ------------------------------------------------------------------------ the migration
def compiled(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())


def test_a_repeated_entry_is_refused_by_the_constraint_rather_than_doubled() -> None:
    """Delete this and two workers shipping the same stretch of log write each entry twice."""
    entry = VaultAccess(at=LONG_AGO, operation="read", part=Part.VALUE, slot="connector_keys/xero")
    sql = compiled(access_rows("e" * 64, [(entry, 10)]))
    assert f"ON CONFLICT ON CONSTRAINT {vault_access_table.ONCE} DO NOTHING" in sql
    table = cast(Table, vault_access_table.VaultAccessRow.__table__)
    assert vault_access_table.ONCE in {str(one.name) for one in table.constraints}


def test_the_migration_holds_the_live_words_and_grammars_it_copied() -> None:
    """Copied for `0009`'s reason. Delete this and one side changes alone: a lease ending the
    worker writes and the table refuses, or a slot the parser admits and the table refuses."""
    migration = migration_module(MIGRATION)
    assert migration.down_revision == "0091"
    assert (
        "lease IN (" + ", ".join(f"'{one}'" for one in connector_sync_table.LEASE_OUTCOMES) + ")"
    ) == migration.LEASE_OUTCOMES
    assert set(connector_sync_table.LEASE_OUTCOMES) == {one.value for one in LeaseOutcome}
    assert (
        "part IN (" + ", ".join(f"'{one}'" for one in vault_access_table.PARTS) + ")"
    ) == migration.PARTS
    assert set(vault_access_table.PARTS) == {one.value for one in Part}
    assert (migration.SLOT_GRAMMAR, migration.SLOT_CHARS) == (
        CREDENTIAL_SLOT,
        CREDENTIAL_SLOT_CHARS,
    )
    assert migration.OPERATION_PATTERN == vault_access_table.OPERATION_PATTERN
    assert migration.HEX_DIGEST == vault_access_table.HEX_DIGEST


def test_the_migration_builds_the_table_exactly_as_the_model_declares_it() -> None:
    """Compared as rendered DDL. Delete this and the model can drift from the table built."""
    expected = squash(
        str(CreateTable(metadata.tables["ops.vault_access"]).compile(dialect=DIALECT))
    )
    assert expected in squash(rendered("upgrade", MIGRATION))


def test_the_trigger_writes_the_subject_actor_and_details_the_recorder_writes() -> None:
    """Delete this and the entry a deployed database keeps and the one `AuditRecorder` would write
    part company: a detail the recorder never writes, or a subject the Audit screen cannot find."""
    migration = migration_module(MIGRATION)
    body = squash(migration.VAULT_ACCESS_TRIGGER_FUNCTION)
    entry = AuditRecorder(
        AuditChain(),
        actor_id=migration.VAULT_ACTOR,
        ent_hash="0" * 32,
        trace_id="t",
        clock=lambda: LONG_AGO,
    ).vault_access(
        slot="connector_keys/xero", operation="read", part="value", refused=True, identity=ACCESSOR
    )
    assert entry.subject == "credential:connector_keys.xero"
    assert "'credential:' || replace(NEW.slot, '/', '.')" in body
    assert set(entry.details) == {"operation", "part", "refused", "identity"}
    for key in entry.details:
        assert f"'{key}'" in body
    assert entry.details["refused"] == "true"
    assert "CASE WHEN NEW.refused THEN 'true' ELSE 'false' END" in body
    assert "'vault_access'" in body


def test_the_application_may_append_and_read_and_never_change_or_remove_a_row() -> None:
    """A record of who read a key that could be edited is a record whose author moved after the
    fact. Delete this and UPDATE or DELETE can arrive with the table, or RLS be left off."""
    migration = migration_module(MIGRATION)
    assert migration.GRANTS == ("GRANT SELECT, INSERT ON ops.vault_access TO brain_app",)
    assert "ALTER TABLE ops.vault_access ENABLE ROW LEVEL SECURITY" in migration.RLS
    upgrade = squash(rendered("upgrade", MIGRATION))
    assert "UPDATE ON ops.vault_access" not in upgrade
    assert "DELETE ON ops.vault_access" not in upgrade


# ------------------------------------------------------------------------ with a server
@pytest.mark.needs_db
def test_a_shipped_entry_appends_exactly_the_recorders_entry_and_the_chain_holds(
    tmp_path: Path,
) -> None:
    """M31.3.2.6 end to end, as the role the application logs in with: one row per entry, one
    `vault_access` ledger entry per row whose subject, actor and details are the recorder's, a
    second run appending nothing, the chain verifying, and the row not editable. **Skips without a
    server.**"""
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import run, sql
    from tests.unit.test_automation_owner_store import app_engine
    from tests.unit.test_credential_writes import entries

    log = a_log(tmp_path, line(), line("auth/token/create/connector-run", operation="update"))
    with retirable("brain_vault_access") as url:
        if not has_pgvector(url):
            pytest.skip("0093 needs the whole chain, which needs pgvector")

        async def ship() -> tuple[str, str]:
            engine = app_engine(url)
            try:
                store = StoredVaultAccess(make_session_factory(engine))
                return await ship_once(store, log), await ship_once(store, log)
            finally:
                await engine.dispose()

        said, again = run(ship)
        rows = sql(
            url, "SELECT slot, part, refused, identity FROM ops.vault_access ORDER BY log_offset"
        )
        chain = entries(url)
        [(may_update,)] = sql(
            url, "SELECT has_table_privilege('brain_app', 'ops.vault_access', 'UPDATE')"
        )

    assert (said, again) == (
        "2 vault entries shipped to the ledger",
        "0 vault entries shipped to the ledger",
    )
    assert rows == [
        ("connector_keys/xero", "value", False, ACCESSOR),
        ("token_role/connector_run", "lease", False, ACCESSOR),
    ]
    recorder = AuditRecorder(
        AuditChain(),
        actor_id="secrets_vault",
        ent_hash="0" * 32,
        trace_id="t",
        clock=lambda: LONG_AGO,
    )
    expected = [
        recorder.vault_access(
            slot="connector_keys/xero",
            operation="read",
            part="value",
            refused=False,
            identity=ACCESSOR,
        ),
        recorder.vault_access(
            slot="token_role/connector_run",
            operation="update",
            part="lease",
            refused=False,
            identity=ACCESSOR,
        ),
    ]
    shipped = [one for one in chain if one.action.value == "vault_access"]
    assert [(one.subject, one.actor_id, one.details) for one in shipped] == [
        (one.subject, "secrets_vault", one.details) for one in expected
    ]
    assert AuditChain(chain).verify() is None
    assert may_update is False
