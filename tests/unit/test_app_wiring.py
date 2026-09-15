"""The lifespan builds the gate and the automation route's wiring, and says when it could not.

Three halves. The first runs the lifespan through `TestClient`, as `tests/unit/test_app.py` does,
with a database address nothing answers on and a realm served over a mock transport: what is
built, what readiness says when it is not, and what shutdown closes. The second is the cache an
install with no Valkey gets. The third needs a server and skips without one: the application role
every transaction takes, and a token signed by a test key getting through a gate the lifespan
built, on a database built through `0002` and `0003`.

The end-to-end test drives the lifespan and the routes through `httpx.ASGITransport` on the event
loop `scratch_postgres.run` makes, rather than through `TestClient`. On Windows the test client's
loop is the proactor loop, which psycopg's async driver refuses, so a `TestClient` against a real
database would test the refusal and not the gate.

Task ids: M31.1.1.2, M1.1.2, M0.3.3
"""

from __future__ import annotations

import asyncio
import importlib.util
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import (
    AN_IDENTITY_PROVIDER_NOT_YET_ANSWERING_IS_ASKED_AGAIN,
    AN_INSTALL_THAT_CANNOT_CHECK_A_SIGN_IN_IS_UNREADY_RATHER_THAN_STOPPED,
    CACHE_CHECK,
    ROW_SECURITY_CHECK,
    SIGN_IN_CHECK,
    SIGN_IN_IS_REPORTED_AND_DOES_NOT_GATE_READINESS,
    Settings,
    create_app,
)
from brain.automation_routes import AutomationWiring
from brain.cache import (
    AN_ABSENT_CACHE_IS_A_MISS_AND_NEVER_AN_ANSWER,
    NoEntitlementCache,
    PostgresVersionSource,
    ValkeyEntitlementCache,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.db import normalise_database_url
from brain.gate.entitlement_store import StoredEntitlements
from brain.gate.resolve import ResolutionFailedError, resolve
from brain.identity.keycloak_tokens import jwks_url_for, verify_rs256
from brain.identity.oidc import SIGN_IN_PROMPT
from brain.identity.principal_directory import StoredDirectory
from brain.identity.principal_store import StoredPrincipals
from brain.identity.sign_in_binding import Binding, SignInBindings, sign_in_bindings
from brain.ops.automation_owner_store import StoredAutomations
from brain.ops.replica_store import console_reads_for
from brain.session import (
    APPLICATION_ROLE,
    SET_APPLICATION_ROLE,
    THE_APPLICATION_ANSWERS_AS_THE_ROLE_ROW_SECURITY_BINDS,
    ApplicationRoleSession,
    check_row_security,
    make_app_engine,
    make_application_sessions,
    make_session_factory,
)
from brain.sign_in_routes import FINISH_PATH, SIGN_INS_PATH
from tests.fixtures.scratch_postgres import drop, fresh, run
from tests.unit.test_entitlement_store import a_grant, a_principal, resolver
from tests.unit.test_keycloak_tokens import ISSUER, Idp, token

ROOT = Path(__file__).resolve().parents[2]

#: An address nothing listens on, so the pool is built and every statement fails at once.
UNANSWERED = "postgresql://u:p@127.0.0.1:1/d"

#: A cache address the tests never dial: `make_async_client` is replaced before it would.
CACHE_URL = "redis://cache.invalid:6379/0"


# ------------------------------------------------------------------ the pieces a test hands in


class Realm:
    """A realm's certs endpoint over a mock transport, which can be down and come back.

    Every client the lifespan asks for is kept, so a test can see whether shutdown closed it, and
    every fetch records whether it ran on a thread with an event loop running, which is the loop.
    """

    def __init__(self) -> None:
        self.idp = Idp()
        self.answering = True
        self.clients: list[httpx.Client] = []
        self.fetched_on_the_loop: list[bool] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        try:
            asyncio.get_running_loop()
            on_loop = True
        except RuntimeError:
            on_loop = False
        self.fetched_on_the_loop.append(on_loop)
        if not self.answering:
            msg = "the realm is still importing"
            raise httpx.ConnectError(msg, request=request)
        return httpx.Response(200, content=self.idp.get(str(request.url)))

    def client(self) -> httpx.Client:
        made = httpx.Client(transport=httpx.MockTransport(self.handle))
        self.clients.append(made)
        return made


class Valkey:
    """The three commands and closing, with a ping that can fail as a wrong address does."""

    def __init__(self, *, answers: bool = True) -> None:
        self.answers = answers
        self.closed = False

    async def get(self, name: str) -> bytes | None:
        del name
        return None

    async def setex(self, name: str, time: int, value: bytes) -> object:
        del name, time, value
        return True

    async def ping(self) -> object:
        if not self.answers:
            msg = "no cache at that address"
            raise ConnectionRefusedError(msg)
        return True

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def realm(monkeypatch: pytest.MonkeyPatch) -> Iterator[Realm]:
    """The realm, handed to the lifespan through `key_set_client`, with the issuer set."""
    served = Realm()
    monkeypatch.setenv("INSTALL_OIDC_ISSUER", ISSUER)
    monkeypatch.setattr("brain.app.key_set_client", served.client)
    monkeypatch.setattr("brain.app.run_migrations", lambda _url: [])
    yield served


def wired_app(*, valkey_url: str = "") -> FastAPI:
    """A development process over an unanswered database, with the cache named explicitly so a
    `VALKEY_URL` in the environment running the test cannot add one."""
    return create_app(Settings(env="development", database_url=UNANSWERED, valkey_url=valkey_url))


# ------------------------------------------------------------------ what the lifespan builds


def test_with_a_database_and_an_issuer_the_lifespan_builds_both_wirings_over_its_own_sessions(
    realm: Realm,
) -> None:
    """The positive case for every refusal below, and the construction every earlier commit left
    undone. Delete this and a lifespan that builds nothing passes the missing-issuer test, and the
    deployed process refuses every sign-in and every automation call exactly as it did before.

    Held by type and by identity: each store is the real one, over the very sessions the
    application serves through, the verifier is the RS256 one, and the realm's key set was read
    once from the certs endpoint of the configured issuer, through the client the lifespan owns."""
    app = wired_app()
    with TestClient(app) as c:
        gate, automation = app.state.gate, app.state.automation
        bindings = app.state.sign_in_bindings
        sessions = app.state.db_sessions
        body = c.get("/health/ready").json()
        checks, reported = body["checks"], body["reported"]

    assert isinstance(bindings, SignInBindings)
    assert bindings.sessions is sessions
    assert bindings.issuer == ISSUER
    assert isinstance(gate, GateWiring)
    assert isinstance(automation, AutomationWiring)
    assert gate.authority.issuer == ISSUER
    assert gate.authority.verify is verify_rs256
    assert isinstance(gate.authority.directory, StoredDirectory)
    assert gate.authority.directory.sessions is sessions
    assert isinstance(gate.versions, PostgresVersionSource)
    assert isinstance(gate.store, StoredEntitlements)
    assert gate.store.sessions is sessions
    assert isinstance(gate.cache, NoEntitlementCache)
    assert isinstance(automation.registrations, StoredAutomations)
    assert automation.registrations.sessions is sessions
    assert isinstance(automation.principals, StoredPrincipals)
    assert automation.principals.sessions is sessions
    assert sessions.kw["sync_session_class"] is ApplicationRoleSession
    assert realm.idp.urls == [jwks_url_for(ISSUER)]
    assert reported[SIGN_IN_CHECK] is True
    assert SIGN_IN_CHECK not in checks
    assert CACHE_CHECK not in checks


def test_the_realms_keys_are_fetched_off_the_event_loop_at_startup(realm: Realm) -> None:
    """See `bearer.A_KEY_FETCH_NEVER_HOLDS_THE_EVENT_LOOP`. Delete this and the startup fetch can
    be called directly in the lifespan coroutine, which blocks the loop for up to the fetch's
    timeout on a realm that is slow to answer, liveness included."""
    with TestClient(wired_app()):
        pass

    assert realm.fetched_on_the_loop == [False]


def test_without_a_database_there_is_no_wiring_and_readiness_says_the_database_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every store in both wirings reads the database, so there is nothing to build without one,
    and the reason readiness gives is the database's rather than sign-in's. Delete this and a
    wiring over a None session factory can be built and fail on the first request instead, or the
    missing database can be reported as a sign-in fault that sends somebody to the realm."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BRAIN_DATABASE_URL", raising=False)
    monkeypatch.setenv("INSTALL_OIDC_ISSUER", ISSUER)
    app = create_app(Settings(env="staging", database_url=""))
    with TestClient(app) as c:
        response = c.get("/health/ready")
        gate, automation = app.state.gate, app.state.automation

    assert (gate, automation) == (None, None)
    assert response.status_code == 503
    assert response.json()["checks"] == {"database_configured": False, "tools": True}
    assert response.json()["reported"] == {}


