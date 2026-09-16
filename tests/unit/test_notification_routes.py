"""The Notifications screen over HTTP: who may read it, what it says, and the four writes.

Driven through the real application by `tests.fixtures.console_http`, with `ops.setting` held in
memory by `tests.fixtures.setting_rows`, so a switch and a saved relay are followed to the row they
write and the next read that sees it. The vault is a stand-in on `app.state.mail_password`, the
operation ledger `tests.fixtures.operation_ledger.MemoryLedger` on `app.state.operation_ledger`, and
the relay `tests.fixtures.fake_relay`, so a test message is followed to a relay that received it.

Task ids: M27.8.11, M27.7.12
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from email import message_from_bytes
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.notification_routes import (
    EMAIL_PATH,
    NO_RELAY_CREDENTIAL_HELD,
    NOT_CONFIGURED,
    NOTIFICATION_AUTHORITY,
    NOTIFICATIONS_PATH,
    PASSWORD_PATH,
    TRIAL_PATH,
)
from brain.ops.credentials import TOLD as VAULT_TOLD
from brain.ops.credentials import VaultState
from brain.ops.mail import (
    RELAY_CREDENTIAL_FIELD,
    RELAY_CREDENTIAL_SLOT,
    MailPassword,
    SmtpTransport,
    TrialOutcome,
)
from brain.ops.notices import NOTICES, NoticeKind
from brain.ops.openbao import StaticVersion, VaultRefusedError, VaultUnreachableError
from tests.fixtures.console_http import Stub, console_client, get, post
from tests.fixtures.fake_relay import LOOPBACK, fake_relay
from tests.fixtures.operation_ledger import MemoryLedger
from tests.fixtures.setting_rows import SettingRows

PAGE = f"{API_PREFIX}{NOTIFICATIONS_PATH}"
RELAY = f"{API_PREFIX}{EMAIL_PATH}"
PASSWORD = f"{API_PREFIX}{PASSWORD_PATH}"
TRIAL = f"{API_PREFIX}{TRIAL_PATH}"
SECRET = "relay-PASSWORD-SENTINEL-0123456789"
WRITTEN = datetime(2019, 3, 4, 9, 0, 5, tzinfo=UTC)

GRANTS = {
    "u_admin": (Grant(capability=NOTIFICATION_AUTHORITY, scope=Scope.unrestricted()),),
    "u_narrow": (Grant(capability=NOTIFICATION_AUTHORITY, scope=Scope.department("web")),),
    "u_none": (),
}


def notice_path(kind: str) -> str:
    return f"{API_PREFIX}{NOTIFICATIONS_PATH}/notices/{kind}"


class Vault:
    """The relay password's slot in memory: what is held, what was asked and written."""

    def __init__(self, *, held: bool = False, fail: Exception | None = None) -> None:
        self.value: str | None = SECRET if held else None
        self.fail = fail
        self.written: list[tuple[str, dict[str, str]]] = []
        self.reads = 0

    def write_static_kv(self, path: str, fields: Any) -> datetime | None:
        if self.fail is not None:
            raise self.fail
        self.written.append((path, dict(fields)))
        self.value = dict(fields)[RELAY_CREDENTIAL_FIELD]
        return WRITTEN

    def static_kv_version(self, path: str) -> StaticVersion | None:
        if self.fail is not None:
            raise self.fail
        return None if self.value is None else StaticVersion(written_at=WRITTEN)

    def read_static_kv(self, path: str) -> dict[str, Any]:
        if self.fail is not None:
            raise self.fail
        self.reads += 1
        if self.value is None:
            raise VaultRefusedError("absent", status=404)
        return {RELAY_CREDENTIAL_FIELD: self.value}


class Writes:
    def __init__(self) -> None:
        self.recorded: list[str] = []

    async def record(self, *, slot: str, written_by: str, trace_id: str, ent_hash: str) -> None:
        self.recorded.append(f"{slot} by {written_by}")


@pytest.fixture
def settings() -> SettingRows:
    return SettingRows()


@pytest.fixture
def served(settings: SettingRows) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        stub.answerers.append(settings.answer)
        yield client, stub


