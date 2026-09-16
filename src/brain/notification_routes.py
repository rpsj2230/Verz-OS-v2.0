"""The Notifications screen over HTTP: who is told what, the switch that stops it, and email.

`brain.ops.notices` holds every kind of notice this product composes and whether a person may
switch it off, and `brain.ops.mail` holds the relay's configuration, its password and the one send.
This module asks each of them in order and decides nothing either decides.

**One authority for the read and every write, held over everything.** `admin:notification` is
asked at `brain.console.govern.NOWHERE`, which only an unrestricted grant admits, before the
database or the vault is reached, for `brain.feature_routes`' reasons: a notice is switched for the
whole install and a relay is the install's, so there is no department's version of either, and a
caller without the authority is refused identically on an install with a database and one without.

**Every write is judged whole before anything is written, and the answers are the Webhooks
screen's four.** 200 with what changed and when. 422 with every problem by field and code. 409
when the install runs no vault, the vault refused, a notice has no switch or the relay is not
configured, and 503 when the vault did not answer, each with a sentence saying what to do.

**No response carries the password, and a refused body is not echoed.** The router is
`brain.api.NoEchoRoute`. What a person is told about the password is whether one is held and
when it was written, from the slot's metadata.

**A test message is sent from this process, with this process's vault, through `issue_once`.**
The ledger is `brain.ops.operation_store.PostgresOperationLedger` on a connection of its own in
autocommit mode, opened for the one send on the same thread as the send; see
`brain.ops.mail.A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION` for the key.

**Every change keeps its last writer on the row, and the audit ledger keeps every one.** A notice
switch and the relay's configuration are `ops.setting` rows, which `0059`'s trigger records as
`setting` entries naming the key and the writer and never the value; the page says so as a
field. The password is a credential write and leaves the `credential` entry every other one
does.

Task ids: M27.8.11, M27.7.12
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any, Final

import psycopg
import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, NoEchoRoute
from brain.api_routes import Asked
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.db import libpq_url
from brain.install_routes import settings_of
from brain.ops.credential_write_store import credential_writes_for
from brain.ops.credentials import TOLD as VAULT_TOLD
from brain.ops.credentials import VaultState
from brain.ops.idempotency import OperationLedger
from brain.ops.mail import (
    MAIL_DOES_NOT_CROSS_A_NETWORK_IN_THE_CLEAR,
    Field,
    FieldProblem,
    MailPassword,
    MailPasswordUnavailableError,
    MailSettings,
    MailTransport,
    PasswordHeld,
    Security,
    SmtpTransport,
    TrialOutcome,
    address_problems,
    configuration_version,
    last_saved,
    password_problems,
    save_settings,
    send_trial,
    settings_from_rows,
    settings_problems,
    settings_rows,
    trial_operation,
)
from brain.ops.notices import (
    A_NOTICE_SHIPS_ON,
    NOTICES,
    Notice,
    NoticeError,
    notice,
    switch,
    switch_states,
    switched_off_in,
)
from brain.ops.openbao import OpenBaoVault
from brain.ops.operation_store import PostgresOperationLedger
from brain.ops.secrets import VaultRole
from brain.ops.setting_store import (
    A_SWITCH_SHOWS_ITS_LAST_CHANGE_AND_THE_LEDGER_KEEPS_EVERY_ONE,
    SettingState,
)
from brain.routing_routes import sessions_of

log = structlog.get_logger()

# ------------------------------------------------------------------------ the figures
#: Reads the Notifications screen and makes every change on it. Held over everything or not at all.
NOTIFICATION_AUTHORITY: Final = Capability(value="admin:notification")

#: The screen's name in a refusal, identical on every install.
NOTIFICATIONS_SCREEN: Final = "notifications"

NOTIFICATIONS_PATH: Final = "/notifications"
NOTICE_PATH: Final = f"{NOTIFICATIONS_PATH}/notices/{{kind}}"
EMAIL_PATH: Final = f"{NOTIFICATIONS_PATH}/relay"
PASSWORD_PATH: Final = f"{EMAIL_PATH}/password"
TRIAL_PATH: Final = f"{EMAIL_PATH}/test"

#: The confirmation's consequence for each write, in the words a person agrees to.
SWITCHING_OFF: Final = (
    "Nobody is sent this notice from now on, and nothing is kept to send later. Switch it on again "
    "to start again from the next one."
)
SWITCHING_ON: Final = "This notice is sent again from the next one."
SAVING_EMAIL: Final = (
    "Mail is sent through this relay from now on, from this sender address. Saving again allows "
    "another test message."
)
KEEPING_THE_RELAY_CREDENTIAL: Final = (
    "The relay's password is replaced in the vault and used for every message from now on. It "
    "cannot be shown or restored from here."
)
SENDING_TRIAL: Final = (
    "One test message is sent to this address through the saved relay. It is sent once for each "
    "saved configuration."
)

#: What a person is told about who sends email today.
WHAT_EMAIL_IS_USED_FOR: Final = (
    "Email is used by the test message on this screen today. No notice is sent by email yet: each "
    "notice below says how it would reach people and whether anything sends it."
)

#: What a person is told about subscribers, which are managed on their own screen.
SUBSCRIBERS_ARE_ON_THE_WEBHOOKS_SCREEN: Final = (
    "Systems outside the company that are told when something happens here are webhook "
    "subscribers, listed and switched off on the Webhooks screen."
)

#: Said when a test is asked for and the relay is not configured.
NOT_CONFIGURED: Final = (
    "No relay is configured, so no test message was sent. Save the relay's host, port, security "
    "and sender first."
)

#: Said when the relay asks for a user name and no password is held.
NO_RELAY_CREDENTIAL_HELD: Final = (
    "The relay's configuration names a user name and no password is held for it, so no test "
    "message was sent. Save the password first."
)

#: The status a write that kept nothing answers, by the vault's state.
NOT_KEPT_STATUS: Final = {
    VaultState.ABSENT: 409,
    VaultState.REFUSED: 409,
    VaultState.UNREACHABLE: 503,
}


# ------------------------------------------------------------------------ the shapes
class NoticeView(BaseModel):
    """One kind of notice, whether it is on, and who last switched it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    title: str
    told: str
    about: str
    how: str
    sent: bool
    switchable: bool
    fixed_because: str
    on: bool
    changed_by: str | None
    changed_at: datetime | None