@pytest.mark.parametrize(
    "issuer",
    [pytest.param(None, id="unset"), pytest.param(f"{ISSUER}/", id="keys_never_matching")],
)
def test_an_install_that_cannot_check_a_sign_in_refuses_it_and_stays_ready_for_everything_else(
    monkeypatch: pytest.MonkeyPatch, realm: Realm, issuer: str | None
) -> None:
    """The decisions `AN_INSTALL_THAT_CANNOT_CHECK_A_SIGN_IN_IS_UNREADY_RATHER_THAN_STOPPED` and
    `SIGN_IN_IS_REPORTED_AND_DOES_NOT_GATE_READINESS`: no gate, no automation wiring and no
    bindings writer, so every sign-in is refused, while /health/ready stays 200 and names sign_in
    as not ready under reported, and never under checks. Both ways an issuer can be unusable,
    because `keycloak_authority` raises a different exception for each. Delete this and sign_in can
    move back into the checks that decide readiness, which on an install with no issuer, the state
    of a deployed container measured on 2026-09-15, fails the next deploy and takes every page that
    needs no sign-in down with it; or the gate can be built with no issuer, which fails open."""
    if issuer is None:
        monkeypatch.delenv("INSTALL_OIDC_ISSUER", raising=False)
    else:
        monkeypatch.setenv("INSTALL_OIDC_ISSUER", issuer)
    app = wired_app()
    monkeypatch.setattr("brain.app.check_row_security", _always_bound)
    with TestClient(app) as c:
        ready = c.get("/health/ready")
        live = c.get("/health/live")
        refused = c.get(f"{API_PREFIX}/me", headers=signed_for("s-anyone"))
        gate, automation = app.state.gate, app.state.automation
        bindings = app.state.sign_in_bindings

    assert (gate, automation, bindings) == (None, None, None)
    assert ready.json()["reported"] == {SIGN_IN_CHECK: False}
    assert SIGN_IN_CHECK not in ready.json()["checks"]
    assert refused.status_code == 401
    assert live.status_code == 200
    assert realm.idp.urls == []
    assert "restart loop" in AN_INSTALL_THAT_CANNOT_CHECK_A_SIGN_IN_IS_UNREADY_RATHER_THAN_STOPPED
    assert "watch-and-deploy" in SIGN_IN_IS_REPORTED_AND_DOES_NOT_GATE_READINESS


