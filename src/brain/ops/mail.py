"""Email delivery: the relay an administrator configures, its password in the vault, and a send.

Nothing in this product could send an email. `brain.channels.email` reads mail a server received
and composes replies it never sends, and says so; no module opened an SMTP connection, no setting
named a relay, and a notice whose docstring said it "arrives by email" arrived nowhere. This module
is the sender and its configuration, and `brain.notification_routes` is where an administrator
sets both and proves them with a test message.

**The configuration is five values in `ops.setting` and the password is not one of them.** Host,
port, how the connection is secured, the sender address and the user name are written under
`mail.` with the writer's name on each row, for `brain.ops.setting_store`'s reasons. The password
goes into the vault at `providers/mail_relay` and is never read back to a person: the screen says
whether one is held and when it was written, from the slot's metadata. See
`A_RELAY_CREDENTIAL_IS_A_PROVIDER_CREDENTIAL`.

**A relay that speaks no TLS is refused.** Two ways of securing the connection are offered, a
connection upgraded with STARTTLS and one that is TLS from the first byte, and the certificate is
verified against the host in both. Plain SMTP would send the password and every message in the
clear across whatever network lies between this server and the relay. See
`MAIL_DOES_NOT_CROSS_A_NETWORK_IN_THE_CLEAR`.

**The relay's address is not put through the webhook address rule.** `brain.tools.fetch.
assert_fetchable` refuses anything only this network can reach, which is right for an address a
stranger's system is told events at and wrong for a relay, which is very often inside the network
by design and is chosen by an administrator holding the authority to choose it.

**Every send goes through `brain.ops.idempotency.issue_once`.** A test message is keyed on who
asked, the recipient and the configuration it tests, where the configuration's version moves every
time it is saved or the password is replaced. Pressing the button twice sends one message; saving
the configuration again, corrected or not, allows another. A relay that did not answer leaves the
attempt unknown, and the screen says that nobody knows whether it arrived rather than that it
failed. See `A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION`.

**A relay's refusal is told by its code and never its text.** An SMTP server's reply quotes the
address it refused and sometimes the user name it could not authenticate, and neither belongs in a
response or a log line that might be read by somebody else.

Rejected: an asynchronous SMTP library. The send runs inside the effect `issue_once` calls, which
is a plain callable, and the route moves the whole door onto a thread; `smtplib` needs no
dependency and no second event loop.

Task ids: M27.8.11
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import Final, Protocol

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from brain.ops.credentials import CredentialVault, CredentialWrites, VaultState, problems_with
from brain.ops.idempotency import (
    CallOutcome,
    Disposition,
    Intent,
    Operation,
    OperationLedger,
    OperationState,
    issue_once,
    operation_for,
)
from brain.ops.object_store import StaticKvReader
from brain.ops.openbao import VaultRefusedError, VaultUnreachableError
from brain.ops.secrets import SecretsUnavailableError
from brain.ops.setting_store import SettingState, put, read_namespace, values_under
from brain.tables.config import SettingType

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the relay password is kept in the providers engine.
A_RELAY_CREDENTIAL_IS_A_PROVIDER_CREDENTIAL: Final = (
    "A relay's password is issued by whoever runs the relay, is valid until they revoke it, and "
    "cannot be minted per message, which is what the providers engine holds: a credential a "
    "service provider issued that nothing can lease. It is read by the process that sends, which "
    "is the application, and that engine's policy already lets the application write, read and "
    "read the metadata of its slots. A new engine would be a second policy granting the same three "
    "verbs to the same role."
)

#: Why only TLS is offered.
MAIL_DOES_NOT_CROSS_A_NETWORK_IN_THE_CLEAR: Final = (
    "SMTP without TLS sends the password and every message in the clear across every network "
    "between this server and the relay. Both ways offered here encrypt the connection and verify "
    "the relay's certificate against its host name, so a relay that cannot do either is refused "
    "rather than used quietly."
)

#: Why a test message is keyed on the configuration it tests.
A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION: Final = (
    "The key is who asked, the recipient and the configuration's version, which moves whenever it "
    "is saved or the password is replaced. So a second press sends nothing, and an administrator "
    "who corrected the configuration, or saved it again after fixing the relay, can test again. A "
    "key that moved on every press would send a message per press, and one that never moved would "
    "test a configuration once for ever."
)

# ---------------------------------------------------------------------- the figures
#: The namespace the configuration is kept under in `ops.setting`.
MAIL_NAMESPACE: Final = "mail"

#: Where the relay's password is kept, and the field it is kept under.
RELAY_CREDENTIAL_SLOT: Final = "providers/mail_relay"
RELAY_CREDENTIAL_FIELD: Final = "password"

#: How long a relay may take to answer each step. A test is a person waiting at a screen.
SMTP_TIMEOUT_SECONDS: Final = 10.0

#: The connector and tool a test message's operation is recorded under.
MAIL_CONNECTOR: Final = "smtp"
TRIAL_TOOL: Final = "mail.test"

#: The longest host name DNS allows, and the longest address a mail system must accept.
MAX_HOST_CHARS: Final = 253
MAX_ADDRESS_CHARS: Final = 254
MAX_USERNAME_CHARS: Final = 256

_HOST_RE: Final = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)
_ADDRESS_RE: Final = re.compile(
    r"^[^@\s<>()\[\],;:\"]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$"
)

#: What a test message says. Names nothing about the install.
TRIAL_SUBJECT: Final = "A test message from the console"
TRIAL_BODY: Final = (
    "An administrator sent this from the console to check that email delivery is configured. "
    "Nothing needs to be done."
)


class Security(enum.StrEnum):
    """How the connection to the relay is secured. See the module docstring on plain SMTP."""

    #: A plain connection upgraded to TLS before anything else is said, usually port 587.
    STARTTLS = "starttls"
    #: TLS from the first byte, usually port 465.
    TLS = "tls"


class Field(enum.StrEnum):
    """The fields a configuration, a password or a test carries, as a problem names them."""

    HOST = "host"
    PORT = "port"
    SECURITY = "security"
    SENDER = "sender"
    USERNAME = "username"
    PASSWORD = "password"  # noqa: S105
    TO = "to"


@dataclass(frozen=True)
class FieldProblem:
    """One thing wrong with what was sent: which field, a stable code, and what to do."""

    field: Field
    code: str
    message: str


@dataclass(frozen=True)
class MailSettings:
    """A relay as an administrator configured it. No password: that is in the vault."""

    host: str
    port: int
    security: Security
    sender: str
    username: str


# ------------------------------------------------------------------- the judgements
def address_problems(field: Field, value: str) -> tuple[FieldProblem, ...]:
    """What is wrong with an email address, judged exactly as given."""
    if not value.strip():
        return (FieldProblem(field, "blank", "Give an email address."),)
    if len(value) > MAX_ADDRESS_CHARS or not _ADDRESS_RE.fullmatch(value):
        return (
            FieldProblem(
                field,
                "not_an_address",
                "Give one email address, such as someone@example.com, with nothing around it.",
            ),
        )
    return ()


def settings_problems(
    *, host: str, port: int, security: str, sender: str, username: str
) -> tuple[FieldProblem, ...]:
    """Every problem with a relay's configuration, in field order. Empty means it may be saved."""
    found: list[FieldProblem] = []
    if not host.strip():
        found.append(FieldProblem(Field.HOST, "blank", "Give the relay's host name."))
    elif len(host) > MAX_HOST_CHARS or not _HOST_RE.fullmatch(host):
        found.append(
            FieldProblem(
                Field.HOST,
                "not_a_host",
                "Give the host name alone, such as smtp.example.com: no scheme, no port and no "
                "spaces.",
            )
        )
    if not 1 <= port <= 65535:
        found.append(FieldProblem(Field.PORT, "out_of_range", "Give a port from 1 to 65535."))
    if security not in {one.value for one in Security}:
        found.append(
            FieldProblem(
                Field.SECURITY,
                "unknown",
                "Choose STARTTLS or TLS. A relay that offers neither cannot be used. "
                f"{MAIL_DOES_NOT_CROSS_A_NETWORK_IN_THE_CLEAR}",
            )
        )
    found.extend(address_problems(Field.SENDER, sender))
    if len(username) > MAX_USERNAME_CHARS or any(
        one.isspace() or not one.isprintable() for one in username
    ):
        found.append(
            FieldProblem(
                Field.USERNAME,
                "not_a_username",
                f"Give the user name alone, at most {MAX_USERNAME_CHARS} characters with no "
                "spaces, or leave it empty for a relay that asks for none.",
            )
        )
    return tuple(found)


