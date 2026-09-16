"""The artifact store: what `0058` builds, the key an artifact's bytes go under, and the two writes.

The migration is rendered offline and compared with the model, for the reason
`tests/unit/test_skill_store.py` gives. The store runs against `tests.fixtures.fake_s3.FakeS3`
behind the real client, and a session that notes each statement and can be told to fail its
commit, so the order of the two writes and what a failed record does to its bytes are asserted
without a database. Nothing here needs a
server; the policies are proven as rendered DDL, and no PostgreSQL was reachable where this was
written to prove them against a live row.

Task ids: M39.5.1.1, M39.5.1.2, M27.7.23
"""

from __future__ import annotations

import hashlib
import itertools
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.app import Settings, create_app
from brain.console.agent_output import (
    Artifact,
    ArtifactError,
    ArtifactInput,
    ArtifactKind,
    Provenance,
    retention_class_for,
)
from brain.core.entitlement import EntitlementSet
from brain.core.field_policy import Classification
from brain.db import metadata
from brain.ops.artifact_store import (
    ARTIFACT_BUCKET,
    NO_STORE_TO_KEEP_AN_ARTIFACT_IN,
    Produced,
    StoredArtifacts,
    artifact_of,
    artifact_values,
    artifacts_for,
    object_key,
)
from brain.ops.object_store import ObjectStore, S3Backend, StoreCredential, unconnected
from brain.ops.retention import DataClass
from brain.ops.storage import Backend, ObjectKind, StorageError, bucket_for, config_for
from brain.tables import artifact as table_module
from brain.tables.artifact import ArtifactRow
from brain.tables.identity import one_of
from tests.fixtures.fake_s3 import FakeS3
from tests.fixtures.scratch_postgres import run
from tests.unit.test_agent_routes import agent_row
from tests.unit.test_artifact_routes import AGENTS, StubSession, _wiring, get
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
MIGRATION = VERSIONS / "0058_artifact_store.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
AT = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
KEY = StoreCredential(access_key_id="brain-test-access", secret_access_key="brain-test-secret")
ENDPOINT = "http://objects.example.test:8333"
CALLER = "u_asker"
REACH = EntitlementSet(principal_id=CALLER)
BODY = b"%PDF-1.7 quarterly figures"

#: A payload input and a restricted record: the record is the most sensitive and has no clock,
#: the payload is shorter-lived, so the class is the payload's. `retention_class_for` decides it.
INPUTS = (
    ArtifactInput(
        label="invoice rows",
        data_class=DataClass.BUSINESS_RECORD,
        classification=Classification.RESTRICTED,
    ),
    ArtifactInput(
        label="the question", data_class=DataClass.PAYLOAD, classification=Classification.INTERNAL
    ),
)


def produced(body: bytes = BODY, **changes: Any) -> Produced:
    fields: dict[str, Any] = {
        "agent_id": "agent_finance",
        "kind": ArtifactKind.REPORT,
        "run_id": "run-1",
        "agent_version": "1.4.2",
        "caller_id": CALLER,
        "reach": REACH,
        "inputs": INPUTS,
        "body": body,
        "content_type": "application/pdf",
        "provenance": Provenance(sources=("xero",), knowledge_items=("k1",)),
    }
    return Produced(**(fields | changes))


# ------------------------------------------------------------------------- the migration
def test_the_migration_and_the_model_hold_the_grammars_and_vocabularies_they_copied() -> None:
    """`0058` copies the patterns and both closed vocabularies, for `0009`'s reason. Delete this and
    an artifact kind or a retention class added to its enum is refused by the database after the
    run that produced it finished."""
    migration = migration_module(MIGRATION)

    assert migration.TABLES == ("agent.artifact",)
    assert migration.ARTIFACT_ID_PATTERN == table_module.ARTIFACT_ID_PATTERN
    assert migration.OBJECT_KEY_PATTERN == table_module.OBJECT_KEY_PATTERN
    assert migration.ENT_HASH_PATTERN == table_module.ENT_HASH_PATTERN
    assert migration.DIGEST_PATTERN == table_module.DIGEST_PATTERN
    assert one_of("kind", ArtifactKind) == migration.KINDS
    assert one_of("data_class", DataClass) == migration.DATA_CLASSES