async def _always_bound(sessions: object) -> bool:
    """The row security check as a reachable database answers it. The unanswered address this
    file's lifespan tests use fails every blocking check, which would hide whether sign_in alone
    decides the status."""
    del sessions
    return True


def test_a_reported_component_decides_nothing_while_a_blocking_one_still_does(
    monkeypatch: pytest.MonkeyPatch, realm: Realm
) -> None:
    """The positive and the negative of the split, on one process. With every blocking check true
    and sign_in reported not ready, readiness is 200; with row_security false beside it, 503.
    Delete this and `ready` can start counting reported components, or stop counting blocking
    ones, and the missing-issuer test above alone would not say which."""
    monkeypatch.delenv("INSTALL_OIDC_ISSUER", raising=False)
    monkeypatch.setattr("brain.app.check_row_security", _always_bound)
    app = create_app(Settings(env="development", database_url="", valkey_url=""))
    with TestClient(app) as c:
        app.state.ready = {ROW_SECURITY_CHECK: True}
        app.state.reported = {SIGN_IN_CHECK: False}
        served = c.get("/health/ready")
        app.state.ready = {ROW_SECURITY_CHECK: False}
        refused = c.get("/health/ready")

    assert (served.status_code, served.json()["status"]) == (200, "ok")
    assert served.json()["reported"] == {SIGN_IN_CHECK: False}
    assert (refused.status_code, refused.json()["status"]) == (503, "degraded")
    del realm


