"""Channels over HTTP: the address a vendor posts to, and a channel's record, switch and history.

`brain.channels.inbound` decides how a request is received and `brain.channels.outbound` how a
message leaves; `brain.ops.channel_store` keeps the rows and borrows the secret. This module
asks them in order, builds the one transport, and decides nothing any of them already decides.
CH2 draws the Channels screen over these routes; until then they are how a channel is set up and
proved on an install.

**`POST /channels/{name}/events` is the one address every vendor posts to (M10.2.1).** It takes
no caller, because a vendor has no session: what it proves is the signature, and the route hands
the exact bytes to the channel's wire through `receive`, which refuses a switched-off channel
before the body is read and a bad signature before the wire reads it. A name that is no channel,
a channel this release has no receiver for, a channel with no record and a channel switched off
are one 404 with one body, so the address cannot be walked to learn which channels an install
runs. See `AN_ADDRESS_A_VENDOR_POSTS_TO_SAYS_NOTHING_ABOUT_THE_INSTALL`. An accepted message from
a sender bound to nobody is answered with the binding prompt, sent back through the channel's own
vendor and recorded like any other delivery.

**One authority governs a channel, and it is the one Connect Lark already asks.**
`brain.ops.connector_admin.may_connect_source` over `<channel>_channel`, which is the slot name
`brain.ops.lark_connect` gives the Lark chat use, so the administrator who may switch Lark's chat
on there is the one who may switch its channel record here, and a grant narrowed to one channel
reaches that channel alone. A reader without it for a channel is shown nothing about that channel
and is refused on it as on a channel that does not exist. See
`A_CHANNEL_IS_GOVERNED_BY_THE_AUTHORITY_CONNECT_LARK_ASKS`.

**Every set-up, switch and secret replacement is in the audit ledger, naming the channel and never
the secret.** The record's write carries the caller, their reach digest and the trace to
`brain.ops.channel_store`, and `0114`'s trigger appends a `setting` entry under
`setting:channel.<channel>` saying `set`, `switched_on` or `switched_off`. The secret goes through
`brain.ops.credentials.Credentials.keep`, whose record is `0054`'s `credential` entry under the
channel's slot, with nothing of the value. See `EVERY_CHANGE_TO_A_CHANNEL_IS_AUDITED`.

**The secret is written into the vault before the record, and is never sent back.** The router is
`brain.api.NoEchoRoute`, the secret is kept through `brain.ops.credentials.Credentials.keep`, which
records the write in the audit ledger, and a response says only whether a secret is held. A vault
that is absent, refused or silent answers 409 or 503 and no record is written, so a channel is
never switched on by this route with nothing behind it.

**A test message goes out through the same `deliver` every reply does.** It is a product sentence
with no recipient, keyed on who asked, where to and the record's last change, so a second press
sends nothing and a record changed since can be tested again, for
`brain.ops.mail.A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION`'s reason. On a channel switched off it is
refused and recorded as `switched_off`, which is how an install shows that switching a channel off
stops its sending.

**The transport is one class for every channel.** `HttpsTransport` checks the vendor's address
with `brain.tools.fetch.assert_fetchable` at every send and connects to the address it checked,
through `brain.ops.webhook_delivery.HttpsSender`, so no channel has its own HTTP client and none
can skip the address rule. It keeps the vendor's answer, because Lark refuses inside a 200; makes a
request's token exchange immediately before it, because Lark authorises with a token minted from
the App ID and App Secret; and has a `read` beside `send`, a GET for who is in a conversation,
which `brain.ops.effects` classifies as a read so no send can go by it.

**A press on an approval card is decided while Lark waits, and its card is closed after
(M10.2.3, M10.2.4).** A press is claimed like a message and handed to
`brain.approval_cards.ApprovalCards`, which decides it through the Approvals route's own
`take_decision` as the bound approver, and the vendor is answered in the wire's words: a toast,
and for a press that decided nothing the card replaced by a closed one in the same answer. A card
a press did decide is replaced after the answer has gone, by the rate-limited patch, and the text
fallback goes to the approver's own chat when the patch was not delivered. A bound sender's
decision word in a message is answered by the same object's `offer` and decides nothing (M10.7.1).

**A chat message is acknowledged before it is answered, and answered by the gate as the bound
person.** A chat vendor posts again after a few seconds of silence, so a message that arrived with
a conversation is answered 200 once claimed and its reply is made after the response, recorded in
the channel's deliveries like any other (`A_CHAT_IS_ACKNOWLEDGED_BEFORE_IT_IS_ANSWERED`). The reply
is `brain.chat_answer.ChatAnswerer`'s on any process with a gate, and a code sent by an unbound
sender is offered to `brain.ops.binding_store.StoredBinder` on any process with a database, which
binds it once against `auth.binding_code` and keeps the binding in `auth.principal_identity`
(CH2); `bindings_of` reads the same table.

**A request for the mail relay leaves by the relay, and every other by HTTPS.** Each delivery's
transport is `brain.channels.relay.RelayingTransport` over the one above, so the email wire's
`RELAY_URL` goes to the relay saved on Notifications (`relay_of`): its settings read from
`ops.setting` on this request's event loop, its password borrowed from the vault on the send's own
thread, and both dropped with the message. A relay not set up sends nothing and is recorded as
refused. See `brain.channels.relay.ONE_RELAY_SERVES_EVERY_MESSAGE_THIS_INSTALL_SENDS`.

**A channel whose vendor needs two secrets takes them as parts, and keeps them whole.** A wire
naming `secret_parts` is saved with every part at once, as one JSON object in its one slot, or with
none to keep the ones held; a single `secret` is refused for it, and parts for any other. See
`brain.channels.adapter.SEVERAL_PARTS_ARE_WRITTEN_AS_ONE`.

**A channel's connect steps and the address to paste ride on its view.** `steps_of` serves the
channel's `GUIDE` and `events_address_of` the events address in full, built on the install setting
that already names this install's public address, as Lark's is; both are empty for a channel with
none, so the console draws a flow only where one was declared.

Task ids: M10.2.1, M10.6.1, M10.6.3, M10.3.3, M10.4.5, M3.2.2, M10.2.6, M1.8.5, M10.5.6, M10.5.1
Task ids: M10.2.3, M10.2.4, M10.7.1
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from datetime import UTC, datetime
from typing import Annotated, Final, cast
from urllib.parse import urlsplit

import psycopg
import structlog
from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, NoEchoRoute
from brain.api_routes import Asked, wiring_of
from brain.approval_cards import (
    PRESS_NOT_TAKEN_TOLD,
    ApprovalCards,
    card_windows_of,
    closed_after,
)
from brain.attribution import trace_of_request
from brain.channels.adapter import (
    CardWire,
    ChannelTransport,
    ChannelWire,
    KeyedWire,
    RegisteredWire,
    RegistrationRefusedError,
    VendorAnswer,
    VendorRequest,
    channel_adapters,
    channel_guides,
    channel_wires,
)
from brain.channels.inbound import (
    MAX_BODY_BYTES,
    ApprovalOfferer,
    CardPresser,
    ChannelAnswerer,
    ChannelBindings,
    ChatBinder,
    NoBindingsYet,
    Pressed,
    Receipt,
    ReceiptKind,
    receive,
    reply_for,
)
from brain.channels.outbound import Delivered, LedgerRunner, Outgoing, deliver
from brain.channels.relay import RelayingTransport
from brain.chat_answer import ChatAnswerer
from brain.connectors.throttle import CallOutcome
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.credential_routes import credentials_of
from brain.db import libpq_conninfo
from brain.gate.context import Channel
from brain.gate.resolve import EntitlementStore
from brain.guide_views import GuideStepView, step_view
from brain.identity.oidc import JwksCache, KeySet, TokenRefusedError
from brain.identity.roles import IdentityError
from brain.install import InstallError, value_of
from brain.install_routes import settings_of
from brain.notification_routes import mail_password_of
from brain.notification_routes import transport_of as mail_transport_of
from brain.ops.binding_store import StoredBinder, StoredBindings
from brain.ops.channel_store import (
    ChannelRecord,
    ChannelRecords,
    ChannelSecrets,
    ChannelSecretsUnavailableError,
    DeliveryEntry,
    DeliveryRecords,
    EventClaims,
    StoredChannels,
    StoredClaims,
    StoredDeliveries,
    VaultChannelSecrets,
    channel_secret_slot,
)
from brain.ops.connect_steps import EVENTS_ADDRESS_MARK
from brain.ops.connector_admin import may_connect_source
from brain.ops.credentials import (
    MAX_CREDENTIAL_CHARS,
    TOLD,
    CredentialProblemError,
    CredentialsUnavailableError,
    VaultState,
)
from brain.ops.idempotency import Intent, Issued, OperationLedger
from brain.ops.lark_connect import install_origin
from brain.ops.mail import (
    MailPasswordUnavailableError,
    MailSettings,
    MailTransport,
    settings_from_rows,
    settings_rows,
)
from brain.ops.openbao import OpenBaoVault
from brain.ops.operation_store import PostgresOperationLedger
from brain.ops.outbox import SignedRequest
from brain.ops.outbox_store import SendResult
from brain.ops.safe_error import describe
from brain.ops.secrets import VaultRole
from brain.ops.webhook_delivery import HttpsSender, SystemResolver
from brain.routing_routes import sessions_of
from brain.tables.channel import DeliveryOutcome, Direction, RefusedBecause
from brain.tools.fetch import Resolver, UnsafeAddressError, assert_fetchable

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why every refusal of the vendor address is one 404.
AN_ADDRESS_A_VENDOR_POSTS_TO_SAYS_NOTHING_ABOUT_THE_INSTALL: Final = (
    "The events address takes no caller, so anybody can post to it. A name that is no channel, a "
    "channel this release cannot receive on, a channel with no record and a channel switched off "
    "are answered with one 404 and one body, so posting to each name in turn cannot tell anybody "
    "which channels this install runs. The refusal is recorded for a channel that exists."
)

#: Why the events address is the one route under the API prefix that takes no sign-in.
A_PLATFORM_PROVES_A_SIGNATURE_AND_HAS_NO_SIGN_IN: Final = (
    "A vendor posting a message has no session and no bearer token, so the events address takes "
    "no caller. What it takes instead is the channel's signature over the exact bytes, checked "
    "before the body is read, on a channel that is switched on; an unsigned request is refused, "
    "and on a channel that is not received it is answered as an address with nothing at it."
)

#: Why a chat's reply is made after the vendor has been answered.
A_CHAT_IS_ACKNOWLEDGED_BEFORE_IT_IS_ANSWERED: Final = (
    "A chat vendor waits a few seconds for the address to answer and posts the event again when "
    "it hears nothing, and an answer can take longer than that. So a chat message is answered 200 "
    "as soon as it is claimed, and the reply is made and sent after; a redelivery meanwhile is "
    "refused by the claim, and what the reply came to is in the channel's deliveries."
)

#: Why a channel is governed by the connector authority over its own name.
A_CHANNEL_IS_GOVERNED_BY_THE_AUTHORITY_CONNECT_LARK_ASKS: Final = (
    "A channel is set up, switched and tested under admin:connector over <channel>_channel, the "
    "slot name Connect Lark already gives the Lark chat use. So the person who may switch Lark's "
    "chat on there may switch its channel here, a grant narrowed to one channel reaches that "
    "channel alone, and a reader without it is shown nothing about the channel."
)

#: Why a channel's set-up, switch and secret each leave a ledger entry.
EVERY_CHANGE_TO_A_CHANNEL_IS_AUDITED: Final = (
    "Setting a channel up, switching it on or off and replacing its secret each leave an entry in "
    "the audit ledger with who did it, at what reach and in which request: a setting entry naming "
    "the channel for the record, and a credential entry naming its slot for the secret. Neither "
    "holds the tenant's values or anything of the secret."
)

# --------------------------------------------------------------------- the figures

CHANNELS_PATH: Final = "/channels"
CHANNEL_PATH: Final = CHANNELS_PATH + "/{name}"
EVENTS_PATH: Final = CHANNEL_PATH + "/events"
SWITCH_PATH: Final = CHANNEL_PATH + "/switch"
DELIVERIES_PATH: Final = CHANNEL_PATH + "/deliveries"
TEST_PATH: Final = CHANNEL_PATH + "/test"

#: The paths under the API prefix reached with no sign-in, each proving a signature instead. Read by
#: `tests/unit/test_api_routes.py`, whose rule that every route authenticates its caller names these
#: as its one written exception.
SIGNED_NOT_SIGNED_IN: Final[frozenset[str]] = frozenset({API_PREFIX + EVENTS_PATH})

#: The source name a channel's authority is asked over: the Lark chat use's slot, generalised.
CHANNEL_SOURCE_SUFFIX: Final = "_channel"

#: How much of a vendor's answer the transport keeps: a chat vendor's refusal, a page of the
#: people in one conversation. The bound on what arrives, applied to what is read back.
KEPT_ANSWER_BYTES: Final = MAX_BODY_BYTES

#: The longest tenant value kept: an identifier or an address, never a document.
MAX_TENANT_VALUE_CHARS: Final = 500

#: The installation setting that names this install's public address, which every events
#: address is built on. See `brain.ops.lark_connect.events_address` for why it is this one.
PUBLIC_ADDRESS_SETTING: Final = "INSTALL_OIDC_REDIRECT_URIS"

#: How long a send's thread waits for the relay's settings to be read.
RELAY_SETTINGS_SECONDS: Final = 10.0

#: The longest destination a test message is sent to.
MAX_TO_CHARS: Final = 255

#: What a test message says. A product sentence, so it carries nothing from the company's data.
TEST_MESSAGE: Final = (
    "This is a test message from the Brain. If you can read it, this channel can send."
)

NOT_HERE: Final = "There is nothing at this address."
NOT_ACCEPTED: Final = "This request was not accepted."
TOO_LARGE: Final = "This request is larger than a message is."
NOT_READABLE: Final = "This request is not a message this channel can read."
NOT_NOW: Final = "This channel cannot check requests just now. Send it again later."
NO_RECORD: Final = "This channel has no record on this install yet. Set it up first."
SAVED: Final = "Saved. The channel's secret, if one was given, is in the vault."
TOLD_CHANNELS: Final = (
    "Each channel is its own record: switching one off stops it receiving and sending and "
    "touches no other. A delivery is recorded as accepted, redelivered, sent, refused or "
    "unknown, with its reason, and never with what it said or who it was from."
)

#: What a person is told for each delivery outcome of a test message.
TEST_TOLD: Final[Mapping[DeliveryOutcome, str]] = {
    DeliveryOutcome.SENT: "Sent. The vendor accepted the test message.",
    DeliveryOutcome.REFUSED: "Not sent. The reason is recorded in this channel's deliveries.",
    DeliveryOutcome.UNKNOWN: (
        "The vendor did not answer, so the test message may or may not have arrived. Check at "
        "the other end before sending another."
    ),
}

#: What a person saving a set-up the vendor must be told about is told when it was not.
NO_PUBLIC_ADDRESS: Final = (
    "This install has no public address yet, so the vendor could not be told where to send. "
    "Set the install's address first, then save this set-up again."
)
NOTHING_HELD_TO_REGISTER_WITH: Final = (
    "No secret is held for this channel yet. Paste it into the secret field and save again."
)
REGISTRATION_NOT_BUILT: Final = (
    "Not saved. This set-up is not one the vendor takes: check each field against the steps."
)
REGISTRATION_TOLD: Final[Mapping[CallOutcome, str]] = {
    CallOutcome.REJECTED: (
        "Not saved. The vendor did not accept this set-up: check the secret you pasted, and that "
        "this install's address is reachable over HTTPS."
    ),
    CallOutcome.QUOTA: "Not saved. The vendor asked to be called less often. Save again shortly.",
    CallOutcome.UNAVAILABLE: (
        "Not saved. The vendor could not be reached just now. Save again in a minute."
    ),
}

_REFUSED_STATUS: Final[Mapping[RefusedBecause, tuple[int, str]]] = {
    RefusedBecause.NOT_CONFIGURED: (404, NOT_HERE),
    RefusedBecause.SWITCHED_OFF: (404, NOT_HERE),
    RefusedBecause.TOO_LARGE: (413, TOO_LARGE),
    RefusedBecause.NO_SECRET: (503, NOT_NOW),
    RefusedBecause.VAULT_UNAVAILABLE: (503, NOT_NOW),
    RefusedBecause.BAD_SIGNATURE: (401, NOT_ACCEPTED),
    RefusedBecause.UNREADABLE: (400, NOT_READABLE),
}

_NOT_KEPT_STATUS: Final[Mapping[VaultState, int]] = {
    VaultState.ABSENT: 409,
    VaultState.REFUSED: 409,
    VaultState.UNREACHABLE: 503,
}


# ------------------------------------------------------------------------ the shapes


class ChannelView(BaseModel):
    """One channel as its manager sees it. No field could hold its secret."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    #: Whether this release can receive and send on it at all.
    receives: bool
    #: Where its vendor posts, under this install's own origin; empty when it cannot receive.
    events_path: str
    #: The same address in full, for a person to paste into the vendor; empty when this install
    #: names no public address yet, or the channel cannot receive.
    events_address: str
    #: The steps that connect it, ending in its own form; empty for a channel with none yet.
    steps: list[GuideStepView]
    #: The tenant fields its record takes.
    tenant_fields: list[str]
    #: The parts its secret holds, each typed on its own; empty when the secret is one value.
    secret_parts: list[str]
    configured: bool
    enabled: bool
    tenant: dict[str, str]
    #: Whether its secret is held, or None when the vault could not be asked.
    secret_held: bool | None
    updated_by: str | None
    updated_at: datetime | None


