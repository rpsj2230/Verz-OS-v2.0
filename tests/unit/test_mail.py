"""Email delivery: what a relay's configuration must be, the password in the vault, and one send.

Three halves. The judgements, each refusal beside the value it accepts. The transport, against
`tests.fixtures.fake_relay`, a relay on the loopback interface speaking enough SMTP for `smtplib`,
with a certificate made here: so a message is read by a relay, a password is refused by one, and a
password never crossing a plain connection is something the relay saw rather than something the
transport said. And the door: a test message through `issue_once` over the in-memory ledger, pressed
twice and pressed after a relay that did not answer.

Task ids: M27.8.11
"""

from __future__ import annotations

import socket
import threading
from datetime import UTC, datetime, timedelta
from email import message_from_bytes
from pathlib import Path
from typing import Any

import pytest

from brain.ops.credentials import VaultState
from brain.ops.idempotency import CallOutcome, OperationState
from brain.ops.mail import (
    RELAY_CREDENTIAL_FIELD,
    RELAY_CREDENTIAL_SLOT,
    Field,
    MailAnswer,
    MailPassword,
    MailPasswordUnavailableError,
    MailSettings,
    Message,
    Security,
    SmtpTransport,
    TrialOutcome,
    configuration_version,
    password_problems,
    send_trial,
    settings_from_rows,
    settings_problems,
    trial_operation,
)
from brain.ops.openbao import StaticVersion, VaultRefusedError, VaultUnreachableError
from brain.ops.setting_store import SettingState
from tests.fixtures.fake_relay import LOOPBACK, Relay, fake_relay
from tests.fixtures.operation_ledger import MemoryLedger

LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
PASSWORD = "relay-PASSWORD-SENTINEL-0123456789"


def configured(relay: Relay, **changed: Any) -> MailSettings:
    base: dict[str, Any] = {
        "host": LOOPBACK,
        "port": relay.port,
        "security": Security.TLS if relay.implicit_tls else Security.STARTTLS,
        "sender": "console@example.com",
        "username": "relay_user",
    }
    base.update(changed)
    return MailSettings(**base)


def good(**changed: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "host": "smtp.example.com",
        "port": 587,
        "security": "starttls",
        "sender": "console@example.com",
        "username": "relay_user",
    }
    base.update(changed)
    return base


# ------------------------------------------------------------------------ the judgements
def test_a_good_configuration_has_no_problems_and_an_empty_user_name_is_one() -> None:
    """The positive half of every refusal below.

    Delete this and a judgement that refused everything would pass every refusal here."""
    assert settings_problems(**good()) == ()
    assert settings_problems(**good(username="", security="tls", port=465)) == ()
    assert settings_problems(**good(host="10.0.0.25")) == ()


def test_every_problem_with_a_configuration_is_told_at_once_by_field() -> None:
    """Delete this and a form is refused for its first mistake and then for its second."""
    found = settings_problems(
        host="smtp://smtp.example.com:587",
        port=0,
        security="none",
        sender="not an address",
        username="has space",
    )
    assert [(one.field, one.code) for one in found] == [
        (Field.HOST, "not_a_host"),
        (Field.PORT, "out_of_range"),
        (Field.SECURITY, "unknown"),
        (Field.SENDER, "not_an_address"),
        (Field.USERNAME, "not_a_username"),
    ]


def test_a_relay_that_offers_no_tls_is_not_a_configuration_this_accepts() -> None:
    """**Plain SMTP is refused.** Delete this and a security value of "none" saves, and the relay's
    password and every message cross the network in the clear."""
    assert [one.code for one in settings_problems(**good(security="none"))] == ["unknown"]
    assert {one.value for one in Security} == {"starttls", "tls"}


@pytest.mark.parametrize(
    "host", ["", "smtp.example.com/", "smtp example.com", "-smtp.example.com", "a" * 254]
)
def test_a_host_that_is_not_a_host_name_is_refused(host: str) -> None:
    """Delete this and a pasted URL or a trailing slash saves and fails at the first message."""
    assert [one.field for one in settings_problems(**good(host=host))] == [Field.HOST]


@pytest.mark.parametrize("port", [-1, 0, 65536])
def test_a_port_outside_the_range_is_refused_and_its_ends_are_not(port: int) -> None:
    """Delete this and a port of zero saves."""
    assert [one.field for one in settings_problems(**good(port=port))] == [Field.PORT]
    assert settings_problems(**good(port=1)) == settings_problems(**good(port=65535)) == ()


def test_a_password_is_judged_as_a_credential_is_and_told_in_a_password_s_words() -> None:
    """Delete this and a password with a line break inside is kept and every message is refused."""
    assert password_problems(PASSWORD) == ()
    assert [one.code for one in password_problems("")] == ["blank"]
    assert [one.code for one in password_problems("two words")] == ["not_one_piece"]
    assert "password" in password_problems("")[0].message