class RelayPasswordView(BaseModel):
    """Whether the relay's password is held. `held` is None when the vault could not be asked."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    held: bool | None
    written_at: datetime | None
    vault: VaultState
    vault_told: str


class RelayView(BaseModel):
    """The relay as saved, or every field null when nothing is saved. Never the password."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    configured: bool
    host: str | None
    port: int | None
    security: Security | None
    sender: str | None
    username: str | None
    changed_by: str | None
    changed_at: datetime | None
    password: RelayPasswordView


class NotificationsPage(BaseModel):
    """The Notifications screen: every notice, the relay, and what this screen cannot do."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    notices: list[NoticeView]
    email: RelayView
    securities: list[Security]
    email_used_for: str
    subscribers: str
    ships_on: str
    only_the_last_change_is_kept: str
    switching_off: str
    switching_on: str
    saving_email: str
    keeping_password: str
    sending_trial: str
    plain_smtp_refused: str


class NoticeSwitchAsked(BaseModel):
    """Switch one notice on or off. Required, so what is sent is what the screen displayed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    on: bool


class RelayAsked(BaseModel):
    """A relay's configuration. No length on any field: `settings_problems` judges them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str
    port: int
    security: str
    sender: str
    username: str


class RelayPasswordAsked(BaseModel):
    """The relay's password."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    password: str


class RelayTrialAsked(BaseModel):
    """Where a test message is sent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    to: str


class RelayPasswordKeptView(BaseModel):
    """The password was written. When, and what that means. Never the password."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    written_at: datetime | None
    told: str


