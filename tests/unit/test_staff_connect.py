"""Connecting a staff source from the console: the test, the save, the first sync, and the ledger.

`brain.ops.staff_connect` and the four addresses `brain.staff_source_routes` gained for it, driven
through the real application with the token machinery `tests/unit/test_api_routes.py` provides.
The directory is the Lark stand-in `tests/unit/test_staff_sync_run.py` answers from, the vault is
the in-memory one `tests/unit/test_credentials.py` provides, and the settings store and the roster
readers are replaced with recorders, so what each route wrote, and what it did not, is visible.

Task ids: M27.7.2, M1.8.6, M1.8.9, M26.3.2
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from brain import staff_source_routes
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.connectors.staff_directories import Answer
from brain.console.staff_source_guide import LOCATION, guide_for
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Scope
from brain.credential_routes import CREDENTIAL_AUTHORITY
from brain.identity.staff_adapters import GOOGLE_WORKSPACE, LARK, MICROSOFT_ENTRA
from brain.identity.staff_roster import Application, RunOutcome, StoredMember
from brain.identity.staff_source import STAFF_SOURCE_LOCATION_SETTING, STAFF_SOURCE_SETTING
from brain.install import hold_saved
from brain.ops import staff_connect, staff_sync_run
from brain.ops.credentials import KEY_FIELD, Credentials, connector_key_slot
from brain.ops.openbao import StaticVersion
from brain.ops.staff_connect import NOTHING_SAVED, TEST_PAGES, check_connection
from brain.ops.staff_sync_run import SHARED_APP_SLOTS, read_lark
from brain.ops.staff_sync_store import RunRecord
from brain.settings_routes import INSTALL_SETTING_AUTHORITY
from brain.staff_source_routes import (
    APPLY_PATH,
    CONNECT_PATH,
    FIRST_SYNC_PATH,
    GUIDES_PATH,
    HELD_SHARED,
    NOT_CONNECTABLE_BY_YOU,
    STAFF_CREDENTIAL_SLOT,
    TEST_PATH,
)
from tests.fixtures.http_client import Response
from tests.fixtures.no_database import as_if_ci_had_a_database
from tests.unit.test_api_routes import Directory as People
from tests.unit.test_api_routes import Keys, NoCache, Versions, token_for, verifier
from tests.unit.test_credentials import Recorded, Vault
from tests.unit.test_staff_sync_run import APP_ID, APP_SECRET, Directory

WHOLE = Scope.unrestricted()
IN_WEB = Scope.department("web")

#: The secret half, spelled so nothing else in any output could contain it.
SECRET = f"{APP_SECRET}-SENTINEL-c0nnect"
LARK_FORM: dict[str, str] = {LOCATION: "larksuite.com", "app_id": APP_ID, "app_secret": SECRET}
LARK_SAVED = {STAFF_SOURCE_SETTING: LARK, STAFF_SOURCE_LOCATION_SETTING: "larksuite.com"}

GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (),
    # Both authorities, over everything: may connect.
    "u_admin": (
        Grant(capability=INSTALL_SETTING_AUTHORITY, scope=WHOLE),
        Grant(capability=CREDENTIAL_AUTHORITY, scope=WHOLE),
    ),
    # One of the two only: may not do half a connection.
    "u_wide": (Grant(capability=INSTALL_SETTING_AUTHORITY, scope=WHOLE),),
    # Both, over one department: a staff source reads everybody, so this is neither.
    "u_narrow": (
        Grant(capability=INSTALL_SETTING_AUTHORITY, scope=IN_WEB),
        Grant(capability=CREDENTIAL_AUTHORITY, scope=IN_WEB),
    ),
    "u_prefix": (),
    "u_elsewhere": (),
}


class Grants:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


def _wiring() -> Any:
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    return GateWiring(
        authority=TokenAuthority(
            issuer="https://id.verz.example/realms/brain",
            audience="brain-api",
            keys=Keys(),
            verify=verifier,
            directory=People(),
        ),
        versions=Versions(),
        store=Grants(),
        cache=NoCache(),
    )


# ------------------------------------------------------------------ the stand-ins
@dataclass
class Session:
    executed: list[Any]

    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        return None

    def begin(self) -> Session:
        return self

    async def execute(self, statement: Any) -> None:
        self.executed.append(statement)

    async def commit(self) -> None:
        self.executed.append("commit")


@dataclass
class Database:
    """The settings table, the roster readers and the run writer, as recorders."""

    saved: dict[str, str] = field(default_factory=dict)
    saves: list[dict[str, str]] = field(default_factory=list)
    executed: list[Any] = field(default_factory=list)
    written: list[tuple[Application, RunRecord]] = field(default_factory=list)
    opened: int = 0

    def __call__(self) -> Session:
        self.opened += 1
        return Session(self.executed)


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Database:
    held = Database()

    async def save(session: object, values: Mapping[str, str], *, updated_by: str) -> int:
        held.saves.append(dict(values))
        held.saved.update(values)
        return len(values)

    async def load(session: object) -> dict[str, str]:
        return dict(held.saved)

    async def read_members(session: object, source: str) -> tuple[StoredMember, ...]:
        return ()

    async def read_last_applied(session: object, source: str) -> datetime | None:
        return None

    async def write_application(session: object, app: Application, record: RunRecord) -> None:
        held.written.append((app, record))

    monkeypatch.setattr(staff_source_routes, "sessions_of", lambda request: held)
    monkeypatch.setattr(staff_source_routes, "save", save)
    monkeypatch.setattr(staff_source_routes, "load", load)
    for module in (staff_connect, staff_sync_run):
        monkeypatch.setattr(module, "read_members", read_members)
        monkeypatch.setattr(module, "read_last_applied", read_last_applied)
    monkeypatch.setattr(staff_sync_run, "write_application", write_application)
    monkeypatch.setattr(staff_sync_run, "run_row", lambda record: ("run", record))
    return held


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Iterator[FastAPI]:
    as_if_ci_had_a_database(monkeypatch)
    before = hold_saved({})
    built: FastAPI = create_app(Settings(env="development", database_url=""))
    yield built
    hold_saved(before)


@pytest.fixture
def vault(app: FastAPI) -> Vault:
    held = Vault()
    app.state.credentials = Credentials(held, environ={}, writes=Recorded())
    return held


@pytest.fixture
def directory(app: FastAPI) -> Directory:
    held = Directory()
    app.state.staff_directory_fetch = held
    return held


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.console_reads = None
        yield c


def headers(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims={'amr': ['otp']})}"}


def post(c: TestClient, path: str, pid: str, body: Mapping[str, object]) -> Response:
    answer: Response = c.post(f"{API_PREFIX}{path}", headers=headers(pid), json=dict(body))
    return answer


def lark_guide() -> Any:
    found = guide_for(LARK)
    assert found is not None
    return found


# ------------------------------------------------------------ the test, as a function
def test_a_connection_test_reads_a_few_pages_says_how_many_people_and_sends_nothing_else() -> None:
    """M27.7.2's "try it before it runs": the credential, scopes and range, proved by a read.

    The directory stand-in records every request. The one POST is the token exchange the reader
    has to make; everything after it is a GET, and no more of them than the page budget. There is
    nothing else the function was given, so there is nowhere it could have written. Delete this
    and the test could walk a whole directory on every press, or send a write."""
    directory = Directory()

    found = asyncio.run(check_connection(lark_guide(), LARK_FORM, directory))

    everybody = asyncio.run(read_lark(Directory(), f"{APP_ID}:{SECRET}", "larksuite.com")).roster()
    assert found.read is True
    assert found.people == len(everybody.people) > 0
    assert found.complete is True
    assert f"{found.people} people" in found.told
    assert found.told.endswith(NOTHING_SAVED)
    first, *rest = directory.sent
    assert first.method == "POST"
    assert first.url.endswith("/auth/v3/tenant_access_token/internal")
    assert rest
    assert all(one.method == "GET" for one in rest)
    assert len(rest) <= TEST_PAGES


def test_a_test_that_stops_before_the_last_page_says_there_are_more_rather_than_all() -> None:
    """Delete this and a test reading two pages of a large company could report the whole company.

    `_lark` stopping between two departments ends on a page that says it is the last, so the walk
    marks it; the test then reads the roster as incomplete and says the first sync reads the rest.
    """
    found = asyncio.run(check_connection(lark_guide(), LARK_FORM, Directory(), pages=2))

    assert found.read is True
    assert found.complete is False
    assert "There are more" in found.told


def test_a_refused_credential_is_a_sentence_that_repeats_the_vendor_and_never_the_secret() -> None:
    """Delete this and a refused secret could come back in the refusal meant to explain it."""
    refused = Directory(token_answer=Answer(200, {"code": 10014, "msg": "app secret invalid"}))

    found = asyncio.run(check_connection(lark_guide(), LARK_FORM, refused))

    assert found.read is False
    assert "app secret invalid" in found.told
    assert found.told.endswith(NOTHING_SAVED)
    assert SECRET not in found.told
    assert found.people == 0


def test_a_source_this_version_cannot_connect_is_refused_before_any_request_is_sent() -> None:
    """Delete this and a Google Workspace form could send a secret to be kept for nothing."""
    workspace = guide_for(GOOGLE_WORKSPACE)
    assert workspace is not None
    directory = Directory()

    found = asyncio.run(check_connection(workspace, {}, directory))

    assert found.read is False
    assert found.told == workspace.unavailable
    assert directory.sent == []


# ------------------------------------------------------------------- the routes
def test_the_guides_are_shown_to_everybody_and_the_chosen_source_only_to_who_may_connect(
    client: TestClient,
) -> None:
    """Steps are product text; which source this install chose is not, and is shown with the forms.

    Delete this and a reader with no authority learns which directory the company uses, or the
    owner is shown every guide with none of them marked as the one in use."""
    before = hold_saved(LARK_SAVED)
    try:
        admin = client.get(f"{API_PREFIX}{GUIDES_PATH}", headers=headers("u_admin")).json()
        nobody = client.get(f"{API_PREFIX}{GUIDES_PATH}", headers=headers("u_none")).json()
    finally:
        hold_saved(before)

    assert admin["may_connect"] is True
    assert [one["source"] for one in admin["guides"] if one["chosen"]] == [LARK]
    assert nobody["may_connect"] is False
    assert not any(one["chosen"] for one in nobody["guides"])
    assert [one["steps"] for one in nobody["guides"]] == [one["steps"] for one in admin["guides"]]
    assert "24 hours" in admin["schedule"]


@pytest.mark.parametrize("pid", ["u_none", "u_wide", "u_narrow"])
def test_a_reader_without_both_authorities_over_everything_contacts_no_directory(
    client: TestClient, directory: Directory, vault: Vault, database: Database, pid: str
) -> None:
    """One refusal for all three routes, asked before any request is built.

    Delete this and somebody holding only the settings authority could make this server send a
    secret to a directory, or keep one."""
    for path in (TEST_PATH, CONNECT_PATH, FIRST_SYNC_PATH, APPLY_PATH):
        answer = post(client, path, pid, {"source": LARK, "values": LARK_FORM})
        assert answer.status_code == 404, (path, answer.text)
        assert NOT_CONNECTABLE_BY_YOU not in answer.text
    assert directory.sent == []
    assert vault.written == []
    assert vault.asked == []
    assert database.saves == []
    assert database.opened == 0


def test_the_test_route_keeps_nothing_and_never_sends_the_secret_back(
    client: TestClient, directory: Directory, vault: Vault, database: Database
) -> None:
    """The read-only guarantee through HTTP: no vault call, no settings, no session opened.

    Delete this and a route could keep what a person was only trying."""
    with capture_logs() as logged:
        answer = post(client, TEST_PATH, "u_admin", {"source": LARK, "values": LARK_FORM})

    assert answer.status_code == 200, answer.text
    assert answer.json()["read"] is True
    assert answer.json()["people"] > 0
    assert vault.written == []
    assert vault.asked == []
    assert database.saves == []
    assert database.opened == 0
    assert SECRET not in answer.text
    assert SECRET not in json.dumps(logged, default=str)


def test_connecting_keeps_the_credential_in_its_slot_saves_two_settings_and_echoes_nothing(
    client: TestClient, directory: Directory, vault: Vault, database: Database
) -> None:
    """M27.7.2 and the owner's "choose the source (Lark) and connect it", with no server edit.

    The credential goes to the vault slot the nightly run reads, as `<App ID>:<App Secret>`; the
    choice and the location go to `ops.setting` through the Settings screen's writer and are held
    by this process; neither the response, the logs nor a saved setting carries the secret.
    Delete this and a connection could save the secret as a setting, or save no choice at all."""
    with capture_logs() as logged:
        answer = post(client, CONNECT_PATH, "u_admin", {"source": LARK, "values": LARK_FORM})

    assert answer.status_code == 200, answer.text
    assert vault.written == [(STAFF_CREDENTIAL_SLOT.path, {KEY_FIELD: f"{APP_ID}:{SECRET}"})]
    assert database.saves == [LARK_SAVED]
    assert not any(SECRET in value for value in database.saved.values())
    assert SECRET not in answer.text
    assert SECRET not in json.dumps(logged, default=str)
    attributed = [one for one in database.executed if "set_config" in str(one)]
    assert {"name": "brain.actor_id", "value": "u_admin"} in [
        one.compile().params for one in attributed
    ]
    assert directory.sent[0].url.endswith("/auth/v3/tenant_access_token/internal")


def test_a_credential_the_directory_refuses_is_never_kept_and_nothing_is_chosen(
    app: FastAPI, client: TestClient, vault: Vault, database: Database
) -> None:
    """The wizard's rule on the console: only a credential the directory just accepted is kept.

    Delete this and a save could leave the nightly sync failing every night on a bad secret."""
    app.state.staff_directory_fetch = Directory(
        token_answer=Answer(200, {"code": 10014, "msg": "app secret invalid"})
    )

    answer = post(client, CONNECT_PATH, "u_admin", {"source": LARK, "values": LARK_FORM})

    assert answer.status_code == 422
    assert "app secret invalid" in answer.json()["message"]
    assert SECRET not in answer.text
    assert vault.written == []
    assert database.saves == []


def test_an_install_with_no_vault_saves_no_choice_it_could_not_read_with(
    app: FastAPI, client: TestClient, directory: Directory, database: Database
) -> None:
    """Delete this and the choice could be saved with the secret kept nowhere."""
    app.state.credentials = Credentials(None)

    answer = post(client, CONNECT_PATH, "u_admin", {"source": LARK, "values": LARK_FORM})

    assert answer.status_code >= 400
    assert database.saves == []
    assert SECRET not in answer.text


def test_the_first_sync_shows_who_it_would_add_and_writes_nothing_until_apply_is_pressed(
    client: TestClient, directory: Directory, vault: Vault, database: Database
) -> None:
    """The dry run first, then the apply, which is the nightly run itself.

    Delete this and the first sync could apply on the press meant to show what it would do."""
    database.saved.update(LARK_SAVED)
    body = {"source": LARK, "values": LARK_FORM}

    shown = post(client, FIRST_SYNC_PATH, "u_admin", body)

    assert shown.status_code == 200, shown.text
    assert shown.json()["applied"] is False
    assert sorted(shown.json()["added"]) == ["Ada Lovelace", "Katherine Johnson"]
    assert shown.json()["safe_to_apply"] is True
    assert database.written == []
    assert not [one for one in database.executed if getattr(one, "is_dml", False)]

    applied = post(client, APPLY_PATH, "u_admin", body)

    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] is True
    assert applied.json()["outcome"] == RunOutcome.APPLIED.value
    ((application, _),) = database.written
    assert sorted(application.added) == ["Ada Lovelace", "Katherine Johnson"]
    assert SECRET not in applied.text
    assert vault.asked == []


def test_a_first_sync_of_a_source_nobody_saved_is_refused_and_contacts_nobody(
    client: TestClient, directory: Directory, database: Database
) -> None:
    """Delete this and the first sync could apply a list the next night's run does not read."""
    database.saved.update({STAFF_SOURCE_SETTING: MICROSOFT_ENTRA})

    answer = post(client, FIRST_SYNC_PATH, "u_admin", {"source": LARK, "values": LARK_FORM})

    assert answer.status_code == 409
    assert "Save this connection" in answer.json()["message"]
    assert directory.sent == []
    assert database.written == []


