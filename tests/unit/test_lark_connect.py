"""Connect Lark: the scopes each use asks for, a test that only reads, a save that copies nothing.

The Lark side is a real HTTP server on the loopback address (`FakeLark`), answering the paths the
test calls with Lark's documented envelopes and recording every request's method and path, and
the real `brain.ops.staff_sync_run.http_fetch` sends to it. So "the test only reads" is asserted
over the requests a server actually received, not over what the module meant to send.

The routes are driven through the real application with the token machinery of
`tests/unit/test_api_routes.py`, the vault of `tests/unit/test_credentials.py` and an in-memory
settings writer, for `tests/unit/test_connector_routes.py`'s reasons.

Task ids: M11.9.4, M11.9.1
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Final, cast
from urllib.parse import parse_qs, urlsplit

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.api_routes import Asking
from brain.app import Settings, create_app
from brain.channels.lark import LarkSecret
from brain.connector_routes import CONNECTORS_READ
from brain.connectors import lark_wiki
from brain.connectors.registry import INSTALL_AUTHORITY
from brain.connectors.staff_directories import LARK_SCOPE_PURPOSE, LARK_SYNC_SCOPES
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.credential_routes import CREDENTIAL_AUTHORITY
from brain.gate.context import Channel
from brain.install import BY_NAME, hold_saved
from brain.lark_connect_routes import (
    EVENTS_ARRIVING,
    EVENTS_NONE_YET,
    EVENTS_OFF,
    LARK_PATH,
    LARK_SWITCH_OFF_PATH,
    LARK_TEST_PATH,
    REFUSED_EVENT_TOLD,
    REPLY_TOLD,
    LarkFacts,
)
from brain.ops.channel_store import DeliveryEntry
from brain.ops.connectable import CONNECTABLE, NotConnectableError, manifest_for
from brain.ops.connector_slots import SLOT_SCOPES
from brain.ops.credentials import KEY_FIELD, Credentials
from brain.ops.lark_connect import (
    MEMBERS_SCOPE,
    MESSAGE_EVENT,
    USES,
    WIKI_PERMISSION_SCOPE,
    StepKey,
    Use,
    UseResult,
    Verdict,
    app_page,
    base_token,
    events_address,
    last_test_from,
    probe_connection,
    redo_for,
    scope_import,
    scopes_for,
    settings_for,
    steps_for,
)
from brain.ops.staff_sync_run import CLIENT_CREDENTIAL_SEPARATOR, http_fetch
from brain.tables.channel import DeliveryOutcome, Direction, RefusedBecause
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
from tests.unit.test_channel_pipeline import Deliveries, Records
from tests.unit.test_credentials import Recorded, Vault

APP_ID: Final = "cli_a1b2c3d4e5f6"
#: A secret nothing else in any output could contain, so finding it anywhere is a leak.
SECRET: Final = "LARK-SECRET-SENTINEL-51d9"
TOKEN: Final = "t-tenant-token-fake"
#: The chat channel's two event keys, sentinels for the same reason as `SECRET`.
ENCRYPT_KEY: Final = "LARK-ENCRYPT-SENTINEL-7c2e"
VERIFY_TOKEN: Final = "LARK-VERIFY-SENTINEL-0b4a"
BASE: Final = "bascnFAKE0123456789"
SECOND_FACTOR: Final[Mapping[str, object]] = {"amr": ["otp"]}


# ------------------------------------------------------------------ a fake Lark


class FakeLark:
    """A loopback HTTP server answering Lark's paths, recording every request it receives.

    `refuse` maps a path prefix to the envelope that path answers instead of success, so a test
    can withhold one scope and keep the rest working.
    """

    def __init__(self) -> None:
        self.seen: list[tuple[str, str, bytes]] = []
        self.refuse: dict[str, dict[str, Any]] = {}
        #: The HTTP status a refused prefix answers with, 200 unless named: Lark refuses most
        #: calls inside a 200 and a department outside the data range with a 403.
        self.refuse_status: dict[str, int] = {}
        self.accept_secret = SECRET
        self.empty_directory = False
        #: False for an app without `contact:department.base:readonly`, which Lark answers by
        #: leaving each department's `name` out of an otherwise successful walk.
        self.department_names = True
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                return

            def _answer(self, body: Mapping[str, Any], status: int = 200) -> None:
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                fake.seen.append(("POST", self.path, body))
                if self.path == "/open-apis/auth/v3/tenant_access_token/internal":
                    sent = json.loads(body or b"{}")
                    if sent.get("app_secret") == fake.accept_secret:
                        self._answer({"code": 0, "tenant_access_token": TOKEN, "expire": 7200})
                    else:
                        self._answer({"code": 10014, "msg": "app secret invalid"})
                    return
                self._answer({"code": 404, "msg": "no such path"}, 404)

            def do_GET(self) -> None:
                fake.seen.append(("GET", self.path, b""))
                path = urlsplit(self.path).path
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    self._answer({"code": 99991663, "msg": "invalid tenant token"})
                    return
                for prefix, envelope in fake.refuse.items():
                    if path.startswith(prefix):
                        self._answer(envelope, fake.refuse_status.get(prefix, 200))
                        return
                self._answer(fake.success(path))

            def do_PUT(self) -> None:
                fake.seen.append(("PUT", self.path, b""))
                self._answer({"code": 0})

            def do_DELETE(self) -> None:
                self.do_PUT()

            def do_PATCH(self) -> None:
                self.do_PUT()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host!s}:{port}"

    def success(self, path: str) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        if path.endswith("/users/find_by_department"):
            items = [] if self.empty_directory else [{"union_id": "on_1", "name": "A"}]
        elif path.endswith("/departments/0/children"):
            department = {"open_department_id": "od_1", "name": "Operations"}
            if not self.department_names:
                del department["name"]
            items = [] if self.empty_directory else [department]
        elif path == "/open-apis/wiki/v2/spaces":
            items = [{"space_id": "7000000000000000001"}]
        elif path.endswith("/nodes"):
            items = [{"node_token": "wikcnNODE1", "obj_token": "doxcnDOC1", "obj_type": "docx"}]
        elif path.endswith("/tables"):
            items = [{"table_id": "tbl1"}]
        elif path == "/open-apis/bot/v3/info":
            return {"code": 0, "bot": {"app_name": "Brain", "open_id": "ou_bot"}}
        elif path.endswith("/members"):
            items = [{"member_type": "openchat"}]
        return {"code": 0, "data": {"items": items, "has_more": False}}

    def start(self) -> FakeLark:
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def lark() -> Iterator[FakeLark]:
    fake = FakeLark().start()
    yield fake
    fake.stop()


def missing(*scopes: str) -> dict[str, Any]:
    """Lark's refusal for a token without a scope, naming the scopes that would admit the call."""
    return {
        "code": 99991672,
        "msg": f"Access denied. One of the following scopes is required: [{', '.join(scopes)}].",
    }


