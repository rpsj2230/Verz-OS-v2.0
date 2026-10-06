"""The install acceptance checks for the channels themselves: what each declares and may carry,
how its health reads, how a chat account is bound and unbound, the REST API's keys, and WhatsApp.

`brain.ops.acceptance_checks` proves the webhook pipeline and `brain.ops.acceptance_checks_chat`
proves Lark answering people. What neither proved is the machinery around them, and each leaf here
was written and tested over fakes with no install ever asked: the capabilities each adapter
declares and the planner reads (M10.1.2), the ceiling a channel may carry (M10.1.3), a channel's
registration and the health its deliveries give it (M10.1.4), binding a chat account from a code
minted in a web sign-in, once (M10.3.1, M10.3.2), rebinding and unbinding (M10.3.4), a service
account's key on the REST API (M10.5.7), and a WhatsApp webhook's signature (M10.6.2).

**Every message goes through the install's own events route, on the application the chat checks
build.** `brain.ops.acceptance_checks_chat.channel_app` is the channel router over the check's
transaction with the gate the lifespan builds, and each check here sets up the channel it needs on
it: the Lark app of the chat checks, the company's own signed webhook, or WhatsApp. So a code is
redeemed, a ceiling is applied and a signature is refused by the route, the claim, the binder, the
answerer and `deliver` an install runs, and nothing is sent anywhere: every vendor is a transport
that keeps its requests. See `NOTHING_A_CHANNEL_CHECK_SENDS_LEAVES_THE_PROCESS`.

**Nothing signs in, so a route that takes a signed-in caller is driven through its own steps.**
The Channels screen's health, a person's code and an unbinding take a verified token, which the
run never holds for anybody (`brain.ops.acceptance.A_RESERVED_PRINCIPAL_CANNOT_SIGN_IN`). So the
check asks what the route asks after its gate: `brain.binding_routes.health_view` and `_rows` for
the Channels screen, the member screen's own `permitted` question, `_offered` and
`brain.channels.binding.mint_code` for a code, and `table_of`'s store for an unbinding, each over
the route's own wiring functions. A code is minted in a sign-in the check records in `auth.session`
through the directory's `standing`, which is the write the bearer path makes on a session's first
request, and handed to `mint_code` as the `Session` `open_session` builds from that request's
verified token. Rejected: a `VerifiedClaims` the check wrote, for
`brain.ops.acceptance_checks_tables.THE_ROUTES_GATE_IS_RESTATED_AND_HELD_TO_THE_ROUTES_OWN`'s
reason: the identity package constructs those from a checked signature and nothing else does.
See `A_SIGN_IN_IS_RECORDED_AND_NOTHING_IS_SIGNED_FOR_IT`.

**A service account's key is the one credential the run can present, so the REST API is asked
whole.** A key is checked by the install's own `TokenAuthority` without the identity provider's
keys, so `brain.api_routes.asking`, the dependency every route under the API prefix runs, is handed
a request carrying it and `/me` answers it; the same key revoked, and one with a character changed,
are refused there.

**What is not proved, and why.** M10.7.4 is left out: its sentence ends in an approval card offered
only where approvals are allowed, and approval cards are not built (M10.2.3), so no check could
show the whole of it. A service account is refused a binding code by the route before any step
this module drives, because its token carries no sign-in, and that refusal needs the token; it is
held by `tests/unit/test_channel_binding.py`. An administrator's unbinding is made through the
store the route uses, and the route's own question of whether the reader may manage the channel is
not asked here: it needs a grant of `admin:connector` over a channel, which is not scoped to a
reserved department (`brain.ops.acceptance.TEST_DATA_LIVES_ONLY_IN_RESERVED_DEPARTMENTS`).

Task ids: M10.1.2, M10.1.3, M10.1.4, M10.3.1, M10.3.2, M10.3.4, M10.5.7, M10.6.2
Task ids: M27.13.1
"""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import text

from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    RESERVED_PRINCIPAL_PREFIX,
    CheckFailedError,
    check,
)

# Imported rather than copied: the webhook check's in-memory secret, ledger and reading spy, and
# the chat checks' application, Lark app and uploaded table. Imported first, so the checks those
# modules declare are registered ahead of these.
from brain.ops.acceptance_checks import _HeldLedger, _in, _Secret, _Spy
from brain.ops.acceptance_checks_chat import channel_app, chat_id, lark_app, open_id, uploaded
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.requests import Request

    from brain.identity.sessions import Session
    from brain.ops.secrets import SecretRef

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 275

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why nothing these checks post or send reaches a vendor, a vault or a person.
NOTHING_A_CHANNEL_CHECK_SENDS_LEAVES_THE_PROCESS: Final = (
    "Each channel a check sets up has a secret made in memory, a record in the check's "
    "transaction and a transport that keeps every request and answers it itself, so every event, "
    "code and reply stays inside the worker. No vault slot is written, and every record, binding, "
    "code, sign-in, key and delivery the checks write is rolled back with the check."
)