def test_a_realm_not_answering_at_startup_is_reported_not_ready_until_it_answers(
    monkeypatch: pytest.MonkeyPatch, realm: Realm
) -> None:
    """The decision `AN_IDENTITY_PROVIDER_NOT_YET_ANSWERING_IS_ASKED_AGAIN`: the wiring is built,
    sign_in is reported not ready, and it is reported ready once the realm answers, with nobody
    restarting anything and readiness never going to 503 for it. Delete this and the retry can be
    dropped, which leaves a process that booted a few seconds before Keycloak reporting sign-in
    down for ever, or sign_in can be reported ready before any key set was ever read."""
    monkeypatch.setattr("brain.app.KEY_PRIMING_FIRST_RETRY_SECONDS", 0.02)
    monkeypatch.setattr("brain.app.check_row_security", _always_bound)
    realm.answering = False
    app = wired_app()
    with TestClient(app) as c:
        first = c.get("/health/ready")
        before = first.json()["reported"][SIGN_IN_CHECK]
        built = isinstance(app.state.gate, GateWiring)
        realm.answering = True
        deadline = time.monotonic() + 10
        after = False
        while time.monotonic() < deadline and not after:
            after = c.get("/health/ready").json()["reported"][SIGN_IN_CHECK]
            time.sleep(0.02)

    assert (before, built, after) == (False, True, True)
    assert SIGN_IN_CHECK not in first.json()["checks"]
    assert "asks again" in AN_IDENTITY_PROVIDER_NOT_YET_ANSWERING_IS_ASKED_AGAIN


def test_shutdown_closes_the_key_set_client_and_the_cache_client_and_not_before(
    monkeypatch: pytest.MonkeyPatch, realm: Realm
) -> None:
    """Both clients are the lifespan's, so both are closed by it, after the last request. Delete
    this and either close can go, leaving a socket per replaced container, or move ahead of
    `yield`, so the process serves over a closed client. A configured cache is also a readiness
    check here, answered by the client the gate reads."""
    cache = Valkey()
    monkeypatch.setattr("brain.app.make_async_client", lambda _url: cache)
    app = wired_app(valkey_url=CACHE_URL)
    with TestClient(app) as c:
        checks = c.get("/health/ready").json()["checks"]
        open_while_serving = (realm.clients[0].is_closed, cache.closed)
        reads_through = app.state.gate.cache

    assert len(realm.clients) == 1
    assert open_while_serving == (False, False)
    assert (realm.clients[0].is_closed, cache.closed) == (True, True)
    assert checks[CACHE_CHECK] is True
    assert isinstance(reads_through, ValkeyEntitlementCache)


def test_a_configured_cache_that_does_not_answer_fails_readiness(
    monkeypatch: pytest.MonkeyPatch, realm: Realm
) -> None:
    """See `brain.cache` on the trade-off, decided by the lifespan: a cache the compose file
    waited for and that still does not answer is a wrong address, which fails the deploy gate
    rather than serving slower for ever. Delete this and the check can be dropped, and a mistyped
    cache password is found by nobody, since every request still resolves."""
    monkeypatch.setattr("brain.app.make_async_client", lambda _url: Valkey(answers=False))
    app = wired_app(valkey_url=CACHE_URL)
    with TestClient(app) as c:
        response = c.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"][CACHE_CHECK] is False
    del realm


