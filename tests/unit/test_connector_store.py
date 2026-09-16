"""A connected source reaches its row and the ledger: the table, the trigger, the store, the lock.

`tests/unit/test_connector_routes.py` holds who may connect a source and what is said, over an
in-memory store. This file holds everything below it. The first half needs no server: it reads
`0057` as the SQL it renders, holds the trigger's subject and details to
`AuditRecorder.connector`'s, holds the migration's copied grammars to the live ones, and drives the
store over a stub session to prove the order a connection is written in, which is the whole of
`brain.ops.connector_store.THE_KEY_IS_KEPT_WHILE_THE_SOURCE_S_NAME_IS_LOCKED`.

The second half builds a database through `0057` and proves a connection reaches the system in the
places `docs/admin-console.md` names for a control: the row, the ledger entry its trigger appends
beside the credential write's, a chain that still verifies, a disconnection that is recorded and
cannot be undone by the application, and a second live connection refused by the table. **It skips
when there is no server**, which is every development machine here, and CI always has one.

Task ids: M42.6.5
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.audit.ledger import IDENTIFIER, AuditChain, AuditEntry
from brain.audit.record import AuditRecorder, ConnectorChange
from brain.connectors.manifest import DIGEST_CHARS
from brain.db import metadata
from brain.ops.connector_store import (
    CONNECT_LOCK_CLASS,
    ConnectorRecords,
    ConnectorTakenError,
    NotConnectedError,
    StoredConnections,
    connected_row,
    disconnection,
    every_live,
    live,
    lock_on,
)
from brain.ops.credential_write_store import StoredCredentialWrites
from brain.ops.credentials import CONNECTOR_NAME_PATTERN, Credentials, connector_key_slot
from brain.session import make_session_factory
from brain.tables import connector_connection as table_module
from brain.tables.connector_connection import ConnectorConnectionRow
from brain.tables.identity import PRINCIPAL_ID_CHARS
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_credentials import Vault
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

MIGRATION: Final = VERSIONS / "0057_connector_connection.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

#: A key nothing else could contain, searched for in everything the database holds.
KEY: Final = "SOURCE-KEY-SENTINEL-4b9d0a"
DIGEST: Final = "a" * 64
SETTINGS: Final = {"tenant_id": "11111111-2222-3333-4444-555555555555"}


def recorder() -> AuditRecorder:
    return AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: LONG_AGO
    )


def compiled(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())


# ------------------------------------------------------------ the migration and the model


def test_the_trigger_writes_the_subject_actor_and_details_the_recorder_writes() -> None:
    """Delete this and the entry a deployed database keeps and the entry `AuditRecorder` writes for
    a chain held anywhere else can come apart without a server to notice: a trigger that wrote the
    settings into the details, or named the actor from a setting, would pass every stubbed test.
    The body is read off the migration module that executes it."""
    connected = recorder().connector(connector="xero", change=ConnectorChange.CONNECTED)
    disconnected = recorder().connector(connector="xero", change=ConnectorChange.DISCONNECTED)
    body = " ".join(migration_module(MIGRATION).CONNECTOR_CONNECTION_TRIGGER_FUNCTION.split())

    assert connected.subject == "connector:xero"
    assert (connected.details, disconnected.details) == (
        {"change": "connected"},
        {"change": "disconnected"},
    )
    assert "v_subject text := 'connector:' || NEW.connector;" in body
    assert "v_details := jsonb_build_object('change', v_changes[i]);" in body
    assert (
        "v_changes := v_changes || 'connected'::text; v_actors := v_actors || NEW.connected_by"
        in (body)
    )
    assert (
        "ELSIF OLD.disconnected_at IS NULL AND NEW.disconnected_at IS NOT NULL THEN v_changes := "
        "v_changes || 'disconnected'::text; v_actors := v_actors || NEW.disconnected_by::text;"
    ) in body
    assert "v_seq, v_at, v_actors[i], 'connector', v_subject, v_ent_hash," in body
    assert "settings" not in body.replace("current_setting", "")


def test_the_migration_holds_the_live_grammars_and_widths_it_copied() -> None:
    """`0057` copies the source name grammar, the digest width, the identifier grammar and the
    principal width for the reason `0009` gives. Delete this and one side can change alone: a name
    the slot rule admits and the table refuses, or an actor the ledger cannot record."""
    migration = migration_module(MIGRATION)

    assert migration.CONNECTOR_NAME_PATTERN == CONNECTOR_NAME_PATTERN
    assert migration.CONNECTOR_CHARS == table_module.CONNECTOR_CHARS
    assert migration.DIGEST_CHARS == DIGEST_CHARS == 64
    assert migration.DIGEST_PATTERN == table_module.DIGEST_PATTERN
    assert migration.IDENTIFIER == IDENTIFIER
    assert migration.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS
    longest = "a" + "b" * 62
    assert re.fullmatch(CONNECTOR_NAME_PATTERN, longest)
    assert len(longest) < table_module.CONNECTOR_CHARS


def test_the_migration_builds_the_table_and_its_index_exactly_as_the_model_declares_them() -> None:
    """Compared as rendered DDL, for the reason `test_tables` compares 0002's. Delete this and the
    model can gain a column, lose a constraint or drop the partial index with the database built the
    old way, and the first write after deploy is where it shows."""
    emitted = squash(rendered("upgrade", MIGRATION))
    mapped = metadata.tables["ops.connector_connection"]

    assert squash(str(CreateTable(mapped).compile(dialect=DIALECT))) in emitted
    [index] = mapped.indexes
    assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted
    assert "WHERE disconnected_at IS NULL" in squash(
        str(CreateIndex(index).compile(dialect=DIALECT))
    )


def test_the_application_may_add_a_connection_and_mark_it_disconnected_and_nothing_else() -> None:
    """A record of who let this system read a source that could be edited is a record whose author
    moved after the fact. Delete this and an UPDATE on the settings or the actor, or a DELETE, can
    arrive with the table, or row-level security can be left off it, with every other test green."""
    emitted = squash(rendered("upgrade", MIGRATION))

    assert "ALTER TABLE ops.connector_connection ENABLE ROW LEVEL SECURITY" in emitted
    assert "GRANT SELECT, INSERT ON ops.connector_connection TO brain_app" in emitted
    assert (
        "GRANT UPDATE (disconnected_at, disconnected_by) ON ops.connector_connection TO brain_app"
        in emitted
    )
    assert "DELETE ON ops.connector_connection" not in emitted
    assert "GRANT UPDATE ON ops.connector_connection" not in emitted
    assert not re.search(r"GRANT [A-Z, ]*UPDATE[A-Z, ]* ON ops\.connector_connection", emitted)
    assert (
        "FOR INSERT TO brain_app WITH CHECK (disconnected_at IS NULL AND disconnected_by IS NULL)"
        in emitted
    )
    assert (
        "FOR UPDATE TO brain_app USING (disconnected_at IS NULL) WITH CHECK (disconnected_at IS "
        "NOT NULL)"
    ) in emitted
    assert (
        "CREATE TRIGGER connector_connection_is_audited AFTER INSERT OR UPDATE ON "
        "ops.connector_connection"
    ) in emitted


def test_nothing_the_table_or_the_store_takes_has_anywhere_to_put_a_key() -> None:
    """The table's columns and the statements' parameters, read off the objects. Delete this and a
    `credential` column, or a `key` parameter on the insert, can be added to make the screen more
    useful, and the key is in a table the application role reads."""
    statement = connected_row("xero", SETTINGS, DIGEST, "u_admin")

    assert set(ConnectorConnectionRow.__table__.columns.keys()) == {
        "id",
        "connector",
        "settings",
        "digest",
        "connected_by",
        "connected_at",
        "disconnected_by",
        "disconnected_at",
    }
    assert set(statement.compile().params) == {"connector", "settings", "digest", "connected_by"}
    assert set(disconnection("xero", "u_admin").compile().params) >= {"disconnected_by"}


# ------------------------------------------------------------------------ the store


class _Result:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar_one(self) -> Any:
        return self._value

    def mappings(self) -> _Result:
        return self

    def all(self) -> Any:
        return self._value


class _Session:
    """An `AsyncSession` in the shape the store uses, noting each statement and how it ended.

    `answers` maps a statement's first words to what executing it returns, so a test says whether
    a live connection exists and what an insert or an update hands back.
    """

    def __init__(self, log: list[str], answers: dict[str, Any]) -> None:
        self.log = log
        self.answers = answers

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def begin(self) -> _Transaction:
        return _Transaction(self.log)

    async def execute(self, statement: Any, *_: Any, **__: Any) -> _Result:
        text = compiled(statement)
        params = statement.compile().params
        if "set_config" in text:
            self.log.append(f"set {params['name']}")
            return _Result(None)
        if "pg_advisory_xact_lock" in text:
            self.log.append(f"lock {params['connector']}")
            return _Result(None)
        word = text.split(" ", 1)[0]
        self.log.append(word)
        answer = self.answers.get(word)
        if isinstance(answer, Exception):
            raise answer
        return _Result(answer)


class _Transaction:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def __aenter__(self) -> None:
        self.log.append("BEGIN")

    async def __aexit__(self, kind: object, *_: object) -> None:
        self.log.append("ROLLBACK" if kind is not None else "COMMIT")


def store_over(log: list[str], **answers: Any) -> StoredConnections:
    return StoredConnections(lambda: _Session(log, answers))  # type: ignore[arg-type]


def connect(store: StoredConnections, log: list[str]) -> Any:
    async def keep_key() -> datetime | None:
        log.append("keep key")
        return LONG_AGO

    return run(
        lambda: store.connect(
            connector="xero",
            settings=SETTINGS,
            digest=DIGEST,
            actor="u_admin",
            trace_id="t",
            ent_hash="e" * 32,
            keep_key=keep_key,
        )
    )


def test_a_connection_locks_the_source_checks_it_keeps_the_key_then_inserts_and_commits_once() -> (
    None
):
    """`THE_KEY_IS_KEPT_WHILE_THE_SOURCE_S_NAME_IS_LOCKED`, as the order of statements. The lock
    comes before the check so a second connection waits; the key comes after the check so a
    connected source's key is never replaced; the reach and trace are set before the insert so the
    trigger attributes the entry; and the ledger is touched only by the insert, last. Delete this
    and any of those can move with every route test still green."""
    log: list[str] = []
    made = connect(store_over(log, SELECT=None, INSERT=LONG_AGO), log)

    assert log == [
        "BEGIN",
        "lock xero",
        "SELECT",
        "keep key",
        "set brain.trace_id",
        "set brain.ent_hash",
        "INSERT",
        "COMMIT",
    ]
    assert (made.connector, made.connected_at, made.digest) == ("xero", LONG_AGO, DIGEST)


def test_a_source_already_connected_is_refused_before_its_key_is_kept_and_nothing_commits() -> None:
    """Delete this and a second connect writes a new key over the one the live row was connected
    with, and only then finds the source taken."""
    log: list[str] = []
    with pytest.raises(ConnectorTakenError):
        connect(store_over(log, SELECT="an-existing-id"), log)

    assert "keep key" not in log
    assert log[-1] == "ROLLBACK"


def test_a_refused_key_leaves_no_row_and_an_insert_that_collides_is_a_taken_source() -> None:
    """A refusal from the vault is raised inside the transaction, so it rolls back with no insert;
    and a unique index refusing the insert, which only a statement written by hand could cause, is
    the same answer as a connected source. Delete this and a vault refusal can be caught and the row
    inserted anyway, or a collision reach the person as a fault."""
    log: list[str] = []
    store = store_over(log, SELECT=None, INSERT=LONG_AGO)

    async def refused() -> datetime | None:
        raise RuntimeError("the vault refused")

    with pytest.raises(RuntimeError):
        run(
            lambda: store.connect(
                connector="xero",
                settings=SETTINGS,
                digest=DIGEST,
                actor="u_admin",
                trace_id="t",
                ent_hash="e" * 32,
                keep_key=refused,
            )
        )
    assert "INSERT" not in log and log[-1] == "ROLLBACK"

    collided: list[str] = []
    with pytest.raises(ConnectorTakenError):
        connect(
            store_over(collided, SELECT=None, INSERT=IntegrityError("insert", {}, Exception())),
            collided,
        )
    assert collided[-1] == "ROLLBACK"


def test_a_disconnection_is_attributed_then_marked_and_a_source_not_connected_is_refused() -> None:
    """Delete this and the update can run before the trace and reach are set, so the ledger entry is
    attributed to nobody, or a disconnect of nothing answers as though it happened."""
    log: list[str] = []
    at = run(
        lambda: store_over(log, UPDATE=LONG_AGO).disconnect(
            "xero", actor="u_admin", trace_id="t", ent_hash="e" * 32
        )
    )
    assert at == LONG_AGO
    assert log == ["BEGIN", "set brain.trace_id", "set brain.ent_hash", "UPDATE", "COMMIT"]

    nothing: list[str] = []
    with pytest.raises(NotConnectedError):
        run(
            lambda: store_over(nothing, UPDATE=None).disconnect(
                "xero", actor="u_admin", trace_id="t", ent_hash="e" * 32
            )
        )
    assert nothing[-1] == "ROLLBACK"


def test_the_statements_name_the_live_row_of_one_source_and_the_lock_is_not_the_ledger_s() -> None:
    """The check, the listing and the update each ask for the row with no disconnection, and the
    lock takes two keys, which PostgreSQL keeps apart from the ledger's one. Delete this and the
    check can match a disconnected row, so a source can never be connected again, or the lock can be
    rewritten onto the ledger's key and deadlock the credential record waiting inside it."""
    lock = compiled(lock_on("xero"))

    assert re.search(r"pg_advisory_xact_lock\(%\(lock_class\)s(::INTEGER)?, hashtext\(", lock)
    assert lock.count("%(") == 2
    # Each key of a two-key lock is 32-bit, so the class must fit one; the ledger's key does not.
    assert -(2**31) <= CONNECT_LOCK_CLASS < 2**31
    for statement in (live("xero"), every_live(), disconnection("xero", "u_admin")):
        assert "connector_connection.disconnected_at IS NULL" in compiled(statement)
    assert "ORDER BY ops.connector_connection.connector" in compiled(every_live())
    assert isinstance(store_over([]), ConnectorRecords)