#: What a person is told for each code `problems_with` gives, in a password's words.
PASSWORD_SENTENCES: Final = {
    "blank": "Paste the relay's password. It is never shown again.",
    "too_long": "That is longer than a password should be. Check that only it was copied.",
    "not_one_piece": (
        "The password has a space, a line break or a character that cannot be sent inside it. "
        "Copy it again without them."
    ),
}


def password_problems(value: str) -> tuple[FieldProblem, ...]:
    """What is wrong with a pasted password: `brain.ops.credentials.problems_with`'s judgement."""
    return tuple(
        FieldProblem(Field.PASSWORD, one.code, PASSWORD_SENTENCES.get(one.code, one.message))
        for one in problems_with(value)
    )


# ---------------------------------------------------------------------- the settings
async def settings_rows(session: AsyncSession) -> dict[str, SettingState]:
    """Every live configuration row, by field name."""
    return values_under(await read_namespace(session, MAIL_NAMESPACE), MAIL_NAMESPACE)


def settings_from_rows(rows: dict[str, SettingState]) -> MailSettings | None:
    """The configuration the rows hold, or None when any field is missing or not its type."""
    try:
        host, port, security = rows["host"].value, rows["port"].value, rows["security"].value
        sender, username = rows["sender"].value, rows["username"].value
    except KeyError:
        return None
    if not (
        isinstance(host, str)
        and isinstance(port, int)
        and not isinstance(port, bool)
        and isinstance(security, str)
        and security in {one.value for one in Security}
        and isinstance(sender, str)
        and isinstance(username, str)
    ):
        return None
    return MailSettings(
        host=host, port=port, security=Security(security), sender=sender, username=username
    )