def test_both_sign_in_routes_are_served_by_the_application_and_answer_as_routes(
    realm: Realm,
) -> None:
    """`brain.sign_in_routes` is mounted by `create_app`, not only by its own tests. Held by what
    each path answers, because this FastAPI wraps an included router and does not list its paths
    at the top of `app.routes`: an unmounted path is the framework's 404 `{"detail": "Not Found"}`,
    and both of these refuse a request carrying no token as 401 with the one sign-in sentence in
    `ErrorBody`, which only a mounted route that checks a token can. Delete this and the router
    can be dropped from `create_app` with every test in `test_sign_in_routes.py` green, since that
    file mounts it itself, and no administrator can bind anybody on a deployed process."""
    app = wired_app()
    with TestClient(app) as c:
        bound = c.post(SIGN_INS_PATH, json={"subject": "s-anyone", "principal_id": "u_anyone"})
        finished = c.post(FINISH_PATH, json={"setup_code": "not-a-code", "principal_id": "u_a"})
        nowhere = c.post(f"{FINISH_PATH}-not-mounted", json={})

    for answered in (bound, finished):
        assert answered.status_code == 401
        assert answered.json()["message"] == SIGN_IN_PROMPT
        assert set(answered.json()) == {"message", "trace_id"}
    assert nowhere.status_code == 404
    assert "message" not in nowhere.json()
    del realm


def test_row_security_is_unready_when_no_transaction_can_be_run() -> None:
    """A transaction that could not run is not evidence the role is right. Delete this and the
    check can answer True on an exception, and a process whose `brain_app` is missing reports its
    requests as bound by row-level security while every one of them fails."""
    engine = make_app_engine("postgresql://nobody@127.0.0.1:1/none")

    async def go() -> bool:
        try:
            return await check_row_security(make_application_sessions(engine))
        finally:
            await engine.dispose()

    assert run(go) is False


def test_the_role_statement_names_the_role_the_first_migration_creates() -> None:
    """The statement is written out rather than assembled. Delete this and it can name a role
    `0001` never created, which fails every transaction, or a role that is not NOBYPASSRLS."""
    spec = importlib.util.spec_from_file_location(
        "foundation", ROOT / "migrations" / "versions" / "0001_foundation.py"
    )
    assert spec is not None
    assert spec.loader is not None
    foundation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(foundation)

    assert foundation.APP_ROLE == APPLICATION_ROLE
    assert f"SET LOCAL ROLE {APPLICATION_ROLE}" == SET_APPLICATION_ROLE
    assert "NOBYPASSRLS" in foundation.CREATE_APP_ROLE
    assert "PgBouncer" in THE_APPLICATION_ANSWERS_AS_THE_ROLE_ROW_SECURITY_BINDS


def test_a_replicas_console_reads_run_as_the_application_role_too() -> None:
    """Delete this and the replica's sessions can go back to the plain factory, so a console page
    served from the replica reads past the policies the same page is held to on the primary."""
    primary = make_application_sessions(make_app_engine(UNANSWERED))
    reads = console_reads_for(primary, "postgresql://nobody@127.0.0.1:1/replica")

    assert reads is not None
    assert reads._replica is not None
    assert reads._replica.kw["sync_session_class"] is ApplicationRoleSession


# ------------------------------------------------------------------ an install with no cache


class CountingStore:
    def __init__(self, held: EntitlementSet) -> None:
        self.held = held
        self.loads = 0

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        del principal_id, now
        self.loads += 1
        return self.held


class FailingStore:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        del principal_id, now
        msg = "the grants could not be read"
        raise RuntimeError(msg)


class Version:
    async def grants_version(self, principal_id: str) -> int:
        del principal_id
        return 3


HELD = EntitlementSet(
    principal_id="u_reader",
    grants=(Grant(capability=Capability(value="read:client"), scope=Scope()),),
)