def probe(lark: FakeLark, *uses: Use, secret: str = SECRET) -> Any:
    return asyncio.run(
        probe_connection(
            http_fetch,
            platform="larksuite.com",
            app_id=APP_ID,
            app_secret=secret,
            uses=uses,
            base_link=f"https://example.invalid/base/{BASE}?table=tbl1",
            open_base=lark.base,
        )
    )


# ------------------------------------------------------------------ the scopes


def test_each_use_asks_for_the_scopes_its_reader_was_written_against() -> None:
    """The staff list's scopes are the staff reader's own constant, the Wiki's include the page
    permission read, and Base and Wiki cover what their vault slots are defined with. Delete this
    and the screen can ask for a scope set that no reader in the product uses."""
    names = {use: {one.name for one in USES[use].scopes} for use in Use}
    assert names[Use.STAFF_LIST] == set(LARK_SYNC_SCOPES.split())
    assert set(LARK_SCOPE_PURPOSE) == set(LARK_SYNC_SCOPES.split())
    assert WIKI_PERMISSION_SCOPE in names[Use.WIKI]
    assert "docs:permission.member:retrieve" not in names[Use.WIKI]
    assert set(SLOT_SCOPES["lark_wiki"].request) <= names[Use.WIKI]
    assert set(SLOT_SCOPES["lark_base"].request) <= names[Use.BASE]
    assert USES[Use.WIKI].slot == lark_wiki.LARK_WIKI
    assert USES[Use.BASE].slot == "lark_base"


def test_every_scope_only_reads_except_the_bots_own_replies() -> None:
    """The one scope that writes is named and is the channel's. Delete this and a write scope can
    be added to any use and shown to the owner as read-only."""
    writes = [one.name for use in Use for one in USES[use].scopes if not one.read_only]
    assert writes == ["im:message:send_as_bot"]
    assert all(":write" not in one.name for use in Use for one in USES[use].scopes)


def test_the_scope_list_and_the_steps_follow_the_uses_chosen() -> None:
    """Choosing only the staff list asks for no wiki, Base or chat scope; adding the Wiki adds its
    scopes and its sharing step. Delete this and every company is asked to grant everything."""
    staff = {one.name for one in scopes_for([Use.STAFF_LIST])}
    assert staff == set(LARK_SYNC_SCOPES.split())
    both = {one.name for one in scopes_for([Use.STAFF_LIST, Use.WIKI])}
    assert both == staff | {one.name for one in USES[Use.WIKI].scopes}
    staff_steps = steps_for([Use.STAFF_LIST], platform="larksuite.com")
    assert [one.key for one in staff_steps] == [
        StepKey.CHOOSE,
        StepKey.CREATE,
        StepKey.CREDENTIALS,
        StepKey.PERMISSIONS,
        StepKey.RELEASE,
        StepKey.TEST,
    ]
    (permissions,) = [one for one in staff_steps if one.key == StepKey.PERMISSIONS]
    assert "All members" in permissions.text and "scopes" in permissions.asks
    keys = [one.key for one in steps_for([Use.WIKI, Use.CHANNEL], platform="feishu.cn")]
    assert StepKey.SHARE_WIKI in keys and StepKey.BOT in keys and StepKey.SHARE_BASE not in keys
    create = steps_for([Use.WIKI], platform="feishu.cn")[1]
    assert create.link == "https://open.feishu.cn/app"


def test_the_events_address_is_built_from_the_installs_own_redirect_uri() -> None:
    """The channel's address comes from configuration, and no address is invented without it.
    Delete this and the step can show an address that points at nobody's install."""
    assert events_address("https://brain.example.test/cb, https://x.test/y") == (
        "https://brain.example.test/api/v1/channels/lark/events"
    )
    assert events_address("") == ""
    assert events_address("not a url") == ""


def test_a_base_token_is_read_from_a_link_or_given_bare_and_nothing_else_is() -> None:
    """Delete this and a pasted link with a query is refused, or a word is taken as a Base."""
    assert base_token(f"https://x.larksuite.com/base/{BASE}?table=tbl1&view=v") == BASE
    assert base_token(BASE) == BASE
    assert base_token("https://x.larksuite.com/wiki/abc") == ""
    assert base_token("all") == ""


# ------------------------------------------------------------------ the test only reads


def test_a_working_app_is_reported_working_for_every_use_and_only_reads(lark: FakeLark) -> None:
    """The positive case: every use works, and every request the server received after the one
    token exchange was a GET. Delete this and the test can write to Lark, or a working app can be
    reported broken, and nothing notices."""
    result = probe(lark, *Use)
    assert result.token_ok
    assert {one.use: one.verdict for one in result.uses} == dict.fromkeys(Use, Verdict.WORKING)
    methods = [(method, urlsplit(path).path) for method, path, _ in lark.seen]
    assert methods[0] == ("POST", "/open-apis/auth/v3/tenant_access_token/internal")
    assert [method for method, _ in methods[1:]] == ["GET"] * (len(methods) - 1)
    assert len(methods) > len(Use)
    for _, path, _ in lark.seen[1:]:
        query = parse_qs(urlsplit(path).query)
        assert query.get("page_size", ["1"]) == ["1"]
    assert not any("raw_content" in path for _, path, _ in lark.seen)


def test_a_refused_secret_tries_no_use(lark: FakeLark) -> None:
    """Delete this and a wrong secret is reported per use as missing scopes, sending the person to
    the wrong page."""
    result = probe(lark, Use.STAFF_LIST, Use.WIKI, secret="wrong-secret")
    assert not result.token_ok and result.uses == ()
    assert "App ID and App Secret" in result.told
    assert [method for method, _, _ in lark.seen] == ["POST"]


def test_a_missing_scope_is_named_by_its_exact_name(lark: FakeLark) -> None:
    """Lark's refusal is read and the use's own missing scope is named, while a use that works
    stays working. Delete this and the person is told something is wrong without being told what."""
    lark.refuse["/open-apis/contact/v3/"] = missing("contact:user.email:readonly")
    result = probe(lark, Use.STAFF_LIST, Use.BASE)
    staff, base = result.uses
    assert staff.verdict is Verdict.MISSING_SCOPE
    assert staff.missing == ("contact:user.email:readonly",)
    assert "contact:user.email:readonly" in staff.told
    assert "Version Management & Release" in staff.told
    assert base.verdict is Verdict.WORKING


