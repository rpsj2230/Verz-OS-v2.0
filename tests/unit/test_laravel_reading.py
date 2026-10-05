"""The Laravel database read by the worker, by a question and by a test of the connection (M11.6.1).

`tests/unit/test_laravel.py` holds the connector's decisions and `tests/unit/test_laravel_reader.py`
the executor. This holds the three places a read of the company's views is made, each through
`laravel.LaravelReading`, the real executor and a recorded driver that opens no socket: the
worker's scheduled read into the minimal index, the live read of one record while somebody waits,
and the connection test. And it holds the rule that put Laravel on the Connectors screen: it is
offered because it reads, and would not be without its reading or its ceiling.

The address every name resolves to is `2000::1`, global unicast in a block no registry has handed
to anybody, which the address rule admits and nothing connects to, because the driver is recorded.

Task ids: M11.6.1, M11.7.7
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Final, cast

import pymysql
import pytest
from structlog.testing import capture_logs

from brain.connectors import laravel
from brain.connectors.contract import FetchRequest
from brain.connectors.declaration import (
    DatabaseLogin,
    PageReply,
    SettingRefusedError,
    ViewReading,
)
from brain.connectors.laravel import (
    ENTITY_CLIENT,
    ENTITY_USER,
    PROJECTED_FIELDS,
    LaravelConnection,
    LaravelError,
    LaravelReading,
    ViewReader,
    checked_address,
    connection_of,
)
from brain.connectors.live_read import RECORD_ID_FILTER, LiveReply
from brain.connectors.manifest import manifest_digest
from brain.connectors.minimal_index import fresh_canary, sightings
from brain.connectors.throttle import CallOutcome
from brain.core.envelope import IdentityMode
from brain.ops.connectable import (
    CONNECTABLE,
    THIS_INSTALL_CANNOT_READ_IT_YET,
    key_reference,
    manifest_for,
    offered,
    reads,
)
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.connector_probe_run import probe_one
from brain.ops.connector_store import Connection, StoredConnections
from brain.ops.connector_sync import (
    ADDRESS_REFUSED,
    DATABASE_REFUSED,
    PROBE_ANSWERED,
    READ_BUT_CUT_SHORT,
    READ_TO_THE_END,
    SHAPE_DISAGREED,
    SyncOutcome,
    plan_for,
)
from brain.ops.connector_sync_run import (
    ConnectorKeyAbsentError,
    SourceAnswer,
    WorkerConnectorKeys,
    attempt,
    sync_on,
)
from brain.ops.connector_sync_store import LiveConnection
from brain.ops.credentials import KEY_FIELD, USER_FIELD
from brain.ops.laravel_reader import MySqlViewReader
from brain.ops.leases import SealedSecret
from brain.ops.live_read_run import ConnectedSources
from brain.tools.fetch import UnsafeAddressError
from tests.unit.test_connector_sync_run import (
    RunReader,
    Vault,
    audited,
    no_sleep,
    projected,
    through,
)

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
NOW: Final = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)

#: The read-only user's password, which nothing but the driver may ever be handed.
PASSWORD: Final = "DB-PASSWORD-SENTINEL-8e30"
USER: Final = "brain_reader"

#: Where every name resolves: global, so the rule admits it, and connected to by nothing.
PUBLIC: Final = "2000::1"

#: A private address, which the rule refuses unless the connection says its database is private.
PRIVATE: Final = "10.0.0.5"

DEPARTMENT: Final = "maintenance"

SETTINGS: Final[Mapping[str, str]] = {
    "schema": "portal",
    "host": "db.example.invalid",
    "port": "3306",
    "private_network": "no",
    "tls": "verify",
    "client_rule": f"department = {DEPARTMENT}",
    "user_rule": f"department = {DEPARTMENT}",
    "max_rows": "200",
    "timeout_seconds": "5",
}


class Resolver:
    """Every name answers the one address it was built with."""

    def __init__(self, address: str = PUBLIC) -> None:
        self.address = address
        self.asked: list[str] = []

    def resolve(self, host: str) -> list[str]:
        self.asked.append(host)
        return [self.address]


# ------------------------------------------------------------------ the recorded database


@dataclass
class Views:
    """A driver answering each view's `SELECT` with the rows the test wrote for it. No socket.

    `refuse` is the MySQL error number every `SELECT` is answered with instead. `opened` holds the
    arguments of every connection, `selected` every `SELECT` with its parameters.
    """

    clients: Sequence[Mapping[str, Any]] = ()
    users: Sequence[Mapping[str, Any]] = ()
    refuse: int | None = None
    opened: list[dict[str, Any]] = field(default_factory=list)
    selected: list[tuple[str, object]] = field(default_factory=list)
    closed: int = 0

    def __call__(self, **kwargs: Any) -> Any:
        self.opened.append(kwargs)
        return _Session(self)

    def opener(
        self, address: str, connection: LaravelConnection, login: DatabaseLogin
    ) -> ViewReader:
        """`laravel.ViewReaderOpener` over the real executor, driving this recording."""
        return MySqlViewReader(
            address=address,
            port=connection.port,
            login=login,
            server_name=connection.host,
            tls=connection.tls,
            driver=self,
        )


@dataclass
class _Session:
    views: Views
    rows: Sequence[Mapping[str, Any]] = ()

    def cursor(self) -> _Session:
        return self

    def execute(self, query: str, args: object = None) -> int:
        if not query.startswith("SELECT"):
            return 0
        self.views.selected.append((query, args))
        if self.views.refuse is not None:
            raise pymysql.err.OperationalError(self.views.refuse, "recorded")
        self.rows = self.views.clients if "v_client" in query else self.views.users
        return len(self.rows)

    def fetchall(self) -> Sequence[Mapping[str, Any]]:
        return tuple(dict(one) for one in self.rows)

    def close(self) -> None:
        self.views.closed += 1


def a_client(
    number: int, canary: str = "CANARY-CONTRACT-7Q4XZ", **overrides: Any
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": number,
        "contract_value": canary,
        "department": DEPARTMENT,
        "manager_id": 7,
        "name": f"Client {number}",
        "status": "active",
        "updated_at": datetime(2019, 3, 1, 10, 0),
    }
    row.update(overrides)
    return row


def a_user(number: int) -> dict[str, Any]:
    return {
        "id": number,
        "department": DEPARTMENT,
        "display_name": f"Staff {number}",
        "status": "active",
        "updated_at": datetime(2019, 3, 1, 10, 0),
    }


def a_vault(**fields: Any) -> Vault:
    """The vault holding a database user's slot: the password as the key, the user beside it."""
    kept = fields if fields else {KEY_FIELD: PASSWORD, USER_FIELD: USER}
    return Vault(reader=RunReader(fields=kept))


