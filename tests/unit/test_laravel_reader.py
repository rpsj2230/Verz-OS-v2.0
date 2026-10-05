"""The executor that reads a company's own MySQL: its statement, bounds, session and faults.

Two halves. The first drives `brain.ops.laravel_reader.MySqlViewReader` over a recorded driver,
which answers from what each test says and opens no socket, so every statement the executor sends
and every setting it hands the driver can be read back and asserted on whole. The second runs the
same executor against a real MySQL 8 server with one view and a read-only user, which the CI job
`laravel_mysql` starts and nothing else does: those tests are marked `needs_mysql` and skipped
when `LARAVEL_TEST_MYSQL_URL` is unset, so a laptop without MySQL skips them rather than
reporting a server it never reached.

Task ids: M11.6.1
"""

from __future__ import annotations

import ast
import os
import socket
import ssl
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote, urlsplit

import pymysql
import pytest

import brain.ops.laravel_reader as executor
from brain.connectors import laravel
from brain.connectors.declaration import DatabaseLogin
from brain.connectors.laravel import (
    ENTITY_CLIENT,
    ENTITY_USER,
    DatabaseFault,
    DatabaseTls,
    LaravelConnection,
    LaravelOutcome,
    ReadBounds,
    TlsMode,
    ViewReply,
    ca_certificate_of,
    interpret,
    read_plan,
)
from brain.knowledge.rows import assert_no_sql_is_built_by_interpolation
from brain.ops.laravel_reader import (
    DRIVER_GRACE_SECONDS,
    IN_UTC,
    MARIADB_TIME_BOUND,
    MYSQL_TIME_BOUND,
    READ_ONLY,
    UNKNOWN_SYSTEM_VARIABLE,
    MySqlViewReader,
    statement_for,
    tls_context,
)
from brain.ops.leases import SealedSecret
from tests.fixtures.tls import Issued, issued

SRC: Final = Path(__file__).resolve().parents[2] / "src" / "brain"

#: A password nothing else in any output could contain, so finding it anywhere is a leak.
PASSWORD: Final = "DB-PASSWORD-SENTINEL-51c2"

#: The address the executor is handed, from the documentation range, which nothing answers.
ADDRESS: Final = "192.0.2.10"

#: What the real-server tests read, and the variable the CI job sets it in.
MYSQL_URL: Final = os.environ.get("LARAVEL_TEST_MYSQL_URL", "")

needs_mysql = pytest.mark.skipif(
    not MYSQL_URL, reason="LARAVEL_TEST_MYSQL_URL is unset, so no MySQL server was read"
)


VERIFIED: Final = DatabaseTls(TlsMode.VERIFIED)
NO_ENCRYPTION: Final = DatabaseTls(TlsMode.NONE)


def a_connection(*, schema: str = "portal", max_rows: int = 200, seconds: float = 5.0) -> Any:
    return LaravelConnection(
        schema=schema,
        bounds=ReadBounds(max_rows=max_rows, timeout_seconds=seconds),
        host="db.example.invalid",
        port=3306,
        private_network=False,
        tls=VERIFIED,
    )


def a_login(user: str = "brain_reader", password: str = PASSWORD) -> DatabaseLogin:
    return DatabaseLogin(user, SealedSecret(password))


# ------------------------------------------------------------------ the recorded driver


@dataclass
class Recorded:
    """A driver answering from what the test says, opening no socket and noting everything.

    `refuse` maps a statement to the MySQL error number the server answers it with; `at_connect`
    is the number the connection itself fails with. Each error is PyMySQL's own class, carrying the
    number where the real driver puts it.
    """

    rows: Sequence[Mapping[str, Any]] = ()
    refuse: Mapping[str, int] = field(default_factory=dict)
    at_connect: int | None = None
    opened: list[dict[str, Any]] = field(default_factory=list)
    executed: list[tuple[str, object]] = field(default_factory=list)
    closed: int = 0

    def __call__(self, **kwargs: Any) -> Any:
        self.opened.append(kwargs)
        if self.at_connect is not None:
            raise pymysql.err.OperationalError(self.at_connect, "recorded")
        return _Session(self)