class RelayTrialView(BaseModel):
    """What a test message came to, in words to act on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: TrialOutcome
    told: str


class NotificationProblemView(BaseModel):
    """One thing wrong with what was sent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: Field
    code: str
    message: str


class NotificationProblemsView(BaseModel):
    """Everything wrong with what was sent. Nothing was written."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    problems: list[NotificationProblemView]


# ------------------------------------------------------------------------ the decisions
def may_manage_notifications(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may read the screen and change anything on it: the authority, over
    everything."""
    return _in_reach(reach, NOTIFICATION_AUTHORITY, NOWHERE, now)


def notice_view(one: Notice, state: SettingState | None, *, on: bool) -> NoticeView:
    return NoticeView(
        kind=one.kind.value,
        title=one.title,
        told=one.told,
        about=one.about,
        how=one.how,
        sent=bool(one.sent_by),
        switchable=one.switchable,
        fixed_because=one.fixed_because,
        on=on,
        changed_by=state.updated_by if state is not None and one.switchable else None,
        changed_at=state.updated_at if state is not None and one.switchable else None,
    )


def notice_views(states: dict[str, SettingState]) -> list[NoticeView]:
    """Every notice in declaration order, on unless a person switched a switchable one off."""
    off = switched_off_in(states)
    return [notice_view(one, states.get(one.kind.value), on=one.kind not in off) for one in NOTICES]


def email_view(rows: dict[str, SettingState], password: RelayPasswordView) -> RelayView:
    saved = settings_from_rows(rows)
    last = last_saved(rows)
    return RelayView(
        configured=saved is not None,
        host=None if saved is None else saved.host,
        port=None if saved is None else saved.port,
        security=None if saved is None else saved.security,
        sender=None if saved is None else saved.sender,
        username=None if saved is None else saved.username,
        changed_by=None if last is None else last.updated_by,
        changed_at=None if last is None else last.updated_at,
        password=password,
    )


def password_view(mail_password: MailPassword) -> tuple[RelayPasswordView, PasswordHeld | None]:
    """Whether a password is held, or not known with the vault's state. Metadata only."""
    try:
        held = mail_password.held()
    except MailPasswordUnavailableError as unavailable:
        return (
            RelayPasswordView(
                held=None,
                written_at=None,
                vault=unavailable.state,
                vault_told=VAULT_TOLD[unavailable.state],
            ),
            None,
        )
    return (
        RelayPasswordView(
            held=held.held,
            written_at=held.written_at,
            vault=VaultState.READY,
            vault_told=VAULT_TOLD[VaultState.READY],
        ),
        held,
    )


# ------------------------------------------------------------------------ the wiring
def mail_password_of(request: Request) -> MailPassword:
    """What `app.state.mail_password` holds, or this process's vault, or no vault at all."""
    found = getattr(request.app.state, "mail_password", None)
    if isinstance(found, MailPassword):
        return found
    settings = settings_of(request)
    writes = credential_writes_for(sessions_of(request))
    if not settings.vault_address or not settings.vault_token:
        return MailPassword(None, writes)
    try:
        vault = OpenBaoVault(
            settings.vault_address, settings.vault_token, role=VaultRole.APPLICATION
        )
    except ValueError:
        return MailPassword(None, writes)
    return MailPassword(vault, writes)


def transport_of(request: Request) -> Callable[[MailSettings, str | None], MailTransport]:
    """How this process builds a transport: `app.state.mail_transport`, or SMTP."""
    found = getattr(request.app.state, "mail_transport", None)
    if callable(found):
        return found  # type: ignore[no-any-return]
    return lambda settings, password: SmtpTransport(settings, password)


def _sessions(request: Request) -> Any:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _not_answerable() -> Absent:
    return Absent(f"the {NOTIFICATIONS_SCREEN} screen is not answerable for this caller")


