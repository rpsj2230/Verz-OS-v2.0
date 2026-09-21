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
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.api_routes import Asking
from brain.app import Settings, create_app
from brain.connector_routes import CONNECTORS_READ
from brain.connectors import lark_wiki
from brain.connectors.registry import INSTALL_AUTHORITY
from brain.connectors.staff_directories import LARK_SCOPES
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.credential_routes import CREDENTIAL_AUTHORITY
from brain.install import BY_NAME, hold_saved
from brain.lark_connect_routes import LARK_PATH, LARK_TEST_PATH
from brain.ops.connectable import CONNECTABLE, NotConnectableError, manifest_for
from brain.ops.connector_slots import SLOT_SCOPES
from brain.ops.credentials import KEY_FIELD, Credentials
from brain.ops.lark_connect import (
    USES,
    Use,
    Verdict,
    base_token,
    events_address,
    probe_connection,
    scopes_for,
    settings_for,
    steps_for,
)
from brain.ops.staff_sync_run import CLIENT_CREDENTIAL_SEPARATOR, http_fetch
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
from tests.unit.test_credentials import Recorded, Vault

APP_ID: Final = "cli_a1b2c3d4e5f6"
#: A secret nothing else in any output could contain, so finding it anywhere is a leak.
SECRET: Final = "LARK-SECRET-SENTINEL-51d9"
TOKEN: Final = "t-tenant-token-fake"
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
        self.accept_secret = SECRET
        self.empty_directory = False
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
                        self._answer(envelope)
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
            items = [] if self.empty_directory else [{"open_department_id": "od_1"}]
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
    assert names[Use.STAFF_LIST] == set(LARK_SCOPES.split())
    assert "docs:permission.member:retrieve" in names[Use.WIKI]
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
    assert staff == set(LARK_SCOPES.split())
    both = {one.name for one in scopes_for([Use.STAFF_LIST, Use.WIKI])}
    assert both == staff | {one.name for one in USES[Use.WIKI].scopes}
    text = " ".join(one.text for one in steps_for([Use.STAFF_LIST], platform="larksuite.com"))
    assert "contact:user.email:readonly" in text
    assert "wiki:wiki:readonly" not in text and "im:chat:readonly" not in text
    assert "All members" in text
    titles = [one.title for one in steps_for([Use.WIKI, Use.CHANNEL], platform="feishu.cn")]
    assert "Share your wiki spaces with it" in titles and "Turn on the bot" in titles
    assert "https://open.feishu.cn/app" in steps_for([Use.WIKI], platform="feishu.cn")[0].text


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
    """The listing works and the permission read is refused: the sentence names exactly
    docs:permission.member:retrieve. Delete this and the scope item 81 was about goes unnamed."""
    lark.refuse["/open-apis/drive/v1/permissions/"] = missing("docs:permission.member:retrieve")
    (wiki, staff) = probe(lark, Use.STAFF_LIST, Use.WIKI).uses[::-1]
    assert wiki.verdict is Verdict.MISSING_SCOPE
    assert wiki.missing == ("docs:permission.member:retrieve",)
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
    }


def test_the_guide_follows_the_uses_asked_about(client: TestClient) -> None:
    """Delete this and the console must hold its own copy of the scope list."""
    staff = client.get(f"{API_PREFIX}{LARK_PATH}?uses=staff_list", headers=headers("u_narrow"))
    assert staff.status_code == 200
    names = {one["name"] for one in staff.json()["scopes"]}
    assert names == set(LARK_SCOPES.split())
    wiki = client.get(f"{API_PREFIX}{LARK_PATH}?uses=knowledge_wiki", headers=headers("u_narrow"))
    assert "docs:permission.member:retrieve" in {one["name"] for one in wiki.json()["scopes"]}
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
    lark.refuse["/open-apis/im/v1/chats"] = missing("im:chat:readonly")
    answered = client.post(
        f"{API_PREFIX}{LARK_TEST_PATH}",
        headers=headers("u_admin"),
        json=body(Use.WIKI, Use.CHANNEL),
    )
    assert answered.status_code == 200
    verdicts = {one["name"]: (one["verdict"], one["missing"]) for one in answered.json()["uses"]}
    assert verdicts == {
        "knowledge_wiki": ("working", []),
        "chat_channel": ("missing_scope", ["im:chat:readonly"]),
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
    for answered in answers:
        assert SECRET not in answered.text
    assert SECRET not in out.out + out.err + caplog.text
    assert SECRET not in " ".join(str(one) for one in logged)


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
    (values,) = app.state.lark_settings.saved
    assert set(values) <= set(BY_NAME)
    assert all(re.fullmatch(r"[A-Za-z0-9_.,:-]*", one) for one in values.values())
    for name in ("lark_wiki", "lark_base"):
        assert name not in CONNECTABLE
        with pytest.raises(NotConnectableError):
            manifest_for(name, {})
    lark_wiki.assert_maps_no_content(lark_wiki.NODE_MAPPING)
    assert lark.seen == []