def _row(name: str, value: object, value_type: str, at: datetime = LONG_AGO) -> SettingState:
    return SettingState(f"mail.{name}", value_type, value, "u_admin", at)


def rows(**changed: SettingState | None) -> dict[str, SettingState]:
    found: dict[str, SettingState | None] = {
        "host": _row("host", "smtp.example.com", "string"),
        "port": _row("port", 587, "integer"),
        "security": _row("security", "starttls", "string"),
        "sender": _row("sender", "console@example.com", "string"),
        "username": _row("username", "", "string"),
    }
    found.update(changed)
    return {name: one for name, one in found.items() if one is not None}


def test_saved_rows_read_as_a_configuration_only_when_every_field_is_there_and_its_type() -> None:
    """The producer from raw rows. Delete this and a half-saved configuration reads as a relay,
    and a test message is tried against a port that is a string."""
    assert settings_from_rows(rows()) == MailSettings(
        host="smtp.example.com",
        port=587,
        security=Security.STARTTLS,
        sender="console@example.com",
        username="",
    )
    assert settings_from_rows(rows(username=None)) is None
    assert settings_from_rows(rows(port=_row("port", "587", "string"))) is None
    assert settings_from_rows(rows(port=_row("port", True, "boolean"))) is None
    assert settings_from_rows(rows(security=_row("security", "none", "string"))) is None


def test_the_configuration_s_version_moves_when_it_is_saved_or_its_password_is_replaced() -> None:
    """Delete this and a test message could never be sent again after a fix, or be sent on every
    press, because the key would never move or always would."""
    settings = settings_from_rows(rows())
    assert settings is not None
    one = configuration_version(settings, saved_at=LONG_AGO, password_written_at=None)

    assert one == configuration_version(settings, saved_at=LONG_AGO, password_written_at=None)
    assert one != configuration_version(
        settings, saved_at=LONG_AGO + timedelta(seconds=1), password_written_at=None
    )
    assert one != configuration_version(settings, saved_at=LONG_AGO, password_written_at=LONG_AGO)
    assert "smtp.example.com" not in one


# ------------------------------------------------------------------------ the transport
def test_a_message_reaches_the_relay_over_starttls_signed_in_with_the_password(
    tmp_path: Path,
) -> None:
    """**The sender, end to end.** The relay reads the message from the configured sender to the
    recipient, and the sign-in arrived after the connection was upgraded.

    Delete this and every other test of email is a test of a function nobody showed a relay."""
    with fake_relay(tmp_path, username="relay_user", password=PASSWORD) as relay:
        answer = SmtpTransport(configured(relay), PASSWORD, context=relay.trusted).send(
            Message(to="someone@example.com", subject="Hello", body="A body.")
        )

    assert answer == MailAnswer(CallOutcome.OK)
    (one,) = relay.delivered
    assert (one.mail_from, one.rcpt_to, one.authenticated_as) == (
        "console@example.com",
        ["someone@example.com"],
        "relay_user",
    )
    parsed = message_from_bytes(one.data)
    assert (parsed["From"], parsed["To"], parsed["Subject"]) == (
        "console@example.com",
        "someone@example.com",
        "Hello",
    )
    assert all(secure for secure, line in relay.lines if line.upper().startswith("AUTH"))


def test_a_message_reaches_a_relay_that_is_tls_from_the_first_byte(tmp_path: Path) -> None:
    """Delete this and the second way of securing the connection is offered and never works."""
    with fake_relay(tmp_path, implicit_tls=True) as relay:
        answer = SmtpTransport(configured(relay, username=""), None, context=relay.trusted).send(
            Message(to="someone@example.com", subject="Hi", body="B.")
        )

    assert answer.outcome is CallOutcome.OK
    assert len(relay.delivered) == 1


def test_a_relay_that_will_not_upgrade_the_connection_is_refused_before_the_password_is_sent(
    tmp_path: Path,
) -> None:
    """**The password never crosses a plain connection.** A relay that does not offer STARTTLS is
    a refusal, and the relay saw no sign-in at all.

    Delete this and a transport that fell back to plain SMTP would send the password in the clear
    to anything answering on the port."""
    with fake_relay(
        tmp_path, username="relay_user", password=PASSWORD, offer_starttls=False
    ) as relay:
        answer = SmtpTransport(configured(relay), PASSWORD, context=relay.trusted).send(
            Message(to="someone@example.com", subject="Hi", body="B.")
        )

    assert answer.outcome is CallOutcome.REJECTED
    assert relay.delivered == []
    assert not any(line.upper().startswith("AUTH") for _, line in relay.lines)


