"""The worker reading a connected source: its key, its call, what it writes, and who can read it.

`tests/unit/test_connector_sync.py` holds the policy without a connection. This drives
`brain.ops.connector_sync_run` against the recorded Xero answers in `tests/fixtures/cassettes.py`,
a stand-in for the call that replays them, and a PostgreSQL database of the test's own, and then
reads what the run wrote through the row plane and the redactor as three different people.

**The proof the leaf asks for is a comparison and not a count.** A synced record is read by a person
whose grant reaches the source's tenant, and for everybody else the answer after the sync is
compared whole with the answer on the same database before the sync, when the record did not exist.
Equal is the property: DENIED and ABSENT are one answer, and nothing about the result says a record
was there.

**The document leg has no recording to be driven by**, because no source the console can connect
yields documents and the corpus records no document source. It is driven through the same loop by a
reading written here over the Xero cassette, whose rows are handed to the corpus as documents with
an owner and a department, and it is read back through the document search as the owner's department
and as another. `brain.ops.connector_sync.NO_CONNECTABLE_SOURCE_YIELDS_A_DOCUMENT` says why.

No test here calls a live API. The key is a sentinel, the call is a replay, and the address is the
one a stand-in resolver hands out.

Task ids: M42.6.5
"""

from __future__ import annotations

import http.server
import json
import ssl
import threading
import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors import xero
from brain.connectors.manifest import manifest_digest
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification
from brain.core.redaction import redact
from brain.core.scope import Scope
from brain.knowledge.chunk_store import ingest_document
from brain.knowledge.columns import ColumnRule, TableClassification
from brain.knowledge.document_tools import DocumentSearch, searcher
from brain.knowledge.embed_policy import REVISION_SETTING
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.row_store import SessionRowSource
from brain.knowledge.rows import RowRequest, RowTool, read_rows
from brain.knowledge.visibility import KnowledgeVisibility
from brain.ops.connectable import manifest_for
from brain.ops.connector_store import StoredConnections
from brain.ops.connector_sync import (
    ADDRESS_REFUSED,
    KEY_DECLINED,
    NO_KEY,
    NO_VAULT,
    READ_TO_THE_END,
    SOURCE_ALLOWANCE_REFUSED,
    SOURCE_UNREACHABLE,
    VAULT_REFUSED,
    VAULT_UNREACHABLE,
    HubSpotReading,
    SourceReading,
    XeroReading,
)
from brain.ops.connector_sync_run import (
    THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES,
    USER_AGENT,
    ConnectorKeyAbsentError,
    HttpsSourceCaller,
    SourceAnswer,
    SyncRun,
    WorkerConnectorKeys,
    key_detail,
    sync_on,
    worker_connector_keys,
)
from brain.ops.connector_sync_store import StoredSyncStates
from brain.ops.credentials import KEY_FIELD, connector_key_slot
from brain.ops.openbao import VaultRefusedError, VaultUnreachableError
from brain.ops.queue import Job
from brain.ops.secrets import SecretRef, SecretsUnavailableError, VaultRole
from brain.session import make_app_engine, make_application_sessions, make_session_factory
from brain.tools.fetch import UnsafeAddressError
from tests.fixtures.cassettes import CASSETTES
from tests.fixtures.scratch_postgres import add_modelled, drop, fresh, run, sql
from tests.unit.test_vault_policies import _granted_paths, _matches, _policy_file
from tests.unit.test_webhook_delivery import NAME, _certificate

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)

#: A key nothing else in any output could contain, so finding it anywhere is a leak.
KEY: Final = "SOURCE-KEY-SENTINEL-4d7a19"

TENANT: Final = "11111111-2222-3333-4444-555555555555"
OTHER_TENANT: Final = "99999999-8888-7777-6666-555555555555"

#: Where the stand-in resolver says every name is.
PUBLIC: Final = "93.184.216.34"

#: The tables a sync reads and writes.
SYNC_TABLES: Final = ("ops.connector_connection", "ops.connector_sync", "proj.record")

INVOICE_ID: Final = "b1f2-0447"
MONEY_CANARY: Final = "CANARY-INVOICE-Z9KRT"


def recorded(cid: str) -> Any:
    return next(one for one in CASSETTES if one.cid == cid)


def answer_for(cid: str) -> SourceAnswer:
    """One recording as the call would have answered with it."""
    one = recorded(cid)
    return SourceAnswer(
        status=one.status,
        headers={key.lower(): value for key, value in one.headers.items()},
        body=json.dumps(one.body).encode("utf-8"),
    )