#: Why a sign-in is recorded and no token is made for it.
A_SIGN_IN_IS_RECORDED_AND_NOTHING_IS_SIGNED_FOR_IT: Final = (
    "A binding code is minted in a sign-in the check records through the directory's standing, "
    "the write the bearer path makes on a session's first request, and asks every step the route "
    "takes after verifying the token. The one step not taken is verifying a token, because the "
    "run holds none for anybody, and so a claim the identity package would have checked is never "
    "written by a check."
)

# ------------------------------------------------------------------------ the figures
#: Where a webhook channel's replies would be posted: an address that resolves nowhere.
REPLY_ADDRESS: Final = "https://acceptance.invalid"

#: How long before the check a lapsed code is minted: past a code's life by a minute.
LAPSED_BY: Final = timedelta(minutes=1)

#: What a question to nobody in particular asks, so no rule or table answers it.
SMALL_TALK: Final = "what is on today"


# --------------------------------------------------------------------- the vendors
@dataclass
class _Vendor:
    """`ChannelTransport` that keeps each request and answers every send with `status`.

    A status the check can change between two messages, so one channel's vendor can accept a
    reply and then refuse the next. Nothing is sent anywhere, and nothing is read: a check here
    has no room to read.
    """

    status: int = 200
    sent: list[Any] = field(default_factory=list)

    def send(self, request: Any) -> Any:
        from brain.channels.adapter import VendorAnswer

        self.sent.append(request)
        return VendorAnswer(status=self.status)

    def read(self, request: Any) -> Any:
        from brain.channels.adapter import VendorAnswer

        del request
        return VendorAnswer(connection_failed=True)


@dataclass
class _Slot:
    """`ChannelSecrets` holding one secret in one vault slot and nothing in any other.

    So a request the route verified was verified with the slot the channel's record names: a
    route that borrowed another slot would be told it holds nothing and refuse every request.
    """

    ref: SecretRef
    value: str = field(repr=False)

    def read(self, ref: object) -> str | None:
        return self.value if ref == self.ref else None

    def held(self, ref: object) -> bool:
        return ref == self.ref


def _request(app: FastAPI, *, bearer: str = "") -> Request:
    """A request on `app`, for the route's own wiring functions, carrying a key when given one."""
    from starlette.requests import Request

    headers = [(b"authorization", f"Bearer {bearer}".encode())] if bearer else []
    return Request({"type": "http", "app": app, "headers": headers, "method": "GET"})


async def _posted(
    app: FastAPI, name: str, raw: bytes, headers: Mapping[str, str]
) -> tuple[int, dict[str, Any]]:
    """One request to the install's events address for channel `name`: the status and body."""
    import httpx

    from brain.api import API_PREFIX
    from brain.channel_routes import EVENTS_PATH

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=REPLY_ADDRESS) as client:
        answered = await client.post(
            API_PREFIX + EVENTS_PATH.format(name=name), content=raw, headers=dict(headers)
        )
    body = answered.json()
    return answered.status_code, body if isinstance(body, dict) else {}


# ------------------------------------------------------------ the company's own system
@dataclass
class _WebhookApp:
    """The webhook channel on the events route for one check, signed with a secret it made."""

    app: FastAPI
    vendor: _Vendor
    secret: str = field(repr=False)

    async def post(self, sender: str, said: str, *, signed_with: str = "") -> tuple[int, str]:
        """One message from `sender`; the status the route answered and its receipt's word."""
        from brain.channels.webhook import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign

        raw = json.dumps(
            {"id": f"acceptance-{secrets.token_hex(8)}", "sender": sender, "text": said}
        ).encode()
        stamp = str(int(time.time()))
        headers = {
            "content-type": "application/json",
            TIMESTAMP_HEADER: stamp,
            SIGNATURE_HEADER: sign(signed_with or self.secret, stamp, raw),
        }
        status, body = await _posted(self.app, "webhook", raw, headers)
        return status, str(body.get("status", ""))

    def replies(self) -> list[str]:
        """The text of every reply the route asked the company's system to take, in order."""
        return [str(json.loads(one.body)["text"]) for one in self.vendor.sent]