def test_a_wrong_password_and_a_refused_recipient_are_refusals_told_by_code(
    tmp_path: Path,
) -> None:
    """Delete this and a relay's refusal reads as a message sent, or as a relay that did not answer,
    which sends somebody to check the network instead of the password."""
    with fake_relay(tmp_path, username="relay_user", password=PASSWORD) as relay:
        wrong = SmtpTransport(configured(relay), "not-it", context=relay.trusted).send(
            Message(to="someone@example.com", subject="Hi", body="B.")
        )
    with fake_relay(tmp_path, refuse_recipients=True) as relay:
        refused = SmtpTransport(configured(relay, username=""), None, context=relay.trusted).send(
            Message(to="nobody@example.com", subject="Hi", body="B.")
        )

    assert wrong == MailAnswer(CallOutcome.REJECTED, 535)
    assert refused == MailAnswer(CallOutcome.REJECTED, 550)


def test_a_certificate_for_another_host_is_not_a_relay_and_nothing_is_sent(tmp_path: Path) -> None:
    """The certificate is verified against the configured host. Delete this and a transport that
    skipped verification hands the password to whatever answers on that address."""
    from tests.fixtures.tls_certificate import certificate

    other, _ = certificate(tmp_path, "relay.elsewhere.test")
    import ssl

    trusts_another = ssl.create_default_context(cafile=str(other))
    with fake_relay(tmp_path, username="relay_user", password=PASSWORD) as relay:
        answer = SmtpTransport(configured(relay), PASSWORD, context=trusts_another).send(
            Message(to="someone@example.com", subject="Hi", body="B.")
        )

    assert answer.outcome is CallOutcome.UNAVAILABLE
    assert relay.delivered == []
    assert not any(line.upper().startswith("AUTH") for _, line in relay.lines)


