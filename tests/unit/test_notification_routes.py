"""The Notifications screen over HTTP: who may read it, what it says, and the four writes.

Driven through the real application by `tests.fixtures.console_http`, with `ops.setting` held in
memory by `tests.fixtures.setting_rows`, so a switch and a saved relay are followed to the row they
write and the next read that sees it. The vault is a stand-in on `app.state.mail_password`, the
operation ledger `tests.fixtures.operation_ledger.MemoryLedger` on `app.state.operation_ledger`, and
the relay `tests.fixtures.fake_relay`, so a test message is followed to a relay that received it.

Task ids: M27.8.11, M27.7.12, M23.2.2
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
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.core.entitlement import Grant
from brain.core.scope import Scope
from brain.notification_routes import (
    EMAIL_PATH,
    NO_CACHE_KEEPS_ALERTS,
    NO_RELAY_CREDENTIAL_HELD,
    NOT_CONFIGURED,
    NOTHING_TO_REMOVE,
    NOTIFICATION_AUTHORITY,
    NOTIFICATIONS_PATH,
    ONLY_THE_LAST_CHANGE_IS_SHOWN,
    PASSWORD_PATH,
    REMOVAL_PATH,
    THE_ALERT_STORE_DID_NOT_ANSWER,
    TRIAL_PATH,
)
from brain.ops.credentials import TOLD as VAULT_TOLD
from brain.ops.credentials import VaultState
from brain.ops.denial_alert_store import AlertStore
from brain.ops.denial_alerts import ALERT_TEXT, AlertLog, DenialAlert, Digest
from brain.ops.limits import DenialShape
from brain.ops.mail import (
    RELAY_CREDENTIAL_FIELD,
    RELAY_CREDENTIAL_SLOT,
    MailPassword,
    SmtpTransport,
    TrialOutcome,
)
from brain.ops.notices import NOTICES, NoticeKind
from brain.ops.openbao import StaticVersion, VaultRefusedError, VaultUnreachableError
from brain.tables.audit import ACTOR_SETTING, ENT_HASH_SETTING, TRACE_ID_SETTING
from tests.fixtures.console_http import Stub, console_client, get, post
from tests.fixtures.fake_alert_valkey import FakeAlertValkey
from tests.fixtures.fake_relay import LOOPBACK, fake_relay
from tests.fixtures.operation_ledger import MemoryLedger
from tests.fixtures.setting_rows import Result, Row, SettingRows

PAGE = f"{API_PREFIX}{NOTIFICATIONS_PATH}"
RELAY = f"{API_PREFIX}{EMAIL_PATH}"
PASSWORD = f"{API_PREFIX}{PASSWORD_PATH}"
TRIAL = f"{API_PREFIX}{TRIAL_PATH}"
REMOVAL = f"{API_PREFIX}{REMOVAL_PATH}"
SECRET = "relay-PASSWORD-SENTINEL-0123456789"
WRITTEN = datetime(2019, 3, 4, 9, 0, 5, tzinfo=UTC)

GRANTS = {
    "u_admin": (Grant(capability=NOTIFICATION_AUTHORITY, scope=Scope.unrestricted()),),
    "u_narrow": (Grant(capability=NOTIFICATION_AUTHORITY, scope=Scope.department("web")),),
    "u_none": (),
}


#: The directory's names, as `brain.routing_routes.names_of` reads them.
NAMES = {"u_admin": "Ada Admin", "u_colleague": "Col League"}


def names(statement: Any) -> Result | None:
    """The names a `names_of` select asks for, or None for any other statement."""
    if not isinstance(statement, Select):
        return None
    if [one["name"] for one in statement.column_descriptions] != ["id", "display_name"]:
        return None
    asked = statement.compile().params["id_1"]
    return Result(Row((pid, NAMES[pid])) for pid in sorted(asked) if pid in NAMES)


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
        stub.answerers.append(names)
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
                (REMOVAL, {}),
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
    assert sent == {NoticeKind.REVERIFICATION_REQUEST.value, NoticeKind.DENIAL_PATTERN.value}
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
    # Who, at what reach, in which request, for the setting's ledger entry (M24.3.1).
    assert [name for name, _ in stub.attributions] == [
        ACTOR_SETTING,
        ENT_HASH_SETTING,
        TRACE_ID_SETTING,
    ]
    assert stub.attributions[0][1] == "u_admin"
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


def test_removing_the_relay_retires_its_rows_names_who_did_and_the_next_read_is_unconfigured(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """**Removed by retirement, attributed.** The five rows leave the live set naming the person
    who removed them, the transaction carries their attribution for `0059`'s `retired` entries,
    the answer and the next read say no relay is configured, and the password is not touched.

    Delete this and a removal can report success while the relay keeps sending, or leave rows
    retired by nobody the ledger can name."""
    client, stub = served
    vault = Vault(held=True)
    attach(client, vault)
    assert post(client, "u_admin", RELAY, relay_body()).status_code == 200
    stub.attributions.clear()

    removed = post(client, "u_admin", REMOVAL, {})
    assert removed.status_code == 200, removed.text
    assert removed.json()["configured"] is False and removed.json()["host"] is None
    assert {one["key"] for one in settings.retired} == {
        f"mail.{name}" for name in ("host", "port", "security", "sender", "username")
    }
    assert {one["updated_by"] for one in settings.retired} == {"u_admin"}
    assert stub.commits == 2
    assert stub.attributions[0] == (ACTOR_SETTING, "u_admin")
    assert get(client, "u_admin", PAGE).json()["email"]["configured"] is False
    assert vault.value == SECRET and vault.written == []


def test_a_removal_with_nothing_saved_is_a_conflict_that_retires_nothing(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """Delete this and removing a relay nobody saved answers 200, which reads as a change."""
    client, stub = served
    attach(client, Vault())
    refused = post(client, "u_admin", REMOVAL, {})
    assert refused.status_code == 409
    assert refused.json()["message"] == NOTHING_TO_REMOVE
    assert settings.retired == [] and stub.commits == 0


def test_the_page_names_the_people_it_mentions_and_asks_for_nobody_else(
    served: tuple[TestClient, Stub], settings: SettingRows
) -> None:
    """**Names, never ids on the page.** Whoever switched a notice or saved the relay is named from
    the directory, and the lookup asks for exactly the people the page mentions.

    Delete this and the console draws a principal id where a person's name belongs."""
    client, stub = served
    attach(client, Vault())
    switched = post(client, "u_admin", notice_path("reverification_request"), {"on": False})
    assert switched.status_code == 200
    body = get(client, "u_admin", PAGE).json()
    assert body["people"] == {"u_admin": "Ada Admin"}
    asked = [
        one.compile().params["id_1"]
        for one in stub.statements
        if isinstance(one, Select)
        and "display_name" in [column["name"] for column in one.column_descriptions]
    ]
    assert asked[-1] == ["u_admin"]


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