def test_a_scope_named_by_lark_that_the_use_does_not_need_is_not_passed_on(lark: FakeLark) -> None:
    """Only the use's own scopes are named, so a refusal cannot send somebody to grant a write.
    Delete this and whatever Lark's message lists becomes advice."""
    lark.refuse["/open-apis/bitable/"] = missing("bitable:app")
    (base,) = probe(lark, Use.BASE, Use.STAFF_LIST).uses[1:]
    assert base.verdict is Verdict.MISSING_SCOPE
    assert set(base.missing) == {one.name for one in USES[Use.BASE].scopes}
    assert "bitable:app," not in base.told and "bitable:app " not in base.told


def test_the_page_permission_scope_is_named_when_only_it_is_missing(lark: FakeLark) -> None:
    """The listing works and the permission settings read is refused: the sentence names exactly
    docs:permission.setting:read, the scope `lark_wiki.read_live` reads a page's lock with.
    Delete this and the scope item 81 was about goes unnamed."""
    lark.refuse["/open-apis/drive/v2/permissions/"] = missing("docs:permission.setting:read")
    (wiki, staff) = probe(lark, Use.STAFF_LIST, Use.WIKI).uses[::-1]
    assert wiki.verdict is Verdict.MISSING_SCOPE
    assert wiki.missing == ("docs:permission.setting:read",)
    assert WIKI_PERMISSION_SCOPE == "docs:permission.setting:read"
    assert staff.verdict is Verdict.WORKING


def test_nothing_granted_at_all_reads_as_a_version_not_released(lark: FakeLark) -> None:
    """Delete this and an unreleased app is reported as a list of scopes to add that were added."""
    for prefix in ("/open-apis/contact/", "/open-apis/wiki/"):
        lark.refuse[prefix] = missing()
    result = probe(lark, Use.STAFF_LIST, Use.WIKI)
    assert [one.verdict for one in result.uses] == [Verdict.NOT_RELEASED] * 2
    assert "Version Management & Release" in result.uses[0].told
    assert "contact:user.base:readonly" in result.uses[0].told


def test_a_directory_the_app_cannot_see_asks_for_the_data_range(lark: FakeLark) -> None:
    """Delete this and an app whose contacts range is empty is reported working over nobody."""
    lark.empty_directory = True
    (staff,) = probe(lark, Use.STAFF_LIST).uses
    assert staff.verdict is Verdict.NOT_SHARED
    assert "All members" in staff.told


def test_an_app_that_reads_departments_without_their_names_is_told_the_scope_that_shows_them(
    lark: FakeLark,
) -> None:
    """Lark admits the department walk without `contact:department.base:readonly` and leaves out
    each name, so the call succeeds and the sync places nobody: the owner's install, 2026-09-29,
    which this test called working because it had read one person. Delete this and the test goes
    back to passing an app one scope short. The positive case is the working app above."""
    lark.department_names = False
    (staff,) = probe(lark, Use.STAFF_LIST).uses
    assert staff.verdict is Verdict.MISSING_SCOPE
    assert staff.missing == ("contact:department.base:readonly",)
    assert "contact:department.base:readonly" in staff.told


def test_a_department_walk_the_range_refuses_is_the_data_range_even_when_a_person_was_read(
    lark: FakeLark,
) -> None:
    """The owner's first sync met "no dept authority" on the department walk while the root could
    list people, and this test had already said working. The walk is the sync's first call, so a
    refusal there is the data range. Delete this and a test passes an app the night's run fails."""
    refused = "/open-apis/contact/v3/departments/"
    lark.refuse[refused] = {"code": 40004, "msg": "no dept authority error"}
    lark.refuse_status[refused] = 403
    (staff,) = probe(lark, Use.STAFF_LIST).uses
    assert staff.verdict is Verdict.NOT_SHARED
    assert "All members" in staff.told


def test_a_base_not_shared_with_the_app_says_to_add_the_app(lark: FakeLark) -> None:
    """Delete this and a Base nobody shared reads as a missing scope."""
    lark.refuse["/open-apis/bitable/"] = {"code": 91403, "msg": "Forbidden"}
    (base,) = probe(lark, Use.BASE).uses
    assert base.verdict is Verdict.NOT_SHARED
    assert "Add document app" in base.told


# ------------------------------------------------------------------ the routes

WHOLE: Final = Scope.unrestricted()
PLANE: Final = Grant(capability=plane_capability(Plane.CONTENT), scope=WHOLE)
WIKI_ONLY: Final = Scope(clauses=(Clause(field="connector", op=Op.EQ, value="lark_wiki"),))
GRANTS: Final[dict[str, tuple[Grant, ...]]] = {
    "u_admin": (
        PLANE,
        Grant(capability=CONNECTORS_READ, scope=WHOLE),
        Grant(capability=INSTALL_AUTHORITY, scope=WHOLE),
        Grant(capability=CREDENTIAL_AUTHORITY, scope=WHOLE),
    ),
    "u_narrow": (
        PLANE,
        Grant(capability=CONNECTORS_READ, scope=WHOLE),
        Grant(capability=INSTALL_AUTHORITY, scope=WIKI_ONLY),
    ),
    "u_none": (PLANE,),
}


class HeldGrants:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


class StoredValues:
    """The settings writer in memory: every save's values, in order."""

    def __init__(self) -> None:
        self.saved: list[dict[str, str]] = []

    async def save(self, values: dict[str, str], asked: Asking) -> None:
        self.saved.append(dict(values))


class KeptFacts:
    """The App ID and the last test in memory: every keep, in order, and what a read answers."""

    def __init__(self) -> None:
        self.facts = LarkFacts()
        self.kept: list[dict[str, object]] = []

    async def read(self) -> LarkFacts:
        return self.facts

    async def keep(
        self, *, app_id: str | None, last_test: dict[str, object] | None, asked: Asking
    ) -> None:
        self.kept.append({"app_id": app_id, "last_test": last_test})
        self.facts = LarkFacts(
            app_id=self.facts.app_id if app_id is None else app_id,
            last_test=self.facts.last_test if last_test is None else last_test_from(last_test),
        )