def test_the_migration_builds_the_table_and_its_index_exactly_as_the_model_declares() -> None:
    """Compared as rendered DDL. Delete this and the model can gain a column or lose a check with
    the database built the old way."""
    table = metadata.tables["agent.artifact"]
    emitted = squash(rendered("upgrade", MIGRATION))

    assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted
    for index in table.indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


def test_the_application_reads_every_row_and_records_only_in_the_callers_name() -> None:
    """Row-level security on, SELECT and INSERT only, and an insert admitted only where the row's
    caller is the session's principal. Delete this and an UPDATE grant, or a policy admitting a row
    recorded for somebody else, ships with every other test green."""
    emitted = squash(rendered("upgrade", MIGRATION))
    principal = "current_setting('app.principal_id', true)"

    assert "ALTER TABLE agent.artifact ENABLE ROW LEVEL SECURITY" in emitted
    assert "GRANT SELECT, INSERT ON agent.artifact TO brain_app" in emitted
    assert "UPDATE ON agent.artifact" not in emitted
    assert "DELETE ON agent.artifact" not in emitted
    assert (
        "CREATE POLICY artifact_recorded_for_the_sessions_principal ON agent.artifact "
        f"FOR INSERT TO brain_app WITH CHECK (caller_id = {principal})"
    ) in emitted
    assert (
        "CREATE POLICY artifact_readable ON agent.artifact FOR SELECT TO brain_app USING (true)"
    ) in emitted
    assert "DROP TABLE agent.artifact" in squash(rendered("downgrade", MIGRATION))


def test_no_column_could_hold_the_produced_bytes() -> None:
    """Delete this and a `content` column added to save a fetch puts the document under the
    database's retention rather than the one its class decided."""
    names = set(metadata.tables["agent.artifact"].columns.keys())
    assert not names & {"body", "content", "payload", "bytes", "data", "document"}


# ---------------------------------------------------------------------------- the key
@pytest.mark.parametrize("data_class", list(DataClass))
def test_every_class_makes_a_key_the_table_accepts_and_the_key_says_nothing_of_the_content(
    data_class: DataClass,
) -> None:
    """Delete this and a class whose name the key pattern refuses fails at the insert, after the
    bytes were put, or a key built from a title passes."""
    artifact = recorded_as(data_class)
    key = object_key("brain", artifact)
    assert re.fullmatch(table_module.OBJECT_KEY_PATTERN, key)
    assert key == f"brain/artifacts/{data_class.value}/{artifact.artifact_id}"
    assert "quarterly" not in key
    assert bucket_for(ObjectKind.AGENT_ARTIFACT).name == ARTIFACT_BUCKET == "assets"


def recorded_as(data_class: DataClass) -> Artifact:
    return Artifact(
        artifact_id="0" * 32,
        agent_id="agent_finance",
        kind=ArtifactKind.DOCUMENT,
        run_id="run-1",
        agent_version="1.4.2",
        caller_id=CALLER,
        entitlement_hash=REACH.ent_hash(),
        at=AT,
        data_class=data_class,
        bytes_stored=len(BODY),
    )


# ------------------------------------------------------------------------ the two writes
class _Transaction:
    def __init__(self, session: _Session) -> None:
        self.session = session

    async def __aenter__(self) -> None:
        self.session.log.append("BEGIN")

    async def __aexit__(self, kind: object, *_: object) -> None:
        if kind is None and self.session.fail_commit:
            self.session.log.append("COMMIT REFUSED")
            msg = "the insert policy refused the row"
            raise RuntimeError(msg)
        self.session.log.append("ROLLBACK" if kind is not None else "COMMIT")


class _Result:
    def __init__(self, rows: list[ArtifactRow]) -> None:
        self.rows = rows

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[ArtifactRow]:
        return self.rows