def a_connection(**settings: str) -> Connection:
    typed = {**SETTINGS, **settings}
    return Connection(
        connector=laravel.CONNECTOR_NAME,
        settings=typed,
        digest=manifest_digest(manifest_for(laravel.CONNECTOR_NAME, typed)),
        connected_by="u_admin",
        connected_at=NOW,
    )


class NoCall:
    """A REST caller a database's read must never use."""

    def get(self, url: str, *, address: str, headers: Any, max_bytes: int) -> SourceAnswer:
        raise AssertionError("a database's views were read over HTTP")


def read_once(views: Views, resolver: Resolver, **settings: str) -> PageReply:
    return LaravelReading(opener=views.opener).read(
        FetchRequest(entity=ENTITY_CLIENT),
        settings={**SETTINGS, **settings},
        login=DatabaseLogin(USER, SealedSecret(PASSWORD)),
        resolver=resolver,
        fetched_at=NOW.isoformat(),
    )


# ------------------------------------------------------------------ the address


def test_a_private_host_is_refused_with_the_setting_off_and_read_with_it_on() -> None:
    """`A_PRIVATE_ADDRESS_IS_THE_CONNECTION_S_OWN_DECISION`, on the read. A name resolving inside
    the network is refused by the REST sources' own rule before any connection is opened; the same
    name with the connection saying its database is private is read, at the address the name
    resolved to. Delete this and a Laravel connection is a way to make this server open a
    connection to its own network, or a company's private database can never be read."""
    views = Views(clients=(a_client(1),))
    with pytest.raises(UnsafeAddressError):
        read_once(views, Resolver(PRIVATE))
    assert views.opened == []

    reply = read_once(views, Resolver(PRIVATE), private_network="yes")
    assert reply.call is CallOutcome.OK and reply.rows is not None
    assert [one["host"] for one in views.opened] == [PRIVATE]


