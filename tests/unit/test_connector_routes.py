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

Task ids: M42.6.5
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.connector_routes import (
    CONNECTORS_PATH,
    CONNECTORS_READ,
    DISCONNECT_PATH,
    ConnectorsView,
)
from brain.connectors.contract import HealthState
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
from brain.ops.connectable import CONNECTABLE, NOT_FROM_THE_CONSOLE, manifest_for
from brain.ops.connector_admin import (
    CONNECTED,
    CONNECTING_A_SOURCE,
    DISCONNECTED,
    DISCONNECTING_A_SOURCE,
    TOLD,
    VAULT_SAYS,
    WHAT_CONNECTING_A_SOURCE_STARTS,
)
from brain.ops.connector_recordings import recorded_in_words
from brain.ops.connector_store import Connection, ConnectorTakenError, NotConnectedError
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
    """The settings a connectable source takes, and none for a source the console cannot connect."""
    if name not in CONNECTABLE:
        return {}
    return {CONNECTABLE[name].settings[0].name: IDENTIFIERS[name]}


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


def attach(
    app: FastAPI, records: Records | None, vault: Vault | None, writes: Recorded | None = None
) -> None:
    if records is not None:
        app.state.connector_records = records
    app.state.credentials = Credentials(vault, environ={}, writes=writes)


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
    app: FastAPI, client: TestClient
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
    assert narrow["hubspot"] == narrow["freshdesk"] | {
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
        post(client, "u_narrow", LISTING, connection_body("freshdesk")),
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
    unknown = post(client, "u_admin", LISTING, connection_body("freshdesk"))
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