class ChannelsView(BaseModel):
    """Every channel this reader may manage, and what a record and a delivery are."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channels: list[ChannelView]
    told: str


class ChannelAsked(BaseModel):
    """A channel's record to keep, and optionally its secret, which is kept and never returned."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool
    tenant: dict[str, str] = Field(default_factory=dict, max_length=8)
    secret: str | None = Field(default=None, max_length=MAX_CREDENTIAL_CHARS)
    #: For a channel whose secret has parts, every part at once, by name; see `secret_problems`.
    secret_parts: dict[str, str] | None = Field(default=None, max_length=8)


class SwitchAsked(BaseModel):
    """On or off."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool


class DeliveryRowView(BaseModel):
    """One recorded delivery. What happened and why, never what it said or who it was for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    direction: Direction
    outcome: DeliveryOutcome
    reason: RefusedBecause | None
    vendor_status: int | None
    recorded_at: datetime


class DeliveriesView(BaseModel):
    """A channel's newest deliveries, newest first."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel: str
    deliveries: list[DeliveryRowView]


class TestAsked(BaseModel):
    """Where a test message goes: a chat, a conversation or a sender, in the vendor's terms."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    to: str = Field(min_length=1, max_length=MAX_TO_CHARS)


class TestView(BaseModel):
    """What a test message came to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: DeliveryOutcome
    reason: RefusedBecause | None
    vendor_status: int | None
    #: False when this test was already sent for this record and destination.
    issued: bool
    told: str


class EventView(BaseModel):
    """What the events address answers a vendor that was not refused."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ReceiptKind
    #: What the reply came to, when one was made.
    reply: DeliveryOutcome | None = None