async def webhook_app(h: Harness) -> _WebhookApp:
    """The webhook channel set up and switched on, on the events route over the transaction."""
    from brain.channels.webhook import REPLY_URL
    from brain.gate.context import Channel
    from brain.ops.channel_store import StoredChannels

    made, vendor = secrets.token_hex(32), _Vendor()
    app = await channel_app(h, channel_secrets=_Secret(made), channel_transport=vendor)
    await StoredChannels(h.sessions).save(
        Channel.WEBHOOK,
        enabled=True,
        tenant={REPLY_URL: f"{REPLY_ADDRESS}/{h.run}"},
        actor=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    return _WebhookApp(app=app, vendor=vendor, secret=made)


# ------------------------------------------------------------------------ sign-ins
async def _signed_in(h: Harness, principal_id: str, session_id: str, at: datetime) -> Session:
    """A sign-in recorded as the bearer path records one, and the `Session` it opens. See
    `A_SIGN_IN_IS_RECORDED_AND_NOTHING_IS_SIGNED_FOR_IT`."""
    from brain.gate.admission import Assurance
    from brain.identity.bearer import SessionStanding
    from brain.identity.principal_directory import StoredDirectory
    from brain.identity.sessions import SESSION_IDLE, Session

    standing = await StoredDirectory(h.sessions).standing(
        session_id=session_id,
        principal_id=principal_id,
        assurance=Assurance.AUTHENTICATED,
        started_at=at,
        now=at,
    )
    if standing is not SessionStanding.OPEN:
        raise CheckFailedError("a reserved person's sign-in was not recorded as open")
    return Session(
        session_id=session_id,
        principal_id=principal_id,
        issuer=RESERVED_PRINCIPAL_PREFIX.rstrip("."),
        subject=principal_id,
        opened_at=at,
        expires_at=at + SESSION_IDLE,
        absolute_expiry=at + SESSION_IDLE,
    )


async def _may_open_channels(h: Harness, principal_id: str) -> None:
    """The member screen's question the person's binding routes ask, at a console sign-in."""
    from brain.binding_routes import MEMBER_CHANNELS
    from brain.console.reads import permitted
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.member.shell import member_screen

    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.AUTHENTICATED)
    if not permitted(member_screen(MEMBER_CHANNELS).read, reach, h.now):
        raise CheckFailedError("a person holding the member surface could not open their channels")


def _member_surface() -> str:
    from brain.identity.sign_in_binding import MEMBER_SURFACE

    return MEMBER_SURFACE.value


async def _bound_to(h: Harness, sender: str) -> str | None:
    """Who this Lark account is bound to on this install, or None."""
    from brain.gate.context import Channel
    from brain.gate.ingress import identity_hash
    from brain.ops.binding_store import StoredBindings

    found = await StoredBindings(h.sessions).binding_for(
        Channel.LARK, identity_hash(Channel.LARK, sender)
    )
    return None if found is None else found.principal_id


async def _sent_alone(chat: Any, sender: str, said: str) -> list[str]:
    """`said`, alone, in a new direct message from `sender`; the text of every reply it got."""
    before = len(chat.lark.sent)
    await chat.post(sender, said, chat=chat_id(), group=False, to_bot=False)
    return [one for _, _, one in chat.lark.messages()[before:]]


# ------------------------------------------------------------------ 1. capabilities
@check(
    leaves=("M10.1.2",),
    sentence=(
        "For every channel adapter the install registers, the Channels screen's health answer "
        "lists the features, ceiling and label rule the adapter declares, and a room where the "
        "asker holds more than the others is answered privately exactly on the channels that "
        "declare ephemeral messages, and with a link on the rest."
    ),
)
async def every_adapter_serves_its_declared_capabilities_and_plans_by_them(h: Harness) -> None:
    from fastapi import FastAPI

    from brain.binding_routes import health_view
    from brain.channels.adapter import Feature, adapter_for, channel_adapters
    from brain.channels.room import Member, plan
    from brain.core.entitlement import EntitlementSet

    await h.found_departments()
    asker = h.principal(A, "asker")
    await h.person(asker, department=A, grants=_in(A, "read:knowledge"))
    nobody = f"{RESERVED_PRINCIPAL_PREFIX}{h.run}.a.nobody"
    holds = await h.reach(asker)
    room = [Member(asker, holds), Member(nobody, EntitlementSet(principal_id=nobody))]
    app = FastAPI()
    app.state.db_sessions = h.sessions
    registered = [factory().capabilities().channel for factory in channel_adapters()]
    private = set()
    for channel in registered:
        view = await health_view(_request(app), channel)
        declared = adapter_for(channel).capabilities()
        served = (view.features, view.max_classification, view.can_carry_label)
        said = (
            sorted(one.value for one in declared.features),
            declared.max_classification.value,
            declared.can_carry_label,
        )
        if view.channel != channel.value or served != said:
            raise CheckFailedError("a channel's health answer was not what its adapter declares")
        aside = plan(room, asker, declared, now=h.now).aside_for == asker
        if aside != (Feature.EPHEMERAL.value in view.features):
            raise CheckFailedError(
                "a room was answered privately on a channel declaring no ephemeral messages, or "
                "with a link on one declaring them"
            )
        if aside:
            private.add(channel)
    if not private or private == set(registered):
        raise CheckFailedError(
            "the registered adapters did not include one declaring ephemeral messages and one not"
        )