def test_a_form_naming_no_listed_source_is_refused_in_product_words(client: TestClient) -> None:
    """Delete this and a refusal could repeat whatever was typed as the source."""
    sent = "SENTINEL-not-a-source"

    answer = post(client, TEST_PATH, "u_admin", {"source": sent, "values": {}})

    assert answer.status_code == 422
    assert sent not in answer.text


# ------------------------------------------------- the Lark app the Connectors screen keeps
class HoldsSome(Vault):
    """A vault holding a key at the named paths only, answered from metadata as the store asks."""

    def __init__(self, held: frozenset[str]) -> None:
        super().__init__()
        self.held_paths = held

    def static_kv_version(self, path: str) -> StaticVersion | None:
        self.asked.append(path)
        return StaticVersion(written_at=None) if path in self.held_paths else None


SHARED_LARK_PATH = connector_key_slot(SHARED_APP_SLOTS[LARK]).path


def test_the_lark_guide_offers_the_lark_app_the_connectors_screen_keeps_when_it_is_held(
    app: FastAPI, client: TestClient
) -> None:
    """The coordinator's 2026-09-21 ask: one Lark app serves the staff list too.

    Only the Lark guide offers it, only when that slot is held, and only to a reader who may
    connect. Delete this and the owner pastes the same App Secret twice, or a Microsoft form
    offers a Lark secret."""
    app.state.credentials = Credentials(HoldsSome(frozenset({SHARED_LARK_PATH})), environ={})

    admin = client.get(f"{API_PREFIX}{GUIDES_PATH}", headers=headers("u_admin")).json()
    nobody = client.get(f"{API_PREFIX}{GUIDES_PATH}", headers=headers("u_none")).json()
    app.state.credentials = Credentials(HoldsSome(frozenset()), environ={})
    empty = client.get(f"{API_PREFIX}{GUIDES_PATH}", headers=headers("u_admin")).json()

    offered = {one["source"]: one["held"] for one in admin["guides"] if one["held"]}
    assert offered == {LARK: HELD_SHARED[LARK]}
    assert not any(one["held"] for one in nobody["guides"])
    assert not any(one["held"] for one in empty["guides"])