# ------------------------------------------------------------------------ the transport


class HttpsTransport:
    """`ChannelTransport` over the pinned HTTPS sender, to an address checked at every request.

    Keeps the vendor's answer, up to `KEPT_ANSWER_BYTES`, because a chat vendor refuses inside a
    200 and the wire that knows it has to read the body to say so. A request carrying a
    `TokenExchange` has it made first, to an address checked the same way, and the token put in
    its `Authorization` header; the token is held for that one request and nowhere else. An
    exchange that does not produce a token is answered as the exchange's own answer, so the wire
    judges what the vendor said about the credential rather than a request never made.
    """

    def __init__(self, resolver: Resolver | None = None, sender: HttpsSender | None = None) -> None:
        self._resolver = resolver if resolver is not None else SystemResolver()
        self._sender = (
            sender if sender is not None else HttpsSender(kept_answer_bytes=KEPT_ANSWER_BYTES)
        )

    def _signed(
        self, url: str, headers: Mapping[str, str], body: bytes
    ) -> SignedRequest | VendorAnswer:
        """The request to the address that passed the check, or the refusal to connect."""
        try:
            target = assert_fetchable(url, self._resolver)
        except UnsafeAddressError:
            return VendorAnswer(unsafe_address=True)
        return SignedRequest(url=url, address=target.address, headers=headers, body=body)

    def _authorised(self, request: VendorRequest) -> dict[str, str] | VendorAnswer:
        """The request's headers with the exchanged token in them, or the exchange's answer."""
        headers = dict(request.headers)
        exchange = request.exchange
        if exchange is None:
            return headers
        signed = self._signed(exchange.url, {"Content-Type": exchange.content_type}, exchange.body)
        if isinstance(signed, VendorAnswer):
            return signed
        answered = _answer_of(self._sender.mint(signed))
        token = bearer_from(answered, exchange.answered_in)
        if token is None:
            return answered
        headers["Authorization"] = f"Bearer {token}"
        return headers

    def send(self, request: VendorRequest) -> VendorAnswer:
        if request.method not in ("POST", "PATCH"):
            msg = "a send is a POST, or a PATCH replacing a card; a read goes through `read`"
            raise ValueError(msg)
        headers = self._authorised(request)
        if isinstance(headers, VendorAnswer):
            return headers
        signed = self._signed(request.url, headers, request.body)
        if isinstance(signed, VendorAnswer):
            return signed
        if request.method == "PATCH":
            return _answer_of(self._sender.edit(signed))
        return _answer_of(self._sender.send(signed))

    def read(self, request: VendorRequest) -> VendorAnswer:
        if request.method != "GET":
            msg = "a read is a GET; a send goes through `send`, inside `issue_once`"
            raise ValueError(msg)
        headers = self._authorised(request)
        if isinstance(headers, VendorAnswer):
            return headers
        signed = self._signed(request.url, headers, b"")
        if isinstance(signed, VendorAnswer):
            return signed
        return _answer_of(self._sender.read(signed))