def _problems(found: tuple[FieldProblem, ...]) -> JSONResponse:
    told = NotificationProblemsView(
        problems=[
            NotificationProblemView(field=one.field, code=one.code, message=one.message)
            for one in found
        ]
    )
    return JSONResponse(status_code=422, content=told.model_dump(mode="json"))


def _refused(status: int, message: str) -> JSONResponse:
    body = ErrorBody(message=message, trace_id=_trace_id())
    return JSONResponse(status_code=status, content=body.model_dump())


def _not_kept(state: VaultState) -> JSONResponse:
    return _refused(NOT_KEPT_STATUS[state], VAULT_TOLD[state])


def trial_in_a_thread(
    request: Request,
    work: Callable[[OperationLedger], Any],
) -> Any:
    """Run `work` with this process's operation ledger, on the thread the caller is on.

    `app.state.operation_ledger` for a test; otherwise a connection of its own in autocommit mode,
    opened and closed around the one send. See the module docstring.
    """
    found = getattr(request.app.state, "operation_ledger", None)
    if found is not None:
        return work(found)
    url = settings_of(request).database_url
    with psycopg.connect(libpq_url(url), autocommit=True, prepare_threshold=None) as conn:
        return work(PostgresOperationLedger(conn))


router = APIRouter(prefix=API_PREFIX, tags=["notifications"], route_class=NoEchoRoute)

_WRITE_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    422: {"model": NotificationProblemsView, "description": "What is wrong with what was sent."},
}


@router.get(NOTIFICATIONS_PATH, response_model=NotificationsPage, responses=COMMON_RESPONSES)
async def notifications(request: Request, asked: Asked) -> NotificationsPage:
    """Every notice, whether it is on, and the relay, for a caller who may change them."""
    if not may_manage_notifications(asked.reach, asked.now):
        log.info("notifications screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    async with _sessions(request)() as session:
        states = await switch_states(session)
        rows = await settings_rows(session)
    password, _ = await asyncio.to_thread(password_view, mail_password_of(request))
    return NotificationsPage(
        notices=notice_views(states),
        email=email_view(rows, password),
        securities=list(Security),
        email_used_for=WHAT_EMAIL_IS_USED_FOR,
        subscribers=SUBSCRIBERS_ARE_ON_THE_WEBHOOKS_SCREEN,
        ships_on=A_NOTICE_SHIPS_ON,
        only_the_last_change_is_kept=A_SWITCH_SHOWS_ITS_LAST_CHANGE_AND_THE_LEDGER_KEEPS_EVERY_ONE,
        switching_off=SWITCHING_OFF,
        switching_on=SWITCHING_ON,
        saving_email=SAVING_EMAIL,
        keeping_password=KEEPING_THE_RELAY_CREDENTIAL,
        sending_trial=SENDING_TRIAL,
        plain_smtp_refused=MAIL_DOES_NOT_CROSS_A_NETWORK_IN_THE_CLEAR,
    )


@router.post(NOTICE_PATH, response_model=NoticeView, responses=COMMON_RESPONSES)
async def switch_notice(
    request: Request, kind: str, body: NoticeSwitchAsked, asked: Asked
) -> NoticeView | JSONResponse:
    """Switch one notice on or off, and answer with what the database now holds.

    The authority first, then the name, then whether it has a switch, then the write.
    """
    if not may_manage_notifications(asked.reach, asked.now):
        log.info("notice switch refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    try:
        one = notice(kind)
    except NoticeError:
        message = f"that notice was not switched: {kind!r} is not a notice this product composes"
        raise Absent(message, public_message=message) from None
    if not one.switchable:
        return _refused(409, f"{one.title} has no switch. {one.fixed_because}")
    async with _sessions(request)() as session:
        await switch(session, one, on=body.on, by=asked.caller.principal.id)
        states = await switch_states(session)
        await session.commit()
    log.info(
        "notice switched", notice=one.kind.value, on=body.on, principal=asked.caller.principal.id
    )
    return notice_views(states)[NOTICES.index(one)]


@router.post(EMAIL_PATH, response_model=RelayView, responses=_WRITE_RESPONSES)
async def save_email(request: Request, body: RelayAsked, asked: Asked) -> JSONResponse:
    """Save the relay's configuration, or write nothing and say every problem."""
    if not may_manage_notifications(asked.reach, asked.now):
        log.info("email configuration refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    found = settings_problems(
        host=body.host,
        port=body.port,
        security=body.security,
        sender=body.sender,
        username=body.username,
    )
    if found:
        return _problems(found)
    settings = MailSettings(
        host=body.host,
        port=body.port,
        security=Security(body.security),
        sender=body.sender,
        username=body.username,
    )
    async with _sessions(request)() as session:
        await save_settings(session, settings, by=asked.caller.principal.id)
        rows = await settings_rows(session)
        await session.commit()
    password, _ = await asyncio.to_thread(password_view, mail_password_of(request))
    log.info("email configuration saved", principal=asked.caller.principal.id)
    answered = email_view(rows, password)
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))