def test_connecting_with_the_held_lark_app_saves_the_choice_keeps_nothing_and_reads_nothing(
    app: FastAPI, client: TestClient, directory: Directory, database: Database
) -> None:
    """Delete this and "use the Lark app" could write an empty credential over the kept one."""
    vault = HoldsSome(frozenset({SHARED_LARK_PATH}))
    app.state.credentials = Credentials(vault, environ={})

    answer = post(
        client,
        CONNECT_PATH,
        "u_admin",
        {"source": LARK, "values": {LOCATION: "larksuite.com"}, "use_held": True},
    )

    assert answer.status_code == 200, answer.text
    assert "not tested here" in answer.json()["told"]
    assert database.saves == [LARK_SAVED]
    assert vault.written == []
    assert directory.sent == []


def test_a_held_connection_is_refused_when_nothing_is_held_or_a_secret_is_sent_with_it(
    app: FastAPI, client: TestClient, directory: Directory, database: Database
) -> None:
    """Delete this and a held connection could be saved with no key anywhere, or a pasted secret
    could be silently dropped by a mode that keeps none."""
    app.state.credentials = Credentials(HoldsSome(frozenset()), environ={})
    nothing = post(
        client,
        CONNECT_PATH,
        "u_admin",
        {"source": LARK, "values": {LOCATION: "larksuite.com"}, "use_held": True},
    )
    app.state.credentials = Credentials(HoldsSome(frozenset({SHARED_LARK_PATH})), environ={})
    with_secret = post(
        client, CONNECT_PATH, "u_admin", {"source": LARK, "values": LARK_FORM, "use_held": True}
    )
    wrong_place = post(
        client,
        CONNECT_PATH,
        "u_admin",
        {"source": LARK, "values": {LOCATION: "attacker.example"}, "use_held": True},
    )

    assert nothing.status_code == with_secret.status_code == wrong_place.status_code == 422
    assert SECRET not in with_secret.text
    assert database.saves == []
    assert directory.sent == []


