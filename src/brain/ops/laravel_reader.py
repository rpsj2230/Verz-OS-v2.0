"""The one place this product runs a statement against a company's own MySQL: one bounded read.

`brain.connectors.laravel` decides everything about a read of a company's views: which view, which
columns, which rows, how many and for how long (`BoundedRead`), whether the address may be
reached (`checked_address`), and what an answer or an error number means (`interpret`,
`fault_for_mysql_error`). This module is the part none of that can hold without owning a client:
the driver, the session and the statement's text. It is the only module that imports the driver,
for CLAUDE.md's reason: nothing that decides policy owns a client, so the decisions are tested
without a socket and this is tested with a recorded driver and, in CI, against a real server.

**The statement is compiled from the read by SQLAlchemy's own MySQL compiler, and every value is
bound.** The view and the columns are identifiers from `DatabaseTransport`'s closed allowlist and
the connector's own column list, which a compiler quotes where MySQL needs it; the filter values
and the row cap are parameters the driver escapes. No string is composed into a statement here,
and `brain.knowledge.rows.assert_no_sql_is_built_by_interpolation` is run over this module by its
tests. See `A_STATEMENT_IS_COMPILED_AND_NEVER_COMPOSED`.

**The row cap is the statement's `LIMIT`, and the rows are ordered by id.** The cap in the
statement is what stops the server reading further, where a cap applied to the rows afterwards
would have read the whole view first. Ordering by the id makes two reads of the same view return
the same rows when there are more than the cap, so the index does not churn between runs.

**The time bound is set twice, and the driver's is the floor.** The session is told
`SET SESSION MAX_EXECUTION_TIME` in milliseconds (MySQL 5.7.8 and later), so the server stops a
read that passes the bound and says so with its own error 3024, which reads as the bound firing.
The driver is given the same bound to connect and one `DRIVER_GRACE_SECONDS` more to read and
write, so on MySQL the server's own refusal arrives first. MariaDB has no `max_execution_time`: it
refuses that `SET` as an unknown system variable (1193), and the executor then sets MariaDB's own
`max_statement_time` in seconds, whose refusal is its error 1969. A server that knows neither is
bounded by the driver's read timeout alone, which ends the read as a lost connection. Not
measured against MariaDB here: the CI job runs MySQL 8. See `THE_DRIVER_S_TIMEOUT_IS_THE_FLOOR`.

**The session is read-only, in UTC, and one per read.** `SET SESSION TRANSACTION READ ONLY` makes
the server refuse a write even from a user somebody granted one by mistake; the grant is the first
restriction and this is the second. The session's time zone is UTC, so a `TIMESTAMP` column comes
back as the instant it is, and a value with no zone is read as UTC, which is Laravel's default
application zone (a view holding local times converts them with `CONVERT_TZ` in its definition).
One connection is opened for one read and closed in a `finally`, whatever the read came to, so no
session of ours sits idle in the company's connection pool.

**TLS is required and the server's certificate verified, by name and chain.** The read-only user's
password crosses whatever network lies between (`laravel.A_LOGIN_CROSSES_ONLY_A_VERIFIED_CHANNEL`),
so `tls_context` builds the standard library's default client context, which requires a certificate
and checks the host name, over the authorities this server trusts or over the one certificate
authority the connection names, and the driver is given it as required rather than preferred: a
server that offers no TLS, or a certificate that does not verify, is a read that is not made. The
socket is opened to the address `laravel.checked_address` resolved, and the name the certificate
must carry is the host the connection names, so pinning the address does not cost the name check.
Only a connection on a private network may say none, which is the tunnel's case
(`laravel.NO_ENCRYPTION_IS_THE_TUNNEL_S_CASE`), and then TLS is switched off rather than left to the
driver's preference, which would encrypt without checking anything.

**What the driver is told beside the statement.** `autocommit`, so no transaction of ours stays
open, and `local_infile` off, so a server asking for a file from this machine is refused by the
driver.

Rejected: `mysqlclient`, which is faster and is a C extension that needs the MySQL client library
in the image; the reads here are bounded to a few thousand rows and speed is not what limits them.
And an `init_command` carrying the session statements, which runs them before the driver has said
whether the server knew them, so MariaDB's refusal could not be answered with its own variable.

Rejected, for TLS: the driver's preferred mode, which encrypts when the server offers it and
checks nothing, so whoever answers on the path is sent the password over an encrypted channel to
themselves.

Task ids: M11.6.1
"""

from __future__ import annotations

import contextlib
import socket
import ssl
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Final, Protocol, cast

import pymysql
from pymysql.cursors import DictCursor
from sqlalchemy import column, select, table
from sqlalchemy.dialects.mysql.pymysql import MySQLDialect_pymysql
from sqlalchemy.sql.compiler import SQLCompiler

from brain.connectors.declaration import DatabaseLogin
from brain.connectors.laravel import (
    ID_COLUMN,
    BoundedRead,
    DatabaseTls,
    TlsMode,
    ViewReply,
    fault_for_mysql_error,
)