# ------------------------------------------------------------------------ 2. ceilings
@check(
    leaves=("M10.1.3",),
    sentence=(
        "On the webhook channel, whose ceiling is internal, a reply marked confidential is refused "
        "and recorded as one it cannot carry with nothing sent, while one marked internal is "
        "sent; and a bound person asking for a restricted column of a table in acceptance_a is "
        "sent where to read it instead of the value, while an open column is sent."
    ),
)
async def a_reply_above_a_channels_ceiling_is_refused_and_points_to_ask(h: Harness) -> None:
    from brain.channels.binding import settle
    from brain.channels.outbound import Outgoing, deliver
    from brain.chat_answer import CEILING_TOLD
    from brain.core.field_policy import Classification
    from brain.gate.context import Channel
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.gate.ingress import Binding, identity_hash
    from brain.ops.binding_store import StoredBindings
    from brain.ops.channel_store import StoredChannels, StoredDeliveries
    from brain.ops.idempotency import Intent
    from brain.tables.channel import DeliveryOutcome, RefusedBecause

    await h.found_departments()
    chat = await webhook_app(h)
    table = await uploaded(h)
    wide, narrow = h.principal(A, "wide"), h.principal(A, "narrow")
    await h.person(wide, department=A, grants=table.reads(A, held=True))
    await h.person(narrow, department=A, grants=table.reads(A, held=False))
    record = await StoredChannels(h.sessions).get(Channel.WEBHOOK)
    deliveries, ledger = StoredDeliveries(h.sessions), _HeldLedger()
    planned = (await h.reach(wide)).ent_hash()

    async def send(n: int, highest: Classification) -> Any:
        outgoing = Outgoing(
            channel=Channel.WEBHOOK,
            to=f"acceptance-{h.run}",
            intent=Intent(principal_id=wide, intent_ref=f"acceptance.{h.run}.ceiling.{n}"),
            text="An acceptance check reply.",
            highest=highest,
            recipient=wide,
            planned_hash=planned,
        )
        return await deliver(
            outgoing,
            record=record,
            secrets=_Secret(chat.secret),
            reach=StoredEntitlements(h.sessions),
            transport=chat.vendor,
            ledger=lambda work: work(ledger),
            deliveries=deliveries,
            now=h.now,
        )

    if (await send(1, Classification.INTERNAL)).outcome is not DeliveryOutcome.SENT:
        raise CheckFailedError("a reply the channel may carry was not sent")
    above = await send(2, Classification.CONFIDENTIAL)
    if above.reason is not RefusedBecause.CANNOT_CARRY or len(chat.vendor.sent) != 1:
        raise CheckFailedError("a reply above the channel's ceiling was sent")
    newest = (await deliveries.recent(Channel.WEBHOOK))[0].entry
    if (newest.outcome, newest.reason) != (DeliveryOutcome.REFUSED, RefusedBecause.CANNOT_CARRY):
        raise CheckFailedError("a reply above the channel's ceiling was not recorded as refused")

    senders = {wide: f"acceptance-{h.run}-wide", narrow: f"acceptance-{h.run}-narrow"}
    for principal, sender in senders.items():
        fresh = Binding(
            channel=Channel.WEBHOOK,
            identity_hash=identity_hash(Channel.WEBHOOK, sender),
            principal_id=principal,
            bound_at=h.now,
        )
        kept = await StoredBindings(h.sessions).bind(
            fresh, decide=partial(settle, fresh), trace_id=h.trace_id
        )
        if kept is None:
            raise CheckFailedError("a reserved person could not be bound on the webhook channel")
    before = len(chat.vendor.sent)
    status, _ = await chat.post(senders[narrow], table.asking(table.open_column))
    open_replies = chat.replies()[before:]
    if status != 200 or len(open_replies) != 1 or table.seen not in open_replies[0]:
        raise CheckFailedError("a column the channel may carry was not sent to the person asking")
    before = len(chat.vendor.sent)
    await chat.post(senders[wide], table.asking(table.held_column))
    held_replies = chat.replies()[before:]
    if len(held_replies) != 1 or not held_replies[0].startswith(CEILING_TOLD):
        raise CheckFailedError("a column above the channel's ceiling was not answered with Ask")
    if any(table.held in one for one in chat.replies()):
        raise CheckFailedError("a value above the channel's ceiling was sent on it")