# ------------------------------------------------------------------------ the database


@contextmanager
def through_0057(database: str) -> Iterator[str]:
    """A database with `0057` applied. Without pgvector, `retirable` stops at `0048`; `0049` is run
    for real, `0050` to `0053` are stamped, and `0054` to `0057` are run for real, as
    `tests/unit/test_agent_automation_store.py` runs `0055`."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "upgrade", "0049")
            migrate(database, "stamp", "0053")
            migrate(database, "upgrade", "0057")
        yield url


def entries(url: str) -> list[AuditEntry]:
    rows = sql(
        url,
        "SELECT seq, at, actor_id, action, subject, ent_hash, trace_id, details, prev_hash,"
        " entry_hash FROM obs.audit_entry ORDER BY seq",
    )
    names = (
        "seq",
        "at",
        "actor_id",
        "action",
        "subject",
        "ent_hash",
        "trace_id",
        "details",
        "prev_hash",
        "entry_hash",
    )
    return [AuditEntry(**dict(zip(names, row, strict=True))) for row in rows]


def test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record() -> None:
    """The control followed to the system, through the store and the credential store the
    application uses and as the role it uses.

    A connection leaves one row with its settings and digest, a `credential` entry for the key under
    the source's slot and a `connector` entry for the connection, in that order, both attributed to
    the person with the request's trace; a disconnection marks the row and appends a second
    `connector` entry; the chain verifies; the key is nowhere in the database; and the application
    role may not edit a connection's settings. Delete this and every one of those can be false in
    production while the stubbed tests above stay green. **Skips without a server.**"""
    with through_0057("brain_connector_connection") as url:

        async def walk() -> None:
            engine = app_engine(url)
            try:
                sessions = make_session_factory(engine)
                credentials = Credentials(
                    Vault(), environ={}, writes=StoredCredentialWrites(sessions)
                )
                store = StoredConnections(sessions)
                slot = connector_key_slot("xero")

                async def keep_key() -> datetime | None:
                    kept = await credentials.keep(
                        slot, KEY, actor="u_admin", trace_id="trace-connect", ent_hash="c" * 32
                    )
                    return kept.set_at

                await store.connect(
                    connector="xero",
                    settings=SETTINGS,
                    digest=DIGEST,
                    actor="u_admin",
                    trace_id="trace-connect",
                    ent_hash="c" * 32,
                    keep_key=keep_key,
                )
                assert [one.connector for one in await store.connected()] == ["xero"]
                await store.disconnect(
                    "xero", actor="u_other", trace_id="trace-disconnect", ent_hash="d" * 32
                )
                assert await store.connected() == ()
            finally:
                await engine.dispose()

        run(walk)
        rows = sql(
            url,
            "SELECT connector, settings, digest, connected_by, disconnected_by,"
            " disconnected_at IS NOT NULL FROM ops.connector_connection",
        )
        chain = entries(url)
        [(may_update_settings,)] = sql(
            url,
            "SELECT has_column_privilege('brain_app', 'ops.connector_connection', 'settings',"
            " 'UPDATE')",
        )
        everything = str(sql(url, "SELECT row_to_json(c) FROM ops.connector_connection c"))

    assert rows == [("xero", SETTINGS, DIGEST, "u_admin", "u_other", True)]
    assert [(one.action.value, one.subject, one.actor_id, one.details) for one in chain] == [
        ("credential", "credential:connector_keys.xero", "u_admin", {}),
        ("connector", "connector:xero", "u_admin", {"change": "connected"}),
        ("connector", "connector:xero", "u_other", {"change": "disconnected"}),
    ]
    assert [one.trace_id for one in chain[1:]] == ["trace-connect", "trace-disconnect"]
    assert AuditChain(chain).verify() is None
    assert KEY not in everything and KEY not in repr(chain)
    assert may_update_settings is False


def test_a_second_live_connection_is_refused_and_a_disconnection_cannot_be_undone() -> None:
    """The index and the update policy stand for a statement written by hand, which no lock
    serialises. Delete this and two rows can both say a source is connected, or the application role
    can clear a disconnection and make a source read as connected again with no ledger entry. The
    positive half is connecting the source again once it was disconnected, which is a new row.
    **Skips without a server.**"""
    insert = (
        "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
        " VALUES ('xero', '{}'::jsonb, %s, 'u_admin')"
    )
    with through_0057("brain_connector_connection_refused") as url:
        sql(url, insert, DIGEST)
        refused: list[str] = []
        try:
            sql(url, insert, DIGEST)
        except Exception as exc:
            refused.append(type(exc).__name__)
        sql(
            url,
            "UPDATE ops.connector_connection SET disconnected_at = now(),"
            " disconnected_by = 'u_admin'",
        )
        sql(url, insert, DIGEST)
        [(clears,)] = sql(
            url,
            "SELECT count(*) FROM ops.connector_connection WHERE disconnected_at IS NOT NULL",
        )

        async def undo() -> int:
            engine = app_engine(url)
            try:
                async with engine.begin() as connection:
                    from sqlalchemy import text

                    done = await connection.execute(
                        text(
                            "UPDATE ops.connector_connection SET disconnected_at = NULL,"
                            " disconnected_by = NULL WHERE disconnected_at IS NOT NULL"
                        )
                    )
                    return done.rowcount
            finally:
                await engine.dispose()

        undone = run(undo)

    assert refused == ["UniqueViolation"]
    assert clears == 1
    assert undone == 0