# ------------------------------------------------------------------ written-down reasons
#: Why no statement here is a composed string.
A_STATEMENT_IS_COMPILED_AND_NEVER_COMPOSED: Final = (
    "The statement is compiled by SQLAlchemy's MySQL compiler from the view and columns the "
    "connector declared and the filters the gate decided, with every value and the row cap as a "
    "bound parameter. A value spliced into a statement is a value that can end the statement, and "
    "the view name reaching here came from a closed allowlist matched by string equality."
)

#: Why the driver's timeout is set as well as the session's.
THE_DRIVER_S_TIMEOUT_IS_THE_FLOOR: Final = (
    "The session's own bound is the one that stops the query on the server, and only MySQL knows "
    "max_execution_time; MariaDB has max_statement_time instead, and a server may know neither. "
    "The driver's read timeout is set from the same bound on every server, so a read ends from "
    "this side even when the server was never told to stop it."
)

# ------------------------------------------------------------------------ the figures
#: The session statements, sent before the read. Constants, with the one value bound.
READ_ONLY: Final = "SET SESSION TRANSACTION READ ONLY"
IN_UTC: Final = "SET SESSION time_zone = '+00:00'"
MYSQL_TIME_BOUND: Final = "SET SESSION MAX_EXECUTION_TIME = %s"
MARIADB_TIME_BOUND: Final = "SET SESSION max_statement_time = %s"

#: What a server answers a `SET` of a variable it does not have. MySQL's documented number.
UNKNOWN_SYSTEM_VARIABLE: Final = 1193

#: How much longer than the bound the driver waits for a read, so the server's own refusal, which
#: says the bound fired, arrives before the driver gives up and calls it a lost connection.
DRIVER_GRACE_SECONDS: Final = 1.0

#: The character set every read asks for: MySQL's full UTF-8, so a name is never mangled.
CHARSET: Final = "utf8mb4"

_DIALECT: Final = MySQLDialect_pymysql()


# ------------------------------------------------------------------------ the statement
@dataclass(frozen=True)
class Statement:
    """A compiled statement and its parameters in the driver's order. Never a composed string."""

    text: str
    parameters: tuple[object, ...]


def statement_for(read: BoundedRead) -> Statement:
    """The one `SELECT` a bounded read is, compiled for MySQL with every value bound.

    The columns are the read's own list, in its order; the filters are equalities on columns in
    that list, which `laravel.read_plan` has already checked; the rows are ordered by the id and
    capped by the read's limit, which `BoundedRead` refuses to be zero. See
    `A_STATEMENT_IS_COMPILED_AND_NEVER_COMPOSED`.
    """
    schema, _, name = read.plan.view.partition(".")
    view = table(name, *(column(one) for one in read.columns), schema=schema)
    query = select(*(view.c[one] for one in read.columns))
    for key, value in read.plan.filters:
        query = query.where(view.c[key] == value)
    query = query.order_by(view.c[ID_COLUMN]).limit(read.plan.limit)
    compiled = query.compile(dialect=_DIALECT)
    # The MySQL dialect's compiler is a positional `SQLCompiler`; the base type `compile` is
    # declared to return says nothing about parameter order, so the narrower type is asserted.
    assert isinstance(compiled, SQLCompiler)
    order = compiled.positiontup or []
    return Statement(text=str(compiled), parameters=tuple(compiled.params[one] for one in order))


# ------------------------------------------------------------------------ the driver
class Cursor(Protocol):
    """The two things a read asks of the driver's cursor."""

    def execute(self, query: str, args: object = None) -> int:
        """Run one statement with its parameters bound by the driver."""
        ...

    def fetchall(self) -> Sequence[Mapping[str, Any]]:
        """Every row the statement returned, by column name."""
        ...


class Session(Protocol):
    """One connection to the database, for one read."""

    def cursor(self) -> Cursor:
        """A cursor on this connection."""
        ...

    def close(self) -> None:
        """Close the connection. Called once, in a `finally`."""
        ...


class Driver(Protocol):
    """Opens one connection, or raises the driver's own error with MySQL's number in it.

    `host` is the address the socket is opened to, `server_name` the name the certificate must
    carry, and `tls` the context the connection must be encrypted under, or None for none.
    """

    def __call__(
        self,
        *,
        host: str,
        port: int,
        server_name: str,
        tls: ssl.SSLContext | None,
        user: str,
        password: str,
        connect_timeout: float,
        read_timeout: float,
        write_timeout: float,
    ) -> Session: ...


def tls_context(tls: DatabaseTls) -> ssl.SSLContext | None:
    """The context a connection is encrypted under, or None for a tunnel's connection.

    The standard library's default client context, unchanged: it requires a certificate and
    checks the host name, over the authorities this server trusts or, where the connection names
    its own, over that one alone. See `laravel.A_LOGIN_CROSSES_ONLY_A_VERIFIED_CHANNEL`.
    """
    if tls.mode is TlsMode.NONE:
        return None
    if tls.mode is TlsMode.OWN_AUTHORITY:
        return ssl.create_default_context(cadata=tls.ca_certificate)
    return ssl.create_default_context()