# ------------------------------------------------------------------------ 3. health
@check(
    leaves=("M10.1.4",),
    sentence=(
        "Every channel adapter the install registers is one row of the Channels list, and the "
        "webhook channel's health, read from its deliveries, is working once a message was "
        "answered, stays working when a stranger's forged request is refused, is failing once the "
        "vendor refuses a reply, and is switched off when the channel is."
    ),
)
async def each_adapter_is_listed_and_its_health_follows_its_deliveries(h: Harness) -> None:
    from brain.binding_routes import _declared, _rows, health_view
    from brain.channels.adapter import channel_adapters
    from brain.console.channel_health import ChannelHealthState
    from brain.gate.context import Channel
    from brain.ops.channel_store import StoredChannels
    from brain.tables.channel import RefusedBecause

    chat = await webhook_app(h)
    request = _request(chat.app)
    rows = await _rows(request, _declared())
    listed = [row.channel for row in rows]
    registered = {factory().capabilities().channel.value for factory in channel_adapters()}
    if len(listed) != len(set(listed)) or set(listed) != registered or len(registered) < 2:
        raise CheckFailedError("the Channels list did not show each registered adapter once")

    async def health() -> Any:
        return await health_view(request, Channel.WEBHOOK)

    status, said = await chat.post(f"acceptance-{h.run}-first", SMALL_TALK)
    if (status, said) != (200, "accepted") or len(chat.vendor.sent) != 1:
        raise CheckFailedError("a signed message was not accepted and answered")
    if (await health()).health is not ChannelHealthState.WORKING:
        raise CheckFailedError("a channel whose newest delivery went through was not working")
    status, _ = await chat.post(
        f"acceptance-{h.run}-stranger", SMALL_TALK, signed_with=secrets.token_hex(32)
    )
    if status != 401 or (await health()).health is not ChannelHealthState.WORKING:
        raise CheckFailedError("a stranger's refused request changed the channel's health")
    chat.vendor.status = 403
    await chat.post(f"acceptance-{h.run}-second", SMALL_TALK)
    failing = await health()
    fault = failing.last_fault
    if failing.health is not ChannelHealthState.FAILING or fault is None:
        raise CheckFailedError("a channel whose newest reply the vendor refused was not failing")
    if fault.reason is not RefusedBecause.VENDOR_REFUSED:
        raise CheckFailedError("a failing channel did not say the vendor refused its reply")
    off = await StoredChannels(h.sessions).switch(
        Channel.WEBHOOK, enabled=False, actor=h.actor, ent_hash="0" * 32, trace_id=h.trace_id
    )
    row = next(one for one in await _rows(request, [Channel.WEBHOOK]))
    if off is None or {(await health()).health, row.health} != {ChannelHealthState.SWITCHED_OFF}:
        raise CheckFailedError("a switched-off channel was not shown as switched off")


# ------------------------------------------------------------------------ 4. codes
@check(
    leaves=("M10.3.1", "M10.3.2", "M27.13.1"),
    sentence=(
        "A code minted in a reserved person's open sign-in and sent alone in a signed Lark direct "
        "message binds that account to them and is kept only as a digest; sent again it binds "
        "nobody, and a code past its ten minutes or one whose sign-in has ended binds nobody, "
        "each answered with the same sentence."
    ),
)
async def a_code_minted_in_an_open_sign_in_binds_one_chat_account_once(h: Harness) -> None:
    from brain.binding_routes import _offered, binding_codes_of
    from brain.channels.binding import code_digest, mint_code
    from brain.channels.inbound import CODE_REFUSED_TOLD, LINKED_TOLD
    from brain.gate.context import Channel
    from brain.gate.ingress import NONCE_TTL
    from brain.identity.session_store import StoredSessions

    await h.found_departments()
    chat = await lark_app(h)
    request = chat.request()
    if Channel.LARK not in await _offered(request):
        raise CheckFailedError("a switched-on chat channel was not offered for binding")
    people = {role: h.principal(A, role) for role in ("once", "late", "gone")}
    lapsed = h.now - NONCE_TTL - LAPSED_BY
    codes: dict[str, str] = {}
    for role, person in people.items():
        await h.person(person, department=A, grants=_in(A, _member_surface()))
        await _may_open_channels(h, person)
        at = lapsed if role == "late" else h.now
        session = await _signed_in(h, person, f"acceptance-{h.run}-{role}", at)
        minted = await mint_code(session, Channel.LARK, now=at, codes=binding_codes_of(request))
        codes[role] = minted.nonce.value
    ended = await StoredSessions(h.sessions).end(
        f"acceptance-{h.run}-gone",
        may=lambda one: True,
        ended_by=people["gone"],
        ent_hash="0" * 32,
        trace_id=h.trace_id,
        now=h.now,
    )
    if ended is None:
        raise CheckFailedError("a reserved person's sign-in could not be ended")
    kept = (
        await h.execute(
            text(
                "SELECT code_digest, channel, principal_id, session_id FROM auth.binding_code"
                " WHERE principal_id = :p"
            ).bindparams(p=people["once"])
        )
    ).all()
    stored = [str(value) for row in kept for value in row]
    if code_digest(Channel.LARK, codes["once"]) not in stored or codes["once"] in stored:
        raise CheckFailedError("a code was not kept as its digest alone")

    first = open_id()
    if await _sent_alone(chat, first, codes["once"]) != [LINKED_TOLD]:
        raise CheckFailedError("a live code sent alone in a direct message was not accepted")
    if await _bound_to(h, first) != people["once"]:
        raise CheckFailedError("a code bound a chat account to somebody other than its minter")
    for said in (codes["once"], codes["late"], codes["gone"]):
        sender = open_id()
        told = await _sent_alone(chat, sender, said)
        if await _bound_to(h, sender) is not None:
            raise CheckFailedError("a used, lapsed or signed-out code bound a chat account")
        if told != [CODE_REFUSED_TOLD]:
            raise CheckFailedError("a code that bound nobody was not answered with the one refusal")