def attach(client: TestClient, vault: Vault | None, writes: Writes | None = None) -> None:
    client.app.state.mail_password = MailPassword(vault, writes)  # type: ignore[attr-defined]


def relay_body(**changed: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "host": "smtp.example.com",
        "port": 587,
        "security": "starttls",
        "sender": "console@example.com",
        "username": "relay_user",
    }
    body.update(changed)
    return body


# ---------------------------------------------------------------------- who may
@pytest.mark.parametrize("pid", ["u_none", "u_narrow"])
def test_a_caller_without_the_authority_over_everything_is_refused_before_the_database(
    pid: str,
) -> None:
    """The same refusal with a database and without one, for the read and every write, and nothing
    written or asked of the vault. Delete this and a department-scoped holder silences a notice
    for the whole install, or a stranger learns whether this process has a pool."""
    vault = Vault()
    answers: list[tuple[int, str]] = []
    for database in (False, True):
        with console_client(GRANTS, database=database) as (client, stub):
            rows = SettingRows()
            stub.answerers.append(rows.answer)
            attach(client, vault)
            for path, body in (
                (notice_path("evening_digest"), {"on": False}),
                (RELAY, relay_body()),
                (PASSWORD, {"password": SECRET}),
                (TRIAL, {"to": "someone@example.com"}),
            ):
                refused = post(client, pid, path, body)
                answers.append((refused.status_code, refused.json()["message"]))
            listed = get(client, pid, PAGE)
            answers.append((listed.status_code, listed.json()["message"]))
            assert rows.writes == [] and stub.statements == []
    assert {status for status, _ in answers} == {404}
    assert len({message for _, message in answers}) == 1
    assert vault.written == [] and vault.reads == 0