#: Xero's contacts endpoint answering with none, in Xero's own envelope. Not a recording: the corpus
#: records a genuine absence only for HubSpot (`HUBSPOT-200-empty`), and this is that fact in the
#: shape the contacts operation declares, as `tests/unit/test_xero.py` writes its empty ledger.
NO_CONTACTS: Final = SourceAnswer(status=200, headers={}, body=b'{"Contacts": []}')


class Resolver:
    def resolve(self, host: str) -> list[str]:
        del host
        return [PUBLIC]


@dataclass
class Call:
    url: str
    address: str
    headers: Mapping[str, str]


@dataclass
class Replay:
    """`SourceCaller` answering from recordings, the last one for every call past the list."""

    answers: Sequence[SourceAnswer]
    calls: list[Call] = field(default_factory=list)

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        del max_bytes
        self.calls.append(Call(url=url, address=address, headers=dict(headers)))
        return self.answers[min(len(self.calls), len(self.answers)) - 1]


@dataclass
class Keys:
    """`ConnectorKeys` handing out the sentinel and noting which reference it was asked for."""

    asked: list[SecretRef] = field(default_factory=list)

    def key_for(self, ref: SecretRef) -> str:
        self.asked.append(ref)
        return KEY


class NoKeys:
    def key_for(self, ref: SecretRef) -> str:
        raise ConnectorKeyAbsentError(NO_KEY)


async def no_documents(item: KnowledgeItem) -> object:
    raise AssertionError(f"no reading here yields a document, and {item.item_id} arrived")


async def no_sleep(seconds: float) -> None:
    del seconds


# ------------------------------------------------------------------ the database


@contextmanager
def a_database(name: str) -> Iterator[str]:
    """A database holding the connections, the attempts and the projection, and nothing else."""
    url = fresh(name)
    try:
        add_modelled(url, SYNC_TABLES)
        yield url
    finally:
        drop(name)


def through[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = make_app_engine(url)
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


def connect(url: str, name: str = "xero", tenant: str = TENANT) -> uuid.UUID:
    """Connect a source through the store the Connectors route writes with, the key kept nowhere."""
    settings = {"tenant_id": tenant}
    digest = manifest_digest(manifest_for(name, settings))

    async def kept() -> datetime | None:
        return None

    through(
        url,
        lambda sessions: StoredConnections(sessions).connect(
            connector=name,
            settings=settings,
            digest=digest,
            actor="u_admin",
            trace_id="t-connect",
            ent_hash="0" * 32,
            keep_key=kept,
        ),
    )
    (found,) = sql(
        url,
        "SELECT id FROM ops.connector_connection WHERE connector = %s AND disconnected_at IS NULL",
        name,
    )
    identifier: uuid.UUID = found[0]
    return identifier


def disconnect(url: str, name: str = "xero") -> None:
    through(
        url,
        lambda sessions: StoredConnections(sessions).disconnect(
            name, actor="u_admin", trace_id="t-disconnect", ent_hash="0" * 32
        ),
    )


def sync(
    url: str,
    caller: Replay,
    *,
    at: datetime = NOW,
    keys: Any = None,
    readings: Mapping[str, SourceReading] | None = None,
    documents: Callable[[KnowledgeItem], Awaitable[object]] = no_documents,
) -> SyncRun:
    clock = iter(at + timedelta(seconds=n) for n in range(10_000))

    async def work(sessions: async_sessionmaker[AsyncSession]) -> SyncRun:
        extra: dict[str, Any] = {} if readings is None else {"readings": readings}
        return await sync_on(
            sessions=sessions,
            documents=documents,
            now=at,
            keys=Keys() if keys is None else keys,
            caller=caller,
            resolver=Resolver(),
            clock=lambda: next(clock),
            sleep=no_sleep,
            **extra,
        )

    return through(url, work)


def attempts(url: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT outcome, health, records, documents, consecutive_failures, next_attempt_at, "
        "finished_at, detail FROM ops.connector_sync ORDER BY finished_at",
    )


def projected(url: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT source, entity, source_id, fields, last_seen_at, deleted_at FROM proj.record "
        "ORDER BY entity, source_id",
    )


# ------------------------------------------------------------------ who reads a record

#: The invoice as a row tool reads it. The tenant is classified under the capability that reaches
#: the row, for `brain.demo.THE_COLUMN_A_SCOPE_TESTS_IS_READ_BY_WHOEVER_REACHES_THE_ROW`; every
#: other column under the connector's own field capability.
INVOICES: Final = RowTool(
    source=xero.CONNECTOR_NAME,
    classification=TableClassification(
        entity=xero.ENTITY_INVOICE,
        rules=(
            ColumnRule("tenant_id", Capability(value="read:invoice"), Classification.INTERNAL),
            *(
                ColumnRule(one.field, one.required_capability, one.classification)
                for one in xero.XERO_FIELD_RULES
                if one.entity == xero.ENTITY_INVOICE and one.field != "amount_due"
            ),
        ),
    ),
    description="Invoices this install keeps from Xero.",
)


def a_reader(principal: str, scope: Scope) -> EntitlementSet:
    """Somebody holding the invoice row and every invoice column, all in one scope."""
    capabilities = [
        "read:invoice",
        *(one.required_capability.value for one in INVOICES.classification.rules),
    ]
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=scope)
            for one in dict.fromkeys(capabilities)
        ),
    )