@router.post(PASSWORD_PATH, response_model=RelayPasswordKeptView, responses=_WRITE_RESPONSES)
async def keep_password(request: Request, body: RelayPasswordAsked, asked: Asked) -> JSONResponse:
    """Write the relay's password into the vault and record the write, or write nothing."""
    if not may_manage_notifications(asked.reach, asked.now):
        log.info("relay password refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    found = password_problems(body.password)
    if found:
        return _problems(found)
    mail_password = mail_password_of(request)
    if not mail_password.configured:
        return _not_kept(VaultState.ABSENT)
    actor = asked.reach.principal_id
    try:
        written = await asyncio.to_thread(mail_password.keep, body.password, actor=actor)
    except MailPasswordUnavailableError as unavailable:
        return _not_kept(unavailable.state)
    await mail_password.record(actor=actor, trace_id=_trace_id(), ent_hash=asked.reach.ent_hash())
    answered = RelayPasswordKeptView(written_at=written, told=KEEPING_THE_RELAY_CREDENTIAL)
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))


@router.post(TRIAL_PATH, response_model=RelayTrialView, responses=_WRITE_RESPONSES)
async def send_trial_message(request: Request, body: RelayTrialAsked, asked: Asked) -> JSONResponse:
    """Send one test message through the saved relay, once per saved configuration."""
    if not may_manage_notifications(asked.reach, asked.now):
        log.info("test message refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    found = address_problems(Field.TO, body.to)
    if found:
        return _problems(found)
    async with _sessions(request)() as session:
        rows = await settings_rows(session)
    settings = settings_from_rows(rows)
    last = last_saved(rows)
    if settings is None or last is None:
        return _refused(409, NOT_CONFIGURED)
    mail_password = mail_password_of(request)
    build = transport_of(request)
    actor = asked.reach.principal_id

    def send() -> RelayTrialView | JSONResponse:
        password: str | None = None
        written_at: datetime | None = None
        if settings.username:
            if not mail_password.configured:
                return _not_kept(VaultState.ABSENT)
            try:
                held = mail_password.held()
                password = mail_password.read() if held.held else None
            except MailPasswordUnavailableError as unavailable:
                return _not_kept(unavailable.state)
            if password is None:
                return _refused(409, NO_RELAY_CREDENTIAL_HELD)
            written_at = held.written_at
        version = configuration_version(
            settings, saved_at=last.updated_at, password_written_at=written_at
        )
        operation = trial_operation(actor=actor, version=version, to=body.to)
        transport = build(settings, password)
        trial = trial_in_a_thread(
            request, lambda ledger: send_trial(ledger, operation, transport, body.to)
        )
        return RelayTrialView(outcome=trial.outcome, told=trial.told)

    answered = await asyncio.to_thread(send)
    if isinstance(answered, JSONResponse):
        return answered
    log.info("test message", outcome=answered.outcome.value, principal=actor)
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))