# ------------------------------------------------------------------ 5. new devices
@check(
    leaves=("M10.3.4",),
    sentence=(
        "A reserved person binding a second Lark account with a new code has the first retired, "
        "which is then answered as bound to nobody; unbinding themselves stops the second being "
        "answered as them; an administrator unbinding a third is recorded as the administrator; "
        "and every bind and unbind is in the ledger under who made it."
    ),
)
async def a_new_device_replaces_the_old_and_unbinding_is_recorded(h: Harness) -> None:
    from brain.binding_routes import binding_codes_of, table_of
    from brain.channels.binding import mint_code
    from brain.channels.inbound import LINKED_TOLD
    from brain.gate.context import Channel
    from brain.gate.ingress import UNRECOGNISED_PROMPT

    await h.found_departments()
    chat = await lark_app(h)
    request = chat.request()
    person, admin = h.principal(A, "person"), h.principal(A, "admin")
    await h.person(person, department=A, grants=_in(A, _member_surface()))
    await h.person(admin, department=A)
    session = await _signed_in(h, person, f"acceptance-{h.run}-device", h.now)

    async def new_device() -> str:
        minted = await mint_code(session, Channel.LARK, now=h.now, codes=binding_codes_of(request))
        sender = open_id()
        if await _sent_alone(chat, sender, minted.nonce.value) != [LINKED_TOLD]:
            raise CheckFailedError("a new code from a signed-in person did not bind their account")
        return sender

    old = await new_device()
    new = await new_device()
    if await _bound_to(h, old) is not None or await _bound_to(h, new) != person:
        raise CheckFailedError("binding a new chat account did not retire the one it replaced")
    if await _sent_alone(chat, old, SMALL_TALK) != [UNRECOGNISED_PROMPT]:
        raise CheckFailedError("a retired chat account was answered as its person")
    table = table_of(request)
    theirs = await table.unbind(
        person,
        Channel.LARK,
        actor=person,
        ent_hash=(await h.reach(person)).ent_hash(),
        trace_id=h.trace_id,
    )
    if len(theirs) != 1 or await _bound_to(h, new) is not None:
        raise CheckFailedError("a person unbinding themselves did not retire their chat account")
    if await _sent_alone(chat, new, SMALL_TALK) != [UNRECOGNISED_PROMPT]:
        raise CheckFailedError("an unbound chat account was answered as its person")
    third = await new_device()
    taken = await table.unbind(
        person,
        Channel.LARK,
        actor=admin,
        ent_hash=(await h.reach(admin)).ent_hash(),
        trace_id=h.trace_id,
    )
    if len(taken) != 1 or await _bound_to(h, third) is not None:
        raise CheckFailedError("an administrator's unbinding did not retire the account")
    rows = (
        await h.execute(
            text(
                "SELECT actor_id, details FROM obs.audit_entry"
                " WHERE subject = :s AND action = 'channel_binding' ORDER BY seq"
            ).bindparams(s=f"principal:{person}")
        )
    ).all()
    entries = [
        (str(actor), details if isinstance(details, dict) else json.loads(details))
        for actor, details in rows
    ]
    written = [(actor, one.get("change"), one.get("channel")) for actor, one in entries]
    lark = Channel.LARK.value
    expected = [
        (person, "bound", lark),
        (person, "unbound", lark),
        (person, "bound", lark),
        (person, "unbound", lark),
        (person, "bound", lark),
        (admin, "unbound", lark),
    ]
    if written != expected:
        raise CheckFailedError("a bind or an unbind did not reach the ledger under who made it")