ENTITLED: Final = a_reader(
    "u_finance", Scope(clauses=xero.XeroConnection(tenant_id=TENANT).visibility().clauses)
)
OTHER_TENANT_READER: Final = a_reader(
    "u_elsewhere", Scope(clauses=xero.XeroConnection(tenant_id=OTHER_TENANT).visibility().clauses)
)
DEPARTMENT_READER: Final = a_reader("u_department", Scope.department("finance"))
NOBODY: Final = EntitlementSet(principal_id="u_nobody", grants=())


def read_as(url: str, who: EntitlementSet) -> Mapping[str, Any]:
    """What this person is handed: the row plane's statement, then the redactor, as a document."""

    async def work(sessions: async_sessionmaker[AsyncSession]) -> Mapping[str, Any]:
        result = await read_rows(
            INVOICES,
            RowRequest(),
            entitlement=who,
            records=SessionRowSource(sessions),
            now=NOW,
        )
        answer = redact(result, entitlement=who, policy=INVOICES.classification.policy(), now=NOW)
        return answer.payload.model_dump(mode="json")

    return through(url, work)


# ------------------------------------------------------------------ the proof


@pytest.mark.needs_db
def test_a_synced_invoice_is_read_within_its_tenant_and_is_absent_for_everybody_else() -> None:
    """**The leaf's first proof, end to end against the recording.** A connected Xero source is read
    by the worker's run with the key the vault would hand it: one call, to the address the rule
    checked, carrying the key, the tenant and a request for JSON. The recorded invoice is written to
    `proj.record` with its declared fields and the tenant its source's rule names, and without the
    amount owing. The attempt is recorded as read to the end, healthy, with one record, and due
    again after Xero's reconciliation interval.

    Then it is read. A person whose grant reaches that tenant is handed the invoice. A person whose
    grant names another tenant, a person whose grant names a department, and a person holding
    nothing are each handed, byte for byte, what they were handed from the same database before the
    sync ran, when there was no record at all.

    Delete this and the sync can write records nobody reaches, or records everybody holding the
    entity reaches whatever their scope, with every other test green."""
    with a_database("brain_connector_sync_records") as url:
        connection_id = connect(url)
        before = {
            who.principal_id: read_as(url, who)
            for who in (ENTITLED, OTHER_TENANT_READER, DEPARTMENT_READER, NOBODY)
        }
        caller = Replay([answer_for("XERO-200-invoices"), NO_CONTACTS])
        keys = Keys()
        ran = sync(url, caller, keys=keys)
        after = {
            who.principal_id: read_as(url, who)
            for who in (ENTITLED, OTHER_TENANT_READER, DEPARTMENT_READER, NOBODY)
        }
        rows = projected(url)
        (attempt,) = attempts(url)
        recorded_attempt = sql(url, "SELECT connection_id, connector FROM ops.connector_sync")
        stored_text = json.dumps([str(one) for one in (*rows, *attempts(url))])

    assert ran == SyncRun(read=1, waiting=0, failed=0, not_due=0, cannot_be_read=0)
    assert [ref.path for ref in keys.asked] == [connector_key_slot("xero").path]
    invoices, contacts = caller.calls
    assert invoices.address == PUBLIC
    assert invoices.url.startswith(f"{xero.BASE_URL}/api.xro/2.0/Invoices")
    assert contacts.url.startswith(f"{xero.BASE_URL}/api.xro/2.0/Contacts")
    assert invoices.headers["Authorization"] == f"Bearer {KEY}"
    assert invoices.headers[xero.TENANT_HEADER] == TENANT
    assert invoices.headers["Accept"] == "application/json"

    ((source, entity, source_id, fields, last_seen_at, deleted_at),) = rows
    assert (source, entity, source_id, deleted_at) == ("xero", "invoice", INVOICE_ID, None)
    assert fields["tenant_id"] == TENANT
    assert fields["status"] == "AUTHORISED"
    assert "amount_due" not in fields
    assert last_seen_at > NOW
    assert MONEY_CANARY not in stored_text
    assert KEY not in stored_text

    outcome, health, records, documents, failures, next_at, finished_at, detail = attempt
    assert (outcome, health, records, documents, failures, detail) == (
        "synced",
        "ok",
        1,
        0,
        0,
        READ_TO_THE_END,
    )
    assert next_at == finished_at + xero.RECONCILIATION_INTERVAL
    assert recorded_attempt == [(connection_id, "xero")]

    (seen,) = after["u_finance"]["records"]
    assert (seen["entity"], seen["id"], seen["tenant_id"]) == ("invoice", INVOICE_ID, TENANT)
    assert seen["status"] == "AUTHORISED"
    assert before["u_finance"]["records"] == []
    for principal in ("u_elsewhere", "u_department", "u_nobody"):
        assert after[principal] == before[principal], principal