@dataclass
class _Session:
    driver: Recorded

    def cursor(self) -> _Cursor:
        return _Cursor(self.driver)

    def close(self) -> None:
        self.driver.closed += 1


@dataclass
class _Cursor:
    driver: Recorded

    def execute(self, query: str, args: object = None) -> int:
        self.driver.executed.append((query, args))
        number = self.driver.refuse.get(query)
        if number is not None:
            raise pymysql.err.OperationalError(number, "recorded")
        return 0

    def fetchall(self) -> Sequence[Mapping[str, Any]]:
        return tuple(self.driver.rows)


def reader(
    driver: Recorded, login: DatabaseLogin | None = None, tls: DatabaseTls = VERIFIED
) -> MySqlViewReader:
    return MySqlViewReader(
        address=ADDRESS,
        port=3306,
        login=a_login() if login is None else login,
        server_name="db.example.invalid",
        tls=tls,
        driver=driver,
    )


def a_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": 4471,
        "contract_value": Decimal("125000.50"),
        "department": "maintenance",
        "manager_id": 7,
        "name": "Acceptance client",
        "status": "active",
        "updated_at": datetime(2019, 3, 1, 10, 0),
    }
    row.update(overrides)
    return row


# ------------------------------------------------------------------ the statement


def test_a_read_is_one_select_of_its_allowlisted_view_with_every_value_bound() -> None:
    """`A_STATEMENT_IS_COMPILED_AND_NEVER_COMPOSED`, on the whole statement. The columns are the
    connector's list, the view is the allowlisted one, the filter's value and the row cap are
    parameters in the order the driver binds them, and the rows are ordered by the id. Delete this
    and the statement can select `*`, read a view the caller named, or carry a value in its text."""
    read = read_plan(a_connection(), ENTITY_CLIENT, filters=(("id", "4471"),))
    statement = statement_for(read)
    columns = ", ".join(f"portal.v_client.{one}" for one in read.columns)
    assert statement.text == (
        f"SELECT {columns} \nFROM portal.v_client \nWHERE portal.v_client.id = %s "
        "ORDER BY portal.v_client.id \n LIMIT %s"
    )
    assert statement.parameters == ("4471", 200)
    assert read.plan.view in a_connection().views()


def test_the_row_cap_is_a_bound_limit_in_the_statement_and_never_a_number_in_its_text() -> None:
    """The cap is what stops the server reading further, so it is in the statement, and it is a
    parameter like every value. Delete this and a read can go to the server with no `LIMIT`, which
    on a company's production database is the whole view."""
    for cap in (1, 37, laravel.MAX_ROWS_EVER):
        read = read_plan(a_connection(max_rows=cap), ENTITY_USER)
        statement = statement_for(read)
        assert statement.text.endswith("LIMIT %s")
        assert statement.parameters[-1] == cap == read.plan.limit
        assert str(cap) not in statement.text


def test_a_value_that_would_end_a_statement_is_bound_and_never_spliced() -> None:
    """The quote-and-comment value an injection is made of arrives as a parameter and appears
    nowhere in the text. Delete this and a filter value could be laid into the statement."""
    hostile = "x' OR '1'='1'; --"
    statement = statement_for(read_plan(a_connection(), ENTITY_CLIENT, filters=(("id", hostile),)))
    assert hostile not in statement.text and "'" not in statement.text
    assert statement.parameters[0] == hostile


def test_no_statement_the_executor_sends_is_built_by_interpolation() -> None:
    """`brain.knowledge.rows.assert_no_sql_is_built_by_interpolation` over the executor's parsed
    source, and the connector's own check over its. The positive sibling is the check refusing a
    module that composes one, which is `tests/unit/test_rows.py`'s. Delete this and a statement
    here can be built from an f-string with every other test green."""
    assert_no_sql_is_built_by_interpolation(executor)
    laravel.assert_builds_no_sql()


