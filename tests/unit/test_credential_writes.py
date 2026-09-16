"""A credential write reaches the ledger: the table, the trigger, the store and the wiring.

`tests/unit/test_credentials.py` holds the order inside `Credentials.keep`, and this file holds
everything below it. The first half needs no server: it reads `0054` as the SQL it renders and
the functions it defines, holds the trigger's subject and details to `AuditRecorder.credential`'s,
holds the migration's copied grammars to the live ones, and drives the store over a stub session.

The second half builds a database through `0054` and proves a write reaches the system in the
places M27.8.17 names for a control: the row, the one ledger entry its trigger appends, a chain
that still verifies, and a process built by the real lifespan recording what its store keeps. **It
skips when there is no server**, which is every development machine here, and CI always has one.

Task ids: M27.8.7
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateTable

from brain.app import Settings, create_app
from brain.audit.ledger import IDENTIFIER, AuditChain, AuditEntry
from brain.audit.record import (
    CREDENTIAL_SLOT,
    CREDENTIAL_SLOT_CHARS,
    AuditRecorder,
    credential_subject_id,
)
from brain.db import metadata
from brain.firstrun import GRANTED_BY
from brain.ops.credential_write_store import (
    StoredCredentialWrites,
    credential_writes_for,
    written,
)
from brain.ops.credentials import SLOTS, Credentials, CredentialWrites
from brain.session import make_session_factory
from brain.tables.credential import CredentialWriteRow
from brain.tables.identity import PRINCIPAL_ID_CHARS
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_credentials import KEY, Vault
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

MIGRATION = VERSIONS / "0054_credential_and_retention_audit.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


def recorder() -> AuditRecorder:
    return AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: LONG_AGO
    )


def compiled(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())


# ------------------------------------------------------------ the subject and the trigger


def test_the_trigger_writes_the_subject_actor_and_details_the_recorder_writes() -> None:
    """Delete this and the entry a deployed database keeps and the entry `AuditRecorder` writes for
    a chain held anywhere else can come apart without a server to notice: a trigger that wrote the
    raw path would be refused by the subject grammar on every write, and one that wrote a detail
    would put something beside the slot that the recorder never does. The body is read off the
    migration module that executes it."""
    entry = recorder().credential(slot="providers/anthropic")
    body = " ".join(migration_module(MIGRATION).CREDENTIAL_WRITE_TRIGGER_FUNCTION.split())

    assert entry.subject == "credential:providers.anthropic"
    assert entry.details == {}
    assert "v_subject text := 'credential:' || replace(NEW.slot, '/', '.');" in body
    assert "v_details jsonb := '{}'::jsonb;" in body
    assert "v_seq, v_at, NEW.written_by, 'credential', v_subject, v_ent_hash," in body
    assert "VALUES (v_seq, v_at, NEW.written_by, 'credential', v_subject," in body


def test_a_slot_s_subject_id_can_be_read_back_and_a_slot_that_would_share_one_is_refused() -> None:
    """The rewrite is reversible only because a slot holds no `.`. Delete this and a slot with a
    dot can be recorded under the subject of the slot with a slash in that place, so a key
    replaced in one reads as a key replaced in the other; or a slot longer than an identifier is
    kept and then refused by the ledger on every write. The positive half is every real slot."""
    for slot in SLOTS:
        ident = credential_subject_id(slot)
        assert ident.replace(".", "/") == slot
        assert recorder().credential(slot=slot).subject == f"credential:{ident}"
    longest = "providers/" + "k" * (CREDENTIAL_SLOT_CHARS - len("providers/"))
    assert credential_subject_id(longest) == longest.replace("/", ".")
    for refused in ("providers.anthropic/x", "providers", "Providers/anthropic", longest + "k"):
        with pytest.raises(ValueError, match="is not a credential slot"):
            credential_subject_id(refused)


def test_the_migration_holds_the_live_grammars_and_widths_it_copied() -> None:
    """`0054` copies the slot grammar, its width, the identifier grammar and the principal width
    for the reason `0009` gives. Delete this and one side can change alone: a slot the recorder
    admits and the table refuses, or a width the ledger's identifier cannot hold."""
    migration = migration_module(MIGRATION)

    assert migration.SLOT_GRAMMAR == CREDENTIAL_SLOT
    assert migration.SLOT_CHARS == CREDENTIAL_SLOT_CHARS
    assert migration.IDENTIFIER == IDENTIFIER
    assert IDENTIFIER.endswith(f"{{1,{CREDENTIAL_SLOT_CHARS}}}$")
    assert migration.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS


def test_the_migration_builds_the_table_exactly_as_the_model_declares_it() -> None:
    """Compared as rendered DDL, for the reason `test_tables` compares 0002's. Delete this and the
    model can gain a column, lose a constraint or change a width with the database built the old
    way, and the first write after deploy is where it shows."""
    expected = squash(
        str(CreateTable(metadata.tables["ops.credential_write"]).compile(dialect=DIALECT))
    )
    assert expected in squash(rendered("upgrade", MIGRATION))


def test_the_application_may_add_a_write_and_read_it_and_never_change_or_remove_one() -> None:
    """A record of who replaced a key that could be edited is a record whose author moved after the
    fact. Delete this and an UPDATE or DELETE grant can arrive with the table, or row-level
    security can be left off it, with every other test here green."""
    emitted = squash(rendered("upgrade", MIGRATION))

    assert "ALTER TABLE ops.credential_write ENABLE ROW LEVEL SECURITY" in emitted
    assert "GRANT SELECT, INSERT ON ops.credential_write TO brain_app" in emitted
    assert "UPDATE ON ops.credential_write" not in emitted
    assert "DELETE ON ops.credential_write" not in emitted
    assert "CREATE TRIGGER credential_write_is_audited AFTER INSERT ON ops.credential_write" in (
        emitted
    )


# ----------------------------------------------------------------- nowhere to put a value


def test_nothing_between_a_kept_key_and_the_ledger_has_anywhere_to_put_the_value() -> None:
    """`A_CREDENTIAL_WRITE_LEAVES_A_LEDGER_ENTRY_AND_NEVER_THE_VALUE`, structurally: the table's
    columns, the protocol's parameters, the recorder's parameters and the statement's columns.
    Delete this and a `fingerprint` column or a `value` parameter can be added to make the entry
    more useful, and the key is in the longest-kept table in the system."""
    protocol = inspect.signature(CredentialWrites.record).parameters
    method = inspect.signature(AuditRecorder.credential).parameters
    statement = written("providers/anthropic", "u_admin")

    assert set(CredentialWriteRow.__table__.columns.keys()) == {
        "id",
        "slot",
        "written_by",
        "created_at",
    }
    assert set(protocol) == {"self", "slot", "written_by", "trace_id", "ent_hash"}
    assert set(method) == {"self", "slot"}
    assert compiled(statement).startswith("INSERT INTO ops.credential_write (slot, written_by) ")
    assert set(statement.compile().params) == {"slot", "written_by"}


# ------------------------------------------------------------------------ the store


class _Session:
    """An `AsyncSession` in the shape the store uses, noting each statement and how it ended."""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def begin(self) -> _Transaction:
        return _Transaction(self.log)

    async def execute(self, statement: Any, *_: Any, **__: Any) -> None:
        text = compiled(statement)
        params = statement.compile().params
        self.log.append(text if "set_config" not in text else f"set {params['name']}")


class _Transaction:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def __aenter__(self) -> None:
        self.log.append("BEGIN")

    async def __aexit__(self, kind: object, *_: object) -> None:
        self.log.append("ROLLBACK" if kind is not None else "COMMIT")


def test_the_store_attributes_the_transaction_then_inserts_the_row_and_commits_once() -> None:
    """The trigger reads the trace and the reach from the transaction's settings, so they are set
    before the insert in the same transaction. Delete this and the entry's trace falls back to a
    transaction id nobody can join to the request, or the insert is split from its settings."""
    log: list[str] = []
    store = StoredCredentialWrites(lambda: _Session(log))  # type: ignore[arg-type]

    run(
        lambda: store.record(
            slot="providers/anthropic", written_by="u_admin", trace_id="t", ent_hash="e" * 32
        )
    )

    assert log == [
        "BEGIN",
        "set brain.trace_id",
        "set brain.ent_hash",
        compiled(written("providers/anthropic", "u_admin")),
        "COMMIT",
    ]


def test_a_process_with_a_database_records_to_it_and_one_without_records_nowhere() -> None:
    """Delete this and the lifespan can attach a store over nothing, which warns on every write in
    a process that has a ledger, or build one without a database, which fails on every write."""
    sessions: Any = object()
    found = credential_writes_for(sessions)

    assert credential_writes_for(None) is None
    assert isinstance(found, StoredCredentialWrites)
    assert found._sessions is sessions


# ------------------------------------------------------------------------ the database