@pytest.mark.needs_db
def test_a_connected_source_is_read_and_once_disconnected_it_is_never_read_again() -> None:
    """**The behaviour a connect and a disconnect change**, cited by the console audit for both
    routes. Connected through the store the route writes with, the source is read on the next run
    and its attempt is listed for the Connectors screen; disconnected through the same store, the
    next run calls nothing, records nothing, and the screen's read lists no attempt for it, while
    the records it already wrote stay, ageing, as `A_SYNC_RETIRES_NOTHING` says.

    Delete this and a disconnected source could go on being read with the key its administrator
    was told to revoke, or a connected one could be listed and never read."""
    with a_database("brain_connector_sync_connected") as url:
        connect(url)
        first = Replay([answer_for("XERO-200-invoices"), NO_CONTACTS])
        sync(url, first)
        listed = through(url, lambda sessions: StoredSyncStates(sessions).states())
        disconnect(url)
        later = Replay([answer_for("XERO-200-invoices")])
        ran = sync(url, later, at=NOW + timedelta(days=2))
        unlisted = through(url, lambda sessions: StoredSyncStates(sessions).states())
        kept = projected(url)
        runs = attempts(url)

    assert len(first.calls) == 2
    assert set(listed) == {"xero"}
    assert listed["xero"].last_synced_at is not None
    assert later.calls == []
    assert ran == SyncRun(read=0, waiting=0, failed=0, not_due=0, cannot_be_read=0)
    assert unlisted == {}
    assert len(runs) == 1
    assert [row[2] for row in kept] == [INVOICE_ID]


@pytest.mark.needs_db
def test_a_refusal_on_volume_waits_as_the_source_asked_and_writes_nothing() -> None:
    """The recorded daily refusal: recorded as waiting for the source's allowance, degraded and not
    failed, due again when the source said, and no record written from an error body.

    Delete this and a 429 is read as an empty ledger, or retried inside the half hour the source
    asked for, spending calls the tenant does not have."""
    with a_database("brain_connector_sync_quota") as url:
        connect(url)
        ran = sync(url, Replay([answer_for("XERO-429")]))
        rows = projected(url)
        ((outcome, health, records, _, failures, next_at, finished_at, detail),) = attempts(url)

    assert ran.waiting == 1
    assert rows == []
    assert (outcome, health, records, failures, detail) == (
        "quota",
        "degraded",
        0,
        0,
        SOURCE_ALLOWANCE_REFUSED,
    )
    assert next_at == finished_at + timedelta(
        seconds=float(recorded("XERO-429").headers["Retry-After"])
    )


@pytest.mark.needs_db
def test_a_declined_key_is_down_at_once_and_an_unreachable_source_backs_off_and_is_down_third() -> (
    None
):
    """**Backing off and marking unhealthy, from real runs.** The recorded expired token is down on
    the first attempt with the sentence that says to replace the key. An unreachable source is
    degraded, then degraded, then down, each attempt waiting twice as long as the last, and a run
    before the wait is over reads nothing and records nothing.

    Delete this and a failing source is attempted on every run, or shown healthy for a week."""
    with a_database("brain_connector_sync_expired") as url:
        connect(url)
        sync(url, Replay([answer_for("XERO-401-expired")]))
        ((_, health, _, _, failures, _, _, detail),) = attempts(url)
    assert (health, failures, detail) == ("down", 1, KEY_DECLINED)

    with a_database("brain_connector_sync_unreachable") as url:
        connect(url)
        silent = Replay([SourceAnswer(connection_failed=True)])
        at = NOW
        for _ in range(3):
            sync(url, silent, at=at)
            next_at = attempts(url)[-1][5]
            early = sync(url, silent, at=next_at - timedelta(seconds=1))
            assert early.not_due == 1
            at = next_at
        runs = attempts(url)

    assert len(silent.calls) == 3
    assert [(one[1], one[4], one[7]) for one in runs] == [
        ("degraded", 1, SOURCE_UNREACHABLE),
        ("degraded", 2, SOURCE_UNREACHABLE),
        ("down", 3, SOURCE_UNREACHABLE),
    ]
    waits = [one[5] - one[6] for one in runs]
    interval = xero.RECONCILIATION_INTERVAL
    assert waits == [interval, interval * 2, interval * 4]