def test_a_public_host_is_read_at_the_address_the_rule_checked_and_not_by_its_name() -> None:
    """The positive case of the rule: the read connects to the address the check resolved, so a
    name that answers differently the second time is not looked up a second time. Delete this and
    the rule can be a check that refuses every name."""
    views = Views(clients=(a_client(1),))
    resolver = Resolver()
    reply = read_once(views, resolver)
    assert reply.call is CallOutcome.OK
    assert resolver.asked == ["db.example.invalid"]
    assert [one["host"] for one in views.opened] == [PUBLIC]


def test_a_private_address_as_the_host_is_refused_at_connect_unless_the_database_is_private() -> (
    None
):
    """At construction, where no resolver is needed: an address literal inside the network with the
    setting off is refused in front of whoever typed it, and taken with it on. Delete this and the
    refusal waits for the first read, after the connection was saved."""
    with pytest.raises(SettingRefusedError) as refused:
        connection_of({**SETTINGS, "host": PRIVATE})
    assert refused.value.setting == "host"
    with pytest.raises(LaravelError):
        dataclasses.replace(connection_of(SETTINGS), host=PRIVATE)
    taken = connection_of({**SETTINGS, "host": PRIVATE, "private_network": "yes"})
    assert checked_address(taken, resolver=Resolver()) == PRIVATE


# ------------------------------------------------------------------ what one read is


def test_absent_refused_and_unreachable_stay_three_through_the_reading() -> None:
    """An empty view answers with no records; a withdrawn grant, a gone view and a changed password
    are REJECTED; a server that went away is UNAVAILABLE; and a read at its cap is TRUNCATED, all
    as the worker and the live read receive them. Delete this and a dropped view reaches the index
    as a company with no clients."""
    empty = read_once(Views(), Resolver())
    assert empty.call is CallOutcome.OK and empty.rows is not None and empty.rows.records == ()
    for number in (1142, 1146, 1045):
        refused = read_once(Views(refuse=number), Resolver())
        assert (refused.call, refused.rows) == (CallOutcome.REJECTED, None)
    gone = read_once(Views(refuse=2006), Resolver())
    assert (gone.call, gone.rows) == (CallOutcome.UNAVAILABLE, None)
    full = read_once(Views(clients=(a_client(1), a_client(2))), Resolver(), max_rows="2")
    assert full.call is CallOutcome.TRUNCATED


def test_the_reading_is_the_worker_s_view_reading_and_keeps_no_login() -> None:
    """The shipped declaration's reading is a `ViewReading`, holds its opener and nothing else,
    and its live lookup names the record's id and nothing that could change the statement. Delete
    this and a reading could keep the login it was handed past the read, or the live read could
    narrow by a value that is not an id."""
    reading = laravel.CONNECTOR.reading
    assert isinstance(reading, ViewReading) and isinstance(reading, LaravelReading)
    assert [one.name for one in dataclasses.fields(reading)] == ["opener"]
    live = laravel.CONNECTOR.live
    assert live is not None
    assert live.entities() == (ENTITY_CLIENT, ENTITY_USER)
    assert live.identity_mode(ENTITY_CLIENT) is IdentityMode.SERVICE
    assert live.arguments_for(ENTITY_CLIENT, "4471") == {RECORD_ID_FILTER: "4471"}
    assert live.arguments_for(ENTITY_USER, "01J9Z3ACEPTANCE0000000000") == {
        RECORD_ID_FILTER: "01J9Z3ACEPTANCE0000000000"
    }
    for hostile in ("1 OR 1=1", "1;", "", "x" * 65):
        with pytest.raises(LaravelError):
            live.arguments_for(ENTITY_CLIENT, hostile)
    with pytest.raises(LaravelError):
        live.arguments_for("invoice", "1")