@contextmanager
def through_0054(database: str) -> Iterator[str]:
    """A database with `0054` applied. Without pgvector, `retirable` stops at `0048`, which built
    the ledger and its append function; `0049` is run for real because `0054` puts triggers on
    two of its tables, `0050` to `0053` are stamped, and `0054` is run for real."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "upgrade", "0049")
            migrate(database, "stamp", "0053")
            migrate(database, "upgrade", "0054")
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


def a_grant_on_the_ledger(url: str) -> None:
    """One entry already on the chain, appended by `0003`'s grant trigger, so the credential's
    entry is linked to a parent rather than to genesis."""
    sql(
        url,
        "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department)"
        " VALUES ('u_holder', 'human', 'staff', 'Holder', 'web')",
    )
    sql(
        url,
        "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by, reason)"
        " VALUES ('u_holder', 'read:client.name', '{\"clauses\": []}', 'u_seed', 'needed')",
    )


def test_a_credential_write_appends_exactly_the_entry_the_recorder_writes_and_the_chain_holds() -> (
    None
):
    """M27.8.17 for this control, through the store the application uses and as the role it uses.

    One row naming the slot and the writer; exactly one `credential` entry, whose subject, actor
    and details are `AuditRecorder.credential`'s and whose reach and trace are the ones the store
    set; the whole chain verifying from genesis across the grant entry before it; and the
    application role refused an edit of the row. Delete this and every one of those can be false
    in production while the stubbed tests above stay green. **Skips without a server.**"""
    with through_0054("brain_credential_write") as url:
        a_grant_on_the_ledger(url)

        async def write() -> None:
            engine = app_engine(url)
            try:
                store = StoredCredentialWrites(make_session_factory(engine))
                await store.record(
                    slot="providers/anthropic",
                    written_by="u_admin",
                    trace_id="trace-kept",
                    ent_hash="a" * 32,
                )
            finally:
                await engine.dispose()

        run(write)
        rows = sql(url, "SELECT slot, written_by FROM ops.credential_write")
        chain = entries(url)
        [(may_update,)] = sql(
            url, "SELECT has_table_privilege('brain_app', 'ops.credential_write', 'UPDATE')"
        )

    expected = recorder().credential(slot="providers/anthropic")
    credential = [one for one in chain if one.action.value == "credential"]
    assert rows == [("providers/anthropic", "u_admin")]
    assert len(credential) == 1
    [entry] = credential
    assert (entry.subject, entry.actor_id, entry.details) == (
        expected.subject,
        "u_admin",
        expected.details,
    )
    assert (entry.ent_hash, entry.trace_id) == ("a" * 32, "trace-kept")
    assert len(chain) >= 2
    assert AuditChain(chain).verify() is None
    assert KEY not in repr(chain)
    assert may_update is False


def test_a_row_that_is_not_a_slot_or_a_writer_is_refused_by_the_table() -> None:
    """The constraints stand for a hand-written statement, which no type checks. Delete this and a
    slot the subject rewrite cannot reverse, or a writer the ledger's actor grammar refuses, is
    accepted by the table and the append fails inside the trigger instead, naming the ledger. The
    positive half is the first-run actor, which is not a principal. **Skips without a server.**"""
    with through_0054("brain_credential_write_refused") as url:
        refused: list[str] = []
        for slot, writer in (("providers.anthropic/x", "u_admin"), ("providers/x", "a b")):
            try:
                sql(
                    url,
                    "INSERT INTO ops.credential_write (slot, written_by) VALUES (%s, %s)",
                    slot,
                    writer,
                )
            except Exception as exc:
                refused.append(type(exc).__name__)
        sql(
            url,
            "INSERT INTO ops.credential_write (slot, written_by) VALUES (%s, %s)",
            "providers/anthropic",
            GRANTED_BY,
        )
        chain = entries(url)

    assert refused == ["CheckViolation", "CheckViolation"]
    assert [(one.actor_id, one.subject) for one in chain] == [
        (GRANTED_BY, "credential:providers.anthropic")
    ]


def test_a_process_built_with_a_database_records_every_key_its_store_keeps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lifespan's own wiring, which nothing above reaches: the store it builds before the
    database, and the record it attaches after. Delete this and the lifespan can leave the record
    off, so every key saved from the console or the wizard on a real install warns into a log and
    the ledger never hears of it. **Skips without a server.**"""
    monkeypatch.delenv("INSTALL_OIDC_ISSUER", raising=False)
    monkeypatch.setattr(
        "brain.app.credentials_at_start",
        lambda address, token: Credentials(Vault(), environ={}),
    )
    with through_0054("brain_credential_lifespan") as url:
        app = create_app(
            Settings(env="development", database_url=url, run_migrations=False, valkey_url="")
        )

        async def walk() -> None:
            async with app.router.lifespan_context(app):
                await app.state.credentials.keep(
                    SLOTS["providers/anthropic"],
                    KEY,
                    actor=GRANTED_BY,
                    trace_id=uuid.uuid4().hex,
                )

        run(walk)
        chain = entries(url)

    assert [(one.action.value, one.actor_id, one.subject) for one in chain] == [
        ("credential", GRANTED_BY, "credential:providers.anthropic")
    ]
