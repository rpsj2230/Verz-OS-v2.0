"""The connectors screen over HTTP: who may see it, who may connect a source, and what is said.

Driven through the real application, with the token machinery, the identity directory and the key
source imported from `tests/unit/test_api_routes.py` rather than rebuilt, for that file's reason:
a second copy of a JWS builder is a second place a token can be minted subtly differently, and it
fails looking like a permission bug. The rows are `Records`, an in-memory
`brain.ops.connector_store.ConnectorRecords` that keeps the store's contract (a source already
connected is refused before its key is kept) and says whether it was asked; the vault is
`tests.unit.test_credentials.Vault`. The database half, that a write reaches the row, the ledger
and the lock in that order, is `tests/unit/test_connector_store.py`.

**Every refusal has a sibling that reads or writes**, and on this screen the sibling matters more
than usual: a route that refused everybody would pass every disclosure test in this file while
answering nothing to anybody, and the screen it produces looks exactly like an install that reads
no outside system.

**No key reaches a response or a log line, and that is asserted over the whole body and over
everything the run logged rather than over a named field.** A test naming the field would go green
the moment somebody added a different one.

Task ids: M42.6.5, M27.15.8
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any, Final

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.connector_routes import (
    ACCEPT_PATH,
    CONNECTORS_PATH,
    CONNECTORS_READ,
    DISCONNECT_PATH,
    DRIFT_PATH,
    EDIT_PATH,
    EXPORT_PATH,
    KEY_PATH,
    PROBE_PATH,
    PROBE_STATE_PATH,
    SOURCE_PATH,
    SOURCES_PATH,
    ConnectorsView,
)
from brain.connectors.contract import HealthState
from brain.connectors.declaration import shipped
from brain.connectors.manifest import manifest_digest
from brain.connectors.registry import INSTALL_AUTHORITY
from brain.console.connector_trust import (
    DECLARATION_AGREED,
    DECLARATION_CHANGED,
    DECLARATION_UNREADABLE,
    KEY_HELD,
    KEY_NOT_KNOWN,
    LIVE_KEY_HELD,
    LIVE_NOT_SHOWN,
    LIVE_NOTHING_LOOKED,
    NEVER_READ_LIVE,
    NOTHING_HERE_CAN_SAY_WHICH_SOURCES_ARE_CONNECTED,
    NOTHING_HERE_COUNTS_TODAYS_CALLS,
)
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.identity.data_steward import declared_capabilities
from brain.ops.connectable import (
    CONNECTABLE,
    DECLARED_FORMS,
    NOT_FROM_THE_CONSOLE,
    THIS_INSTALL_CANNOT_READ_IT_YET,
    manifest_for,
)
from brain.ops.connector_admin import (
    ALLOWING_A_WRITE,
    CONNECTED,
    CONNECTING_A_SOURCE,
    DISCONNECTED,
    DISCONNECTING_A_SOURCE,
    EDITED,
    KEY_REPLACED,
    NO_SUCH_WRITE,
    TOLD,
    VAULT_SAYS,
    WHAT_CONNECTING_A_SOURCE_STARTS,
    WRITE_ALLOWED,
)
from brain.ops.connector_probe import (
    TEST_WAITING,
    TESTING_A_SOURCE,
    ProbeRecord,
    ProbeStatus,
)
from brain.ops.connector_recordings import recorded_in_words
from brain.ops.connector_store import (
    Connection,
    ConnectionRecord,
    ConnectorTakenError,
    NotConnectedError,
)
from brain.ops.connector_sync import (
    KEY_DECLINED,
    NO_VERIFIED_CEILING,
    NOT_READ_YET,
    READ_TO_THE_END,
    TRIED_AGAIN,
    SyncOutcome,
    SyncState,
)
from brain.ops.credentials import KEY_FIELD, Credentials, VaultState
from brain.ops.openbao import StaticVersion, VaultRefusedError, VaultUnreachableError
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)
from tests.unit.test_credentials import AT, Recorded, Vault

LISTING: Final = f"{API_PREFIX}{CONNECTORS_PATH}"

#: A key nothing else in any output could contain, so finding it anywhere is a leak.
KEY: Final = "SOURCE-KEY-SENTINEL-8c1f2e"

WHOLE: Final = Scope.unrestricted()
ONE_SOURCE: Final = Scope(clauses=(Clause(field="connector", op=Op.EQ, value="xero"),))
ONE_DEPARTMENT: Final = Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),))

#: The plane grant this screen needs beside its own capability. `brain.console.reads.permitted`
#: asks for both, and the route calls that function rather than checking the capability alone.
THE_CONSOLE_PLANE: Final[Grant] = Grant(capability=plane_capability(Plane.CONTENT), scope=WHOLE)

#: An `amr` a Keycloak session carries when a second factor was used.
SECOND_FACTOR: Final[Mapping[str, object]] = {"amr": ["otp"]}

#: Far outside any plausible wall clock. See `CLAUDE.md` on a fixture with a date in it.
LONG_AGO: Final = datetime(2019, 1, 1, tzinfo=UTC)

#: One identifier per connectable source, shaped as the source's own would be and naming nobody.
IDENTIFIERS: Final[Mapping[str, str]] = {
    "xero": "11111111-2222-3333-4444-555555555555",
    "hubspot": "12345678",
    "freshdesk": "example.freshdesk.com",
    "cloudflare": "0123456789abcdef0123456789abcdef",
    "google_drive": "1AbCdEfGhIjKlMnOpQrStUv",
    "google_analytics": "123456789",
    "search_console": "sc-domain:example.com",
    "laravel": "portal",
    "domains": "example.com, example.org",
}

#: The settings after the first that a source asks for, for the sources that ask for more than one.
FURTHER_SETTINGS: Final[Mapping[str, Mapping[str, str]]] = {
    "freshdesk": {"department": "support"},
    "cloudflare": {"department": "operations"},
    "google_drive": {"domain": "example.com", "department": "operations", "steward": "u_steward"},
    "domains": {"department": "operations"},
    "google_analytics": {"department": "marketing"},
    "search_console": {"department": "marketing"},
    "laravel": {
        "host": "db.example.invalid",
        "port": "3306",
        "private_network": "no",
        "tls": "verify",
        "client_rule": "department = sales",
        "user_rule": "department = operations",
        "max_rows": "500",
        "timeout_seconds": "10",
    },
}


def _grant(capability: Any, scope: Scope) -> Grant:
    return Grant(capability=capability, scope=scope)


#: What each of `test_api_routes`' people holds here. `u_narrow` reads and connects one source;
#: `u_prefix` may connect every source and read none; `u_wide` reads every source and connects
#: none; `u_elsewhere` holds the read with no console plane and the install authority narrowed by
#: department, which admits no source at all.
GRANTS: Final[dict[str, tuple[Grant, ...]]] = {
    "u_none": (THE_CONSOLE_PLANE,),
    "u_narrow": (
        THE_CONSOLE_PLANE,
        _grant(CONNECTORS_READ, ONE_SOURCE),
        _grant(INSTALL_AUTHORITY, ONE_SOURCE),
    ),
    "u_prefix": (THE_CONSOLE_PLANE, _grant(INSTALL_AUTHORITY, WHOLE)),
    "u_wide": (THE_CONSOLE_PLANE, _grant(CONNECTORS_READ, WHOLE)),
    "u_admin": (
        THE_CONSOLE_PLANE,
        _grant(CONNECTORS_READ, WHOLE),
        _grant(INSTALL_AUTHORITY, WHOLE),
    ),
    "u_elsewhere": (_grant(CONNECTORS_READ, WHOLE), _grant(INSTALL_AUTHORITY, ONE_DEPARTMENT)),
}


class HeldGrants:
    """A `brain.gate.resolve.EntitlementStore` over `GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


def _wiring() -> Any:
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=HeldGrants(),
        cache=NoCache(),
    )


class NoDatabase:
    """A session factory that must never be asked, and is not one `sessions_of` recognises."""

    def __call__(self) -> Any:
        raise AssertionError("a database session was opened")


def settings_for(name: str) -> dict[str, str]:
    """The settings a declared form takes, and none for a source with no form."""
    if name not in DECLARED_FORMS:
        return {}
    first = DECLARED_FORMS[name].settings[0].name
    return {first: IDENTIFIERS[name], **FURTHER_SETTINGS.get(name, {})}


def a_connection(
    name: str = "xero",
    *,
    settings: Mapping[str, str] | None = None,
    digest: str | None = None,
    by: str = "u_admin",
) -> Connection:
    """One connection, pinned to the digest its settings build today unless told otherwise."""
    given = dict(settings) if settings is not None else settings_for(name)
    pinned = digest if digest is not None else manifest_digest(manifest_for(name, given))
    return Connection(
        connector=name, settings=given, digest=pinned, connected_by=by, connected_at=LONG_AGO
    )


class Records:
    """`ConnectorRecords` in memory, keeping the store's contract, and noting what it was asked."""

    def __init__(self, existing: tuple[Connection, ...] = ()) -> None:
        self.rows = {one.connector: one for one in existing}
        self.asked = 0
        self.connects: list[dict[str, Any]] = []
        self.disconnects: list[tuple[str, str]] = []
        #: What each connect was asked to grant the data steward, in order.
        self.declared: list[tuple[str, ...]] = []

    async def connected(self) -> tuple[Connection, ...]:
        self.asked += 1
        return tuple(self.rows[name] for name in sorted(self.rows))

    async def connect(
        self,
        *,
        connector: str,
        settings: Mapping[str, str],
        digest: str,
        actor: str,
        trace_id: str,
        ent_hash: str,
        keep_key: Callable[[], Awaitable[datetime | None]],
        declared: Sequence[str] = (),
        agreed: str = "",
    ) -> Connection:
        self.asked += 1
        self.declared.append(tuple(declared))
        if connector in self.rows:
            raise ConnectorTakenError(connector)
        await keep_key()
        made = Connection(
            connector=connector,
            settings=dict(settings),
            digest=digest,
            connected_by=actor,
            connected_at=LONG_AGO,
            agreed=agreed,
        )
        self.rows[connector] = made
        self.connects.append({"connection": made, "ent_hash": ent_hash})
        return made

    async def disconnect(
        self, connector: str, *, actor: str, trace_id: str, ent_hash: str
    ) -> datetime:
        self.asked += 1
        if connector not in self.rows:
            raise NotConnectedError(connector)
        del self.rows[connector]
        self.disconnects.append((connector, actor))
        return LONG_AGO


@pytest.fixture
def app() -> Iterator[FastAPI]:
    """The real application, built the way a deployment builds it.

    `create_app` produces the router registration as well as the routes: a test mounting the
    router itself would prove the route works and not that it is served.
    """
    built: FastAPI = create_app(Settings(env="development"))
    yield built


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """An install with no database and no vault until a test attaches them."""
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = NoDatabase()
        yield c


async def everybody_is_live(principal_id: str) -> bool:
    """A directory in which every id names somebody, for the routes' own tests."""
    del principal_id
    return True


def attach(
    app: FastAPI, records: Records | None, vault: Vault | None, writes: Recorded | None = None
) -> None:
    if records is not None:
        app.state.connector_records = records
    app.state.credentials = Credentials(vault, environ={}, writes=writes)
    app.state.people_are_live = everybody_is_live


def headers(pid: str, claims: Mapping[str, object] | None = None) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims=claims or SECOND_FACTOR)}"}


def get(c: TestClient, pid: str) -> Response:
    response: Response = c.get(LISTING, headers=headers(pid))
    return response


def post(c: TestClient, pid: str, path: str, body: object = None, **kw: Any) -> Response:
    response: Response = c.post(path, headers=headers(pid, **kw), json=body)
    return response


def connection_body(name: str = "xero", **changed: object) -> dict[str, object]:
    body: dict[str, object] = {"connector": name, "settings": settings_for(name), "credential": KEY}
    body.update(changed)
    return body


def disconnect_path(name: str) -> str:
    return API_PREFIX + DISCONNECT_PATH.replace("{connector}", name)


def without_trace(response: Response) -> dict[str, Any]:
    found = dict(response.json())
    found.pop("trace_id", None)
    return found


def held_vault() -> Vault:
    return Vault(version=StaticVersion(written_at=AT))


# ------------------------------------------------------------------ what a reader is told


@pytest.fixture
def hubspot_unmeasured(monkeypatch: pytest.MonkeyPatch) -> None:
    """HubSpot with its recorded ceiling taken away, so its plan refuses as an unmeasured source's
    does. Since 2026-09-30 every source the console offers has a ceiling, so a refusal for want
    of one is shown on a source that had it taken away."""
    from brain.ops import limits

    kept = {name: one for name, one in limits._BY_NAME.items() if name != "hubspot"}
    monkeypatch.setattr(limits, "_BY_NAME", kept)


@pytest.fixture
def forms_offered_as_if_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Google Drive's and Laravel's declared forms offered as though this install could read them,
    so their route halves (a key file, a database user, an answerable person) are proved before
    their readings land. See `A_SOURCE_THE_CONSOLE_OFFERS_IS_ONE_THIS_INSTALL_READS` in
    `brain.ops.connectable`."""
    import brain.connector_routes as routes
    import brain.ops.connectable as connectable
    import brain.ops.connector_admin as admin

    both = ("google_drive", "laravel")
    offered = MappingProxyType(
        {**connectable.CONNECTABLE, **{one: connectable.DECLARED_FORMS[one] for one in both}}
    )
    listed = {k: v for k, v in connectable.NOT_FROM_THE_CONSOLE.items() if k not in both}
    for module in (routes, connectable, admin):
        if hasattr(module, "CONNECTABLE"):
            monkeypatch.setattr(module, "CONNECTABLE", offered)
        if hasattr(module, "NOT_FROM_THE_CONSOLE"):
            monkeypatch.setattr(module, "NOT_FROM_THE_CONSOLE", MappingProxyType(listed))


def test_a_reader_is_told_which_sources_are_connected_and_what_each_may_read(
    app: FastAPI, client: TestClient
) -> None:
    """The positive case, and the sibling of every refusal below.

    Asserted by naming a source and reading its fields rather than by counting the list. The
    lifecycle is `registered` and serving is false, because nothing runs a connected source, and
    the credential column says the key is held rather than how a lease is borrowed.

    Delete this and the refusals are satisfied by a route that refuses everybody, which renders
    as an install that reads no outside system at all."""
    attach(app, Records((a_connection("xero"), a_connection("hubspot"))), held_vault())
    body = get(client, "u_wide").json()

    by_name = {one["name"]: one for one in body["connectors"]}
    assert set(by_name) == {"xero", "hubspot"}
    xero = by_name["xero"]
    assert (xero["connected_by"], xero["key_held"], xero["pinned"]) == ("u_admin", True, True)
    assert xero["key_written_at"] is not None
    assert xero["declaration"] == DECLARATION_AGREED
    assert xero["trust"]["wiring"] == "rest"
    assert xero["trust"]["lifecycle"] == "registered"
    assert xero["trust"]["serving"] is False
    assert xero["trust"]["health"] == ""
    assert xero["trust"]["credential"] == KEY_HELD
    assert IDENTIFIERS["xero"] in xero["trust"]["reaches"]
    assert xero["may_disconnect"] is False
    assert all(one["may_disconnect"] for one in get(client, "u_admin").json()["connectors"])


def test_a_grant_narrowed_to_one_source_is_told_about_that_source_and_asks_the_vault_of_no_other(
    app: FastAPI, client: TestClient
) -> None:
    """Deleting this lets a narrowed grant answer the whole list, which is the disclosure this
    screen exists to prevent, or lets the vault be asked about a source the reader holds nothing
    over, so a vault that refuses for that source's slot tells them it exists."""
    vault = held_vault()
    attach(app, Records((a_connection("xero"), a_connection("hubspot"))), vault)
    body = get(client, "u_narrow").json()

    assert [one["name"] for one in body["connectors"]] == ["xero"]
    assert vault.asked == ["connector_keys/xero"]


class SyncRecords:
    """`brain.ops.connector_sync_store.ConnectorSyncRecords` in memory, noting that it was asked."""

    def __init__(self, states: Mapping[str, SyncState]) -> None:
        self.found = dict(states)
        self.asked = 0

    async def states(self) -> Mapping[str, SyncState]:
        self.asked += 1
        return dict(self.found)


def an_attempt(name: str, **changed: Any) -> SyncState:
    base: dict[str, Any] = {
        "connector": name,
        "finished_at": LONG_AGO,
        "outcome": SyncOutcome.SYNCED,
        "health": HealthState.OK,
        "consecutive_failures": 0,
        "next_attempt_at": LONG_AGO,
        "detail": READ_TO_THE_END,
        "last_synced_at": LONG_AGO,
    }
    base.update(changed)
    return SyncState(**base)


def test_a_connected_source_shows_when_it_was_last_read_and_how_that_went(
    app: FastAPI, client: TestClient, hubspot_unmeasured: None
) -> None:
    """**The screen's half of the leaf.** A source read to the end shows the attempt's time and
    health in its trust row and its last read beside them. A source whose key was declined shows
    down, when it is tried again, and the last time it was read, which is older than the attempt.
    A source nothing has tried says so, and a source nothing may read says why rather than showing
    an attempt. A reader told of one source is told of that source's reading and of no other.

    Delete this and the Connectors screen goes back to an empty state column for every source
    while the worker reads them, or shows a failing source's old read as current."""
    declined = an_attempt(
        "xero",
        finished_at=LONG_AGO + timedelta(days=2),
        outcome=SyncOutcome.FAILED,
        health=HealthState.DOWN,
        consecutive_failures=1,
        next_attempt_at=LONG_AGO + timedelta(days=3),
        detail=KEY_DECLINED,
    )
    attach(app, Records((a_connection("xero"), a_connection("hubspot"))), held_vault())
    app.state.connector_sync_records = SyncRecords(
        {"xero": declined, "hubspot": an_attempt("hubspot")}
    )
    wide = {one["name"]: one for one in get(client, "u_wide").json()["connectors"]}
    narrow = get(client, "u_narrow").json()["connectors"]

    xero = wide["xero"]
    assert xero["trust"]["health"] == "down"
    assert xero["trust"]["checked_at"] == declined.finished_at.isoformat()
    assert xero["last_synced_at"] == LONG_AGO.isoformat().replace("+00:00", "Z")
    assert xero["next_sync_at"] == (LONG_AGO + timedelta(days=3)).isoformat().replace("+00:00", "Z")
    assert xero["sync"].startswith(KEY_DECLINED)
    assert TRIED_AGAIN in xero["sync"]
    assert wide["hubspot"]["sync"] == NO_VERIFIED_CEILING
    assert [one["name"] for one in narrow] == ["xero"]
    assert "hubspot" not in json.dumps(narrow)

    app.state.connector_sync_records = SyncRecords({})
    untried = get(client, "u_wide").json()["connectors"]
    assert {one["name"]: one["sync"] for one in untried}["xero"] == NOT_READ_YET
    assert all(one["last_synced_at"] is None for one in untried)
    assert all(one["trust"]["health"] == "" for one in untried)


def test_the_attempts_are_asked_for_only_when_there_is_a_connection_to_describe(
    app: FastAPI, client: TestClient
) -> None:
    """A reader of the screen told of no connection, on an install with none and on one whose only
    connection their grant does not reach, has the worker's record read on nobody's behalf.

    Delete this and the attempts are read for a page that can show none of them, and a store that
    failed for a source the reader may not be told of would fail their listing."""
    records = SyncRecords({"xero": an_attempt("xero")})
    attach(app, Records(), held_vault())
    app.state.connector_sync_records = records
    get(client, "u_wide")
    attach(app, Records((a_connection("hubspot"),)), held_vault())
    get(client, "u_narrow")
    assert records.asked == 0

    attach(app, Records((a_connection("xero"),)), held_vault())
    get(client, "u_narrow")
    assert records.asked == 1


def test_every_connector_says_what_it_was_tested_against_apart_from_what_is_live_here(
    app: FastAPI, client: TestClient
) -> None:
    """The release's recordings and this install's credential are two sentences, and a source the
    reader may not be told of reads exactly like one nobody connected.

    Delete this and a connector tested against recordings can render as one that works here, or
    the evidence list can tell a narrowed reader that hubspot is connected."""
    attach(app, None, held_vault())
    unread = {one["name"]: one for one in get(client, "u_wide").json()["evidence"]}
    attach(app, Records((a_connection("xero"), a_connection("hubspot"))), held_vault())
    wide = {one["name"]: one for one in get(client, "u_wide").json()["evidence"]}
    narrow = {one["name"]: one for one in get(client, "u_narrow").json()["evidence"]}

    every = set(CONNECTABLE) | set(NOT_FROM_THE_CONSOLE)
    assert set(wide) == set(narrow) == set(unread) == every
    assert all(one["recorded"] == recorded_in_words(name) for name, one in wide.items())
    assert (wide["xero"]["credential"], wide["xero"]["live_read"]) == (
        LIVE_KEY_HELD,
        NEVER_READ_LIVE,
    )
    assert wide["xero"]["last_read_live_at"] is None
    assert narrow["hubspot"] == narrow["laravel"] | {
        "name": "hubspot",
        "label": narrow["hubspot"]["label"],
        "recorded": recorded_in_words("hubspot"),
    }
    assert narrow["hubspot"]["credential"] == LIVE_NOT_SHOWN
    assert unread["xero"]["credential"] == LIVE_NOTHING_LOOKED


def test_a_body_carries_no_count_of_the_sources_that_were_left_out(
    app: FastAPI, client: TestClient
) -> None:
    """Deleting this lets a `total` appear beside a filtered list, and a reader holding one grant
    then learns how many other systems this company reads by subtraction."""
    attach(app, Records((a_connection("xero"), a_connection("hubspot"))), held_vault())
    body = get(client, "u_narrow").json()

    assert not any(key in body for key in ("total", "truncated", "hidden", "withheld", "of"))
    assert not any(key in body["connectors"][0] for key in ("total", "hidden", "of"))


def test_a_caller_without_the_screen_is_answered_alike_whatever_the_install_holds(
    app: FastAPI, client: TestClient
) -> None:
    """DENIED and ABSENT are one answer. Somebody holding no connector grant on an install with two
    connections, on one with no database, and somebody holding only the install authority, get the
    same status and body, and neither the store nor the vault is asked for any of them.

    Delete this and a refusal acquires a message of its own, or the store is read first and
    filtered after, which is the change that reads as helpfulness."""
    refused_without = get(client, "u_none")
    records, vault = Records((a_connection("xero"), a_connection("hubspot"))), held_vault()
    attach(app, records, vault)
    refused_with = get(client, "u_none")
    authority_alone = get(client, "u_prefix")

    for one in (refused_with, authority_alone):
        assert (one.status_code, without_trace(one)) == (
            refused_without.status_code,
            without_trace(refused_without),
        )
    assert without_trace(refused_with) == {"message": Absent.public_message}
    assert records.asked == 0 and vault.asked == []
    assert get(client, "u_wide").status_code == 200


def test_the_console_plane_is_asked_for_as_well_as_the_capability(
    app: FastAPI, client: TestClient
) -> None:
    """`u_elsewhere` holds the read over every source and no console plane, and is refused; `u_wide`
    holds both and is answered. Deleting this lets the route check the capability alone."""
    attach(app, Records((a_connection("xero"),)), held_vault())
    assert get(client, "u_elsewhere").status_code == 404
    assert get(client, "u_wide").status_code == 200


# ------------------------------------------------------------------ when nothing looked


def test_an_install_with_no_database_answers_a_sentence_and_never_an_empty_list(
    app: FastAPI, client: TestClient
) -> None:
    """Deleting this lets the route send `connectors: []` on an install where nothing looked, which
    reads as a system that reads no outside data. The sibling is an install whose store holds no
    connection, which is an empty list and no sentence."""
    attach(app, None, held_vault())
    unread = get(client, "u_wide").json()
    attach(app, Records(), held_vault())
    empty = get(client, "u_wide").json()

    assert (unread["connectors"], unread["unread"]) == (
        None,
        NOTHING_HERE_CAN_SAY_WHICH_SOURCES_ARE_CONNECTED,
    )
    assert (empty["connectors"], empty["unread"]) == ([], "")


def test_something_attached_that_is_not_a_store_is_not_treated_as_one(
    app: FastAPI, client: TestClient
) -> None:
    """A string on `app.state.connector_records` would otherwise be awaited inside the request and
    reach the caller as a 500 that reads as a bug in the gate. With no database beside it the
    answer is the sentence. Delete this and the `isinstance` check can go."""
    app.state.connector_records = "not a store"
    body = get(client, "u_wide").json()

    assert body["connectors"] is None
    assert body["unread"] == NOTHING_HERE_CAN_SAY_WHICH_SOURCES_ARE_CONNECTED


def test_a_list_and_a_sentence_cannot_both_be_sent() -> None:
    """Deleting this lets a body carry both, and a reader cannot then tell an install that reads
    nothing from one nothing looked at. Asserted on the model, because no route builds the bad
    value."""
    common: dict[str, Any] = {
        "connecting": "x",
        "confirm_connect": "x",
        "confirm_disconnect": "x",
        "copy_policy": [],
        "budget_unread": "y",
        "may_connect": False,
        "vault": VaultState.READY,
        "vault_told": "",
        "connectable": [],
        "not_connectable": [],
        "evidence": [],
        "key_max_chars": 1,
        "key_blank": "x",
    }
    with pytest.raises(ValidationError):
        ConnectorsView(connectors=[], unread="something", **common)
    with pytest.raises(ValidationError):
        ConnectorsView(**common)
    ConnectorsView(connectors=[], **common)
    ConnectorsView(unread="nothing looked", **common)


def test_every_answer_says_what_connecting_does_not_do_and_offers_the_same_sources(
    app: FastAPI, client: TestClient
) -> None:
    """The sentence stands beside the controls, and it is dropped most easily from the branch
    nobody looks at, which is the unread one. The sources that can be connected and the reasons
    the others cannot are the release's, so they are the same with and without a database.
    Delete this and a screen offers a connect button with nothing saying nothing will read."""
    attach(app, None, held_vault())
    unread = get(client, "u_admin").json()
    attach(app, Records((a_connection("xero"),)), held_vault())
    wired = get(client, "u_admin").json()

    for body in (unread, wired):
        assert body["connecting"] == WHAT_CONNECTING_A_SOURCE_STARTS
        assert body["confirm_connect"] == CONNECTING_A_SOURCE
        assert body["confirm_disconnect"] == DISCONNECTING_A_SOURCE
        assert body["budget_unread"] == NOTHING_HERE_COUNTS_TODAYS_CALLS
        assert len(body["copy_policy"]) > 2
        assert {one["name"] for one in body["connectable"]} == set(CONNECTABLE)
        assert all(one["why"] for one in body["not_connectable"])
    assert unread["connectable"] == wired["connectable"]
    # The sentences a console says for a blank field before confirming are the route's own.
    blank = post(client, "u_admin", LISTING, connection_body(settings={}, credential=""))
    told = {one["field"]: one["message"] for one in blank.json()["problems"]}
    xero = next(one for one in wired["connectable"] if one["name"] == "xero")
    assert told == {"tenant_id": xero["settings"][0]["blank"], "credential": wired["key_blank"]}


def test_the_screen_lists_every_shipped_connector_from_its_own_declaration(
    app: FastAPI, client: TestClient
) -> None:
    """**What the Connectors screen shows is read off each connector's `CONNECTOR`.** Every source
    this release ships is either offered with its form or explained with its reason, under the
    label its module declares, and none is both. Delete this and a connector added with a
    declaration can be missing from the screen, or shown under words no module states, and the
    only list anybody checks is the one the route builds."""
    from brain.connectors.declaration import shipped

    attach(app, None, held_vault())
    body = get(client, "u_admin").json()
    declared = shipped()
    offered = {one["name"]: one["label"] for one in body["connectable"]}
    explained = {one["name"]: (one["label"], one["why"]) for one in body["not_connectable"]}

    assert len(declared) >= 7
    assert set(offered) | set(explained) == set(declared)
    assert not set(offered) & set(explained)
    for name, label in offered.items():
        assert declared[name].console is not None and label == declared[name].label
    for name, (label, why) in explained.items():
        # A form this install cannot read yet says so; a source with no form, in its own words.
        said = declared[name].not_from_the_console or THIS_INSTALL_CANNOT_READ_IT_YET
        assert (label, why) == (declared[name].label, said)


def test_every_source_is_served_with_the_steps_of_its_connect_flow(
    app: FastAPI, client: TestClient
) -> None:
    """The console draws each source's connect flow from these steps, so they are served with the
    form: a console source's last step asks for its form's fields and its key, a server source's
    for nothing. Delete this and the flow has nothing to draw, or draws steps the route never
    sent."""
    from brain.connectors.declaration import shipped

    attach(app, None, held_vault())
    body = get(client, "u_admin").json()
    declared = shipped()
    for one in body["connectable"]:
        keys = [step["key"] for step in one["steps"]]
        assert keys == [step.key for step in declared[one["name"]].guide]
        # A source that takes no key (M11.7.4) asks for its settings alone.
        key = [] if one["credential_shape"] == "none" else ["credential"]
        assert one["steps"][-1]["asks"] == [
            *(setting["name"] for setting in one["settings"]),
            *key,
        ]
        assert all(step["sketch"]["heading"] for step in one["steps"])
    # Since 2026-09-30 (M11.7.7) no source is connected at the server: Lark's are Connect Lark's
    # own. Laravel's form is offered since M11.6.1 and Drive's since M11.6.7, because each reads.
    served = {one["name"]: one for one in body["not_connectable"]}
    assert set(served) == {"lark_base", "lark_wiki"}


def test_the_authority_to_connect_is_a_fact_about_the_reader_and_narrows_nothing(
    app: FastAPI, client: TestClient
) -> None:
    """Deleting this lets `may_connect` become a filter, and a reader holding the install authority
    would see sources their read does not reach. Per source it is the reader's own grant over that
    source: `u_narrow` may connect Xero and not HubSpot."""
    attach(app, Records((a_connection("xero"), a_connection("hubspot"))), held_vault())
    holder = get(client, "u_admin").json()
    without = get(client, "u_wide").json()
    narrow = get(client, "u_narrow").json()

    assert (holder["may_connect"], without["may_connect"]) == (True, False)
    assert [one["name"] for one in holder["connectors"]] == [
        one["name"] for one in without["connectors"]
    ]
    assert {one["name"]: one["may_connect"] for one in narrow["connectable"]} == {
        "xero": True,
        "hubspot": False,
        "freshdesk": False,
        "cloudflare": False,
        "domains": False,
        "google_analytics": False,
        "google_drive": False,
        "search_console": False,
        "laravel": False,
    }


# ------------------------------------------------------------------ what the vault said


def test_a_key_the_vault_cannot_be_asked_about_is_not_known_rather_than_not_held(
    app: FastAPI, client: TestClient
) -> None:
    """One silence answers for every row, as `brain.credential_routes.listing` does, and a row whose
    key is not known says so rather than reading as a source with no key. An install naming no vault
    is `absent` without asking. Delete this and a vault that did not answer draws every source as
    missing its key, which sends somebody to connect them all again."""
    silent = Vault(fail=VaultUnreachableError("no answer"))
    attach(app, Records((a_connection("xero"),)), silent)
    unreachable = get(client, "u_wide").json()
    attach(app, Records((a_connection("xero"),)), None)
    absent = get(client, "u_wide").json()

    [row] = unreachable["connectors"]
    assert (row["key_held"], row["key_written_at"]) == (None, None)
    assert row["trust"]["credential"] == KEY_NOT_KNOWN[VaultState.UNREACHABLE]
    assert unreachable["vault"] == "unreachable"
    assert unreachable["vault_told"] == VAULT_SAYS[VaultState.UNREACHABLE]
    assert (absent["vault"], absent["vault_told"]) == ("absent", VAULT_SAYS[VaultState.ABSENT])
    assert absent["connectors"][0]["key_held"] is None


def test_a_connection_this_release_cannot_rebuild_or_that_changed_is_listed_and_says_which(
    app: FastAPI, client: TestClient
) -> None:
    """A source the console no longer connects is still a key in the vault and a row naming who
    connected it, so it is listed with nothing said about what it may read; a source whose
    declaration moved since it was connected says so. Delete this and the one connection nobody can
    account for is the one nobody sees, or a new declaration reads as one somebody agreed to."""
    unreadable = Connection(
        connector="laravel",
        settings={"views": "anything"},
        digest="0" * 64,
        connected_by="u_admin",
        connected_at=LONG_AGO,
    )
    moved = a_connection("xero", digest="f" * 64)
    attach(app, Records((unreadable, moved)), held_vault())
    by_name = {one["name"]: one for one in get(client, "u_wide").json()["connectors"]}

    assert (by_name["laravel"]["trust"], by_name["laravel"]["declaration"]) == (
        None,
        DECLARATION_UNREADABLE,
    )
    assert by_name["laravel"]["pinned"] is False
    assert (by_name["xero"]["pinned"], by_name["xero"]["declaration"]) == (
        False,
        DECLARATION_CHANGED,
    )
    assert by_name["xero"]["trust"] is not None


# ------------------------------------------------------------------ connecting a source


def test_an_administrator_connects_a_source_and_its_key_is_kept_in_its_slot_and_recorded(
    app: FastAPI, client: TestClient
) -> None:
    """M42.6.5's write, through the route: the settings reach the store with their outer whitespace
    gone, pinned to the digest the manifest they build has; the key reaches the source's own slot
    under the one field `Credentials.keep` writes and is recorded as a credential write by the
    person; and the answer says what happened and carries no key. Delete this and the connect can
    store a digest of nothing, write the key somewhere nothing looks, or write it unrecorded."""
    records, vault, writes = Records(), Vault(), Recorded()
    attach(app, records, vault, writes)
    sent = connection_body(settings={"tenant_id": f"  {IDENTIFIERS['xero']}\n"})
    answered = post(client, "u_admin", LISTING, sent)

    assert answered.status_code == 200
    body = answered.json()
    assert (body["connector"], body["change"], body["told"]) == ("xero", "connected", CONNECTED)
    assert body["key_written_at"] is not None
    [made] = records.connects
    assert made["connection"].settings == settings_for("xero")
    assert made["connection"].digest == manifest_digest(manifest_for("xero", settings_for("xero")))
    assert made["connection"].connected_by == "u_admin"
    assert made["ent_hash"]
    assert vault.written == [("connector_keys/xero", {KEY_FIELD: KEY})]
    assert [(one["slot"], one["written_by"]) for one in writes.records] == [
        ("connector_keys/xero", "u_admin")
    ]
    assert KEY not in answered.text


def test_a_key_file_and_a_database_user_reach_their_slots_in_their_own_shapes(
    app: FastAPI, client: TestClient, forms_offered_as_if_read: None
) -> None:
    """M11.7.7 through the route: Google Drive's key file is kept whole as its slot's key, and the
    Laravel user as its password with its name beside it, and the forms say which shape each
    takes. Delete this and the two sources connect with their credentials kept where no reader
    looks, or a form offers a key box for a key file."""
    from brain.ops.credentials import MAX_KEY_FILE_CHARS, SERVICE_ACCOUNT, USER_FIELD

    records, vault = Records(), Vault()
    attach(app, records, vault)
    key_file = json.dumps(
        {"type": SERVICE_ACCOUNT, "client_email": "a@b.example", "private_key": "FILE-SENTINEL"},
        indent=2,
    )
    user = json.dumps({"user": "brain_reader", "password": "PASSWORD-SENTINEL"})
    drive = post(client, "u_admin", LISTING, connection_body("google_drive", credential=key_file))
    views = post(client, "u_admin", LISTING, connection_body("laravel", credential=user))

    assert (drive.status_code, views.status_code) == (200, 200)
    assert vault.written == [
        ("connector_keys/google_drive", {KEY_FIELD: key_file}),
        ("connector_keys/laravel", {KEY_FIELD: "PASSWORD-SENTINEL", USER_FIELD: "brain_reader"}),
    ]
    assert "FILE-SENTINEL" not in drive.text and "PASSWORD-SENTINEL" not in views.text
    forms = {one["name"]: one for one in get(client, "u_admin").json()["connectable"]}
    assert (forms["google_drive"]["credential_shape"], forms["laravel"]["credential_shape"]) == (
        "key_file",
        "database_user",
    )
    assert forms["google_drive"]["credential_max_chars"] == MAX_KEY_FILE_CHARS
    assert forms["xero"]["credential_shape"] == "key"


def test_an_answerable_person_who_is_nobody_here_is_refused_and_nothing_is_kept(
    app: FastAPI, client: TestClient, forms_offered_as_if_read: None
) -> None:
    """`Setting.names_a_person`: Google Drive's steward must be somebody live on this install. The
    connector reads no table, so the route asks. Delete this and a mistyped id is kept as the
    person answerable for a folder, and nobody is ever asked to re-check its files."""
    from brain.ops.credentials import SERVICE_ACCOUNT

    records, vault = Records(), Vault()
    attach(app, records, vault)
    asked: list[str] = []

    async def only_one(principal_id: str) -> bool:
        asked.append(principal_id)
        return principal_id == "u_steward"

    app.state.people_are_live = only_one
    key_file = json.dumps({"type": SERVICE_ACCOUNT, "client_email": "a", "private_key": "b"})
    nobody = connection_body(
        "google_drive",
        settings={**settings_for("google_drive"), "steward": "u_nobody"},
        credential=key_file,
    )
    refused = post(client, "u_admin", LISTING, nobody)
    kept = post(client, "u_admin", LISTING, connection_body("google_drive", credential=key_file))

    assert refused.status_code == 422
    assert [(one["field"], one["code"]) for one in refused.json()["problems"]] == [
        ("steward", "refused")
    ]
    assert kept.status_code == 200 and asked == ["u_nobody", "u_steward"]
    assert [slot for slot, _ in vault.written] == ["connector_keys/google_drive"]


def test_a_credential_in_the_wrong_shape_is_refused_and_nothing_is_kept(
    app: FastAPI, client: TestClient, forms_offered_as_if_read: None
) -> None:
    """Delete this and a pasted key is kept as though it were a key file, or a user with no
    password is kept and every read fails at the database."""
    records, vault = Records(), Vault()
    attach(app, records, vault)
    drive = post(client, "u_admin", LISTING, connection_body("google_drive", credential=KEY))
    views = post(client, "u_admin", LISTING, connection_body("laravel", credential='{"user": "u"}'))

    assert (drive.status_code, views.status_code) == (422, 422)
    assert [(one["field"], one["code"]) for one in drive.json()["problems"]] == [
        ("credential", "not_a_key_file")
    ]
    assert [(one["field"], one["code"]) for one in views.json()["problems"]] == [
        ("credential", "blank")
    ]
    assert records.asked == 0 and vault.written == []


def test_a_connection_hands_the_store_what_the_source_declares_for_the_data_steward(
    app: FastAPI, client: TestClient
) -> None:
    """The route computes the steward's grants from the manifest the connection is pinned to, and
    the store writes them in the connection's transaction. Delete this and the route can hand the
    store nothing, so every source connected from the console is a source whose data nobody on the
    install can ever be granted, while `tests/unit/test_data_steward.py` stays green over the store
    alone."""
    records, vault = Records(), Vault()
    attach(app, records, vault)
    for name in ("xero", "hubspot"):
        answered = post(client, "u_admin", LISTING, connection_body(name))
        assert answered.status_code == 200, name

    assert records.declared == [
        declared_capabilities(manifest_for(name, settings_for(name)))
        for name in ("xero", "hubspot")
    ]
    assert all(records.declared)


def test_a_caller_who_may_not_connect_this_source_is_refused_before_anything_is_judged(
    app: FastAPI, client: TestClient
) -> None:
    """One refusal, before the body is judged, the store asked or the vault written: for somebody
    holding nothing, for a reader holding no authority, for an authority narrowed by department,
    for a grant over one source asking for another, and for a malformed body from any of them. The
    positive sibling is the one-source grant connecting its own source.

    Delete this and a stranger's malformed connection gets a 422 naming the fields, which confirms
    the surface and what it takes, or a grant written for one source writes another's key."""
    records, vault = Records(), Vault()
    attach(app, records, vault)
    refusals = [
        post(client, "u_none", LISTING, connection_body()),
        post(client, "u_wide", LISTING, connection_body()),
        post(client, "u_elsewhere", LISTING, connection_body()),
        post(client, "u_narrow", LISTING, connection_body("hubspot")),
        post(client, "u_none", LISTING, connection_body(settings={}, credential="")),
        post(client, "u_narrow", LISTING, connection_body("lark_base")),
    ]
    for refused in refusals:
        assert (refused.status_code, without_trace(refused)) == (
            404,
            {"message": Absent.public_message},
        )
    assert records.asked == 0 and vault.written == []
    assert post(client, "u_narrow", LISTING, connection_body("xero")).status_code == 200


def test_a_password_only_session_holding_the_authority_connects_nothing(
    app: FastAPI, client: TestClient
) -> None:
    """The authority is an `admin:` verb, so `gate.admission` withholds it from a session with no
    second factor. Delete this and the capability can be respelled `write:` to make a form work."""
    records, vault = Records(), Vault()
    attach(app, records, vault)
    weak = post(client, "u_admin", LISTING, connection_body(), claims={"amr": ["pwd"]})

    assert weak.status_code == 404
    assert records.asked == 0 and vault.written == []
    assert INSTALL_AUTHORITY.value.startswith("admin:")


def test_every_problem_with_a_connection_is_told_at_once_and_nothing_is_written(
    app: FastAPI, client: TestClient
) -> None:
    """A blank identifier and a key with a space in it are two problems in one answer, by field and
    code; a source the console cannot connect is a problem on the source; and an identifier the
    connector itself refuses is told in that source's words. Nothing is written for any of them.
    Delete this and a form is refused for its first mistake and then for its second, or the key is
    written before a bad setting is noticed."""
    records, vault = Records(), Vault()
    attach(app, records, vault)
    both = post(client, "u_admin", LISTING, connection_body(settings={}, credential="one two"))
    unknown = post(client, "u_admin", LISTING, connection_body("lark_base"))
    refused = post(client, "u_admin", LISTING, connection_body(settings={"tenant_id": "*"}))

    assert both.status_code == unknown.status_code == refused.status_code == 422
    assert {(one["field"], one["code"]) for one in both.json()["problems"]} == {
        ("tenant_id", "blank"),
        ("credential", "not_one_piece"),
    }
    assert [(one["field"], one["code"]) for one in unknown.json()["problems"]] == [
        ("connector", "not_connectable")
    ]
    [told] = refused.json()["problems"]
    assert (told["field"], told["code"]) == ("tenant_id", "refused")
    assert told["message"] == CONNECTABLE["xero"].settings[0].refused
    assert records.asked == 0 and vault.written == []


def test_a_source_already_connected_is_a_problem_on_the_source_and_its_key_is_not_replaced(
    app: FastAPI, client: TestClient
) -> None:
    """Connecting a connected source again would write a new key over the one its live settings
    were connected with. Delete this and a second connect replaces a working key with a mistyped
    one while the answer says the source was connected."""
    records, vault = Records((a_connection("xero"),)), Vault()
    attach(app, records, vault)
    again = post(client, "u_admin", LISTING, connection_body())

    assert again.status_code == 422
    assert [(one["field"], one["code"]) for one in again.json()["problems"]] == [
        ("connector", "connected")
    ]
    assert vault.written == []


@pytest.mark.parametrize(
    ("vault", "status", "state"),
    [
        (None, 409, VaultState.ABSENT),
        (Vault(fail=VaultRefusedError("no", status=403)), 409, VaultState.REFUSED),
        (Vault(fail=VaultUnreachableError("silent")), 503, VaultState.UNREACHABLE),
    ],
)
def test_a_vault_that_cannot_keep_the_key_connects_nothing_and_says_which_problem(
    app: FastAPI, client: TestClient, vault: Vault | None, status: int, state: VaultState
) -> None:
    """No vault, a refusal and a silence are three sentences, each as `ErrorBody`, and no source is
    recorded as connected in any of them. Delete this and a vault that refused leaves a source
    listed as connected with no key behind it, or the three become one sentence that tells nobody
    what to fix."""
    records = Records()
    attach(app, records, vault)
    answered = post(client, "u_admin", LISTING, connection_body())

    assert answered.status_code == status
    assert without_trace(answered) == {"message": TOLD[state]}
    assert records.rows == {}


# ------------------------------------------------------------------ disconnecting a source


def test_disconnecting_records_who_did_and_a_second_disconnect_is_the_one_refusal(
    app: FastAPI, client: TestClient
) -> None:
    """The positive case first: the store is asked to mark the connection by the person, and the
    answer says the key is still in the vault. Then a source not connected, a source name that is
    not a name, and a one-source grant asking about another source are each the one refusal, and
    the malformed name reaches no store. Delete this and a disconnect can go unattributed, or
    answer differently for a source that was never connected than for one the caller may not
    touch."""
    records, vault = Records((a_connection("xero"), a_connection("hubspot"))), Vault()
    attach(app, records, vault)
    gone = post(client, "u_admin", disconnect_path("xero"))

    assert gone.status_code == 200
    assert (gone.json()["change"], gone.json()["told"]) == ("disconnected", DISCONNECTED)
    assert records.disconnects == [("xero", "u_admin")]
    asked = records.asked
    for refused in (
        post(client, "u_admin", disconnect_path("xero")),
        post(client, "u_narrow", disconnect_path("hubspot")),
        post(client, "u_none", disconnect_path("hubspot")),
        post(client, "u_admin", disconnect_path("Not-A-Name")),
    ):
        assert (refused.status_code, without_trace(refused)) == (
            404,
            {"message": Absent.public_message},
        )
    assert records.asked == asked + 1
    assert "hubspot" in records.rows and vault.written == []


# ------------------------------------------------------------------ nothing leaves the process


def test_no_response_body_and_no_log_line_carries_the_key(
    app: FastAPI,
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every answer these routes give, a body refused by its model included, read for the sentinel.
    The write is proved to have happened, so a router that stored nothing cannot pass. Delete this
    and a refused connection echoes the key it was sent."""
    caplog.set_level(logging.DEBUG)
    records, vault = Records(), Vault()
    attach(app, records, vault, Recorded())
    with structlog.testing.capture_logs() as logged:
        answers = [
            post(client, "u_admin", LISTING, connection_body()),
            post(client, "u_admin", LISTING, connection_body()),
            post(client, "u_admin", LISTING, connection_body("hubspot", settings={})),
            post(client, "u_admin", LISTING, {"connector": "hubspot", "credential": [KEY]}),
            post(client, "u_none", LISTING, connection_body("hubspot")),
            post(client, "u_admin", disconnect_path("xero")),
            get(client, "u_admin"),
        ]
    assert vault.written, "nothing was written, so the absence of the key proves nothing"
    out = capsys.readouterr()
    for answered in answers:
        assert KEY not in answered.text
        assert KEY not in json.dumps(dict(answered.headers))
    assert KEY not in out.out + out.err + caplog.text
    assert KEY not in " ".join(str(one) for one in logged)


def test_no_listing_carries_the_path_a_key_is_kept_at(app: FastAPI, client: TestClient) -> None:
    """The slot is `connector_keys/<source>`, and a console row naming it is the second place a
    path appears, which `brain.console.connector_trust.
    A_VAULT_PATH_IS_NOT_A_CREDENTIAL_AND_IS_STILL_NOT_A_CONSOLE_ROW` refuses. Delete this and a
    `slot` field arrives on a row for convenience."""
    attach(app, Records((a_connection("xero"),)), held_vault())
    with structlog.testing.capture_logs() as logged:
        answered = get(client, "u_wide")

    assert answered.status_code == 200
    assert "connector_keys" not in answered.text
    assert "connector_keys" not in " ".join(str(one) for one in logged)


# ------------------------------------------------------ the module's list and one source's page

SOURCES: Final = f"{API_PREFIX}{SOURCES_PATH}"


def source_path(name: str) -> str:
    return API_PREFIX + SOURCE_PATH.replace("{connector}", name)


def export_path(name: str) -> str:
    return API_PREFIX + EXPORT_PATH.replace("{connector}", name)


def edit_path(name: str) -> str:
    return API_PREFIX + EDIT_PATH.replace("{connector}", name)


def key_path(name: str) -> str:
    return API_PREFIX + KEY_PATH.replace("{connector}", name)


def read(c: TestClient, pid: str, path: str) -> Response:
    response: Response = c.get(path, headers=headers(pid))
    return response


class ChangingRecords(Records):
    """`Records` that also edits and keeps a history, as `StoredConnections` does."""

    def __init__(self, existing: tuple[Connection, ...] = ()) -> None:
        super().__init__(existing)
        self.ended: list[ConnectionRecord] = []
        self.edits: list[dict[str, Any]] = []

    async def reconnect(
        self,
        *,
        connector: str,
        settings: Mapping[str, str],
        digest: str,
        actor: str,
        trace_id: str,
        ent_hash: str,
        declared: Sequence[str] = (),
        agreed: str = "",
    ) -> Connection:
        old = self.rows.get(connector)
        if old is None:
            raise NotConnectedError(connector)
        self.ended.append(
            ConnectionRecord(
                connector=connector,
                settings=old.settings,
                digest=old.digest,
                connected_by=old.connected_by,
                connected_at=old.connected_at,
                disconnected_by=actor,
                disconnected_at=LONG_AGO + timedelta(days=1),
            )
        )
        made = Connection(
            connector=connector,
            settings=dict(settings),
            digest=digest,
            connected_by=actor,
            connected_at=LONG_AGO + timedelta(days=1),
            agreed=agreed,
        )
        self.rows[connector] = made
        self.edits.append({"connection": made, "declared": tuple(declared)})
        return made

    async def history(self, connector: str) -> tuple[ConnectionRecord, ...]:
        live = self.rows.get(connector)
        current = (
            ()
            if live is None
            else (
                ConnectionRecord(
                    connector=connector,
                    settings=live.settings,
                    digest=live.digest,
                    connected_by=live.connected_by,
                    connected_at=live.connected_at,
                    disconnected_by=None,
                    disconnected_at=None,
                ),
            )
        )
        return (*current, *(one for one in self.ended if one.connector == connector))


def test_the_module_lists_every_shipped_source_and_a_connection_only_adds_to_its_row(
    app: FastAPI, client: TestClient
) -> None:
    """Every declared source is a row whether or not it is connected, a connected one says so with
    its department and last read, and a failing attempt reads failing. Delete this and the list can
    show only what is connected, which is the old screen the owner found told him nothing about
    what could be connected, or draw a failing source as connected."""
    freshdesk = a_connection("freshdesk")
    attach(app, Records((a_connection("xero"), freshdesk)), held_vault())
    app.state.connector_sync_records = SyncRecords(
        {
            "xero": an_attempt("xero"),
            "freshdesk": an_attempt(
                "freshdesk", outcome=SyncOutcome.FAILED, health=HealthState.DOWN
            ),
        }
    )
    answered = read(client, "u_admin", SOURCES)

    assert answered.status_code == 200
    body = answered.json()
    rows = {one["name"]: one for one in body["items"]}
    assert set(rows) == set(shipped())
    assert (rows["xero"]["status"], rows["xero"]["health"]) == ("connected", "ok")
    assert rows["xero"]["last_read_at"] is not None and rows["xero"]["department"] is None
    assert (rows["freshdesk"]["status"], rows["freshdesk"]["department"]) == (
        "failing",
        "support",
    )
    assert rows["hubspot"]["status"] == "not_connected"
    assert (rows["hubspot"]["connect_from"], rows["lark_wiki"]["connect_from"]) == (
        "console",
        "lark",
    )
    assert rows["laravel"]["connect_from"] == "console"
    assert body["total"] is None
    narrowed = read(client, "u_admin", f"{SOURCES}?filter=status:connected").json()
    assert [one["name"] for one in narrowed["items"]] == ["xero"]


def test_a_connection_the_reader_may_not_see_reads_exactly_as_one_nobody_made(
    app: FastAPI, client: TestClient
) -> None:
    """DENIED and ABSENT, on the list, the page and the export: a reader whose grant covers only
    Xero is told HubSpot is not connected, in the same words as when it is not, with no history
    and no settings. The positive half is the same reader told about Xero. Delete this and the
    module discloses which sources a company reads to anybody holding one narrow grant."""
    hubspot = a_connection("hubspot")
    attach(app, ChangingRecords((a_connection("xero"), hubspot)), held_vault())
    connected = [
        read(client, "u_narrow", path).json()
        for path in (SOURCES, source_path("hubspot"), export_path("hubspot"))
    ]
    attach(app, ChangingRecords((a_connection("xero"),)), held_vault())
    absent = [
        read(client, "u_narrow", path).json()
        for path in (SOURCES, source_path("hubspot"), export_path("hubspot"))
    ]

    for one in (connected[2], absent[2]):
        one.pop("exported_at")
    assert connected == absent
    rows = {one["name"]: one["status"] for one in connected[0]["items"]}
    assert (rows["xero"], rows["hubspot"]) == ("connected", "not_connected")
    assert connected[1]["history"] == [] and connected[1]["settings"] == []
    xero = read(client, "u_narrow", source_path("xero")).json()
    assert xero["source"]["status"] == "connected" and xero["history"]


def test_a_source_s_page_names_what_it_keeps_and_reads_live_and_never_a_value(
    app: FastAPI, client: TestClient
) -> None:
    """The profile half: the settings under their labels, each projected entity with its field
    names, the tools it reads live with, the ceiling and how it is read. Delete this and the page
    can lose the minimal index, which is the owner's rule made visible, or draw the settings under
    their internal names."""
    attach(app, ChangingRecords((a_connection("freshdesk"),)), held_vault())
    answered = read(client, "u_admin", source_path("freshdesk"))

    assert answered.status_code == 200
    body = answered.json()
    manifest = manifest_for("freshdesk", settings_for("freshdesk"))
    assert [(one["label"], one["value"]) for one in body["settings"]] == [
        (one.label, settings_for("freshdesk")[one.name])
        for one in CONNECTABLE["freshdesk"].settings
    ]
    assert body["keeps"] == [
        {"entity": one.entity, "fields": [field.name for field in one.fields]}
        for one in manifest.projections
    ]
    assert [one["tool"] for one in body["reads_live"]] == [one.name for one in manifest.tools]
    assert body["source"]["department"] == "support" and body["department_says"] == ""
    assert "every 15 minutes" in body["reading"]
    assert body["ceiling"] and body["recorded"]
    assert body["history"][0]["connected_by"] == "u_admin"
    assert body["agents"] == [] and body["skills"] == []
    assert read(client, "u_admin", source_path("nothing_ships_this")).status_code == 404


def test_an_export_carries_the_declaration_and_history_and_no_key(
    app: FastAPI, client: TestClient
) -> None:
    """M27.15.39: the record exports with the settings, the digest agreed to, what the manifest
    declares and every connection in its history, and no key whatever the vault holds. Delete this
    and an export can drop the history, or carry the vault path a key is kept at."""
    records = ChangingRecords((a_connection("xero"),))
    vault = held_vault()
    attach(app, records, vault, Recorded())
    assert post(client, "u_admin", key_path("xero"), {"credential": KEY}).status_code == 200
    answered = read(client, "u_admin", export_path("xero"))

    assert answered.status_code == 200
    body = answered.json()
    assert body["connection"]["settings"] == settings_for("xero")
    assert body["connection"]["declaration_agreed"] is True
    assert body["declaration"]["access"] and body["declaration"]["keeps"]
    assert len(body["history"]) == 1 and body["credential"]
    assert KEY not in answered.text and "connector_keys" not in answered.text


def test_an_edit_leaves_two_rows_one_live_and_the_key_where_it_was(
    app: FastAPI, client: TestClient
) -> None:
    """W2.9's edit: new settings reach the store as one reconnection pinned to their own digest,
    with the steward's grants, and the old connection stays in the history; no key is written.
    Delete this and an edit can change the settings under the old digest, or write a key."""
    records, vault = ChangingRecords((a_connection("freshdesk"),)), held_vault()
    attach(app, records, vault, Recorded())
    changed = {**settings_for("freshdesk"), "department": "billing"}
    answered = post(client, "u_admin", edit_path("freshdesk"), {"settings": changed})

    assert answered.status_code == 200, answered.text
    assert answered.json()["told"] == EDITED
    [made] = records.edits
    assert made["connection"].settings == changed
    assert made["connection"].digest == manifest_digest(manifest_for("freshdesk", changed))
    assert made["declared"] == declared_capabilities(manifest_for("freshdesk", changed))
    history = read(client, "u_admin", source_path("freshdesk")).json()["history"]
    assert [one["disconnected_at"] is None for one in history] == [True, False]
    assert vault.written == []


def test_an_edit_is_refused_before_anything_changes_when_it_should_be(
    app: FastAPI, client: TestClient
) -> None:
    """A caller without the authority, a source not connected and a malformed name are the one
    refusal; settings the connector refuses and settings that change nothing are told as problems.
    Nothing is edited by any of them, and the positive case is the edit above. Delete this and an
    edit by the wrong person, or an edit of nothing, writes two rows."""
    records = ChangingRecords((a_connection("xero"),))
    attach(app, records, held_vault())
    same = {"settings": settings_for("xero")}
    for refused in (
        post(client, "u_none", edit_path("xero"), same),
        post(client, "u_narrow", edit_path("hubspot"), {"settings": settings_for("hubspot")}),
        post(client, "u_admin", edit_path("hubspot"), {"settings": settings_for("hubspot")}),
        post(client, "u_admin", edit_path("Not-A-Name"), same),
    ):
        assert (refused.status_code, without_trace(refused)) == (
            404,
            {"message": Absent.public_message},
        )
    unchanged = post(client, "u_admin", edit_path("xero"), same)
    wrong = post(client, "u_admin", edit_path("xero"), {"settings": {"tenant_id": "*"}})

    assert unchanged.status_code == 422
    assert [one["code"] for one in unchanged.json()["problems"]] == ["unchanged"]
    assert wrong.status_code == 422
    assert [one["field"] for one in wrong.json()["problems"]] == ["tenant_id"]
    assert records.edits == []


def test_a_replaced_key_is_a_credential_write_and_changes_no_connection(
    app: FastAPI, client: TestClient
) -> None:
    """W2.9's key replacement: the key reaches the source's own slot and is recorded as a write by
    the person, the connection is not asked to change, and the answer carries no key. A source not
    connected is the one refusal, a blank key a problem, and an install with no vault a 409.
    Delete this and a replacement can reconnect the source, or write a key for nothing."""
    records, vault, writes = ChangingRecords((a_connection("xero"),)), Vault(), Recorded()
    attach(app, records, vault, writes)
    answered = post(client, "u_admin", key_path("xero"), {"credential": KEY})

    assert answered.status_code == 200
    assert answered.json()["told"] == KEY_REPLACED
    assert vault.written == [("connector_keys/xero", {KEY_FIELD: KEY})]
    assert [(one["slot"], one["written_by"]) for one in writes.records] == [
        ("connector_keys/xero", "u_admin")
    ]
    assert records.connects == [] and records.disconnects == [] and records.edits == []
    assert KEY not in answered.text
    assert post(client, "u_admin", key_path("hubspot"), {"credential": KEY}).status_code == 404
    assert post(client, "u_none", key_path("xero"), {"credential": KEY}).status_code == 404
    blank = post(client, "u_admin", key_path("xero"), {"credential": " "})
    assert [one["code"] for one in blank.json()["problems"]] == ["blank"]
    attach(app, records, None)
    assert post(client, "u_admin", key_path("xero"), {"credential": KEY}).status_code == 409
    assert len(vault.written) == 1


def test_a_write_grants_key_goes_to_its_own_slot_and_the_screen_says_the_write_is_allowed(
    app: FastAPI, client: TestClient
) -> None:
    """**A write is a grant of its own (M11.7.3).** The key route naming Cloudflare's DNS change
    grant keeps the key in that grant's slot and never the read key's, recorded as a credential
    write by the person, and says the write is now allowed; a grant the source does not declare is
    a problem on the field, and nothing is written. The screen lists the grant on the form and says
    which grants this install has given: none while the slot is empty, this one once it holds a
    key. Delete this and the second key can land in the read key's slot, or the screen can say a
    write is allowed that is not."""
    records, vault, writes = ChangingRecords((a_connection("cloudflare"),)), Vault(), Recorded()
    attach(app, records, vault, writes)
    body = {"credential": KEY, "grant": "dns_changes"}

    answered = post(client, "u_admin", key_path("cloudflare"), body)
    unknown = post(client, "u_admin", key_path("cloudflare"), {**body, "grant": "zone_changes"})

    assert answered.status_code == 200, answered.text
    assert answered.json()["told"] == WRITE_ALLOWED
    assert vault.written == [("connector_keys/cloudflare_dns_changes", {KEY_FIELD: KEY})]
    assert [one["slot"] for one in writes.records] == ["connector_keys/cloudflare_dns_changes"]
    assert unknown.status_code == 422
    assert [(one["field"], one["code"], one["message"]) for one in unknown.json()["problems"]] == [
        ("grant", "unknown", NO_SUCH_WRITE)
    ]
    assert len(vault.written) == 1 and KEY not in answered.text
    form = next(
        one for one in get(client, "u_admin").json()["connectable"] if one["name"] == "cloudflare"
    )
    assert [one["name"] for one in form["writes"]] == ["dns_changes"]
    assert "DNS Edit" in form["writes"][0]["credential_hint"]
    assert form["writes"][0]["confirmation"] == ALLOWING_A_WRITE
    empty = next(
        one for one in get(client, "u_admin").json()["connectors"] if one["name"] == "cloudflare"
    )
    attach(app, records, held_vault())
    held = next(
        one for one in get(client, "u_admin").json()["connectors"] if one["name"] == "cloudflare"
    )
    assert (empty["writes_allowed"], held["writes_allowed"]) == ([], ["dns_changes"])


# ------------------------------------------------------------------ testing a connection


class Probes:
    """`brain.ops.connector_sync_store.ConnectorProbes` in memory, noting every press."""

    def __init__(self) -> None:
        self.asks: list[tuple[str, datetime, str]] = []
        self.last: ProbeRecord | None = None

    async def ask(
        self, connector: str, *, at: datetime, by: str, trace_id: str, ent_hash: str
    ) -> None:
        self.asks.append((connector, at, by))

    async def status(self, connector: str) -> ProbeStatus:
        asked = [one[1] for one in self.asks if one[0] == connector]
        return ProbeStatus(requested_at=asked[-1] if asked else None, last=self.last)


def probe_path(name: str) -> str:
    return API_PREFIX + PROBE_PATH.replace("{connector}", name)


def probe_state_path(name: str) -> str:
    return API_PREFIX + PROBE_STATE_PATH.replace("{connector}", name)


def test_an_administrator_asks_for_a_test_and_is_told_it_waits_for_the_worker(
    app: FastAPI, client: TestClient
) -> None:
    """**The console's half of M27.15.8.** A press by somebody who may manage the source writes the
    request under their name and answers that the worker has it, with the words the confirmation
    agreed to. Delete this and the button writes nothing the worker reads, or writes it as
    nobody."""
    probes = Probes()
    attach(app, Records((a_connection("xero"),)), held_vault())
    app.state.connector_probes = probes
    answered = post(client, "u_admin", probe_path("xero"))

    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert (body["pending"], body["verdict"], body["said"]) == (True, None, TEST_WAITING)
    assert body["confirm"] == TESTING_A_SOURCE
    assert [(one[0], one[2]) for one in probes.asks] == [("xero", "u_admin")]
    assert "u_admin" not in answered.text


def test_a_test_is_refused_before_anything_is_asked_when_it_should_be(
    app: FastAPI, client: TestClient, hubspot_unmeasured: None
) -> None:
    """A caller who may not manage the source, a source not connected and a name that is not a
    source are the one refusal; a source whose plan refuses it is a problem in the plan's own words.
    Nothing is asked by any of them. Delete this and a reader can spend a source's allowance, or a
    test waits for ever on a source the worker will never call."""
    probes = Probes()
    attach(app, Records((a_connection("xero"), a_connection("hubspot"))), held_vault())
    app.state.connector_probes = probes
    for refused in (
        post(client, "u_wide", probe_path("xero")),
        post(client, "u_narrow", probe_path("hubspot")),
        post(client, "u_admin", probe_path("freshdesk")),
        post(client, "u_admin", probe_path("lark-app")),
    ):
        assert (refused.status_code, without_trace(refused)) == (
            404,
            {"message": Absent.public_message},
        )
    unverified = post(client, "u_admin", probe_path("hubspot"))

    assert unverified.status_code == 422
    assert [(one["code"], one["message"]) for one in unverified.json()["problems"]] == [
        ("not_testable", NO_VERIFIED_CEILING)
    ]
    assert probes.asks == []


def test_how_a_test_went_is_read_by_a_reader_of_the_source_and_by_nobody_else(
    app: FastAPI, client: TestClient
) -> None:
    """The finding is the source's health, so a reader of the screen told of the connection reads
    it; a reader it is hidden from is answered as for a source nobody connected. Delete this and a
    test's finding is hidden from the people the page is for, or tells somebody a source exists."""
    probes = Probes()
    probes.last = ProbeRecord(
        started_at=LONG_AGO, finished_at=LONG_AGO, health="down", detail=KEY_DECLINED
    )
    attach(app, Records((a_connection("xero"), a_connection("hubspot"))), held_vault())
    app.state.connector_probes = probes
    wide = read(client, "u_wide", probe_state_path("xero"))

    assert wide.status_code == 200, wide.text
    assert (wide.json()["verdict"], wide.json()["health"], wide.json()["said"]) == (
        "failed",
        "down",
        KEY_DECLINED,
    )
    hidden = read(client, "u_narrow", probe_state_path("hubspot"))
    nobody = read(client, "u_wide", probe_state_path("freshdesk"))
    outside = read(client, "u_none", probe_state_path("xero"))
    for refused in (hidden, nobody, outside):
        assert (refused.status_code, without_trace(refused)) == (
            404,
            {"message": Absent.public_message},
        )


def test_the_test_route_leaves_connect_larks_own_test_to_connect_lark() -> None:
    """Connect Lark's router answers `POST /connectors/lark-app/test` and is registered after this
    one, so a route here matching that address would answer it first. Delete this and the next
    rename of the probe path to `/test` breaks Connect Lark's test with every connector test
    green."""
    from starlette.routing import Match

    from brain.connector_routes import router

    scope = {"type": "http", "path": f"{API_PREFIX}/connectors/lark-app/test", "method": "POST"}
    assert [one for one in router.routes if one.matches(scope)[0] is not Match.NONE] == []
    probing = {"type": "http", "path": probe_path("xero"), "method": "POST"}
    assert [one for one in router.routes if one.matches(probing)[0] is Match.FULL]


# ------------------------------------------------------------------ a changed declaration


def an_older_xero() -> tuple[str, str, str]:
    """Xero as an earlier release declared it, one field fewer kept in its index: the text agreed,
    its digest, and the field this release added. Built from this release's own manifest, so the
    field is one Xero really keeps."""
    import dataclasses

    from brain.connectors.manifest import digest_input

    current = manifest_for("xero", settings_for("xero"))
    entity = current.projections[0]
    dropped = entity.fields[-1]
    older = dataclasses.replace(
        current,
        version="0.9.0",
        projections=(
            dataclasses.replace(entity, fields=entity.fields[:-1]),
            *current.projections[1:],
        ),
    )
    return digest_input(older), manifest_digest(older), f"a {entity.entity}'s {dropped.name}"


def drift_path(name: str) -> str:
    return API_PREFIX + DRIFT_PATH.replace("{connector}", name)


def accept_path(name: str) -> str:
    return API_PREFIX + ACCEPT_PATH.replace("{connector}", name)


def an_agreed_connection(agreed: str, digest: str) -> Connection:
    return dataclasses.replace(a_connection("xero", digest=digest), agreed=agreed)


def test_the_diff_names_a_field_the_new_declaration_keeps(app: FastAPI, client: TestClient) -> None:
    """A connection agreed when Xero kept one field fewer is told, in words, that the index now
    keeps that field, and which versions are compared. Delete this and a person accepts a change
    they were never shown, which is the gap the pill alone left."""
    agreed, digest, field = an_older_xero()
    field_words = field.replace("_", " ")
    attach(app, ChangingRecords((an_agreed_connection(agreed, digest),)), held_vault())
    answered = read(client, "u_admin", drift_path("xero")).json()
    assert answered["changed"] is True and answered["known"] is True
    assert {"kind": "added", "what": f"Now also keeps in its index: {field_words}", "was": ""} in (
        answered["lines"]
    )
    assert answered["was_version"] == "0.9.0" and answered["now_version"] != "0.9.0"
    assert answered["agreed_digest"] == digest
    assert answered["current_digest"] == manifest_digest(manifest_for("xero", settings_for("xero")))
    assert answered["may_accept"] is True and answered["confirm"]


def test_an_agreed_text_that_does_not_hash_to_the_pin_is_not_believed(
    app: FastAPI, client: TestClient
) -> None:
    """A row whose kept text is not the declaration its digest names, or keeps none, cannot say
    what changed, and the screen lists everything the declaration does now instead. Delete this
    and a row edited by hand puts words in front of the person about to accept."""
    agreed, digest, _ = an_older_xero()
    forged = agreed.replace("0.9.0", "0.9.1")
    attach(app, ChangingRecords((an_agreed_connection(forged, digest),)), held_vault())
    answered = read(client, "u_admin", drift_path("xero")).json()
    assert answered["changed"] is True and answered["known"] is False
    assert answered["lines"] == [] and answered["now_does"]
    current = manifest_for("xero", settings_for("xero"))
    assert current.tools[0].description in answered["now_does"]


def test_an_unchanged_connection_shows_no_pill_and_no_diff(
    app: FastAPI, client: TestClient
) -> None:
    """The positive case: a connection agreed under this release's declaration is not marked and
    has nothing to accept. Delete this and every connected source shows a change, which teaches
    people to accept without reading."""
    attach(app, ChangingRecords((a_connection("xero"),)), held_vault())
    answered = read(client, "u_admin", drift_path("xero")).json()
    assert answered["changed"] is False and answered["lines"] == [] and not answered["may_accept"]
    [row] = [
        one
        for one in read(client, "u_admin", f"{API_PREFIX}{SOURCES_PATH}").json()["items"]
        if one["name"] == "xero"
    ]
    assert row["declaration_changed"] is False


def test_accepting_repins_the_declaration_and_the_source_is_read_again(
    app: FastAPI, client: TestClient
) -> None:
    """The accept names the digest shown, connects the source again with its own settings under
    this release's declaration and keeps the text agreed; the pill goes and the scheduled read's
    plan no longer refuses it. Delete this and accepting a change leaves the source unread, or
    pins something other than what was shown."""
    from brain.connectors.manifest import digest_input
    from brain.ops.connector_sync import DECLARATION_NOT_AGREED, plan_for

    agreed, digest, _ = an_older_xero()
    records = ChangingRecords((an_agreed_connection(agreed, digest),))
    attach(app, records, held_vault())
    before = records.rows["xero"]
    assert plan_for(before, last=None, now=AT).refused == DECLARATION_NOT_AGREED
    shown = read(client, "u_admin", drift_path("xero")).json()["current_digest"]
    answered = post(client, "u_admin", accept_path("xero"), {"digest": shown})
    assert answered.status_code == 200 and answered.json()["digest"] == shown
    after = records.rows["xero"]
    current = manifest_for("xero", settings_for("xero"))
    assert (after.digest, after.settings, after.agreed) == (
        shown,
        before.settings,
        digest_input(current),
    )
    assert records.ended[-1].digest == digest
    assert plan_for(after, last=None, now=AT).refused != DECLARATION_NOT_AGREED
    assert read(client, "u_admin", drift_path("xero")).json()["changed"] is False


def test_an_accept_naming_another_digest_or_nothing_changed_is_refused(
    app: FastAPI, client: TestClient
) -> None:
    """An accept must name the declaration the reader was shown; a release landing in between is
    refused by field, and an accept with nothing changed says so. Delete this and a change can be
    accepted by a person who read a different one."""
    agreed, digest, _ = an_older_xero()
    records = ChangingRecords((an_agreed_connection(agreed, digest),))
    attach(app, records, held_vault())
    moved = post(client, "u_admin", accept_path("xero"), {"digest": "f" * 64})
    assert moved.status_code == 422
    assert [one["field"] for one in moved.json()["problems"]] == ["digest"]
    assert records.edits == []
    same = ChangingRecords((a_connection("xero"),))
    attach(app, same, held_vault())
    current = manifest_digest(manifest_for("xero", settings_for("xero")))
    unchanged = post(client, "u_admin", accept_path("xero"), {"digest": current})
    assert unchanged.status_code == 422 and same.edits == []


def test_a_reader_without_the_install_authority_sees_the_diff_and_cannot_accept(
    app: FastAPI, client: TestClient
) -> None:
    """u_wide reads the Connectors screen and holds no installation authority: they are shown the
    pill and what changed, offered no accept, and refused one in the one way this router refuses.
    Delete this and anybody who can read the screen can agree a source to a new declaration."""
    agreed, digest, field = an_older_xero()
    records = ChangingRecords((an_agreed_connection(agreed, digest),))
    attach(app, records, held_vault())
    answered = read(client, "u_wide", drift_path("xero")).json()
    assert answered["changed"] is True and answered["may_accept"] is False
    assert any(field.replace("_", " ") in one["what"] for one in answered["lines"])
    refused = post(client, "u_wide", accept_path("xero"), {"digest": answered["current_digest"]})
    assert refused.status_code == 404 and records.edits == []


def test_connecting_and_editing_keep_the_declaration_text_the_digest_is_taken_over(
    app: FastAPI, client: TestClient
) -> None:
    """Every row written from now on keeps what it agreed to, so the next release can say what
    changed. Delete this and the drift view can never be anything but "not kept"."""
    import hashlib

    records = ChangingRecords()
    attach(app, records, held_vault())
    assert post(client, "u_admin", LISTING, connection_body()).status_code == 200
    made = records.rows["xero"]
    assert hashlib.sha256(made.agreed.encode("utf-8")).hexdigest() == made.digest