# ------------------------------------------------------------------ the credential


def test_the_lease_hands_over_the_user_beside_the_password_and_forgets_both_when_it_closes() -> (
    None
):
    """The slot a database user is kept in holds the password as the key and the user beside it;
    the lease hands over both for the attempt and neither after it closes, and a slot holding one
    key has no user to hand over. Delete this and the worker reads a database as nobody, or keeps
    the login after the lease is given back."""
    vault = a_vault()
    lease = WorkerConnectorKeys(vault).lease(key_reference(laravel.CONNECTOR_NAME), now=NOW)
    assert (lease.user(), lease.key()) == (USER, PASSWORD)
    assert PASSWORD not in repr(lease)
    assert lease.close(NOW) is LeaseOutcome.REVOKED
    with pytest.raises(ConnectorKeyAbsentError):
        lease.user()
    with pytest.raises(ConnectorKeyAbsentError):
        lease.key()

    key_only = WorkerConnectorKeys(a_vault(**{KEY_FIELD: PASSWORD})).lease(
        key_reference(laravel.CONNECTOR_NAME), now=NOW
    )
    assert key_only.key() == PASSWORD
    with pytest.raises(ConnectorKeyAbsentError):
        key_only.user()


def test_a_database_slot_with_no_user_fails_the_attempt_and_opens_no_connection() -> None:
    """The attempt reads the user before anything else, and a slot keeping none is the key being
    absent. Delete this and a read is attempted as an empty user name."""
    views = Views(clients=(a_client(1),))
    connection = a_connection()
    plan = plan_for(
        connection, last=None, now=NOW, readings={"laravel": LaravelReading(views.opener)}
    )
    done = asyncio.run(
        attempt(
            LiveConnection(id=uuid.uuid4(), connection=connection),
            plan,
            previous=None,
            sessions=cast(Any, None),
            keys=WorkerConnectorKeys(a_vault(**{KEY_FIELD: PASSWORD})),
            caller=NoCall(),
            resolver=Resolver(),
            clock=lambda: NOW,
            sleep=no_sleep,
        )
    )
    assert done.outcome is SyncOutcome.FAILED and views.opened == []
    assert done.lease is LeaseOutcome.REVOKED


def test_an_address_the_rule_refuses_fails_the_worker_s_read_and_is_said_so() -> None:
    """The worker records the refused address in the sentence every source's refusal leaves, and
    the database is never connected to. Delete this and a refused address reads as the source
    answering in a shape nobody declared, which sends the operator to the wrong place."""
    views = Views(clients=(a_client(1),))
    connection = a_connection()
    plan = plan_for(
        connection, last=None, now=NOW, readings={"laravel": LaravelReading(views.opener)}
    )
    assert not plan.refused
    done = asyncio.run(
        attempt(
            LiveConnection(id=uuid.uuid4(), connection=connection),
            plan,
            previous=None,
            sessions=cast(Any, None),
            keys=WorkerConnectorKeys(a_vault()),
            caller=NoCall(),
            resolver=Resolver(PRIVATE),
            clock=lambda: NOW,
            sleep=no_sleep,
        )
    )
    assert (done.outcome, done.detail) == (SyncOutcome.FAILED, ADDRESS_REFUSED)
    assert views.opened == []


# ------------------------------------------------------------------ the worker's index