@pytest.mark.needs_db
def test_a_key_the_worker_cannot_read_fails_the_attempt_and_calls_nothing() -> None:
    """Delete this and a source whose slot is empty is called with no key, and the refusal it earns
    reads as the source declining us rather than as the vault holding nothing."""
    with a_database("brain_connector_sync_no_key") as url:
        connect(url)
        caller = Replay([answer_for("XERO-200-invoices")])
        sync(url, caller, keys=NoKeys())
        ((outcome, health, _, _, failures, _, _, detail),) = attempts(url)

    assert caller.calls == []
    assert (outcome, health, failures, detail) == ("failed", "degraded", 1, NO_KEY)


class InsideResolver:
    def resolve(self, host: str) -> list[str]:
        del host
        return ["10.0.0.5"]


@pytest.mark.needs_db
def test_a_source_whose_name_resolves_inside_the_network_is_not_called() -> None:
    """The address rule the skill importer applies, applied to a source. Delete this and a name
    that answers inside the network is sent the key."""
    with a_database("brain_connector_sync_inside") as url:
        connect(url)
        caller = Replay([answer_for("XERO-200-invoices")])

        async def work(sessions: async_sessionmaker[AsyncSession]) -> SyncRun:
            return await sync_on(
                sessions=sessions,
                documents=no_documents,
                now=NOW,
                keys=Keys(),
                caller=caller,
                resolver=InsideResolver(),
                clock=lambda: NOW,
                sleep=no_sleep,
            )

        through(url, work)
        ((outcome, _, _, _, _, _, _, detail),) = attempts(url)

    assert caller.calls == []
    assert (outcome, detail) == ("failed", ADDRESS_REFUSED)
    with pytest.raises(UnsafeAddressError):
        xero.operation_for(xero.ENTITY_INVOICE, resolver=InsideResolver()).prepare(
            {"page": "1"}, resolver=InsideResolver()
        )


@pytest.mark.needs_db
def test_a_source_nothing_may_read_is_counted_as_such_and_never_called() -> None:
    """HubSpot, whose ceiling nobody verified, is connected beside Xero: Xero is read and HubSpot is
    not called, and no attempt is recorded for it, because an attempt is a call and none was made.

    Delete this and a source with no verified ceiling is read against no limit at all."""
    with a_database("brain_connector_sync_unverified") as url:
        connect(url)
        settings = {"portal_id": "12345678"}

        async def kept() -> datetime | None:
            return None

        through(
            url,
            lambda sessions: StoredConnections(sessions).connect(
                connector="hubspot",
                settings=settings,
                digest=manifest_digest(manifest_for("hubspot", settings)),
                actor="u_admin",
                trace_id="t",
                ent_hash="0" * 32,
                keep_key=kept,
            ),
        )
        caller = Replay([answer_for("XERO-200-invoices"), NO_CONTACTS])
        ran = sync(url, caller)
        connectors = sql(url, "SELECT connector FROM ops.connector_sync")

    assert ran == SyncRun(read=1, waiting=0, failed=0, not_due=0, cannot_be_read=1)
    assert all("hubapi" not in one.url for one in caller.calls)
    assert connectors == [("xero",)]


@pytest.mark.needs_db
def test_a_record_somebody_retired_stays_retired_whatever_the_source_still_says() -> None:
    """An erasure retires a projected record, and the source still lists it. The next sync leaves it
    retired, with the fields it was retired with, and reads the rest of the page as usual.

    Delete this and a sync undoes an erasure on its next run, silently, as the worker, which is the
    one thing `A_RETIRED_RECORD_STAYS_RETIRED_WHATEVER_THE_SOURCE_SAYS` exists to refuse."""
    with a_database("brain_connector_sync_retired") as url:
        connect(url)
        sql(
            url,
            "INSERT INTO proj.record (source, entity, source_id, fields, last_seen_at, deleted_at) "
            "VALUES ('xero', 'invoice', %s, '{}'::jsonb, %s, %s)",
            INVOICE_ID,
            NOW - timedelta(days=30),
            NOW - timedelta(days=1),
        )
        ran = sync(url, Replay([answer_for("XERO-200-invoices"), NO_CONTACTS]))
        rows = projected(url)
        after = read_as(url, ENTITLED)

    assert ran.read == 1
    ((_, _, _, fields, last_seen_at, deleted_at),) = rows
    assert fields == {}
    assert last_seen_at == NOW - timedelta(days=30)
    assert deleted_at == NOW - timedelta(days=1)
    assert after["records"] == []