def test_an_install_with_no_cache_resolves_every_request_from_the_store() -> None:
    """See `AN_ABSENT_CACHE_IS_A_MISS_AND_NEVER_AN_ANSWER`. Delete this and the stand-in can
    answer a read with a set of its own, an empty one that tells a reader with grants that there
    is nothing, or a remembered one that no revocation retires."""
    store = CountingStore(HELD)
    cache = NoEntitlementCache()

    async def twice() -> tuple[EntitlementSet, EntitlementSet]:
        first = await resolve("u_reader", versions=Version(), store=store, cache=cache)
        second = await resolve("u_reader", versions=Version(), store=store, cache=cache)
        return first.entitlements, second.entitlements

    assert asyncio.run(twice()) == (HELD, HELD)
    assert store.loads == 2
    assert "every request resolves" in AN_ABSENT_CACHE_IS_A_MISS_AND_NEVER_AN_ANSWER


def test_an_install_with_no_cache_never_turns_a_failed_store_into_an_answer() -> None:
    """The fail-closed sibling. Delete this and a stand-in that answers reads can hide a store
    outage behind whatever it hands back, which is a reach computed from nothing."""
    with pytest.raises(ResolutionFailedError):
        asyncio.run(
            resolve(
                "u_reader", versions=Version(), store=FailingStore(), cache=NoEntitlementCache()
            )
        )


# ------------------------------------------------------------------ the database


def test_an_application_transaction_runs_as_a_role_row_security_binds_whatever_the_login() -> None:
    """The scratch server's login is its superuser, as a deployment's is. Delete this and the
    listener can go, and every request runs as a role that reads past every policy while each
    store's own tests, which log in as `brain_app`, stay green. The plain factory on the same
    engine is the negative, which proves the check can say no."""
    database = "brain_lw_role"
    url = fresh(database)
    try:

        async def go() -> tuple[bool, bool, str]:
            engine = make_app_engine(url)
            try:
                plain = await check_row_security(make_session_factory(engine))
                applied = await check_row_security(make_application_sessions(engine))
                async with make_application_sessions(engine)() as session:
                    who = (await session.execute(text("SELECT current_user"))).scalar_one()
                return plain, applied, str(who)
            finally:
                await engine.dispose()

        assert run(go) == (False, True, APPLICATION_ROLE)
    finally:
        drop(database)


def test_the_role_ends_with_the_transaction_so_a_pooled_connection_goes_back_as_it_came() -> None:
    """See `THE_APPLICATION_ANSWERS_AS_THE_ROLE_ROW_SECURITY_BINDS`. One pooled connection stands
    for PgBouncer's server connection. Delete this and the statement can lose LOCAL, which passes
    every other test here and, behind a transaction pooler, hands the role to whichever client
    gets the connection next while this one's next transaction runs as the superuser."""
    database = "brain_lw_local"
    url = fresh(database)
    try:

        async def go() -> tuple[str, str, str]:
            engine = create_async_engine(normalise_database_url(url), pool_size=1, max_overflow=0)
            try:
                async with engine.connect() as conn:
                    login = (await conn.execute(text("SELECT current_user"))).scalar_one()
                async with make_application_sessions(engine)() as session, session.begin():
                    inside = (await session.execute(text("SELECT current_user"))).scalar_one()
                async with engine.connect() as conn:
                    after = (await conn.execute(text("SELECT current_user"))).scalar_one()
                return str(login), str(inside), str(after)
            finally:
                await engine.dispose()

        login, inside, after = run(go)
        assert inside == APPLICATION_ROLE
        assert after == login != APPLICATION_ROLE
    finally:
        drop(database)