def test_only_the_executor_imports_the_driver() -> None:
    """Read from every module's parsed imports under `src/brain`. Delete this and the driver can
    be imported by a module that decides policy, which is then a module that owns a client."""
    importing = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [one.name for one in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            if any(one == "pymysql" or one.startswith("pymysql.") for one in names):
                importing.add(path.relative_to(SRC).as_posix())
    assert importing == {"ops/laravel_reader.py"}


# ------------------------------------------------------------------ the bounds and the session


def test_the_time_bound_is_set_on_the_driver_and_on_the_session_before_the_read() -> None:
    """`THE_DRIVER_S_TIMEOUT_IS_THE_FLOOR`. The driver connects within the bound and reads within
    the bound and its grace, and the session is made read-only, put in UTC and told the bound in
    milliseconds before the one `SELECT`, in that order. Delete this and a read can run on the
    company's database for as long as the server lets it, or be sent before the session is
    read-only."""
    driver = Recorded(rows=(a_row(),))
    read = read_plan(a_connection(seconds=7.0), ENTITY_CLIENT)
    reply = reader(driver).rows(read)

    assert reply.fault is None and len(reply.rows) == 1
    [opened] = driver.opened
    assert (opened["connect_timeout"], opened["read_timeout"], opened["write_timeout"]) == (
        7.0,
        7.0 + DRIVER_GRACE_SECONDS,
        7.0 + DRIVER_GRACE_SECONDS,
    )
    statement = statement_for(read)
    assert driver.executed == [
        (READ_ONLY, None),
        (IN_UTC, None),
        (MYSQL_TIME_BOUND, (7000,)),
        (statement.text, statement.parameters),
    ]


def test_a_server_with_no_max_execution_time_is_bounded_in_mariadb_s_own_words() -> None:
    """MariaDB answers `SET SESSION MAX_EXECUTION_TIME` with 1193, and the executor then sets
    `max_statement_time` in seconds and reads. Delete this and every read of a MariaDB database
    fails at its first statement, or is read with no bound on the server at all."""
    driver = Recorded(rows=(a_row(),), refuse={MYSQL_TIME_BOUND: UNKNOWN_SYSTEM_VARIABLE})
    reply = reader(driver).rows(read_plan(a_connection(seconds=4.0), ENTITY_CLIENT))
    assert reply.fault is None and len(reply.rows) == 1
    assert [one for one, _ in driver.executed][2:4] == [MYSQL_TIME_BOUND, MARIADB_TIME_BOUND]
    assert driver.executed[3] == (MARIADB_TIME_BOUND, (4.0,))


def test_a_server_that_knows_neither_bound_is_read_under_the_driver_s_timeout_alone() -> None:
    """Both variables refused as unknown still reads, because the driver's read timeout was set
    from the bound before the connection opened. Delete this and a server that is neither MySQL
    5.7.8 nor MariaDB 10.1 can never be read."""
    unknown = {MYSQL_TIME_BOUND: UNKNOWN_SYSTEM_VARIABLE, MARIADB_TIME_BOUND: 1193}
    driver = Recorded(rows=(a_row(),), refuse=unknown)
    reply = reader(driver).rows(read_plan(a_connection(), ENTITY_CLIENT))
    assert reply.fault is None and len(reply.rows) == 1
    assert driver.opened[0]["read_timeout"] == 5.0 + DRIVER_GRACE_SECONDS


def test_any_other_refusal_of_the_session_s_bound_is_the_read_s_fault_and_nothing_is_read() -> None:
    """Only the unknown variable is answered by trying the other; a lost connection while setting
    the bound is the database not answering, and no `SELECT` is sent. Delete this and a refusal of
    the bound is swallowed and the read sent without one."""
    for statement in (MYSQL_TIME_BOUND, MARIADB_TIME_BOUND):
        refuse = {MYSQL_TIME_BOUND: UNKNOWN_SYSTEM_VARIABLE, statement: 2013}
        driver = Recorded(rows=(a_row(),), refuse=refuse)
        reply = reader(driver).rows(read_plan(a_connection(), ENTITY_CLIENT))
        assert reply.fault is DatabaseFault.UNAVAILABLE
        assert not any(one.startswith("SELECT") for one, _ in driver.executed)


def test_every_read_opens_one_connection_and_closes_it_whatever_the_read_came_to() -> None:
    """One connection per read, closed in a `finally`: two reads open two and close two, and a
    read the server refused mid-statement closes its connection too. Delete this and a session of
    ours can sit open in the company's connection pool after every refused read."""
    driver = Recorded(rows=(a_row(),))
    one = reader(driver)
    one.rows(read_plan(a_connection(), ENTITY_CLIENT))
    one.rows(read_plan(a_connection(), ENTITY_USER))
    assert (len(driver.opened), driver.closed) == (2, 2)

    statement = statement_for(read_plan(a_connection(), ENTITY_CLIENT))
    refused = Recorded(refuse={statement.text: 1142})
    reply = reader(refused).rows(read_plan(a_connection(), ENTITY_CLIENT))
    assert reply.fault is DatabaseFault.ACCESS_DENIED
    assert (len(refused.opened), refused.closed) == (1, 1)


def test_the_login_reaches_the_driver_and_is_rendered_nowhere() -> None:
    """The user and the password are handed to the driver as the connection's own, and neither
    the reader, the login nor anything either renders shows the password. Delete this and a
    traceback holding the reader prints the company's database password."""
    driver = Recorded(rows=(a_row(),))
    login = a_login()
    one = reader(driver, login)
    one.rows(read_plan(a_connection(), ENTITY_CLIENT))
    assert (driver.opened[0]["user"], driver.opened[0]["password"]) == ("brain_reader", PASSWORD)
    assert driver.opened[0]["host"] == ADDRESS
    for shown in (repr(one), str(one), repr(login), str(login), f"{login.password}"):
        assert PASSWORD not in shown
    assert ADDRESS not in repr(one) and "brain_reader" not in repr(one)


# ------------------------------------------------------------------ what came back


def test_absent_refused_and_unreachable_come_back_as_three_answers() -> None:
    """A view with no rows is absent; the grant withdrawn, the view gone and the password changed
    are refused; a server that will not take the connection is unreachable; the executor passes
    MySQL's number to `fault_for_mysql_error` and decides none of it. Delete this and a dropped
    view reads as a company with no clients."""
    read = read_plan(a_connection(), ENTITY_CLIENT)
    statement = statement_for(read).text

    def outcome(driver: Recorded) -> LaravelOutcome:
        return interpret(
            read, reader(driver).rows(read), fetched_at="2019-03-01T10:00:00+00:00"
        ).outcome

    assert outcome(Recorded(rows=(a_row(),))) is LaravelOutcome.PRESENT
    assert outcome(Recorded(rows=())) is LaravelOutcome.ABSENT
    for number in (1142, 1146):
        assert outcome(Recorded(refuse={statement: number})) is LaravelOutcome.REFUSED
    assert outcome(Recorded(at_connect=1045)) is LaravelOutcome.REFUSED
    for number in (2003, 2013):
        assert outcome(Recorded(at_connect=number)) is LaravelOutcome.UNREACHABLE
    for number in (3024, 1969):
        assert outcome(Recorded(refuse={statement: number})) is LaravelOutcome.UNREACHABLE
    assert laravel.fault_for_mysql_error(1969) is DatabaseFault.TIMED_OUT


def test_a_value_comes_back_as_the_rest_of_the_product_reads_one() -> None:
    """A timestamp with no zone is read as UTC, which the session was put in; a date is its ISO
    form; money is its exact digits as text. Delete this and a stored `updated_at` is read as eight
    hours old in Singapore, or a contract value rounds on its way to a person."""
    driver = Recorded(
        rows=(a_row(updated_at=datetime(2019, 3, 1, 10, 0), contract_value=Decimal("0.10")),)
    )
    [row] = reader(driver).rows(read_plan(a_connection(), ENTITY_CLIENT)).rows
    assert row["updated_at"] == datetime(2019, 3, 1, 10, 0, tzinfo=UTC)
    assert row["contract_value"] == "0.10"
    assert executor._plain(date(2019, 3, 1)) == "2019-03-01"
    aware = datetime(2019, 3, 1, 10, 0, tzinfo=UTC)
    assert executor._plain(aware) is aware
    assert executor._plain(7) == 7


# ------------------------------------------------------------------ the encryption


def handshake(made: Issued, context: ssl.SSLContext, server_name: str) -> None:
    """One TLS handshake with a local server presenting `made`'s certificate, or its refusal."""
    served = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    with tempfile.TemporaryDirectory() as held:
        certificate, key = Path(held) / "server.pem", Path(held) / "server-key.pem"
        certificate.write_text(made.certificate, encoding="ascii")
        key.write_text(made.key, encoding="ascii")
        served.load_cert_chain(certificate, key)
    with socket.create_server(("127.0.0.1", 0)) as listener:
        port = listener.getsockname()[1]

        def answer() -> None:
            accepted, _ = listener.accept()
            try:
                with served.wrap_socket(accepted, server_side=True) as wrapped:
                    wrapped.recv(1)
            except (ssl.SSLError, OSError):
                pass

        thread = threading.Thread(target=answer, daemon=True)
        thread.start()
        try:
            with (
                socket.create_connection(("127.0.0.1", port), timeout=5) as raw,
                context.wrap_socket(raw, server_hostname=server_name),
            ):
                pass
        finally:
            thread.join(timeout=5)


def test_by_default_every_connection_is_encrypted_and_its_certificate_checked_by_name() -> None:
    """`A_LOGIN_CROSSES_ONLY_A_VERIFIED_CHANNEL`, against a real TLS handshake. The default context
    requires a certificate and checks the name, so a server whose certificate this server's
    authorities did not sign is refused; the same server with its own authority handed over is
    accepted under its name and refused under another. Delete this and a context that encrypts
    without checking anything hands the password to whoever answers on the path."""
    made = issued()
    verified = tls_context(VERIFIED)
    assert verified is not None
    assert (verified.verify_mode, verified.check_hostname) == (ssl.CERT_REQUIRED, True)
    with pytest.raises(ssl.SSLCertVerificationError):
        handshake(made, verified, "127.0.0.1")

    own = tls_context(DatabaseTls(TlsMode.OWN_AUTHORITY, ca_certificate_of(made.authority)))
    assert own is not None
    assert (own.verify_mode, own.check_hostname) == (ssl.CERT_REQUIRED, True)
    handshake(made, own, "127.0.0.1")
    with pytest.raises(ssl.SSLCertVerificationError):
        handshake(made, own, "db.example.invalid")


def test_the_driver_is_given_the_context_and_the_name_and_a_tunnel_s_connection_none() -> None:
    """The executor hands the driver the connection's own name to check the certificate against,
    beside the address it connects to, and a context that verifies; a tunnel's connection is handed
    no context at all. Delete this and the executor could open a verified context and never pass
    it, or check the certificate against the address."""
    driver = Recorded(rows=(a_row(),))
    reader(driver).rows(read_plan(a_connection(), ENTITY_CLIENT))
    [opened] = driver.opened
    assert (opened["host"], opened["server_name"]) == (ADDRESS, "db.example.invalid")
    assert isinstance(opened["tls"], ssl.SSLContext)
    assert opened["tls"].verify_mode is ssl.CERT_REQUIRED and opened["tls"].check_hostname

    tunnel = Recorded(rows=(a_row(),))
    reader(tunnel, tls=NO_ENCRYPTION).rows(read_plan(a_connection(), ENTITY_CLIENT))
    assert tunnel.opened[0]["tls"] is None


def test_the_real_driver_requires_the_context_and_connects_to_the_checked_address_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PyMySQL is told the name, the context as required, and to wait; the socket is opened to the
    checked address and handed over. A tunnel's connection switches TLS off rather than leaving it
    to PyMySQL's preference, which encrypts and checks nothing. A socket that cannot be opened is
    MySQL's own number for a server it cannot reach. Delete this and the driver can fall back to
    an unverified connection, or resolve the name a second time past the address rule."""
    told: list[dict[str, Any]] = []
    opened: list[tuple[str, int]] = []

    class Held:
        def connect(self, sock: object) -> None:
            assert sock == "socket"

    def connect(**kwargs: Any) -> Held:
        told.append(kwargs)
        return Held()

    def create_connection(address: tuple[str, int], timeout: float) -> str:
        opened.append(address)
        return "socket"

    monkeypatch.setattr(pymysql, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    context = ssl.create_default_context()
    for tls in (context, None):
        executor.pymysql_driver(
            host=ADDRESS,
            port=3306,
            server_name="db.example.invalid",
            tls=tls,
            user="brain_reader",
            password=PASSWORD,
            connect_timeout=5.0,
            read_timeout=6.0,
            write_timeout=6.0,
        )
    assert [
        (one["host"], one["ssl"], one["ssl_disabled"], one["defer_connect"]) for one in told
    ] == [
        ("db.example.invalid", context, False, True),
        ("db.example.invalid", None, True, True),
    ]
    assert opened == [(ADDRESS, 3306), (ADDRESS, 3306)]

    def unreachable(address: tuple[str, int], timeout: float) -> str:
        raise ConnectionRefusedError

    monkeypatch.setattr(socket, "create_connection", unreachable)
    with pytest.raises(pymysql.err.OperationalError) as raised:
        executor.pymysql_driver(
            host=ADDRESS,
            port=3306,
            server_name="db.example.invalid",
            tls=context,
            user="brain_reader",
            password=PASSWORD,
            connect_timeout=5.0,
            read_timeout=6.0,
            write_timeout=6.0,
        )
    assert laravel.fault_for_mysql_error(raised.value.args[0]) is DatabaseFault.UNAVAILABLE


def test_a_certificate_authority_is_read_on_one_line_or_many_and_anything_else_is_refused() -> None:
    """A text box turns a pasted certificate into one line, so the body is read whatever its line
    breaks and written back in the standard shape; a private key, text past the bound, text that
    is not only certificates and a block that does not parse are each refused. Delete this and a
    company's own authority cannot be pasted, or a private key is kept as configuration."""
    made = issued()
    one_line = made.authority.replace("\n", "")
    assert ca_certificate_of(one_line) == ca_certificate_of(made.authority) == made.authority
    refused = (
        made.key,
        made.authority + made.key,
        "not a certificate",
        made.authority + " and something else",
        "-----BEGIN CERTIFICATE-----AAAA-----END CERTIFICATE-----",
        made.authority * (laravel.MAX_CA_CERTIFICATE_CHARS // len(made.authority) + 1),
    )
    for text in refused:
        with pytest.raises(laravel.LaravelError):
            ca_certificate_of(text)


# ------------------------------------------------------------------ a real server


def real_login() -> tuple[str, int, DatabaseLogin, str]:
    """The address, port, login and schema `LARAVEL_TEST_MYSQL_URL` names."""
    parts = urlsplit(MYSQL_URL)
    user, password = unquote(parts.username or ""), unquote(parts.password or "")
    return (
        parts.hostname or "",
        parts.port or 3306,
        DatabaseLogin(user, SealedSecret(password)),
        parts.path.strip("/"),
    )


def real_authority() -> DatabaseTls:
    """The CI job's own certificate authority, which signed the server's certificate."""
    text = Path(os.environ.get("LARAVEL_TEST_MYSQL_CA", "")).read_text(encoding="ascii")
    return DatabaseTls(TlsMode.OWN_AUTHORITY, ca_certificate_of(text))


def real(
    entity: str,
    *,
    max_rows: int = 200,
    seconds: float = 5.0,
    schema: str = "",
    tls: DatabaseTls | None = None,
) -> ViewReply:
    host, port, login, named = real_login()
    connection = a_connection(schema=schema or named, max_rows=max_rows, seconds=seconds)
    return MySqlViewReader(
        address=host,
        port=port,
        login=login,
        server_name=host,
        tls=real_authority() if tls is None else tls,
    ).rows(read_plan(connection, entity))


@pytest.mark.needs_mysql
@needs_mysql
def test_on_a_real_server_a_view_is_read_capped_ordered_and_in_utc() -> None:
    """**The real read**, over TLS verified against the CI job's own authority. The view holds three
    clients; a read capped at two returns the first two by id, with a zoned timestamp and exact
    money. Delete this and the executor is proved only against a driver somebody recorded."""
    reply = real(ENTITY_CLIENT, max_rows=2)
    assert reply.fault is None
    assert [row["id"] for row in reply.rows] == [1, 2]
    assert all(row["updated_at"].tzinfo is not None for row in reply.rows)
    assert isinstance(reply.rows[0]["contract_value"], str)
    assert set(reply.rows[0]) == set(laravel.columns_for(ENTITY_CLIENT))


@pytest.mark.needs_mysql
@needs_mysql
def test_on_a_real_server_an_empty_view_is_absent_and_a_view_not_granted_is_refused() -> None:
    """The CI job's staff view is empty and a second schema's client view exists without a grant.
    Delete this and the three answers are kept apart only in front of a recorded driver."""
    absent = real(ENTITY_USER)
    assert absent.fault is None and absent.rows == ()
    refused = real(ENTITY_CLIENT, schema="ungranted")
    assert refused.fault is DatabaseFault.ACCESS_DENIED


@pytest.mark.needs_mysql
@needs_mysql
def test_on_a_real_server_a_closed_port_is_unreachable() -> None:
    """Nothing listens on port 1. Delete this and a server that is not there could read as
    absent."""
    _, _, login, schema = real_login()
    reply = MySqlViewReader(
        address="127.0.0.1", port=1, login=login, server_name="127.0.0.1", tls=real_authority()
    ).rows(read_plan(a_connection(schema=schema, seconds=2.0), ENTITY_CLIENT))
    assert reply.fault is DatabaseFault.UNAVAILABLE


@pytest.mark.needs_mysql
@needs_mysql
def test_on_a_real_server_a_read_past_its_bound_is_stopped_by_the_server_in_time() -> None:
    """The CI job's `slow` schema holds a client view that sleeps two seconds a row. A read bounded
    at one second is stopped by the server's own `max_execution_time`, as 3024, before the driver's
    grace runs out. Delete this and the session's bound is proved only by the statement being
    sent."""
    started = time.monotonic()
    reply = real(ENTITY_CLIENT, schema="slow", seconds=1.0)
    elapsed = time.monotonic() - started
    assert reply.fault is DatabaseFault.TIMED_OUT
    assert elapsed < 1.0 + DRIVER_GRACE_SECONDS + 1.0


@pytest.mark.needs_mysql
@needs_mysql
def test_on_a_real_server_the_session_the_executor_opens_is_read_only() -> None:
    """`READ_ONLY`, sent through the executor's own driver function, is in force on the server
    itself. Delete this and it could be a statement MySQL accepts and ignores."""
    host, port, login, _ = real_login()
    session = executor.pymysql_driver(
        host=host,
        port=port,
        server_name=host,
        tls=tls_context(real_authority()),
        user=login.user,
        password=login.password.reveal(),
        connect_timeout=5.0,
        read_timeout=5.0,
        write_timeout=5.0,
    )
    try:
        cursor = session.cursor()
        cursor.execute(READ_ONLY)
        cursor.execute("SELECT @@session.transaction_read_only AS read_only")
        # PyMySQL's dictionary cursor hands back a list, which its stubs call a tuple; the rows
        # are compared as a list so the assertion is about the value and not the container.
        assert list(cursor.fetchall()) == [{"read_only": 1}]
    finally:
        session.close()


@pytest.mark.needs_mysql
@needs_mysql
def test_on_a_real_server_a_certificate_no_trusted_authority_signed_is_never_sent_the_login() -> (
    None
):
    """The CI job's server presents a certificate its own authority signed, which none of this
    runner's authorities did, so the default connection refuses it before the login is sent, and
    the same server is read with that authority named. Delete this and verification is proved only
    against a local socket, never against MySQL's own handshake."""
    assert real(ENTITY_CLIENT, tls=VERIFIED).fault is DatabaseFault.UNAVAILABLE
    assert real(ENTITY_CLIENT).fault is None


@pytest.mark.needs_mysql
@needs_mysql
def test_on_a_real_server_a_tunnel_s_connection_reads_without_encryption() -> None:
    """The tunnel's case, which the form allows only with the private network setting on: TLS is
    switched off and the read is made. Delete this and the one case that may not encrypt could be
    one that cannot connect at all."""
    reply = real(ENTITY_CLIENT, tls=NO_ENCRYPTION)
    assert reply.fault is None and len(reply.rows) == 3