def connect(url: str) -> None:
    """Connect the database through the store the Connectors route writes with, keeping no key."""
    connection = a_connection()

    async def kept() -> datetime | None:
        return None

    through(
        url,
        lambda sessions: StoredConnections(sessions).connect(
            connector=connection.connector,
            settings=dict(connection.settings),
            digest=connection.digest,
            actor="u_admin",
            trace_id="t-connect",
            ent_hash="0" * 32,
            keep_key=kept,
        ),
    )


@pytest.mark.needs_db
def test_the_worker_keeps_only_the_minimal_index_and_the_contract_value_is_in_no_table_or_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """**The owner's rule, on a database built through every migration.** The worker reads both
    views through the real executor and a recorded driver, as the user the vault keeps: each view
    once, capped and bounded, with the password handed to the driver and nowhere else. Every
    `proj.record` row holds only the fields the view's projection names, the contract value (a
    canary) and a column no contract names are in no table and no log line, and the lease is given
    back. The positive half: a client's name, an index field, is found by the same search.

    Delete this and the database's rows could be kept whole, or the contract value stored beside
    the index, with every test over a single read still green."""
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.fixtures.scratch_postgres import admin_url

    if not has_pgvector(admin_url()):
        pytest.skip("every table needs the full chain, which needs pgvector; CI's image has it")
    canary = fresh_canary("LARAVEL")
    views = Views(
        clients=(a_client(1, canary), a_client(2, canary, api_token=canary)),
        users=(a_user(12),),
    )
    vault = a_vault()
    caplog.set_level(logging.DEBUG)
    clock = iter(NOW + timedelta(seconds=n) for n in range(10_000))
    with retirable("brain_laravel_index") as url, capture_logs() as logged:
        connect(url)
        ran = through(
            url,
            lambda sessions: sync_on(
                sessions=sessions,
                now=NOW,
                keys=WorkerConnectorKeys(vault),
                caller=NoCall(),
                resolver=Resolver(),
                clock=lambda: next(clock),
                sleep=no_sleep,
                readings={"laravel": LaravelReading(views.opener)},
            ),
        )
        rows = projected(url)
        report = audited(url, canary)
        named = audited(url, "Client 1")
        details = [str(one) for (one,) in _details(url)]

    assert (ran.read, ran.failed) == (1, 0)
    assert details == [READ_TO_THE_END]
    assert len(views.selected) == 2 and views.closed == 2
    assert {one["password"] for one in views.opened} == {PASSWORD}
    assert vault.reader.revoked == 1
    kept = {(entity, source_id): set(fields) for _, entity, source_id, fields, *_ in rows}
    assert set(kept) == {(ENTITY_CLIENT, "1"), (ENTITY_CLIENT, "2"), (ENTITY_USER, "12")}
    for (entity, _), names in kept.items():
        assert names == {one.name for one in PROJECTED_FIELDS[entity]}
    assert report.holding == ()
    assert "proj.record" in named.holding
    assert sightings(canary, logged, [one.getMessage() for one in caplog.records]) == ()
    assert sightings(PASSWORD, logged, [one.getMessage() for one in caplog.records]) == ()


def _details(url: str) -> list[tuple[Any, ...]]:
    from tests.fixtures.scratch_postgres import sql

    return sql(url, "SELECT detail FROM ops.connector_sync ORDER BY finished_at")