# ------------------------------------------------------------------- the ledger
def test_the_owner_change_trigger_writes_the_details_the_recorder_writes() -> None:
    """Delete this and the entry `0105`'s trigger writes can drift from `AuditRecorder.agent_owner`,
    so a chain held in memory and the database disagree about what an owner change looks like."""
    from brain.audit.ledger import AuditAction, AuditChain
    from brain.audit.record import ACTION_BY_METHOD, AuditRecorder
    from tests.unit.test_tables import VERSIONS, migration_module

    recorder = AuditRecorder(
        AuditChain(),
        actor_id="u_admin",
        ent_hash="0" * 32,
        trace_id="t",
        clock=lambda: datetime.now(UTC),
    )
    entry = recorder.agent_owner(agent_id="quote-helper", from_owner="u_gone", to_owner="u_admin")
    module = migration_module(VERSIONS / "0105_agent_owner_audit.py")

    assert dict(entry.details) == {
        "change": "owner_changed",
        "from_owner": "u_gone",
        "to_owner": "u_admin",
    }
    assert entry.subject == "agent:quote-helper"
    assert ACTION_BY_METHOD["agent_owner"] is AuditAction.AGENT_OWNER
    for key, value in (("change", "'owner_changed'"), ("from_owner", "OLD.owner_id")):
        assert f"'{key}', {value}" in module.TRIGGER_FUNCTION
    assert "'to_owner', NEW.owner_id" in module.TRIGGER_FUNCTION
    assert "'agent:' || NEW.id" in module.TRIGGER_FUNCTION
    assert "AFTER UPDATE OF owner_id ON agent.agent" in module.TRIGGER
    assert "'agent_owner'" in module.WIDENED_ACTIONS
    assert "'agent_owner'" not in module.NARROWER_ACTIONS