def test_a_console_read_can_still_declare_itself_read_only_after_the_role_is_taken() -> None:
    """`replica_store` begins every console read with SET TRANSACTION READ ONLY, which PostgreSQL
    accepts only before the transaction's first query. Delete this and a role statement that
    counted as a query would fail every console page, found on the first page load."""
    database = "brain_lw_read_only"
    url = fresh(database)
    try:

        async def go() -> tuple[str, str]:
            engine = make_app_engine(url)
            try:
                async with make_application_sessions(engine)() as session:
                    await session.execute(text("SET TRANSACTION READ ONLY"))
                    who = (await session.execute(text("SELECT current_user"))).scalar_one()
                    mode = (await session.execute(text("SHOW transaction_read_only"))).scalar_one()
                return str(who), str(mode)
            finally:
                await engine.dispose()

        assert run(go) == (APPLICATION_ROLE, "on")
    finally:
        drop(database)


def signed_for(subject: str) -> dict[str, str]:
    issued = int(time.time())
    return {"authorization": f"Bearer {token(sub=subject, iat=issued, exp=issued + 300)}"}


def test_a_subject_an_administrator_bound_gets_through_the_gate_the_lifespan_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end, on a real database, with nothing wired by hand: the lifespan builds the gate,
    a subject is bound with `sign_in_binding` as an administrator will bind one, and a token that
    names it, signed by a test key and verified against the key set fetched through the lifespan's
    own client, reaches the question route's entitlement step, where the grants are read as the
    application role. An unbound subject with an equally valid token is refused in the one
    sentence and reads no grants.

    Delete this and every piece can pass alone while the assembled process refuses everybody:
    a role the sessions cannot take, a directory over another factory, or a key set fetched from
    somewhere the tokens were not signed for."""
    loaded: list[EntitlementSet] = []
    original = StoredEntitlements.load

    async def spied(self: StoredEntitlements, principal_id: str, now: datetime) -> EntitlementSet:
        found = await original(self, principal_id, now)
        loaded.append(found)
        return found

    served = Realm()
    monkeypatch.setenv("INSTALL_OIDC_ISSUER", ISSUER)
    monkeypatch.setattr("brain.app.key_set_client", served.client)
    monkeypatch.setattr(StoredEntitlements, "load", spied)

    with resolver("brain_lw_end_to_end") as url:
        a_principal(url, "u_admin")
        a_principal(url, "u_bound")
        a_grant(url, "u_bound", "read:client")

        async def bind() -> Binding:
            engine = make_app_engine(url)
            try:
                writer = sign_in_bindings(make_application_sessions(engine))
                return await writer.bind(
                    "s-bound", principal_id="u_bound", bound_by="u_admin", now=datetime.now(UTC)
                )
            finally:
                await engine.dispose()

        assert run(bind) is Binding.BOUND

        app = create_app(
            Settings(env="development", database_url=url, run_migrations=False, valkey_url="")
        )

        async def ask() -> tuple[dict[str, bool], int, str, int, int, str]:
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://brain") as c:
                    health = (await c.get("/health/ready")).json()
                    checks = {**health["checks"], **health["reported"]}
                    me = await c.get(f"{API_PREFIX}/me", headers=signed_for("s-bound"))
                    answered = await c.post(
                        f"{API_PREFIX}/answer",
                        headers=signed_for("s-bound"),
                        json={"question": "how many hours are left"},
                    )
                    stranger = await c.post(
                        f"{API_PREFIX}/answer",
                        headers=signed_for("s-stranger"),
                        json={"question": "how many hours are left"},
                    )
            return (
                checks,
                me.status_code,
                str(me.json().get("principal_id")),
                answered.status_code,
                stranger.status_code,
                str(stranger.json().get("message")),
            )

        checks, me_status, me_principal, answered_status, stranger_status, refusal = run(ask)

    assert checks[SIGN_IN_CHECK] is True
    assert checks[ROW_SECURITY_CHECK] is True
    assert (me_status, me_principal) == (200, "u_bound")
    assert answered_status != 401
    assert [one.principal_id for one in loaded] == ["u_bound", "u_bound"]
    assert all(one.holds(Capability(value="read:client")) for one in loaded)
    assert (stranger_status, refusal) == (401, SIGN_IN_PROMPT)
    assert served.idp.urls == [jwks_url_for(ISSUER)]