def _answer_of(result: SendResult) -> VendorAnswer:
    return VendorAnswer(
        status=result.status,
        timed_out=result.timed_out,
        connection_failed=result.connection_failed,
        body=result.body,
    )


def bearer_from(answer: VendorAnswer, answered_in: str) -> str | None:
    """The token a successful exchange answered with, or None for anything else."""
    if answer.status != 200 or not answer.body:
        return None
    try:
        parsed = json.loads(answer.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    token = parsed.get(answered_in) if isinstance(parsed, dict) else None
    return token if isinstance(token, str) and token else None


# ------------------------------------------------------------------------ the wiring


def records_of(request: Request) -> ChannelRecords:
    """`app.state.channel_records` when a test put one there, the database otherwise."""
    found = getattr(request.app.state, "channel_records", None)
    if isinstance(found, ChannelRecords):
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredChannels(sessions)


def deliveries_of(request: Request) -> DeliveryRecords:
    """`app.state.channel_deliveries` when a test put one there, the database otherwise."""
    found = getattr(request.app.state, "channel_deliveries", None)
    if isinstance(found, DeliveryRecords):
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredDeliveries(sessions)


def claims_of(request: Request) -> EventClaims:
    """`app.state.channel_claims` when a test put one there, `gate.channel_event` otherwise."""
    found = getattr(request.app.state, "channel_claims", None)
    if isinstance(found, EventClaims):
        return found
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredClaims(sessions)


def secrets_of(request: Request) -> ChannelSecrets:
    """`app.state.channel_secrets`, or this process's vault as the application, or no vault."""
    found = getattr(request.app.state, "channel_secrets", None)
    if isinstance(found, ChannelSecrets):
        return found
    settings = settings_of(request)
    if not settings.vault_address or not settings.vault_token:
        return VaultChannelSecrets(None)
    try:
        vault = OpenBaoVault(
            settings.vault_address, settings.vault_token, role=VaultRole.APPLICATION
        )
    except ValueError:
        return VaultChannelSecrets(None)
    return VaultChannelSecrets(vault)


def transport_of(request: Request) -> ChannelTransport:
    """`app.state.channel_transport` when a test put one there, `HttpsTransport` otherwise."""
    found = getattr(request.app.state, "channel_transport", None)
    return found if found is not None else HttpsTransport()


def relay_settings_of(
    request: Request,
) -> Callable[[], Coroutine[None, None, MailSettings | None]]:
    """How the relay's settings are read: `app.state.mail_settings` for a test, `ops.setting`
    otherwise, and none with no database."""
    found = getattr(request.app.state, "mail_settings", None)

    async def read() -> MailSettings | None:
        if isinstance(found, MailSettings):
            return found
        sessions = sessions_of(request)
        if sessions is None:
            return None
        async with sessions() as session:
            return settings_from_rows(await settings_rows(session))

    return read


def relay_of(request: Request) -> Callable[[], MailTransport | None]:
    """The mail relay a reply by mail leaves through, asked on the send's own thread.

    The relay set up on Notifications, never one of a channel's own: see
    `brain.channels.relay.ONE_RELAY_SERVES_EVERY_MESSAGE_THIS_INSTALL_SENDS`. Its settings are
    read on this request's event loop, which is free while the send's thread waits, and its
    password is borrowed from the vault for the one message and dropped with the transport. A
    relay not set up, or whose password the vault will not give, answers None and sends nothing.
    """
    loop = asyncio.get_running_loop()
    read_settings = relay_settings_of(request)
    mail_password = mail_password_of(request)
    build = mail_transport_of(request)

    def relay() -> MailTransport | None:
        if _on_a_running_loop():
            msg = "the relay is asked on the send's thread, never on the event loop"
            raise RuntimeError(msg)
        settings = asyncio.run_coroutine_threadsafe(read_settings(), loop).result(
            RELAY_SETTINGS_SECONDS
        )
        if settings is None:
            return None
        password: str | None = None
        if settings.username:
            try:
                password = mail_password.read() if mail_password.configured else None
            except MailPasswordUnavailableError:
                return None
            if password is None:
                return None
        return build(settings, password)

    return relay


def _on_a_running_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


class PublishedKeys:
    """`brain.identity.oidc.JwksFetch` for a `KeyedWire`: its metadata, then its key set.

    Both are read through the channel transport, so the address rule applies to each, and the
    key set is read only from the host the metadata document is on: a document that pointed
    anywhere else would be choosing where this install's trust comes from. See
    `brain.channels.adapter.A_PUBLISHED_KEY_IS_FETCHED_BY_THE_ROUTE_AND_JUDGED_BY_THE_WIRE`.
    """

    def __init__(self, wire: KeyedWire, transport: ChannelTransport) -> None:
        self._wire = wire
        self._transport = transport

    def _get(self, url: str) -> bytes:
        answer = self._transport.read(VendorRequest(url=url, headers={}, body=b"", method="GET"))
        if answer.status != 200 or not answer.body:
            msg = f"{urlsplit(url).hostname} did not answer with its document"
            raise IdentityError(msg)
        return answer.body

    def __call__(self, issuer: str) -> KeySet:
        del issuer  # One address per wire; the cache's key is it.
        address = self._wire.keys_address
        metadata = self._get(address)
        try:
            listed = json.loads(metadata).get("jwks_uri")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
            raise IdentityError("the metadata document is not JSON") from exc
        if (
            not isinstance(listed, str)
            or urlsplit(listed).scheme != "https"
            or urlsplit(listed).hostname != urlsplit(address).hostname
        ):
            raise IdentityError("the metadata document names its keys on another host")
        try:
            return self._wire.key_set_of(metadata, self._get(listed), datetime.now(UTC))
        except ValueError as exc:
            raise IdentityError(describe(exc)) from exc


def vendor_keys_of(request: Request, wire: object) -> Callable[[], Awaitable[KeySet | None]] | None:
    """How a request fetches its vendor's published keys: None for a wire that needs none.

    `app.state.channel_keys` when a test put a key set there; otherwise one cache per
    application and address, so a key set is fetched once an hour rather than once a request,
    and an unreachable vendor leaves the cached set in use for its grace, then refuses.
    """
    if not isinstance(wire, KeyedWire):
        return None
    keyed: KeyedWire = wire
    found = getattr(request.app.state, "channel_keys", None)
    caches: dict[str, JwksCache] | None = getattr(request.app.state, "channel_key_caches", None)
    if caches is None:
        caches = {}
        request.app.state.channel_key_caches = caches
    cache = caches.setdefault(
        keyed.keys_address, JwksCache(PublishedKeys(keyed, transport_of(request)))
    )

    async def load() -> KeySet | None:
        if isinstance(found, KeySet):
            return found
        try:
            return await asyncio.to_thread(cache.keys_for, keyed.keys_address, datetime.now(UTC))
        except TokenRefusedError:
            log.info("vendor keys not read", address=urlsplit(keyed.keys_address).hostname)
            return None

    return load


def ledger_of(request: Request) -> LedgerRunner:
    """How one send reaches the operation ledger: `app.state.operation_ledger` for a test, or a
    connection of its own in autocommit mode, opened for the one send on the send's thread, as
    `brain.notification_routes.trial_in_a_thread` does for a test message."""

    def run(work: Callable[[OperationLedger], Issued]) -> Issued:
        found = getattr(request.app.state, "operation_ledger", None)
        if found is not None:
            return work(found)
        url = settings_of(request).database_url
        with psycopg.connect(libpq_conninfo(url), autocommit=True, prepare_threshold=None) as conn:
            return work(PostgresOperationLedger(conn))

    return run


def bindings_of(request: Request) -> ChannelBindings:
    """`app.state.channel_bindings` when a test put one there, `auth.principal_identity` through
    `brain.ops.binding_store.StoredBindings` otherwise, and `NoBindingsYet` with no database."""
    found: ChannelBindings | None = getattr(request.app.state, "channel_bindings", None)
    if found is not None:
        return found
    sessions = sessions_of(request)
    return NoBindingsYet() if sessions is None else StoredBindings(sessions)


def answerer_of(request: Request) -> ChannelAnswerer | None:
    """`app.state.channel_answerer` when a test put one there; otherwise the gate, run as the
    bound person through `brain.chat_answer.ChatAnswerer`, on a process that has a gate to run;
    otherwise None, which is recorded as `not_answerable`."""
    found: ChannelAnswerer | None = getattr(request.app.state, "channel_answerer", None)
    if found is not None:
        return found
    if wiring_of(request) is None:
        return None
    return ChatAnswerer(
        request,
        secrets=secrets_of(request),
        transport=transport_of(request),
        bindings=bindings_of(request),
    )


def binder_of(request: Request) -> ChatBinder | None:
    """`app.state.channel_binder` when a test put one there, the stored codes and bindings
    otherwise, for this request's trace, and None with no database.

    None takes no message as a code, so an unbound sender is prompted, which is
    `NOBODY_IS_BOUND_UNTIL_A_BINDING_IS_KEPT`'s direction. The trace is read now, while the request
    is being handled, because a chat's reply is made after the response has gone."""
    found: ChatBinder | None = getattr(request.app.state, "channel_binder", None)
    if found is not None:
        return found
    sessions = sessions_of(request)
    return None if sessions is None else StoredBinder(sessions, trace_id=trace_of_request())


def _approval_cards(request: Request) -> object | None:
    """`app.state.approval_cards` when a test put one there; otherwise the cards over this
    process's gate, directory and suspension store, for this request's trace; otherwise None.

    None answers a decision word with where to decide and nothing else, and a press with the one
    refusal: a process with no gate or no directory has nobody to decide as."""
    found: object = getattr(request.app.state, "approval_cards", None)
    if found is not None:
        return found
    if wiring_of(request) is None:
        return None
    try:
        return ApprovalCards.of(request, bindings=bindings_of(request))
    except Failed:
        return None


def approval_cards_of(request: Request) -> ApprovalOfferer | None:
    """What a bound sender's decision word is answered by. See `_approval_cards`."""
    # A cast at the boundary of a test's state, where proving the structural match buys nothing.
    return cast("ApprovalOfferer | None", _approval_cards(request))


def presser_of(request: Request) -> CardPresser | None:
    """What decides a press on a card: the same object as `approval_cards_of`."""
    return cast("CardPresser | None", _approval_cards(request))


class _NoReach:
    """The entitlement store on a process with no gate wired: asked, it fails loudly."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        del principal_id, now
        raise Failed("no entitlement store on this process")


def reach_of(request: Request) -> EntitlementStore:
    """The gate's entitlement store, which a message made for somebody is held to at send time."""
    gate = getattr(request.app.state, "gate", None)
    store = getattr(gate, "store", None)
    return store if store is not None else _NoReach()


# ------------------------------------------------------------------------ the decisions


def channel_named(name: str) -> Channel | None:
    """The channel an adapter declares under this name, or None."""
    declared = {factory().capabilities().channel for factory in channel_adapters()}
    for channel in declared:
        if channel.value == name:
            return channel
    return None


def may_manage(reach: EntitlementSet, channel: Channel, now: datetime) -> bool:
    """See `A_CHANNEL_IS_GOVERNED_BY_THE_AUTHORITY_CONNECT_LARK_ASKS`."""
    return may_connect_source(reach, f"{channel.value}{CHANNEL_SOURCE_SUFFIX}", now)


def tenant_problems(wire: ChannelWire, tenant: Mapping[str, str]) -> list[str]:
    """Every field the wire does not take, and every value that is not one unbroken line."""
    problems = [
        f"{key} is not a field this channel takes"
        for key in tenant
        if key not in wire.tenant_fields
    ]
    for key, value in tenant.items():
        if key not in wire.tenant_fields:
            continue
        if (
            not value
            or len(value) > MAX_TENANT_VALUE_CHARS
            or any(one.isspace() or not one.isprintable() for one in value)
        ):
            problems.append(f"{key} is one line of at most {MAX_TENANT_VALUE_CHARS} characters")
    return problems


def secret_problems(wire: ChannelWire, body: ChannelAsked) -> list[str]:
    """What is wrong with the secret asked: the wrong shape for this channel, or a part missing.

    A channel with parts takes every part at once or none, and never a single `secret`; one with
    none takes `secret` alone. See `brain.channels.adapter.SEVERAL_PARTS_ARE_WRITTEN_AS_ONE`.
    """
    parts = wire.secret_parts
    if not parts:
        return [] if body.secret_parts is None else ["this channel's secret is one value"]
    if body.secret is not None:
        return [f"this channel's secret is given as its parts: {', '.join(parts)}"]
    if body.secret_parts is None:
        return []
    given = body.secret_parts
    problems = [
        f"{name} is not a part of this channel's secret" for name in given if name not in parts
    ]
    for name in parts:
        value = given.get(name, "")
        if not value.strip() or len(value) > MAX_CREDENTIAL_CHARS:
            problems.append(f"{name} is needed with the others, as one line")
    return problems


def secret_to_keep(wire: ChannelWire, body: ChannelAsked) -> str | None:
    """The value the channel's slot keeps: the secret, or its parts as one JSON object."""
    if not wire.secret_parts or body.secret_parts is None:
        return body.secret
    return json.dumps(
        {name: body.secret_parts[name] for name in wire.secret_parts}, separators=(",", ":")
    )


def _saved(name: str) -> str:
    try:
        return value_of(name)
    except InstallError:
        return ""


def events_path_of(channel: Channel) -> str:
    """Where a channel's vendor posts, under this install's origin; empty for one with no wire."""
    if channel not in channel_wires():
        return ""
    return API_PREFIX + EVENTS_PATH.format(name=channel.value)


def events_address_of(channel: Channel) -> str:
    """The same address in full, for a person to paste into the vendor.

    Built on the install setting that already names its public address, as Lark's is (see
    `brain.ops.lark_connect.events_address`), so no second setting can disagree with it. Empty
    while the install names none, rather than a relative path a vendor could not reach.
    """
    path = events_path_of(channel)
    origin = install_origin(_saved(PUBLIC_ADDRESS_SETTING))
    return f"{origin}{path}" if origin and path else ""


def steps_of(channel: Channel) -> list[GuideStepView]:
    """The steps that connect a channel, holding its own form; none for a channel with none.

    A text to copy that names the events address has this install's written in, where it names
    one; see `brain.ops.connect_steps.EVENTS_ADDRESS_MARK`.
    """
    address = events_address_of(channel)
    served = []
    for one in channel_guides().get(channel, ()):
        view = step_view(one)
        if address and EVENTS_ADDRESS_MARK in view.copy_text:
            view = view.model_copy(
                update={"copy_text": view.copy_text.replace(EVENTS_ADDRESS_MARK, address)}
            )
        served.append(view)
    return served


def _error(status: int, message: str) -> JSONResponse:
    body = ErrorBody(message=message, trace_id=trace_of_request())
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def _not_here() -> Absent:
    return Absent("no channel here for this caller")


def _managed_wire(name: str, asked: Asked) -> tuple[Channel, ChannelWire]:
    """The channel and its wire when this reader may manage it; otherwise one absence."""
    channel = channel_named(name)
    wire = None if channel is None else channel_wires().get(channel)
    if channel is None or wire is None or not may_manage(asked.reach, channel, asked.now):
        raise _not_here()
    return channel, wire


async def _view(
    channel: Channel, record: ChannelRecord | None, secrets: ChannelSecrets
) -> ChannelView:
    wire = channel_wires().get(channel)
    held: bool | None = None
    if record is not None:
        try:
            held = await asyncio.to_thread(secrets.held, record.secret)
        except ChannelSecretsUnavailableError:
            held = None
    return ChannelView(
        channel=channel.value,
        receives=wire is not None,
        events_path=events_path_of(channel),
        events_address=events_address_of(channel),
        steps=steps_of(channel),
        tenant_fields=list(wire.tenant_fields) if wire else [],
        secret_parts=list(wire.secret_parts) if wire else [],
        configured=record is not None,
        enabled=record is not None and record.enabled,
        tenant=dict(record.tenant) if record else {},
        secret_held=held,
        updated_by=record.updated_by if record else None,
        updated_at=record.updated_at if record else None,
    )


# ------------------------------------------------------------------------ the routes

router = APIRouter(prefix=API_PREFIX, tags=["channels"], route_class=NoEchoRoute)

Name = Annotated[str, Path(max_length=32)]


@router.post(EVENTS_PATH, response_model=EventView, responses=COMMON_RESPONSES)
async def channel_event(name: Name, request: Request) -> JSONResponse:
    """What a vendor posts. Takes no caller: the signature is what is proved."""
    channel = channel_named(name)
    wire = None if channel is None else channel_wires().get(channel)
    if channel is None or wire is None:
        return _error(404, NOT_HERE)
    now = datetime.now(UTC)
    records = records_of(request)
    record = await records.get(channel)
    deliveries = deliveries_of(request)
    declared = request.headers.get("content-length")

    async def capped() -> bytes:
        # Read no further than one byte past the bound, so a request that declared no length
        # cannot make this process hold whatever it chooses to stream.
        taken = bytearray()
        async for chunk in request.stream():
            taken.extend(chunk)
            if len(taken) > MAX_BODY_BYTES:
                break
        return bytes(taken)

    receipt = await receive(
        wire,
        record=record,
        headers={key.lower(): value for key, value in request.headers.items()},
        declared_length=int(declared) if declared and declared.isdigit() else None,
        body=capped,
        secrets=secrets_of(request),
        claims=claims_of(request),
        deliveries=deliveries,
        now=now,
        keys=vendor_keys_of(request, wire),
    )
    if receipt.kind is ReceiptKind.REFUSED:
        assert receipt.reason is not None
        status, message = _REFUSED_STATUS[receipt.reason]
        log.info("channel request refused", channel=channel.value, reason=receipt.reason.value)
        return _error(status, message)
    if receipt.kind is ReceiptKind.HANDSHAKE:
        return JSONResponse(status_code=200, content=dict(receipt.handshake or {}))
    if receipt.kind is ReceiptKind.REDELIVERED:
        return JSONResponse(status_code=200, content=EventView(status=receipt.kind).model_dump())

    assert record is not None
    if receipt.inbound is not None and receipt.inbound.press is not None:
        return await _pressed(request, wire, receipt, record, now)
    if receipt.inbound is not None and receipt.inbound.conversation is not None:
        # A chat vendor waits seconds, not the length of an answer, and posts the event again
        # when it hears nothing: so the reply is made after the answer to the vendor has gone.
        # See `A_CHAT_IS_ACKNOWLEDGED_BEFORE_IT_IS_ANSWERED`.
        view = EventView(status=receipt.kind)
        return JSONResponse(
            status_code=200,
            content=view.model_dump(),
            background=BackgroundTask(answer_receipt, request, receipt, record, now),
        )
    outcome = await answer_receipt(request, receipt, record, now)
    view = EventView(status=receipt.kind, reply=outcome)
    return JSONResponse(status_code=200, content=view.model_dump())


async def answer_receipt(
    request: Request, receipt: Receipt, record: ChannelRecord, now: datetime
) -> DeliveryOutcome | None:
    """Make and send the reply to an accepted message; what the first message sent came to.

    Nothing sent answers None: a shared conversation's message that was not for the bot. Nothing
    able to answer records `not_answerable`. An answer that failed while it was being made is
    recorded the same way and logged by its kind alone, because a chat has nobody waiting on a
    status code to be told, and the message it answered is claimed and will not come again.
    """
    deliveries = deliveries_of(request)
    try:
        replies = await reply_for(
            receipt,
            record=record,
            bindings=bindings_of(request),
            answerer=answerer_of(request),
            binder=binder_of(request),
            offerer=approval_cards_of(request),
            now=now,
        )
    except Exception as exc:
        log.warning("channel reply not made", channel=record.channel.value, kind=type(exc).__name__)
        replies = None
    if replies is None:
        await deliveries.record(
            DeliveryEntry(
                channel=record.channel,
                direction=Direction.OUTBOUND,
                outcome=DeliveryOutcome.REFUSED,
                reason=RefusedBecause.NOT_ANSWERABLE,
            )
        )
        return DeliveryOutcome.REFUSED
    # Each message is held to its reader's reach when it leaves, not when the event came.
    outcomes = [
        (await _deliver(request, one, record, datetime.now(UTC))).outcome for one in replies
    ]
    return outcomes[0] if outcomes else None


async def _pressed(
    request: Request, wire: ChannelWire, receipt: Receipt, record: ChannelRecord, now: datetime
) -> JSONResponse:
    """Decide a press and answer the vendor in its wire's words; close the card after.

    A process with nothing to decide a press, or a wire with no cards, answers the one refusal and
    decides nothing. Whatever deciding raised is answered the same way and logged by its kind,
    because the vendor is waiting and the presser is told in words either way.
    """
    assert receipt.inbound is not None
    presser = presser_of(request)
    pressed = Pressed(told=PRESS_NOT_TAKEN_TOLD)
    if presser is not None and isinstance(wire, CardWire):
        try:
            pressed = await presser.press(
                receipt.inbound, record=record, reply_to=receipt.reply_to, now=now
            )
        except Exception as exc:
            log.warning(
                "card press not decided", channel=record.channel.value, kind=type(exc).__name__
            )
    if not isinstance(wire, CardWire):
        view = EventView(status=receipt.kind)
        return JSONResponse(status_code=200, content=view.model_dump())
    body = dict(
        wire.press_answer(told=pressed.told, closed=pressed.closed, decided=pressed.decided)
    )
    if pressed.patch is None and pressed.fallback is None:
        return JSONResponse(status_code=200, content=body)
    return JSONResponse(
        status_code=200,
        content=body,
        background=BackgroundTask(_close_after_press, request, pressed, record),
    )


async def _close_after_press(request: Request, pressed: Pressed, record: ChannelRecord) -> None:
    """The card a press decided, replaced; the text fallback when the replacement did not go."""
    await closed_after(
        pressed,
        send=lambda one: _deliver(request, one, record, datetime.now(UTC)),
        windows=card_windows_of(request),
        now=datetime.now(UTC),
    )


async def _deliver(
    request: Request, outgoing: Outgoing, record: ChannelRecord | None, now: datetime
) -> Delivered:
    return await deliver(
        outgoing,
        record=record,
        secrets=secrets_of(request),
        reach=reach_of(request),
        transport=RelayingTransport(transport_of(request), relay_of(request)),
        ledger=ledger_of(request),
        deliveries=deliveries_of(request),
        now=now,
    )


@router.get(CHANNELS_PATH, response_model=ChannelsView, responses=COMMON_RESPONSES)
async def channels(request: Request, asked: Asked) -> ChannelsView:
    """Every channel this reader may manage, with its record. Nothing about any other."""
    mine = [
        factory().capabilities().channel
        for factory in channel_adapters()
        if may_manage(asked.reach, factory().capabilities().channel, asked.now)
    ]
    if not mine:
        return ChannelsView(channels=[], told=TOLD_CHANNELS)
    kept = {one.channel: one for one in await records_of(request).every()}
    secrets = secrets_of(request)
    return ChannelsView(
        channels=[await _view(channel, kept.get(channel), secrets) for channel in mine],
        told=TOLD_CHANNELS,
    )


async def _register(
    request: Request,
    channel: Channel,
    wire: RegisteredWire,
    kept: str | None,
    tenant: Mapping[str, str],
) -> JSONResponse | None:
    """Tell the vendor this install's events address, or say why not; None when it accepted.

    See `brain.channels.adapter.A_VENDOR_THAT_MUST_BE_TOLD_THE_ADDRESS_IS_TOLD_ON_SAVE`. Made
    before the secret is kept, so a secret the vendor refused never replaces the one that works.
    The secret is the one being saved, or else the one the vault holds, borrowed for the call.
    """
    address = events_address_of(channel)
    if not address:
        return _error(409, NO_PUBLIC_ADDRESS)
    secret = kept
    if secret is None:
        record = await records_of(request).get(channel)
        try:
            held = (
                None
                if record is None
                else await asyncio.to_thread(secrets_of(request).read, record.secret)
            )
        except ChannelSecretsUnavailableError:
            return _error(503, NOT_NOW)
        if held is None:
            return _error(409, NOTHING_HELD_TO_REGISTER_WITH)
        secret = held
    try:
        told = wire.registration_for(address=address, secret=secret, tenant=tenant)
    except RegistrationRefusedError as problem:
        return _error(422, str(problem))
    except ValueError:
        return _error(422, REGISTRATION_NOT_BUILT)
    del secret
    answer = await asyncio.to_thread(transport_of(request).send, told)
    outcome = wire.judge(answer)
    log.info("channel address registered", channel=channel.value, outcome=outcome.value)
    if outcome is CallOutcome.OK:
        return None
    return _error(502, REGISTRATION_TOLD.get(outcome, REGISTRATION_TOLD[CallOutcome.REJECTED]))


@router.put(CHANNEL_PATH, response_model=ChannelView, responses=COMMON_RESPONSES)
async def configure(
    name: Name, body: ChannelAsked, request: Request, asked: Asked
) -> ChannelView | JSONResponse:
    """Keep this channel's record, and its secret first when one is given."""
    channel, wire = _managed_wire(name, asked)
    problems = tenant_problems(wire, body.tenant) + secret_problems(wire, body)
    if problems:
        return _error(422, " ".join(problems))
    actor = asked.caller.principal.id
    kept = secret_to_keep(wire, body)
    # Typed as an object: whether a wire registers its address is a question about its class.
    registering: object = wire
    if isinstance(registering, RegisteredWire):
        refused = await _register(request, channel, registering, kept, body.tenant)
        if refused is not None:
            return refused
    if kept is not None:
        try:
            await credentials_of(request).keep(
                channel_secret_slot(channel),
                kept,
                actor=actor,
                trace_id=trace_of_request(),
                ent_hash=asked.reach.ent_hash(),
            )
        except CredentialsUnavailableError as unavailable:
            return _error(_NOT_KEPT_STATUS.get(unavailable.state, 503), TOLD[unavailable.state])
        except CredentialProblemError as problem:
            return _error(422, " ".join(one.message for one in problem.problems))
    record = await records_of(request).save(
        channel,
        enabled=body.enabled,
        tenant=body.tenant,
        actor=actor,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
    )
    log.info("channel saved", channel=channel.value, enabled=record.enabled, actor=actor)
    return await _view(channel, record, secrets_of(request))


@router.post(SWITCH_PATH, response_model=ChannelView, responses=COMMON_RESPONSES)
async def switch(
    name: Name, body: SwitchAsked, request: Request, asked: Asked
) -> ChannelView | JSONResponse:
    """Switch this channel on or off. Touches this channel's record and no other."""
    channel, _ = _managed_wire(name, asked)
    actor = asked.caller.principal.id
    record = await records_of(request).switch(
        channel,
        enabled=body.enabled,
        actor=actor,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
    )
    if record is None:
        return _error(409, NO_RECORD)
    log.info("channel switched", channel=channel.value, enabled=record.enabled, actor=actor)
    return await _view(channel, record, secrets_of(request))


@router.get(DELIVERIES_PATH, response_model=DeliveriesView, responses=COMMON_RESPONSES)
async def deliveries(name: Name, request: Request, asked: Asked) -> DeliveriesView:
    """This channel's newest deliveries: what happened and why, and nothing of what was said."""
    channel, _ = _managed_wire(name, asked)
    found = await deliveries_of(request).recent(channel)
    return DeliveriesView(
        channel=channel.value,
        deliveries=[
            DeliveryRowView(
                direction=one.entry.direction,
                outcome=one.entry.outcome,
                reason=one.entry.reason,
                vendor_status=one.entry.vendor_status,
                recorded_at=one.recorded_at,
            )
            for one in found
        ],
    )


@router.post(TEST_PATH, response_model=TestView, responses=COMMON_RESPONSES)
async def test_message(name: Name, body: TestAsked, request: Request, asked: Asked) -> TestView:
    """Send a test message through this channel's vendor, once per record and destination."""
    channel, _ = _managed_wire(name, asked)
    actor = asked.caller.principal.id
    record = await records_of(request).get(channel)
    version = "none" if record is None else str(int(record.updated_at.timestamp() * 1_000_000))
    outgoing = Outgoing(
        channel=channel,
        to=body.to,
        intent=Intent(principal_id=actor, intent_ref=f"channel_test.{version}"),
        text=TEST_MESSAGE,
    )
    delivered = await _deliver(request, outgoing, record, asked.now)
    log.info(
        "channel test message",
        channel=channel.value,
        outcome=delivered.outcome.value,
        issued=delivered.issued,
        actor=actor,
    )
    return TestView(
        outcome=delivered.outcome,
        reason=delivered.reason,
        vendor_status=delivered.vendor_status,
        issued=delivered.issued,
        told=TEST_TOLD[delivered.outcome],
    )