# ------------------------------------------------------------------------ 6. keys
@check(
    leaves=("M10.5.7",),
    sentence=(
        "A service account a reserved person in acceptance_a registers and keys through the "
        "store the Service accounts routes use is answered by the REST API's /me through the "
        "install's own gate at its owner's reach narrowed to its ceiling; a key with one "
        "character changed is refused, and the key is refused once revoked, in the ledger."
    ),
)
async def an_api_key_is_answered_until_it_is_revoked(h: Harness) -> None:
    from brain.api_routes import asking, me
    from brain.audit.record import credential_subject_id
    from brain.core.entitlement import Capability
    from brain.identity.oidc import TokenRefusedError
    from brain.identity.service_account_store import Registered, slot_for
    from brain.identity.sessions import ServiceAccount
    from brain.service_account_routes import store_of

    await h.found_departments()
    owner = h.principal(A, "integrator")
    ceiling, beyond = "read:knowledge", "read:knowledge.title"
    await h.person(owner, department=A, grants=_in(A, ceiling, beyond))
    app = await channel_app(h, channel_secrets=_Secret(""), channel_transport=_Vendor())
    store = store_of(_request(app))
    client_id = f"svc_acceptance_{h.run}"
    lapses = h.now + timedelta(minutes=30)
    by = {"ent_hash": (await h.reach(owner)).ent_hash(), "trace_id": h.trace_id}
    account = ServiceAccount(
        client_id=client_id,
        subject=client_id,
        owner_principal_id=owner,
        ceiling=(Capability(value=ceiling),),
        not_after=lapses,
    )
    if await store.register(account, subject=None, label="Acceptance check", **by) is not (
        Registered.REGISTERED
    ):
        raise CheckFailedError("a reserved person could not register a service account")
    minted = await store.issue_key(
        client_id, owner=owner, not_after=lapses, label="Acceptance check", now=h.now, **by
    )
    if minted is None:
        raise CheckFailedError("a service account's owner could not issue it a key")

    asked = await asking(_request(app, bearer=minted.secret))
    answered = await me(asked)
    if (answered.principal_id, answered.channel) != (client_id, "api"):
        raise CheckFailedError("a live key was not answered by the REST API as its account")
    now = datetime.now(UTC)
    narrowed = asked.reach.scope_for(Capability(value=beyond), now) is None
    if asked.reach.scope_for(Capability(value=ceiling), now) is None or not narrowed:
        raise CheckFailedError("a key was not answered at its owner's reach within its ceiling")

    async def refused(presented: str) -> bool:
        try:
            await asking(_request(app, bearer=presented))
        except TokenRefusedError:
            return True
        return False

    changed = minted.secret[:-1] + ("A" if minted.secret[-1] != "A" else "B")
    if not await refused(changed):
        raise CheckFailedError("a key with one character changed was answered")
    if not await store.revoke_key(minted.record.handle, owner=owner, **by):
        raise CheckFailedError("a live key could not be revoked by its account's owner")
    if not await refused(minted.secret):
        raise CheckFailedError("a revoked key was answered")
    rows = (
        await h.execute(
            text(
                "SELECT actor_id, details FROM obs.audit_entry"
                " WHERE subject = :s AND action = 'credential' ORDER BY seq"
            ).bindparams(s=f"credential:{credential_subject_id(slot_for(client_id))}")
        )
    ).all()
    last = rows[-1] if rows else None
    details = {} if last is None else last[1]
    change = (details if isinstance(details, dict) else json.loads(details)).get("change")
    if len(rows) < 3 or last is None or (str(last[0]), change) != (owner, "key_revoked"):
        raise CheckFailedError("registering, keying and revoking did not reach the ledger")