def test_a_password_only_sign_in_holding_the_authority_changes_nothing(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """`admin:` is withheld from a session with no second factor. Delete this and a stolen password
    alone silences a notice."""
    client, _ = served
    attach(client, Vault())
    weak = post(client, "u_admin", notice_path("evening_digest"), {"on": False}, strong=False)
    assert weak.status_code == 404
    assert settings.writes == []


def test_the_authority_is_an_administration_capability_the_first_administrator_holds() -> None:
    """Delete this and the screen needs a grant nobody on a fresh install has."""
    from brain.identity.first_administrator import ADMINISTRATION

    assert NOTIFICATION_AUTHORITY.value in ADMINISTRATION
    assert NOTIFICATION_AUTHORITY.value.startswith("admin:")


# ------------------------------------------------------------------ what is shown
def test_the_screen_lists_every_notice_on_and_an_unconfigured_relay_with_no_password(
    served: tuple[TestClient, Stub],
) -> None:
    """Delete this and a fresh install draws a notice nobody switched as off, or a relay nobody
    saved as configured."""
    client, _ = served
    attach(client, Vault())
    body = get(client, "u_admin", PAGE).json()

    assert [one["kind"] for one in body["notices"]] == [one.kind.value for one in NOTICES]
    assert all(one["on"] is True and one["changed_by"] is None for one in body["notices"])
    sent = {one["kind"] for one in body["notices"] if one["sent"]}
    assert sent == {NoticeKind.REVERIFICATION_REQUEST.value}
    assert body["email"]["configured"] is False and body["email"]["host"] is None
    assert body["email"]["password"] == {
        "held": False,
        "written_at": None,
        "vault": "ready",
        "vault_told": VAULT_TOLD[VaultState.READY],
    }
    assert body["securities"] == ["starttls", "tls"]


@pytest.mark.parametrize(
    ("vault", "state"),
    [
        (None, VaultState.ABSENT),
        (Vault(fail=VaultUnreachableError("x")), VaultState.UNREACHABLE),
        (Vault(fail=VaultRefusedError("x", status=403)), VaultState.REFUSED),
    ],
)
def test_a_vault_that_cannot_be_asked_leaves_the_password_unknown_rather_than_not_held(
    served: tuple[TestClient, Stub], vault: Vault | None, state: VaultState
) -> None:
    """Delete this and a silent vault reads as a relay with no password."""
    client, _ = served
    attach(client, vault)
    password = get(client, "u_admin", PAGE).json()["email"]["password"]
    assert (password["held"], password["vault"]) == (None, state.value)


# ------------------------------------------------------------------ the switch
def test_switching_a_notice_off_writes_its_row_with_the_writer_and_the_next_read_sees_it(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """The write followed to the row, the commit and the next read. Delete this and the switch can
    render as turned while writing a key the sender never reads."""
    client, stub = served
    attach(client, Vault())
    answer = post(client, "u_admin", notice_path("reverification_request"), {"on": False})

    assert answer.status_code == 200, answer.text
    assert (answer.json()["on"], answer.json()["changed_by"]) == (False, "u_admin")
    assert settings.writes == [
        {
            "key": "notice.reverification_request",
            "value_type": "boolean",
            "value": False,
            "updated_by": "u_admin",
        }
    ]
    assert stub.commits == 1
    listed = get(client, "u_admin", PAGE).json()["notices"]
    assert {one["kind"]: one["on"] for one in listed}["reverification_request"] is False


def test_a_notice_with_no_switch_is_refused_with_the_reason_and_nothing_is_written(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and the notice of emergency access can be silenced from the console."""
    client, stub = served
    attach(client, Vault())
    refused = post(client, "u_admin", notice_path("emergency_access"), {"on": False})

    assert refused.status_code == 409
    assert "has no switch" in refused.json()["message"]
    assert settings.writes == [] and stub.commits == 0
    unknown = post(client, "u_admin", notice_path("made_up"), {"on": False})
    assert unknown.status_code == 404 and "not a notice" in unknown.json()["message"]


# ------------------------------------------------------------------ the relay
def test_a_relay_is_saved_as_five_rows_with_its_writer_and_read_back_configured(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and a saved relay lands under keys nothing reads, or reads back unconfigured."""
    client, stub = served
    attach(client, Vault())
    answer = post(client, "u_admin", RELAY, relay_body())

    assert answer.status_code == 200, answer.text
    assert {one["key"]: one["value"] for one in settings.writes} == {
        "mail.host": "smtp.example.com",
        "mail.port": 587,
        "mail.security": "starttls",
        "mail.sender": "console@example.com",
        "mail.username": "relay_user",
    }
    assert {one["updated_by"] for one in settings.writes} == {"u_admin"}
    assert stub.commits == 1
    email = get(client, "u_admin", PAGE).json()["email"]
    assert (email["configured"], email["host"], email["port"], email["changed_by"]) == (
        True,
        "smtp.example.com",
        587,
        "u_admin",
    )


def test_a_bad_relay_is_told_every_problem_by_field_and_nothing_is_written(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and a half-valid relay is saved, or its problems are told one at a time."""
    client, stub = served
    attach(client, Vault())
    refused = post(
        client, "u_admin", RELAY, relay_body(host="https://x", security="none", sender="x")
    )

    assert refused.status_code == 422
    assert [one["field"] for one in refused.json()["problems"]] == ["host", "security", "sender"]
    assert settings.writes == [] and stub.commits == 0


def test_a_password_is_kept_at_its_slot_recorded_and_never_answered(
    served: tuple[TestClient, Stub], caplog: pytest.LogCaptureFixture
) -> None:
    """**Written once and never read back.** The vault holds it, the write is recorded where every
    credential write is, and neither the answer, the page after it nor any log line carries it.

    Delete this and a response or a log line can carry the relay's password."""
    client, _ = served
    vault, writes = Vault(), Writes()
    attach(client, vault, writes)
    answer = post(client, "u_admin", PASSWORD, {"password": f"{SECRET}\n"})

    assert answer.status_code == 200, answer.text
    assert vault.written == [(RELAY_CREDENTIAL_SLOT, {RELAY_CREDENTIAL_FIELD: SECRET})]
    assert writes.recorded == [f"{RELAY_CREDENTIAL_SLOT} by u_admin"]
    page = get(client, "u_admin", PAGE)
    assert page.json()["email"]["password"]["held"] is True
    for text in (answer.text, page.text, caplog.text):
        assert SECRET not in text


@pytest.mark.parametrize(
    ("vault", "status"),
    [
        (None, 409),
        (Vault(fail=VaultUnreachableError("x")), 503),
        (Vault(fail=VaultRefusedError("x", status=403)), 409),
    ],
)
def test_a_password_the_vault_cannot_keep_is_refused_with_what_to_do(
    served: tuple[TestClient, Stub], vault: Vault | None, status: int
) -> None:
    """Delete this and a vault outage answers 200 and the relay has no password."""
    client, _ = served
    writes = Writes()
    attach(client, vault, writes)
    refused = post(client, "u_admin", PASSWORD, {"password": SECRET})
    assert refused.status_code == status
    assert SECRET not in refused.text
    assert writes.recorded == []
    blank = post(client, "u_admin", PASSWORD, {"password": " "})
    assert blank.status_code == 422 and blank.json()["problems"][0]["field"] == "password"


# ------------------------------------------------------------------ the test message
def test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password(
    served: tuple[TestClient, Stub], tmp_path: Path
) -> None:
    """**The relay and the password, proved to reach the behaviour they configure.** A relay saved
    on the screen and a password kept on the screen, then the test button pressed twice: the relay
    reads one message from the saved sender, signed in with the kept password, and the second
    press is told the message was already sent.

    Delete this and every write on the screen can be followed to a row and none of them to a
    message."""
    client, _ = served
    vault = Vault()
    attach(client, vault)
    with fake_relay(tmp_path, username="relay_user", password=SECRET) as relay:
        client.app.state.operation_ledger = MemoryLedger()  # type: ignore[attr-defined]
        client.app.state.mail_transport = (  # type: ignore[attr-defined]
            lambda settings, password: SmtpTransport(settings, password, context=relay.trusted)
        )
        assert (
            post(client, "u_admin", RELAY, relay_body(host=LOOPBACK, port=relay.port)).status_code
            == 200
        )
        assert post(client, "u_admin", PASSWORD, {"password": SECRET}).status_code == 200
        first = post(client, "u_admin", TRIAL, {"to": "someone@example.com"})
        second = post(client, "u_admin", TRIAL, {"to": "someone@example.com"})

    assert first.status_code == 200, first.text
    assert first.json()["outcome"] == TrialOutcome.SENT.value
    assert second.json()["outcome"] == TrialOutcome.ALREADY_SENT.value
    (delivered,) = relay.delivered
    assert delivered.authenticated_as == "relay_user"
    assert message_from_bytes(delivered.data)["From"] == "console@example.com"
    assert SECRET not in first.text + second.text


def test_a_test_message_needs_a_saved_relay_and_a_password_when_it_names_a_user(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and a test is tried against a relay nobody saved, or signs in with none."""
    client, _ = served
    attach(client, Vault())
    client.app.state.operation_ledger = MemoryLedger()  # type: ignore[attr-defined]

    unsaved = post(client, "u_admin", TRIAL, {"to": "someone@example.com"})
    assert (unsaved.status_code, unsaved.json()["message"]) == (409, NOT_CONFIGURED)

    assert post(client, "u_admin", RELAY, relay_body()).status_code == 200
    nopass = post(client, "u_admin", TRIAL, {"to": "someone@example.com"})
    assert (nopass.status_code, nopass.json()["message"]) == (409, NO_RELAY_CREDENTIAL_HELD)

    bad = post(client, "u_admin", TRIAL, {"to": "not an address"})
    assert bad.status_code == 422 and bad.json()["problems"][0]["field"] == "to"


def test_no_answer_on_this_screen_carries_a_value_a_response_should_not(
    served: tuple[TestClient, Stub],
) -> None:
    """The page carries no vault path. Delete this and the slot the password is kept at rides out
    on the page, which says where to look for it."""
    client, _ = served
    attach(client, Vault(held=True))
    body = get(client, "u_admin", PAGE).text
    assert RELAY_CREDENTIAL_SLOT not in body and SECRET not in body
    assert "providers/" not in json.dumps(body)
