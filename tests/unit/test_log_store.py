"""The application log's table, written by the real store and read through the real screen.

**M27.8.14 end to end** is the second test: the application started over a database with the
migration applied, a route that logs a secret, a token, a credential, a question and a record's
field value every way a call site could, the rows those calls left read back as the superuser and
through `GET /api/v1/logs` as an administrator, and none of the five anywhere in either. The rest
hold the table's own promises: the migration builds the model, the ceiling keeps the newest rows, a
storm is bounded in rows, the retention sweep removes what is past the trace window, and the
database refuses an edit and an oversized row from the application role.

Every test here but the last two **skips without a server**, as every scratch-database test does.

Task ids: M27.8.14
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any

import psycopg
import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Grant
from brain.core.errors import Failed
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.log_routes import LOG_AUTHORITY
from brain.ops.log_capture import LogCapture, install
from brain.ops.log_store import LogStore, secrets_of, start_log_store, stop_log_store
from brain.ops.retention import TRACE_RETENTION_DAYS, Store
from brain.ops.retention_store import PostgresSweeper
from brain.session import make_app_engine, make_application_sessions
from tests.fixtures.console_http import Store as GrantStore
from tests.fixtures.console_http import headers
from tests.fixtures.scratch_postgres import (
    ROOT,
    database_url,
    drop,
    fresh,
    migrate,
    modelled,
    pointed_at,
    run,
    secured,
    shape,
    sql,
)
from tests.unit.test_agent_routes import Directory
from tests.unit.test_api_routes import AUDIENCE, ISSUER, Keys, NoCache, Versions, verifier

MIGRATION = ROOT / "migrations" / "versions" / "0063_application_log.py"
TABLE = "obs.application_log"

#: The five things that must never reach the table, each as a call site would have it.
#: A secret this process was configured with, shaped like vocabulary so only that check stops it.
SECRET = "velvet-orbit-lantern-quiet"
#: A bearer token and an API key, the second lowercase so only the token-shape check stops it.
TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1X2FkbWluIn0.c2lnbmF0dXJlLWJ5dGVz"
API_KEY = "sk-live-4f9a8b7c6d5e4f3a2b1c0d9e8f7a"
#: A credential value, as a person would type one.
CREDENTIAL = "Hunter2!Pa55word"
#: A question, in the case it was asked and in lower case, which no grammar refuses as an event.
QUESTION = "What is the contract value for SNM Construction?"
LOWER_QUESTION = "what is the contract value for snm construction"
#: A record's field value, formatted and bare.
FIELD_VALUE = "SGD 125,000.00"
BARE_FIELD_VALUE = "125000"

#: Fragments that would betray any of the five, whatever was done to them on the way.
NEVER = (
    SECRET,
    "eyJhbGci",
    "sk-live",
    "Hunter2",
    "Pa55word",
    "contract value",
    "SNM",
    "snm construction",
    "125,000",
    BARE_FIELD_VALUE,
)

GRANTS = {
    "u_admin": (
        Grant(capability=LOG_AUTHORITY, scope=Scope.unrestricted()),
        Grant(capability=plane_capability(Plane.CONFIGURATION), scope=Scope.unrestricted()),
    ),
}

log = structlog.get_logger()


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0063", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def through_0063(database: str) -> Iterator[str]:
    """A database with `0063` run for real on top of the revision it is chained to, and nothing
    else, because the table depends on nothing an earlier migration builds."""
    url = fresh(database)
    try:
        migrate(database, "stamp", migration().down_revision)
        migrate(database, "upgrade", migration().revision)
        yield url
    finally:
        drop(database)


def rows_text(url: str) -> str:
    """Every row of the table, every column, as the superuser reads it."""
    return "\n".join(
        str(one[0]) for one in sql(url, "SELECT row_to_json(l)::text FROM obs.application_log AS l")
    )


def as_app(url: str, statement: str, *params: object) -> None:
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute(statement, params or None)


@contextmanager
def storing(url: str, capture: LogCapture, **options: Any) -> Iterator[LogStore]:
    """A store over this database as the application role, with `capture` installed."""
    engine = make_app_engine(url)
    uninstall = install(capture)
    try:
        yield LogStore(make_application_sessions(engine), capture, **options)
    finally:
        uninstall()
        run(engine.dispose)


def storm(method: str, lines: int) -> None:
    """`lines` calls of `log.<method>`, each on a line of its own."""
    source = "\n".join(f"log.{method}('storm')" for _ in range(lines))
    exec(compile(source, "<storm>", "exec"), {"__name__": "storm", "log": log})  # noqa: S102


# ------------------------------------------------------------------------ the table
def test_the_migration_builds_the_table_the_model_declares_with_row_security_on() -> None:
    """Delete this and the migration and the model can disagree about a column, a width or a
    check, and the table the writer is tested against is not the one an install has."""
    with through_0063("brain_log_store_shape") as url:
        built = shape(url, (TABLE,))
        on = secured(url, (TABLE,))
    with modelled("brain_log_store_modelled", (TABLE,)) as from_models:
        declared = shape(from_models, (TABLE,))

    assert built == declared
    assert on == {TABLE: True}
    assert migration().TABLES == (TABLE,)


# ------------------------------------------------------------------------ the claim
def test_an_administrator_reads_the_warnings_and_nothing_sensitive_is_in_them() -> None:
    """**M27.8.14.** The application is started over the database, so the lifespan is what installs
    the capture and starts the store. A route logs the five sensitive things every way a call site
    could: under a key nobody allowed, under vocabulary keys shaped to pass, as the event name
    itself, inside an exception's message, and in a refusal's detail that `brain.app` logs. The
    rows are written by the store, read as the superuser and through the Logs screen as an
    administrator holding the log under a second factor.

    What the administrator reads: the warning by its name with its vocabulary, the error by its
    exception type, the refusal the application logged with the reference the caller was given,
    and the event whose name was a question, by its place. What is in neither the table nor the
    answer: any of the five.

    Delete this and each half can pass its own test while a value reaches the screen between
    them."""
    database = "brain_log_store_claim"
    with through_0063(database) as url:
        options = {"loop_factory": asyncio.SelectorEventLoop} if os.name == "nt" else None
        server = database_url()
        assert server is not None
        address = pointed_at(server, database)
        app: FastAPI = create_app(
            Settings(
                env="development", database_url=address, run_migrations=False, vault_token=SECRET
            )
        )

        @app.get("/_leaky")
        async def leaky() -> dict[str, str]:
            log.warning(
                "leaky.warning",
                reason="not_permitted",
                attempts=2,
                question=QUESTION,
                credential=CREDENTIAL,
                value=FIELD_VALUE,
                outcome=API_KEY,
                tool=TOKEN,
                status=SECRET,
                seconds=BARE_FIELD_VALUE,
            )
            log.warning(LOWER_QUESTION, reason=LOWER_QUESTION)
            try:
                raise ValueError(f"{CREDENTIAL} {TOKEN} {FIELD_VALUE} {QUESTION}")
            except ValueError:
                log.exception("leaky.exception", error=f"refused {CREDENTIAL}")
            raise Failed(f"the key {API_KEY} for {QUESTION} was refused")

        with TestClient(app, raise_server_exceptions=False, backend_options=options) as client:
            app.state.gate = GateWiring(
                authority=TokenAuthority(
                    issuer=ISSUER,
                    audience=AUDIENCE,
                    keys=Keys(),
                    verify=verifier,
                    directory=Directory(),
                ),
                versions=Versions(),
                store=GrantStore(GRANTS),
                cache=NoCache(),
            )
            refused = client.get("/_leaky")
            reference = refused.headers["x-trace-id"]
            # On the application's own loop, which is the loop the store's sessions belong to.
            assert client.portal is not None
            written = client.portal.call(app.state.log_store.store.flush)
            read = client.get(f"{API_PREFIX}/logs?limit=200", headers=headers("u_admin"))
            stored = rows_text(url)

        installed = [
            one for one in structlog.get_config()["processors"] if isinstance(one, LogCapture)
        ]

    assert refused.status_code == 500
    assert written >= 4
    assert read.status_code == 200, read.text
    entries = {(one["level"], one["event"]): one for one in read.json()["items"]}

    warning = entries[("warning", "leaky.warning")]
    assert warning["fields"]["reason"] == "not_permitted"
    assert warning["fields"]["attempts"] == "2"
    assert warning["reference"] == reference
    exception = entries[("error", "leaky.exception")]
    assert exception["error_type"] == "ValueError"
    assert exception["reference"] == reference
    failed = entries[("warning", "request failed")]
    assert failed["fields"]["outcome"] == "failed"
    assert failed["origin"].startswith("brain.app:")
    assert failed["reference"] == reference
    unnamed = entries[("warning", None)]
    assert unnamed["origin"].startswith(f"{__name__}:")

    for fragment in NEVER:
        assert fragment not in stored, fragment
        assert fragment not in read.text, fragment
    # The lifespan took the capture out again at shutdown.
    assert installed == []


# ------------------------------------------------------------------------ the bounds
def test_the_ceiling_keeps_the_newest_rows_and_removes_the_rest() -> None:
    """Thirty rows written against a ceiling of ten leave the ten newest.

    Delete this and the ceiling can remove the newest rows, or none, and a storm fills the table
    whatever the retention window says."""
    clock = [datetime(2019, 3, 6, 9, 0, tzinfo=UTC)]
    capture = LogCapture(clock=lambda: clock[0])
    with (
        through_0063("brain_log_store_ceiling") as url,
        storing(url, capture, ceiling=10, trim_every=1) as store,
    ):
        for _ in range(3):
            storm("warning", 10)
            run(store.flush)
            clock[0] += timedelta(minutes=1)
        kept = sql(url, "SELECT at FROM obs.application_log ORDER BY at, id")

    assert len(kept) == 10
    assert {one[0] for one in kept} == {datetime(2019, 3, 6, 9, 2, tzinfo=UTC)}


def test_a_storm_writes_no_more_rows_a_minute_than_the_bound_and_says_how_many_it_did_not() -> None:
    """Five minutes of two thousand warnings from distinct places, and a hundred thousand of one.

    Delete this and the bound can hold in memory while the writer writes around it."""
    clock = [datetime(2019, 3, 6, 9, 0, tzinfo=UTC)]
    capture = LogCapture(clock=lambda: clock[0])
    with through_0063("brain_log_store_storm") as url, storing(url, capture) as store:
        for _ in range(5):
            storm("warning", 2000)
            run(store.flush)
            clock[0] += timedelta(minutes=1)
        for _ in range(100_000):
            log.error("store.repeated")
        run(store.flush)
        counts = sql(
            url, "SELECT event, count(*), sum(repeats) FROM obs.application_log GROUP BY event"
        )

    by_event = {event: (rows, repeats) for event, rows, repeats in counts}
    assert by_event[None][0] == 5 * 60
    assert by_event["log_store.not_kept"][0] == 5
    assert by_event["store.repeated"] == (1, 100_000)


def test_the_retention_sweep_removes_log_rows_past_the_trace_window() -> None:
    """Through the sweep's own executor and its shipped attribution, as the scheduled run makes it.

    Delete this and `obs.application_log` could lose its attribution, which refuses every store in
    `obs`, or its clock, and the log is kept for ever."""
    now = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
    old = now - timedelta(days=TRACE_RETENTION_DAYS + 1)
    young = now - timedelta(days=1)
    with through_0063("brain_log_store_sweep") as url:
        for at in (old, young):
            as_app(
                url,
                "INSERT INTO obs.application_log (at, last_at, level, repeats) "
                "VALUES (%s, %s, 'warning', 1)",
                at,
                at,
            )
        with psycopg.connect(url) as conn:
            sweeper = PostgresSweeper(conn)
            due = sweeper.census(Store.TRACE, now).beyond_horizon
            removed = sweeper.expire(Store.TRACE, now)
            conn.commit()
        left = sql(url, "SELECT at FROM obs.application_log")

    assert (due, removed) == (1, 1)
    assert left == [(young,)]


def test_the_database_refuses_an_edit_an_unknown_level_and_an_oversized_row() -> None:
    """Measured as the application role. The positive insert first, so each refusal is the
    database's and not a statement that could never have worked.

    Delete this and the grant or the checks are claims about a table nobody has written to."""
    at = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)
    insert = (
        "INSERT INTO obs.application_log (at, last_at, level, repeats, fields) "
        "VALUES (%s, %s, %s, 1, %s)"
    )
    with through_0063("brain_log_store_refusals") as url:
        as_app(url, insert, at, at, "warning", '{"reason": "ok"}')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            as_app(url, "UPDATE obs.application_log SET repeats = 2")
        with pytest.raises(psycopg.errors.CheckViolation):
            as_app(url, insert, at, at, "debug", "{}")
        with pytest.raises(psycopg.errors.CheckViolation):
            as_app(url, insert, at, at, "warning", '{"reason": "' + "x" * 5000 + '"}')
        as_app(url, "DELETE FROM obs.application_log")
        left = sql(url, "SELECT count(*) FROM obs.application_log")

    assert left == [(0,)]


# ------------------------------------------------------------------------ without a server
def test_a_process_with_no_database_or_a_capture_already_installed_starts_nothing() -> None:
    """Delete this and a process with no sessions starts a writer with nowhere to write, or a
    second lifespan in one process writes every row twice."""
    settings = Settings(env="development")
    assert start_log_store(None, settings) is None
    uninstall = install(LogCapture())
    try:
        assert start_log_store(object(), settings) is None  # type: ignore[arg-type]
    finally:
        uninstall()
    run(lambda: stop_log_store(None))


def test_the_secrets_a_process_refuses_are_the_ones_it_was_configured_with() -> None:
    """The vault token, the trace store's key and every password inside a connection address.

    Delete this and a secret the process holds, filed under a vocabulary key by a call site,
    reaches the table because nobody told the capture about it."""
    settings = Settings(
        env="development",
        vault_token="vault-token-value",
        langfuse_secret_key="trace-store-key",
        database_url="postgresql://brain:database-password@db:5432/brain",
        valkey_url="redis://:cache-password@cache:6379/0",
    )

    found = set(secrets_of(settings))

    assert {
        "vault-token-value",
        "trace-store-key",
        "database-password",
        "cache-password",
    } <= found
    assert "" not in found