def test_a_view_that_fills_its_cap_is_read_as_far_as_one_run_reads() -> None:
    """A database does not page, so a read that reached its row cap is cut short and read again
    from the start by the next run, and the sentence says so. The rows are not written here,
    because the cut is decided before the write. Delete this and a view larger than the cap reads
    as read to the end, and the index is quietly missing clients."""
    views = Views(clients=(a_client(1), a_client(2)), users=())
    connection = a_connection(max_rows="2")
    plan = plan_for(
        connection, last=None, now=NOW, readings={"laravel": LaravelReading(views.opener)}
    )
    written: list[Any] = []

    class Sessions:
        """Enough of a session factory for `_write_page`: a transaction that records statements."""

        def __call__(self) -> Sessions:
            return self

        async def __aenter__(self) -> Sessions:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def begin(self) -> Sessions:
            return self

        async def execute(self, statement: Any) -> Any:
            # The index rows written, and nothing else: the worker also reads the rows a page
            # names before writing it, and counts a change in the source's epoch.
            if getattr(statement, "table", None) is not None and (
                statement.table.fullname == "proj.record"
            ):
                written.append(statement)
            return SimpleNamespace(all=list, scalars=lambda: SimpleNamespace(all=list))

    done = asyncio.run(
        attempt(
            LiveConnection(id=uuid.uuid4(), connection=connection),
            plan,
            previous=None,
            sessions=cast(Any, Sessions()),
            keys=WorkerConnectorKeys(a_vault()),
            caller=NoCall(),
            resolver=Resolver(),
            clock=lambda: NOW,
            sleep=no_sleep,
        )
    )
    assert (done.outcome, done.detail, done.records) == (SyncOutcome.SYNCED, READ_BUT_CUT_SHORT, 2)
    assert len(written) == 2


def test_a_row_that_breaks_the_view_s_own_rule_fails_the_read_and_keeps_nothing() -> None:
    """A client in another department than the rule the view is kept under cannot be stored under
    that rule, so the page is refused whole in the sentence a shape nobody declared leaves. Delete
    this and a row could be kept under a rule it does not satisfy, and reached by the wrong
    readers."""
    views = Views(clients=(a_client(1, department="sales"),))
    connection = a_connection()
    plan = plan_for(
        connection, last=None, now=NOW, readings={"laravel": LaravelReading(views.opener)}
    )
    done = asyncio.run(
        attempt(
            LiveConnection(id=uuid.uuid4(), connection=connection),
            plan,
            previous=None,
            sessions=cast(Any, None),
            keys=WorkerConnectorKeys(a_vault()),
            caller=NoCall(),
            resolver=Resolver(),
            clock=lambda: NOW,
            sleep=no_sleep,
        )
    )
    assert (done.outcome, done.detail, done.records) == (SyncOutcome.FAILED, SHAPE_DISAGREED, 0)


def test_a_database_s_refusal_is_down_at_once_in_its_own_words() -> None:
    """A withdrawn grant, a gone view or a changed password fails the attempt with
    `DATABASE_REFUSED` and a REJECTED call, which is down at once; a server that went away is
    unreachable. Delete this and a dropped view is told to the operator as a key to replace."""
    for number, detail in ((1146, DATABASE_REFUSED), (2006, "The source did not answer.")):
        views = Views(refuse=number)
        connection = a_connection()
        plan = plan_for(
            connection, last=None, now=NOW, readings={"laravel": LaravelReading(views.opener)}
        )
        done = asyncio.run(
            attempt(
                LiveConnection(id=uuid.uuid4(), connection=connection),
                plan,
                previous=None,
                sessions=cast(Any, None),
                keys=WorkerConnectorKeys(a_vault()),
                caller=NoCall(),
                resolver=Resolver(),
                clock=lambda: NOW,
                sleep=no_sleep,
            )
        )
        assert (done.outcome, done.detail) == (SyncOutcome.FAILED, detail)


# ------------------------------------------------------------------ a live read