class NeverAsked:
    """Stands where the connector rows and the database would be; asking it fails the test."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"Connect Lark touched {name}: it must register no connection")

    def __call__(self) -> Any:
        raise AssertionError("Connect Lark opened a database session")


@pytest.fixture
def app() -> Iterator[FastAPI]:
    built: FastAPI = create_app(Settings(env="development"))
    before = hold_saved({})
    yield built
    hold_saved(before)


@pytest.fixture
def client(app: FastAPI, lark: FakeLark) -> Iterator[TestClient]:
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=HeldGrants(),
            cache=NoCache(),
        )
        app.state.db_sessions = NeverAsked()
        app.state.connector_records = NeverAsked()
        app.state.lark_open_base = lark.base
        app.state.lark_settings = StoredValues()
        app.state.lark_facts = KeptFacts()
        # The chat channel's own record and deliveries, in memory: a save writes the one and
        # the card reads the other.
        app.state.channel_records = Records()
        app.state.channel_deliveries = Deliveries()
        yield c


def headers(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"}


def body(*uses: Use, secret: str = SECRET) -> dict[str, object]:
    return {
        "app_id": APP_ID,
        "app_secret": secret,
        "uses": [use.value for use in uses],
        "platform": "larksuite.com",
        "base_link": f"https://example.invalid/base/{BASE}",
        "encrypt_key": ENCRYPT_KEY,
        "verification_token": VERIFY_TOKEN,
    }


def test_the_guide_follows_the_uses_asked_about(client: TestClient) -> None:
    """Delete this and the console must hold its own copy of the scope list."""
    staff = client.get(f"{API_PREFIX}{LARK_PATH}?uses=staff_list", headers=headers("u_narrow"))
    assert staff.status_code == 200
    names = {one["name"] for one in staff.json()["scopes"]}
    assert names == set(LARK_SYNC_SCOPES.split())
    wiki = client.get(f"{API_PREFIX}{LARK_PATH}?uses=knowledge_wiki", headers=headers("u_narrow"))
    assert "docs:permission.setting:read" in {one["name"] for one in wiki.json()["scopes"]}
    mine = {one["name"]: one["may_switch_on"] for one in wiki.json()["uses"]}
    assert mine == {
        "staff_list": False,
        "knowledge_wiki": True,
        "knowledge_base": False,
        "chat_channel": False,
    }


def test_a_reader_of_no_screen_is_refused_the_guide(client: TestClient) -> None:
    """Delete this and the guide, with which uses are on, is served to anybody signed in."""
    assert client.get(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_none")).status_code == 404


def test_the_test_route_reports_each_use_and_writes_nothing(
    app: FastAPI, client: TestClient, lark: FakeLark
) -> None:
    """Through the application: verdicts per use, nothing kept, nothing saved. Delete this and the
    route can store what it was sent to test."""
    vault = Vault()
    app.state.credentials = Credentials(vault, environ={}, writes=Recorded())
    lark.refuse["/open-apis/im/v1/chats"] = missing(MEMBERS_SCOPE)
    answered = client.post(
        f"{API_PREFIX}{LARK_TEST_PATH}",
        headers=headers("u_admin"),
        json=body(Use.WIKI, Use.CHANNEL),
    )
    assert answered.status_code == 200
    verdicts = {one["name"]: (one["verdict"], one["missing"]) for one in answered.json()["uses"]}
    assert verdicts == {
        "knowledge_wiki": ("working", []),
        "chat_channel": ("missing_scope", [MEMBERS_SCOPE]),
    }
    assert vault.written == [] and app.state.lark_settings.saved == []
    assert {method for method, _, _ in lark.seen[1:]} == {"GET"}


def test_a_caller_short_of_one_chosen_uses_authority_is_refused_and_nothing_is_sent(
    app: FastAPI, client: TestClient, lark: FakeLark
) -> None:
    """u_narrow may connect the Wiki and not the staff list. Delete this and one grant switches on
    every use, and the secret is sent to Lark on behalf of somebody who may not."""
    vault = Vault()
    app.state.credentials = Credentials(vault, environ={}, writes=Recorded())
    for path in (LARK_TEST_PATH, LARK_PATH):
        answered = client.post(
            f"{API_PREFIX}{path}", headers=headers("u_narrow"), json=body(Use.WIKI, Use.STAFF_LIST)
        )
        assert answered.status_code == 404
    assert lark.seen == [] and vault.written == [] and app.state.lark_settings.saved == []
    alone = client.post(
        f"{API_PREFIX}{LARK_PATH}", headers=headers("u_narrow"), json=body(Use.WIKI)
    )
    assert alone.status_code == 200


def test_a_save_keeps_one_credential_in_each_uses_slot_and_switches_them_on(
    app: FastAPI, client: TestClient
) -> None:
    """The credential goes to each chosen use's slot in the shape the staff reader splits, and the
    settings name the uses, the platform, the Base and the staff source. Delete this and a use can
    be switched on with no key behind it, or the staff sync reads a credential it cannot split."""
    vault = Vault()
    app.state.credentials = Credentials(vault, environ={}, writes=Recorded())
    answered = client.post(
        f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin"), json=body(Use.STAFF_LIST, Use.BASE)
    )
    assert answered.status_code == 200
    assert answered.json()["switched_on"] == ["staff_list", "knowledge_base"]
    kept = f"{APP_ID}{CLIENT_CREDENTIAL_SEPARATOR}{SECRET}"
    assert vault.written == [
        ("connector_keys/staff_source", {KEY_FIELD: kept}),
        ("connector_keys/lark_base", {KEY_FIELD: kept}),
    ]
    assert app.state.lark_settings.saved == [
        {
            "INSTALL_LARK_USES": "staff_list,knowledge_base",
            "INSTALL_LARK_PLATFORM": "larksuite.com",
            "INSTALL_LARK_BASE": BASE,
            "INSTALL_STAFF_SOURCE": "lark",
            "INSTALL_STAFF_SOURCE_LOCATION": "larksuite.com",
        }
    ]


def test_an_install_with_no_vault_switches_nothing_on(app: FastAPI, client: TestClient) -> None:
    """Delete this and a use is switched on with its credential kept nowhere."""
    app.state.credentials = Credentials(None)
    answered = client.post(
        f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin"), json=body(Use.WIKI)
    )
    assert answered.status_code == 409
    assert app.state.lark_settings.saved == []


def test_a_bad_app_id_and_a_missing_base_link_are_told_by_field(
    app: FastAPI, client: TestClient, lark: FakeLark
) -> None:
    """Delete this and a wrong paste is sent to Lark and answered as a refused credential."""
    sent = body(Use.BASE) | {"app_id": "my app", "base_link": ""}
    answered = client.post(f"{API_PREFIX}{LARK_TEST_PATH}", headers=headers("u_admin"), json=sent)
    assert answered.status_code == 422
    fields = {one["field"] for one in answered.json()["problems"]}
    assert fields == {"app_id", "base_link"}
    assert lark.seen == []


def test_the_secret_is_never_answered_or_logged(
    app: FastAPI,
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every answer, a refused body included, and every log line, read for the sentinel. The save
    is proved to have kept it, so a route that stored nothing cannot pass. Delete this and a
    refusal can echo the App Secret."""
    caplog.set_level(logging.DEBUG)
    vault = Vault()
    app.state.credentials = Credentials(vault, environ={}, writes=Recorded())
    with structlog.testing.capture_logs() as logged:
        answers = [
            client.post(
                f"{API_PREFIX}{LARK_TEST_PATH}", headers=headers("u_admin"), json=body(*Use)
            ),
            client.post(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin"), json=body(*Use)),
            client.post(
                f"{API_PREFIX}{LARK_PATH}",
                headers=headers("u_admin"),
                json=body(Use.WIKI) | {"app_id": ""},
            ),
            client.post(
                f"{API_PREFIX}{LARK_PATH}",
                headers=headers("u_admin"),
                json={"app_secret": [SECRET]},
            ),
            client.post(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_none"), json=body(Use.WIKI)),
            client.get(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin")),
        ]
    assert any(SECRET in fields[KEY_FIELD] for _, fields in vault.written)
    out = capsys.readouterr()
    assert any(ENCRYPT_KEY in fields[KEY_FIELD] for _, fields in vault.written)
    for sentinel in (SECRET, ENCRYPT_KEY, VERIFY_TOKEN):
        for answered in answers:
            assert sentinel not in answered.text
        assert sentinel not in out.out + out.err + caplog.text
        assert sentinel not in " ".join(str(one) for one in logged)


def test_after_a_save_each_use_says_where_it_stands(app: FastAPI, client: TestClient) -> None:
    """Delete this and the Connectors screen cannot tell a switched-on use from one that is not."""
    app.state.credentials = Credentials(Vault(), environ={}, writes=Recorded())
    hold_saved(settings_for([Use.WIKI, Use.STAFF_LIST], platform="larksuite.com", base_link=""))
    uses = {
        one["name"]: one
        for one in client.get(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin")).json()["uses"]
    }
    assert uses["knowledge_wiki"]["switched_on"] and uses["staff_list"]["switched_on"]
    assert not uses["knowledge_base"]["switched_on"]
    # The fake vault holds nothing, so a switched-on use says its key is missing rather than "on".
    assert uses["knowledge_wiki"]["key_held"] is False
    assert "not in the vault" in uses["knowledge_wiki"]["status"]
    assert uses["knowledge_base"]["status"] == "Not switched on."


# ------------------------------------------------------------------ nothing is copied


def test_connecting_lark_copies_no_content_and_registers_nothing_the_sync_worker_reads(
    app: FastAPI, client: TestClient, lark: FakeLark
) -> None:
    """The owner's rule: a minimal index and a live read, never a bulk copy. A save writes vault
    slots and installation settings and nothing else: the connector rows and the database are
    `NeverAsked` and would fail the test if touched; every setting written is a declared
    configuration value; the Lark connectors stay out of `CONNECTABLE`, so the sync worker, which
    reads only connectable sources, has nothing of Lark's to ingest; and the Wiki's mapping carries
    no content target. Delete this and a later change can make Connect Lark a bulk import."""
    app.state.credentials = Credentials(Vault(), environ={}, writes=Recorded())
    answered = client.post(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin"), json=body(*Use))
    assert answered.status_code == 200
    # The one read a save makes: the chat channel's bot id, after the token exchange.
    assert [(method, urlsplit(path).path) for method, path, _ in lark.seen] == [
        ("POST", "/open-apis/auth/v3/tenant_access_token/internal"),
        ("GET", "/open-apis/bot/v3/info"),
    ]
    lark.seen.clear()
    (values,) = app.state.lark_settings.saved
    assert set(values) <= set(BY_NAME)
    assert all(re.fullmatch(r"[A-Za-z0-9_.,:-]*", one) for one in values.values())
    for name in ("lark_wiki", "lark_base"):
        assert name not in CONNECTABLE
        with pytest.raises(NotConnectableError):
            manifest_for(name, {})
    lark_wiki.assert_maps_no_content(lark_wiki.NODE_MAPPING)
    assert lark.seen == []


# ------------------------------------------------------------------ the chat channel (L1)


def test_the_chat_steps_name_every_scope_and_the_event_and_save_before_the_address() -> None:
    """The owner creates the Lark app from these steps and nothing else, so the permissions they
    copy name each of the four chat scopes, the steps name the one event and both keys, and the
    save here comes before the Request URL in Lark, which Lark checks the moment it is entered.
    Delete this and a step can be dropped or reordered, and the owner's app is refused its address
    with no sentence saying why."""
    steps = steps_for([Use.CHANNEL], platform="larksuite.com")
    text = " ".join(one.text for one in steps)
    copied = json.loads(scope_import([Use.CHANNEL]))["scopes"]["tenant"]
    assert set(copied) == {
        "im:message.p2p_msg:readonly",
        "im:message.group_at_msg:readonly",
        MEMBERS_SCOPE,
        "im:message:send_as_bot",
    }
    assert {one.name for one in USES[Use.CHANNEL].scopes} == set(copied)
    assert MESSAGE_EVENT == "im.message.receive_v1" and MESSAGE_EVENT in text
    assert "Encrypt Key" in text and "Verification Token" in text
    assert [one.key for one in steps] == [
        StepKey.CHOOSE,
        StepKey.CREATE,
        StepKey.CREDENTIALS,
        StepKey.BOT,
        StepKey.PERMISSIONS,
        StepKey.EVENTS_KEYS,
        StepKey.EVENTS_ADDRESS,
        StepKey.RELEASE,
        StepKey.TEST,
    ]
    (keys,) = [one for one in steps if one.key == StepKey.EVENTS_KEYS]
    assert "save_channel" in keys.asks and "encrypt_key" in keys.asks


def test_every_use_takes_fewer_screens_than_the_list_it_replaced() -> None:
    """The owner asked for fewer steps. The list this flow replaced had, for the staff list alone,
    nine things to do counting the choice of uses, and for all four uses eighteen; the flow is six
    and eleven. Delete this and a step can be split back out one screen at a time."""
    assert len(steps_for([Use.STAFF_LIST], platform="larksuite.com")) == 6
    assert len(steps_for(list(Use), platform="larksuite.com")) == 11
    for use in Use:
        assert len(steps_for([use], platform="larksuite.com")) <= 9


def test_copy_all_holds_exactly_the_scopes_the_chosen_uses_need_in_lark_import_shape() -> None:
    """The text pasted into Lark's batch import is the staff reader's own scope list for the
    staff list, the union for several uses, and asks for no user scope. Delete this and the
    pasted list can drift from the one the test checks, or ask for a scope nobody chose."""
    staff = json.loads(scope_import([Use.STAFF_LIST]))
    assert staff == {"scopes": {"tenant": LARK_SYNC_SCOPES.split(), "user": []}}
    both = json.loads(scope_import([Use.STAFF_LIST, Use.WIKI]))["scopes"]["tenant"]
    assert both == [one.name for one in scopes_for([Use.STAFF_LIST, Use.WIKI])]
    assert len(both) == len(set(both))
    assert json.loads(scope_import([]))["scopes"]["tenant"] == []


def test_the_app_id_turns_each_later_step_into_a_link_to_its_own_page() -> None:
    """Once the App ID is known, the permissions step opens that app's permissions page on the
    chosen platform; before it, and for anything not in Lark's shape, the console's app list.
    Delete this and a typed value can become a link somewhere else, or the links never arrive."""
    assert app_page("feishu.cn", APP_ID, StepKey.PERMISSIONS) == (
        f"https://open.feishu.cn/app/{APP_ID}/auth"
    )
    assert app_page("larksuite.com", APP_ID, StepKey.RELEASE) == (
        f"https://open.larksuite.com/app/{APP_ID}/version"
    )
    for typed in ("", "cli_", "https://elsewhere.example/x", f"{APP_ID}/../../x"):
        assert app_page("larksuite.com", typed, StepKey.PERMISSIONS) == (
            "https://open.larksuite.com/app"
        )
    linked = {
        one.key: one.link for one in steps_for(list(Use), platform="larksuite.com", app_id=APP_ID)
    }
    assert linked[StepKey.PERMISSIONS].endswith(f"/{APP_ID}/auth")
    assert linked[StepKey.SHARE_WIKI] == ""


def test_each_verdict_sends_the_administrator_to_the_step_that_fixes_it() -> None:
    """A missing scope goes to the permissions and then the release, because Lark cannot tell a
    scope not added from one not released; a directory the app cannot see goes to the contacts
    range on the permissions page; a Base not shared goes to sharing the Base; a working use goes
    nowhere. Delete this and the flow can send somebody to the wrong screen."""

    def verdict(use: Use, found: Verdict) -> tuple[StepKey, ...]:
        return redo_for(UseResult(use, found, "told"))

    assert verdict(Use.WIKI, Verdict.MISSING_SCOPE) == (StepKey.PERMISSIONS, StepKey.RELEASE)
    assert verdict(Use.STAFF_LIST, Verdict.NOT_RELEASED) == (StepKey.RELEASE,)
    assert verdict(Use.STAFF_LIST, Verdict.NOT_SHARED)[0] == StepKey.PERMISSIONS
    assert verdict(Use.BASE, Verdict.NOT_SHARED) == (StepKey.SHARE_BASE,)
    assert verdict(Use.BASE, Verdict.NEEDS_SETTING) == (StepKey.SHARE_BASE,)
    assert verdict(Use.WIKI, Verdict.NOT_SHARED) == (StepKey.SHARE_WIKI,)
    assert verdict(Use.CHANNEL, Verdict.NOT_SHARED)[0] == StepKey.BOT
    assert verdict(Use.CHANNEL, Verdict.CREDENTIAL_REFUSED) == (StepKey.CREDENTIALS,)
    assert verdict(Use.WIKI, Verdict.WORKING) == ()
    for use in Use:
        chosen = {one.key for one in steps_for([use], platform="larksuite.com")}
        for found in Verdict:
            assert set(verdict(use, found)) <= chosen


def test_a_missing_scope_sends_the_test_route_back_to_permissions_and_release(
    app: FastAPI, client: TestClient, lark: FakeLark
) -> None:
    """Through the application: the use with a scope missing names the two steps to redo and the
    working use names none, and a refused credential sends the whole test back to the
    credentials. Delete this and the console has no step to send anybody to."""
    lark.refuse["/open-apis/im/v1/chats"] = missing(MEMBERS_SCOPE)
    answered = client.post(
        f"{API_PREFIX}{LARK_TEST_PATH}",
        headers=headers("u_admin"),
        json=body(Use.WIKI, Use.CHANNEL),
    ).json()
    redo = {one["name"]: one["redo"] for one in answered["uses"]}
    assert redo == {"knowledge_wiki": [], "chat_channel": ["permissions", "release"]}
    assert answered["redo"] == []
    refused = client.post(
        f"{API_PREFIX}{LARK_TEST_PATH}",
        headers=headers("u_admin"),
        json=body(Use.WIKI, secret="not-the-secret"),
    ).json()
    assert refused["accepted"] is False and refused["redo"] == ["credentials", "choose"]


def test_a_test_records_when_it_ran_and_each_verdict_and_nothing_it_was_sent(
    app: FastAPI, client: TestClient, lark: FakeLark
) -> None:
    """The card says when Lark was last tested. What is kept is the instant and a verdict word per
    use, never the secret or the App ID typed for the test, and the guide reads it back. Delete
    this and the card has no last test, or the record can grow to hold what was sent."""
    lark.refuse["/open-apis/im/v1/chats"] = missing(MEMBERS_SCOPE)
    client.post(
        f"{API_PREFIX}{LARK_TEST_PATH}",
        headers=headers("u_admin"),
        json=body(Use.WIKI, Use.CHANNEL),
    )
    (kept,) = app.state.lark_facts.kept
    assert kept["app_id"] is None
    record = kept["last_test"]
    assert isinstance(record, dict)
    assert set(record) == {"at", "accepted", "uses"}
    assert record["uses"] == {"knowledge_wiki": "working", "chat_channel": "missing_scope"}
    assert SECRET not in json.dumps(kept) and APP_ID not in json.dumps(kept)
    shown = client.get(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin")).json()["last_test"]
    assert shown["accepted"] is True
    assert {one["name"]: one["verdict"] for one in shown["uses"]} == record["uses"]


def test_a_save_keeps_the_app_id_so_every_later_link_opens_the_app(
    app: FastAPI, client: TestClient
) -> None:
    """The App ID is not a secret and is kept on a save, so the card and a later Add a use open the
    app's own pages. Delete this and a returning administrator has to find the app again."""
    app.state.credentials = Credentials(Vault(), environ={}, writes=Recorded())
    client.post(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin"), json=body(Use.WIKI))
    assert app.state.lark_facts.kept[-1] == {"app_id": APP_ID, "last_test": None}
    hold_saved(settings_for([Use.WIKI], platform="larksuite.com", base_link=""))
    guide = client.get(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin")).json()
    assert guide["app_id"] == APP_ID and guide["connected"] is True
    links = {one["key"]: one["link"] for one in guide["steps"]}
    assert links["permissions"] == f"https://open.larksuite.com/app/{APP_ID}/auth"
    assert json.loads(guide["scope_import"])["scopes"]["tenant"] == [
        one.name for one in USES[Use.WIKI].scopes
    ]


def test_nothing_switched_on_reads_as_not_connected(client: TestClient) -> None:
    """The Connect Lark button is offered only while this is false. Delete this and the button
    stays after Lark is connected, which is what the owner found."""
    guide = client.get(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin")).json()
    assert guide["connected"] is False and guide["last_test"] is None


def test_switching_a_use_off_leaves_the_others_on_and_the_key_in_the_vault(
    app: FastAPI, client: TestClient
) -> None:
    """Switching the Wiki off keeps the staff list on and writes no key; switching the staff list
    off hands the staff source to nothing only while Lark is it. Delete this and Disconnect can
    switch off more than was asked, or leave the staff sync reading a source nobody chose."""
    vault = Vault()
    app.state.credentials = Credentials(vault, environ={}, writes=Recorded())
    hold_saved(settings_for([Use.WIKI, Use.STAFF_LIST], platform="larksuite.com", base_link=""))
    answered = client.post(
        f"{API_PREFIX}{LARK_SWITCH_OFF_PATH}",
        headers=headers("u_admin"),
        json={"uses": ["knowledge_wiki"]},
    )
    assert answered.status_code == 200 and answered.json()["switched_off"] == ["knowledge_wiki"]
    assert app.state.lark_settings.saved[-1] == {"INSTALL_LARK_USES": "staff_list"}
    client.post(
        f"{API_PREFIX}{LARK_SWITCH_OFF_PATH}",
        headers=headers("u_admin"),
        json={"uses": ["staff_list"]},
    )
    assert app.state.lark_settings.saved[-1] == {
        "INSTALL_LARK_USES": "knowledge_wiki",
        "INSTALL_STAFF_SOURCE": "none",
    }
    hold_saved(
        settings_for([Use.STAFF_LIST], platform="larksuite.com", base_link="")
        | {"INSTALL_STAFF_SOURCE": "google_workspace"}
    )
    client.post(
        f"{API_PREFIX}{LARK_SWITCH_OFF_PATH}",
        headers=headers("u_admin"),
        json={"uses": ["staff_list"]},
    )
    assert app.state.lark_settings.saved[-1] == {"INSTALL_LARK_USES": "none"}
    assert vault.written == []


def test_switching_off_asks_each_uses_own_authority(app: FastAPI, client: TestClient) -> None:
    """u_narrow may switch the Wiki and not the staff list. Delete this and one grant switches off
    every use, including the staff source somebody else governs."""
    hold_saved(settings_for([Use.WIKI, Use.STAFF_LIST], platform="larksuite.com", base_link=""))
    both = client.post(
        f"{API_PREFIX}{LARK_SWITCH_OFF_PATH}",
        headers=headers("u_narrow"),
        json={"uses": ["knowledge_wiki", "staff_list"]},
    )
    assert both.status_code == 404 and app.state.lark_settings.saved == []
    alone = client.post(
        f"{API_PREFIX}{LARK_SWITCH_OFF_PATH}",
        headers=headers("u_narrow"),
        json={"uses": ["knowledge_wiki"]},
    )
    assert alone.status_code == 200
    assert app.state.lark_settings.saved == [{"INSTALL_LARK_USES": "staff_list"}]


def test_switching_the_chat_channel_off_switches_its_record_off_and_keeps_its_ids(
    app: FastAPI, client: TestClient
) -> None:
    """The Channels screen reads the same record, so switching the chat channel off here switches
    it off there, and its App ID and bot id stay for the next save. Delete this and Lark keeps
    answering after Disconnect."""
    app.state.credentials = Credentials(Vault(), environ={}, writes=Recorded())
    client.post(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin"), json=body(Use.CHANNEL))
    before = asyncio.run(app.state.channel_records.get(Channel.LARK))
    assert before is not None and before.enabled
    hold_saved(settings_for([Use.CHANNEL], platform="larksuite.com", base_link=""))
    client.post(
        f"{API_PREFIX}{LARK_SWITCH_OFF_PATH}",
        headers=headers("u_admin"),
        json={"uses": ["chat_channel"]},
    )
    after = asyncio.run(app.state.channel_records.get(Channel.LARK))
    assert after is not None and not after.enabled
    assert dict(after.tenant) == dict(before.tenant)


def test_the_chat_channel_needs_both_event_keys_and_names_each_field_missing(
    client: TestClient, lark: FakeLark
) -> None:
    """Without the Encrypt Key and Verification Token no event verifies, so a save without them
    is refused by field before anything reaches Lark. Delete this and the channel is switched on
    with keys that refuse every event, and the card says only that nothing arrived."""
    sent = body(Use.CHANNEL) | {"encrypt_key": "", "verification_token": "two words"}
    answered = client.post(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin"), json=sent)
    assert answered.status_code == 422
    problems = {one["field"]: one["code"] for one in answered.json()["problems"]}
    assert problems == {"encrypt_key": "blank", "verification_token": "shape"}
    assert lark.seen == []
    wiki_only = body(Use.WIKI) | {"encrypt_key": "", "verification_token": ""}
    assert (
        client.post(
            f"{API_PREFIX}{LARK_TEST_PATH}", headers=headers("u_admin"), json=wiki_only
        ).status_code
        == 200
    )


def test_saving_the_chat_channel_keeps_its_keys_where_the_application_reads_them(
    app: FastAPI, client: TestClient
) -> None:
    """CH1's finding, fixed: the application reads `providers/channel_lark` and may not read
    `connector_keys/lark_channel`. So the App Secret, Encrypt Key and Verification Token are kept
    together there, as the Lark wire parses them, nothing is kept in the connector slot, and the
    channel's own record is written on, naming the app, the platform and the bot. Delete this and
    Connect Lark switches the chat on with a secret no event can be checked against."""
    vault = Vault()
    app.state.credentials = Credentials(vault, environ={}, writes=Recorded())
    answered = client.post(
        f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin"), json=body(Use.CHANNEL)
    )
    assert answered.status_code == 200
    ((slot, fields),) = vault.written
    assert slot == "providers/channel_lark"
    kept = LarkSecret.parse(fields[KEY_FIELD])
    assert (kept.app_secret, kept.encrypt_key, kept.verification_token) == (
        SECRET,
        ENCRYPT_KEY,
        VERIFY_TOKEN,
    )
    record = app.state.channel_records.kept[Channel.LARK]
    assert record.enabled
    assert dict(record.tenant) == {
        "app_id": APP_ID,
        "platform": "larksuite.com",
        "bot_id": "ou_bot",
    }
    assert record.secret.path == "providers/channel_lark"


def test_a_save_before_release_keeps_the_bot_id_already_known(
    app: FastAPI, client: TestClient, lark: FakeLark
) -> None:
    """Before release Lark may have no bot to read, and a later save must not forget the id an
    earlier one recorded. Delete this and saving again after a key change stops every group
    answer, because the record no longer names the bot a group message has to mention."""
    app.state.credentials = Credentials(Vault(), environ={}, writes=Recorded())
    client.post(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin"), json=body(Use.CHANNEL))
    lark.refuse["/open-apis/bot/"] = {"code": 10003, "msg": "bot not enabled"}
    client.post(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin"), json=body(Use.CHANNEL))
    assert app.state.channel_records.kept[Channel.LARK].tenant["bot_id"] == "ou_bot"
    app.state.channel_records.kept.clear()
    client.post(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin"), json=body(Use.CHANNEL))
    assert "bot_id" not in app.state.channel_records.kept[Channel.LARK].tenant


def test_the_card_shows_the_events_address_and_whether_events_are_arriving(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner's proof that Lark reaches the install: the address to paste, and what the last
    event came to, in words, with nothing of any message. Only a reader who may switch the chat
    on is shown it. Delete this and the card cannot tell a working channel from one whose keys
    refuse every event."""
    app.state.credentials = Credentials(Vault(), environ={}, writes=Recorded())
    monkeypatch.setenv("INSTALL_OIDC_REDIRECT_URIS", "https://brain.example.test/callback")
    before = client.get(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin")).json()["events"]
    assert before["address"] == "https://brain.example.test/api/v1/channels/lark/events"
    assert before["switched_on"] is False and before["told"] == EVENTS_OFF
    client.post(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin"), json=body(Use.CHANNEL))
    waiting = client.get(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin")).json()["events"]
    assert waiting["switched_on"] is True and waiting["told"] == EVENTS_NONE_YET
    deliveries = app.state.channel_deliveries
    asyncio.run(
        deliveries.record(
            DeliveryEntry(
                channel=Channel.LARK,
                direction=Direction.INBOUND,
                outcome=DeliveryOutcome.REFUSED,
                reason=RefusedBecause.BAD_SIGNATURE,
            )
        )
    )
    refused = client.get(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin")).json()["events"]
    assert refused["refused_because"] == "bad_signature"
    assert refused["told"] == REFUSED_EVENT_TOLD[RefusedBecause.BAD_SIGNATURE]
    for entry in (
        DeliveryEntry(Channel.LARK, Direction.INBOUND, DeliveryOutcome.ACCEPTED),
        DeliveryEntry(Channel.LARK, Direction.OUTBOUND, DeliveryOutcome.SENT, vendor_status=200),
    ):
        asyncio.run(deliveries.record(entry))
    arriving = client.get(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_admin")).json()["events"]
    assert arriving["told"] == f"{EVENTS_ARRIVING} {REPLY_TOLD[DeliveryOutcome.SENT]}"
    assert arriving["last_received"] is not None and arriving["reply_outcome"] == "sent"
    narrow = client.get(f"{API_PREFIX}{LARK_PATH}", headers=headers("u_narrow")).json()
    assert narrow["events"] is None


# ------------------------------------------------------------------ the facts, on a database


class _Principal:
    id = "u_admin"


class _Caller:
    principal = _Principal()


class _Reach:
    def ent_hash(self) -> str:
        return "0" * 32


@pytest.mark.needs_db
def test_the_app_id_and_the_last_test_are_kept_in_the_settings_table_and_read_back() -> None:
    """Through the real `ops.setting` table and its constraints: the App ID is a string row, the
    last test a JSON row the table accepts, a second keep writes over the first, and reading them
    back gives the card what it shows. Delete this and a store that the table refuses passes every
    test over the in-memory one, and the card never says when Lark was last tested."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from brain.lark_connect_routes import StoredLarkFacts
    from brain.ops.lark_connect import ProbeResult, UseResult, last_test_value
    from tests.fixtures.scratch_postgres import add_modelled, drop, fresh, sql
    from tests.unit.test_connector_sync_run import through

    asked = cast(Asking, type("Asked", (), {"caller": _Caller(), "reach": _Reach()})())
    at = datetime(2999, 1, 2, 3, 4, tzinfo=UTC)
    tested = ProbeResult(
        True,
        "told",
        (UseResult(Use.WIKI, Verdict.WORKING, "ok"), UseResult(Use.BASE, Verdict.NOT_SHARED, "no")),
    )
    name = "brain_test_lark_facts"
    url = fresh(name)
    try:
        add_modelled(url, ("ops.setting",))

        async def work(sessions: async_sessionmaker[AsyncSession]) -> Any:
            store = StoredLarkFacts(sessions)
            await store.keep(app_id="cli_old0000", last_test=None, asked=asked)
            await store.keep(app_id=APP_ID, last_test=last_test_value(tested, at=at), asked=asked)
            return await store.read()

        facts = through(url, work)
        rows = sql(url, "SELECT key, value_type FROM ops.setting ORDER BY key")
    finally:
        drop(name)
    assert rows == [
        ("connector.lark_app.app_id", "string"),
        ("connector.lark_app.last_test", "json"),
    ]
    assert facts.app_id == APP_ID
    assert facts.last_test is not None and facts.last_test.at == at
    assert dict(facts.last_test.verdicts) == {
        Use.WIKI: Verdict.WORKING,
        Use.BASE: Verdict.NOT_SHARED,
    }