def pymysql_driver(
    *,
    host: str,
    port: int,
    server_name: str,
    tls: ssl.SSLContext | None,
    user: str,
    password: str,
    connect_timeout: float,
    read_timeout: float,
    write_timeout: float,
) -> Session:
    """PyMySQL, told everything the module docstring lists, over a socket to the checked address.

    The connection is made with the server's name and started over a socket this function opened
    to `host`, so the certificate is checked against the name while the bytes go to the address
    that passed the address rule. A context handed over is required: PyMySQL refuses a server that
    offers no TLS rather than falling back.
    """
    connection = pymysql.connect(
        host=server_name,
        port=port,
        user=user,
        password=password,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        write_timeout=write_timeout,
        autocommit=True,
        charset=CHARSET,
        cursorclass=DictCursor,
        local_infile=False,
        ssl=tls,
        ssl_disabled=tls is None,
        defer_connect=True,
    )
    try:
        opened = socket.create_connection((host, port), timeout=connect_timeout)
    except OSError as unreached:
        # The number MySQL's own client gives a server it cannot reach, so the fault table reads it.
        raise pymysql.err.OperationalError(2003, "the database did not answer") from unreached
    connection.connect(opened)
    # A cast at the library boundary: PyMySQL's connection over a `DictCursor` is this protocol,
    # and its stubs declare `execute` as two overloads a protocol cannot name as one.
    return cast(Session, connection)


def _errno(failed: pymysql.err.MySQLError) -> int:
    """MySQL's number for this error, or 0 when the driver gave none, which reads as unreachable."""
    number = failed.args[0] if failed.args else 0
    return number if isinstance(number, int) else 0


def _bound(cursor: Cursor, seconds: float) -> None:
    """Tell the session its time bound, in MySQL's words and then MariaDB's.

    See `THE_DRIVER_S_TIMEOUT_IS_THE_FLOOR`. Only the unknown variable is answered by trying the
    other; any other refusal is the read's fault like any statement's.
    """
    try:
        cursor.execute(MYSQL_TIME_BOUND, (int(seconds * 1000),))
    except pymysql.err.MySQLError as unknown:
        if _errno(unknown) != UNKNOWN_SYSTEM_VARIABLE:
            raise
        try:
            cursor.execute(MARIADB_TIME_BOUND, (seconds,))
        except pymysql.err.MySQLError as neither:
            if _errno(neither) != UNKNOWN_SYSTEM_VARIABLE:
                raise


def _plain(value: object) -> object:
    """A value as the rest of the product reads one: an instant with its zone, and text.

    A `DATETIME` or `TIMESTAMP` with no zone is read as UTC, which the session is set to; a `DATE`
    is its ISO form; a `DECIMAL` is its exact digits as text, because a float would round money.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


# ------------------------------------------------------------------------ the reader
class MySqlViewReader:
    """`brain.connectors.laravel.ViewReader` over one connection per read, as one leased login.

    Built for one read by `laravel.open_mysql` with the address `checked_address` resolved, and
    dropped when the read returns, so the login it holds lives as long as the read and no longer.
    Its representation names the port and nothing else: not the address, the user or the password.
    """

    def __init__(
        self,
        *,
        address: str,
        port: int,
        login: DatabaseLogin,
        server_name: str,
        tls: DatabaseTls,
        driver: Driver = pymysql_driver,
    ) -> None:
        self._address = address
        self._port = port
        self._login = login
        self._server_name = server_name
        self._tls = tls
        self._driver = driver

    def __repr__(self) -> str:
        return f"MySqlViewReader(port={self._port})"

    __str__ = __repr__

    def rows(self, read: BoundedRead) -> ViewReply:
        """One bounded read, as the rows it returned or the fault MySQL's number is."""
        statement = statement_for(read)
        seconds = read.timeout_seconds
        try:
            session = self._driver(
                host=self._address,
                port=self._port,
                server_name=self._server_name,
                tls=tls_context(self._tls),
                user=self._login.user,
                password=self._login.password.reveal(),
                connect_timeout=seconds,
                read_timeout=seconds + DRIVER_GRACE_SECONDS,
                write_timeout=seconds + DRIVER_GRACE_SECONDS,
            )
        except pymysql.err.MySQLError as failed:
            return ViewReply(fault=fault_for_mysql_error(_errno(failed)))
        try:
            cursor = session.cursor()
            cursor.execute(READ_ONLY)
            cursor.execute(IN_UTC)
            _bound(cursor, seconds)
            cursor.execute(statement.text, statement.parameters)
            fetched = cursor.fetchall()
        except pymysql.err.MySQLError as failed:
            return ViewReply(fault=fault_for_mysql_error(_errno(failed)))
        finally:
            # A connection the server already dropped closes without a word; one closed twice is
            # the driver's complaint, and the read's answer is what this returns either way.
            with contextlib.suppress(pymysql.err.MySQLError):
                session.close()
        return ViewReply(
            rows=tuple({name: _plain(value) for name, value in row.items()} for row in fetched)
        )