class _Session:
    """An `AsyncSession` in the shape the store uses, noting what it was asked."""

    def __init__(self, log: list[str], rows: list[ArtifactRow], *, fail_commit: bool) -> None:
        self.log = log
        self.rows = rows
        self.fail_commit = fail_commit

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def begin(self) -> _Transaction:
        return _Transaction(self)

    async def execute(self, statement: Any, *_: Any, **__: Any) -> _Result:
        text = " ".join(str(statement.compile(dialect=DIALECT)).split())
        if "set_config" in text:
            params = statement.compile().params
            self.log.append(f"set {params['name']}={params['value']}")
        else:
            self.log.append(" ".join(text.split(" ")[:2]))
        return _Result(self.rows)

    def add(self, row: ArtifactRow) -> None:
        self.log.append("INSERT agent.artifact")
        self.rows.append(row)


def a_store(
    fake: FakeS3,
    *,
    fail_commit: bool = False,
    rows: list[ArtifactRow] | None = None,
    mint: Any = None,
) -> tuple[StoredArtifacts, list[str], list[ArtifactRow]]:
    log: list[str] = []
    held = [] if rows is None else rows
    backend = S3Backend(
        config_for(Backend.SEAWEEDFS, endpoint_url=ENDPOINT), KEY, transport=fake.transport()
    )
    store = StoredArtifacts(
        lambda: _Session(log, held, fail_commit=fail_commit),  # type: ignore[arg-type]
        backend,
        "brain",
        mint=mint or (lambda: "a" * 32),
    )
    return store, log, held


def test_an_artifact_is_put_in_the_store_and_recorded_for_its_caller_under_its_inputs_class() -> (
    None
):
    """**The write path, end to end.** The bytes under the key, the row naming them with the digest
    of exactly those bytes, the class `retention_class_for` decides from the inputs, the run's reach
    hashed onto the record, and the principal set to the caller before the insert. Delete this and
    every refusal below is satisfied by a store that keeps nothing."""
    fake = FakeS3(credential=KEY).holding(ARTIFACT_BUCKET, {})
    store, log, rows = a_store(fake)

    kept = run(lambda: store.keep(produced(), at=AT))

    assert kept.data_class is retention_class_for(INPUTS) is DataClass.PAYLOAD
    assert kept.entitlement_hash == REACH.ent_hash()
    assert (kept.caller_id, kept.bytes_stored) == (CALLER, len(BODY))
    key = f"brain/artifacts/payload/{'a' * 32}"
    assert fake.buckets[ARTIFACT_BUCKET] == {key: BODY}
    assert log == ["BEGIN", f"set app.principal_id={CALLER}", "INSERT agent.artifact", "COMMIT"]
    (row,) = rows
    assert (row.object_key, row.content_digest) == (key, hashlib.sha256(BODY).hexdigest())
    assert (row.sources, row.knowledge_items) == (["xero"], ["k1"])


def test_a_record_that_does_not_commit_takes_its_bytes_back_out_of_the_store() -> None:
    """Delete this and bytes nothing records sit in a bucket that keeps everything, with nothing
    that would ever delete them."""
    fake = FakeS3(credential=KEY).holding(ARTIFACT_BUCKET, {})
    store, log, _ = a_store(fake, fail_commit=True)

    with pytest.raises(RuntimeError, match="insert policy"):
        run(lambda: store.keep(produced(), at=AT))

    assert fake.buckets[ARTIFACT_BUCKET] == {}
    assert ("DELETE", f"/{ARTIFACT_BUCKET}/brain/artifacts/payload/{'a' * 32}", "") in fake.asked
    assert log[-1] == "COMMIT REFUSED"


def test_bytes_the_store_would_not_take_are_never_recorded() -> None:
    """The put comes first. Delete this and the order can be swapped, listing an artifact nobody can
    fetch in a table nothing may delete from."""
    fake = FakeS3(credential=KEY, down=True)
    store, log, rows = a_store(fake)

    with pytest.raises(StorageError):
        run(lambda: store.keep(produced(), at=AT))

    assert (log, rows) == ([], [])