async def save_settings(session: AsyncSession, settings: MailSettings, *, by: str) -> None:
    """Write the five values in the caller's transaction. The caller has judged them already."""
    values: tuple[tuple[str, SettingType, str | int, str], ...] = (
        ("host", SettingType.STRING, settings.host, "The relay's host name."),
        ("port", SettingType.INTEGER, settings.port, "The relay's port."),
        ("security", SettingType.STRING, settings.security.value, "How the relay is reached."),
        ("sender", SettingType.STRING, settings.sender, "The address mail is sent from."),
        ("username", SettingType.STRING, settings.username, "The user name the relay expects."),
    )
    for name, kind, value, description in values:
        await put(
            session,
            f"{MAIL_NAMESPACE}.{name}",
            value_type=kind,
            value=value,  # type: ignore[arg-type]
            description=description,
            updated_by=by,
        )


def last_saved(rows: dict[str, SettingState]) -> SettingState | None:
    """The row changed most recently, which says who last saved the configuration and when."""
    return max(rows.values(), key=lambda one: one.updated_at, default=None)


def configuration_version(
    settings: MailSettings, *, saved_at: datetime, password_written_at: datetime | None
) -> str:
    """A digest of the configuration a test would exercise and when each half last changed.

    See `A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION`. Hashed, so the key carries no host or address.
    """
    material = json.dumps(
        {
            "host": settings.host,
            "port": settings.port,
            "security": settings.security.value,
            "sender": settings.sender,
            "username": settings.username,
            "saved_at": saved_at.isoformat(),
            "password_written_at": (
                None if password_written_at is None else password_written_at.isoformat()
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:40]


# ---------------------------------------------------------------------- the password
class MailVault(CredentialVault, StaticKvReader, Protocol):
    """What the password needs from a vault: write a slot, read its metadata, read its value."""


class MailPasswordUnavailableError(Exception):
    """The vault could not be asked, or refused. `state` says which."""

    def __init__(self, state: VaultState) -> None:
        super().__init__(state.value)
        self.state = state


@dataclass(frozen=True)
class PasswordHeld:
    """Whether a password is held, and when its current version was written. Never the value."""

    held: bool
    written_at: datetime | None


class MailPassword:
    """This process's way to the relay password, or its lack of one. Holds no value.

    `writes` is where a kept password is recorded, which is `ops.credential_write` and the audit
    ledger's `credential` entry, the record every other credential written from the console leaves.
    """

    def __init__(self, vault: MailVault | None, writes: CredentialWrites | None = None) -> None:
        self._vault = vault
        self._writes = writes

    def __repr__(self) -> str:
        return f"MailPassword(configured={self.configured})"

    __str__ = __repr__

    @property
    def configured(self) -> bool:
        return self._vault is not None

    def _vault_or_refuse(self) -> MailVault:
        if self._vault is None:
            raise MailPasswordUnavailableError(VaultState.ABSENT)
        return self._vault

    def held(self) -> PasswordHeld:
        """Whether a password is held. Reads the slot's metadata, which holds no field of it."""
        vault = self._vault_or_refuse()
        try:
            version = vault.static_kv_version(RELAY_CREDENTIAL_SLOT)
        except VaultUnreachableError as silent:
            raise MailPasswordUnavailableError(VaultState.UNREACHABLE) from silent
        except SecretsUnavailableError as refused:
            raise MailPasswordUnavailableError(VaultState.REFUSED) from refused
        if version is None:
            return PasswordHeld(held=False, written_at=None)
        return PasswordHeld(held=True, written_at=version.written_at)

    def keep(self, value: str, *, actor: str) -> datetime | None:
        """Write the password and return the vault's time for it. The caller judged the value."""
        vault = self._vault_or_refuse()
        try:
            written = vault.write_static_kv(
                RELAY_CREDENTIAL_SLOT, {RELAY_CREDENTIAL_FIELD: value.strip()}
            )
        except VaultUnreachableError as silent:
            log.info("relay password not kept", actor=actor)
            raise MailPasswordUnavailableError(VaultState.UNREACHABLE) from silent
        except SecretsUnavailableError as refused:
            log.info("relay password not kept", actor=actor)
            raise MailPasswordUnavailableError(VaultState.REFUSED) from refused
        log.info("relay password kept", actor=actor)
        return written

    async def record(self, *, actor: str, trace_id: str, ent_hash: str) -> None:
        """Record a password already kept, and never raise: it is in the vault either way.

        `brain.ops.credentials.Credentials._record`'s rule and reasons, for this slot.
        """
        if self._writes is None:
            log.warning("relay password write has no ledger to be recorded in", actor=actor)
            return
        try:
            await self._writes.record(
                slot=RELAY_CREDENTIAL_SLOT, written_by=actor, trace_id=trace_id, ent_hash=ent_hash
            )
        except Exception as exc:
            log.error("relay password write not recorded", actor=actor, error=type(exc).__name__)

    def read(self) -> str | None:
        """The password, for the one call that sends with it, or None when none is held."""
        vault = self._vault_or_refuse()
        try:
            fields = vault.read_static_kv(RELAY_CREDENTIAL_SLOT)
        except VaultRefusedError as refused:
            if refused.status == 404:
                return None
            raise MailPasswordUnavailableError(VaultState.REFUSED) from refused
        except VaultUnreachableError as silent:
            raise MailPasswordUnavailableError(VaultState.UNREACHABLE) from silent
        except SecretsUnavailableError as refused:
            raise MailPasswordUnavailableError(VaultState.REFUSED) from refused
        value = fields.get(RELAY_CREDENTIAL_FIELD)
        return value if isinstance(value, str) and value else None


# ------------------------------------------------------------------------ the send
@dataclass(frozen=True)
class Message:
    """One message: a recipient, a subject and a plain-text body."""

    to: str
    subject: str
    body: str


@dataclass(frozen=True)
class MailAnswer:
    """What the relay did with one message: its outcome, and its reply code when it refused."""

    outcome: CallOutcome
    code: int | None = None


class MailTransport(Protocol):
    """Whatever hands a message to a relay. `SmtpTransport` is one."""

    def send(self, message: Message) -> MailAnswer: ...


class SmtpTransport:
    """`MailTransport` over `smtplib`, with TLS verified against the relay's host name.

    Holds the password for as long as the instance lives, which is one request: the route builds
    one per test and drops it. `context` is a parameter so a test can trust its own certificate.
    """

    def __init__(
        self,
        settings: MailSettings,
        password: str | None,
        *,
        timeout_seconds: float = SMTP_TIMEOUT_SECONDS,
        context: ssl.SSLContext | None = None,
    ) -> None:
        self._settings = settings
        self._password = password
        self._timeout = timeout_seconds
        self._context = context if context is not None else ssl.create_default_context()

    def __repr__(self) -> str:
        return f"SmtpTransport(host={self._settings.host!r}, port={self._settings.port})"

    __str__ = __repr__

    def _connect(self) -> smtplib.SMTP:
        settings = self._settings
        if settings.security is Security.TLS:
            return smtplib.SMTP_SSL(
                settings.host, settings.port, timeout=self._timeout, context=self._context
            )
        connection = smtplib.SMTP(settings.host, settings.port, timeout=self._timeout)
        try:
            connection.starttls(context=self._context)
        except BaseException:
            connection.close()
            raise
        return connection

    def send(self, message: Message) -> MailAnswer:
        settings = self._settings
        built = EmailMessage()
        built["From"] = settings.sender
        built["To"] = message.to
        built["Subject"] = message.subject
        built.set_content(message.body)
        try:
            connection = self._connect()
        except smtplib.SMTPNotSupportedError:
            return MailAnswer(CallOutcome.REJECTED)
        except smtplib.SMTPResponseException as refused:
            return MailAnswer(CallOutcome.REJECTED, refused.smtp_code)
        except (OSError, smtplib.SMTPException):
            return MailAnswer(CallOutcome.UNAVAILABLE)
        try:
            if settings.username:
                connection.login(settings.username, self._password or "")
            connection.send_message(built)
        except smtplib.SMTPRecipientsRefused as refused:
            codes = [code for code, _ in refused.recipients.values()]
            return MailAnswer(CallOutcome.REJECTED, codes[0] if codes else None)
        except smtplib.SMTPResponseException as refused:
            return MailAnswer(CallOutcome.REJECTED, refused.smtp_code)
        except smtplib.SMTPNotSupportedError:
            return MailAnswer(CallOutcome.REJECTED)
        except (OSError, smtplib.SMTPException):
            return MailAnswer(CallOutcome.UNAVAILABLE)
        finally:
            try:
                connection.quit()
            except (OSError, smtplib.SMTPException):
                connection.close()
        return MailAnswer(CallOutcome.OK)


class TrialOutcome(enum.StrEnum):
    """What pressing the test button came to."""

    SENT = "sent"
    REFUSED = "refused"
    UNREACHABLE = "unreachable"
    ALREADY_SENT = "already_sent"
    UNSETTLED = "unsettled"


#: What a person is told for each outcome.
TRIAL_TOLD: Final = {
    TrialOutcome.SENT: (
        "The relay accepted the test message. If it does not arrive, look in the relay's own log "
        "and the recipient's spam folder."
    ),
    TrialOutcome.REFUSED: (
        "The relay refused the test message. Check the host, port, security, sender, user name and "
        "password, save the corrected configuration, and test again."
    ),
    TrialOutcome.UNREACHABLE: (
        "The relay did not answer, or the connection or its certificate failed, so nobody knows "
        "whether the message was accepted. Check the host, port and security, save the "
        "configuration again, and test again."
    ),
    TrialOutcome.ALREADY_SENT: (
        "A test message to this address was already accepted under this configuration, so nothing "
        "was sent again. Save the configuration again, or choose another address, to send another."
    ),
    TrialOutcome.UNSETTLED: (
        "A test message to this address was already sent under this configuration and never "
        "answered, so nothing was sent again. Save the configuration again to test again."
    ),
}


@dataclass(frozen=True)
class Trial:
    """What one press of the test button did, and the relay's code when it refused."""

    outcome: TrialOutcome
    code: int | None = None

    @property
    def told(self) -> str:
        said = TRIAL_TOLD[self.outcome]
        return said if self.code is None else f"{said} The relay's reply code was {self.code}."


def trial_operation(*, actor: str, version: str, to: str) -> Operation:
    """The operation one test message is: who asked, of which configuration, to whom."""
    return operation_for(
        Intent(principal_id=actor, intent_ref=f"mail_test.{version}"),
        connector=MAIL_CONNECTOR,
        tool=TRIAL_TOOL,
        arguments={"to": to},
    )


def send_trial(
    ledger: OperationLedger, operation: Operation, transport: MailTransport, to: str
) -> Trial:
    """Send one test message through `issue_once`, and say what came of it."""
    answered: list[MailAnswer] = []

    def post(_: Operation) -> CallOutcome:
        answer = transport.send(Message(to=to, subject=TRIAL_SUBJECT, body=TRIAL_BODY))
        answered.append(answer)
        return answer.outcome

    issued = issue_once(ledger, operation, post)
    if issued.issued and answered:
        answer = answered[-1]
        if answer.outcome is CallOutcome.OK:
            return Trial(TrialOutcome.SENT)
        if answer.outcome is CallOutcome.UNAVAILABLE:
            return Trial(TrialOutcome.UNREACHABLE)
        return Trial(TrialOutcome.REFUSED, answer.code)
    found = issued.resumption
    if found is not None and found.disposition is Disposition.DONE:
        return Trial(TrialOutcome.ALREADY_SENT)
    if issued.operation.state is OperationState.FAILED:
        return Trial(TrialOutcome.REFUSED)
    return Trial(TrialOutcome.UNSETTLED)