def test_a_relay_that_hangs_up_is_unavailable_and_not_an_exception() -> None:
    """Delete this and a relay that is down raises out of the effect, which leaves the attempt
    unknown with a traceback instead of a sentence."""
    listener = socket.socket()
    listener.bind((LOOPBACK, 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def hang_up() -> None:
        accepted, _ = listener.accept()
        accepted.close()

    thread = threading.Thread(target=hang_up, daemon=True)
    thread.start()
    settings = MailSettings(LOOPBACK, port, Security.STARTTLS, "console@example.com", "")
    try:
        answer = SmtpTransport(settings, None, timeout_seconds=5.0).send(
            Message(to="someone@example.com", subject="Hi", body="B.")
        )
    finally:
        thread.join(timeout=5.0)
        listener.close()

    assert answer.outcome is CallOutcome.UNAVAILABLE


def test_a_transport_says_nothing_about_its_password_when_printed() -> None:
    """Delete this and an exception handler formatting the transport logs the relay's password."""
    settings = MailSettings("smtp.example.com", 587, Security.STARTTLS, "a@example.com", "user")
    assert PASSWORD not in repr(SmtpTransport(settings, PASSWORD))


# ------------------------------------------------------------------------------ the door
class _Transport:
    def __init__(self, *answers: MailAnswer) -> None:
        self.answers = list(answers)
        self.sent: list[Message] = []

    def send(self, message: Message) -> MailAnswer:
        self.sent.append(message)
        return self.answers.pop(0)


def test_pressing_the_test_button_twice_sends_one_message() -> None:
    """**The duplicate the door exists for.** Delete this and every press of the button is a message
    in somebody's inbox."""
    ledger = MemoryLedger()
    transport = _Transport(MailAnswer(CallOutcome.OK), MailAnswer(CallOutcome.OK))
    operation = trial_operation(actor="u_admin", version="v1", to="someone@example.com")

    first = send_trial(ledger, operation, transport, "someone@example.com")
    second = send_trial(ledger, operation, transport, "someone@example.com")

    assert (first.outcome, second.outcome) == (TrialOutcome.SENT, TrialOutcome.ALREADY_SENT)
    assert len(transport.sent) == 1
    assert ledger.records[operation.key].state is OperationState.SUCCEEDED


def test_a_new_configuration_or_another_address_is_another_message() -> None:
    """The positive half of the test above. Delete this and a key that never moved would test a
    relay once for ever."""
    ledger = MemoryLedger()
    transport = _Transport(*(MailAnswer(CallOutcome.OK) for _ in range(3)))
    for version, to in (("v1", "a@example.com"), ("v2", "a@example.com"), ("v1", "b@example.com")):
        sent = send_trial(
            ledger, trial_operation(actor="u_admin", version=version, to=to), transport, to
        )
        assert sent.outcome is TrialOutcome.SENT
    assert len(transport.sent) == 3


def test_a_relay_that_did_not_answer_is_unknown_and_pressing_again_sends_nothing() -> None:
    """Nobody knows whether it arrived, so it is not sent again under that configuration, and the
    sentence says to save the configuration again rather than that it failed.

    Delete this and a relay that answered slowly is sent the message again on every press."""
    ledger = MemoryLedger()
    transport = _Transport(MailAnswer(CallOutcome.UNAVAILABLE), MailAnswer(CallOutcome.OK))
    operation = trial_operation(actor="u_admin", version="v1", to="someone@example.com")

    first = send_trial(ledger, operation, transport, "someone@example.com")
    second = send_trial(ledger, operation, transport, "someone@example.com")

    assert (first.outcome, second.outcome) == (TrialOutcome.UNREACHABLE, TrialOutcome.UNSETTLED)
    assert len(transport.sent) == 1
    assert ledger.records[operation.key].state is OperationState.UNKNOWN


def test_a_refusal_is_told_with_its_code_and_pressing_again_is_still_a_refusal() -> None:
    """Delete this and a relay's refusal reads, on the second press, as a message already sent."""
    ledger = MemoryLedger()
    transport = _Transport(MailAnswer(CallOutcome.REJECTED, 535))
    operation = trial_operation(actor="u_admin", version="v1", to="someone@example.com")

    first = send_trial(ledger, operation, transport, "someone@example.com")
    second = send_trial(ledger, operation, transport, "someone@example.com")

    assert first.outcome is TrialOutcome.REFUSED and "535" in first.told
    assert second.outcome is TrialOutcome.REFUSED
    assert len(transport.sent) == 1


# --------------------------------------------------------------------------- the password
class _Vault:
    def __init__(
        self,
        *,
        held: StaticVersion | None = None,
        value: str | None = None,
        fail: Exception | None = None,
    ) -> None:
        self.held = held
        self.value = value
        self.fail = fail
        self.written: list[tuple[str, dict[str, str]]] = []

    def write_static_kv(self, path: str, fields: Any) -> datetime | None:
        if self.fail is not None:
            raise self.fail
        self.written.append((path, dict(fields)))
        return LONG_AGO

    def static_kv_version(self, path: str) -> StaticVersion | None:
        if self.fail is not None:
            raise self.fail
        return self.held

    def read_static_kv(self, path: str) -> dict[str, Any]:
        if self.fail is not None:
            raise self.fail
        if self.value is None:
            raise VaultRefusedError("absent", status=404)
        return {RELAY_CREDENTIAL_FIELD: self.value}


class _Writes:
    def __init__(self) -> None:
        self.recorded: list[dict[str, str]] = []

    async def record(self, *, slot: str, written_by: str, trace_id: str, ent_hash: str) -> None:
        self.recorded.append({"slot": slot, "written_by": written_by, "trace_id": trace_id})


def test_the_password_is_written_to_its_slot_read_back_only_to_send_and_recorded() -> None:
    """Delete this and the password lands at a slot nothing reads, or its write leaves no ledger
    entry while every other credential's does."""
    import asyncio

    vault, writes = _Vault(value=PASSWORD, held=StaticVersion(written_at=LONG_AGO)), _Writes()
    password = MailPassword(vault, writes)

    assert password.keep(f" {PASSWORD}\n", actor="u_admin") == LONG_AGO
    asyncio.run(password.record(actor="u_admin", trace_id="t-1", ent_hash="e"))

    assert vault.written == [(RELAY_CREDENTIAL_SLOT, {RELAY_CREDENTIAL_FIELD: PASSWORD})]
    assert writes.recorded == [
        {"slot": RELAY_CREDENTIAL_SLOT, "written_by": "u_admin", "trace_id": "t-1"}
    ]
    assert password.read() == PASSWORD
    assert password.held().held is True
    assert PASSWORD not in repr(password)
    assert RELAY_CREDENTIAL_SLOT.startswith("providers/")


@pytest.mark.parametrize(
    ("fail", "state"),
    [
        (VaultUnreachableError("x"), VaultState.UNREACHABLE),
        (VaultRefusedError("x", status=403), VaultState.REFUSED),
    ],
)
def test_a_vault_that_cannot_be_asked_says_which_problem_and_never_that_nothing_is_held(
    fail: Exception, state: VaultState
) -> None:
    """Delete this and a silent vault reads as a relay with no password, which sends somebody to
    replace one."""
    password = MailPassword(_Vault(fail=fail))
    for call in (password.held, password.read):
        with pytest.raises(MailPasswordUnavailableError) as raised:
            call()
        assert raised.value.state is state
    with pytest.raises(MailPasswordUnavailableError) as absent:
        MailPassword(None).held()
    assert absent.value.state is VaultState.ABSENT
    assert MailPassword(_Vault()).read() is None