def test_a_live_read_returns_the_value_the_index_never_kept_under_a_borrowed_lease() -> None:
    """**The contract value, read while somebody waits.** The live read narrows the view's read to
    the record's id, bound as a parameter, as the user the vault keeps, and hands back the value;
    the lease is given back when the read ends. Delete this and the one value this connector exists
    to answer is never read, or read under a lease nobody gives back."""
    canary = fresh_canary("LIVE")
    views = Views(clients=(a_client(4471, canary),))
    vault = a_vault()
    sources = ConnectedSources(
        {laravel.CONNECTOR_NAME: a_connection()},
        keys=WorkerConnectorKeys(vault),
        caller=NoCall(),
        resolver=Resolver(),
        clock=lambda: NOW,
        declarations={
            laravel.CONNECTOR_NAME: dataclasses.replace(
                laravel.CONNECTOR, reading=LaravelReading(views.opener)
            )
        },
    )
    assert sources.reads(laravel.CONNECTOR_NAME, ENTITY_CLIENT) is IdentityMode.SERVICE
    fetch = sources.source_for(laravel.CONNECTOR_NAME, mode=IdentityMode.SERVICE, asker="u_finance")
    assert fetch is not None

    async def asked(source_id: str) -> LiveReply:
        return await fetch(
            FetchRequest(entity=ENTITY_CLIENT, filters=((RECORD_ID_FILTER, source_id),))
        )

    reply = asyncio.run(asked("4471"))
    assert reply.outcome is CallOutcome.OK and reply.rows is not None
    [record] = reply.rows.records
    assert record.model_dump()["contract_value"] == canary
    [(statement, parameters)] = views.selected
    assert "WHERE portal.v_client.id = %s" in statement
    assert parameters == ("4471", 200)
    assert vault.reader.revoked == 1

    refused = asyncio.run(asked("1 OR 1=1"))
    assert refused.outcome is CallOutcome.REJECTED
    assert len(views.selected) == 1


# ------------------------------------------------------------------ a test of the connection


def test_a_connection_test_reads_one_row_and_keeps_nothing_or_says_the_database_refused() -> None:
    """The Connectors screen's test is one read of the first view with a row cap of one, as the
    user the vault keeps, and nothing it returns is kept; a refused read says the database refused
    in its own sentence. Delete this and a test of a database connection makes an HTTP call, or
    reads a whole view to prove a password."""
    for views, detail in (
        (Views(clients=(a_client(1),)), PROBE_ANSWERED),
        (Views(refuse=1142), DATABASE_REFUSED),
    ):
        connection = a_connection()
        plan = plan_for(
            connection, last=None, now=NOW, readings={"laravel": LaravelReading(views.opener)}
        )
        done = probe_one(
            LiveConnection(id=uuid.uuid4(), connection=connection),
            plan,
            previous=None,
            recent=(),
            keys=WorkerConnectorKeys(a_vault()),
            caller=NoCall(),
            resolver=Resolver(),
            clock=lambda: NOW,
        )
        assert done.detail == detail
        [(_, parameters)] = views.selected
        assert isinstance(parameters, tuple) and parameters[-1] == 1


# ------------------------------------------------------------------ the rule


def test_laravel_is_offered_because_it_reads_and_would_not_be_without_its_reading_or_ceiling() -> (
    None
):
    """`A_SOURCE_THE_CONSOLE_OFFERS_IS_ONE_THIS_INSTALL_READS`, on Laravel's own declaration.
    Offered as it ships; listed as not readable yet with neither a reading nor a live lookup, and
    under a name no ceiling is recorded for. Delete this and Laravel could be offered by a line in
    a list rather than by reading, or dropped from the screen with its reading in place."""
    real = laravel.CONNECTOR
    assert reads(real) and laravel.CONNECTOR_NAME in CONNECTABLE
    offers, listed = offered({laravel.CONNECTOR_NAME: real})
    assert set(offers) == {laravel.CONNECTOR_NAME} and listed == {}

    unread = dataclasses.replace(real, reading=None, live=None)
    offers, listed = offered({laravel.CONNECTOR_NAME: unread})
    assert offers == {}
    assert listed[laravel.CONNECTOR_NAME].why == THIS_INSTALL_CANNOT_READ_IT_YET

    unmeasured = dataclasses.replace(real, name="nowhere")
    offers, listed = offered({"nowhere": unmeasured})
    assert offers == {} and listed["nowhere"].why == THIS_INSTALL_CANNOT_READ_IT_YET