def test_nothing_is_kept_without_a_store_or_without_bytes() -> None:
    """Delete this and a record pointing at nowhere, or at an empty file from a failed render, is
    listed on the Artifacts screen as something produced."""
    without = StoredArtifacts(lambda: None, None, "")  # type: ignore[arg-type]
    with pytest.raises(StorageError, match="not connected"):
        run(lambda: without.keep(produced(), at=AT))
    assert NO_STORE_TO_KEEP_AN_ARTIFACT_IN.startswith("This process is not connected")

    fake = FakeS3(credential=KEY).holding(ARTIFACT_BUCKET, {})
    store, log, _ = a_store(fake)
    with pytest.raises(ArtifactError):
        run(lambda: store.keep(produced(body=b""), at=AT))
    assert (fake.asked, log) == ([], [])


# ------------------------------------------------------------------------ reading them back
def test_a_recorded_artifact_reads_back_as_the_record_and_a_broken_row_is_absent() -> None:
    """Delete this and a column read into the wrong field lists an artifact under the wrong person,
    or one row broken by hand answers the whole screen with a 500."""
    fake = FakeS3(credential=KEY).holding(ARTIFACT_BUCKET, {})
    store, _, rows = a_store(fake)
    kept = run(lambda: store.keep(produced(), at=AT))
    values = artifact_values(kept, key="k", content_type="t", digest="d")
    broken = ArtifactRow(**(values | {"artifact_id": "b" * 32, "kind": "spreadsheet"}))
    rows.append(broken)

    assert artifact_of(rows[0]) == kept
    assert artifact_of(broken) is None
    assert run(store.every) == (kept,)


def test_a_process_with_a_database_reads_artifacts_whether_or_not_it_can_keep_one() -> None:
    """Delete this and a store that is down hides every artifact already recorded, or a process
    with no database is handed a store over nothing."""
    sessions: Any = object()
    backend = S3Backend(config_for(Backend.SEAWEEDFS, endpoint_url=ENDPOINT), KEY)
    assert artifacts_for(None, ObjectStore(backend=backend, prefix="brain")) is None
    assert isinstance(artifacts_for(sessions, unconnected("no vault")), StoredArtifacts)
    assert isinstance(artifacts_for(sessions, None), StoredArtifacts)
    connected = ObjectStore(backend=backend, prefix="brain")
    assert isinstance(artifacts_for(sessions, connected), StoredArtifacts)


def test_what_the_store_keeps_is_what_the_artifacts_screen_lists_to_each_reader() -> None:
    """**M27.7.23 through the store rather than a list.** Two artifacts kept for two agents, the
    screen reading `StoredArtifacts.every` as the lifespan attaches it, a reader scoped to one agent
    seeing that agent's, a company-wide reader seeing both with the run, version, person and window,
    and a reader without the screen refused. Delete this and the screen can pass every route test
    over hand-built records while reading nothing the store wrote."""
    fake = FakeS3(credential=KEY).holding(ARTIFACT_BUCKET, {})
    ids: Iterator[str] = (f"{n:032x}" for n in itertools.count(1))
    store, _, _ = a_store(fake, mint=lambda: next(ids))
    recent = datetime.now(UTC) - timedelta(hours=1)
    run(lambda: store.keep(produced(agent_id="quoting"), at=recent))
    run(lambda: store.keep(produced(agent_id="hiring"), at=recent))

    app = create_app(Settings(env="development"))
    AGENTS[:] = [agent_row("quoting"), agent_row("hiring")]
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        app.state.artifact_source = store.every
        narrow = get(c, "u_narrow").json()
        wide = get(c, "u_admin").json()
        refused = get(c, "u_none")

    assert [one["agent_id"] for one in narrow["artifacts"]] == ["quoting"]
    assert sorted(one["agent_id"] for one in wide["artifacts"]) == ["hiring", "quoting"]
    row = next(one for one in wide["artifacts"] if one["agent_id"] == "quoting")
    assert (row["produced_for"], row["run_id"], row["agent_version"]) == (CALLER, "run-1", "1.4.2")
    assert row["kept_as"] == DataClass.PAYLOAD.value
    assert row["kept_until"] != ""
    assert refused.status_code == 404