# ------------------------------------------------------------ refusal-pattern alerts (M23.2.2)
def _alert(recipient: str, subject: str) -> DenialAlert:
    shape = DenialShape.ENUMERATION
    return DenialAlert(
        recipient_id=recipient,
        subject_id=subject,
        shape=shape,
        raised_at=WRITTEN,
        text=ALERT_TEXT[shape],
    )


def test_the_readers_own_refusal_pattern_alerts_are_listed_by_shape_and_nobody_elses(
    served: tuple[TestClient, Stub],
) -> None:
    """ "A denial-pattern alert reaches Notifications naming the shape of the pattern." The
    reader's own alert is listed with who it is about, the sentence for its shape and when; an
    alert kept for somebody else is not; and nothing on the page names a capability, an object
    or a number.

    Delete this and the digest can keep alerts that no screen ever shows."""
    client, _ = served
    attach(client, Vault())
    store = AlertStore(client=FakeAlertValkey())
    store.keep(
        Digest(
            alerts=(_alert("u_admin", "u_weiling"), _alert("u_other", "u_jason")), log=AlertLog()
        )
    )
    client.app.state.alert_store = store  # type: ignore[attr-defined]

    body = get(client, "u_admin", PAGE).json()

    assert body["alerts_unread"] == ""
    [one] = body["alerts"]
    assert one["subject"] == "u_weiling"
    assert one["said"] == ALERT_TEXT[DenialShape.ENUMERATION]
    assert set(one) == {"subject", "said", "raised_at"}
    assert "u_jason" not in json.dumps(body["alerts"])
    assert not any(char.isdigit() for char in one["said"])


def test_a_process_with_no_cache_says_no_alert_can_be_kept_rather_than_listing_none(
    served: tuple[TestClient, Stub],
) -> None:
    """An empty list says nobody was told anything; no cache says nothing could have been kept.
    Delete this and the second reads as the first."""
    client, _ = served
    attach(client, Vault())

    body = get(client, "u_admin", PAGE).json()

    assert body["alerts"] is None
    assert body["alerts_unread"] == NO_CACHE_KEEPS_ALERTS


def test_a_cache_that_does_not_answer_is_said_rather_than_failing_the_screen(
    served: tuple[TestClient, Stub],
) -> None:
    """The notices and the relay are still worth showing when the alerts cannot be read.
    Delete this and a cache outage takes the whole screen down with a 500."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    client, _ = served
    attach(client, Vault())
    client.app.state.alert_store = AlertStore(  # type: ignore[attr-defined]
        client=FakeAlertValkey(raises=RedisConnectionError("down"))
    )

    body = get(client, "u_admin", PAGE).json()

    assert body["alerts"] is None
    assert body["alerts_unread"] == THE_ALERT_STORE_DID_NOT_ANSWER
    assert body["notices"]


def test_the_screens_sentences_point_the_right_way_and_name_no_table(
    served: tuple[TestClient, Stub],
) -> None:
    """Found on the owner's install on 2026-09-29: the relay card said the notices were "below"
    when they are drawn above it, and the line under the notices named a table and a migration.

    Delete this and either sentence can go back to what the walk found."""
    client, _ = served
    attach(client, Vault())
    body = get(client, "u_admin", PAGE).json()

    assert "above" in body["email_used_for"] and "below" not in body["email_used_for"]
    said = body["only_the_last_change_is_kept"]
    assert said == ONLY_THE_LAST_CHANGE_IS_SHOWN
    assert "ops." not in said and "trigger" not in said
    assert not any(ch.isdigit() for ch in said)