@pytest.mark.needs_db
def test_the_schedule_starts_the_real_sync_and_a_run_with_nothing_connected_says_so() -> None:
    """The control the worker's tick starts, reached through `start_control` with the worker's real
    parts: its vault reader from this process's settings, the HTTPS caller and the system resolver,
    over a database with no connection, so nothing is called. In report-only mode it reads nothing
    and says why.

    Delete this and the runner could import, build or name something that fails only when the
    schedule first starts it, which is the first time anybody would see it."""
    from brain.ops.schedule_runner import A_READ_IN_REPORT_ONLY_MODE_READS_NOTHING, start_control

    with a_database("brain_connector_sync_started") as url:
        said = start_control("connector_sync", now=NOW, report_only=False, database_url=url)
        reported = start_control("connector_sync", now=NOW, report_only=True, database_url=url)
        runs = attempts(url)

    assert said == SyncRun(read=0, waiting=0, failed=0, not_due=0, cannot_be_read=0).summary()
    assert A_READ_IN_REPORT_ONLY_MODE_READS_NOTHING in reported
    assert runs == []


# ------------------------------------------------------------------ documents


class DocumentReading(XeroReading):
    """Xero's reading, with each invoice row also handed over as a department's document.

    Written here because no connectable source yields documents; see the module docstring.
    """

    def __init__(self, *, owner: str, department: str) -> None:
        self.owner = owner
        self.department = department

    def document(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> KnowledgeItem | None:
        del seen_at
        if entity != xero.ENTITY_INVOICE:
            return None
        return KnowledgeItem(
            item_id=f"src.xero.{row['id']}",
            content=f"Invoice {row['invoice_number']} is {str(row['status']).lower()}.",
            title=f"Invoice {row['invoice_number']}",
            visibility=KnowledgeVisibility.of_department(self.department, owner_id=self.owner),
            owner_id=self.owner,
            state=KnowledgeState.PUBLISHED,
        )


@pytest.mark.needs_db
def test_a_synced_document_is_found_within_its_owners_department_and_is_absent_outside_it() -> None:
    """**The leaf's second proof.** A reading hands the recorded invoice over as a web department
    document owned by a person who reads web. The run hands it to `ingest_document`, which writes
    it under that owner's reach, and the attempt counts one document. A search as a web reader finds
    it; a search as a finance reader is handed, whole, what it was handed before the sync, when the
    document did not exist. A document whose owner reaches nothing is withheld and the run says so
    in one sentence, with no count.

    Delete this and the document leg can write a document everybody finds, or nobody, with the
    record leg's tests all green."""
    from tests.unit.test_embedding_path_db import (
        A_REVISION,
        FINANCE_OWNER,
        WEB_OWNER,
        _database,
        people,
        reader_of,
    )

    queued: list[Job] = []

    def ask(url: str, who: EntitlementSet) -> Mapping[str, Any]:
        async def work(sessions: async_sessionmaker[AsyncSession]) -> Mapping[str, Any]:
            handler = searcher(SessionRowSource(sessions))
            found = await handler(DocumentSearch(question="authorised"), entitlement=who, now=NOW)
            return found.model_dump(mode="json")

        engine_url = url

        async def go() -> Mapping[str, Any]:
            engine = make_app_engine(engine_url)
            try:
                return await work(make_application_sessions(engine))
            finally:
                await engine.dispose()

        return run(go)

    def sink_for(url: str) -> Callable[[KnowledgeItem], Awaitable[object]]:
        async def sink(item: KnowledgeItem) -> object:
            async def enqueue(job: Job) -> None:
                queued.append(job)

            engine = make_app_engine(url)
            try:
                return await ingest_document(
                    make_application_sessions(engine),
                    item,
                    enqueue=enqueue,
                    now=NOW,
                    env={REVISION_SETTING: A_REVISION},
                )
            finally:
                await engine.dispose()

        return sink

    with _database("brain_connector_sync_documents") as url:
        people(url)
        add_modelled(url, SYNC_TABLES)
        connect(url)
        web, finance = reader_of(WEB_OWNER, "web"), reader_of(FINANCE_OWNER, "finance")
        before = {"web": ask(url, web), "finance": ask(url, finance)}
        sync(
            url,
            Replay([answer_for("XERO-200-invoices"), NO_CONTACTS]),
            readings={"xero": DocumentReading(owner=WEB_OWNER, department="web")},
            documents=sink_for(url),
        )
        after = {"web": ask(url, web), "finance": ask(url, finance)}
        ((_, _, records, documents, _, _, _, detail),) = attempts(url)

    assert (records, documents, detail) == (1, 1, READ_TO_THE_END)
    assert before["web"]["records"] == []
    assert [one["document_id"] for one in after["web"]["records"]] == [f"src.xero.{INVOICE_ID}"]
    assert after["finance"] == before["finance"]


# ------------------------------------------------------------------ the key


@dataclass
class Vault:
    """`StaticKvReader` answering with one slot's fields, or refusing as it is told."""

    fields: Mapping[str, Any] = field(default_factory=lambda: {KEY_FIELD: KEY})
    refuse: Exception | None = None
    asked: list[str] = field(default_factory=list)

    def read_static_kv(self, path: str) -> dict[str, Any]:
        self.asked.append(path)
        if self.refuse is not None:
            raise self.refuse
        return dict(self.fields)


def test_the_worker_reads_a_key_only_at_a_sources_slot_and_only_for_its_own_role() -> None:
    """**The key-handling half of the leaf.** A reference outside `connector_keys/`, the engine's
    bare prefix, the leased connector path and a reference made for the application are each
    refused before the vault is asked; the sibling is the source's own slot under the worker's
    role, which is read.

    Delete this and a declaration edited to point at a provider key, or at another role's path, is
    handed to the vault by the least-watched process in the system."""
    vault = Vault()
    keys = WorkerConnectorKeys(vault)
    slot = connector_key_slot("xero").path
    for refused in (
        SecretRef(path="providers/anthropic", role=VaultRole.WORKER),
        SecretRef(path="connector_keys/", role=VaultRole.WORKER),
        SecretRef(path="connectors/creds/xero", role=VaultRole.WORKER),
        SecretRef(path=slot, role=VaultRole.APPLICATION),
    ):
        with pytest.raises(SecretsUnavailableError):
            keys.key_for(refused)
    assert vault.asked == []

    assert keys.key_for(SecretRef(path=slot, role=VaultRole.WORKER)) == KEY
    assert vault.asked == [slot]


def test_an_empty_slot_is_absent_and_each_vault_failure_says_its_own_sentence() -> None:
    """A slot the vault answers 404 for, or holds with no key, is no key; a refusal is the policy; a
    silence is the vault; no vault at all names the two settings.

    Delete this and every failure reads as the vault being down, and the person sent to fix it
    restarts OpenBao for a key nobody put in."""
    ref = SecretRef(path=connector_key_slot("xero").path, role=VaultRole.WORKER)

    def failure(vault: Vault | None) -> SecretsUnavailableError:
        with pytest.raises(SecretsUnavailableError) as raised:
            WorkerConnectorKeys(vault).key_for(ref)
        return raised.value

    missing = failure(Vault(refuse=VaultRefusedError("gone", status=404)))
    blank = failure(Vault(fields={KEY_FIELD: "  "}))
    refused = failure(Vault(refuse=VaultRefusedError("no", status=403)))
    silent = failure(Vault(refuse=VaultUnreachableError("timeout")))
    none = failure(None)

    assert isinstance(missing, ConnectorKeyAbsentError)
    assert isinstance(blank, ConnectorKeyAbsentError)
    assert [key_detail(one) for one in (missing, blank, refused, silent, none)] == [
        NO_KEY,
        NO_KEY,
        VAULT_REFUSED,
        VAULT_UNREACHABLE,
        NO_VAULT,
    ]


def test_a_worker_with_half_a_vault_configuration_has_none_and_prints_no_token() -> None:
    """Delete this and a worker with an address and no token builds a client that fails as a
    refusal, and a traceback holding the reader prints the token."""
    for keys in (worker_connector_keys("", ""), worker_connector_keys("http://vault:8200", "")):
        assert "configured=False" in repr(keys)
    configured = worker_connector_keys("http://vault:8200", "a-token")
    assert "configured=True" in repr(configured)
    assert "a-token" not in repr(configured)
    assert "vault:8200" not in str(configured)


def test_the_worker_policy_grants_read_on_the_path_the_reader_calls_and_nothing_more() -> None:
    """Held against the path `OpenBaoVault` reads for a source name at the grammar's longest.

    Delete this and a source name that makes two path segments is refused by the vault on the first
    install, or the worker's rule widens with nothing reading the policy."""
    granted = _granted_paths(_policy_file(VaultRole.WORKER).read_text(encoding="utf-8"))
    mount, _, rest = connector_key_slot("a" + "0" * 62).path.partition("/")

    assert [caps for rule, caps in granted.items() if _matches(rule, f"{mount}/data/{rest}")] == [
        ["read"]
    ]
    assert not [rule for rule in granted if _matches(rule, f"{mount}/metadata/{rest}")]
    assert "worker" in THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES


# ------------------------------------------------------------------ the call


@dataclass
class _Asked:
    path: str
    headers: dict[str, str]


@dataclass
class _Source:
    port: int
    trusted: ssl.SSLContext
    asked: list[_Asked]
    status: list[int]
    body: list[bytes]


@pytest.fixture
def source(tmp_path: Path) -> Iterator[_Source]:
    """An HTTPS source on the loopback interface answering GETs as `NAME`."""
    cert, key = _certificate(tmp_path, NAME)
    asked: list[_Asked] = []
    status = [200]
    body = [b'{"Invoices": []}']

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            asked.append(_Asked(self.path, dict(self.headers.items())))
            self.send_response(status[0])
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", "60")
            self.send_header("Content-Length", str(len(body[0])))
            self.end_headers()
            self.wfile.write(body[0])

        def log_message(self, *args: Any) -> None:
            return None

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    serving = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    serving.load_cert_chain(cert, key)
    server.socket = serving.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield _Source(
            int(server.server_address[1]),
            ssl.create_default_context(cafile=str(cert)),
            asked,
            status,
            body,
        )
    finally:
        server.shutdown()
        server.server_close()


def test_a_call_goes_to_the_checked_address_as_the_name_with_its_headers_and_reads_the_answer(
    source: _Source,
) -> None:
    """The name ends in `.invalid`, so a caller that looked it up again could not have connected.
    The source receives the key header and the product's user agent, and the answer comes back as
    its status, its headers and its body.

    Delete this and a caller that connected by name reopens the rebinding hole with a key attached,
    or one that dropped the status reads a refusal as a ledger."""
    source.status[0] = 429
    got = HttpsSourceCaller(context=source.trusted).get(
        f"https://{NAME}:{source.port}/api.xro/2.0/Invoices?page=1",
        address="127.0.0.1",
        headers={"Authorization": f"Bearer {KEY}"},
        max_bytes=1024,
    )

    assert (got.status, got.body, got.timed_out, got.connection_failed) == (
        429,
        b'{"Invoices": []}',
        False,
        False,
    )
    assert got.headers is not None
    assert got.headers["retry-after"] == "60"
    (asked,) = source.asked
    assert asked.path == "/api.xro/2.0/Invoices?page=1"
    assert asked.headers["Authorization"] == f"Bearer {KEY}"
    assert asked.headers["User-Agent"] == USER_AGENT
    assert asked.headers["Host"] == f"{NAME}:{source.port}"


def test_a_body_past_the_bound_is_not_read_as_a_shorter_answer_and_http_is_never_called(
    source: _Source,
) -> None:
    """Delete this and a truncated body parses as a shorter list, or a plain-http address is sent
    the key."""
    source.body[0] = b'{"Invoices": [' + b" " * 2048 + b"]}"
    caller = HttpsSourceCaller(context=source.trusted)
    long = caller.get(
        f"https://{NAME}:{source.port}/x", address="127.0.0.1", headers={}, max_bytes=1024
    )
    plain = caller.get(
        f"http://{NAME}:{source.port}/x", address="127.0.0.1", headers={}, max_bytes=1024
    )

    assert (long.status, long.body) == (200, b"")
    assert plain.connection_failed is True
    assert len(source.asked) == 1


def test_a_certificate_for_another_name_is_a_failed_connection_and_sends_nothing(
    source: _Source,
) -> None:
    """Delete this and a caller that skipped verification sends a source's key to whatever answers
    on that address."""
    got = HttpsSourceCaller(context=source.trusted).get(
        f"https://another.source.invalid:{source.port}/x",
        address="127.0.0.1",
        headers={"Authorization": f"Bearer {KEY}"},
        max_bytes=1024,
    )

    assert got.connection_failed is True
    assert source.asked == []


def test_hubspots_reading_would_follow_every_page_it_is_told_of_once_its_ceiling_is_recorded() -> (
    None
):
    """The reading HubSpot has today, driven as the run drives it, page by page over a cursor.

    Delete this and HubSpot's reading can be broken in any way at all while its ceiling is
    unverified, and the day the row is added the first run reads one page and stops."""
    reading = HubSpotReading()
    pages = [
        {"results": [], "paging": {"next": {"after": "c2"}}},
        {"results": [], "paging": {"next": {"after": "c3"}}},
        {"results": []},
    ]
    asked = [dict(reading.first_page("client"))]
    for page in pages:
        following = reading.next_page("client", asked[-1], page, 0)
        if following is None:
            break
        asked.append(dict(following))

    assert [one.get("after") for one in asked] == [None, "c2", "c3"]