# ------------------------------------------------------------------------ 7. WhatsApp
def whatsapp_message(sender: str, said: str, *, phone_number_id: str = "0") -> dict[str, Any]:
    """One text message as the WhatsApp Cloud API posts it to a webhook, about `phone_number_id`.

    Written from Meta's documented shape for a received text message (the `messages` field of a
    `whatsapp_business_account` change), not from `brain.channels.whatsapp`, so a wire that read
    it wrongly is refused here as it would be by Meta's own bytes. Every id is one no account
    holds.
    """
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "0",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "0",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": "Acceptance"}, "wa_id": sender}],
                            "messages": [
                                {
                                    "from": sender,
                                    "id": f"wamid.acceptance{secrets.token_hex(16)}",
                                    "timestamp": str(int(time.time())),
                                    "text": {"body": said},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def a_number() -> str:
    """A WhatsApp number no person holds: country code 999 is reserved and assigned to nobody."""
    return f"999{secrets.randbelow(10**9):09d}"


@check(
    leaves=("M10.6.2",),
    sentence=(
        "WhatsApp message bytes posted to the events address are accepted and claimed once when "
        "signed with the app secret the record's slot holds, and refused unread when unsigned, "
        "signed with another secret, altered by one byte, or signed over the same JSON written "
        "again; the sender is answered once from the record's number, kept rather than sent."
    ),
)
async def a_whatsapp_webhook_is_accepted_only_under_its_app_secret(h: Harness) -> None:
    from brain.channels.adapter import channel_wires
    from brain.channels.inbound import receive
    from brain.channels.whatsapp import (
        ACCESS_TOKEN,
        APP_SECRET,
        GRAPH_API_URL,
        GRAPH_API_VERSION,
        PHONE_NUMBER_ID,
        SIGNATURE_HEADER,
        VERIFY_TOKEN,
        signature_for,
    )
    from brain.gate.context import Channel
    from brain.ops.channel_store import (
        StoredChannels,
        StoredClaims,
        StoredDeliveries,
        channel_secret_ref,
    )
    from brain.tables.channel import RefusedBecause

    app_secret, vendor = secrets.token_hex(32), _Vendor()
    kept = {APP_SECRET: app_secret, ACCESS_TOKEN: secrets.token_hex(24), VERIFY_TOKEN: "v"}
    slot = _Slot(channel_secret_ref(Channel.WHATSAPP), json.dumps(kept))
    app = await channel_app(h, channel_secrets=slot, channel_transport=vendor)
    number = f"10{secrets.randbelow(10**10):010d}"
    record = await StoredChannels(h.sessions).save(
        Channel.WHATSAPP,
        enabled=True,
        tenant={PHONE_NUMBER_ID: number},
        actor=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    said = h.word()
    message = whatsapp_message(a_number(), said, phone_number_id=number)
    raw = json.dumps(message).encode()
    wamid = message["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
    # One byte of the question changed, so the altered bytes are a message the wire would read.
    altered = raw.replace(said.encode(), f"{said[0].lower()}{said[1:]}".encode(), 1)
    again = json.dumps(message, separators=(",", ":")).encode()

    async def post(body: bytes, signature: str | None) -> tuple[int, str]:
        headers = {"content-type": "application/json"}
        if signature is not None:
            headers[SIGNATURE_HEADER] = signature
        status, answered = await _posted(app, Channel.WHATSAPP.value, body, headers)
        return status, str(answered.get("status", ""))

    async def claimed() -> int:
        found = await h.execute(
            text(
                "SELECT count(*) FROM gate.channel_event WHERE channel = :c AND external_id = :e"
            ).bindparams(c=Channel.WHATSAPP.value, e=wamid)
        )
        return int(found.scalar_one())

    forged = (
        (raw, None),
        (raw, signature_for(secrets.token_hex(32), raw)),
        (altered, signature_for(app_secret, raw)),
        (raw, signature_for(app_secret, again)),
    )
    for body, signature in forged:
        if (await post(body, signature))[0] != 401:
            raise CheckFailedError("an unsigned, forged, altered or rewritten request was taken")
    spy = _Spy(channel_wires()[Channel.WHATSAPP])

    async def the_altered_bytes() -> bytes:
        return altered

    unread = await receive(
        spy,
        record=record,
        headers={SIGNATURE_HEADER: signature_for(app_secret, raw)},
        declared_length=len(altered),
        body=the_altered_bytes,
        secrets=slot,
        claims=StoredClaims(h.sessions),
        deliveries=StoredDeliveries(h.sessions),
        now=h.now,
    )
    if unread.reason is not RefusedBecause.BAD_SIGNATURE or spy.reads or await claimed():
        raise CheckFailedError("an altered WhatsApp request was read before it was refused")
    if await post(raw, signature_for(app_secret, raw)) != (200, "accepted"):
        raise CheckFailedError("a request signed with the app secret was not accepted")
    if await post(raw, signature_for(app_secret, raw)) != (200, "redelivered") or (
        await claimed() != 1
    ):
        raise CheckFailedError("a signed WhatsApp message and its redelivery were not claimed once")
    answered = f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{number}/messages"
    if [one.url for one in vendor.sent] != [answered]:
        raise CheckFailedError("the sender was not answered once, from the record's number")
